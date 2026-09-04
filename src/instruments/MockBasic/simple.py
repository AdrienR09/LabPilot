"""One minimal mock instrument per InstrumentType.

Distinct from `instruments/mock/` (36 devices covering many instrument
families for realistic testing). This is the deliberately small set — one
adapter per `catalog.InstrumentType` bucket — used as the dashboard's
starter/demo seed and for quick smoke-testing UI generation per type,
without pulling in the full mock library.

Each adapter simulates realistic instrument behavior rather than returning
static/independent-random numbers: detectors drift and add noise that scales
with their config knobs (averaging/integration/exposure), actuators take
real time to move (a background thread advances position toward the last
commanded target at a configurable velocity, matching how a real motion
controller's position loop behaves), and sources apply their compliance
limit to the commanded output.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Optional

import numpy as np

from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema

# A "true" peak position per axis name, deliberately inside the default
# AXIS_RANGES every omniscan-family template declares (e.g. x/y in
# (-4, 4), z in (-2, 2)) — so a scan or optimizer run against these mocks
# with no configuration changes at all lands on a real, findable feature
# instead of needing the user to already know where to look.
_DEFAULT_PEAK_POSITION = {"x": 1.5, "y": -0.8, "z": 0.4}
_DEFAULT_PEAK_FALLBACK = 0.5  # any other axis name


class _SimulatedSample:
    """Shared ground-truth position for a coupled mock actuator+detector
    pair — a fixed peak that a detector's simulated signal genuinely
    depends on, rather than drifting with wall-clock time independent of
    where the actuator actually is (the previous behavior: `_read_sync`
    used to vary its blob center as a function of `time.monotonic()`
    alone, so any scan or optimizer run against it was really fitting
    noise, not a real spatial feature — "update that kind of fake
    instrument so they generate fake data that can be reliable for
    testing all the optimizer settings").

    Every `MockBasic*` actuator writes its current position here
    (`update_position`) each time it moves; every `MockBasic*` detector
    reads `distance_sq()` from here to scale its own signal. Keyed by
    `sample` (a constructor param on every adapter below, default
    `"default"`) so the common case — one actuator + one detector, the
    dashboard's own starter/demo instruments — is coupled automatically
    with no configuration, while still allowing independent simulated
    pairs in the same session if ever needed (a different `sample` name
    per pair).
    """

    _registry: dict[str, "_SimulatedSample"] = {}

    def __init__(self) -> None:
        self.peak: dict[str, float] = {}
        self.position: dict[str, float] = {}

    @classmethod
    def get(cls, sample: str, axes: tuple[str, ...]) -> "_SimulatedSample":
        instance = cls._registry.setdefault(sample, cls())
        for axis in axes:
            instance.peak.setdefault(axis, _DEFAULT_PEAK_POSITION.get(axis, _DEFAULT_PEAK_FALLBACK))
            instance.position.setdefault(axis, 0.0)
        return instance

    def update_position(self, position: dict[str, float]) -> None:
        self.position.update(position)

    def distance_sq(self, axes: Optional[tuple[str, ...]] = None) -> float:
        keys = axes if axes is not None else tuple(self.peak.keys())
        return sum((self.position.get(a, 0.0) - self.peak.get(a, 0.0)) ** 2 for a in keys)


class MockBasicDetector0D(AdapterBase):
    """Single scalar reading (e.g. power meter, photodiode) — genuinely
    peaks at the paired actuator's own true position (`_SimulatedSample`,
    see module docstring), not just wall-clock time."""

    def __init__(self, name: str = "mock_basic_detector_0d", sample: str = "default") -> None:
        super().__init__()
        self._name = name
        self._averaging = 1.0
        self._start_time = time.monotonic()
        self._sample_name = sample

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"value": "float64"},
            settable={"averaging": "float64"},
            units={"value": "a.u.", "averaging": "samples"},
            limits={"averaging": (1.0, 100.0)},
            tags=["MockBasic", "detector_0d"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        sample = _SimulatedSample.get(self._sample_name, ())
        peak_width = 1.5
        signal = math.exp(-sample.distance_sq() / (2 * peak_width**2))
        noise = 0.05 / math.sqrt(max(self._averaging, 1.0))
        value = 1.0 * signal + np.random.normal(0, noise)
        return {"value": float(value)}

    async def write(self, values: dict[str, Any]) -> None:
        if "averaging" in values:
            self._averaging = max(1.0, float(values["averaging"]))


class MockBasicDetector1D(AdapterBase):
    """1D array reading (e.g. spectrometer, oscilloscope trace) — overall
    amplitude genuinely peaks at the paired actuator's true position
    (`_SimulatedSample`); the trace's own internal spectral shape/center
    stays fixed, a separate, detector-internal concept from the actuator's
    axes (see omniscan.py's own actuator-vs-detector-axis distinction)."""

    def __init__(self, name: str = "mock_basic_detector_1d", sample: str = "default") -> None:
        super().__init__()
        self._name = name
        self._n = 256
        self._integration_time_ms = 100.0
        self._start_time = time.monotonic()
        self._sample_name = sample

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"trace": "ndarray1d"},
            settable={"integration_time_ms": "float64"},
            units={"trace": "a.u.", "integration_time_ms": "ms"},
            limits={"integration_time_ms": (1.0, 5000.0)},
            tags=["MockBasic", "detector_1d"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        sample = _SimulatedSample.get(self._sample_name, ())
        peak_width = 1.5
        signal_scale = math.exp(-sample.distance_sq() / (2 * peak_width**2))
        x = np.linspace(0, 10, self._n)
        center = 5.0
        noise = 0.05 / math.sqrt(max(self._integration_time_ms, 1.0) / 100.0)
        trace = signal_scale * np.exp(-((x - center) ** 2) / 2) + np.random.normal(0, noise, self._n)
        return {"trace": trace}

    async def write(self, values: dict[str, Any]) -> None:
        if "integration_time_ms" in values:
            self._integration_time_ms = max(1.0, float(values["integration_time_ms"]))


class MockBasicDetector2D(AdapterBase):
    """2D image reading (e.g. camera) — overall blob brightness genuinely
    peaks at the paired actuator's true position (`_SimulatedSample`);
    the blob's own pixel position within the frame stays fixed, a
    separate, detector-internal concept from the actuator's axes."""

    def __init__(self, name: str = "mock_basic_detector_2d", sample: str = "default") -> None:
        super().__init__()
        self._name = name
        self._shape = (64, 64)
        self._exposure_ms = 50.0
        self._gain = 1.0
        self._start_time = time.monotonic()
        self._sample_name = sample

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"image": "ndarray2d"},
            settable={"exposure_ms": "float64", "gain": "float64"},
            units={"image": "counts", "exposure_ms": "ms", "gain": "x"},
            limits={"exposure_ms": (1.0, 5000.0), "gain": (1.0, 10.0)},
            tags=["MockBasic", "detector_2d"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        sample = _SimulatedSample.get(self._sample_name, ())
        peak_width = 1.5
        signal_scale = math.exp(-sample.distance_sq() / (2 * peak_width**2))
        h, w = self._shape
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = w / 2, h / 2
        blob = 80 * self._gain * signal_scale * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 8.0**2))
        base = np.random.poisson(max(self._exposure_ms / 10.0, 1.0), self._shape).astype("float64")
        return {"image": base + blob}

    async def write(self, values: dict[str, Any]) -> None:
        if "exposure_ms" in values:
            self._exposure_ms = max(1.0, float(values["exposure_ms"]))
        if "gain" in values:
            self._gain = max(1.0, float(values["gain"]))


class MockBasicDetectorND(AdapterBase):
    """3D hyperspectral cube reading (x, y, spectral) — e.g. a
    hyperspectral imaging camera or a scanning spectrometer stack.
    Overall cube intensity genuinely peaks at the paired actuator's true
    position (`_SimulatedSample`) — the cube's own internal spatial/
    spectral pattern (its row/col/wavelength axes) stays fixed, a
    separate, detector-internal concept from whatever real actuator axes
    (e.g. x/y/z) it's being scanned against (see omniscan.py's own
    actuator-axis-vs-detector-axis distinction: this cube's row/col are
    NOT the same "x"/"y" as the actuator's, even though they share
    letters conceptually)."""

    def __init__(self, name: str = "mock_basic_detector_nd", sample: str = "default") -> None:
        super().__init__()
        self._name = name
        self._shape = (32, 32, 64)  # (ny, nx, n_wavelengths)
        self._integration_time_ms = 50.0
        self._start_time = time.monotonic()
        self._sample_name = sample

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"cube": "ndarray3d"},
            settable={"integration_time_ms": "float64"},
            units={"cube": "counts", "integration_time_ms": "ms"},
            limits={"integration_time_ms": (1.0, 5000.0)},
            tags=["MockBasic", "detector_nd"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        sample = _SimulatedSample.get(self._sample_name, ())
        peak_width = 1.5
        signal_scale = math.exp(-sample.distance_sq() / (2 * peak_width**2))
        ny, nx, nw = self._shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        cx, cy = nx / 2, ny / 2
        spatial = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 6.0**2))
        wavelengths = np.linspace(0, 10, nw)
        spectral = np.exp(-((wavelengths - 5.0) ** 2) / (2 * 0.5**2))
        cube = spatial[:, :, None] * spectral[None, None, :] * 1000 * signal_scale
        noise = np.random.poisson(max(self._integration_time_ms / 10.0, 1.0), cube.shape).astype("float64")
        return {"cube": cube + noise}

    async def write(self, values: dict[str, Any]) -> None:
        if "integration_time_ms" in values:
            self._integration_time_ms = max(1.0, float(values["integration_time_ms"]))


class MockBasicActuator0D(AdapterBase):
    """Binary on/off control (e.g. shutter, relay)."""

    def __init__(self, name: str = "mock_basic_actuator_0d") -> None:
        super().__init__()
        self._name = name
        self._state = False

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"state": "bool"},
            settable={"state": "bool"},
            units={},
            tags=["MockBasic", "actuator_0d"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"state": self._state}

    async def write(self, values: dict[str, Any]) -> None:
        if "state" in values:
            self._state = bool(values["state"])


class _MovingAxisMixin:
    """Shared background position loop for actuators that take real time to move.

    A daemon thread advances position(s) toward the last commanded target at
    `self._velocity` units/s, started on connect and stopped on disconnect —
    the same continuously-serviced-position-loop model a real motion
    controller uses, so read() during a move reflects genuine in-transit
    values instead of jumping straight to the setpoint.
    """

    _velocity: float
    _running: bool
    _thread: threading.Thread | None

    def _start_mover(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._move_loop, daemon=True)
        self._thread.start()

    def _stop_mover(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _move_loop(self) -> None:
        dt = 0.05
        while self._running:
            self._step(dt)
            time.sleep(dt)

    def _step(self, dt: float) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class MockBasicActuator1D(_MovingAxisMixin, AdapterBase):
    """Single-axis position control (e.g. linear stage) — writes its
    current position into the shared `_SimulatedSample` on every step, so
    a paired `MockBasic*` detector's signal genuinely depends on it.

    `instant=True` skips the background mover thread's gradual approach
    entirely — `write()` snaps straight to the target (and the shared
    `_SimulatedSample` is updated synchronously), so a caller's very next
    `read()` (even with zero wait) already reports the commanded
    position. For a per-point scan loop (`move_and_settle`,
    `core/workflow_templates/_common.py`) built on the ordinary
    real-time-motion behavior, this removes that per-point wait
    entirely — the option a timing test isolates the "is it the
    simulated motion, or something else" question needs (see
    `core/workflow_templates/omniscan.py`'s own timing investigation).
    Default False preserves the existing realistic-motion demo
    behavior for everyone else."""

    def __init__(
        self, name: str = "mock_basic_actuator_1d", sample: str = "default", instant: bool = False,
    ) -> None:
        super().__init__()
        self._name = name
        self._position = 0.0
        self._target = 0.0
        self._velocity = 10.0  # mm/s
        self._running = False
        self._thread: threading.Thread | None = None
        self._sample = _SimulatedSample.get(sample, ("position",))
        self._instant = instant

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"position": "float64"},
            settable={"position": "float64", "velocity": "float64"},
            units={"position": "mm", "velocity": "mm/s"},
            limits={"position": (-50.0, 50.0), "velocity": (0.1, 100.0)},
            tags=["MockBasic", "actuator_1d"],
        )

    def _connect_sync(self) -> None:
        self._start_mover()

    def _disconnect_sync(self) -> None:
        self._stop_mover()

    def _step(self, dt: float) -> None:
        delta = self._target - self._position
        step = self._velocity * dt
        self._position = self._target if abs(delta) <= step else self._position + math.copysign(step, delta)
        self._sample.update_position({"position": self._position})

    def _read_sync(self) -> dict[str, Any]:
        return {"position": float(self._position + np.random.normal(0, 0.005))}

    async def write(self, values: dict[str, Any]) -> None:
        if "velocity" in values:
            self._velocity = max(0.1, float(values["velocity"]))
        if "position" in values:
            target = float(values["position"])
            lo, hi = self.schema.limits["position"]
            if not (lo <= target <= hi):
                raise ValueError(f"position {target} out of range [{lo}, {hi}]")
            self._target = target
            if self._instant:
                self._position = target
                self._sample.update_position({"position": self._position})


class MockBasicActuatorND(_MovingAxisMixin, AdapterBase):
    """Multi-axis position control (e.g. XY/XYZ stage) — writes its
    current position into the shared `_SimulatedSample` on every step, so
    a paired `MockBasic*` detector's signal genuinely depends on it.

    `instant=True` — see `MockBasicActuator1D`'s docstring; same
    bypass-the-mover-thread behavior, all axes at once."""

    AXES = ("x", "y", "z")

    def __init__(
        self, name: str = "mock_basic_actuator_nd", sample: str = "default", instant: bool = False,
    ) -> None:
        super().__init__()
        self._name = name
        self._position = {axis: 0.0 for axis in self.AXES}
        self._target = {axis: 0.0 for axis in self.AXES}
        self._velocity = 10.0  # units/s, shared across axes
        self._running = False
        self._thread: threading.Thread | None = None
        self._sample = _SimulatedSample.get(sample, self.AXES)
        self._instant = instant

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={axis: "float64" for axis in self.AXES},
            settable={**{axis: "float64" for axis in self.AXES}, "velocity": "float64"},
            units={**{axis: "mm" for axis in self.AXES}, "velocity": "mm/s"},
            limits={
                **{axis: (-50.0, 50.0) for axis in self.AXES},
                "velocity": (0.1, 100.0),
            },
            tags=["MockBasic", "actuator_nd"],
        )

    def _connect_sync(self) -> None:
        self._start_mover()

    def _disconnect_sync(self) -> None:
        self._stop_mover()

    def _step(self, dt: float) -> None:
        step = self._velocity * dt
        for axis in self.AXES:
            delta = self._target[axis] - self._position[axis]
            self._position[axis] = (
                self._target[axis] if abs(delta) <= step else self._position[axis] + math.copysign(step, delta)
            )
        self._sample.update_position(self._position)

    def _read_sync(self) -> dict[str, Any]:
        return {axis: float(self._position[axis] + np.random.normal(0, 0.005)) for axis in self.AXES}

    async def write(self, values: dict[str, Any]) -> None:
        if "velocity" in values:
            self._velocity = max(0.1, float(values["velocity"]))
        lo, hi = -50.0, 50.0
        for axis in self.AXES:
            if axis in values:
                target = float(values[axis])
                if not (lo <= target <= hi):
                    raise ValueError(f"{axis} {target} out of range [{lo}, {hi}]")
                self._target[axis] = target
                if self._instant:
                    self._position[axis] = target
        if self._instant:
            self._sample.update_position(self._position)


class MockBasicSource(AdapterBase):
    """Signal/output source (e.g. laser, voltage source)."""

    def __init__(self, name: str = "mock_basic_source") -> None:
        super().__init__()
        self._name = name
        self._output = 0.0
        self._compliance_limit = 10.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"output": "float64"},
            settable={"output": "float64", "compliance_limit": "float64"},
            units={"output": "V", "compliance_limit": "V"},
            limits={"output": (0.0, 10.0), "compliance_limit": (0.0, 10.0)},
            tags=["MockBasic", "source"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        # Small ripple, like a real supply's output noise.
        return {"output": float(self._output + np.random.normal(0, 0.002))}

    async def write(self, values: dict[str, Any]) -> None:
        if "compliance_limit" in values:
            self._compliance_limit = max(0.0, float(values["compliance_limit"]))
        if "output" in values:
            target = float(values["output"])
            lo, hi = self.schema.limits["output"]
            if not (lo <= target <= hi):
                raise ValueError(f"output {target} out of range [{lo}, {hi}]")
            self._output = min(target, self._compliance_limit)


adapter_registry.register("mock_basic_detector_0d", MockBasicDetector0D)
adapter_registry.register("mock_basic_detector_1d", MockBasicDetector1D)
adapter_registry.register("mock_basic_detector_2d", MockBasicDetector2D)
adapter_registry.register("mock_basic_detector_nd", MockBasicDetectorND)
adapter_registry.register("mock_basic_actuator_0d", MockBasicActuator0D)
adapter_registry.register("mock_basic_actuator_1d", MockBasicActuator1D)
adapter_registry.register("mock_basic_actuator_nd", MockBasicActuatorND)
adapter_registry.register("mock_basic_source", MockBasicSource)
