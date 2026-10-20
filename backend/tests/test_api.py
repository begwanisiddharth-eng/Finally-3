"""API integration tests: drive the real app (simulator + mock LLM) through
the HTTP layer with FastAPI's TestClient, which runs the lifespan so the
database, market manager, and snapshot task are all live."""

import pytest
from fastapi.testclient import TestClient

DEFAULT_WATCHLIST = [
    "HEROMOTOCO", "BEL", "PIDILITIND", "LTF", "HDFCBANK",
    "INFY", "RELIANCE", "TCS", "ICICIBANK", "TATAMOTORS",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("MARKET_DATA_SOURCE", "simulator")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TAPETIDE_API_KEY", "")
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["data_source"] == "simulator"
    assert body["market_data_healthy"] is True


def test_default_watchlist_order_and_prices(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    tickers = r.json()["tickers"]
    assert [t["ticker"] for t in tickers] == DEFAULT_WATCHLIST
    # Simulator seeds the cache on start, so prices are present immediately.
    assert all(t["price"] is not None for t in tickers)


def test_starting_cash(client):
    r = client.get("/api/portfolio")
    assert r.json()["cash_balance"] == 1000000.0
    assert r.json()["positions"] == []


def test_watchlist_add_valid_invalid_duplicate(client):
    # Valid symbol from the simulator universe.
    r = client.post("/api/watchlist", json={"ticker": "wipro"})
    assert r.status_code == 200
    assert r.json()["ticker"] == "WIPRO"
    assert "WIPRO" in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]

    # Duplicate is idempotent 200.
    assert client.post("/api/watchlist", json={"ticker": "WIPRO"}).status_code == 200

    # Unrecognized symbol -> 400 with error envelope.
    r = client.post("/api/watchlist", json={"ticker": "ZZZZINVALID"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_watchlist_capped_at_20(client):
    # 10 are seeded; add 10 more valid symbols to reach the cap of 20.
    extras = ["WIPRO", "SBIN", "AXISBANK", "KOTAKBANK", "LT",
              "MARUTI", "SUNPHARMA", "TITAN", "ITC", "NTPC"]
    for sym in extras:
        assert client.post("/api/watchlist", json={"ticker": sym}).status_code == 200
    assert len(client.get("/api/watchlist").json()["tickers"]) == 20

    # The 21st new ticker is rejected with the cap message.
    r = client.post("/api/watchlist", json={"ticker": "ONGC"})
    assert r.status_code == 400
    assert r.json()["error"] == "The watchlist can only contain 20 shares"

    # Re-adding an already-watched ticker is still an idempotent success at the cap.
    assert client.post("/api/watchlist", json={"ticker": "WIPRO"}).status_code == 200


def test_watchlist_delete_idempotent(client):
    r = client.delete("/api/watchlist/HDFCBANK")
    assert r.status_code == 200 and r.json()["removed"] is True
    # Deleting again -> still 200, removed False.
    r = client.delete("/api/watchlist/HDFCBANK")
    assert r.status_code == 200 and r.json()["removed"] is False


def test_buy_updates_cash_and_positions(client):
    before = client.get("/api/portfolio").json()["cash_balance"]
    r = client.post("/api/portfolio/trade", json={"ticker": "HDFCBANK", "side": "buy", "quantity": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["trade"]["ticker"] == "HDFCBANK"
    assert body["trade"]["side"] == "buy"
    portfolio = body["portfolio"]
    assert portfolio["cash_balance"] < before
    pos = [p for p in portfolio["positions"] if p["ticker"] == "HDFCBANK"]
    assert pos and pos[0]["quantity"] == 10


def test_sell_to_zero_removes_position(client):
    client.post("/api/portfolio/trade", json={"ticker": "INFY", "side": "buy", "quantity": 5})
    r = client.post("/api/portfolio/trade", json={"ticker": "INFY", "side": "sell", "quantity": 5})
    assert r.status_code == 200
    tickers = [p["ticker"] for p in r.json()["portfolio"]["positions"]]
    assert "INFY" not in tickers


def test_trade_untracked_ticker_rejected(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "SBIN", "side": "buy", "quantity": 1})
    assert r.status_code == 400
    assert "watchlist" in r.json()["error"].lower()


def test_trade_bad_quantity_rejected(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "HDFCBANK", "side": "buy", "quantity": 0})
    assert r.status_code == 400
    assert "error" in r.json()


def test_insufficient_cash_rejected(client):
    r = client.post(
        "/api/portfolio/trade", json={"ticker": "TCS", "side": "buy", "quantity": 1000000}
    )
    assert r.status_code == 400
    assert "cash" in r.json()["error"].lower()


def test_insufficient_shares_rejected(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "BEL", "side": "sell", "quantity": 1})
    assert r.status_code == 400
    assert "shares" in r.json()["error"].lower()


def test_history_has_startup_snapshot(client):
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert r.json()[0]["total_value"] == 1000000.0


def test_trades_listed_most_recent_first(client):
    client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 1})
    client.post("/api/portfolio/trade", json={"ticker": "TCS", "side": "buy", "quantity": 1})
    trades = client.get("/api/portfolio/trades").json()
    assert trades[0]["ticker"] == "TCS"


def test_chat_mock_executes_buy(client):
    r = client.post("/api/chat", json={"message": "please buy HDFCBANK"})
    assert r.status_code == 200
    body = r.json()
    assert body["actions"]
    trade_actions = [a for a in body["actions"] if a["type"] == "trade"]
    assert trade_actions and trade_actions[0]["status"] == "executed"
    # The position now exists via the chat-driven trade.
    positions = client.get("/api/portfolio").json()["positions"]
    assert "HDFCBANK" in [p["ticker"] for p in positions]


def test_chat_mock_add_and_remove_watchlist(client):
    r = client.post("/api/chat", json={"message": "add WIPRO to my list"})
    assert any(a["type"] == "watchlist" and a["status"] == "executed" for a in r.json()["actions"])
    assert "WIPRO" in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]

    r = client.post("/api/chat", json={"message": "remove WIPRO"})
    assert any(a["action"] == "remove" for a in r.json()["actions"])
    assert "WIPRO" not in [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]]


def test_chat_history_persists(client):
    client.post("/api/chat", json={"message": "hello there"})
    history = client.get("/api/chat/history").json()
    assert len(history) >= 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_chat_no_sebi_disclaimer_under_simulator(client):
    r = client.post("/api/chat", json={"message": "how is my portfolio"})
    assert "SEBI" not in r.json()["message"]


def test_watchlist_add_transport_failure_returns_503(client, monkeypatch):
    from app.market import MarketDataError

    async def _raise(_ticker):
        raise MarketDataError("unreachable")

    monkeypatch.setattr(client.app.state.manager, "validate_ticker", _raise)
    r = client.post("/api/watchlist", json={"ticker": "NEWSYM"})
    assert r.status_code == 503
    assert "error" in r.json()


def test_chat_appends_sebi_disclaimer_under_tapetide(client, monkeypatch):
    from app.market import MarketDataManager

    # Force the active-source label to 'tapetide' so the disclaimer is appended.
    monkeypatch.setattr(
        MarketDataManager, "active_source_name", property(lambda self: "tapetide")
    )
    r = client.post("/api/chat", json={"message": "how is my portfolio"})
    assert "SEBI-registered" in r.json()["message"]


def test_chat_upstream_failure_returns_502_and_persists_nothing(client, monkeypatch):
    # Simulate Groq timing out / erroring / returning unparseable output.
    import app.chat as chat_mod

    async def _boom(*_args, **_kwargs):
        raise chat_mod.ChatError("upstream exploded")

    monkeypatch.setattr(chat_mod, "_generate", _boom)

    before = len(client.get("/api/chat/history").json())
    r = client.post("/api/chat", json={"message": "how is my portfolio"})
    assert r.status_code == 502
    assert "error" in r.json()
    # No chat_messages row is written on an upstream failure (section 8).
    after = len(client.get("/api/chat/history").json())
    assert after == before


def test_reset_restores_first_launch_state(client):
    # Dirty the state: add a ticker, buy a share, send a chat message.
    client.post("/api/watchlist", json={"ticker": "WIPRO"})
    client.post("/api/portfolio/trade", json={"ticker": "HDFCBANK", "side": "buy", "quantity": 2})
    client.post("/api/chat", json={"message": "how is my portfolio"})

    assert client.get("/api/portfolio").json()["positions"]
    assert client.get("/api/portfolio/trades").json()
    assert client.get("/api/chat/history").json()

    r = client.post("/api/reset")
    assert r.status_code == 200

    # Cash restored, no positions, default watchlist, no trades, blank chat.
    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash_balance"] == 1000000.0
    assert portfolio["positions"] == []
    assert [t["ticker"] for t in client.get("/api/watchlist").json()["tickers"]] == DEFAULT_WATCHLIST
    assert client.get("/api/portfolio/trades").json() == []
    assert client.get("/api/chat/history").json() == []
    # A fresh snapshot is taken so the P&L chart has a point.
    assert len(client.get("/api/portfolio/history").json()) >= 1
