# Market Data Backend — Detailed Design

Implementation-ready design for everything under `backend/app/market/`: the unified interface,
the shared price cache, the GBM simulator, the Tapetide MCP client, live handover, degraded-mode
fallback, health, SSE streaming, and how `main.py` and the API routes wire it in.

**Date:** 2026-10-19. **Supersedes** `planning/archive/MARKET_DATA_DESIGN.md` (the original
Massive/Polygon.io, US-ticker design). **Precedence:** `PLAN.md` wins on any conflict; raise the
conflict rather than silently diverging.

Companion references (read only when you need the detail):

| Doc | Use it for |
|---|---|
| `MARKET_DATA_SUMMARY.md` | One-page summary of what is built |
| `MARKET_INTERFACE.md` | The optional pull / end-of-day history API (summarized in §13 here) |
| `MARKET_SIMULATOR.md` | GBM math derivation and the synthetic-history algorithm |
| `TAPETIDE_API.md` | Tapetide tool payloads, quotas, verified-live facts |

### How to read this document

Every section is tagged:

- **[BUILT]** — exists in `backend/app/market/` and is tested (108 tests pass). The code shown is
  the real code, sometimes trimmed; the file is the source of truth.
- **[CHANGE]** — a modification to built code. Shown as the new version, with the reason.
- **[NEW]** — does not exist yet. Code is a complete, drop-in starting point.
- **[OPTIONAL]** — not required by PLAN.md; design kept so nobody re-derives it.

> **Implementation status (updated 2026-10-19, after `MARKET_DATA_REVIEW.md`).** The Tapetide
> error-handling hardening in this document is **now implemented**: the `is_error` tool-error
> wrapper (§9.3, as `_call_tool` raising `TapetideToolError`/`MarketDataError`), the per-call
> timeout (§9.4, `TAPETIDE_CALL_TIMEOUT`), the mid-poll removal guard (§9.4), and the SSE
> router-per-call fix (§12.1). The following §/items were **intentionally realized differently**
> and are equivalent, not pending: the `desired_source_name()`/`build_source()` factory split
> (§10) — the shipped `factory.create_market_data_source` + `manager` cover the same decisions;
> the 1s health tick and split `_maybe_fallback`/`_swap_locked` (§11) — the shipped `manager`
> uses a ~5s combined tick with the same latch semantics (tested in `test_degraded.py`); the
> monotonic `last_write_age` (§5.2) — shipped as `PriceCache.seconds_since_update()`; and the
> standalone `health.py`/`tracking.py` modules (§14.3/§14.4) — their logic lives inline in the
> backend's `routes/health.py`, `portfolio.py`, and `watchlist.py`. Treat the code as source of
> truth where it differs.

---

## Table of Contents

1. [Requirements traceability](#1-requirements-traceability)
2. [Architecture](#2-architecture)
3. [File layout](#3-file-layout)
4. [Data model — `models.py`](#4-data-model--modelspy)
5. [Price cache — `cache.py`](#5-price-cache--cachepy)
6. [Unified interface — `interface.py`](#6-unified-interface--interfacepy)
7. [Seed data and trading hours](#7-seed-data-and-trading-hours)
8. [Simulator — `simulator.py`](#8-simulator--simulatorpy)
9. [Tapetide client — `tapetide_client.py`](#9-tapetide-client--tapetide_clientpy)
10. [Source selection — `factory.py`](#10-source-selection--factorypy)
11. [Manager, handover and fallback — `manager.py`](#11-manager-handover-and-fallback--managerpy)
12. [SSE streaming — `stream.py`](#12-sse-streaming--streampy)
13. [Pull API and end-of-day history (optional)](#13-pull-api-and-end-of-day-history-optional)
14. [Integration: lifespan, health, routes](#14-integration-lifespan-health-routes)
15. [Error handling matrix](#15-error-handling-matrix)
16. [Configuration reference](#16-configuration-reference)
17. [Testing](#17-testing)
18. [Implementation order](#18-implementation-order)

---

## 1. Requirements traceability

Every market-data requirement in PLAN.md, where it lives, and whether it exists.

| PLAN.md requirement | Where | Status |
|---|---|---|
| One interface for simulator and Tapetide (§6) | `interface.MarketDataSource` | BUILT |
| Downstream depends only on the manager + cache (§6) | `manager.MarketDataManager` | BUILT |
| GBM, ~500ms ticks, correlated sectors, 2-5% random events (§6) | `simulator.GBMSimulator` | BUILT |
| Simulator seeds from last real price (§6) | `SimulatorDataSource.start/add_ticker` | BUILT |
| Tapetide over MCP streamable HTTP, Bearer token, `get_batch_quotes` (§6) | `tapetide_client` | BUILT |
| Batches of ≤20, cache keyed by `requested` (§6) | `TapetideDataSource._poll_once/_cache_quote` | BUILT |
| All Tapetide calls serialized by an `asyncio.Lock` (§6) | `_call_lock` | BUILT |
| `validate_ticker` raises `MarketDataError` on transport failure (§6) | `interface`, `tapetide_client` | BUILT (incl. `is_error` tool-error → `MarketDataError`, §9.3) |
| Successful Tapetide validation seeds the cache (§6) | `validate_ticker` → `_cache_quote` | BUILT |
| Naive upstream timestamps parsed as IST (§7) | `_parse_timestamp` | BUILT |
| `MARKET_DATA_SOURCE` auto/simulator/tapetide (§5) | `factory` | BUILT, **[CHANGE]** §10 (split for the latch) |
| NSE hours 9:15-15:30 IST Mon-Fri, explicit IST conversion (§5) | `nse_hours` | BUILT |
| Live handover every ~60s, cache never replaced (§6) | `MarketDataManager._supervise` | BUILT, **[CHANGE]** §11 |
| `previous_close` carry-forward; day vs tick change (§6) | `PriceCache.update`, `PriceUpdate` | BUILT |
| SSE pushes whole map when version advances, ~500ms cadence (§6) | `stream` | BUILT (router-per-call fix applied, §12.1) |
| `TAPETIDE_POLL_SECONDS` named constant, default 2 (§6) | `tapetide_client` | **[NEW]** §9.2 |
| One-time budget warning when Tapetide starts polling (§6) | `TapetideDataSource._run` | **[NEW]** §9.3 |
| N=3 consecutive failures (poll errors **and** dead task) → fallback (§6) | `TapetideDataSource.is_degraded` | **[NEW]** §9.5 |
| `_force_fallback` + `retry_after` cooldown latch, 5 min (§6) | `MarketDataManager` | **[NEW]** §11 |
| `market_data_healthy`: cache written within ~10s (§6, §8) | `PriceCache.last_write_age` + `health.py` | **[NEW]** §5.2, §14.3 |
| Tracked = watchlist ∪ positions; untrack on remove / sell-to-zero (§6) | `tracking.untrack_if_unused` | **[NEW]** §14.4 |
| Lifespan ordering; snapshot falls back to `avg_cost` (§7) | `main.py` | **[NEW]** §14.1 |
| `MarketDataError` → 503 on the validation path (§6, §8) | watchlist route | **[NEW]** §14.5 |

---

## 2. Architecture

```
                       ┌──────────────────────────────────────────────────────────┐
                       │ MarketDataManager            (the only thing routes use) │
 env + IST clock ─────▶│  supervisor task (tick 1s)                               │
 (desired_source_name) │   ├─ every 60s: desired source changed?  → handover      │
                       │   └─ every tick: active source degraded? → fallback+latch│
                       │  _force_fallback / _retry_after (cooldown latch)         │
                       └──────────────┬───────────────────────────────────────────┘
                                      │ owns exactly one at a time
                     ┌────────────────┴─────────────────┐
                     ▼                                  ▼
          SimulatorDataSource                   TapetideDataSource
          GBMSimulator.step() every 0.5s         MCP Client (one per source lifetime)
                     │                           get_batch_quotes every 2s, ≤20/call
                     │                           failure counter, dead-task check
                     │ cache.update(...)                │ cache.update(...)
                     └──────────────┬───────────────────┘
                                    ▼
                   PriceCache  (one instance for the whole process; never replaced)
                    version counter · last_write_at · per-ticker PriceUpdate
                                    │
      ┌──────────────────┬──────────┴─────────┬────────────────────┬─────────────────┐
      ▼                  ▼                    ▼                    ▼                 ▼
 SSE /api/stream/   GET /api/watchlist   portfolio valuation   trade fills     GET /api/health
 prices (0.5s poll) (first render)       + 30s snapshots       (latest price)  (healthy flag)
```

### Rules that make this work

1. **One writer at a time, one cache forever.** A handover swaps the writer; the `PriceCache`
   object is created once in the lifespan and never replaced. SSE clients read the cache, so
   they see no gap.
2. **Sources push, consumers pull from the cache.** Nothing downstream calls a source for a
   price. The only source calls routes make are `validate_ticker`, `add_ticker`,
   `remove_ticker` — always through the manager.
3. **Tracking ≠ pricing.** A ticker can be tracked (in `get_tickers()`) and still have no cache
   entry for a moment. Consumers handle `None` (§14.6).
4. **"Couldn't check" ≠ "doesn't exist".** Transport failures raise `MarketDataError`; only a
   definitive answer returns `False`.

### Concurrency model

Everything runs on the single uvicorn event loop. Background tasks: the manager supervisor, the
active source's loop (simulator or Tapetide poller), one SSE generator per client, and the
30-second snapshot task (owned by `main.py`). `PriceCache` uses a `threading.Lock`, which is
uncontended on one loop but keeps the cache safe if a thread (e.g. `asyncio.to_thread` in a
future route) ever reads it. Locks:

| Lock | Type | Guards | Held across `await`? |
|---|---|---|---|
| `PriceCache._lock` | `threading.Lock` | price dict, version, last write | Never |
| `MarketDataManager._lock` | `asyncio.Lock` | `_active`, handover, latch | Yes (start/stop/validate) |
| `TapetideDataSource._call_lock` | `asyncio.Lock` | the shared MCP `Client` | Yes (one tool call, bounded by timeout) |

Lock order is always manager → Tapetide call lock, never the reverse, so they cannot deadlock.
Every Tapetide tool call has a hard timeout (§9.4), so the manager lock is never held unbounded.

---

## 3. File layout

```
backend/app/market/
├── __init__.py          public exports                                   [BUILT, CHANGE: exports]
├── models.py            PriceUpdate                                      [BUILT]
├── cache.py             PriceCache (+ last_write_age)                    [BUILT, CHANGE]
├── interface.py         MarketDataSource ABC, MarketDataError (+ is_degraded) [BUILT, CHANGE]
├── seed_prices.py       seeds, GBM params, correlation groups, NSE universe   [BUILT]
├── nse_hours.py         is_nse_trading_hours()                           [BUILT]
├── simulator.py         GBMSimulator, SimulatorDataSource                [BUILT]
├── tapetide_client.py   TapetideDataSource (+ failure tracking, tool errors) [BUILT, CHANGE]
├── factory.py           desired_source_name(), build_source(), create_...[BUILT, CHANGE]
├── manager.py           MarketDataManager (+ fallback latch, fast health tick) [BUILT, CHANGE]
├── stream.py            create_stream_router()                           [BUILT, CHANGE]
├── health.py            market_data_healthy()                            [NEW]
├── tracking.py          normalize_ticker(), untrack_if_unused()          [NEW]
└── api.py, history.py…  pull facade + EOD history                        [OPTIONAL, §13]
```

`backend/app/main.py`, `backend/app/routes/*` and `backend/db/` are owned by the backend agent;
§14 specifies exactly how they consume this package.

---

## 4. Data model — `models.py`

**[BUILT]** No changes.

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float     # previous TICK  → flash colour
    previous_close: float     # day baseline   → daily change %
    timestamp: float = field(default_factory=time.time)  # Unix seconds (upstream time under Tapetide)

    @property
    def change(self) -> float:            # tick-over-tick, rupees, 4 dp
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def day_change(self) -> float:
        return round(self.price - self.previous_close, 4)

    @property
    def day_change_percent(self) -> float:
        if self.previous_close == 0:
            return 0.0
        return round((self.price - self.previous_close) / self.previous_close * 100, 4)

    @property
    def direction(self) -> str:           # 'up' | 'down' | 'flat' (tick-over-tick)
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict: ...        # all fields + all derived properties
```

Example — HDFCBANK, Tapetide, mid-session:

```python
u = PriceUpdate("HDFCBANK", price=708.35, previous_price=708.50, previous_close=728.85,
                timestamp=1760862649.0)
u.direction            # 'down'   → red flash
u.change               # -0.15
u.day_change_percent   # -2.8127  → watchlist "daily change", coloured by day_change
u.to_dict()
# {"ticker": "HDFCBANK", "price": 708.35, "previous_price": 708.5, "previous_close": 728.85,
#  "timestamp": 1760862649.0, "change": -0.15, "change_percent": -0.0212,
#  "day_change": -20.5, "day_change_percent": -2.8127, "direction": "down"}
```

Rounding contract: derived fields are 4 dp here; **API responses round money and percentages to
2 dp** (PLAN.md §8) at the route layer. SSE sends `to_dict()` as is.

Why frozen + slots: updates are shared between the SSE generators, the routes and the cache;
immutability means a reader can never observe a half-written update, and slots keep the
per-tick allocation cheap (~20 objects/s).

---

## 5. Price cache — `cache.py`

### 5.1 Built behaviour **[BUILT]**

```python
cache = PriceCache()
cache.update("INFY", 1161.20)                        # first write: previous_price = previous_close = 1161.20
cache.update("INFY", 1161.45)                        # previous_price 1161.20, previous_close carried (1161.20)
cache.update("INFY", 1158.00, previous_close=1170.0) # explicit baseline (Tapetide) overrides
cache.update("INFY", 1158.10)                        # 1170.0 carried forward (simulator after handover)
cache.get("INFY"); cache.get_price("INFY"); cache.get_all(); cache.remove("INFY")
cache.version                                        # +1 on EVERY update, changed price or not
```

The `previous_close` carry-forward is what keeps the daily change % continuous on a
Tapetide → simulator handover: the simulator never passes `previous_close`, so it inherits the
real exchange close Tapetide left behind (PLAN.md §6).

`update()` rounds `price`, `previous_price` and `previous_close` to 2 dp. Keep it that way:
the SSE frame and REST payloads then agree to the paisa.

### 5.2 Write-recency for health **[CHANGE]**

PLAN.md §6 defines `market_data_healthy` as "the active source has written to the cache within
the last ~10s". That needs the **local time of the last write**, which the cache does not track
today. `PriceUpdate.timestamp` cannot be used: under Tapetide it is the upstream `updated_at`,
which was observed ~2.5 minutes behind the wall clock (TAPETIDE_API.md §4.1) and does not advance
at all after hours, so a perfectly healthy feed would read as stale.

Add a monotonic last-write stamp (monotonic so a system clock change cannot fake staleness):

```python
import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0
        self._last_write_monotonic: float | None = None   # NEW

    def update(self, ticker, price, timestamp=None, previous_close=None) -> PriceUpdate:
        with self._lock:
            ...                                            # unchanged body
            self._prices[ticker] = update
            self._version += 1
            self._last_write_monotonic = time.monotonic()  # NEW
            return update

    @property
    def last_write_age(self) -> float | None:              # NEW
        """Seconds since any writer last called update(), or None if never written.

        `remove()` is not a write: removing a ticker must not make a frozen feed look alive.
        """
        with self._lock:
            if self._last_write_monotonic is None:
                return None
            return time.monotonic() - self._last_write_monotonic
```

A Tapetide poll that returns an unchanged quote still calls `update()`, so "writer alive" is
measured correctly even when the market is quiet. That is the intended meaning: the flag
detects a dead or failing writer, not a quiet stock.

---

## 6. Unified interface — `interface.py`

### 6.1 Built contract **[BUILT]**

```python
class MarketDataError(Exception):
    """Source unreachable (transport/connection/tool failure) — NOT 'symbol not found'."""


class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...   # spawn background writer; call once
    @abstractmethod
    async def stop(self) -> None: ...                        # idempotent; no writes afterwards
    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...     # no-op if present
    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...  # no-op if absent; also cache.remove
    @abstractmethod
    def get_tickers(self) -> list[str]: ...
    @abstractmethod
    async def validate_ticker(self, ticker: str) -> bool: ...# True/False = definitive; raises MarketDataError if unreachable
```

Contract details every implementation honours (and the conformance test in §17 checks):

| Method | Must | Must not |
|---|---|---|
| `start` | write initial prices if it can do so synchronously (simulator); return promptly (Tapetide connects in its task) | block on network |
| `stop` | cancel and await its task; be safe twice; be safe if the task already died | remove tickers from the cache (the next source needs those prices to seed from) |
| `add_ticker` | be idempotent; make the ticker part of the next cycle | validate (the caller validated already) |
| `remove_ticker` | drop from the tracked set **and** `cache.remove(ticker)` | raise for unknown tickers |
| `validate_ticker` | return a definitive bool, or raise `MarketDataError` | return `False` for "couldn't reach the source" |

Tickers arrive already normalized (`strip().upper()`) from the API boundary (§14.2). Sources may
normalize again defensively; Tapetide does, the simulator does for `validate_ticker`.

### 6.2 Degradation hook **[CHANGE]**

The manager needs to ask "has the active source failed?" without knowing its concrete type. Add
one **non-abstract** method, so the simulator (which cannot fail this way) needs no change:

```python
class MarketDataSource(ABC):
    ...
    def is_degraded(self) -> bool:
        """True if this source can no longer be relied on to keep the cache fresh.

        Polled by MarketDataManager every supervisor tick. A True answer triggers a
        fallback to the simulator plus a cooldown latch (PLAN.md §6). Default: never.
        """
        return False
```

`MarketDataManager` itself also subclasses `MarketDataSource`; it does not override
`is_degraded` (it heals itself by falling back, it does not report up).

---

## 7. Seed data and trading hours

### 7.1 `seed_prices.py` **[BUILT]**

| Name | Contents |
|---|---|
| `SEED_PRICES` | 10 default tickers, fetched from Tapetide 2026-10-16 (HEROMOTOCO 5225.00, BEL 376.85, PIDILITIND 1502.80, LTF 253.85, HDFCBANK 728.85, INFY 1161.20, RELIANCE 1211.20, TCS 2465.00, ICICIBANK 1397.00, TATAMOTORS 421.05) |
| `TICKER_PARAMS` | per-ticker `sigma`/`mu` (banks ~0.20, TATAMOTORS 0.38, BEL 0.35) |
| `DEFAULT_PARAMS` | `{"sigma": 0.25, "mu": 0.08}` |
| `CORRELATION_GROUPS` | banking {HDFCBANK, ICICIBANK}, it {INFY, TCS}, auto {HEROMOTOCO, TATAMOTORS} |
| `INTRA_GROUP_CORR` / `CROSS_GROUP_CORR` | 0.6 / 0.3 |
| `NSE_SYMBOL_UNIVERSE` | ~60 real NSE symbols; the simulator's definition of "valid ticker" |

This file seeds **simulator state** only. Database row seeding (default user, 10 watchlist rows)
lives in `backend/db/` and never imports this module (PLAN.md §4).

To add a symbol the simulator should accept: add it to `NSE_SYMBOL_UNIVERSE`; optionally to
`SEED_PRICES`/`TICKER_PARAMS`/a correlation group. A universe member without a seed starts at
`random.uniform(50, 300)`.

### 7.2 `nse_hours.py` **[BUILT]**

```python
IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN, MARKET_CLOSE = time(9, 15), time(15, 30)

def is_nse_trading_hours(now: datetime | None = None) -> bool:
    moment = (now or datetime.now(IST)).astimezone(IST)   # explicit IST, any server TZ
    if moment.weekday() >= 5:
        return False
    return MARKET_OPEN <= moment.time() <= MARKET_CLOSE    # inclusive both ends
```

Examples: `2026-10-19 09:15 IST` → True; `15:30:00` → True; `15:30:01` → False;
`2026-10-19 03:45 UTC` (= 09:15 IST) → True; Saturday any time → False. No holiday calendar,
by design (PLAN.md §5). A naive `now` is treated by `astimezone` as server-local; callers always
pass aware datetimes (tests use explicit offsets).

`tzdata` is a Windows-only dependency in `pyproject.toml` because Windows has no system zoneinfo.

---

## 8. Simulator — `simulator.py`

**[BUILT]** No changes required. Summarized here so an implementer of the rest of the backend
understands its behaviour; derivations are in `MARKET_SIMULATOR.md`.

### 8.1 `GBMSimulator` — pure, synchronous math

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600      # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR      # ≈ 8.48e-8

    def __init__(self, tickers, dt=DEFAULT_DT, event_probability=0.001, seed_overrides=None): ...

    def step(self) -> dict[str, float]:
        n = len(self._tickers)
        if n == 0:
            return {}
        z = np.random.standard_normal(n)
        if self._cholesky is not None:
            z = self._cholesky @ z                    # correlated N(0,1) draws
        out = {}
        for i, t in enumerate(self._tickers):
            mu, sigma = self._params[t]["mu"], self._params[t]["sigma"]
            self._prices[t] *= math.exp((mu - 0.5 * sigma**2) * self._dt
                                        + sigma * math.sqrt(self._dt) * z[i])
            if random.random() < self._event_prob:    # "news" shock, 2-5% either way
                self._prices[t] *= 1 + random.uniform(0.02, 0.05) * random.choice([-1, 1])
            out[t] = round(self._prices[t], 2)        # internal price stays unrounded
        return out

    def add_ticker(self, ticker, seed_price=None): ...   # rebuilds Cholesky
    def remove_ticker(self, ticker): ...                 # rebuilds Cholesky
    def get_price(self, ticker) -> float | None: ...
    def get_tickers(self) -> list[str]: ...
```

Correlation matrix: diagonal 1, same group 0.6, else 0.3; `L = np.linalg.cholesky(C)` rebuilt on
every add/remove (O(n³), trivial for n < 50). All off-diagonals in [0.3, 0.6] keep `C` positive
definite, so Cholesky cannot fail.

Seed priority for a ticker: explicit `seed_price` > `seed_overrides` (last cached real price) >
`SEED_PRICES` > `random.uniform(50, 300)`.

What a tick looks like in rupees (per-tick stdev = `price · sigma · sqrt(dt)`, `sqrt(dt)` ≈
2.91e-4):

| Ticker | Price | sigma | 1-tick stdev | Visible at 2 dp? |
|---|---|---|---|---|
| HEROMOTOCO | 5225 | 0.28 | ≈ Rs 0.43 | almost every tick |
| HDFCBANK | 728.85 | 0.20 | ≈ Rs 0.042 | most ticks |
| LTF | 253.85 | 0.32 | ≈ Rs 0.024 | ~half the ticks |

Hence sparse flashes on cheap tickers, with the random events (≈ one every 50s across 10
tickers) supplying the drama — accepted in PLAN.md §13.

### 8.2 `SimulatorDataSource` — asyncio adapter

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache, update_interval=0.5, event_probability=0.001): ...

    async def start(self, tickers):
        # Seed from whatever is already in the cache (e.g. Tapetide's last real prices).
        seed_overrides = {t: p for t in tickers if (p := self._cache.get_price(t)) is not None}
        self._sim = GBMSimulator(tickers, event_probability=self._event_prob,
                                 seed_overrides=seed_overrides)
        for t in tickers:                                   # cache populated BEFORE first tick
            self._cache.update(ticker=t, price=self._sim.get_price(t))
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def add_ticker(self, ticker):
        self._sim.add_ticker(ticker, seed_price=self._cache.get_price(ticker))
        self._cache.update(ticker=ticker, price=self._sim.get_price(ticker))  # immediate fill price

    async def remove_ticker(self, ticker):
        self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    async def validate_ticker(self, ticker):
        return ticker.upper() in NSE_SYMBOL_UNIVERSE        # never raises

    async def _run_loop(self):
        while True:
            try:
                for t, p in self._sim.step().items():
                    self._cache.update(ticker=t, price=p)   # no previous_close → carried forward
            except Exception:
                logger.exception("Simulator step failed")   # log and keep going; never dies
            await asyncio.sleep(self._interval)
```

Usage:

```python
cache = PriceCache()
sim = SimulatorDataSource(cache)
await sim.start(["HDFCBANK", "INFY"])
cache.get_price("HDFCBANK")             # 728.85 immediately
await sim.add_ticker("WIPRO")           # in NSE_SYMBOL_UNIVERSE, no seed → uniform(50, 300)
await asyncio.sleep(1.1)
cache.get("WIPRO").direction            # 'up' | 'down' | 'flat'
await sim.stop()
```

Under the simulator, `previous_close` = the ticker's first price this process saw (or the
inherited real close), so "daily change %" means "since the session began" (PLAN.md §6).

---

## 9. Tapetide client — `tapetide_client.py`

### 9.1 Built behaviour **[BUILT]**

- `start()` stores the tickers and spawns `_run()`; it returns immediately.
- `_run()` owns the connection for the source's lifetime: `httpx2.AsyncClient` with
  `Authorization: Bearer <key>` → `streamable_http_client(TAPETIDE_MCP_URL, http_client=...)` →
  `async with Client(transport)`; immediate first poll, then poll every interval.
- `_poll_once()` splits tickers into batches of 20 and calls `get_batch_quotes` per batch.
- `_cache_quote()` keys by `requested`, skips `found: false`, parses `updated_at` (naive → IST),
  passes `prev_close` as `previous_close`, skips malformed rows with a warning.
- `validate_ticker()` makes a 1-symbol call; `found: true` writes the quote into the cache.
- `_call_lock` serializes the poller and validation on the one `Client`.

The changes below fix three gaps in that code: tool errors are silently treated as "no data",
a hung call can hold the lock for the 300s httpx read timeout, and nothing counts failures.

### 9.2 Constants **[CHANGE]**

```python
TAPETIDE_MCP_URL = "https://mcp.tapetide.com/mcp"
BATCH_SIZE = 20                  # get_batch_quotes accepts at most 20 symbols
TAPETIDE_POLL_SECONDS = 2.0      # PLAN.md §6 named constant; raise it to save daily quota
TAPETIDE_DAILY_CALL_CAP = 400    # project owner's plan; used only in the startup warning
TAPETIDE_CALL_TIMEOUT = 10.0     # hard cap per tool call (seconds), so a hang becomes a failure
TAPETIDE_CONNECT_WAIT = 5.0      # how long validate_ticker waits for the first connection
FAILURE_THRESHOLD = 3            # N consecutive failures → degraded (PLAN.md §6)
IST = ZoneInfo("Asia/Kolkata")
```

`poll_interval` in the constructor defaults to `TAPETIDE_POLL_SECONDS`, so tests can still pass
their own.

Budget arithmetic, for the warning text and for anyone tuning the knob:

| `TAPETIDE_POLL_SECONDS` | Calls/min (≤20 tickers) | 400 calls last |
|---|---|---|
| 2 (default) | 30 | ≈ 13 min |
| 5 | 12 | ≈ 33 min |
| 15 | 4 | 100 min |

### 9.3 Tool-call wrapper with error detection and timeout **[CHANGE]**

The MCP SDK (`mcp` 2.3) does **not** raise when a tool fails: `call_tool` returns a
`CallToolResult` with `is_error=True` and the message in `content` (verified against the
installed SDK). Today `_call_batch_quotes` reads `structured_content`, finds `None`, and returns
`[]`. Consequences: a quota-exhausted or auth-failing poll looks like "no data" (never counted as
a failure, feed freezes silently), and `validate_ticker` would answer `False` → a 400 "No stock
with ticker X exists" for a transport problem — exactly what PLAN.md §6 forbids.

```python
class TapetideToolError(MarketDataError):
    """Tapetide reached, but the tool call returned is_error=True (quota, auth, server error)."""


def _error_text(result) -> str:
    parts = [getattr(c, "text", "") for c in (result.content or [])]
    return " ".join(p for p in parts if p) or "unknown tool error"


class TapetideDataSource(MarketDataSource):
    ...
    async def _call_tool(self, name: str, arguments: dict) -> dict:
        """One serialized, time-bounded tool call. Returns structured_content (or {}).

        Raises MarketDataError for: no client, timeout, transport exception, is_error result.
        """
        client = self._client
        if client is None:
            raise MarketDataError("Tapetide client is not connected")
        async with self._call_lock:
            try:
                result = await asyncio.wait_for(
                    client.call_tool(name, arguments), timeout=TAPETIDE_CALL_TIMEOUT
                )
            except TimeoutError as e:
                raise MarketDataError(f"Tapetide {name} timed out after {TAPETIDE_CALL_TIMEOUT}s") from e
            except MarketDataError:
                raise
            except Exception as e:  # httpx2 transport errors, MCPError, pydantic ValidationError
                raise MarketDataError(f"Tapetide {name} failed: {e}") from e
        if result.is_error:
            raise TapetideToolError(f"Tapetide {name} returned an error: {_error_text(result)}")
        return result.structured_content or {}

    async def _call_batch_quotes(self, symbols: list[str]) -> list[dict]:
        payload = await self._call_tool("get_batch_quotes", {"symbols": symbols})
        return payload.get("data", [])
```

`asyncio.wait_for` (rather than the SDK's `read_timeout_seconds`) is used so the timeout covers
the whole call including any SDK-internal retry, and so tests can exercise it with a plain
`AsyncMock` that sleeps.

Note the behaviour change: `_call_batch_quotes` now **raises** on a missing client instead of
returning `[]`. The poller only calls it from inside `_run` while connected, and
`validate_ticker` already converted "no client" into `MarketDataError`, so callers are
unaffected; one existing test that asserted the `[]` return must be updated.

### 9.4 Polling, failure counting, dead-task detection **[CHANGE]**

PLAN.md §6 requires that **both** a swallowed per-batch error **and** a dead poll task arm the
fallback. Counting rule: one failed tool call = one failure; any successful poll call resets the
counter to zero. With N=3 at 2s, an outage is detected within ~6s.

```python
class TapetideDataSource(MarketDataSource):
    def __init__(self, api_key, price_cache, poll_interval: float = TAPETIDE_POLL_SECONDS,
                 failure_threshold: int = FAILURE_THRESHOLD) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._failure_threshold = failure_threshold
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: Client | None = None
        self._connected = asyncio.Event()
        self._call_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._stopping = False

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(dict.fromkeys(t.strip().upper() for t in tickers))
        self._task = asyncio.create_task(self._run(), name="tapetide-poller")

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        self._connected.clear()

    def is_degraded(self) -> bool:
        if self._consecutive_failures >= self._failure_threshold:
            return True
        # A poll task that exited on its own (not via stop()) produces no further per-batch
        # failures, so a counter alone would never reach N. Treat it as degraded immediately.
        return self._task is not None and self._task.done() and not self._stopping

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def _run(self) -> None:
        try:
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=httpx2.Timeout(30.0, read=60.0),
            ) as http_client:
                transport = streamable_http_client(TAPETIDE_MCP_URL, http_client=http_client)
                async with Client(transport) as client:
                    self._client = client
                    self._connected.set()
                    logger.warning(
                        "Tapetide polling started: %d tickers every %.1fs ≈ %d calls/min. "
                        "The %d calls/day plan lasts ≈ %d min of continuous polling. "
                        "Keep demo sessions short; raise TAPETIDE_POLL_SECONDS to save quota.",
                        len(self._tickers), self._interval, self._calls_per_minute(),
                        TAPETIDE_DAILY_CALL_CAP,
                        TAPETIDE_DAILY_CALL_CAP // max(self._calls_per_minute(), 1),
                    )
                    await self._poll_once()          # immediate first poll
                    while True:
                        await asyncio.sleep(self._interval)
                        await self._poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:                            # incl. ExceptionGroup from the SDK's task group
            logger.exception("Tapetide poller crashed")   # task now done → is_degraded() True
        finally:
            self._client = None
            self._connected.clear()

    def _calls_per_minute(self) -> int:
        batches = max(1, -(-len(self._tickers) // BATCH_SIZE))   # ceil
        return int(60 / self._interval * batches)

    async def _poll_once(self) -> None:
        tickers = list(self._tickers)                # snapshot: add/remove may run mid-poll
        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i : i + BATCH_SIZE]
            try:
                quotes = await self._call_batch_quotes(batch)
            except MarketDataError as e:
                self._consecutive_failures += 1
                logger.error("Tapetide poll failed (%d/%d) for %d symbols: %s",
                             self._consecutive_failures, self._failure_threshold, len(batch), e)
                continue
            self._consecutive_failures = 0
            for quote in quotes:
                if quote.get("requested", "").upper() in self._tickers:  # dropped mid-poll? skip
                    self._cache_quote(quote)
```

Why `except Exception` is enough in `_run`: the SDK runs its transport in an anyio task group,
so a connection failure (bad token → HTTP 401 during `initialize`) surfaces as an
`ExceptionGroup`, which is an `Exception` subclass. `CancelledError` is re-raised first so
`stop()` works; `KeyboardInterrupt`/`SystemExit` are deliberately not swallowed. Logging with `exception()` never prints the token: it is
only in a header, and httpx does not include headers in exception messages.

Why the `in self._tickers` check: without it, a ticker removed during an in-flight poll would be
written back into the cache after `remove_ticker` cleared it, leaving a ghost row in SSE.

The `read=60.0` timeout (down from 300s) is a backstop; `TAPETIDE_CALL_TIMEOUT` is the real
bound. The 60s still covers the SDK's long-lived GET stream for server notifications.

Bad token, end to end: `_run` raises during `Client(...).__aenter__` → logs "Tapetide poller
crashed" → task done → `is_degraded()` True → manager falls back on its next 1s tick (§11).

### 9.5 Validation **[CHANGE]**

```python
    async def validate_ticker(self, ticker: str) -> bool:
        ticker = ticker.strip().upper()
        if not self._connected.is_set():
            # Just started or reconnecting: give the first connect a moment rather than 503-ing.
            try:
                await asyncio.wait_for(self._connected.wait(), timeout=TAPETIDE_CONNECT_WAIT)
            except TimeoutError as e:
                raise MarketDataError("Tapetide is not connected") from e
        quotes = await self._call_batch_quotes([ticker])   # raises MarketDataError on any failure
        if not quotes or not quotes[0].get("found", False):
            return False                                    # definitive: Tapetide says no such symbol
        self._cache_quote(quotes[0])                        # seed the cache: "add X and buy 10" works
        return True
```

Validation failures are deliberately **not** added to `_consecutive_failures`: they are reported
to the caller (503), and one flaky add should not trigger a source swap. If the feed is really
down, the poller's own failures arm the fallback within seconds anyway.

Example exchange:

```python
await tap.validate_ticker("wipro ")      # → call get_batch_quotes(["WIPRO"])
# {"data": [{"requested": "WIPRO", "found": true, "price": 251.4, "prev_close": 249.9,
#            "updated_at": "2026-10-19T08:30:49+00:00", ...}]}
# → True, cache now has WIPRO at 251.4 (previous_close 249.9)

await tap.validate_ticker("NOTAREALCO")  # found: false → False  (API: 400)
await tap.validate_ticker("TCS")         # quota exhausted: is_error=True → TapetideToolError (API: 503)
```

### 9.6 `add_ticker` / `remove_ticker` **[BUILT]**

`add_ticker` appends (normalized, idempotent); the ticker is priced on the next poll — unless
`validate_ticker` already seeded the cache, which it does on the normal add path.
`remove_ticker` drops it and calls `cache.remove`.

---

## 10. Source selection — `factory.py`

**[CHANGE]** The latch (§11) has to ask "what *would* we pick?" without constructing a source,
and then build a *different* one. Split the factory into a pure decision and a builder, keeping
`create_market_data_source` as the composition so existing callers and tests keep working.

```python
"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os
from typing import Literal

from .cache import PriceCache
from .interface import MarketDataSource
from .nse_hours import is_nse_trading_hours
from .simulator import SimulatorDataSource
from .tapetide_client import TapetideDataSource

logger = logging.getLogger(__name__)

SourceName = Literal["simulator", "tapetide"]


def desired_source_name() -> SourceName:
    """Which source the env + IST clock say we should use right now. Pure; no side effects.

    Re-reads os.environ every call (not .env), per PLAN.md §5.
    """
    override = os.environ.get("MARKET_DATA_SOURCE", "auto").strip().lower()
    api_key = os.environ.get("TAPETIDE_API_KEY", "").strip()

    if override == "simulator":
        return "simulator"
    if override == "tapetide":
        if not api_key:
            raise RuntimeError("MARKET_DATA_SOURCE=tapetide requires TAPETIDE_API_KEY to be set")
        return "tapetide"
    if override != "auto":
        logger.warning("Unknown MARKET_DATA_SOURCE=%r; treating as 'auto'", override)
    return "tapetide" if api_key and is_nse_trading_hours() else "simulator"


def build_source(name: SourceName, price_cache: PriceCache) -> MarketDataSource:
    """Construct an unstarted source by label."""
    if name == "tapetide":
        api_key = os.environ.get("TAPETIDE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Tapetide source requested but TAPETIDE_API_KEY is not set")
        return TapetideDataSource(api_key=api_key, price_cache=price_cache)
    return SimulatorDataSource(price_cache=price_cache)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Unstarted source for the current moment. Used by tests and one-off scripts."""
    name = desired_source_name()
    logger.info("Market data source: %s", name)
    return build_source(name, price_cache)
```

Decision table (`desired_source_name`):

| `MARKET_DATA_SOURCE` | `TAPETIDE_API_KEY` | NSE open? | Result |
|---|---|---|---|
| `simulator` | any | any | simulator |
| `tapetide` | set | any | tapetide |
| `tapetide` | unset | any | `RuntimeError` (fail fast at startup) |
| `auto` / unset / unknown | set | yes | tapetide |
| `auto` / unset / unknown | set | no | simulator |
| `auto` / unset / unknown | unset | any | simulator |

Mid-run, if someone unsets the key while `MARKET_DATA_SOURCE=tapetide`, the supervisor's call
raises; the supervisor logs it and keeps the current source (§11), rather than crashing.

---

## 11. Manager, handover and fallback — `manager.py`

**[CHANGE]** The built manager swaps on a 60s tick by comparing `type(candidate)` with
`type(active)`. The new version adds: a fast tick (1s) that checks `is_degraded()`; the
`_force_fallback` + `_retry_after` cooldown latch; label-based comparison instead of
constructing a throwaway candidate every minute; an injectable clock for tests.

### 11.1 State machine

```
                  desired=tapetide (market opens / key set)
     ┌───────────┐ ─────────────────────────────────────────▶ ┌───────────┐
     │ SIMULATOR │                                             │ TAPETIDE  │
     │ (normal)  │ ◀───────────────────────────────────────── │           │
     └───────────┘     desired=simulator (market closes)       └─────┬─────┘
                                                                     │ is_degraded()
                                                                     │ (3 failures or dead task)
                                                                     ▼
                            cooldown elapsed AND desired=tapetide ┌───────────────────┐
                 ┌──────────────────────────────────────────────── │ SIMULATOR         │
                 │  (one retry; a fresh failure re-enters below)   │ (fallback latched,│
                 ▼                                                  │  retry_after=+5m) │
            TAPETIDE ──── is_degraded() again ───────────────────▶ └───────────────────┘
```

While latched, the 60s desired-source check is **suppressed** from swapping back to Tapetide
even though key + clock say Tapetide; without that, the supervisor would flap sim ↔ Tapetide
every minute against a broken server. If the market closes during the cooldown, desired becomes
`simulator`, which is already active, and the latch simply expires unused.

### 11.2 Code

```python
"""Supervises the active market data source: live handover between Tapetide and the
simulator, plus fallback with a cooldown latch when Tapetide fails (PLAN.md §6)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .cache import PriceCache
from .factory import SourceName, build_source, desired_source_name
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL = 60.0     # seconds between desired-source checks
DEFAULT_HEALTH_INTERVAL = 1.0     # seconds between is_degraded() checks
DEFAULT_FALLBACK_COOLDOWN = 300.0 # seconds the latch holds before one Tapetide retry


class MarketDataManager(MarketDataSource):
    _SOURCE_LABELS = {"TapetideDataSource": "tapetide", "SimulatorDataSource": "simulator"}

    def __init__(
        self,
        price_cache: PriceCache,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        health_interval: float = DEFAULT_HEALTH_INTERVAL,
        fallback_cooldown: float = DEFAULT_FALLBACK_COOLDOWN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache = price_cache
        self._check_interval = check_interval
        self._health_interval = health_interval
        self._fallback_cooldown = fallback_cooldown
        self._clock = clock
        self._active: MarketDataSource | None = None
        self._lock = asyncio.Lock()
        self._supervisor_task: asyncio.Task | None = None
        self._force_fallback = False
        self._retry_after: float | None = None

    # --- lifecycle -------------------------------------------------------------------------

    async def start(self, tickers: list[str]) -> None:
        async with self._lock:
            self._active = build_source(desired_source_name(), self._cache)
            await self._active.start(tickers)
        self._supervisor_task = asyncio.create_task(self._supervise(), name="market-data-supervisor")
        logger.info("MarketDataManager started: %s, %d tickers", self.active_source_name, len(tickers))

    async def stop(self) -> None:
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
        self._supervisor_task = None
        async with self._lock:
            if self._active:
                await self._active.stop()
                self._active = None

    # --- MarketDataSource delegation (unchanged) ---------------------------------------------

    async def add_ticker(self, ticker: str) -> None:
        async with self._lock:
            if self._active:
                await self._active.add_ticker(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        async with self._lock:
            if self._active:
                await self._active.remove_ticker(ticker)

    def get_tickers(self) -> list[str]:
        return self._active.get_tickers() if self._active else []

    async def validate_ticker(self, ticker: str) -> bool:
        async with self._lock:
            return await self._active.validate_ticker(ticker) if self._active else False

    @property
    def active_source_name(self) -> str:
        if self._active is None:
            return "none"
        name = type(self._active).__name__
        return self._SOURCE_LABELS.get(name, name)

    @property
    def fallback_active(self) -> bool:
        """True while the cooldown latch holds (for logs/diagnostics, not the API contract)."""
        return self._force_fallback

    # --- supervision -------------------------------------------------------------------------

    async def _supervise(self) -> None:
        last_check = self._clock()
        while True:
            await asyncio.sleep(self._health_interval)
            try:
                await self._maybe_fallback()
                if self._clock() - last_check >= self._check_interval:
                    last_check = self._clock()
                    await self._maybe_handover()
            except Exception:
                logger.exception("Market data supervision failed; keeping current source")

    def _latched(self) -> bool:
        """Is the fallback latch holding? Clears it (allowing one retry) once cooldown elapses."""
        if not self._force_fallback:
            return False
        if self._retry_after is not None and self._clock() >= self._retry_after:
            logger.info("Tapetide fallback cooldown elapsed; Tapetide may be retried")
            self._force_fallback = False
            self._retry_after = None
            return False
        return True

    async def _maybe_fallback(self) -> None:
        """Active source degraded → simulator now, and arm the latch."""
        async with self._lock:
            if self._active is None or not self._active.is_degraded():
                return
            failed = self.active_source_name
            self._force_fallback = True
            self._retry_after = self._clock() + self._fallback_cooldown
            await self._swap_locked("simulator", reason=f"{failed} degraded")
            logger.warning("Fell back to simulator; Tapetide retry in %.0fs", self._fallback_cooldown)

    async def _maybe_handover(self) -> None:
        """Swap if the env/clock decision changed, unless the fallback latch suppresses it."""
        desired: SourceName = desired_source_name()
        if desired == "tapetide" and self._latched():
            desired = "simulator"
        async with self._lock:
            if self._active is None or desired == self.active_source_name:
                return
            await self._swap_locked(desired, reason="desired source changed")

    async def _swap_locked(self, name: SourceName, *, reason: str) -> None:
        """Start the new source on the old one's tickers, then stop the old one.

        Caller holds self._lock. The PriceCache is untouched, so SSE sees no gap; the
        simulator seeds from whatever real prices are in it.
        """
        old = self._active
        tickers = old.get_tickers() if old else []
        new = build_source(name, self._cache)
        await new.start(tickers)
        if old:
            await old.stop()
        self._active = new
        logger.info("Market data handover (%s): %s -> %s, %d tickers",
                    reason, type(old).__name__ if old else None, name, len(tickers))
```

Ordering detail: start-new-then-stop-old means for a few hundred ms both write. That is fine:
the simulator writes the same tickers from the same cached prices, and at worst one extra
tick lands. Stop-then-start would instead leave a window with no writer at all.

On a simulator → simulator "fallback" (cannot happen — the simulator is never degraded) and on
a handover to the source already active, `_maybe_*` return early, so the existing
"no-op when unchanged" test still holds.

### 11.3 Timeline example — Tapetide outage at 11:00:00 IST

| Time | Event |
|---|---|
| 11:00:00 | last successful poll; poll #1 starts and hangs |
| 11:00:10 | poll #1 times out (`TAPETIDE_CALL_TIMEOUT`), failures=1 |
| 11:00:22 | poll #2 (started 11:00:12) times out, failures=2 |
| 11:00:34 | poll #3 times out, failures=3 → `is_degraded()` True |
| 11:00:35 | supervisor tick: swap to simulator (seeded from last real prices, real `previous_close` carried), latch until 11:05:35 |
| 11:01:00, 11:02:00 … | 60s checks: desired=tapetide but latched → stay on simulator |
| 11:05:35+ | next 60s check after cooldown: latch clears, swap to Tapetide (one retry) |
| retry fails | 3 more failures → fallback again, new latch to ~11:11 |
| retry succeeds | first poll overwrites prices with real ones; normal operation |

A hard failure (bad token) is faster: the task dies on connect, so fallback happens within ~1s
of start.

`/api/health` across this timeline: `data_source` reads `"tapetide"` until 11:00:25 then
`"simulator"`; `market_data_healthy` goes false once no write has happened for 10s (from
~11:00:10 to 11:00:35 — the frontend shows "stale"), then true again on the simulator's first
write. Fast failures (connection refused, tool error) fall back in ~6s instead of ~35s.

---

## 12. SSE streaming — `stream.py`

### 12.1 Router-per-call fix **[CHANGE]**

`router = APIRouter(...)` is module level today and the factory decorates it, so calling
`create_stream_router()` twice (two test apps, or a reload) registers `/prices` twice on the same
router, and both closures capture different caches. Create the router inside the factory:

```python
def create_stream_router(price_cache: PriceCache, interval: float = 0.5) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request, interval),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                     "X-Accel-Buffering": "no"},
        )

    return router
```

### 12.2 Generator **[BUILT]** (plus a keep-alive comment **[CHANGE]**)

```python
KEEPALIVE_SECONDS = 15.0


async def _generate_events(price_cache, request, interval=0.5):
    yield "retry: 1000\n\n"                       # browser reconnects after 1s
    last_version = -1                             # → first frame is sent immediately
    last_sent = time.monotonic()
    try:
        while True:
            if await request.is_disconnected():
                break
            version = price_cache.version
            if version != last_version:
                last_version = version
                prices = price_cache.get_all()
                if prices:
                    payload = json.dumps({t: u.to_dict() for t, u in prices.items()})
                    yield f"data: {payload}\n\n"
                    last_sent = time.monotonic()
            elif time.monotonic() - last_sent >= KEEPALIVE_SECONDS:
                yield ": keep-alive\n\n"          # SSE comment; EventSource ignores it
                last_sent = time.monotonic()
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
```

The keep-alive matters only when nothing writes (empty watchlist, or a dead feed before
fallback); it stops idle-connection reaping and lets the frontend's connection dot stay
truthful. It sends no `data:` so the frontend never sees a fake frame.

### 12.3 Wire format

```
retry: 1000

data: {"HDFCBANK": {"ticker": "HDFCBANK", "price": 728.91, "previous_price": 728.85,
       "previous_close": 728.85, "timestamp": 1760862649.51, "change": 0.06,
       "change_percent": 0.0082, "day_change": 0.06, "day_change_percent": 0.0082,
       "direction": "up"}, "INFY": {...}, ...}

data: {...}                      ← next frame ~500ms later (simulator) / ~2s (Tapetide)

: keep-alive                     ← only after 15s with no new version
```

(The JSON is a single line on the wire; wrapped here for reading.)

Contract reminders for the frontend (PLAN.md §6, §10): frames are the **whole** cache including
held-but-unwatched tickers; frames are **not** de-duplicated (flash on `direction != "flat"`,
not on frame arrival); several frames can share one Unix second (aggregate per second before
feeding Lightweight Charts).

Cost: one `get_all()` copy + one `json.dumps` of ~10-20 entries per client per frame — trivial
for a single-user app. If many clients ever connect, serialize once per version in a shared
broadcaster; not needed now.

---

## 13. Pull API and end-of-day history (optional)

**[OPTIONAL]** PLAN.md does not require this: §10 and §13 make the main chart live-since-load
with no history endpoint. The design is fully specified in `MARKET_INTERFACE.md` §4-10 (with the
synthetic-history algorithm in `MARKET_SIMULATOR.md` §7 and Tapetide paging in
`TAPETIDE_API.md` §5.3). The essentials, so this document covers the whole unified API:

### 13.1 Live pull: zero-cost reads from the cache

Most "give me prices for these tickers" needs (LLM context, portfolio valuation) are just cache
reads and need no new class:

```python
def get_quotes(cache: PriceCache, tickers: list[str]) -> dict[str, PriceUpdate | None]:
    """Latest quote per ticker. None = untracked or not priced yet. Never calls a provider."""
    return {t: cache.get(t) for t in dict.fromkeys(x.strip().upper() for x in tickers)}


def get_latest_closes(cache: PriceCache, tickers: list[str]) -> dict[str, float | None]:
    """Previous close per ticker (real exchange close under Tapetide)."""
    return {t: (u.previous_close if u else None) for t, u in get_quotes(cache, tickers).items()}
```

Untracked tickers are deliberately not fetched ad hoc: it would spend quota and break
"priced == tracked". Callers add the ticker through the validated watchlist path first.

### 13.2 History, if a future plan revision wants it

```python
@dataclass(frozen=True, slots=True)
class DailyBar:
    ticker: str; day: date
    open: float; high: float; low: float; close: float   # Tapetide: split/bonus adjusted
    raw_close: float | None                               # printed close; compare THIS to live prices
    volume: int | None
    source: str                                           # "tapetide" | "simulated"


class HistoricalSource(ABC):
    @abstractmethod
    async def get_daily_bars(self, ticker: str, start: date, end: date) -> "DailyBars": ...


class TapetideHistory(HistoricalSource):
    """Own short-lived MCP client per batch (does not stall the 2s poller's lock).
    get_price_history(symbol, days=calendar_days, end_date) paged by meta.window.next_cursor.
    A tool error whose text starts 'Stock not found' → DailyBars(error='unknown ticker');
    any other failure → MarketDataError. Remember: tool errors arrive as is_error results (§9.3)."""


class SimulatedHistory(HistoricalSource):
    """Deterministic, stateless sha256-seeded one-factor GBM, anchored so the last completed
    day's close == SEED_PRICES[ticker]. Weekdays only. Never raises."""
```

Selection for history differs from live: key set → Tapetide **any time of day** (history is most
useful when the market is closed), else simulated. Results go through a TTL `EodCache` (24h for
closed ranges, 15 min if the range includes today). Adding it requires a PLAN.md §8 endpoint
and a §13 decision change first.

---

## 14. Integration: lifespan, health, routes

Owned by the backend agent; specified here so the market package is used correctly.

### 14.1 Lifespan (`app/main.py`) **[NEW]**

```python
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio, os

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")                    # before any os.environ read (PLAN.md §5)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.market import MarketDataManager, PriceCache, create_stream_router

DB_PATH = Path(os.environ.get("DATABASE_PATH") or REPO_ROOT / "db" / "finally.db")
FRONTEND_OUT = Path(os.environ.get("FRONTEND_DIR") or REPO_ROOT / "frontend" / "out")

price_cache = PriceCache()                          # ONE cache for the process lifetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db(DB_PATH)                                     # 1. schema + seed (idempotent)
    watchlist = await load_watchlist(db)                            # 2. ordered by added_at
    positions = await load_positions(db)
    tracked = list(dict.fromkeys([*watchlist, *(p.ticker for p in positions)]))

    manager = MarketDataManager(price_cache)                        # 3. watchlist ∪ held
    await manager.start(tracked)

    snapshot_task = asyncio.create_task(snapshot_loop(db, price_cache))   # 4. every 30s
    await record_snapshot(db, price_cache)                          # 5. startup snapshot

    app.state.db, app.state.cache, app.state.market = db, price_cache, manager
    try:
        yield                                                       # 6. serve
    finally:
        await manager.stop()                                        # reverse order
        snapshot_task.cancel()
        await asyncio.gather(snapshot_task, return_exceptions=True)
        await db.close()


app = FastAPI(lifespan=lifespan)
register_error_handlers(app)                       # {"error": ...} envelope for 400/422/500
app.include_router(create_stream_router(price_cache))
app.include_router(api_router)                     # portfolio, watchlist, chat, health
app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True), name="static")   # LAST
```

Valuation helper for step 5 and the snapshot loop — falls back to `avg_cost` when the price has
not arrived (Tapetide's first poll is asynchronous), so a snapshot is never valued at zero:

```python
def position_value(cache: PriceCache, ticker: str, quantity: float, avg_cost: float) -> float:
    price = cache.get_price(ticker)
    return quantity * (price if price is not None else avg_cost)
```

### 14.2 Ticker normalization — `market/tracking.py` **[NEW]**

```python
def normalize_ticker(raw: str) -> str:
    """PLAN.md §8: every ticker is strip().upper() at the API boundary and stored that way."""
    ticker = (raw or "").strip().upper()
    if not ticker:
        raise ValueError("Ticker must not be empty")
    return ticker
```

Path segments arrive URL-decoded by FastAPI (`M%26M` → `M&M`), so the route only normalizes.

### 14.3 Health — `market/health.py` **[NEW]**

```python
HEALTHY_WRITE_WINDOW = 10.0   # seconds; > Tapetide's 2s poll, < the frontend's stale threshold


def market_data_healthy(manager: MarketDataManager, cache: PriceCache,
                        window: float = HEALTHY_WRITE_WINDOW) -> bool:
    if not manager.get_tickers():
        return True              # nothing to price: an empty set is not a frozen feed
    age = cache.last_write_age
    return age is not None and age < window
```

```python
@router.get("/api/health")
async def health(request: Request) -> dict:
    m, c = request.app.state.market, request.app.state.cache
    return {"status": "ok", "data_source": m.active_source_name,
            "market_data_healthy": market_data_healthy(m, c)}
# → {"status": "ok", "data_source": "simulator", "market_data_healthy": true}
```

### 14.4 Tracked-ticker coordination **[NEW]**

PLAN.md §6: tracked = watchlist ∪ positions. Two transitions remove tracking; both go through one
function so the rule lives in one place. It takes booleans, not a DB handle, so `market/` stays
database-agnostic.

```python
async def untrack_if_unused(manager: MarketDataManager, ticker: str, *,
                            on_watchlist: bool, held: bool) -> bool:
    """Stop pricing `ticker` if nothing needs it any more. Returns True if untracked."""
    if on_watchlist or held:
        return False
    await manager.remove_ticker(ticker)      # also clears it from the cache / SSE
    return True
```

Call sites:

```python
# DELETE /api/watchlist/{ticker}
ticker = normalize_ticker(ticker)
removed = await db_remove_watchlist(db, ticker)
await untrack_if_unused(manager, ticker, on_watchlist=False, held=await db_is_held(db, ticker))
return {"ticker": ticker, "removed": removed}

# sell that zeroes a position (inside the trade handler, after the position row is deleted)
if position_deleted:
    await untrack_if_unused(manager, ticker,
                            on_watchlist=await db_on_watchlist(db, ticker), held=False)
```

### 14.5 Watchlist add: duplicate → validate → track **[NEW]**

```python
@router.post("/api/watchlist")
async def add_to_watchlist(body: AddTicker, request: Request):
    db, manager = request.app.state.db, request.app.state.market
    ticker = normalize_ticker(body.ticker)

    if (existing := await db_get_watchlist_entry(db, ticker)) is not None:
        return existing                       # idempotent, BEFORE validation: spends no quota

    try:
        valid = await manager.validate_ticker(ticker)
    except MarketDataError:
        return JSONResponse(status_code=503,
                            content={"error": f"Couldn't check {ticker} right now. Try again shortly."})
    if not valid:
        return JSONResponse(status_code=400,
                            content={"error": f"No stock with ticker {ticker} exists"})

    entry = await db_insert_watchlist(db, ticker)   # {"ticker": ..., "added_at": ...}
    await manager.add_ticker(ticker)                # idempotent if already held/tracked
    return entry
```

The AI's `watchlist_changes` path calls the same function body (shared service function, not the
HTTP route), so the 400/503 messages are identical in chat.

### 14.6 Trades: tracked and priced **[NEW]**

```python
def fill_price(manager: MarketDataManager, cache: PriceCache, ticker: str) -> float:
    if ticker not in manager.get_tickers():
        raise TradeError(f"Only tickers in your watchlist or held in your portfolio can be traded. "
                         f"Add {ticker} to your watchlist first.")
    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker} yet — try again in a moment.")
    return price
```

`TradeError` maps to `400 {"error": ...}`. Use `manager.get_tickers()` (the tracked set) for the
tracked check, not `ticker in cache` — the two can briefly differ, and the error messages
distinguish them.

### 14.7 LLM context (PLAN.md §9 step 1)

```python
def market_context(manager: MarketDataManager, cache: PriceCache, watchlist: list[str]) -> dict:
    return {
        "data_source": manager.active_source_name,     # 'tapetide' → backend appends SEBI text
        "watchlist": [
            {"ticker": t, "price": u.price, "day_change_percent": round(u.day_change_percent, 2)}
            if (u := cache.get(t)) else {"ticker": t, "price": None}
            for t in watchlist
        ],
    }
```

Read `active_source_name` **once per chat turn** and use that same value for both the prompt and
the SEBI-disclaimer decision, so a handover mid-turn cannot make them disagree.

---

## 15. Error handling matrix

| Situation | Detected by | Behaviour | User sees |
|---|---|---|---|
| Unknown symbol, simulator | `validate_ticker` → False | no row created | 400 "No stock with ticker X exists" |
| Unknown symbol, Tapetide | `found: false` → False | no row created | same 400 |
| Tapetide unreachable / timeout on validate | `MarketDataError` | no row created | 503 "Couldn't check X right now" |
| Tapetide tool error (quota, auth) on validate | `is_error` → `TapetideToolError` | same | same 503 |
| Poll call fails | `_poll_once` counter | log; after 3 in a row → fallback | brief "stale" badge, then "SIMULATED" |
| Bad token / connect failure | `_run` crashes, task done | fallback within ~1s | "SIMULATED" badge |
| Tapetide still broken after cooldown | counter again | re-fallback, new 5-min latch | stays "SIMULATED" |
| Malformed quote row | `_cache_quote` | skip that ticker this poll, warn | that ticker holds its last price |
| Simulator step exception | `_run_loop` | log, continue next tick | nothing |
| Trade on untracked ticker | `fill_price` | rejected | 400 "Only tickers in your watchlist…" |
| Trade on tracked, unpriced ticker | `fill_price` | rejected | 400 "No price available… yet" |
| Key removed with `MARKET_DATA_SOURCE=tapetide` mid-run | `desired_source_name` raises | supervisor logs, keeps current source | nothing |
| `MARKET_DATA_SOURCE=tapetide` without key at startup | `RuntimeError` in lifespan | process exits | start script reports failure |
| SSE client disconnects | `request.is_disconnected()` | generator exits | — |
| No tracked tickers | — | no frames; keep-alive every 15s; health stays true | empty panels |

---

## 16. Configuration reference

Environment (PLAN.md §5) — read by the market package:

| Variable | Default | Read where | Effect |
|---|---|---|---|
| `TAPETIDE_API_KEY` | empty | `factory` (each supervisor check) | enables Tapetide during NSE hours |
| `MARKET_DATA_SOURCE` | `auto` | `factory` (each supervisor check) | `auto` / `simulator` / `tapetide` |

Code constants:

| Constant | Module | Value |
|---|---|---|
| `update_interval` (simulator) | `simulator` | 0.5 s |
| `event_probability` | `simulator` | 0.001 per ticker per tick |
| `GBMSimulator.DEFAULT_DT` | `simulator` | 0.5 / (252·6.5·3600) ≈ 8.48e-8 |
| `INTRA_GROUP_CORR` / `CROSS_GROUP_CORR` | `seed_prices` | 0.6 / 0.3 |
| `TAPETIDE_MCP_URL` | `tapetide_client` | `https://mcp.tapetide.com/mcp` |
| `BATCH_SIZE` | `tapetide_client` | 20 |
| `TAPETIDE_POLL_SECONDS` | `tapetide_client` | 2.0 |
| `TAPETIDE_CALL_TIMEOUT` | `tapetide_client` | 10.0 s |
| `TAPETIDE_CONNECT_WAIT` | `tapetide_client` | 5.0 s |
| `FAILURE_THRESHOLD` | `tapetide_client` | 3 |
| `DEFAULT_CHECK_INTERVAL` | `manager` | 60 s |
| `DEFAULT_HEALTH_INTERVAL` | `manager` | 1 s |
| `DEFAULT_FALLBACK_COOLDOWN` | `manager` | 300 s |
| SSE `interval` / `KEEPALIVE_SECONDS` | `stream` | 0.5 s / 15 s |
| `HEALTHY_WRITE_WINDOW` | `health` | 10 s |
| `MARKET_OPEN` / `MARKET_CLOSE` | `nse_hours` | 09:15 / 15:30 IST |

Updated `__init__.py` exports:

```python
from .cache import PriceCache
from .factory import build_source, create_market_data_source, desired_source_name
from .health import market_data_healthy
from .interface import MarketDataError, MarketDataSource
from .manager import MarketDataManager
from .models import PriceUpdate
from .stream import create_stream_router
from .tracking import normalize_ticker, untrack_if_unused
```

---

## 17. Testing

Existing suite: `cd backend && uv run --extra dev pytest` → 108 passed. Keep every existing test
green. Two test adjustments are expected: any Tapetide test asserting that
`_call_batch_quotes` returns `[]` without a client (it now raises), and the `_mock_client`
helper in `test_tapetide.py`, which must set `result.is_error = False` — an unset attribute on a
`MagicMock` is a truthy `MagicMock`, so every mocked call would otherwise read as a tool error.
Tests that set `source._client` directly must also call `source._connected.set()` before
`validate_ticker`.

### 17.1 New tests by module

| Module | Test |
|---|---|
| `test_cache.py` | `last_write_age` is None before any write; small after `update`; **unchanged** by `remove` |
| `test_tapetide.py` | `is_error` result raises `TapetideToolError` from `_call_batch_quotes` |
| | `validate_ticker` on an `is_error` result raises `MarketDataError` (→ 503), **not** False |
| | a call slower than `TAPETIDE_CALL_TIMEOUT` raises `MarketDataError` (patch the constant small) |
| | 3 failing polls → `is_degraded()`; a success in between resets the counter |
| | dead task (task done, not stopped) → `is_degraded()`; after `stop()` → not degraded |
| | quote for a ticker removed mid-poll is not written back |
| | one-time budget warning logged on connect (caplog) |
| `test_factory.py` | `desired_source_name()` table in §10, incl. unknown value → auto |
| `test_manager.py` | degraded Tapetide → simulator within one health tick; tickers preserved |
| | latch suppresses swap-back during cooldown (fake clock) |
| | after cooldown, swap back to Tapetide once; degrade again → re-latched |
| | market closes during cooldown → stays simulator, latch expires harmlessly |
| | `desired_source_name` raising mid-run keeps the current source |
| `test_stream.py` (new) | `create_stream_router` twice → each router has exactly one `/prices` route |
| | generator: first frame immediate; no frame when version unchanged; keep-alive after window |
| `test_health.py` (new) | no tickers → healthy; fresh write → healthy; age > 10s → unhealthy |
| `test_tracking.py` (new) | `untrack_if_unused` matrix (watched × held); `normalize_ticker(" m&m ") == "M&M"` |
| conformance (new) | both sources, parametrized: `stop()` twice is safe; `remove_ticker` unknown is a no-op; `add_ticker` twice is idempotent; `validate_ticker` returns bool |

### 17.2 Sample tests

```python
# tests/market/test_tapetide.py
def _error_client(text: str) -> MagicMock:
    client, result = MagicMock(), MagicMock()
    result.is_error = True
    result.structured_content = None
    result.content = [MagicMock(text=text)]
    client.call_tool = AsyncMock(return_value=result)
    return client


async def test_validate_tool_error_is_transport_failure_not_not_found():
    source = TapetideDataSource(api_key="k", price_cache=PriceCache(), poll_interval=60.0)
    source._client = _error_client("Daily quota exceeded")
    source._connected.set()
    with pytest.raises(MarketDataError):
        await source.validate_ticker("TCS")


async def test_three_consecutive_poll_failures_degrade_and_success_resets():
    source = TapetideDataSource(api_key="k", price_cache=PriceCache(), poll_interval=60.0)
    source._tickers = ["TCS"]
    source._client = _error_client("boom")
    await source._poll_once(); await source._poll_once()
    assert not source.is_degraded()
    source._client = _mock_client([_quote("TCS", 2465.0, "2026-10-19T08:30:49+00:00")])
    await source._poll_once()
    assert source.consecutive_failures == 0
    source._client = _error_client("boom")
    for _ in range(3):
        await source._poll_once()
    assert source.is_degraded()


async def test_dead_poll_task_is_degraded():
    source = TapetideDataSource(api_key="k", price_cache=PriceCache())
    source._task = asyncio.create_task(asyncio.sleep(0))   # stands in for a crashed _run
    await source._task
    assert source.is_degraded()
```

```python
# tests/market/test_manager.py
class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


async def test_fallback_latch_suppresses_flap_then_retries():
    cache, clock = PriceCache(), FakeClock()
    m = MarketDataManager(cache, check_interval=1e9, fallback_cooldown=300.0, clock=clock)
    env = {"TAPETIDE_API_KEY": "k"}
    with patch.dict(os.environ, env, clear=True), \
         patch("app.market.factory.is_nse_trading_hours", return_value=True):
        await m.start(["TCS"])
        assert m.active_source_name == "tapetide"

        with patch.object(TapetideDataSource, "is_degraded", return_value=True):
            await m._maybe_fallback()
        assert m.active_source_name == "simulator" and m.fallback_active
        assert m.get_tickers() == ["TCS"]

        clock.t = 299.0
        await m._maybe_handover()                  # desired=tapetide, but latched
        assert m.active_source_name == "simulator"

        clock.t = 301.0
        await m._maybe_handover()                  # cooldown elapsed → one retry
        assert m.active_source_name == "tapetide" and not m.fallback_active
        await m.stop()
```

Patching `TapetideDataSource.is_degraded` avoids any network: the real `_run` task is started
but `stop()` cancels it before it can connect in a test (the httpx connection attempt to an
unreachable host would otherwise log a crash, which is harmless). For a fully offline test,
also patch `TapetideDataSource._run` with `AsyncMock()`.

```python
# tests/market/test_stream.py
def test_router_factory_is_independent():
    r1, r2 = create_stream_router(PriceCache()), create_stream_router(PriceCache())
    assert [r.path for r in r1.routes] == ["/api/stream/prices"]
    assert [r.path for r in r2.routes] == ["/api/stream/prices"]
```

### 17.3 Manual verification

```bash
cd backend
uv run --extra dev pytest -q
uv run --extra dev ruff check app/ tests/
uv run --extra demo market_data_demo.py          # simulator dashboard, 60s
# With a real key, during NSE hours (spends a few calls):
MARKET_DATA_SOURCE=tapetide TAPETIDE_API_KEY=... uv run python -m app.market.smoke   # optional script,
#   see TAPETIDE_API.md §5.6; compare the dashboard quota counter before/after
# Fallback drill: a bogus key must fall back to the simulator within ~1-2s
MARKET_DATA_SOURCE=tapetide TAPETIDE_API_KEY=bogus uv run uvicorn app.main:app --port 8001
curl -s localhost:8001/api/health      # → "data_source": "simulator" after a second or two
```

---

## 18. Implementation order

Each step is independently testable; land them in this order.

1. **`cache.py`**: `last_write_age` + tests. (No behaviour change for existing callers.)
2. **`interface.py`**: non-abstract `is_degraded()`.
3. **`tapetide_client.py`**: constants, `_call_tool` with timeout and `is_error`,
   `TapetideToolError`, failure counter, dead-task detection, `_connected` event, budget
   warning, mid-poll removal guard. Update the one test that relied on `[]`.
4. **`factory.py`**: `desired_source_name()` / `build_source()`; keep
   `create_market_data_source`.
5. **`manager.py`**: fast health tick, latch, `_swap_locked`, injectable clock + tests.
6. **`stream.py`**: router inside the factory, keep-alive + `test_stream.py`.
7. **`health.py`**, **`tracking.py`**, `__init__.py` exports + tests.
8. Hand off to the backend agent: §14 (lifespan, routes) is consumed as specified.
9. Update `planning/STATUS.md` (degraded mode built) and `MARKET_DATA_SUMMARY.md`.

Out of scope here: §13 history (optional), NSE holiday calendar, budget-aware throttling (PLAN.md
§6 explicitly declines it), multi-user caches.
