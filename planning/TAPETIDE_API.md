# Tapetide API Reference (Real-Time and End-of-Day Prices)

Reference for how FinAlly gets real NSE prices from Tapetide. Written for agents implementing
or extending `backend/app/market/tapetide_client.py`.

## Provenance and confidence

Tapetide's own docs pages were **not reachable** from the research sandbox (outbound network
policy blocked `tapetide.com`, `mcp.tapetide.com` and `glama.ai`). Facts below come from three
sources, and each section says which applies:

| Tag | Meaning |
|---|---|
| **[verified-in-repo]** | Taken from working code and tests in this repo (`tapetide_client.py`, `backend/tests/market/test_tapetide.py`), which was written against live responses (seed prices were fetched from Tapetide on 2026-10-16). |
| **[listing]** | Reported by third-party directory listings and search summaries of Tapetide's tool pages (Glama, GitHub README, mcp.tapetide.com), not confirmed against a live call. |
| **[unverified]** | Inferred or not found. Must be checked with a live call before relying on it. |

Before building on anything tagged **[listing]** or **[unverified]**, run the smoke test
(section 5.6) with a real key and diff the output against this document. Fix the doc, then the
code.

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
| Failed calls | Reported as "successful calls" being counted, so failures are probably free. | **[unverified]** |

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
| `symbols` | `list[str]` | NSE symbols, **max 20 per call**. Example `["RELIANCE","TCS","HDFCBANK"]`. **[listing]** |

Response (`result.structured_content`), shape **[verified-in-repo]**:

```json
{
  "data": [
    {
      "requested": "HDFCBANK",
      "symbol": "HDFCBANK",
      "found": true,
      "price": 728.85,
      "prev_close": 731.40,
      "updated_at": "2026-10-16T15:29:58+05:30"
    },
    {
      "requested": "NOTAREALCO",
      "found": false
    }
  ]
}
```

Field notes:

| Field | Meaning |
|---|---|
| `requested` | The symbol you asked for, echoed back. **Key the cache by this**, not `symbol`. |
| `symbol` | The symbol Tapetide resolved to. Can differ after a corporate action (e.g. a demerger/rename such as TATAMOTORS to TMCV). |
| `found` | `false` means Tapetide does not know the symbol. This is the validation signal. A `found: false` entry may carry no price fields at all, so always check `found` first. |
| `price` | Last traded price, rupees. |
| `prev_close` | The exchange's previous close. Drives day-change %. May be absent; treat as optional. |
| `updated_at` | ISO-8601. Normally has a UTC offset. If naive, **assume IST**, not server-local time. |

Other fields the tool may return (volume, change %, market cap, 52-week range) are **[unverified]**
for `get_batch_quotes` and are ignored by FinAlly. Do not depend on them.

Real-time vs delayed: no source states the latency. Treat `updated_at` as the truth and surface
staleness through `market_data_healthy` rather than assuming real-time. **[unverified]**

Outside NSE hours (9:15-15:30 IST, Mon-Fri) the quote stays at the last close and `updated_at`
does not advance. This is why FinAlly switches to the simulator then (PLAN.md §5).

### 4.2 `get_stock_quote` — one symbol, richer fields

Single-symbol quote described as returning LTP, change %, volume, market cap, PE, PB and the
52-week range. **[listing]** FinAlly does not use it for prices: `get_batch_quotes` with one symbol
is the same cost and has the same `found` semantics we already parse. Mentioned so nobody
re-researches it.

### 4.3 `get_price_history` — end-of-day (daily) OHLCV

This is the tool for end-of-day prices. **[listing]** for the arguments below.

| Argument | Type | Notes |
|---|---|---|
| `symbol` | `str` | Required. `ticker` is accepted as an alias. **One symbol per call.** |
| `days` | `int` | Lookback window. Default **365**, max **2000**. |
| `end_date` | `str` `YYYY-MM-DD` | Optional, **inclusive** upper bound. Also the paging cursor. |
| `interval` | `str` | `daily` (default) or `weekly`. |

Output: one row per bar with date, open, high, low, close, volume and delivery %. **[listing]**
Exact JSON key names, and whether rows live under `data`, are **[unverified]**. The code in this
document therefore normalizes defensively (several candidate key names). Confirm with the smoke
test, then tighten `_parse_bar`.

Truncation and paging **[listing]**:

- A request longer than 2000 days is silently shortened. Always read `meta.window`.
- `meta.window.truncated: true` means you did not get everything. `meta.window.requested_days`
  is what you asked for and `meta.window.next_cursor` is the `end_date` to pass on the next call
  to go further back.
- To build a long series, loop until `truncated` is false.

Expected (illustrative, not verified) shape:

```json
{
  "data": [
    {"date": "2026-10-16", "open": 731.0, "high": 735.2, "low": 726.4,
     "close": 728.85, "volume": 8123456, "delivery_pct": 52.1}
  ],
  "meta": {"window": {"truncated": false, "requested_days": 30, "next_cursor": null}}
}
```

Important limitation: **there is no batch history tool.** End-of-day prices for N tickers cost
N calls. The unified API therefore fans out with bounded concurrency and caches aggressively.
For "the latest close of many tickers" use `prev_close` from `get_batch_quotes` instead (one
call for up to 20); it is the previous trading day's close during the session, and equals the
last close after hours.

### 4.4 Other tools you may meet

`search_stocks` (find a symbol by name, symbol, BSE code or ISIN), `get_index_history`,
`screen_stocks`, `screen_stocks_technical`, `get_financials`, `get_fii_dii_detail`, option-chain
and IV tools. **[listing]** None are used for pricing. `search_stocks` is a candidate for a future
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

```python
from datetime import date


async def fetch_daily(client, symbol: str, days: int = 365, end_date: date | None = None):
    """Return raw rows (newest window first page, then older pages) for one symbol."""
    rows: list[dict] = []
    remaining = days
    cursor = end_date.isoformat() if end_date else None
    while remaining > 0:
        args = {"symbol": symbol, "days": min(remaining, 2000)}
        if cursor:
            args["end_date"] = cursor
        res = await client.call_tool("get_price_history", args)
        payload = res.structured_content or {}
        page = payload.get("data", [])
        rows.extend(page)
        window = (payload.get("meta") or {}).get("window") or {}
        remaining -= len(page)
        if not window.get("truncated") or not window.get("next_cursor") or not page:
            break
        cursor = window["next_cursor"]
    return rows
```

### 5.4 Fan out history for many tickers (bounded concurrency)

```python
async def fetch_daily_many(client, symbols: list[str], days: int, limit: int = 4):
    sem = asyncio.Semaphore(limit)

    async def one(sym: str):
        async with sem:
            return sym, await fetch_daily(client, sym, days)

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

Three calls, three units of quota. Paste the output into this file's section 4 and remove the
**[unverified]** tags that it settles.

## 6. Error handling

| Situation | What you see | FinAlly behavior |
|---|---|---|
| Unknown symbol | Entry with `found: false` | `validate_ticker` returns `False`; poll skips it. |
| Bad/expired token | Connection or tool call raises | Transport failure: `MarketDataError` (503), counts toward fallback (PLAN.md §6). |
| Network down / timeout | Exception from `call_tool` | Same. |
| Quota exhausted | Tool error (exact text **[unverified]**) | Same; falls back to simulator after N failures. |
| Malformed row | Missing `price` / `updated_at` | Skip the row, log a warning (as `_cache_quote` does). |
| History truncated | `meta.window.truncated` true | Page with `next_cursor`, or return what we have and flag `truncated`. |

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
