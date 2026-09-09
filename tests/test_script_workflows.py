"""A workflow script is plain Python.

`async def run(session) -> dict` made you know what a coroutine is, what
`session` is, and which calls to await, before writing five lines of
physics. A script is now top-level code that imports what it uses.

Two properties carry the design and are what these pin: **imports, not
injected globals**, so the file stays valid, lintable, directly runnable
Python; and **both shapes on one executor**, so no existing template has
to be rewritten to land this.
"""

from __future__ import annotations

import asyncio
import textwrap

import pytest

from labpilot.core.run.script import has_run_function, run_script
from labpilot.core.session import Session
from labpilot.instruments import adapter_registry

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _session(**devices: str) -> Session:
    session = Session()
    for role, key in devices.items():
        adapter = adapter_registry.get(key)()
        await adapter.connect()
        session.register(adapter, role)
    return session


def write(tmp_path, source: str, name: str = "wf.py"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(source).lstrip())
    return path


# --- Which shape is this file? --------------------------------------------


def test_a_top_level_run_function_marks_the_legacy_shape():
    assert has_run_function("async def run(session):\n    return {}\n")
    assert has_run_function("def run(session):\n    return {}\n")


def test_a_plain_script_is_not_mistaken_for_the_legacy_shape():
    assert not has_run_function("from labpilot.script import scan\nx = 1\n")


def test_a_nested_run_does_not_count():
    """Only a top-level `run` is the contract; a helper named `run` inside
    a class or another function is the author's business."""
    assert not has_run_function("class Thing:\n    def run(self):\n        pass\n")


def test_the_shape_is_decided_without_executing_the_file(tmp_path):
    """Importing to find out would already have run a plain script's body
    — the same never-execute-to-inspect property REQUIRED_INSTRUMENTS has."""
    path = write(tmp_path, """
        from pathlib import Path
        Path(__file__).with_suffix(".ran").touch()
        RESULT = {"ok": True}
    """)
    assert not has_run_function(path.read_text())
    assert not path.with_suffix(".ran").exists()


# --- The plain shape runs --------------------------------------------------


async def test_a_plain_script_body_is_the_program(tmp_path):
    session = await _session()
    path = write(tmp_path, """
        RESULT = {"answer": 6 * 7}
    """)
    assert await run_script(session, path) == {"answer": 42}


async def test_a_script_with_no_result_returns_an_empty_one(tmp_path):
    session = await _session()
    assert await run_script(session, write(tmp_path, "x = 1\n")) == {}


async def test_a_non_dict_result_is_wrapped(tmp_path):
    session = await _session()
    path = write(tmp_path, "RESULT = [1, 2, 3]\n")
    assert await run_script(session, path) == {"result": [1, 2, 3]}


async def test_a_script_reaches_its_instruments_by_role(tmp_path):
    """`bind` gives the same surface `session.get` does in a template and
    `lp[...]` does at the console — the same API, a different transport."""
    session = await _session(detector="mock_basic_detector_0d")
    path = write(tmp_path, """
        from labpilot.script import bind

        apd = bind("detector")
        reading = apd.read()
        RESULT = {"keys": sorted(reading)}
    """)
    result = await run_script(session, path)
    assert result["keys"]


async def test_a_script_writes_settings_with_keywords(tmp_path):
    session = await _session(source="mock_basic_source")
    path = write(tmp_path, """
        from labpilot.script import bind

        source = bind("source")
        source.write(output=0.75)
        RESULT = {"output": source.read()["output"]}
    """)
    # The mock adds readback noise, as a real source would.
    assert (await run_script(session, path))["output"] == pytest.approx(0.75, rel=1e-2)


async def test_an_unbound_role_says_what_is_registered(tmp_path):
    session = await _session(detector="mock_basic_detector_0d")
    path = write(tmp_path, """
        from labpilot.script import bind
        apd = bind("nonexistent")
    """)
    with pytest.raises(KeyError, match="detector"):
        await run_script(session, path)


async def test_an_optional_role_that_is_unbound_is_none(tmp_path):
    session = await _session()
    path = write(tmp_path, """
        from labpilot.script import bind
        RESULT = {"bound": bind("laser", optional=True) is not None}
    """)
    assert (await run_script(session, path))["bound"] is False


async def test_a_script_runs_a_plan_and_that_becomes_its_result(tmp_path):
    """A script whose whole job is one plan needs no RESULT — and gets
    patch streaming, pause, abort and the HDF5 save it would not get from
    a hand-written loop."""
    session = await _session(stage="mock_basic_actuator_nd", apd="mock_basic_detector_0d")
    path = write(tmp_path, """
        from labpilot.script import scan

        RANGE = (0.0, 1.0, 4)

        scan(over={"stage.x": RANGE}, read="apd")
    """)
    result = await run_script(session, path)
    assert len(result["data"]) == 4


async def test_an_exception_in_a_script_propagates_with_its_line(tmp_path):
    """So the Workflows tab shows where it broke, not where we ran it."""
    session = await _session()
    path = write(tmp_path, """
        x = 1
        raise ValueError("deliberate")
    """)
    with pytest.raises(ValueError, match="deliberate"):
        await run_script(session, path)


async def test_a_missing_file_says_so(tmp_path):
    session = await _session()
    with pytest.raises(FileNotFoundError):
        await run_script(session, tmp_path / "absent.py")


# --- Parameters ------------------------------------------------------------


async def test_an_instance_parameter_overrides_the_file(tmp_path):
    """The convention is unchanged — a module-level UPPERCASE constant —
    and only where the value is kept has changed. The file itself is never
    rewritten, which is what the old parameter store did."""
    path = write(tmp_path, """
        POINTS = 5
        RESULT = {"points": POINTS}
    """)
    session = await _session()
    assert (await run_script(session, path))["points"] == 5
    assert (await run_script(session, path, {"POINTS": 11}))["points"] == 11
    assert "POINTS = 5" in path.read_text()


async def test_an_annotated_parameter_is_overridden_too(tmp_path):
    session = await _session()
    path = write(tmp_path, """
        POINTS: int = 5
        RESULT = {"points": POINTS}
    """)
    assert (await run_script(session, path, {"POINTS": 9}))["points"] == 9


async def test_a_parameter_the_file_does_not_declare_is_ignored(tmp_path):
    """Same granularity the legacy shape's `setattr` has."""
    session = await _session()
    path = write(tmp_path, "RESULT = {'ok': True}\n")
    assert await run_script(session, path, {"UNKNOWN": 1}) == {"ok": True}


async def test_a_parameter_is_applied_before_the_body_uses_it(tmp_path):
    """The whole difficulty of the plain shape: there is no `run()` to be
    called later, so a value set afterwards would be set too late."""
    session = await _session()
    path = write(tmp_path, """
        SCALE = 2
        DOUBLED = SCALE * 10
        RESULT = {"doubled": DOUBLED}
    """)
    assert (await run_script(session, path, {"SCALE": 7}))["doubled"] == 70


async def test_two_runs_of_one_file_do_not_share_parameters(tmp_path):
    session = await _session()
    path = write(tmp_path, """
        POINTS = 5
        RESULT = {"points": POINTS}
    """)
    first = await run_script(session, path, {"POINTS": 11})
    second = await run_script(session, path)
    assert (first["points"], second["points"]) == (11, 5)


# --- Abort -----------------------------------------------------------------


async def test_aborting_a_plain_script_stops_it_at_its_next_call(tmp_path):
    """Cancellation stops depending on where the author put an `await`:
    every instrument call is a checkpoint, because every one checks the
    abort flag around its I/O."""
    session = await _session(detector="mock_basic_detector_0d")
    path = write(tmp_path, """
        from pathlib import Path
        from labpilot.script import bind

        apd = bind("detector")
        marker = Path(__file__).with_suffix(".stopped")
        try:
            while True:
                apd.read()
        finally:
            marker.touch()
    """)
    task = asyncio.ensure_future(run_script(session, path))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The body unwound through its own `finally` — a script that turns its
    # laser off in one gets to.
    assert path.with_suffix(".stopped").exists()


async def test_a_script_can_catch_its_own_abort(tmp_path):
    """Stop arrives as an ordinary exception the script can name, so a
    script that must park its hardware on the way out can."""
    session = await _session(detector="mock_basic_detector_0d")
    path = write(tmp_path, """
        from pathlib import Path
        from labpilot.script import ScriptAbortedError, bind

        apd = bind("detector")
        try:
            while True:
                apd.read()
        except ScriptAbortedError:
            Path(__file__).with_suffix(".caught").touch()
            raise
    """)
    task = asyncio.ensure_future(run_script(session, path))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert path.with_suffix(".caught").exists()


async def test_a_script_can_check_the_abort_flag_itself(tmp_path):
    """For a long computation between instrument calls, which has no
    checkpoint of its own."""
    session = await _session()
    path = write(tmp_path, """
        from labpilot.script import aborted
        RESULT = {"aborted": aborted()}
    """)
    assert (await run_script(session, path))["aborted"] is False


# --- The legacy shape still runs -------------------------------------------


async def test_the_original_shape_is_unchanged(tmp_path):
    """No template has to be rewritten to land this."""
    session = await _session()
    path = write(tmp_path, """
        POINTS = 3

        async def run(session):
            return {"points": POINTS}
    """)
    assert (await run_script(session, path))["points"] == 3
    assert (await run_script(session, path, {"POINTS": 8}))["points"] == 8


async def test_a_legacy_script_returning_a_non_dict_is_wrapped(tmp_path):
    session = await _session()
    path = write(tmp_path, """
        async def run(session):
            return 42
    """)
    assert await run_script(session, path) == {"result": 42}


# --- Outside a run ---------------------------------------------------------


def test_the_script_api_outside_a_run_says_where_to_run_it():
    """The file is ordinary Python, so someone will run it directly. The
    error has to say what is missing rather than fail on a None."""
    from labpilot.script import session as script_session

    with pytest.raises(RuntimeError, match="LABPILOT_URL"):
        script_session()


def test_report_outside_a_run_is_a_no_op():
    """So a script can call it unconditionally."""
    from labpilot.script import report

    report(progress=1.0)


def test_aborted_outside_a_run_is_false():
    from labpilot.script import aborted

    assert aborted() is False
