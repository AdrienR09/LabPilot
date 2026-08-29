# Workflow Composition Strategy (Phase 3)

Design for how a workflow declares which tier-2 capabilities it needs
(scanning, optimizing, acquisition, saving) and has the framework wire them
— and their tier-3 UI — in automatically, without exposing that wiring to
the end user. Builds on `LOGIC_LIBRARY_NOTES.md` (Phase 1: what scanning/
optimizer/acquisition logic looks like in the three reference frameworks)
and `UI_FRAMEWORK_DESIGN.md` (Phase 2: the tier-3 catalog and the proposal
to extend LabPilot's own `COMPONENT_REGISTRY` to workflow-level UI).

This is a design document only — no implementation in this phase, per the
phase constraints. It is written to be concrete enough that Phase 4 can
implement directly from it, grounded in the actual current code rather
than the reference frameworks in the abstract.

---

## 1. The problem, as it actually exists in this repo today

Two real, current pieces of evidence motivate this design — not hypothetical
gaps, things already present in `core/workflow_templates/`:

- **Two independent optimizer implementations already exist, sharing no
  code.** `server.py`'s `_run_optimize` (a fixed-range grid scan around the
  crosshair-bound actuator's current position, `LOGIC_LIBRARY_NOTES.md`'s
  finding that this only reads its range from a hardcoded default today)
  and `actuator_optimization.py`'s hand-written `run()` (a coarse grid scan
  over `SEARCH_RANGE` followed by a step-halving hill-climb refinement) both
  solve "move an actuator to maximize a detector reading," with entirely
  separate code, entirely separate settings, and no shared abstraction
  between them. A third, different-again approach
  (`autofocus.py`: scan a range, fit a peak, move to the fit center) solves
  a closely related problem a third way. None of these three call each
  other or share a base class.
- **"Does this workflow have an optimizer" is currently inferred from a UI
  declaration, not a capability declaration.** `server.py`'s
  `_resolve_optimize_targets` (`server.py:694`) determines whether
  `/optimize/start` is even valid for a given workflow by checking
  `RESULT_UI.get("crosshair")` — i.e. *whether the scan panel happens to
  draw a draggable position marker* is what currently gates *whether a
  background optimize task can run at all*. These are genuinely different
  concerns (one is "should this workflow's live view show a movable
  marker," the other is "should this workflow expose an auto-centering
  routine") that happen to coincide for `omniscan.py` today but need not in
  general — a future workflow might want the optimizer without ever
  wanting a draggable crosshair, or vice versa.
- **Partial precedent for shared tier-2 already exists and works well**:
  `core/workflow_templates/_common.py` (`move_and_settle`, `detector_axes`,
  `spectrum_key`, `integration_time_key`) and `core/analysis/fits.py`
  (`fit_peak`/`fit_dip`, used by both `autofocus.py` and
  `peak_fit_series.py`) are genuine shared tier-2-*adjacent* functions,
  extracted specifically because they were "previously copy-pasted
  near-identically into several templates" (`_common.py`'s own docstring).
  This is the right instinct, not yet extended to the bigger, stateful
  capabilities (scanning-as-a-loop, optimizing, timed acquisition) — those
  remain hand-rolled per template rather than reusable objects, which is
  precisely what "Each capability is its own object-oriented, independently
  parametrized module" (this project's own tier-2 definition) asks for.
- **Saving is already capability-shaped, and already automatic** — worth
  noting as the one piece of this problem that's *already solved* the way
  the rest should be: `hdf5_export.py`'s `save_workflow_result_hdf5` is one
  shared function, dispatched generically by `RESULT_UI["type"]`
  (`"ndscan"`/`"image2d"`/`"spectrum"`/fallback), available from
  `workflow_window.py`'s menu for *any* workflow with no per-template save
  code at all. This is the target shape for scanning and optimizing too —
  the design below is really "make scanning and optimizing as automatic as
  saving already is," not inventing a new pattern from nothing.

---

## 2. The capability contract (tier-2)

A **capability** is an independently parametrized, object-oriented module
implementing one reusable piece of acquisition behavior, decoupled from any
specific workflow template. Four to start with, each grounded in something
that already exists in this repo in un-shared form:

- **`ScanCapability`** — steps one or more actuator axes across declared
  ranges, reading a detector at each point. Generalizes `omniscan.py`'s
  current inline `run()` loop (the actuator-shape/detector-shape/
  `itertools.product` logic already there) into a reusable object other
  capabilities (below) can drive instead of reimplementing.
- **`OptimizerCapability`** — refines/centers a position by repeatedly
  reading a detector and moving an actuator, reporting progress the same
  way a scan does. Internally **built on `ScanCapability`** rather than
  moving actuators directly — a grid-search-then-refine optimizer (today's
  `actuator_optimization.py` shape) or a sequence-of-sub-scans-then-fit
  optimizer (qudi's shape, `LOGIC_LIBRARY_NOTES.md` §2.1) are both, at
  bottom, "run one or more small scans and look at where the result peaks"
  — reusing `ScanCapability` for the actual move-and-read mechanics avoids
  the exact duplication described in §1. (pyMoDAQ's ask/tell interface,
  `LOGIC_LIBRARY_NOTES.md` §2.2, is a genuinely different — more general —
  shape than either; noted as the fuller upgrade path, not required for
  the first concrete implementation.)
- **`AcquisitionCapability`** — repeated, timed reads at a fixed position
  (no actuator motion), with start/stop and a reportable rate. Generalizes
  `time_series_acquisition.py`'s inline `asyncio.sleep` loop and the read-
  side of `pid_stabilization.py`'s loop.
- **`SaveCapability`** — already effectively exists (`hdf5_export.py`) and
  needs the least new work; included here mainly so it's declared the same
  way as the other three, for a uniform story, not because it needs a new
  implementation.

**Common lifecycle**, so the framework can drive any of them uniformly
without knowing which concrete capability it's talking to:
- `configure(**params) -> None` — validate and store this run's settings
  (mirrors `ScanningProbeLogic.set_scan_settings`'s reject-while-running
  discipline, `LOGIC_LIBRARY_NOTES.md` §1.1).
- `async run(session) -> dict` (or `run_step` for a capability with a
  natural per-step granularity like `ScanCapability`) — does the work,
  calling `session.report_progress(...)` exactly as today's templates do
  (no change to that already-working mechanism).
- `stop()` — cooperative cancellation, matching every existing template's
  existing `except asyncio.CancelledError` handling.
- A capability that depends on another declares it via a flat
  `requires: list[str]` class attribute (e.g. `OptimizerCapability.
  requires = ["scan"]`) — see §4 for what "requires" means here precisely
  (shared infrastructure, not execution order).

This contract is deliberately thin — four methods, one dependency list —
matching the user's own instruction that "internally this can be as
structured as needed... but the user-facing surface must stay simple":
with only four capability types envisioned, an elaborate plugin/dependency-
injection framework would be solving a problem this project doesn't have
yet. A flat list + topological instantiation order is enough.

---

## 3. Declaration surface (what a workflow author writes)

A new, optional top-level constant, parsed the same safe way
`REQUIRED_INSTRUMENTS`/`RESULT_UI` already are (`ast.literal_eval` on the
parsed AST — never executes the script, matching `instrument_roles.py`'s
existing safety property exactly):

```python
CAPABILITIES = {
    "scan": {},                        # this workflow's own run() IS the scan;
                                        # empty dict = "yes, wire this in"
    "optimizer": {"around": "actuator"},  # which role to optimize the position of
    "save": {},                        # always cheap to declare; see below
}
```

- **Backward compatible by construction**: a template with no
  `CAPABILITIES` constant at all (every existing template today) keeps
  working exactly as it does now — `read_capabilities()` falls back to
  inferring `{"optimizer": {"around": crosshair["role"]}}` from
  `RESULT_UI.get("crosshair")` when present, reproducing today's exact
  behavior for `omniscan.py`/`confocal_scanner.py` without editing either
  file. This means Phase 4 does not need to touch every existing template
  — only the new generalized scanner needs to declare `CAPABILITIES`
  explicitly (see §7).
- **Save is cheap to always declare** (or infer unconditionally, the same
  way it's unconditionally available today) — it has no real "off" state
  worth exposing; listed mainly for uniformity with the other three, not
  because anyone needs to opt out of it.
- **What this deliberately does NOT ask the workflow author to specify**:
  which tier-3 UI components appear, which server endpoints exist, or how
  `OptimizerCapability` gets its actuator/detector adapters — all of that
  is resolved automatically from `CAPABILITIES` + the already-existing
  `REQUIRED_INSTRUMENTS`/`instrument_bindings`, per §4/§5. The one-line
  declaration above is the *entire* user-facing surface this phase adds.

---

## 4. Auto-wiring (framework side, backend)

**`CapabilityRegistry`** — the same registration pattern as this project's
own `adapter_registry` (tier-1 instruments) and `COMPONENT_REGISTRY`
(tier-3 UI components, `UI_FRAMEWORK_DESIGN.md` §1) — a dict of
`{capability_name: capability_class}`, so adding a fifth capability later
never means touching `server.py`'s routing code, only registering a new
class.

**Instantiation, given a workflow's `CAPABILITIES` + `instrument_bindings`**:
1. Read `CAPABILITIES` (with the §3 fallback) and `REQUIRED_INSTRUMENTS`/
   `instrument_bindings` (already-existing mechanisms, unchanged).
2. Topologically order declared capabilities by `requires` (§2) — with
   only four capability types and at most one level of dependency
   (`optimizer` → `scan`), this is a two-pass "instantiate anything with no
   unmet `requires` first, then anything that depended on it," not a
   general-purpose scheduler.
3. Instantiate each, resolving its needed roles from `instrument_bindings`
   the same way `_resolve_optimize_targets` already does today (§1) — that
   function's actuator/detector-resolution logic becomes the generic
   capability-instantiation helper instead of code specific to the
   optimizer route.
4. **"Requires" means shared infrastructure, not run-before/-after
   sequencing.** This is the one nuance worth being explicit about:
   `OptimizerCapability.requires = ["scan"]` does **not** mean "run a scan,
   then optimize" — it means "reuse the already-resolved actuator/detector
   adapters and the `ScanCapability` instance's own move-and-read
   primitives, rather than re-resolving/reimplementing them." The optimizer
   stays exactly what it is today: a separate, on-demand action
   (`/optimize/start`, triggered from the toolbar independent of Execute/
   Stop) — §4 is about *sharing objects*, not *ordering phases of one
   pipeline*. A future capability that genuinely needs ordering (e.g. "run
   an autofocus pass before the main scan starts") is a real, different
   case this document doesn't need to solve yet — none of the four
   capabilities above require it.
5. **Generic endpoints per declared capability**, replacing the current
   omniscan-specific hand-written routes: instead of `/optimize/start`/
   `/stop`/`/state` existing unconditionally in `server.py` and gating
   themselves internally on whether `RESULT_UI` happens to have a
   crosshair, these three routes become **conditional on `"optimizer"`
   being a resolved capability for that workflow_id** — any workflow
   declaring the `optimizer` capability gets them for free, any workflow
   that doesn't gets a clean 404, and the routes' *implementation* becomes
   "call `OptimizerCapability.run()`" instead of the bespoke grid-scan code
   `_run_optimize` hardcodes today. The same shape generalizes to a future
   `AcquisitionCapability` needing its own start/stop/state trio, without
   writing three more bespoke routes each time.

---

## 5. Tier-3 wiring (linking to Phase 2)

`CAPABILITIES` drives which UI components appear, via the `COMPONENT_
REGISTRY` extension `UI_FRAMEWORK_DESIGN.md` §4 already proposed:

- Declaring `"optimizer"` is what should add the `optimizer_panel`
  component (today: `_add_optimizer_dock`, called unconditionally whenever
  `RESULT_UI["crosshair"]` is present) — decoupling *this* wiring from the
  crosshair the same way §4 decouples the backend routes from it.
  `RESULT_UI["crosshair"]` then goes back to meaning only what its name
  says — "does the scan panel draw a draggable marker" — a purely tier-3,
  cosmetic concern, independent of whether an optimizer capability backs
  it.
- Declaring `"scan"` is what selects `scan_panel`/`ndscan_view` (§4 of
  `UI_FRAMEWORK_DESIGN.md`'s dimensionality-dispatched viewer proposal) —
  today this is implied entirely by `RESULT_UI["type"]`; with `CAPABILITIES`
  present, `RESULT_UI` can shrink to being purely a UI-shape hint (which
  axes, which labels) rather than also being relied on as a proxy for "this
  workflow does scanning" the way `_resolve_optimize_targets` currently
  half-relies on it (via `REQUIRED_INSTRUMENTS`'s `kind: "detector"` lookup,
  `server.py:719`).
- Declaring `"save"` is what adds the "Save Data (HDF5)…" menu action —
  today unconditional for every workflow with any `RESULT_UI` at all,
  including ones whose shape `hdf5_export.py`'s `_write_generic` fallback
  handles only best-effort. Tightening this to "only offer Save when a
  save capability is actually declared" is a minor, optional cleanup this
  design enables but doesn't require Phase 4 to do.

---

## 6. Before / after, concretely

**Before** (today, `actuator_optimization.py` — optimizer logic hand-rolled,
invisible to `server.py`'s generic `/optimize/*` routes, which only work
for a `RESULT_UI["crosshair"]`-declaring workflow like `omniscan.py`):
```python
# ~80 lines of coarse-grid + hill-climb optimizer logic inside run(),
# nothing shared with server.py's separate, different optimizer.
```

**After** (a hypothetical future template using the capability contract):
```python
REQUIRED_INSTRUMENTS = {"actuator": {...}, "detector": {...}}
CAPABILITIES = {"optimizer": {"around": "actuator"}, "save": {}}
# No hand-written grid-search/hill-climb code — OptimizerCapability
# (backed by ScanCapability) does it, the SAME implementation
# server.py's /optimize/* routes already use for any other workflow
# declaring the same capability.
```
The workflow author's own `run()` (if any) shrinks to whatever is
genuinely specific to that experiment; the optimizer, its endpoints, and
its UI panel are no longer something each template re-derives.

---

## 7. Migration strategy — what Phase 4 should and shouldn't touch

Consistent with this project's own explicit constraint ("do not proceed to
any other experiment type... until this scanner workflow is fully
working"):

- **Phase 4 implements `ScanCapability`, `OptimizerCapability`, and
  `CapabilityRegistry`**, and wires the new generalized N-D scanner
  workflow through them (likely evolving `omniscan.py` itself, since it's
  already the closest thing to this shape — decided in Phase 4, not here).
- **Phase 4 should NOT migrate** `actuator_optimization.py`,
  `autofocus.py`, `pid_stabilization.py`, `peak_fit_series.py`, or
  `time_series_acquisition.py` onto the new capability classes yet — they
  keep working exactly as they are (nothing in §3's backward-compatibility
  design requires touching them), and migrating them is explicitly
  deferred until after the scanner proving ground is evaluated, per this
  project's own stated sequencing. `actuator_optimization.py` in particular
  is left as a visible, honest "before" example (§1) rather than quietly
  fixed as a side effect of Phase 4 — revisiting it is a natural candidate
  for whatever comes after the scanner is validated, not before.
- **`AcquisitionCapability` and `SaveCapability`'s own classes** can be
  stubbed/deferred if Phase 4's scanner doesn't need them directly (the
  scanner's own `run()` loop already needs to become `ScanCapability`;
  saving already works via `hdf5_export.py` regardless of whether it's
  formally wrapped in a `SaveCapability` class yet) — implementing all four
  capability classes is not a precondition for Phase 4 to proceed, only
  `ScanCapability`/`OptimizerCapability` are actually load-bearing for the
  scanner.

---

## 8. Open questions, deliberately deferred to Phase 4

- Exact method signature for `ScanCapability.run_step` vs. a single
  `run()` that internally loops — Phase 4's actual generalized scanner
  requirements (manual jogging *independent of* a running scan, per-axis
  subset selection) may push toward a step-callable design rather than one
  opaque `run()`; not resolved here since it's an implementation detail
  best settled against the real requirements, not guessed at abstractly.
- Whether `OptimizerCapability`'s first concrete implementation should be
  the grid-search-then-refine shape (`actuator_optimization.py`'s existing
  approach, simplest to generalize) or move toward pyMoDAQ's ask/tell
  interface (`LOGIC_LIBRARY_NOTES.md` §2.2, more general but a bigger
  lift) — both are compatible with the contract in §2; Phase 4 should pick
  based on what the generalized scanner's own optimizer requirement
  actually needs, not preemptively build the more general one.
- Whether `RESULT_UI` should eventually shrink to a pure UI-shape hint
  (§5) or keep double-duty a while longer — not a blocking decision for
  Phase 4, which can introduce `CAPABILITIES` alongside the existing
  `RESULT_UI` without immediately trimming the latter.

No new external-framework code was read for this phase (it draws on
Phase 1/2's already-cited material — pyMoDAQ's ask/tell optimizer and
`CustomApp` mixin composition, qudi's `Connector`-based dependency wiring,
PyMeasure's declarative constructor injection) — no new licensing citations
beyond what `LOGIC_LIBRARY_NOTES.md` §5 and `UI_FRAMEWORK_DESIGN.md` §5
already recorded (Qudi: LGPLv3 per-file; pyMoDAQ, PyMeasure: MIT). Nothing
here is copied code, only pattern-level design informed by both.
