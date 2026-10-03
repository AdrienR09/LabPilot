"""The interactive scripting surface — what the IPython console binds to `lp`.

`lp["stage"]` hands back a kind-typed handle whose methods are the same
ones a workflow template gets from `session.get("actuator")`
(`core/device/kinds.py`): `move_abs`, `move_rel`, `get_position`,
`read_value`, `acquire_once`, `set_integration_time`, `stage`, `unstage`,
`actions`. Same names, same arguments, same meaning — the difference is
the transport underneath. In a template the wrapper holds the adapter
directly and its methods are awaited; here every call is a REST round trip
to the server that owns the hardware, and the methods block instead, which
is what an interactive prompt wants.

That symmetry is the point. Before this, the console had exactly five
verbs — read, write, connect, schema, status — so you could not write an
acquisition loop at it: no settle-wait, no staging, no actions. The loop
you can now type here,

    >>> apd = lp["fake_apd"]
    >>> stage = lp["mock_xyz_stage"]
    >>> apd.stage()
    >>> for x in np.linspace(0, 10, 51):
    ...     stage.move_abs(x=x)
    ...     print(x, apd.read_value())
    >>> apd.unstage()

is the same loop a template writes, with `await` in front of each call.

Or you can skip the loop: `lp.scan(...)` starts a real `ScanPlan` on the
server — the same plan a template builds, run by the same engine, with the
same pause and abort and the same automatic HDF5 save — and hands back a
`RunHandle`.

    >>> run = lp.scan(over={"stage.x": (0, 10, 51)}, read="apd")
    >>> run.wait().result()["data"]

The settle rule is not reimplemented here: `move_abs` polls with
`core.device.motion.is_settled` and that module's tolerance and poll
budget, so a move from the console and a move from a scan agree on when
the stage has arrived.

Instruments live in the server process, so this talks to it over the same
REST API the desktop app and web UI use — see `core/api_client.py`.

    >>> lp.instruments
    ['mock_xyz_stage_2', 'fake_apd_8', ...]
    >>> lp['fake_apd_8'].read()
    {'counts': 1023.4}
    >>> lp.workflows
    ['omniscan', ...]
    >>> wf = lp.workflow('641a113f-...')
    >>> wf.run(); wf.wait()
"""

from __future__ import annotations

import difflib
import functools
import os
import time
from typing import Any

from labpilot.core.api_client import LabPilotClient
from labpilot.core.device.motion import (
    DEFAULT_MAX_POLLS,
    DEFAULT_TOLERANCE,
    POLL_INTERVAL,
    is_settled,
    resolve_targets,
)
from labpilot.core.errors import UnsupportedOperationError

__all__ = [
    "Detector",
    "Instrument",
    "LabPilotSession",
    "Motor",
    "RunHandle",
    "Source",
    "WorkflowHandle",
]


class Instrument:
    """One instrument, addressed by id — the remote half of the same
    surface `core/device/kinds.py` gives a workflow template."""

    def __init__(self, client: LabPilotClient, instrument_id: str) -> None:
        self._client = client
        self.id = instrument_id

    # --- The contract every device has ------------------------------------

    def read(self) -> dict[str, Any]:
        """Current readable values. Raises if not connected — see connect()."""
        return self._client.read(self.id)

    def write(self, **values: Any) -> None:
        """Set one or more settable values, e.g. `.write(x=1.0, y=0.5)`.

        Validated against the device's own limits and choices before it
        reaches hardware; an illegal value comes back as an HTTP 422 whose
        message names the bound and the unit.
        """
        self._client.write(self.id, values)

    def connect(self) -> None:
        self._client.connect(self.id)

    def disconnect(self) -> None:
        self._client.disconnect(self.id)

    def stage(self) -> None:
        """Prepare for acquisition (arm the camera, allocate the buffer)."""
        self._client.stage(self.id)

    def unstage(self) -> None:
        """Release after acquisition."""
        self._client.unstage(self.id)

    def call(self, action: str, **arguments: Any) -> Any:
        """Invoke one of this device's declared `actions` — a state
        transition or command that isn't a parameter write.

            mw.call("cw_on")
            actual = counter.call("configure", bin_width_s=1e-9, gates=50)

        Arguments are keyword-only and validated against the action's
        declared parameters, so a typo or an out-of-range value is an error
        here rather than a driver exception later. Returns whatever the
        action reported.
        """
        return self._client.call_action(self.id, action, arguments or None)

    # --- Introspection ----------------------------------------------------

    @property
    def schema(self) -> dict[str, Any]:
        """This device's parameters, dtypes, units, limits and roles."""
        return self._client.get_schema(self.id)

    @property
    def status(self) -> dict[str, Any]:
        return self._client.get_instrument(self.id) or {}

    @property
    def connected(self) -> bool:
        return bool(self.status.get("connected"))

    @property
    def actions(self) -> list[str]:
        """The names of this device's callable actions."""
        schema = self.schema
        names = schema.get("action_names")
        if names is not None:
            return list(names)
        # An older backend, whose `actions` was a plain list of names.
        return [a if isinstance(a, str) else a.get("name", "") for a in schema.get("actions") or ()]

    @property
    def action_specs(self) -> list[dict[str, Any]]:
        """The full action records — declared arguments, their units and
        limits, and what the action reports back. `actions` is just the
        names."""
        return [a for a in self.schema.get("actions") or () if isinstance(a, dict)]

    @property
    def parameters(self) -> list[dict[str, Any]]:
        """The full `Parameter` records, including role, tags and choices —
        richer than the flat `schema["readable"]`/`["settable"]` views."""
        return list(self.schema.get("parameters") or ())

    def _parameter(self, name: str) -> dict[str, Any] | None:
        return next((p for p in self.parameters if p["name"] == name), None)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id!r}>"


class Motor(Instrument):
    """A `kind="motor"` device — one or more commandable axes."""

    @property
    def axes(self) -> list[str]:
        """The axes this device can actually be moved along — the
        parameters it declares `role="position"`, which excludes settings
        like velocity that happen to be readable and numeric."""
        return [p["name"] for p in self.parameters if p.get("role") == "position"]

    def get_position(self, axis: str | None = None) -> float | dict[str, float]:
        data = self.read()
        axes = self.axes
        if axis is not None:
            if axis not in axes:
                raise KeyError(f"{axis!r} is not an axis of {self.id} (axes: {axes})")
            return float(data[axis])
        if len(axes) == 1:
            return float(data[axes[0]])
        return {name: float(data[name]) for name in axes}

    def move_abs(self, *args: Any, tolerance: float = DEFAULT_TOLERANCE,
                 max_polls: int = DEFAULT_MAX_POLLS,
                 **kwargs: float) -> float | dict[str, float]:
        """Move to an absolute target and block until settled.

        Three equivalent forms: `move_abs(5.0)` (single-axis devices only),
        `move_abs("x", 5.0)`, or `move_abs(x=5.0, y=2.0)` — any subset of
        axes, moved together.
        """
        return self._move(args, kwargs, tolerance, max_polls)

    def move_rel(self, *args: Any, tolerance: float = DEFAULT_TOLERANCE,
                 max_polls: int = DEFAULT_MAX_POLLS,
                 **kwargs: float) -> float | dict[str, float]:
        """Same forms as `move_abs()`, but each value is a delta from the
        device's current position."""
        return self._move(args, kwargs, tolerance, max_polls, relative=True)

    def stop(self) -> None:
        """Stop where it is — what to reach for when a move is running long
        or a scan is going somewhere it should not."""
        self._client.stop(self.id)

    def _move(self, args: tuple, kwargs: dict, tolerance: float, max_polls: int,
              *, relative: bool = False) -> float | dict[str, float]:
        targets = resolve_targets(args, kwargs, self.axes, self.id)
        if relative:
            current = self.read()
            targets = {name: current[name] + delta for name, delta in targets.items()}

        self.write(**targets)
        for _ in range(max_polls):
            position = self.read()
            if is_settled(position, targets, tolerance):
                if len(targets) == 1:
                    return float(position[next(iter(targets))])
                return {name: float(position[name]) for name in targets}
            time.sleep(POLL_INTERVAL)
        raise RuntimeError(
            f"{self.id} did not reach {targets} after {max_polls} polls"
        )


class Detector(Instrument):
    """A `kind="detector"` or `kind="counter"` device."""

    def acquire_once(self) -> dict[str, Any]:
        """stage -> read -> unstage, for one single-shot reading. Not the
        right bracket around a whole averaged sweep that must stay staged
        across many reads — call stage()/unstage() around that yourself."""
        self.stage()
        try:
            return self.read()
        finally:
            self.unstage()

    def read_value(self, key: str | None = None) -> float:
        """One scalar reading. `key` defaults to the first readable
        parameter. Raises ValueError if that reading is an array — use
        `.read()` and index into it instead."""
        data = self.read()
        if key is None:
            readable = self.schema.get("readable") or {}
            if not readable:
                raise ValueError(f"{self.id} declares nothing readable")
            key = next(iter(readable))
        value = data[key]
        if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
            raise ValueError(
                f"{key!r} on {self.id} is not a scalar reading — use .read()"
            )
        return float(value)

    def set_integration_time(self, value: float) -> None:
        """Set however this device spells its integration time, in whatever
        unit it declares — the parameter it tags `integration_time`, which
        may be `integration_time_ms`, `exposure_time_ms`, ... Check
        `.schema["units"]` for which."""
        name = next(
            (p["name"] for p in self.parameters
             if "integration_time" in (p.get("tags") or ())),
            None,
        )
        if name is None:
            raise UnsupportedOperationError(
                f"{self.id} declares no integration-time parameter", device=self.id
            )
        self.write(**{name: value})


class Source(Instrument):
    """A `kind="source"` device.

    Deliberately thin beyond the common surface: a generic
    `enable()`/`disable()` does not hold up across real sources — some use
    a zero-argument action (`cw_on`, `off`), some a settable flag, some
    have no on/off concept at all. Use `.actions` and `.call(...)`, or
    `.write(...)` for a settable flag.
    """


_BY_KIND: dict[str, type[Instrument]] = {
    "motor": Motor,
    "detector": Detector,
    "counter": Detector,
    "source": Source,
}


class WorkflowHandle:
    """One workflow, bound to its id — see LabPilotSession.workflow()."""

    def __init__(self, client: LabPilotClient, workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    @property
    def params(self) -> dict[str, Any]:
        return self._client.get_workflow_params(self.id)

    def set_param(self, name: str, value: Any) -> Any:
        return self._client.set_workflow_param(self.id, name, value)

    @property
    def script(self) -> str | None:
        return self._client.get_workflow_script(self.id)

    def run(self) -> dict[str, Any]:
        """Starts execution and returns immediately — poll .state() or
        .wait() for progress/completion."""
        return self._client.execute_workflow(self.id)

    def stop(self) -> None:
        self._client.stop_workflow(self.id)

    def state(self) -> dict[str, Any]:
        """Live progress while running, plus the last completed run's
        status/results — see LabPilotClient.get_workflow_execution_state."""
        return self._client.get_workflow_execution_state(self.id)

    def wait(self, poll_interval: float = 0.5,
             timeout: float | None = None) -> dict[str, Any]:
        """Blocks until the current/most recent run stops running, then
        returns the final state. Convenient for a notebook cell that should
        finish only once the scan has (`wf.run(); wf.wait()`)."""
        start = time.monotonic()
        while True:
            state = self.state()
            if not state.get("running"):
                return state
            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError(f"Workflow {self.id} still running after {timeout}s")
            time.sleep(poll_interval)

    def __repr__(self) -> str:
        return f"<WorkflowHandle {self.id!r}>"


class RunHandle:
    """One running or finished scan — see `LabPilotSession.scan()`.

    The console half of `core/run/run.py`'s `Run`: the same three controls,
    the same progress, over REST. `pause()` and `abort()` mean here exactly
    what they mean there — a hold at the next point boundary, and a stop
    that keeps its points and stops the actuators — because they are the
    same object underneath, reached by id.
    """

    def __init__(self, client: LabPilotClient, run_id: str, name: str = "scan") -> None:
        self._client = client
        self.id = run_id
        self.name = name

    def state(self) -> dict[str, Any]:
        """{running, completed, total, paused, ...}."""
        return self._client.get_run_state(self.id)

    @property
    def running(self) -> bool:
        return bool(self.state().get("running"))

    @property
    def progress(self) -> tuple[int, int]:
        """(points measured, points planned)."""
        state = self.state()
        return int(state.get("completed") or 0), int(state.get("total") or 0)

    def pause(self) -> None:
        """Hold at the next point boundary. The detector is not left staged
        mid-integration and the stage is at a known position."""
        self._client.pause_run(self.id)

    def resume(self) -> None:
        self._client.resume_run(self.id)

    def abort(self) -> None:
        """Stop for good, keeping the points already measured.

        Not a cancellation: the run stops at its next point boundary, tells
        its actuators to stop, unstages the detector, and is saved as a
        partial run.
        """
        self._client.stop_run(self.id)

    stop = abort

    def wait(self, poll_interval: float = 0.2,
             timeout: float | None = None) -> RunHandle:
        """Block until the scan finishes, then return this handle.

        `lp.scan(...).wait().result()` is the whole synchronous form; the
        scan runs on the server either way, so a notebook cell that wants
        to plot at the end waits and one that wants to watch does not.
        """
        start = time.monotonic()
        while self.running:
            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError(f"Run {self.id} still running after {timeout}s")
            time.sleep(poll_interval)
        return self

    def result(self) -> Any:
        """What the scan measured, as a `Dataset`.

        A `Dataset` *is* the result dict — same keys, same values — with
        the axes, units and shape attached, so `result()["data"]` works
        exactly as it always did and `result().to_hdf5("scan.h5")` also
        does. While the scan is still running this is its latest frame,
        with the untaken points still None.

        Every run is already written to HDF5 and indexed as it finishes
        (`lp.runs`), so this is for looking at one now, not for keeping it.
        """
        from labpilot.core.data.dataset import Dataset, RunMeta

        payload = self._client.get_run_result(self.id)
        described = Dataset.from_result(
            payload, RunMeta(run_uid=self.id, plan_name=self.name)
        )
        # Keep the server's payload as the dict half rather than only the
        # arrays `from_result` recognised: `result()["shape"]` and the rest
        # of the flat convention are what an existing script reads, and a
        # partial run's untaken points stay None instead of becoming NaN
        # through a numpy round trip.
        return Dataset(described.arrays, described.meta, raw=payload)

    def __repr__(self) -> str:
        done, total = self.progress
        return f"<RunHandle {self.name!r} {done}/{total}>"


class LabPilotSession:
    """Entry point for interactive use — see the module docstring. Wraps a
    `LabPilotClient` with the kind-typed handles; use `.client` directly
    for anything not exposed here."""

    def __init__(self, base_url: str | None = None) -> None:
        base_url = base_url or os.environ.get("LABPILOT_URL", "http://localhost:8000")
        self.client = LabPilotClient(base_url)

    @property
    def base_url(self) -> str:
        return self.client.base_url

    @property
    def instruments(self) -> list[str]:
        """Every registered instrument's id."""
        return [inst["id"] for inst in self.client.list_instruments()]

    def __getitem__(self, instrument_id: str) -> Instrument:
        """The handle for one instrument, typed by its kind.

        Unknown ids are caught here rather than at the first call. A
        registered id carries a numeric suffix (`fake_apd_2`, not
        `fake_apd`), so asking for the adapter's name instead used to
        produce a bare 404 from whichever method you happened to call
        first, naming a URL rather than the mistake.
        """
        known = {inst["id"]: inst for inst in self.client.list_instruments()}
        instrument = known.get(instrument_id)
        if instrument is None:
            suggestions = difflib.get_close_matches(instrument_id, known, n=3, cutoff=0.4)
            hint = f" Did you mean {' or '.join(map(repr, suggestions))}?" if suggestions else ""
            raise KeyError(
                f"No instrument {instrument_id!r}.{hint} "
                f"See lp.instruments for all {len(known)}."
            )
        return _BY_KIND.get(instrument.get("kind", ""), Instrument)(
            self.client, instrument_id
        )

    def get(self, instrument_id: str) -> Instrument:
        """Alias for `lp[instrument_id]`, for symmetry with a template's
        `session.get(role)`."""
        return self[instrument_id]

    def context(self, **entries: Any) -> dict[str, Any]:
        """Record what is being measured, or read back what was recorded.

            lp.context(sample="NV-3", cooldown=7)   # set, merging
            lp.context()                            # read

        Every run started afterwards stamps this into its HDF5 attributes,
        alongside the instrument schemas and the software version. Nothing
        else in the framework can tell you which sample a file came from,
        and a file written without it can never be annotated retroactively
        — so this is worth setting at the start of a session, once.

        Merges rather than replaces; pass `None` to drop a key.
        """
        if not entries:
            return self.client.get_context()
        return self.client.set_context(entries)

    def scan(
        self,
        over: dict[str, tuple[float, float, int]],
        read: str | list[str],
        using: str | None = None,
        name: str = "scan",
        hold: dict[str, float] | None = None,
    ) -> RunHandle:
        """Run a scan, without writing a workflow first.

            >>> run = lp.scan(over={"stage.x": (0, 10, 51)}, read="apd")
            >>> run.wait().result()["data"][:3]

        `over` maps each swept axis to `(start, stop, points)`. Name the
        axis as `"<instrument>.<parameter>"`, or as a bare parameter with
        `using=` naming the instrument once for all of them. Axes vary in
        the order given, the first slowest — the convention every result
        view already reads.

        `hold` parks the other parameters of the first axis's instrument
        before the grid starts, e.g. `hold={"z": 1.0}` on an XYZ stage.

        This is the same `ScanPlan` a workflow template builds, run by the
        same engine on the same worker loop: it streams patches, it can be
        paused and aborted, and it is saved to HDF5 and indexed when it
        finishes. The difference is only that nobody wrote a workflow
        record for it.

        A convenience over `lp.execute(ScanPlan(...))`, and built on it, so
        the two cannot drift apart.

        Returns immediately with a `RunHandle`; call `.wait()` to block.
        """
        from labpilot.core.run.plans import ScanPlan, scan_axes

        detector = read[0] if isinstance(read, list) else read
        if isinstance(read, list) and len(read) != 1:
            raise ValueError(
                "A scan reads one detector — pass read='apd'. Reading several "
                "at once needs a workflow (see lp.workflows)."
            )
        return self.execute(
            ScanPlan(
                scan_axes(over, using), detector=detector, name=name, hold=hold or {}
            )
        )

    def execute(self, plan: Any) -> RunHandle:
        """Run a plan object, the way a template runs one.

        The same `ScanPlan` runs in both places, and the two lines differ
        only by the `await`:

            plan = ScanPlan([ScanAxis("x", "stage", 0, 10, 51)], detector="apd")

            await session.execute(plan)     # in a workflow template
            lp.execute(plan)                # at the console, in a notebook

        Instruments live in the server process, so the plan cannot be sent
        as an object; its fields are, and the server rebuilds it. That is
        the same boundary every other console call crosses — one API over
        two transports, not two APIs.

        Which plans can cross it is declared by the plans themselves
        (`core/run/requests.py`), so a new plan type becomes runnable from
        here by declaring its transport rather than by growing this method
        another branch.
        """
        from labpilot.core.run import plan_request

        name, params = plan_request(plan)
        run_id = self.client.start_run(name, params, getattr(plan, "name", name))
        return RunHandle(self.client, run_id, getattr(plan, "name", name))

    @property
    def pulse(self) -> Any:
        """The pulse-sequence generator library.

            >>> seq = lp.pulse.rabi(tau=(20e-9, 2e-6, 50))
            >>> seq.points, seq.readouts()

        Pure functions of numbers, so they run in this process — there is
        no hardware in a sequence. `lp.pulse.saved()` lists the ones
        already written to `~/.labpilot/sequences/`.
        """
        return _PulseLibrary()

    def pulsed(
        self,
        sequence: Any,
        pulser: str,
        counter: str,
        sweeps: int = 1000,
        channels: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> RunHandle:
        """Play a pulse sequence and accumulate the curve it measures.

            >>> seq = lp.pulse.rabi(tau=(20e-9, 2e-6, 50))
            >>> run = lp.pulsed(seq, pulser="pulse_streamer", counter="tt",
            ...                 sweeps=2000)
            >>> run.wait().result().to_hdf5("rabi.h5")

        `sequence` is a `PulseSequence` or the name of a saved one.
        `channels` maps its symbolic channels onto this rig's physical
        ones — the one genuinely rig-specific thing, which is why it lives
        with the run and not in the saved file.

        The same `PulsedMeasurementPlan` a workflow builds, run by the
        same engine: it streams, pauses, aborts and saves to HDF5 with
        real coordinates.
        """
        from labpilot.core.pulse import load_sequence
        from labpilot.core.run import PulsedMeasurementPlan

        return self.execute(
            PulsedMeasurementPlan(
                sequence=load_sequence(sequence) if isinstance(sequence, str) else sequence,
                pulser=pulser, counter=counter, sweeps=int(sweeps),
                channels=dict(channels or {}), **kwargs,
            )
        )

    def run(self, run_id: str) -> RunHandle:
        """A handle on a run already in flight — including one started from
        the Workflows tab, whose id is its workflow id."""
        return RunHandle(self.client, run_id)

    @property
    def runs(self) -> list[dict[str, Any]]:
        """Every saved run, newest first — the provenance index every run
        is written into as it finishes."""
        return self.client.list_runs()

    @property
    def workflows(self) -> list[str]:
        """Every loaded workflow's id."""
        return [wf["id"] for wf in self.client.list_workflows()]

    def workflow(self, workflow_id: str) -> WorkflowHandle:
        return WorkflowHandle(self.client, workflow_id)

    def __repr__(self) -> str:
        return f"<LabPilotSession {self.base_url!r}>"


class _PulseLibrary:
    """`lp.pulse` — the sequence generators, called like ordinary functions.

    A sequence is pure data: no hardware, no connection, no server. So
    these run in *this* process, unlike everything else on `lp`, and the
    result is an object you can inspect, edit and save before any pulser
    exists to play it.

        >>> seq = lp.pulse.rabi(tau=(20e-9, 2e-6, 50), rabi_period=180e-9)
        >>> seq.duration, seq.readouts()

    `tau=(start, stop, points)` is sugar over whichever pair of parameters
    the generator actually declares — a linear sweep takes a step and a
    log-spaced one takes an endpoint, and neither should be something a
    caller has to remember at the console.

    Anything the rig profile declares (`rabi_period`, `laser_length`,
    `mw_channel`, ...) can be passed alongside; it is split out and used
    to build the profile. Physics and generator settings read as one
    argument list because at a console that is what they are.
    """

    def __dir__(self) -> list[str]:
        from labpilot.core.pulse.library import GENERATORS

        return [*sorted(GENERATORS), "load", "saved"]

    def __repr__(self) -> str:
        from labpilot.core.pulse.library import GENERATORS

        return f"<lp.pulse: {', '.join(sorted(GENERATORS))}>"

    def __getattr__(self, name: str) -> Any:
        from labpilot.core.pulse.library import GENERATORS

        if name not in GENERATORS:
            raise AttributeError(
                f"No pulse generator {name!r} — lp.pulse offers "
                f"{', '.join(sorted(GENERATORS))}."
            )
        return functools.partial(self._build, name)

    @staticmethod
    def _build(generator: str, tau: tuple[float, float, int] | None = None, **kwargs: Any) -> Any:
        import dataclasses

        from labpilot.core.pulse.library import RigProfile, build, generator_parameters

        rig_fields = {f.name for f in dataclasses.fields(RigProfile)}
        profile = {k: kwargs.pop(k) for k in list(kwargs) if k in rig_fields}

        if tau is not None:
            try:
                start, stop, points = tau
            except (TypeError, ValueError):
                raise ValueError(
                    f"tau needs (start, stop, points), got {tau!r}"
                ) from None
            declared = {p.name for p in generator_parameters(generator)}
            kwargs["points"] = int(points)
            kwargs["tau_start"] = float(start)
            if "tau_stop" in declared:
                kwargs["tau_stop"] = float(stop)
            else:
                kwargs["tau_step"] = (float(stop) - float(start)) / max(int(points) - 1, 1)

        return build(generator, RigProfile(**profile), **kwargs)

    @staticmethod
    def saved() -> list[str]:
        """Every sequence written to `~/.labpilot/sequences/`."""
        from labpilot.core.pulse import list_sequences

        return [entry.name for entry in list_sequences()]

    @staticmethod
    def load(name: str) -> Any:
        """One of them, by name."""
        from labpilot.core.pulse import load_sequence

        return load_sequence(name)
