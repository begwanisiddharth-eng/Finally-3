# PLAN.md Review

A fresh review of `planning/PLAN.md` (910 lines), written from scratch. Findings were checked
against the code that already exists (`backend/app/market/`) where the plan makes factual claims
about it. Severity is about impact on the build, not on prose quality.

**Overall:** the plan is unusually complete and internally coherent for a document this size. It
is buildable as written. The findings below are mostly (a) a few places where the plan states
something the schema/code cannot actually support, (b) gaps around what the *frontend* does after
the AI mutates state, and (c) an earlier decision that got logged but not enforced.

---

## High

### H1. Realized P&L is claimed to be derivable from the `trades` table, but the schema cannot support it

PLAN.md:396 says: *"Realized P&L on a sell is `(sell_price - avg_cost) * sell_qty`, logged
implicitly via the `trades` row (price vs. the position's `avg_cost` at the time); it is not
separately stored."*

The `trades` schema (PLAN.md:398-405) is `id, user_id, ticker, side, quantity, price, executed_at`
— **there is no cost-basis column**. `positions.avg_cost` is overwritten on the next buy
(PLAN.md:396) and the position row is *deleted* when a sell zeroes it (PLAN.md:396). So the
"avg_cost at the time" of a sale is nowhere in the stored data, and realized P&L is therefore **not
recoverable at all** — it is neither explicitly stored nor implicitly inferable. The sentence
overstates what the schema provides.

Nothing in §2 or §10 actually displays realized P&L, so the cheapest fix is to delete the
"logged implicitly" clause and state plainly that realized P&L is not tracked. If it ever should
be, add an `avg_cost` (cost basis) column to `trades` and record it at execution time.

### H2. The plan never says the non-chat UI refreshes after AI-executed trades/watchlist changes

The headline feature is that the AI executes trades and edits the watchlist (§9 "Auto-Execution",
PLAN.md:676-691). But the `POST /api/chat` response carries only `message` + `actions`
(PLAN.md:598-609) — **no portfolio payload** — and the SSE stream carries **prices only**. §10's
chat panel says only that actions are "shown inline as confirmations" (PLAN.md:756).

Consequence: after the AI buys 10 HDFCBANK, the positions table, heatmap, cash balance, header
total, and (for watchlist changes) the watchlist *membership* all stay stale until something else
happens to refetch. For manual trades this is fine because the trade response embeds the
post-trade portfolio (PLAN.md:573-584), but the chat path has no equivalent.

Fix: state explicitly either (a) that the frontend refetches `GET /api/portfolio` and
`GET /api/watchlist` after any chat turn whose `actions` contain executed/failed entries, or
(b) that `POST /api/chat` returns the post-execution `portfolio` too (mirroring the trade
response). Add a matching E2E assertion (§12 already checks "trade execution appears inline", but
not that the portfolio panel updated).

---

## Medium

### M1. `.env` loading is specified as bare `load_dotenv()` while the app launches from `backend/`

PLAN.md:169 says the backend loads `.env` "via python-dotenv's `load_dotenv()` called at the top of
`app/main.py`". PLAN.md:788-789 launches with `cd backend && uv run uvicorn app.main:app`, so the
process CWD is `backend/`, while the file lives at the repo root (§4, PLAN.md:115).

`load_dotenv()` with no argument relies on python-dotenv's stack-walking/`find_dotenv` search,
which happens to walk up from `backend/app/` and find the root `.env` — but that is incidental
behaviour, not a guarantee. §11 makes a point of *never* trusting the working directory for
`db/finally.db` and `frontend/out/` (PLAN.md:797-801); the same discipline should apply here.
Specify `load_dotenv(REPO_ROOT / ".env")` (with the `REPO_ROOT` computation at PLAN.md:799). If
this is got wrong, `GROQ_API_KEY` silently doesn't load and every `/api/chat` call 502s.

### M2. The Tapetide degraded-mode fallback is mis-attributed to `main.py`, but it must live in already-built market code

PLAN.md:247-248 says the degraded-mode policy is "deferred until the backend app is wired
(`app/main.py`)", and STATUS.md also lists it as a `main.py` task. But the contract it describes
requires changes to the market subsystem that is currently marked complete:

- "The Tapetide source tracks consecutive connection/poll failures" (§6, PLAN.md:230) → needs a
  counter in `TapetideDataSource`.
- `_force_fallback` + `retry_after` latch "on the manager" (§6, PLAN.md:233-239) → needs
  `MarketDataManager._maybe_handover` (`manager.py:110`) to consult it.

Also worth tightening the trigger definition: `TapetideDataSource._run` (`tapetide_client.py:122-141`)
exits the whole poll task on any unhandled error (it logs "Tapetide poller crashed" and sets
`_client=None`), while per-batch poll errors are swallowed and `continue`d
(`tapetide_client.py:148-154`). So "N consecutive failures" must define whether it counts
per-batch poll failures, a dead task, or both — a crashed task currently produces *no further
failures*, so a per-poll counter alone would never reach N. State this explicitly and place the
counter so a crashed poller is also detected.

### M3. The 400-calls/day Tapetide budget is acknowledged but not mitigated, and `auto` will drain it unattended

PLAN.md:198 correctly computes that 400 calls/day ≈ 13 minutes of continuous 2s polling, then
relies on "the project owner ... short, deliberate demo sessions". But under the default
`MARKET_DATA_SOURCE=auto`, merely *leaving the app running during NSE hours with a key set* starts
polling immediately via the supervisor and drains the daily budget in ~13 minutes with no warning,
after which (once M2 is built) it flips to the simulator for the rest of the day. There is no
budget-aware throttle and the poll interval is only "a backend config constant" (PLAN.md:198) — it
is not surfaced in §5 or `.env.example`.

At minimum: name the constant/default in §5 and §6, or add a `TAPETIDE_POLL_INTERVAL` env var, and
consider logging a one-time warning when a Tapetide session starts. Leaving this purely to operator
discipline is the weakest operational assumption in the plan.

### M4. §13 contradicts itself by pointing into REVIEW.md

The §13 preamble (PLAN.md:872-875) says the log exists precisely so decisions are *not* left behind
a "pointer into `planning/REVIEW.md` — that file is regenerated by each review pass and its section
numbers shift, so a cross-reference into it goes stale." A few lines later, PLAN.md:889 does
exactly the forbidden thing: *"(Reaffirmed during review; see REVIEW.md finding 4.2.)"*. That
cross-reference is already stale/meaningless here (no `REVIEW.md` existed at review time). Drop
the parenthetical; the decision stands on its own.

### M5. No UI indicator of the active data source, despite the whole SEBI disclaimer hinging on it

The SEBI disclaimer is applied server-side only when `data_source == "tapetide"` (§9,
PLAN.md:704) because real prices carry an advisory obligation. Yet §10's header specifies only a
connection dot and a freshness badge (PLAN.md:757) — nothing tells the *user* whether the prices
on screen are real NSE quotes or simulated ones. `GET /api/health` already exposes `data_source`
(PLAN.md:630), so this is cheap: require the header to show a "LIVE (NSE)" vs "SIMULATED" badge
from `/api/health`. Without it, a reviewer judging SEBI compliance cannot tell which mode the app
is in, and the user cannot either.

### M6. Frontend polling of `/api/health` is required but never specified

The header's freshness indicator is "driven by `market_data_healthy` from `GET /api/health`"
(PLAN.md:757), but neither §8 nor §10 says how often the frontend polls it, or whether it is part
of the SSE stream. §8 only frames `/api/health` as a start-script readiness probe (PLAN.md:486).
Specify a cadence (e.g. every 5-10s) and that the freshness badge considers a health response older
than roughly the `market_data_healthy` window (~10s, PLAN.md:242) as itself stale.

### M7. E2E isolation vs. the single `.finally.pid` file is underspecified

§12 (PLAN.md:857) runs E2E on a dedicated `PORT` with a temp DB, "via the start/stop scripts". But
the scripts key off a single `.finally.pid` and the already-running check decides based on "a live
process listening on the port" (PLAN.md:818). Two problems: (1) if a developer's own instance is
already running, the harness's start script may treat the live-but-wrong-port PID ambiguously
(PLAN.md:818 only special-cases "process gone"); (2) the harness would overwrite the developer's
`.finally.pid` on start and delete it on teardown, orphaning the developer's instance. Either give
the E2E harness its own PID file / launch path, or state that E2E requires no other instance
running and the scripts take an explicit PID-file override.

### M8. The plan carries volatile implementation constants that will drift from the code

The plan hard-codes several values that live (or will live) in code: the GBM `dt ≈ 8.48e-8` and its
derivation (§13, PLAN.md:907-909), the 1e-9 quantity epsilon (§7, PLAN.md:396), `N=3` /
5-minute cooldown / 10s health window (§6, PLAN.md:230-243), and the exact seed prices (§6,
PLAN.md:189). `dt` and the seed table already exist in `simulator.py:46-47` and
`seed_prices.py:4-15`; duplicating them in the plan guarantees drift. Consider a single
"§6.1 Constants" table, or phrase these as "see `<file>`" rather than restating the number.

---

## Low

### L1. `GET /api/portfolio` example is internally inconsistent

PLAN.md:528-545: one shown position (HDFCBANK, market_value 7500) but `positions_value` is 15250
and the implied cash (985000) is not `1,000,000 − 7250`. The header comment states
`positions_value = sum(market_value)` (PLAN.md:550), which the example violates. Agents copy
examples verbatim — make the numbers add up, or say the example elides other positions.

### L2. `direction` in the watchlist payload is ambiguous next to the day-change fields

`GET /api/watchlist` returns `day_change`, `day_change_percent`, and `direction` together
(PLAN.md:563-566). `direction` is *tick-over-tick* (defined in `models.py:51-58`) while its
neighbours are day-based, inviting a frontend that colours the daily-change cell by tick direction.
Rename to `tick_direction`, or add a one-line note in the JSON block.

### L3. Watchlist response field list contradicts "straight from `PriceUpdate.to_dict()`"

PLAN.md:570-571 says the price fields "come straight from the cache (`PriceUpdate.to_dict()`)",
but the documented shape omits `change`/`change_percent` and `previous_price`, which `to_dict()`
does include (`models.py:60-73`). Either show the full object or say "a subset of `to_dict()`".

### L4. `DELETE /api/watchlist/{ticker}` returns `removed: true` when nothing was removed

PLAN.md:624: the idempotent-success rule (PLAN.md:505-507) means a delete of an absent ticker
returns `{"ticker": "...", "removed": true}`. That is misleading. Return the actual boolean
(`removed: false` when absent) or drop the field.

### L5. The "one point per second" chart rule is applied to the P&L chart, which doesn't need it

PLAN.md:763 lumps "sparkline, main chart, and P&L chart" under the aggregation rule. But the P&L
chart is sourced from `portfolio_snapshots` at a 30s cadence (PLAN.md:752), already strictly
ascending and unique — it is not on the SSE buffer at all. Scope the rule to the SSE-fed charts.

### L6. `active_source_name` can return `"none"`, which the plan does not acknowledge

`manager.py:94-97` returns `"none"` before the source is started. §9 step 1 (PLAN.md:647) and the
health example (PLAN.md:630) assume only `"tapetide"`/`"simulator"`. State the pre-start behaviour
(or guarantee the field is never surfaced before start), especially since the SEBI rule branches on
this exact value.

### L7. Tapetide "polls the full watchlist" should be "the full tracked set"

PLAN.md:197 says the poll covers the watchlist, but tracked tickers are watchlist ∪ positions
(§6, PLAN.md:250-267). Held-but-unwatched tickers are polled too. Say "tracked set" for accuracy.

### L8. `last 20` chat rows can begin mid-conversation

Both the LLM context window and `GET /api/chat/history` use the last 20 rows (PLAN.md:465, 648).
When every turn writes a user + assistant row, the window can open on an assistant message with no
preceding user turn. Harmless for chat display, but worth a note for the LLM prompt construction.

### L9. Static-export frontend caveats are unstated

§11 specifies `output: 'export'` (PLAN.md:783) but not the follow-on requirements: static export
disables Next.js image optimisation (needs `images.unoptimized` if `next/image` is used) and API
routes/ISR. Given §4 leaves frontend internals to the agent, one line in §11 would prevent a build
surprise.

### L10. Auto-execution has no prompt-injection note

Trades execute with no confirmation (PLAN.md:676-683). Portfolio/watchlist text is fed into the
LLM (PLAN.md:647), so a crafted ticker or chat message could in principle drive an unintended
(`failed` or executed) trade. Stakes are zero (simulated money), so this is not a blocker — but a
one-line acknowledgement in §9 that there is no confirmation gate *by design* would pre-empt the
obvious reviewer question.

### L11. Frontend unit test for the flash animation is optimistic

§12 (PLAN.md:846) lists "Price flash animation triggers correctly on price changes" as a Vitest/RTL
test. CSS transitions aren't observable in jsdom; the test can only assert class toggling / that
the trigger fires on `direction != "flat"`. Reword to match what is actually testable.

### L12. `.env.example` comments out four of the seven documented variables

§5's comment says `.env.example` "lists every supported var" (PLAN.md:116), but
`MARKET_DATA_SOURCE`, `DATABASE_PATH`, `FRONTEND_DIR`, and `PORT` are present only as commented
lines (`.env.example:11-22`). They are listed, so this is cosmetic — but "lists every supported
var" reads as if they are active.

---

## Verified accurate against the built code

These are the plan's factual claims about the existing market subsystem; all check out:

- `httpx2` / `mcp>=2.3.0` are real dependencies and used as described (`pyproject.toml:11-12`,
  `tapetide_client.py:17-19,129`). The claim that the MCP streamable-HTTP client is built on
  `httpx2` matches the code.
- The 20-symbol `get_batch_quotes` batch limit and the requested-vs-resolved symbol cache keying
  (`tapetide_client.py:27,157-160`).
- `previous_close` carry-forward-on-unsupplied semantics and cold-start default-to-first-price
  (`cache.py:39-51`).
- SSE version-counter change detection at ~500ms and full-map frames (`stream.py:51-85`).
- `MarketDataError` on transport failure vs. `False` for "not found" (`interface.py:8-14,69-81`;
  `tapetide_client.py:104-118`).
- The `MARKET_DATA_SOURCE` override values and `tapetide`-without-key fast failure
  (`factory.py:31-41`).
- Seed prices (HDFCBANK 728.85, INFY 1161.20), the `NSE_SYMBOL_UNIVERSE` (includes `WIPRO`),
  correlation groups, and the `dt ≈ 8.48e-8` figure (`seed_prices.py`, `simulator.py:44-47`).
- The groq-skill model string `groq/openai/gpt-oss-120b` and dependency list
  (`.claude/skills/groq-skill/SKILL.md:17-30`).

One item the plan *omits* but the code implements: the "cache key is the requested ticker, not
Tapetide's resolved symbol (corporate actions)" decision
(`MARKET_DATA_SUMMARY.md:52`, `tapetide_client.py:157-160`). It is a real contract detail and is
not in §6; consider adding it.

---

## Open questions to confirm externally

1. **Groq model availability.** `groq/openai/gpt-oss-120b` matches the groq-skill, but confirm the
   model is still served (and its id unchanged) at implementation time; a model rename would make
   every chat call 502.
2. **Tapetide `prev_close` presence.** If a real quote omits `prev_close`, day-change silently
   falls back to carry-forward/first-price (PLAN.md:283-309 assumes it is always returned). Confirm
   against a live response.
3. **`request.is_disconnected()` reliability** for SSE teardown (`stream.py:71`) — a known rough
   edge in some ASGI servers; worth a smoke test rather than an assumption.

---

## Disposition (what was processed)

Verdict and action taken per finding. All changes landed in `PLAN.md`; no code was changed (the
findings are about the spec, and the market subsystem's facts all check out).

| # | Verdict | Change made |
|---|---------|-------------|
| H1 | Valid | Rewrote the `positions` note: realized P&L is **not tracked** (no cost basis stored); how to add it later. |
| H2 | Valid | §9/§10: frontend refetches `GET /api/portfolio` + `/api/watchlist` after any chat turn with non-empty `actions`; added matching E2E assertion (§12). |
| M1 | Valid | §5: `load_dotenv(REPO_ROOT / ".env")` with rationale, not bare `load_dotenv()`. |
| M2 | Valid | §6: degraded-mode re-attributed across `TapetideDataSource` + manager (not just `main.py`); "N failures" now counts a crashed poll task too. |
| M3 | Valid (partial) | §6: named the interval constant `TAPETIDE_POLL_SECONDS` (default 2) + a one-time startup warning. No budget throttle built — left to owner by design. |
| M4 | Valid | §13: dropped the stale "see REVIEW.md finding 4.2" cross-reference. |
| M5 | Valid | §10 header: added a "LIVE (NSE)" vs "SIMULATED" data-source badge from `/api/health`. |
| M6 | Valid | §10: specified ~5s `/api/health` poll cadence and stale-if-older-than-~10s rule. |
| M7 | Valid | §11/§12: PID file overridable via `FINALLY_PID_FILE`; E2E harness uses its own. |
| M8 | Valid (partial) | Replaced the duplicated `dt` figure with "see `simulator.py`" (§13); seed prices already point to the source file. Other constants left inline as contract values. |
| L1 | Valid | §8: fixed the `GET /api/portfolio` example so the numbers add up. |
| L2 | Valid | §8: noted `direction` is tick-over-tick; colour the daily cell by `day_change`. |
| L3 | Valid | §8: watchlist fields described as a **subset** of `to_dict()`. |
| L4 | Valid | §8: `removed` now reflects the actual delete (false if absent). |
| L5 | Valid | §10: one-point-per-second rule scoped to the SSE-fed charts; P&L chart excluded. |
| L6 | Valid | §9: noted `active_source_name` can be `"none"` pre-start but is never surfaced (manager starts before serving). |
| L7 | Valid | §6: "full watchlist" → "full tracked set (watchlist ∪ positions)". |
| L8 | Valid | §9: noted the 20-row window may open on an assistant row; prompt build must tolerate it. |
| L9 | Valid | §11: static-export caveats (`images.unoptimized`, no API routes/ISR). |
| L10 | Valid | §9: one-line "no confirmation gate by design" / prompt-injection acknowledgement. |
| L11 | Valid | §12: reworded the flash test to class-toggle assertion (jsdom can't observe CSS transitions). |
| L12 | Valid (cosmetic) | §4: clarified `.env.example` lists optional vars as commented-out lines. |
| Omitted detail | Valid | §6: added the "cache keyed by requested ticker, not resolved symbol" contract note. |
| OQ1 (Groq model) | Valid, no spec change | Owner to confirm `groq/openai/gpt-oss-120b` is still served at build time. |
| OQ2 (`prev_close`) | Valid, already handled | If absent, §6 carry-forward/first-price fallback applies — no defect; confirm against a live response. |
| OQ3 (`is_disconnected`) | Valid, no spec change | Smoke-test at implementation; not a plan change. |
| Verified-accurate list | Accepted | No action — confirms the plan matches the built market code. |

Also compressed PLAN.md: trimmed redundant prose in §5 (supervisor), §6 (SEBI text kept as single
source of truth, degraded-mode intro), §8 (chat-502 bullet), §9 (mock extraction), and §13 (`dt`
derivation) without dropping any contract detail.
