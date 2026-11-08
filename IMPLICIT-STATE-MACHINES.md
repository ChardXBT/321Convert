# Implicit State Machines — 321Convert audit

Places where mutually-exclusive state is encoded without a single declared
state model. Report only — no refactors proposed as code.

## Frontend per-file conversion lifecycle

**States** — `ready`, `unsupported`, `uploading`, `converting`, `done`,
`error` (6 states per file row), plus a batch-level "a conversion is in
flight" flag.

**Encoded as** — `row.status` raw strings in `static/app.js`, coupled with
companion fields that are only meaningful in some states (`row.progress` for
`uploading`, `row.resultUrl`/`row.resultName` for `done`, `row.error` for
`error`, `row.family === null` for `unsupported`) and the global
`state.running` boolean. The same status is mirrored into
`li.dataset.status` (app.js:212, 223) and is a cross-file contract: CSS keys
off it (`static/styles.css:452-459`) and the e2e test asserts on it
(`tests/e2e/test_ui.py:164`). No enum, no transition function — each write
site sets `.status` plus whichever companion fields it remembers to update.

**Invalid combos** —
- `status === "done"` with `resultUrl === null` → `link.href = null`
  produces a dead "Download" (app.js:187) and `downloadAll` clicks it anyway
  (app.js:542-548).
- `status === "error"` with `error === ""` → a Retry button with no
  explanation.
- `family === null` with `status !== "unsupported"` → the row is counted
  convertible (app.js:90) but `optionsForRow` dereferences `row.family.id`
  (app.js:87) and throws; today unreachable only because `addFiles` always
  sets the pair together (app.js:344-352).
- `state.running === true` with no row actually in flight (see below).

**Transitions** —
- set `ready`: app.js:264 (target change also revokes `resultUrl`, clears
  `error`/`notes`), app.js:331 (intake)
- set `unsupported`: app.js:345, 349 (pairs `family = null`)
- set `uploading`: app.js:385
- set `converting`: app.js:407, 411
- set `done`: app.js:426 (also mints `resultUrl` at 419)
- set `error`: app.js:440, 449, 455
- read/decide: app.js:90, 92-93, 112-116, 126-139, 171-208, 542, and the
  `beforeunload` guard at 551-556 via `state.running`

**Risk** — *High.* One unhandled path wedges the whole converter: if
`convertRow`'s promise **rejects** — any synchronous throw in its executor
(`renderRow`, `FormData`, `xhr.send`), or the `family === null` combo above —
the `.then` callbacks that reset `state.running` never run (app.js:200-205
for retry, app.js:483-493 for `convertAll`). The UI then sits permanently in
"Converting…", Convert stays disabled (app.js:126), retry buttons stay
disabled (app.js:138, 195), rows stuck in `uploading`/`converting` can never
be retried (they are excluded from `pendingRows`, app.js:93), and
`beforeunload` nags on every navigation (app.js:552). Adding a seventh
status also means remembering six scattered read sites plus the CSS/DOM
contract.

## Worker result protocol

**States** — `success`, `user-facing error`, `crash` (3 outcomes the parent
maps to `ConversionResult` / `ConversionError` / `ConversionCrashed`).

**Encoded as** — a `{"ok": bool}` boolean plus which of the nullable fields
`result` / `user_message` / `error_type` are populated, sent over the result
pipe in `core/runner.py`. The same `user_message` slot carries "safe to show
the user" vs `None` meaning "crash", and `error_type` is only honoured when
`user_message` is falsy.

**Invalid combos** —
- `ok: True` missing `"result"` → `KeyError` at runner.py:257 propagates as
  an unhandled exception → generic 422 via app.py:305 instead of
  `ConversionCrashed`.
- `ok: False` with `user_message` set → `error_type` is silently dropped;
  the child *does* send both for `ConversionError` (runner.py:110-116), so
  the exception type is never seen by the parent's crash logging.
- `ok: False` with both fields `None` → `ConversionCrashed("UnknownError")`.

**Transitions** —
- write success: runner.py:107
- write user-error: runner.py:109-118 (`ConversionError`)
- write crash/memory-error: runner.py:119-133 (`BaseException`; only a true
  `MemoryError` gets a `user_message`)
- read/decode: runner.py:254-265
- timeouts/missing messages synthesise the same states: runner.py:248-251
  (`ConversionTimeout`, `EOFError` → `ConversionCrashed`), runner.py:254-255
  (`BadMessage`)

**Risk** — *Medium.* A child sending an unexpected shape is a latent
`KeyError`/misclassification rather than a clean crash, and anyone adding a
new outcome must reverse-engineer the 3-field convention (bool + two
nullable strings) with no schema. Also note the asymmetry: a
`user_message`-bearing crash is reported to the user but its `error_type` is
never logged server-side.

## Idle worker pool lifecycle

**States** — `no idle worker` / `registered and alive` / `registered but
dead (zombie)` — plus the per-job phases `sent` / `received` encoded only in
pipe open/close.

**Encoded as** — `_IDLE is None` vs `worker.proc.is_alive()` in
`core/runner.py` (declared runner.py:145); whether a worker was sent a job
is tracked by closing `job_conn` (runner.py:237), not by any flag.

**Invalid combos** —
- `_IDLE` holding a dead process — representable, filtered by `is_alive()`
  checks at runner.py:186 and 200.
- a worker whose result pipe is dead while `proc.is_alive()` — not filtered
  anywhere: `job_conn.send` can succeed into a buffer, then
  `result_conn.poll` burns the whole `CONVERSION_TIMEOUT` (runner.py:245)
  and the request fails as `ConversionTimeout` even though a fresh worker
  would have succeeded. Only *send* failure triggers respawn+retry
  (runner.py:228-236); poll timeout does not.

**Transitions** —
- create: `_start_worker` runner.py:157-176
- claim/discard corpse: `_take_idle` runner.py:179-190
- respawn (spawn platforms only, on a daemon thread): `_replenish_idle`
  runner.py:193-208, kicked off at runner.py:241-242 and `warm_up`
  runner.py:53-71
- teardown: `_stop_idle` runner.py:211-221 and the `finally` at
  runner.py:266-270

**Risk** — *Medium-low.* The zombie states are handled, but the
alive-vs-usable distinction isn't: a wedged child costs the full timeout and
still errors the request instead of falling back to a fresh worker. The
"at most one idle worker" invariant lives only in `_IDLE_LOCK` plus the
convention that `_replenish_idle` is the sole writer of a live worker.

## DOCX table merged-cell roles

**States** — `normal cell` / `colspan head` / `rowspan head` /
`covered phantom` (4 roles a rendered cell can play).

**Encoded as** — the `skip` boolean plus `span`/`rowspan` magic ints in the
cell dicts built by `_table_html` (`conversions/documents.py:245-254`). A
`skip=False, span=1, rowspan=1` triple is "normal"; `span>1` or `rowspan>1`
makes it a merge head; `skip=True` means the `<w:tc>` is a phantom re-entry
of a vertically merged cell.

**Invalid combos** — `skip=True` with `span>1` is produced today whenever a
vertically-merged cell is also the head of a horizontal merge: the first
pass assigns `span` (documents.py:255-256) and the second pass later sets
`skip` (documents.py:271) — the span is silently ignored only because the
renderer checks `skip` first (documents.py:337). `skip=True` with
`rowspan>1` is representable too.

**Transitions** —
- span assignment (horizontal merge): documents.py:237-256
- skip/rowspan fold (vertical merge, found by `tc` identity scan of all
  rows above): documents.py:260-271
- reads: renderer documents.py:337-343, text export documents.py:350

**Risk** — *Low.* Wrong combos are silently ignored rather than crashed, but
silently: a docx with a both-directions merged region can drop or mis-size
cells in docx→pdf/html output with no note to the user. The `tc`-identity
lookup is also O(rows²) and order-dependent.

## `CONVERSION_ISOLATION` execution mode

**States** — `process` / `inline` (2 declared states, `docs/ARCHITECTURE.md:101`),
plus a silently-accepted third: *any other string*.

**Encoded as** — a free-form env string (`core/config.py:46`) compared
against raw literals in three places: `app.py:128` (`== "process"`, gates
the warm-up thread), `core/runner.py:61` (`!= "process"`, gates `warm_up`),
`core/runner.py:294` (`== "inline"`, selects `_run_inline` vs `_run_process`).

**Invalid combos** — `CONVERSION_ISOLATION="proces"` (or any typo) is valid
to every comparison: `run()` takes `_run_process` (it is "not inline") while
`warm_up` and the `_warmed` hook never fire — the app runs process-isolated
conversions but with a cold first request and no pre-spawned idle worker.

**Transitions** — none at runtime; the mode is read at call time in the
three sites above, so a typo splits the app across two half-initialised
modes rather than failing fast.

**Risk** — *Low.* Degraded-latency deployment rather than a correctness bug,
but a typo is undetectable: nothing validates the value and no third state
is named.
