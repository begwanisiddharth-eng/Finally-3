# Tapetide API Reference (Real-Time and End-of-Day Prices)

Reference for how FinAlly gets real NSE prices from Tapetide. Written for agents implementing
or extending `backend/app/market/tapetide_client.py`.

## Provenance and confidence

Tapetide's own docs pages were **not reachable** from the research sandbox (outbound network
policy blocked `tapetide.com`, `mcp.tapetide.com` and `glama.ai`). The first draft of this
document therefore relied on search summaries; it was then **checked against live tool calls**
(4 calls: a 3-symbol batch quote incl. one bad symbol, `get_price_history` for 5 days, for an
unknown symbol, and for a 3000-day request with `end_date`) plus Tapetide's own `read_me` guide.
Several corrections resulted (response keys, UTC timestamps, calendar-day `days`, no delivery %, adjusted vs raw prices, unknown-symbol behavior) and are folded in below. Facts come from four sources, and each
section says which applies:

| Tag | Meaning |
|---|---|
| **[verified-in-repo]** | Taken from working code and tests in this repo (`tapetide_client.py`, `backend/tests/market/test_tapetide.py`), which was written against live responses (seed prices were fetched from Tapetide on 2026-10-16). |
| **[verified-live]** | Observed in live calls to Tapetide's MCP tools on 2026-10-19 (a Monday, ~14:00 IST, market open), made through the Tapetide MCP tools attached to the research session. These are the same tools and server the backend calls. |
| **[listing]** | Reported by third-party directory listings and search summaries of Tapetide's tool pages (Glama, GitHub README, mcp.tapetide.com), not confirmed against a live call. |
| **[unverified]** | Inferred or not found. Must be checked with a live call before relying on it. |

Anything still tagged **[listing]** or **[unverified]** was not settled by the live checks.
Note that live checks went through the MCP tools attached to the research session, **not
through `TAPETIDE_API_KEY` over the bearer-token HTTP path** the backend uses; the tool schemas
and payloads should be identical, but the smoke test (section 5.6) with the real key remains the
final confirmation.

## 1. What Tapetide is

- Indian stock market data (NSE and BSE, ~8,200 stocks) exposed as an **MCP server**, not a
  REST API. There is no plain HTTP/JSON endpoint of its own. **[listing]**
- Remote endpoint (streamable HTTP transport): `https://mcp.tapetide.com/mcp`. **[verified-in-repo]**
- Tool count is reported inconsistently by sources (26, 48, 52, 55). The set of tools below is
  stable across all of them. Use `list_tools()` at runtime rather than trusting a count. **[listing]**
- Also distributed as a stdio server (`npx -y tapetide-mcp`, or `uvx tapetide-mcp`) that takes the
  token in env var `TAPETIDE_TOKEN`. FinAlly does **not** use the stdio server. **[listing]**

## 2. Authentication

- The remote server accepts either Google OAuth sign-in (for interactive clients such as Claude
  Desktop) or a **personal token sent as an HTTP bearer header**. FinAlly uses the latter. **[listing]**
- Header: `Authorization: Bearer <token>`. **[verified-in-repo]**
- Tokens are free to create and are reported to start with `tpt_rt_`. **[listing]**
- Naming: Tapetide's own docs call the variable `TAPETIDE_TOKEN`; **this project's variable is
  `TAPETIDE_API_KEY`** (PLAN.md §5). They hold the same value. Do not rename ours.
- The token is a secret. Never log it, never put it in a URL, never return it from an API route.

## 3. Quotas and rate limits

| Item | Value | Source |
|---|---|---|
| Plan used by this project | 400 calls/day | PLAN.md §6 (project owner's plan) |
| Free tier (public listing) | 50 successful calls/day, 1,000/month | **[listing]** |
| Cost of one `get_batch_quotes` call | 1 call regardless of symbol count (up to 20) | **[listing]** |
| Failed calls | Listing says *successful* calls are counted, so failures are probably free. | **[unverified]** |
| Whether `get_price_history` costs more than one call | Not stated anywhere, including `read_me`. | **[unverified]** |

Consequences for design (already reflected in PLAN.md §6):

- Always batch. One call for 10 tickers costs the same as one call for 1.
- 2s polling burns 400 calls in ~13 minutes of market hours. `TAPETIDE_POLL_SECONDS` is the knob.
- End-of-day history changes once a day. **Cache it** (see MARKET_INTERFACE.md, "EOD cache"); never
  poll it.
- Validation (`found: false`) spends a call per add.

## 4. Tools relevant to prices

Only these are used. All are called with `session.call_tool(name, arguments)`.

### 4.1 `get_batch_quotes` — real-time quotes for many symbols

| Argument | Type | Notes |
|---|---|---|
| `symbols` | `list[str]` (a string is also accepted by the schema) | NSE symbols, **max 20 per call**; over 20, split. Example `["RELIANCE","TCS","HDFCBANK"]`. **[verified-live]** (schema) |

Response (`result.structured_content`). **[verified-live]**, 2026-10-19:

```json
{
  "data": [
    {
      "requested": "HDFCBANK",
      "symbol": "HDFCBANK",
      "name": "HDFC Bank Ltd",
      "found": true,
      "price": 708.35,
      "prev_close": 728.85,
      "change": -20.5,
      "change_pct": -2.81265006517116,
      "open": 733.4,
      "high": 733.4,
      "low": 707.7,
      "volume": 22644319,
      "updated_at": "2026-10-19T08:30:49+00:00"
    },
    {
      "requested": "NOTAREALCO",
      "symbol": "NOTAREALCO",
      "found": false,
      "name": null, "price": null, "prev_close": null, "change": null,
      "change_pct": null, "open": null, "high": null, "low": null,
      "volume": null, "updated_at": null
    }
  ],
  "meta": {"count": 3}
}
```

An unknown symbol is **not** an error: the entry is present with `found: false` and every other
field `null` (not absent). All entries come back in request order.

Field notes:

| Field | Meaning |
|---|---|
| `requested` | The symbol you asked for, echoed back. **Key the cache by this**, not `symbol`. |
| `symbol` | The symbol Tapetide resolved to. Can differ after a corporate action (e.g. a demerger/rename such as TATAMOTORS to TMCV). |
| `found` | `false` means Tapetide does not know the symbol. This is the validation signal. Price fields are `null` then, so check `found` before using them. |
| `price` | Last traded price, rupees. |
| `prev_close` | The exchange's previous close. Drives day-change %. May be absent; treat as optional. |
| `updated_at` | ISO-8601. Observed with a **UTC** offset (`+00:00`), not IST. Parse offset-aware; if one is ever naive, **assume IST**, not server-local time. `null` when `found` is false. |
| `change`, `change_pct` | Day change vs `prev_close`, in rupees and percent (`-2.81` means -2.81%, not a fraction). Redundant with what `PriceUpdate.day_change*` derive; FinAlly ignores them. |
| `open`, `high`, `low`, `volume`, `name` | Today's session so far. Available if the UI ever wants them; not used today. |

Not in the batch payload (so do not expect them): market cap, PE/PB, 52-week range. Those are
in `get_stock_quote` / `get_company_profile`.

Real-time vs delayed: still not stated by Tapetide. In the live check, `updated_at` was about
2.5 minutes behind the wall clock when read, and the two symbols' stamps were one second apart.
That is consistent with quotes refreshed server-side every so often rather than a tick feed, so
a 2s poll can legitimately return an unchanged `updated_at`/`price` for several polls in a row.
Do not treat "price unchanged" as an outage. Surface staleness via `market_data_healthy`
(PLAN.md §6). **[verified-live]** for the observation, **[unverified]** for the refresh cadence.

Note `price` can be well away from the seed table: HDFCBANK was 708.35 against the simulator seed
728.85, because `prev_close` here (728.85) is what the seed was taken from on the previous
session. Expected, not a bug.

Outside NSE hours (9:15-15:30 IST, Mon-Fri) the quote stays at the last close and `updated_at`
does not advance. This is why FinAlly switches to the simulator then (PLAN.md §5).

### 4.2 `get_stock_quote` (alias `get_live_quote`) — one symbol, richer fields

Single-symbol quote described as returning LTP, change %, volume, market cap, PE, PB and the
52-week range. **[listing]**; `get_live_quote` is documented by Tapetide as an alias taking
`symbol` (with `ticker`/`identifier` accepted as aliases of `symbol`). FinAlly does not use it for prices: `get_batch_quotes` with one symbol
is the same cost and has the same `found` semantics we already parse. Mentioned so nobody
re-researches it.

### 4.3 `get_price_history` — end-of-day (daily) OHLCV

This is the tool for end-of-day prices. Arguments and response **[verified-live]**.

| Argument | Type | Notes |
|---|---|---|
| `symbol` | `str` | Required. `ticker` is accepted as an alias. **One symbol per call.** |
| `days` | `int` | Lookback window in **calendar days** counted back from `end_date` (or from today if omitted), **not** a count of bars/sessions. Default **365**, max **2000**. The tool description's "days:5 for the last 5 sessions" is misleading: on Mon 2026-10-19 `days: 5` returned **3** bars (Oct 14-16). A 3000-day request with `end_date=2026-10-16` was capped to 2000 days and started 2021-04-26, i.e. exactly 2000 calendar days earlier. |
| `end_date` | `str` `YYYY-MM-DD` | Optional, **inclusive** upper bound. Also the paging cursor. |
| `interval` | `str` | `daily` (default) or `weekly`. |

Response, RELIANCE `days: 5`, **[verified-live]** (trimmed):

```json
{
  "data": [
    {"date": "2026-10-15", "open": 1185.2, "high": 1218.8, "low": 1177.2,
     "close": 1215, "raw_close": 1215, "volume": 23456219},
    {"date": "2026-10-16", "open": 1215, "high": 1215.4, "low": 1193,
     "close": 1211.2, "raw_close": 1211.2, "volume": 17225283}
  ],
  "meta": {
    "count": 3, "days": 5, "interval": "daily",
    "adjustment": {"series": "split_bonus_adjusted", "dividend_adjusted": false,
                   "volume_adjusted": false, "currency": "INR",
                   "raw_series_field": "raw_close"},
    "window": {"requested_days": 5, "served_days": 5, "max_days": 2000,
               "truncated": false, "returned_rows": 3, "has_more": true,
               "first_date": "2026-10-14", "last_date": "2026-10-16",
               "end_date": null, "next_cursor": "2026-10-13"},
    "coverage": {"first_stored_date": "2000-09-22", "last_stored_date": "2026-10-16"}
  }
}
```

Facts established by the live calls:

- Rows are under `data`, ascending by `date` (`YYYY-MM-DD`, a trading date, no time). Keys:
  `date, open, high, low, close, raw_close, volume`. There is **no delivery %** in the payload
  despite the tool description; do not model it.
- **Prices are split/bonus back-adjusted; dividends are not.** `close` (and, per
  `meta.adjustment.series`, open/high/low) are adjusted. `raw_close` is the actual printed close
  and is the only raw field (no raw open/high/low). Example: RELIANCE on 2021-04-26 shows
  `close: 879.65` but `raw_close: 1937.85`, because of the 1:1 bonus. The latest bars equal
  their raw values. `raw_close` is `null` where no raw print exists (older history, ETFs); never
  substitute `close` for it. `volume` is **not** adjusted.
- Consequence for FinAlly: live `price`/`prev_close` are raw. For "last close" use `raw_close`
  (or the quote's `prev_close`), not the adjusted `close`, or old and new numbers will not
  reconcile after a corporate action. Charts of adjusted series are fine.
- Weekends and exchange holidays have no row, which is why `days: 5` over a weekend returns
  fewer than 5 bars. Today's bar does not exist until the day is stored: on Monday 2026-10-19
  during market hours the newest bar was Friday's (`last_stored_date: 2026-10-16`).
- `meta.window.has_more` and `next_cursor` are present **even when `truncated` is false**
  (`next_cursor` is the day before `first_date`, here `2026-10-13`). `has_more: true` therefore
  only means "older data exists", not "you got less than you asked for". `truncated: true` is the
  signal that the request was capped (requested 3000, `served_days` 2000, `returned_rows` 1355).
- Oldest stored bar for RELIANCE is 2000-09-22.
- Large responses are big (126 of 1355 rows alone filled ~25k characters). Page and trim in
  code; do not log payloads.

Paging recipe: request `days = min(remaining_calendar_days, 2000)` with `end_date = cursor`;
append `data`; set `cursor = meta.window.next_cursor`; stop when the oldest returned date is
`<= wanted_start`, when `has_more` is false, or when `data` is empty.

Unknown symbol: `get_price_history` **raises a tool error** (not an empty result):
`Stock not found: NOTAREALCO. Use search to find the correct symbol.` **[verified-live]**. Map
a message that starts with `Stock not found` to "unknown ticker"; treat any other exception as a
transport failure. This differs from `get_batch_quotes`, which returns `found: false`.

Important limitation: **there is no batch history tool.** End-of-day prices for N tickers cost
N calls. The unified API therefore fans out with bounded concurrency and caches aggressively.
For "the latest close of many tickers" use `prev_close` from `get_batch_quotes` instead (one
call for up to 20); it is the previous trading day's close during the session, and equals the
last close after hours.

### 4.4 Other tools you may meet

Tapetide's own `read_me` guide lists them. None are used for pricing, except those noted.
`search_stocks` (find a symbol by name, symbol, BSE code or ISIN), `get_index_history` (index
levels, e.g. Nifty), `get_adjustment_factors` (split/bonus factors to rebuild raw prices),
`get_observation_status` (per-day reason: traded / weekend / holiday / no_print, useful to tell a
holiday from missing data), `get_trending_stocks`, `get_market_pulse`, `get_india_vix`, screeners,
financials, options tools. `read_me` also mentions REST routes on `mcp.tapetide.com`
(`/v1/stocks/{symbol}/documents...`) for filings only; no REST price endpoint was found, so
MCP remains the only price path. **[verified-live]** for the list (from `read_me`). `search_stocks` is a candidate for a future
"did you mean" on a failed ticker validation.

## 5. Connecting from Python

Dependencies (already in `backend/pyproject.toml`): `mcp`, `httpx2`.

### 5.1 Minimal real-time quote fetch (mirrors `tapetide_client.py`)

```python
import asyncio
import os

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

TAPETIDE_MCP_URL = "https://mcp.tapetide.com/mcp"


async def fetch_quotes(symbols: list[str]) -> list[dict]:
    api_key = os.environ["TAPETIDE_API_KEY"]
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(TAPETIDE_MCP_URL, http_client=http_client)
        async with Client(transport) as client:
            result = await client.call_tool("get_batch_quotes", {"symbols": symbols})
            return (result.structured_content or {}).get("data", [])


if __name__ == "__main__":
    for q in asyncio.run(fetch_quotes(["RELIANCE", "TCS", "HDFCBANK", "NOTAREALCO"])):
        if q.get("found"):
            print(q["requested"], q["price"], q.get("prev_close"), q["updated_at"])
        else:
            print(q.get("requested"), "not found")
```

Run: `cd backend && TAPETIDE_API_KEY=... uv run python snippet.py`.

### 5.2 Batching more than 20 symbols

```python
BATCH_SIZE = 20


async def fetch_quotes_chunked(client, symbols: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(symbols), BATCH_SIZE):
        res = await client.call_tool(
            "get_batch_quotes", {"symbols": symbols[i : i + BATCH_SIZE]}
        )
        out.extend((res.structured_content or {}).get("data", []))
    return out
```

Each chunk is one billable call.

### 5.3 End-of-day history for one symbol, with paging

`days` is **calendar days** back from `end_date`, so page by date, not by row count:

```python
from datetime import date, timedelta


async def fetch_daily(client, symbol: str, start: date, end: date) -> list[dict]:
    """Raw rows for [start, end], ascending.

    Raises on transport failure and on an unknown symbol ("Stock not found: ...").
    """
    rows: list[dict] = []
    cursor = end                                   # inclusive upper bound
    while cursor >= start:
        span = min((cursor - start).days + 1, 2000)
        res = await client.call_tool(
            "get_price_history",
            {"symbol": symbol, "days": span, "end_date": cursor.isoformat()},
        )
        payload = res.structured_content or {}
        page = payload.get("data", [])
        rows = page + rows                         # older page goes in front
        window = (payload.get("meta") or {}).get("window") or {}
        next_cursor = window.get("next_cursor")
        if not page or not window.get("has_more") or not next_cursor:
            break
        cursor = date.fromisoformat(next_cursor)
        if span < 2000:                            # window already reached `start`
            break
    return [r for r in rows if start <= date.fromisoformat(r["date"]) <= end]
```

One page covers up to 2000 calendar days (~5.5 years, ~1,350 bars), so a 1-year request is one
call. Each page is one billable call (assumed; see section 3).

### 5.4 Fan out history for many tickers (bounded concurrency)

```python
async def fetch_daily_many(client, symbols: list[str], start: date, end: date, limit: int = 4):
    sem = asyncio.Semaphore(limit)

    async def one(sym: str):
        async with sem:
            return sym, await fetch_daily(client, sym, start, end)

    return dict(await asyncio.gather(*(one(s) for s in symbols)))
```

In the real client, **all calls still go through the existing `asyncio.Lock`** because one MCP
`Client` is shared with the poller (PLAN.md §6). The semaphore then only bounds queueing. Note
the lock means a long history fan-out delays the 2s poll; see MARKET_INTERFACE.md for how the
design avoids that (a separate short-lived client for history).

### 5.5 Raw HTTP (debugging only)

Streamable-HTTP MCP is JSON-RPC over POST. For a one-off check without the SDK:

```bash
curl -sS https://mcp.tapetide.com/mcp \
  -H "Authorization: Bearer $TAPETIDE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
```

A real session needs the `Mcp-Session-Id` response header on subsequent calls plus an
`notifications/initialized` message. Prefer the SDK; this is only to prove auth works.

### 5.6 Smoke test (do this first with a real key)

```python
async def smoke():
    # ... open client as in 5.1 ...
    tools = await client.list_tools()
    print(sorted(t.name for t in tools.tools))          # is get_price_history present?
    q = await client.call_tool("get_batch_quotes", {"symbols": ["RELIANCE", "NOPE"]})
    print(q.structured_content)                          # confirm keys in section 4.1
    h = await client.call_tool("get_price_history", {"symbol": "RELIANCE", "days": 5})
    print(h.structured_content)                          # confirm row keys and meta.window
```

Three calls, three units of quota. The equivalent checks were already run once through the
attached MCP tools (see Provenance); running this with the real `TAPETIDE_API_KEY` additionally
confirms the bearer-token path, token validity and that quota decrements as assumed. Compare the
quota counter in your Tapetide dashboard before and after to settle the remaining **[unverified]**
cost questions in section 3.

## 6. Error handling

| Situation | What you see | FinAlly behavior |
|---|---|---|
| Unknown symbol (quotes) | Entry with `found: false`, all other fields `null` | `validate_ticker` returns `False`; poll skips it. |
| Unknown symbol (history) | Tool error `Stock not found: X. Use search to find the correct symbol.` | `DailyBars(error="unknown ticker")`, not a transport failure. |
| Unsupported `interval` (`1m`, `monthly`...) | Tool error with an explanation (per tool description) | Programming error; only `daily`/`weekly` are valid. |
| Bad/expired token | Connection or tool call raises | Transport failure: `MarketDataError` (503), counts toward fallback (PLAN.md §6). |
| Network down / timeout | Exception from `call_tool` | Same. |
| Quota exhausted | Tool error (exact text **[unverified]**, not triggered) | Same; falls back to simulator after N failures. |
| Malformed row | Missing `price` / `updated_at` | Skip the row, log a warning (as `_cache_quote` does). |
| History capped | `meta.window.truncated` true | Page with `next_cursor` (section 4.3). |

Never report a transport failure as "invalid symbol".

## 7. Symbols

- Plain NSE trading symbols, uppercase: `RELIANCE`, `HDFCBANK`. Some contain `&` or `-`
  (`M&M`, `BAJAJ-AUTO`); URL-encode in our own paths only, not in tool arguments.
- Normalize with `strip().upper()` before every call (PLAN.md §8).
- Corporate actions can make the resolved `symbol` differ from `requested`. Key by `requested`.

## 8. Sources

- Tapetide MCP landing page: https://mcp.tapetide.com/ and https://tapetide.com/mcp
- Tool pages (Glama): `get_batch_quotes`, `get_stock_quote`, `get_price_history` under
  https://glama.ai/mcp/servers/Tapetide-hq/nse-bse-indian-stock-market-data-mcp/tools/
- Repository: https://github.com/Tapetide-hq/nse-bse-indian-stock-market-data-mcp
- In-repo: `backend/app/market/tapetide_client.py`, `backend/tests/market/test_tapetide.py`
