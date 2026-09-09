"""End-to-end smoke test for every shipped workflow template.

This is the regression net the data-model work depends on. Each template is
run the same way `RunManager._execute_script` runs it — through
`core/run/script.py`, so both accepted shapes are covered by the same
harness — bound to mock instruments matching its own `REQUIRED_INSTRUMENTS`
declaration, shrunk to a handful of points, and run to completion. Then the
invariant that nothing previously checked:

    every `*_key` a template's RESULT_UI names must actually be produced by
    that template — in a progress frame, in the final result, or both.

`RESULT_UI` is a string map from renderer slots to whatever keys the script
happens to emit, and nothing validates the two against each other. A typo
renders a blank panel in the workflow window with no error anywhere. Here it
fails a test.

Templates are run against `instruments.MockBasic` rather than the simpler
`instruments.mock` family because MockBasic actuators and detectors share a
simulated sample, so a scan produces a real peak instead of noise — which
keeps the fitting templates on their success path.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from labpilot.core.run.script import run_script
from labpilot.core.session import Session
from labpilot.core.workflow.instrument_roles import (
    read_required_instruments,
    read_result_ui,
    read_workflow_params,
)
from labpilot.core.workflow.presets import load_presets
from labpilot.instruments.mock.hardware_scan import MockNIScanner
from labpilot.instruments.mock.microwave_sources import MockMicrowaveSource
from labpilot.instruments.MockBasic.simple import (
    MockBasicActuator1D,
    MockBasicActuatorND,
    MockBasicDetector0D,
    MockBasicDetector1D,
    MockBasicDetector2D,
    MockBasicSource,
)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "labpilot" / "core" / "workflow_templates"

# One mock per (kind, dimensionality) a template can ask for. `dimensionality`
# is omitted by roles that accept anything, hence the None fallbacks.
_MOCKS = {
    ("motor", "1D"): MockBasicActuator1D,
    ("motor", "ND"): MockBasicActuatorND,
    ("motor", None): MockBasicActuatorND,
    ("detector", "0D"): MockBasicDetector0D,
    ("detector", "1D"): MockBasicDetector1D,
    ("detector", "2D"): MockBasicDetector2D,
    ("detector", None): MockBasicDetector0D,
    ("source", "SOURCE"): MockBasicSource,
    ("source", None): MockBasicSource,
    ("generic", None): MockNIScanner,
}

# Per-template constant overrides, passed as the workflow instance's
# parameters — exactly how a saved instance overrides a template's
# defaults. Purely about runtime: every template ships defaults sized for a real
# acquisition (a 5x5 grid, 5 averages, a 20 s PID settle), which would make
# this suite minutes long for no extra coverage.
_SHRINK: dict[str, dict] = {
    "actuator_optimization": {"N_COARSE_STEPS": 4, "N_REFINE_ROUNDS": 1},
    "autofocus": {"Z_POSITIONS": [-1.0, 0.0, 1.0]},
    "grating_spectrometer": {"GRATING_POSITIONS": [0.0, 1.0]},
    "hardware_timed_scan": {
        "SCAN_AXES": ["x", "y"],
        "SCAN_RANGES": {"x": (-2.0, 2.0, 8), "y": (-2.0, 2.0, 8)},
    },
    "odmr_sweep": {"SWEEP_POINTS": 5, "AVERAGES": 2},
    # MockBasicSource's output is a 0-10 generic drive level, so keep the PID
    # setpoint and actuation range inside what it will actually accept — it is
    # one of the few adapters that enforces its own declared limits.
    "pid_stabilization": {"DURATION_S": 0.6, "DT_S": 0.2, "SETPOINT": 0.5, "OUTPUT_MAX": 10.0},
    "omniscan": {
        "SCAN_AXES": ["x", "y"],
        "AXIS_RANGES": {"x": (-1.0, 1.0, 2), "y": (-1.0, 1.0, 2)},
    },
    "peak_fit_series": {"N_REPEATS": 3},
    "pump_probe_spectroscopy": {"DELAY_POSITIONS_MM": [0.0, 1.0]},
    "time_series_acquisition": {"DURATION_S": 0.6, "SAMPLE_INTERVAL_S": 0.2},
}

# omniscan declares three optional roles and picks a strategy from whichever
# are bound. Binding actuator+detector exercises the per-point path; the
# hardware-timed path is covered by hardware_timed_scan's own scanner role.
_ROLE_OVERRIDES: dict[str, set[str]] = {"omniscan": {"actuator", "detector"}}

# Where the generic per-kind mock is the wrong physical instrument. ODMR sweeps
# a microwave frequency in the GHz, which MockBasicSource's 0-10 generic output
# rejects outright; MockMicrowaveSource is the mock this template was written
# against, and it also exercises the sweep-key/power-key detection in run().
_MOCK_OVERRIDES: dict[tuple[str, str], type] = {
    ("odmr_sweep", "source"): MockMicrowaveSource,
    # A hyperspectral scan is a spectrometer at every pixel, and this preset
    # asks for an integration time — which a 0D counter has no parameter
    # for, and omniscan rightly refuses to silently ignore.
    ("hyperspectral_imaging", "detector"): MockBasicDetector1D,
}


def _template_names() -> list[str]:
    return sorted(
        p.stem
        for p in TEMPLATE_DIR.glob("*.py")
        if p.stem not in ("__init__", "_common")
    )


TEMPLATES = _template_names()

# A preset is loadable exactly like a template (see
# core/workflow/presets.py), so it gets the same smoke coverage: its base
# module, its declared parameters applied on top, run to completion. Four
# templates became presets, and without this the suite would simply have
# stopped covering them.
PRESETS = sorted(load_presets())


class _KeyRecordingSink(dict):
    """Progress sink that remembers every key any frame carried.

    `Session.report_progress` overwrites `sink[workflow_id]` on each call, so
    the plain dict only ever holds the last frame — but a key can legitimately
    appear only in progress (hyperspectral_imaging's `live_image` is never in
    the final result) so the union across frames is what the assertion needs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.seen_keys: set[str] = set()

    def __setitem__(self, key, value):
        if isinstance(value, dict):
            self.seen_keys.update(value)
        super().__setitem__(key, value)


def _source(name: str) -> str:
    """A template's text. Never imported to inspect it: a plain script's
    body is its program, so importing would already have run it."""
    return (TEMPLATE_DIR / f"{name}.py").read_text()


async def _build_session(script: str, name: str, mock_key: str | None = None) -> Session:
    """Bind one mock per role the module declares.

    `mock_key` names the entry to look up in `_MOCK_OVERRIDES` when it is
    not the module's own — a preset picks its instruments under its own
    name while taking its roles from the template it runs.
    """
    session = Session()
    mock_key = mock_key or name
    wanted = _ROLE_OVERRIDES.get(name)
    for role, spec in read_required_instruments(script).items():
        if wanted is not None and role not in wanted:
            continue
        kind = spec.get("kind")
        dim = spec.get("dimensionality")
        factory = (
            _MOCK_OVERRIDES.get((mock_key, role))
            or _MOCKS.get((kind, dim))
            or _MOCKS.get((kind, None))
        )
        assert factory is not None, f"{name}: no mock for kind={kind!r} dim={dim!r}"
        adapter = factory()
        await adapter.connect()
        session.register(adapter, name=role)
    return session


@pytest.mark.parametrize("name", TEMPLATES)
async def test_template_runs_and_emits_its_declared_result_keys(name):
    script = _source(name)
    declared = read_workflow_params(script)

    params = _SHRINK.get(name, {})
    for const in params:
        assert const in declared, f"{name}: shrink target {const} no longer exists"

    session = await _build_session(script, name)
    sink = _KeyRecordingSink()
    session.set_progress_context(f"smoke_{name}", "exec_smoke", sink)
    try:
        result = await asyncio.wait_for(
            run_script(session, TEMPLATE_DIR / f"{name}.py", params), timeout=120
        )
    finally:
        session.clear_progress_context()

    assert isinstance(result, dict) and result, f"{name}: produced {result!r}"

    produced = set(result) | sink.seen_keys
    declared = {v for k, v in read_result_ui(script).items() if k.endswith("_key")}
    missing = sorted(declared - produced)
    assert not missing, (
        f"{name}: RESULT_UI names {missing}, which the run never produced in a "
        f"progress frame or its result. Produced: {sorted(produced)}"
    )


@pytest.mark.parametrize("name", PRESETS)
async def test_preset_runs_its_base_template_and_emits_its_result_keys(name):
    """The same check the templates get, for the presets that replaced four
    of them — a preset that names a parameter its base template dropped
    would otherwise fail silently at load time."""
    preset = load_presets()[name]
    script = _source(preset.template)

    declared = read_workflow_params(script)
    for const in preset.params:
        assert const in declared, (
            f"preset {name!r} sets {const!r}, which {preset.template!r} does "
            f"not declare — it would be dropped on load"
        )
    # Small enough to run in a test; the preset's own grid is sized for a
    # real acquisition.
    params = {**preset.params, **_SHRINK.get(preset.template, {})}

    session = await _build_session(script, preset.template, mock_key=name)
    sink = _KeyRecordingSink()
    session.set_progress_context(f"smoke_{name}", "exec_smoke", sink)
    try:
        result = await asyncio.wait_for(
            run_script(session, TEMPLATE_DIR / f"{preset.template}.py", params),
            timeout=120,
        )
    finally:
        session.clear_progress_context()

    produced = set(result) | sink.seen_keys
    missing = sorted(
        {v for k, v in read_result_ui(script).items() if k.endswith("_key")} - produced
    )
    assert not missing, f"{name}: RESULT_UI names {missing}, never produced"


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_declarations_are_readable_without_executing_it(name):
    """Both declaration readers work purely on the AST — the server must be
    able to discover what a template needs without importing it."""
    script = (TEMPLATE_DIR / f"{name}.py").read_text()
    read_result_ui(script)
    read_workflow_params(script)
