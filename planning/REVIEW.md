# FinAlly — Review of `planning/PLAN.md`

**Review date:** 2026-10-19
**Scope:** `planning/PLAN.md` (879 lines), read end to end with a fresh eye.
**Method:** Read the plan standalone, then cross-checked the market-data contract against the
already-built subsystem in `backend/app/market/` to distinguish plan defects from implementation
drift. This review intentionally does not reference any prior review.

---

## Verdict

The plan is unusually complete and internally self-aware. The architecture choices are sound for
the stated goal (single-process demo, no Docker), the endpoint/response contracts are concrete, and
the "Design Decisions Log" (§13) captures the tradeoffs that usually go undocumented. It is
buildable as written.

The concerns below are not showstoppers. They cluster into three buckets: (a) a few genuine
internal inconsistencies where two sections state different rules, (b) underspecified contracts an
implementing agent would have to guess at, and (c) places where the delivered market-data code
already diverges from the plan's own stated contract. The most important ones are
[1.1](#11-validate_ticker-cannot-express-the-required-transport-vs-not-found-distinction),
[1.2](#12-sebi-disclaimer-scope-§6-advisory-vs-§9-unconditional),
[1.3](#13-watchlist-seed-order-is-unachievable-with-the-stated-schema),
[1.4](#14-degraded-mode-fallback-mechanism-is-underspecified-and-would-flap). Everything else is
lower-stakes tidy-up.

---

## 1. Internal inconsistencies and contradictions

### 1.1 `validate_ticker` cannot express the required "transport vs not-found" distinction
- The interface is `validate_ticker` (a bool-returning method) — §6 line 172, matching
  `backend/app/market/interface.py:60`.
- But §6 line 259 says a transport failure "must be distinguished from a genuine `found: false` …
  must not surface as 'No stock with ticker XYZ exists'", and §6 line 231 repeats the requirement.

A boolean cannot carry three states (valid / not-found / transport-failure). Either the method must
raise on transport failure, return a tri-state, or the validation path must be restructured so the
error distinction is made by the caller. As written, an implementer cannot satisfy §6 with the §6
interface. **Pick one and state it.** My preference: `validate_ticker` raises a dedicated
`TickerValidationError`/transport exception on connection failure and returns bool only for the
"we actually reached the source" case; the API layer maps the exception to a 502/503 rather than a
400.

### 1.2 SEBI disclaimer scope (§6 advisory vs §9 unconditional)
- §6 line 194 scopes the disclaimer to responses that contain "commentary, analysis, buy/hold/sell
  suggestions, or portfolio advice derived from Tapetide data."
- §9 line 677 says it is appended whenever `data_source == "tapetide"` — unconditionally, for every
  chat turn.

These conflict: under Tapetide, "what is my cash balance?" would get the disclaimer per §9 but not
per §6. The unconditional server-side rule is the only one that is actually implementable (the
backend cannot reliably classify "advisory"), so §9 is the sensible rule — but §6's narrower
phrasing should be corrected to defer to §9, or the mismatch will confuse whoever implements the
check.

### 1.3 Watchlist seed order is unachievable with the stated schema
§7 line 366 requires the watchlist to be "Returned ordered by `added_at ASC` (tie-broken by `id`) …
so the default ten appear in their seed order." The `id` is a **UUID** (line 360), and the ten seed
rows are inserted together. If they share an `added_at` value, the `id` tie-break sorts by random
UUID — the exact "arbitrary order" the sentence is trying to avoid.

To actually guarantee seed order you need one of: staggered `added_at` values on insert, an integer
`sort_order`/autoincrement column, or an explicit seed-order column. As specified, the stated goal
and the stated tie-break are contradictory.

### 1.4 Degraded-mode fallback mechanism is underspecified and would flap
§6 (lines 216–235) says the manager "hands over to the simulator" after N consecutive Tapetide
failures, and that "if Tapetide recovers while still in trading hours it will be picked up again on
a later check." But:

- The manager's only swap signal today is `create_market_data_source()` (a pure function of key +
  clock). While trading hours hold and the key is set, that function keeps returning Tapetide, so
  the 60 s supervisor would swap *back* to the still-broken Tapetide on the very next check — an
  endless sim↔Tapetide flap every minute.
- Nothing in the plan defines where the "we fell back" latch lives, nor a cooldown/backoff before
  retrying Tapetide.

This needs a concrete contract: e.g. the manager holds a `_force_fallback` flag plus a
`retry_after` timestamp, suppresses the desired-source swap until the cooldown elapses, and
periodically re-attempts Tapetide. Right now the section is a behavior description with no
mechanism, and the obvious naive implementation is wrong.

### 1.5 Who owns `PORT`?
- §5 line 151/162 presents `PORT` as a backend setting ("overrides the bind port").
- §11 line 762 launches `uvicorn … --port 8000` on the command line; `main.py` cannot override a
  port uvicorn has already bound.

So `PORT` is only meaningful if the **start scripts** plumb it into `uvicorn --port $PORT`. The
plan should say that explicitly, and stop implying the app reads `PORT` at runtime. (`DATABASE_PATH`
and `FRONTEND_DIR` *are* read by `main.py`; `PORT` is not in the same category.)

### 1.6 "Only when the cache actually changes" overstates the SSE contract
§6 line 296–302 says the stream pushes "only when the cache actually changes." In the built code
the cache version increments on **every** `update()` (`cache.py:54`), and the simulator writes every
500 ms regardless of whether the 2-dp price moved (`simulator.py:286`). So identical frames are
re-sent at 500 ms for tickers that didn't move. This is fine behaviorally, but the wording should be
"on every write" rather than "when the cache actually changes," or the frontend author may assume
frames are deduplicated (they are not).

### 1.7 Start-script key handling vs the E2E path
§11 line 788 says the start script warns — or fails — when `GROQ_API_KEY` is not filled in. §12
line 830 says the E2E harness starts the app with `LLM_MOCK=true`, where the key is irrelevant and
often absent in CI. If the script treats an empty/placeholder key as fatal, the documented E2E
launch cannot start. Clarify: `LLM_MOCK=true` must bypass the key check entirely, and the script
must tolerate the literal placeholder `your-groq-api-key-here` as "not filled in" (or never fail,
only warn).

---

## 2. Gaps / underspecified contracts

1. **`current_price` for an un-priced position.** §8 line 543 documents null price fields for a
   just-added watchlist ticker, but the `/api/portfolio` shape (lines 511–522) assumes every
   position has a `current_price` and non-null `market_value`/`unrealized_pnl`. A held ticker whose
   Tapetide first poll hasn't landed yet has no cached price (the startup-snapshot fallback at §7
   line 331 uses `avg_cost`, but the *endpoint* response isn't specified). Define the null/fallback
   behavior for the endpoint, not just the snapshot.
2. **`market_data_healthy` window.** §6 line 230 / §8 line 603 define it as "written within a recent
   window" without a number. Given Tapetide's 2 s cadence, the window must be comfortably larger
   (e.g. 10 s). State it.
3. **Persisted assistant content and the disclaimer.** §9 line 626 stores "the message"; §8 line 588
   shows the assistant `content`. It is unstated whether the stored content is the pre- or
   post-disclaimer text. It should be the final (post-append) text so a reload via
   `/api/chat/history` shows exactly what the user saw.
4. **`POST /api/watchlist` — duplicate check vs validation order.** §8 line 480 makes re-adding
   idempotent-200; §6 line 259 notes each Tapetide validation spends one call of the 400/day budget.
   Does re-adding an already-watched ticker re-validate (spending a call) or short-circuit on the
   duplicate lookup first? Specify duplicate-check-first.
5. **Simulator→Tapetide `previous_close` transition.** §6 lines 284–291 cover the Tapetide→simulator
   direction (carry-forward) thoroughly, but not what happens when the market opens mid-session and
   a simulator-sourced `previous_close` is replaced by the real exchange close. The day-change %
   jumps at that instant; that's probably intended, but it's unstated.
6. **Flash trigger definition.** §10 line 737 says flash "on receiving a new price," but §13 lines
   876–878 expect flashes to be *sparse* (rounded prices often unchanged). If "new price" means
   "every SSE frame," low-priced tickers flash continuously and §13's stated behavior never appears.
   Define the trigger as `direction != "flat"` (i.e. `change != 0`).
7. **LLM `quantity` type.** §9 line 637 shows `"quantity": 10` (integer) in the structured schema,
   but fractional shares are supported (§7). The schema example should show a number and say
   fractional is allowed, or an agent may type it as `int`.
8. **`.env.example` doesn't list the optional vars.** §5 documents `MARKET_DATA_SOURCE`,
   `DATABASE_PATH`, `FRONTEND_DIR`, `PORT`; `.env.example` (the only file a fresh clone sees, per §4
   line 114) omits all four. Add them commented-out. Same drift exists in the README env table.
9. **Float-zero and float-compare edges.** Positions are `REAL` and sell-to-zero deletes the row
   (§7 line 376) — a leftover `1e-15` won't compare `== 0`. Likewise "insufficient shares" is a
   float comparison. State an epsilon policy, or note that rounding quantities to a sane precision
   is acceptable.
10. **Frontend membership source.** §8 line 428 / §6 line 237 mean the SSE payload (entire cache)
    can include held-but-unwatched tickers that must *not* appear in the watchlist panel. The plan
    implies the panel keys off `GET /api/watchlist`, but never says it outright. One sentence
    ("the watchlist panel's membership comes from `/api/watchlist`; SSE supplies prices only") would
    prevent a panel that renders every streamed ticker.

---

## 3. Where delivered market code already diverges from the plan's contract

These are things the plan *correctly* requires but the shipped `backend/app/market/` does not do.
Flagging because the plan is being reviewed as the contract, and STATUS.md currently marks the
subsystem "complete, tested, reviewed."

1. **Naive Tapetide timestamps are interpreted in the server's local zone, not IST.** §7 line
   346–348 requires a naive upstream timestamp to be assumed IST. `tapetide_client.py:138` does
   `datetime.fromisoformat(quote["updated_at"]).timestamp()`, which interprets a naive datetime in
   *local* time. On a non-IST machine this shifts display times silently — exactly the failure the
   plan calls out.
2. **Tapetide validation is not serialized against the poller.** §6 line 259 requires Tapetide tool
   calls to be serialized (lock/single worker) because validation shares the MCP `Client` with the
   background poll loop. `TapetideDataSource.validate_ticker` calls `_call_batch_quotes` directly
   with no lock, concurrent with `_poll_once`. STATUS §"To build" acknowledges this is uncoded, but
   it lives in the *delivered* `TapetideDataSource`, not in the unbuilt `main.py` — so the
   "complete" label is premature for that specific requirement.
3. **Degraded-mode fallback is absent** (see 1.4). STATUS correctly scopes this to `main.py`, but
   note that the mechanism (1.4) doesn't exist anywhere yet.

Recommendation: either fix 1 and 2 in the market module, or move them to STATUS "To build" so the
"complete" claim is honest.

---

## 4. Opportunities to simplify

1. **Collapse the two-baseline prose.** §6 "Daily Change % vs. Tick-over-Tick" states the rule, then
   re-states it with a handover exception ("This continuity is intended; it refines the 'session
   start price' wording above"). State it once: *`previous_close` = the exchange close if one has
   ever been observed for the ticker, else the ticker's first simulated price; it is carried
   forward across a handover.* One paragraph instead of two plus a correction.
2. **Reconsider the multi-user scaffolding / two `db/` directories.** §13 defends `user_id` as
   deliberate, and the two-`db` split (`backend/db/` vs top-level `db/`) is explained — but the
   latter is a footgun the plan itself guards against in §11 line 776. A single `backend/app/db/`
   for schema+seed removes the ambiguity for near-zero cost. (The `user_id` call is the author's;
   just noting it's the largest "complexity not needed for the demo" item.)
3. **Scale the handover machinery to actual usage.** §6 line 194 says most demos never touch
   Tapetide. Live handover + degraded mode + serialized validation is a lot of surface for a path
   that rarely runs. If Tapetide is truly a near-unused path, consider a smaller contract (e.g.
   decide source once at startup, or drop degraded mode and let the health endpoint expose
   staleness). If it's kept, fix 1.4 properly.
4. **Consolidate the scattered scope decisions.** "No synthetic 500 ms re-emission" (§6 line 300,
   §13 line 861), "main chart has no history" (§10 line 723, §13 line 864), and the heatmap
   denominator (§10 line 724, §13 line 871) are each stated twice. §13 is the right home; the inline
   duplicate sentences can shrink to a pointer.
5. **The `PORT`/`DATABASE_PATH`/`FRONTEND_DIR` story** would be simpler framed as "the start
   scripts own binding and pass everything to `uvicorn`/`main.py`," rather than three vars described
   in two different sections as if the app reads them all uniformly (see 1.5).

---

## 5. Questions for the author

1. For 1.1 — should `validate_ticker` raise on transport failure, or should the caller own the
   distinction?
2. For 1.4 — where does the "fell back to simulator" latch live, and what is the retry cooldown?
3. For 1.3 — are the ten seed rows inserted with distinct `added_at` values, or is an explicit
   ordering column expected?
4. For §8 portfolio — what should `current_price` / `market_value` / `unrealized_pnl` be for a held
   ticker with no cached price yet?
5. For §9 — is the assistant's stored `chat_messages.content` the post-disclaimer text?
6. For §12 — does the E2E harness run the platform start scripts, or its own fixture? This changes
   whether 1.7 matters in practice.
7. For §6 — is the simulator→Tapetide `previous_close` jump at market open intended to be visible
   in the day-change %?

---

## 6. Minor / nits

- §11 line 756: "per Next.js's `output: 'export'` default" — `out/` is the default *directory* when
  `output: 'export'` is configured; it is not Next.js's default output mode. Reword.
- §4 tree omits `.finally.pid` (introduced in §11 line 799) and `.env.example`.
- §8 line 519 uses `change_percent` for a position's return vs. cost basis, while §6/§8 use
  `day_change_percent`/`change_percent` for tick-over-tick in the watchlist. Two meanings for
  "change_percent" invite frontend bugs; consider `return_percent` for the position field.
- §9 line 696: "scans *all* all-caps alphanumeric tokens" reads awkwardly ("all all-caps").
- §12 line 839: "SSE resilience: disconnect and verify reconnection" — driving a browser
  `EventSource` disconnect from Playwright is nontrivial; consider testing reconnect at the unit
  level and keeping the E2E check to "prices keep updating."
- §2 "What the user can do" and §10 disagree slightly on the panel list (Recent trades panel is in
  §10 only). Harmless, but §2 is the user-facing summary and would benefit from matching §10.

---

## 7. Suggested disposition

**Fix before implementation (contract-level):** 1.1, 1.2, 1.3, 1.4, 1.5.
**Fix or explicitly defer, with a note in STATUS:** 1.6, 1.7, and §3 items 1–2.
**Tidy-up (no behavior change):** §2, §4, §5, §6 of this review.

None of these block starting `backend/app/main.py`, but 1.1–1.4 are exactly the kind of ambiguity
that produces a plausible-looking implementation with a subtle wrong behavior, so they are worth
settling in the plan first.

---

## Rectification Pass — Verdicts & Actions

Implementing-agent pass (2026-10-19). Every observation was re-checked against the code and plan.
Standing scope from the owner: **fix clear bugs in the delivered market code now, spec the rest in
PLAN.md.** Code changes were validated: `uv run pytest` → **107 passed**, ruff clean.

| # | Sev | Valid? | Action |
|---|-----|--------|--------|
| 1.1 | BLK | Yes | **Code:** added `MarketDataError`; `validate_ticker` now returns bool only when Tapetide was reached and raises on transport failure. PLAN §6/§8: API maps it to `503`, never `400`. |
| 1.2 | BLK | Yes | PLAN §6: disclaimer rule reworded to defer to §9's unconditional "every assistant turn while `data_source=="tapetide"`" — removes the §6-advisory vs §9-unconditional conflict. |
| 1.3 | BLK | Yes | PLAN §7: seed rows inserted with distinct, increasing `added_at`; the UUID `id` tie-break is explicitly not relied on for order. |
| 1.4 | BLK | Yes | PLAN §6: added the `_force_fallback` + `retry_after` cooldown latch (default 5 min) that suppresses the swap-back, fixing the every-minute sim↔Tapetide flap. |
| 1.5 | HIGH | Yes | PLAN §5/§11: `PORT` is owned by the start scripts (`uvicorn --port`), not read by `main.py`; `DATABASE_PATH`/`FRONTEND_DIR` are read by `main.py`. |
| 1.6 | HIGH | Yes | PLAN §6 SSE: reworded to "pushes on every cache write (version bump); frames are not de-duplicated." |
| 1.7 | HIGH | Yes | PLAN §11: `LLM_MOCK=true` skips the key check entirely; placeholder treated as "not filled"; warn, don't fail. |
| 2.1 | gap | Yes | PLAN §8: un-priced held position → `current_price: null`, fall back to cost basis (`market_value=qty*avg_cost`, pnl/return 0). |
| 2.2 | gap | Yes | PLAN §6/§8: `market_data_healthy` window set to ~10s (> 2s Tapetide cadence). |
| 2.3 | gap | Yes | PLAN §9: stored `chat_messages.content` is the final, post-disclaimer text. |
| 2.4 | gap | Yes | PLAN §8: duplicate watchlist add short-circuits **before** validation (spends no Tapetide call). |
| 2.5 | gap | Yes | PLAN §6: documented the intended day-change % jump when sim→Tapetide replaces the baseline at market open. |
| 2.6 | gap | Yes | PLAN §10: flash trigger defined as `direction != "flat"`, not per-frame. |
| 2.7 | gap | Yes | PLAN §9: `quantity` is a number, fractional allowed; the `10` is illustrative. |
| 2.8 | gap | Yes | `.env.example` + README env table now list `MARKET_DATA_SOURCE`, `DATABASE_PATH`, `FRONTEND_DIR`, `PORT`. |
| 2.9 | gap | Yes | PLAN §7: epsilon policy (`|qty| < 1e-9` ≈ 0) for sell-to-zero and insufficient-shares. |
| 2.10 | gap | Yes | PLAN §10: watchlist panel membership comes from `GET /api/watchlist`; SSE supplies prices only. |
| 3.1 | code | Yes | **Code:** naive Tapetide `updated_at` now parsed as IST (`_parse_timestamp`), with a test. |
| 3.2 | code | Yes | **Code:** Tapetide MCP calls serialized through an `asyncio.Lock` shared by poll + validate. |
| 3.3 | code | Yes | Degraded-mode mechanism now specified (1.4); implementation remains `main.py` scope in STATUS. |
| 4.1 | simplify | Yes | PLAN §6: collapsed the two-baseline prose + correction into one statement. |
| 4.2 | simplify | Author | Two-`db` split / `user_id` scaffolding kept (deliberate, §13). Path footgun is already guarded (§11). Flagged for your call below. |
| 4.3 | simplify | Author | Live handover kept (deliberate, §13); its failure mode (1.4) is now fixed rather than the feature dropped. |
| 4.4 | simplify | Ack | Duplicated scope sentences (§10/§13) left in place — the inline context helps the frontend agent; §13 remains the canonical home. No change. |
| 4.5 | simplify | Yes | Covered by 1.5 (PORT/paths framing). |
| 6a | nit | Yes | PLAN §11: corrected "Next.js `output:'export'` default" wording. |
| 6b | nit | Yes | PLAN §4 tree now lists `.env.example` and `.finally.pid`. |
| 6c | nit | Yes | PLAN §8: position field renamed `change_percent` → `return_percent` to disambiguate. |
| 6d | nit | Yes | PLAN §9: "all all-caps" reworded to "every all-caps token." |
| 6e | nit | Yes | PLAN §12: SSE-resilience E2E softened to unit-level reconnect + "prices keep updating." |
| 6f | nit | Yes | PLAN §2: "Review recent trades" added to the user-capability list to match §10. |

**Questions for the author (§5):** 1→1.1 (raises), 2→1.4 (latch on manager, 5-min cooldown),
3→1.3 (distinct `added_at`), 4→2.1 (cost-basis fallback), 5→2.3 (post-disclaimer), 6→§12 (E2E
uses `LLM_MOCK`, so 1.7's check is skipped), 7→2.5 (jump is intended). All answered by the edits
above.

**Finding 4.2 — resolved (owner, 2026-10-19): keep as-is.** The `backend/db/` ↔ top-level `db/`
split and the `user_id` scaffolding both stay. Recorded as a standing decision in PLAN.md §13 so
it is not re-raised by a future review.
