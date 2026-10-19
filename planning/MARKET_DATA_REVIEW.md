# Market Data Backend - Code Review

**Date:** 2026-10-19
**Scope:** `backend/app/market/` and `backend/tests/market/` - the market data subsystem only
(simulator, Tapetide client, cache, interface, factory, manager, SSE stream, seed data, NSE
hours). Reviewed against the binding contract in `PLAN.md` sections 5-6 and the companion design
docs (`MARKET_DATA_DESIGN.md`, `MARKET_DATA_SUMMARY.md`, `MARKET_INTERFACE.md`,
`MARKET_SIMULATOR.md`, `TAPETIDE_API.md`).
**Method:** full read of every module and test, cross-checked against PLAN.md and the design docs;
test suite executed; the installed MCP SDK and the Tapetide API contract inspected to confirm or
reject suspected bugs rather than guessing.

---

## 1. Verdict

The subsystem is **well-architected, readable, and largely conformant**. The strategy pattern,
the "one cache, never replaced" invariant, correlated-GBM simulation, day-change-vs-tick-change
split, requested-symbol cache keying, IST timestamp handling, and the degraded-mode fallback latch
are all present, correct, and tested.

**Tests: 119 passed, 0 failed. `ruff check app/market` clean.**

One **confirmed correctness bug** (Tapetide tool errors are misclassified - section 4.1) and a
small number of lower-severity gaps were found, all on the **Tapetide path**, which the default
simulator demo never exercises. The simulator path - the one used for every offline demo and the
E2E suite - has no defects found.

A secondary finding is **documentation drift**: `MARKET_DATA_DESIGN.md` specifies a hardening pass
(its `[CHANGE]`/`[NEW]` sections) that is only partly reflected in the shipped code. The items that
matter are captured as findings below; the rest are equivalent alternative implementations.

---

## 2. What was reviewed and what is sound

| Module | Assessment |
|---|---|
| `models.py` | `PriceUpdate` frozen dataclass; change/day-change/direction math correct; `to_dict()` complete. No issues. |
| `cache.py` | Thread-safe, version counter bumps on every write, `previous_close` carry-forward correct (keeps day-change continuous across a handover). No issues. |
| `interface.py` | Clean ABC; `MarketDataError` vs bool contract for `validate_ticker` is exactly right; non-abstract `is_degraded()` default. No issues. |
| `seed_prices.py` | Realistic seeds, per-ticker GBM params, sector correlation groups, curated `NSE_SYMBOL_UNIVERSE`. No issues. |
| `nse_hours.py` | Explicit IST conversion, inclusive 09:15-15:30, weekday gate, no holiday calendar (per PLAN). No issues. |
| `simulator.py` | GBM math matches the derivation; Cholesky rebuilt on add/remove; seed priority correct; `_run_loop` logs and continues (never dies). No issues. |
| `factory.py` | `MARKET_DATA_SOURCE` override + key + hours decision correct; fails fast on `tapetide` without a key. No issues. |
| `manager.py` | Handover in both directions, cache never replaced, tickers preserved, fallback latch with cooldown + retry. Works and is tested. Minor notes in section 5. |
| `tapetide_client.py` | Correct happy-path parsing (field names verified against `TAPETIDE_API.md`), batching over 20, `_call_lock` serialization, IST naive-timestamp handling. **Error-handling gaps in section 4.** |
| `stream.py` | Version-gated SSE, whole-map frames, disconnect handling. **Latent double-registration issue, section 4.4.** |

### Contract conformance confirmed against PLAN.md

- One interface for both sources; downstream depends only on the manager + cache (section 6).
- GBM ~500ms ticks, correlated sectors, 2-5% random events (section 6).
- Simulator seeds from the last real price left in the cache (section 6).
- Tapetide over MCP streamable-HTTP with a Bearer token, `get_batch_quotes`, batches of <=20,
  cache keyed by `requested` not the resolved `symbol` (section 6). Field names (`requested`,
  `found`, `prev_close`, `updated_at`) match `TAPETIDE_API.md` section 4.1.
- All Tapetide tool calls serialized through `_call_lock` (section 6).
- `validate_ticker` seeds the cache on success (enables one-turn "add X and buy 10", section 6).
- Naive upstream timestamps parsed as IST (section 7).
- Live handover every ~60s; degraded Tapetide falls back to the simulator with a 5-minute
  cooldown latch that prevents flapping, then allows one retry (section 6). Tested end to end in
  `test_degraded.py`.
- `active_source_name` returns the plan's `"tapetide"`/`"simulator"`/`"none"` labels.

---

## 3. Test suite

`uv run --extra dev pytest tests/market -q` -> **119 passed**. Nine modules covering models,
cache, simulator math + source, Tapetide (mocked MCP client), factory selection, NSE hours,
manager handover, and degraded-mode fallback.

Coverage is good on the happy paths and on transport-exception failures. The one structural
weakness, which is also the root of finding 4.1, is that the Tapetide test mocks
(`_mock_client`, `_ok_client`) build a `MagicMock` result and set only `structured_content` -
they **never set `is_error`**, and the code never reads it, so the tool-error path is entirely
unexercised. (`test_manager.py::test_supervise_triggers_handover_on_interval` was repaired in a
prior session: it depended on a real Tapetide source not failing within 150ms, which is racy on a
host where the MCP/SSL connection fails fast.)

---

## 4. Findings

### 4.1 [HIGH - confirmed bug] Tapetide tool errors are misclassified, defeating fallback and returning the wrong HTTP status

**Where:** `tapetide_client.py`, `_call_batch_quotes` / `_poll_once` / `validate_ticker`.

**What:** `_call_batch_quotes` reads `result.structured_content` and returns
`payload.get("data", []) if payload else []`. It never inspects `result.is_error`.

**Why it is a real bug (verified, not inferred):** I inspected the installed SDK
(`mcp.client.client.Client.call_tool`). It returns a `CallToolResult` and its documented `Raises`
are only `InputRequiredRoundsExceededError`, `MCPError` (callback error), and
`pydantic.ValidationError` - it does **not** raise on an ordinary tool-level error. A tool error
(daily-quota exhausted, bad token, server error) therefore comes back as a `CallToolResult` with
`is_error=True` and no `structured_content`, which the current code turns into an empty list with
no exception. Consequences:

- **Polling:** an empty list means `poll_failed` stays `False`, so `_consecutive_failures` resets
  to 0. The feed **freezes silently and never degrades or falls back** - a direct violation of
  PLAN.md section 6 ("a swallowed per-batch poll error ... must count ... after N consecutive
  failures the manager hands over to the simulator").
- **Validation:** `validate_ticker` sees `[]`, returns `False`, and the API reports **400 "No
  stock with ticker X exists"** for what is actually a transport/quota failure - exactly the
  400-vs-503 confusion PLAN.md section 6 forbids ("a transport failure must not be reported to the
  user as an invalid symbol").

Note: genuine transport *exceptions* (e.g. a dropped connection) **are** handled - `call_tool`
raises, `_poll_once` catches it and counts a failure (covered by `test_degraded.py`). Only the
non-raising `is_error` result is missed. `MARKET_DATA_DESIGN.md` section 9.3 specifies the exact
fix (a `_call_tool` wrapper that checks `is_error` and raises `MarketDataError`/`TapetideToolError`);
it was written but not applied to the code.

**Fix:** inspect `result.is_error` in the tool-call path and raise `MarketDataError` on a true
value, so both the poll counter and the validate-to-503 mapping see it. Add a test that sets
`is_error=True` (the current mocks hide the bug).

### 4.2 [MEDIUM] No per-call timeout on Tapetide tool calls

**Where:** `tapetide_client.py`, `_run` uses `httpx2.Timeout(30.0, read=300.0)`; there is no
timeout around the individual `call_tool`.

**What:** a hung tool call can hold `_call_lock` for up to the 300s read timeout. Because the
poller and `validate_ticker` share that lock, a single stuck call stalls both live pricing and any
watchlist add for minutes, and - combined with 4.1 - may not count as a failure.

**Fix (per design section 9.4):** wrap each call in `asyncio.wait_for(..., TAPETIDE_CALL_TIMEOUT)`
(10s), converting a timeout into a counted `MarketDataError`, and lower the httpx `read` backstop.

### 4.3 [LOW] A ticker removed mid-poll can be written back into the cache

**Where:** `tapetide_client.py`, `_poll_once` caches every returned quote without re-checking
current membership.

**What:** if `remove_ticker` runs while a batch call is in flight, the in-flight response is still
written, re-creating a cache entry for a ticker that is no longer tracked - a ghost row in the SSE
frame until the next frame. Low impact (single-user, small window).

**Fix (per design section 9.4):** skip a quote whose `requested` symbol is no longer in
`self._tickers` before calling `_cache_quote`.

### 4.4 [LOW - latent] `create_stream_router` decorates a module-level router

**Where:** `stream.py` - `router = APIRouter(...)` is created at import time and the factory
decorates that shared instance.

**What:** calling `create_stream_router()` more than once (two test apps, a reload) registers
`/prices` on the same router repeatedly, and each call's closure captures a different cache. It
does **not** affect the running app today because `app/main.py` defines its own SSE route and does
not call this factory - but the factory is part of the market package's public API and is
documented as the way to mount SSE, so the latent bug should be fixed.

**Fix (per design section 12.1):** create the `APIRouter` inside the factory so each call returns
an independent router.

### 4.5 [DOC/PROCESS] Design doc diverges from shipped code

`MARKET_DATA_DESIGN.md` (dated 2026-10-19) documents a hardening pass as if applied, but several
of its `[CHANGE]`/`[NEW]` items are not in the code: the `is_error` tool-error wrapper (4.1), the
per-call timeout (4.2), the mid-poll guard (4.3), the stream router-per-call fix (4.4), the
`desired_source_name()`/`build_source()` factory split, the 1s health tick, a monotonic
`last_write_age`, and the standalone `health.py`/`tracking.py` modules. The functional gaps are
findings 4.1-4.4; the remainder (factory split, tick cadence, health/tracking placement) are
**equivalent alternative implementations** already satisfied functionally by the shipped
`manager.py` and by the backend's inline health/tracking logic, so they are not defects - but the
design doc and `STATUS.md` should be reconciled with the code so the next reader is not misled
about which hardening is actually present.

---

## 5. Minor observations (no action required)

- `manager._maybe_handover` constructs a throwaway source via `create_market_data_source` on every
  60s check even when nothing changed (then discards it if the type is unchanged). Harmless - an
  unstarted `TapetideDataSource` opens no connection - but the design's label comparison avoids it.
- `manager.get_tickers()` / `active_source_name` read `self._active` without the async lock. Benign
  in CPython (a single attribute read is atomic) and never observed mid-corruption because a swap
  reassigns the reference atomically.
- `_cache_quote` returns a bool that the poll loop ignores. Dead but harmless.
- Environmental (not a code defect): on this Windows + Python 3.13 host, `httpx2`'s default
  `truststore` SSL context raises `ssl.SSLError` when a real Tapetide client is constructed, which
  would block live NSE data here. It does not affect the simulator or any test. If live Tapetide is
  needed on this machine, construct the `httpx2.AsyncClient` with an explicit `ssl` context.

---

## 6. Recommendations

1. **Fix 4.1** before any real-money-less-but-real-data demo that uses Tapetide: it is the only
   finding that breaks a stated PLAN.md section 6 guarantee (silent freeze + wrong status code).
   It is a small, localized change plus one honest test.
2. Apply **4.2-4.4** as a single Tapetide-hardening commit; `MARKET_DATA_DESIGN.md` sections
   9.3-9.4 and 12.1 already contain drop-in code.
3. **Reconcile the docs** (4.5): update `STATUS.md` and `MARKET_DATA_DESIGN.md` section tags so
   they describe the code that actually ships.
4. Strengthen the Tapetide tests so the mock result carries `is_error`, locking in the 4.1 fix and
   preventing regression.

Nothing here blocks the simulator-based demo or the existing E2E path; the findings are confined to
the optional real-data provider.

---

## 7. Resolution (2026-10-19)

All five findings have been fixed.

- **4.1** — `tapetide_client.py` now routes every tool call through `_call_tool`, which inspects
  `CallToolResult.is_error` and raises `TapetideToolError` (a `MarketDataError`). A quota/auth
  error now counts as a poll failure (arming the fallback) and makes `validate_ticker` raise, so
  the API returns 503, not a false 400.
- **4.2** — `_call_tool` wraps the call in `asyncio.wait_for(..., TAPETIDE_CALL_TIMEOUT=10s)`; a
  hang becomes a counted `MarketDataError` instead of holding `_call_lock` for the httpx read
  timeout (also lowered to 60s as a backstop).
- **4.3** — `_poll_once` snapshots the ticker list and skips any quote whose `requested` symbol is
  no longer tracked, so a ticker removed mid-poll is not written back.
- **4.4** — `create_stream_router` builds its `APIRouter` inside the factory, so repeated calls
  return independent routers.
- **4.5** — `STATUS.md` and this document's parent design (`MARKET_DATA_DESIGN.md`, new
  implementation-status banner + traceability rows) now describe the code that actually ships.

Regression tests added: `is_error` raises on a batch call and on validate; three tool-error polls
arm `is_degraded()`; a call slower than the timeout raises; a quote for a removed ticker is not
cached; `create_stream_router` twice yields one `/prices` route each. The `_mock_client` /
`_ok_client` helpers now set `is_error = False` (an unset `MagicMock` attr is truthy and would
otherwise read as a tool error).

**Suite after the fixes: 144 passed (125 market + 19 API), 0 failed. `ruff` clean.**

No `PLAN.md` change was needed: the fixes bring the code into line with behaviour PLAN.md section 6
already specifies (fallback on a swallowed poll error; 503, not 400, on a transport/quota failure).
`README.md` needed only its test-count references updated; the public API is unchanged. The one new
constant, `TAPETIDE_CALL_TIMEOUT`, is internal and not user-facing.
