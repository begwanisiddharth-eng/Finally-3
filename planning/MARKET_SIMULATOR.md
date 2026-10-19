# Market Simulator — Approach and Code Structure

How FinAlly fakes stock prices when Tapetide is unavailable (no `TAPETIDE_API_KEY`, outside NSE
hours, or `MARKET_DATA_SOURCE=simulator`). Companion docs: `MARKET_INTERFACE.md` (the unified
API) and `TAPETIDE_API.md` (the real provider).

**Status.** Sections 1-6 describe the **built and tested** live simulator
(`backend/app/market/simulator.py`, `seed_prices.py`). Section 7 (synthetic end-of-day history)
is a **design to implement**, with a prototype that was run against the invariants listed there.

## 1. Purpose and requirements

- Looks alive: visible movement every ~500ms, green/red flashes, occasional dramatic moves.
- Looks plausible: NSE-scale prices, realistic relative volatility, sector co-movement.
- Zero dependencies: in-process asyncio task, no network, no API key.
- Source-agnostic output: writes the same `PriceCache` entries Tapetide does, so nothing
  downstream can tell the difference (except `active_source_name`).
- Hands over cleanly to and from Tapetide mid-session (PLAN.md §6).

It is a demo-grade simulator, not a market model. No order book, no volumes, no intraday
seasonality, no market holidays.

## 2. The model: correlated geometric Brownian motion

Each ticker follows GBM, advanced in discrete steps:

```
S(t+dt) = S(t) * exp( (mu - sigma^2 / 2) * dt  +  sigma * sqrt(dt) * Z )
```

| Symbol | Meaning | Source |
|---|---|---|
| `S` | price, rupees | `SEED_PRICES`, or last real price in cache |
| `mu` | annualized drift | `TICKER_PARAMS[t]["mu"]`, default 0.08 |
| `sigma` | annualized volatility | `TICKER_PARAMS[t]["sigma"]`, default 0.25 |
| `dt` | step as a fraction of a trading year | `0.5 s / (252 * 6.5 * 3600 s)` ≈ 8.48e-8 |
| `Z` | standard normal, **correlated across tickers** | Cholesky (below) |

Why GBM: prices stay positive (the `exp`), returns are log-normal, and volatility scales
correctly with time, so changing the tick interval does not change how "wild" the market is.

Known consequences, accepted (PLAN.md §13):

- `dt` is tiny, so a 0.5s step moves a Rs 400 stock by a few paise; with 2-dp rounding many
  ticks for low-priced tickers produce no change. Flashes are therefore sparse for them and the
  random events supply most of the drama.
- The 6.5h-day constant is US-flavored (NSE is 6h15m). It only scales volatility by ~2%; left
  as is.

### 2.1 Correlation via Cholesky

Independent noise would make every stock wander separately, which looks fake. Instead:

1. Build an `n x n` correlation matrix `C`: diagonal 1; same sector group `0.6`
   (`INTRA_GROUP_CORR`); everything else `0.3` (`CROSS_GROUP_CORR`).
2. Compute `L = cholesky(C)` so that `L @ L.T == C`.
3. Each step draw `z_ind ~ N(0, I)` and use `z = L @ z_ind`. The components of `z` are
   standard normal with correlation `C`.

Sector groups (`CORRELATION_GROUPS`): `banking` {HDFCBANK, ICICIBANK}, `it` {INFY, TCS},
`auto` {HEROMOTOCO, TATAMOTORS}. Tickers in no group correlate at `0.3` with everything.

The matrix is rebuilt on every add/remove: O(n²) for the matrix and O(n³) for Cholesky, trivial
for n < 50. A matrix with all off-diagonals in [0, 1) and diagonal 1 is positive definite for
these values, so `np.linalg.cholesky` does not fail.

### 2.2 Random events

Per ticker per step, with probability `event_probability` (default `0.001`), multiply the price
by `1 ± U(0.02, 0.05)`. With 10 tickers at 2 steps/s that is one event about every 50s: enough
for drama, rare enough to feel like news. Events are independent of correlation and not
mean-reverting (the price just stays at its new level).

### 2.3 Rounding

`step()` returns prices rounded to 2 dp; the **internal** price is kept unrounded so small
drifts accumulate instead of being rounded away each tick. `PriceCache.update` rounds again.

## 3. Seed data (`seed_prices.py`)

| Name | Purpose |
|---|---|
| `SEED_PRICES` | Starting price for the 10 default tickers, fetched from Tapetide on 2026-10-16 (e.g. HDFCBANK 728.85, INFY 1161.20). |
| `TICKER_PARAMS` | Per-ticker `sigma`/`mu`. Banks ~0.20-0.21, IT 0.22-0.25, high-vol names (TATAMOTORS 0.38, BEL 0.35) deliberately wilder. |
| `DEFAULT_PARAMS` | `{sigma: 0.25, mu: 0.08}` for any other ticker. |
| `CORRELATION_GROUPS`, `INTRA_GROUP_CORR`, `CROSS_GROUP_CORR` | Section 2.1. |
| `NSE_SYMBOL_UNIVERSE` | Curated frozenset (~60 symbols) of real NSE tickers; the simulator's definition of "a valid ticker" for watchlist validation, since it has no real backing universe. |

Seed price priority when a ticker is added (`_add_ticker_internal`):
explicit `seed_price` argument > `seed_overrides` (last real price) > `SEED_PRICES` >
`random.uniform(50, 300)` for a ticker with no seed. The random fallback exists so validated
but unseeded symbols (e.g. WIPRO) still work. Refreshing the seed table is a manual task:
fetch quotes through Tapetide and update the dict and the date in the comment.

## 4. Code structure

```
backend/app/market/
  seed_prices.py   data only: prices, params, groups, symbol universe
  simulator.py
    GBMSimulator          pure math, no asyncio, no cache. step() -> {ticker: price}
    SimulatorDataSource   MarketDataSource adapter: asyncio loop + PriceCache writes
  cache.py         PriceCache (shared with Tapetide source)
  interface.py     MarketDataSource ABC
```

The split is the key design choice: **`GBMSimulator` is synchronous and pure** (it only needs
`numpy` and `random`), so the math is unit-testable without an event loop or a cache.
`SimulatorDataSource` is a thin shell that owns the task.

### 4.1 `GBMSimulator`

```python
sim = GBMSimulator(["HDFCBANK", "INFY"], event_probability=0.001, seed_overrides={"INFY": 1170.0})
sim.step()                      # {'HDFCBANK': 728.9, 'INFY': 1170.1}
sim.add_ticker("WIPRO")         # rebuilds Cholesky; optional seed_price=
sim.remove_ticker("INFY")
sim.get_price("WIPRO"); sim.get_tickers()
```

`step()`: draw `n` normals, multiply by `L`, apply the GBM update per ticker, maybe apply an
event, return rounded prices. Hot path, called twice a second.

### 4.2 `SimulatorDataSource`

| Method | Behavior |
|---|---|
| `start(tickers)` | Read `PriceCache` for existing prices and use them as `seed_overrides`; build `GBMSimulator`; **write initial prices to the cache immediately** (so SSE has data before the first tick); start `_run_loop`. |
| `_run_loop` | `while True: step(); cache.update(...) per ticker; sleep(update_interval)`. A step exception is logged and the loop continues; it never dies silently. |
| `add_ticker` | Seed from cache if present, add to the simulator, write the first price to the cache **immediately** so a trade on it has a fill price (PLAN.md §8, "No cached price yet"). |
| `remove_ticker` | Remove from simulator and from the cache. |
| `validate_ticker` | `ticker.upper() in NSE_SYMBOL_UNIVERSE`. Never raises. |
| `stop` | Cancel the task and await it. Safe to call twice. |

`previous_close` handling: the simulator never passes one to `PriceCache.update`, so the cache
sets it to the ticker's first price (cold start) or **carries forward** whatever is already
there (e.g. Tapetide's real exchange close after a handover). That is what keeps the daily
change % continuous across a Tapetide to simulator handover (PLAN.md §6).

## 5. Handover behavior

- **Tapetide to simulator** (market closes, key removed, or Tapetide failure fallback): the
  manager starts a new `SimulatorDataSource` with the old source's ticker list. Its `start()`
  seeds from the real prices left in the cache, and the real `previous_close` carries forward.
  No jump in price or in day-change %.
- **Simulator to Tapetide** (market opens): Tapetide's first poll overwrites prices and replaces
  `previous_close` with the exchange close, so day-change % visibly jumps. Intended.
- The `PriceCache` object is never replaced; SSE clients see neither gap nor reset.

## 6. Testing (built: `test_simulator.py`, `test_simulator_source.py`)

- Prices stay positive over many steps; every step returns every tracked ticker.
- GBM math: with `sigma=0` and fixed `mu`, price follows the closed form; log-return mean and
  stdev over many steps match `(mu - sigma²/2)·dt` and `sigma·sqrt(dt)` within tolerance.
- Correlation: sample correlation of same-group tickers exceeds cross-group.
- Events: `event_probability=1.0` always produces a 2-5% move; `0` never does.
- Add/remove rebuilds the Cholesky and keeps the others' prices.
- Seeding priority order (section 3).
- `SimulatorDataSource`: cache populated immediately on `start`/`add_ticker`; removed from the
  cache on `remove_ticker`; seeds from existing cache prices; `validate_ticker` against the
  universe; stop is idempotent.

Determinism for tests: pass `np.random.seed(...)` and `random.seed(...)`, or use
`sigma=0, event_probability=0`. The live simulator is deliberately **not** deterministic.

## 7. Synthetic end-of-day history (design)

Needed by `SimulatedHistory` (`MARKET_INTERFACE.md` section 6.2) so `get_daily_bars` works with no
API key. The live simulator cannot supply this: it only has "now".

### 7.1 Requirements

1. **Deterministic and stateless**: the same `(ticker, day)` always yields the same bar, across
   calls, restarts and processes. No DB, no stored series.
2. **Range independent**: asking for Sep 15-Oct 16 returns exactly the bars that a Sep 1-Oct 16
   request returns for those days. (Otherwise charts shift when the window changes.)
3. **Anchored**: the close of the last completed trading day equals the live simulator's seed
   price (`SEED_PRICES`), so history joins the live price series.
4. **Same statistics as live**: per-ticker `mu`/`sigma` from `TICKER_PARAMS`, and cross-ticker
   correlation.
5. Valid OHLC: `low <= min(open, close) <= max(open, close) <= high`, prices `> 0`, weekdays only.

### 7.2 Approach

- **Randomness**: never use Python's `hash()` (randomized per process). Derive a
  `random.Random` from `sha256` of a label such as `("idio", ticker, day)`. Each (label, day) is
  its own independent stream, which gives requirements 1 and 2 for free: a day's return depends
  only on that day, not on how many days were generated.
- **Correlation**: daily shock `z = sqrt(w)·z_market(day) + sqrt(1-w)·z_idio(ticker, day)`
  with `w = 0.5`. `z_market` depends only on the day, so all tickers share it. This is a
  one-factor model; it approximates, rather than reuses, the sector Cholesky structure, which
  is intentional (no matrix, works for any ticker set; the pairwise correlation is `w` = 0.5, in
  the same range as the live 0.3-0.6).
- **Anchoring by walking backwards**: set `close[anchor] = anchor_price`, then for earlier days
  `close[i-1] = close[i] / exp(r_i)`; for later days (if the request extends past the anchor)
  walk forward with `close[i] = close[i-1] * exp(r_i)`. `r_i` is the GBM log-return into day
  `i`, with `dt = 1/252`.
- **Anchor day**: the last completed trading day: today if the market has closed, otherwise
  yesterday, stepping back over weekends. Holidays are not modeled (same as `nse_hours.py`).
  The anchor moves forward each day, so the whole synthetic history re-bases daily; this is fine
  for a demo and keeps the "last close" aligned with the live price. State it in the UI if
  history is ever charted next to real data.
- **OHLC from the close series**: open = previous close times a small gap
  `exp(N(0, 0.3·σ√dt))`; high/low extend beyond `max/min(open, close)` by a random fraction of
  an intraday range `~|N(0, 0.5·σ√dt)|`; volume is lognormal around 2M. Open/high/low/volume are
  cosmetic and not constrained to match the live tick stream.
- **Weekdays only**; no holiday calendar.

### 7.3 Reference implementation

Prototype, run against the invariants above (anchor close exact; two overlapping ranges
produce identical bars for shared days; OHLC valid). It belongs in
`backend/app/market/sim_history.py`; the `SimulatedHistory` class wraps `synth_bars` and returns
`DailyBars(source="simulated")`, building each `DailyBar` with `raw_close == close` (the
simulator has no corporate actions, so there is nothing to adjust).

```python
import hashlib
import math
import random
from datetime import date, timedelta

TRADING_DAYS = 252
MARKET_WEIGHT = 0.5  # share of daily variance from the common market factor


def _rng(*parts) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def trading_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def last_completed_day(today: date, market_open_now: bool) -> date:
    d = today - timedelta(days=1) if market_open_now else today
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def synth_bars(ticker, anchor_price, mu, sigma, start, end, anchor_day):
    """(day, open, high, low, close, volume) tuples, close(anchor_day) == anchor_price."""
    days = trading_days(min(start, anchor_day), max(end, anchor_day))
    a = days.index(anchor_day)          # ValueError if anchor_day is a weekend
    dt = 1 / TRADING_DAYS
    closes = [0.0] * len(days)
    closes[a] = anchor_price

    def ret(d):  # log-return INTO day d (close[d-1] -> close[d])
        z_mkt = _rng("mkt", d).gauss(0, 1)
        z_idio = _rng("idio", ticker, d).gauss(0, 1)
        z = math.sqrt(MARKET_WEIGHT) * z_mkt + math.sqrt(1 - MARKET_WEIGHT) * z_idio
        return (mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z

    for i in range(a, 0, -1):
        closes[i - 1] = closes[i] / math.exp(ret(days[i]))
    for i in range(a + 1, len(days)):
        closes[i] = closes[i - 1] * math.exp(ret(days[i]))

    bars = []
    for i, d in enumerate(days):
        if not (start <= d <= end):
            continue
        r = _rng("ohlc", ticker, d)
        prev = closes[i - 1] if i > 0 else closes[i] / math.exp(ret(d))
        o = prev * math.exp(r.gauss(0, sigma * math.sqrt(dt) * 0.3))
        c = closes[i]
        span = abs(r.gauss(0, sigma * math.sqrt(dt) * 0.5))
        h = max(o, c) * math.exp(span * r.random())
        lo = min(o, c) * math.exp(-span * r.random())
        vol = int(r.lognormvariate(math.log(2_000_000), 0.4))
        bars.append((d, round(o, 2), round(h, 2), round(lo, 2), round(c, 2), vol))
    return bars
```

Caveats on the prototype:

- Rounding to 2 dp after generation can, in rare edge cases on very low prices, make
  `high == low`; the OHLC test uses `<=`, not `<`.
- The pairwise correlation over a short window is noisy (a 33-day sample measured ~0.19 for
  HDFCBANK vs TCS against the 0.5 target); the model is right in expectation, not per window.
  Do not assert a tight correlation in tests on short ranges; use a long range (500+ days).
- Anchor beyond `end` costs extra generation. A request for 2000 days is still only 2000
  iterations of cheap math; no cache is required.

### 7.4 Tests for the history simulator

- Anchor: last bar close equals the seed price when `end == anchor_day`.
- Determinism: two calls, and a call in a fresh process, return equal bars.
- Range independence: overlapping ranges agree on the shared days.
- OHLC invariants and weekday-only on a 2000-day range.
- Unseeded ticker (e.g. WIPRO) still works, using `DEFAULT_PARAMS` and an anchor from a
  deterministic hash of the ticker rather than `random.uniform`, so it is stable across runs
  (the live simulator's random fallback is **not** deterministic and must not be used here).
- Correlation over 500+ days: same-market tickers positively correlated (expect ~0.5).
- `last_completed_day`: weekend rolls back to Friday; during market hours returns yesterday.

## 8. Extension points

| Want | Change |
|---|---|
| New default ticker | Add to `SEED_PRICES`, `TICKER_PARAMS`, optionally a correlation group, and `NSE_SYMBOL_UNIVERSE`. Also PLAN.md §7 if it becomes a default watchlist entry. |
| More realistic sectors | Extend `CORRELATION_GROUPS`; matrix rebuild is automatic. |
| Calmer/wilder demo | `event_probability` and `sigma`; do not touch `dt`. |
| Faster/slower ticks | `SimulatorDataSource(update_interval=...)`; the frontend's 250ms flash assumes <= 2 ticks/s. |
| Replayable run for a bug report | Seed `numpy` and `random` before `start()`. |
