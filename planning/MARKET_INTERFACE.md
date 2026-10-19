# Unified Market Data Interface

How FinAlly code gets stock prices — real-time and end-of-day, for many tickers — without
knowing whether Tapetide or the simulator is behind it. Companion docs:
`TAPETIDE_API.md` (the real provider) and `MARKET_SIMULATOR.md` (the fake one).

**Status.** The *streaming* half (sections 2-3) is **built** in `backend/app/market/` and is
summarized here for context. The *pull* half (sections 4-8: `get_quotes`, `get_daily_bars`,
`DailyBar`, the EOD cache) is a **design to implement**; nothing in sections 4-8 exists yet.
Where this doc conflicts with PLAN.md, PLAN.md wins; raise the conflict rather than silently
diverging.

## 1. Goals and non-goals

Goals

1. One import surface for all price needs: live quotes, end-of-day bars, ticker validation.
2. Selection rule: **Tapetide when `TAPETIDE_API_KEY` is set, otherwise the simulator** —
   refined by the existing trading-hours rule for live quotes (section 3).
3. Identical shapes from both sources, so callers never branch on source.
4. Respect Tapetide's quota: batch, cache, never poll history.
5. A failed provider must degrade, not crash (PLAN.md §6 fallback).

Non-goals: intraday bars, order books, multi-user, any exchange other than NSE.

## 2. Two access patterns, one cache

| Pattern | Used by | API | Backing |
|---|---|---|---|
| **Push / streaming** | SSE, portfolio valuation, trade fills | `PriceCache.get/get_all` | Background task writes every 0.5s (sim) or 2s (Tapetide). |
| **Pull / on demand** | Watchlist validation, AI analysis, anything wanting history | `MarketData.get_quotes`, `MarketData.get_daily_bars` | Cache first, provider on a miss. |

Streaming stays exactly as built: `MarketDataSource` (`start/stop/add_ticker/remove_ticker/
get_tickers/validate_ticker`) writes into `PriceCache`; `MarketDataManager` owns the active
source and swaps on a 60s supervisor tick; the cache is never replaced. Do not change this.

The pull API is a **facade over the same cache and the same manager**, plus a new optional
capability for history. It adds no second connection to Tapetide for live data.

```
                    ┌──────────────────────────────────────────┐
 callers ─────────▶ │ MarketData (facade)    market/api.py     │
 (routes, LLM,      │  get_quotes()  get_daily_bars()          │
  portfolio)        │  get_latest_closes()  validate_ticker()  │
                    └───────┬───────────────────┬──────────────┘
                            │ live              │ history
                            ▼                   ▼
                 PriceCache ◀── MarketDataManager      EodCache (TTL, in-memory)
                            ▲        │                      │ miss
                 SSE reads  │        ▼                      ▼
                            └── active MarketDataSource   HistoricalSource
                               (Simulator | Tapetide)     (SimulatedHistory | TapetideHistory)
```

## 3. Source selection

Two independent decisions, because live quotes and history have different constraints:

| Question | Rule | Why |
|---|---|---|
| Live quotes | `MARKET_DATA_SOURCE` override, else key set **and** NSE open → Tapetide, else simulator. **Unchanged** (`factory.py`). | Tapetide quotes do not move outside 9:15-15:30 IST. |
| History / EOD | `MARKET_DATA_SOURCE=simulator` → simulated; else key set → Tapetide (any time of day, any weekday); else simulated. | History is meaningful when the market is closed, and a closed market is exactly when you want yesterday's close. |

So at 9pm with a key set: live quotes come from the simulator, daily bars from Tapetide. That is
intended. Callers see only `Quote.source` / `DailyBar.source` if they care.

`MARKET_DATA_SOURCE=tapetide` without a key still fails fast (existing behavior). If Tapetide
history fails (transport error), fall back to simulated bars **and mark them**
`source="simulated"` so the UI/LLM can say so; never silently mix.

New helper in `factory.py`:

```python
def create_historical_source() -> "HistoricalSource":
    override = os.environ.get("MARKET_DATA_SOURCE", "auto").strip().lower()
    api_key = os.environ.get("TAPETIDE_API_KEY", "").strip()
    if override == "simulator" or (override != "tapetide" and not api_key):
        return SimulatedHistory()
    if not api_key:
        raise RuntimeError("MARKET_DATA_SOURCE=tapetide requires TAPETIDE_API_KEY to be set")
    return TapetideHistory(api_key=api_key)
```

## 4. Data models (`market/models.py`, additions)

Live quote: **reuse `PriceUpdate`** — it already is the cross-source quote (price, previous
tick, previous close, timestamp, derived day change and direction). Do not invent a second type.
It gains one optional field for provenance only if a caller needs it; until then the facade
returns `PriceUpdate` and exposes `MarketData.active_source_name`.

New, for history:

```python
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DailyBar:
    """One end-of-day OHLCV bar. Prices in rupees, unadjusted unless the provider says otherwise."""

    ticker: str          # normalized: strip().upper(), the REQUESTED symbol
    day: date            # trading date (IST), not a timestamp
    open: float          # Tapetide: split/bonus-adjusted (dividends not adjusted)
    high: float
    low: float
    close: float         # Tapetide: split/bonus-adjusted close
    raw_close: float | None  # the actual printed close; None if no raw print exists
    volume: int | None   # unadjusted; None if the provider omits it
    source: str          # "tapetide" | "simulated"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "date": self.day.isoformat(),
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume, "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class DailyBars:
    """Result for one ticker. `truncated` is True if the provider returned less than asked."""

    ticker: str
    bars: list[DailyBar]          # ascending by day, unique days
    truncated: bool = False
    error: str | None = None      # per-ticker failure; other tickers are unaffected
```

Invariants every provider must satisfy (tested identically against both):
`bars` ascending by `day` with unique days; `high >= max(open, close)`; `low <= min(open,
close)`; all prices `> 0`; `low <= high`; weekdays only.

Adjusted vs raw: Tapetide's `close`/OHLC are back-adjusted for splits and bonuses, so old bars
do not match what was printed then. Live prices and `prev_close` are raw. Anything comparing a
bar to a live price (e.g. `get_latest_closes`) must use `raw_close`, never `close`. The
simulator produces unadjusted bars and sets `raw_close == close`. Tapetide does not return
delivery %, so there is no such field.

## 5. Interfaces

### 5.1 `HistoricalSource` (new ABC, `market/history.py`)

```python
from abc import ABC, abstractmethod
from datetime import date


class HistoricalSource(ABC):
    @abstractmethod
    async def get_daily_bars(
        self, ticker: str, start: date, end: date
    ) -> DailyBars:
        """Daily bars for one ticker, inclusive range, ascending.

        Raises MarketDataError only on transport failure. An unknown ticker returns
        DailyBars(ticker, [], error="unknown ticker"), not an exception.
        """

    async def close(self) -> None:  # optional resource release
        return None
```

One ticker per call is the **provider** contract because Tapetide has no batch history tool.
Multi-ticker fan-out lives in the facade (5.2), once, not in each provider.

`MarketDataSource` is untouched. History deliberately is **not** added to it: the live sources
hold a long-lived poller and an MCP session; history is bursty, cacheable and independent.

### 5.2 `MarketData` facade (`market/api.py`)

```python
class MarketData:
    def __init__(
        self,
        manager: MarketDataManager,
        cache: PriceCache,
        history: HistoricalSource | None = None,
        eod_cache: EodCache | None = None,
        max_concurrency: int = 4,
    ) -> None: ...

    # ---- live ---------------------------------------------------------
    async def get_quotes(self, tickers: list[str]) -> dict[str, PriceUpdate | None]:
        """Latest price per ticker. Tracked tickers: read from PriceCache (free).
        Missing key => ticker is untracked or not priced yet => value None.
        Never calls the provider; to price an untracked ticker add it to the watchlist first
        (PLAN.md §8: a trade or quote requires a tracked ticker)."""

    async def validate_ticker(self, ticker: str) -> bool:
        """Delegates to the manager (Tapetide found:false / simulator universe).
        Raises MarketDataError on transport failure (=> API 503)."""

    # ---- end of day ---------------------------------------------------
    async def get_daily_bars(
        self, tickers: list[str], start: date, end: date | None = None
    ) -> dict[str, DailyBars]:
        """Daily bars for many tickers. Cache first; misses fetched concurrently
        (bounded by max_concurrency). One failing ticker yields DailyBars(error=...) and does not
        fail the batch."""

    async def get_latest_closes(self, tickers: list[str]) -> dict[str, float | None]:
        """Most recent completed close per ticker, cheaply.
        Reads PriceCache.previous_close (batched, already paid for). Falls back to
        get_daily_bars(last 5 days) only for tickers not in the cache."""

    @property
    def active_source_name(self) -> str: ...      # live source: 'tapetide' | 'simulator'
```

Design notes:

- `get_quotes` reads the cache rather than hitting Tapetide. This is the quota-safe answer to
  "real-time prices for multiple tickers": the poller already fetches the whole tracked set in
  one call per cycle, so a pull of 10 tickers costs **zero** extra calls.
- Untracked tickers are *not* fetched ad hoc. An on-demand one-shot would burn quota and break the
  invariant "priced == tracked" (PLAN.md §6). Callers that need a price call `add_ticker` (via
  the validated watchlist path) first.
- `end` defaults to today in IST. A request whose `end` is today during market hours returns
  bars through *yesterday*; today's partial bar is not an end-of-day price. Documented, tested.
- Inputs are normalized once at the facade: `strip().upper()`, de-duplicated preserving order.

### 5.3 `EodCache`

```python
@dataclass
class _Entry:
    bars: DailyBars
    fetched_at: float


class EodCache:
    """In-memory, keyed (ticker, start, end, source). Daily data is immutable once the day closes,
    so TTL is long once the range ends before today and short otherwise."""

    CLOSED_RANGE_TTL = 24 * 3600
    OPEN_RANGE_TTL = 15 * 60

    def get(self, key: tuple) -> DailyBars | None: ...
    def put(self, key: tuple, bars: DailyBars, *, range_closed: bool) -> None: ...
```

Cache errors are not stored (a failed fetch must retry), except a definitive
`error="unknown ticker"` which gets a short TTL (60s) to stop a hot loop re-asking.

In-memory only for v1: a restart re-spends a few calls. If this becomes a quota problem, persist
to a new SQLite table `eod_bars(ticker, day, o, h, l, c, v, source)` — an explicit schema change
needing a PLAN.md §7 update, so **not** done here.

## 6. Implementations

### 6.1 `TapetideHistory` (`market/tapetide_history.py`)

- Opens its **own short-lived MCP client per `get_daily_bars` batch**, not the poller's. Reason:
  the poller's client is serialized behind one lock for 2s cadence quotes; a 10-ticker history
  fan-out sharing it would stall live prices. A separate session costs an extra connection
  handshake but no quota (handshake is not a tool call). **[unverified: confirm handshake
  does not count against quota.]**
- Calls `get_price_history` (`symbol`, `days`, `end_date`, `interval="daily"`), pages with
  `meta.window.next_cursor` while `truncated`, then trims to `[start, end]`.
- `days` is **calendar days** back from `end_date` (verified live: `days: 5` returned 3 bars), so
  pass `days = (end - start).days + 1`, clamped to 2000, with `end_date = end`, and page with
  `meta.window.next_cursor` per `TAPETIDE_API.md` section 5.3.
- Row keys (verified live): `date, open, high, low, close, raw_close, volume`.

```python
class TapetideHistory(HistoricalSource):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_daily_bars(self, ticker: str, start: date, end: date) -> DailyBars:
        try:
            async with self._client() as client:
                rows, truncated = await self._fetch(client, ticker, start, end)
        except Exception as e:
            raise MarketDataError(f"Tapetide history failed for {ticker}: {e}") from e
        bars = [b for r in rows if (b := self._parse_bar(ticker, r)) and start <= b.day <= end]
        bars = sorted({b.day: b for b in bars}.values(), key=lambda b: b.day)
        return DailyBars(ticker=ticker, bars=bars, truncated=truncated)

    @staticmethod
    def _parse_bar(ticker: str, row: dict) -> DailyBar | None:
        try:
            return DailyBar(
                ticker=ticker,
                day=date.fromisoformat(str(row["date"])[:10]),
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                raw_close=float(rc) if (rc := row.get("raw_close")) is not None else None,
                volume=int(v) if (v := row.get("volume")) is not None else None,
                source="tapetide",
            )
        except (KeyError, TypeError, ValueError):
            return None   # skip malformed row, caller logs the count
```

`_client()` and `_fetch()` are the section 5.1/5.3 snippets from `TAPETIDE_API.md`.

An unknown symbol makes `get_price_history` raise a tool error whose text starts with
`Stock not found` (verified live). Map exactly that to `DailyBars(error="unknown ticker")`; any
other exception is a transport failure and becomes `MarketDataError`. (Batch quotes behave
differently: `found: false`, no error.)

### 6.2 `SimulatedHistory` (`market/sim_history.py`)

Deterministic synthetic daily bars from the same parameters as the live simulator. Algorithm
and rationale are in `MARKET_SIMULATOR.md` section 7. Interface-relevant properties:

- **Deterministic**: same `(ticker, day)` gives the same bar on every call and across restarts.
  No state, no DB. This makes tests trivial and the cache optional.
- **Anchored**: the most recent bar's close equals the live simulator's seed price
  (`SEED_PRICES`), so history joins up with the live price.
- Never raises `MarketDataError`.
- Unknown ticker (not in `NSE_SYMBOL_UNIVERSE`) returns `DailyBars(error="unknown ticker")`, same
  as validation.

## 7. Error semantics (shared with PLAN.md §6, §8)

| Condition | Live (`get_quotes`) | History (`get_daily_bars`) |
|---|---|---|
| Unknown ticker | `None` for that key | `DailyBars(error="unknown ticker")` |
| Tracked, no price yet | `None` | n/a |
| Provider unreachable | cache keeps serving last price; health flag goes false | `MarketDataError` from provider is **caught in the facade**: fall back to simulated bars with `source="simulated"`, log a warning |
| Bad input (empty list, `start > end`) | `ValueError` | `ValueError` (API layer maps to 400) |

Transport failure is never an "invalid symbol" (503, not 400).

## 8. Wiring and usage

`main.py` lifespan builds one of each and puts the facade on `app.state`:

```python
cache = PriceCache()
manager = MarketDataManager(cache)
await manager.start(sorted(watchlist | held))           # unchanged
market = MarketData(manager, cache, history=create_historical_source())
app.state.market = market
...
await market.aclose()   # closes history source; manager.stop() as before
```

Callers:

```python
quotes = await market.get_quotes(["HDFCBANK", "INFY"])
price = quotes["HDFCBANK"].price if quotes["HDFCBANK"] else None

bars = await market.get_daily_bars(["HDFCBANK", "INFY", "TCS"], start=date(2026, 9, 1))
for t, res in bars.items():
    print(t, res.error or f"{len(res.bars)} bars, last close {res.bars[-1].close}")

closes = await market.get_latest_closes(["HDFCBANK", "INFY"])
```

Candidate consumers (not part of this task): `GET /api/portfolio` could show "since last
close"; the LLM context (PLAN.md §9) could include 5-day closes; a future price-history
endpoint would remove the "main chart is live-since-load" limitation (PLAN.md §13). Adding
any endpoint requires a PLAN.md §8 update first.

## 9. File layout

```
backend/app/market/
  models.py             + DailyBar, DailyBars
  history.py            HistoricalSource ABC, EodCache
  tapetide_history.py   TapetideHistory
  sim_history.py        SimulatedHistory
  api.py                MarketData facade
  factory.py            + create_historical_source()
  __init__.py           export MarketData, DailyBar, DailyBars, HistoricalSource
```

## 10. Tests required (pytest, `backend/tests/market/`)

- Provider contract suite parametrized over `SimulatedHistory` and `TapetideHistory` (MCP client
  mocked): ascending/unique, OHLC invariants, range trimming, weekday-only.
- `TapetideHistory`: paging across `truncated`/`next_cursor`; malformed row skipped; transport
  error raises `MarketDataError`; days clamp at 2000.
- Selection: key unset, key set, `MARKET_DATA_SOURCE` = simulator / tapetide-without-key; key set
  outside trading hours still gives Tapetide history but simulator live source.
- Facade: dedupe + normalization; one failing ticker does not fail the batch; concurrency bound
  respected; cache hit makes zero provider calls; Tapetide failure falls back to
  `source="simulated"`; `get_quotes` makes zero provider calls; `end=today` excludes the partial
  day.
- `get_latest_closes` prefers `previous_close` from the cache.

## 11. Open questions

Resolved by live checks on 2026-10-19 (see `TAPETIDE_API.md`): response keys and `meta` shape;
unknown-symbol behavior; calendar-day semantics of `days`; split/bonus adjustment (`raw_close`
provided).

Still open (need the real key and the Tapetide dashboard quota counter):

1. Behavior and error text on quota exhaustion.
2. Whether history calls and MCP handshakes count against the 400/day plan, and whether a
   history call costs more than one unit.
3. Refresh cadence of `updated_at` (quotes looked a couple of minutes behind wall clock), which
   decides whether 2s polling is worth its quota.
4. Mixed-source charts show a seam at any corporate action, since the simulator's bars are
   unadjusted; state it in the UI if history is ever charted.
