"""The SPAD512, against a stand-in for Pi Imaging's own library.

Three things this adapter is responsible for, and all three are the kind
of mistake that yields a plausible image rather than an error:

- **The integration time's unit depends on the bit depth.** Their library
  takes `intTime` in milliseconds at 6 bits and above and in
  *microseconds* at 1 and 4. The same number is therefore a thousandfold
  different exposure depending on another setting.
- **Iterations are summed, not averaged.** Summing is what keeps the
  result Poisson-distributed, which is what every error bar downstream is
  computed from.
- **Their constructor does not raise on a refused connection.** It
  returns `None` from `__init__`, leaving a half-built object whose first
  real call fails somewhere unhelpful.

Everything about the wire — framing, reshape order, 16-bit byte
interleaving — is their library's and is deliberately not retested here;
wrapping it rather than the protocol is the whole point.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.device.parameter import INTEGRATION_TIME
from labpilot.core.errors import ChoiceError, DeviceError
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.PiImaging.spad512 import (
    BIT_DEPTHS,
    IMAGE_WIDTHS,
    SENSOR_ROWS,
    SPAD512Adapter,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Socket:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _FakeSPAD512S:
    """Pi Imaging's class, as far as this adapter uses it.

    The signatures are the contract relied on:
    `get_intensity(iterations, intTime, bitDepth, overlap, timeout, pileup,
    im_width)` returning `(rows, width, iterations)`.
    """

    #: Set by the test to simulate their "connection refused" behaviour,
    #: which leaves `detType` unset rather than raising.
    answer = True

    def __init__(self, port: int) -> None:
        self.port = port
        self.t = _Socket()
        self.calls: list[tuple] = []
        self.calibrations = 0
        self.cooling: list[int] = []
        if not type(self).answer:
            return
        self.detType = "SPAD512S"

    def get_info(self) -> list[str]:
        return ["MSTR-1", "SLV-2", "sw 1.2", "fw 3.4", "hw 5", "flavour", "1", "1", "0"]

    def get_temps(self):
        return ("41.5", "39.0", "33.2", "12.8")

    def get_freq(self):
        return ("20000000", "100")

    def get_intensity(
        self,
        iterations,
        intTime,  # noqa: N803 - Pi Imaging's own parameter name
        bitDepth,  # noqa: N803
        overlap,
        timeout,
        pileup,
        im_width,
    ):
        self.calls.append(
            (iterations, intTime, bitDepth, overlap, timeout, pileup, im_width)
        )
        # One count per pixel per iteration, so a sum is distinguishable
        # from a mean by inspection.
        return np.ones((SENSOR_ROWS, im_width, iterations))

    def calib_noise(self):
        self.calibrations += 1

    def enable_cooling(self, enable):
        self.cooling.append(int(enable))


@pytest.fixture
def library(monkeypatch):
    _FakeSPAD512S.answer = True
    monkeypatch.setattr(SPAD512Adapter, "_import", lambda self: _FakeSPAD512S)
    return _FakeSPAD512S


async def _connected(library, **kwargs) -> SPAD512Adapter:
    adapter = SPAD512Adapter(port=63110, **kwargs)
    await adapter.connect()
    return adapter


# --- Describing itself ------------------------------------------------------


def test_it_is_registered_and_catalogued():
    assert "spad512" in adapter_registry.list()
    assert any(m.adapter_key == "spad512" for m in INSTRUMENT_CATALOG)


def test_it_describes_itself_without_their_library():
    schema = SPAD512Adapter.describe()
    assert schema is not None
    assert schema.kind == "detector"
    assert schema.dimensionality == 2


def test_the_integration_time_is_findable_by_tag():
    """Which is what spares every downstream layer from guessing which
    settable is the exposure."""
    parameter = SPAD512Adapter.describe().integration_time
    assert parameter is not None
    assert parameter.name == "integration_time_ms"
    assert INTEGRATION_TIME in parameter.tags


def test_only_the_bit_depths_and_widths_the_camera_has_are_offered():
    schema = SPAD512Adapter.describe()
    assert schema.require("bit_depth").choices == BIT_DEPTHS
    assert schema.require("image_width").choices == IMAGE_WIDTHS


# --- Connecting -------------------------------------------------------------


async def test_a_port_is_required_and_the_message_says_why(library):
    """There is no safe default: a wrong port connects to whatever else is
    listening on this machine."""
    with pytest.raises(DeviceError, match="no safe default"):
        await SPAD512Adapter().connect()


async def test_a_refused_connection_is_caught_despite_their_constructor(library):
    """Their `__init__` returns `None` on a refused connection rather than
    raising, leaving a half-built object. The handshake is what gets
    checked, not the call."""
    library.answer = False
    with pytest.raises(DeviceError, match="has to be running"):
        await SPAD512Adapter(port=63110).connect()


async def test_connecting_records_what_their_software_reports(library):
    adapter = await _connected(library)
    try:
        reading = await adapter.read()
        assert reading["detector_type"] == "SPAD512S"
        assert "MSTR-1" in reading["system_info"]
    finally:
        await adapter.disconnect()


async def test_disconnecting_closes_the_socket(library):
    adapter = await _connected(library)
    camera = adapter._camera
    await adapter.disconnect()
    assert camera.t.closed == 1
    with pytest.raises(DeviceError, match="not connected"):
        adapter._read_sync()


# --- Acquiring --------------------------------------------------------------


async def test_a_frame_is_the_sum_over_iterations(library):
    """Not the mean: summing is what keeps the result Poisson, which is
    what every error bar downstream is computed from."""
    adapter = await _connected(library, iterations=5, image_width=64)
    try:
        frame = (await adapter.read())["frame"]
        assert frame.shape == (SENSOR_ROWS, 64)
        assert frame[0, 0] == 5.0
    finally:
        await adapter.disconnect()


async def test_the_settings_reach_their_library_in_order(library):
    adapter = await _connected(
        library, iterations=3, bit_depth=10, image_width=128,
        pileup_correction=False, overlap=True,
    )
    try:
        await adapter.read()
        iterations, _time, depth, overlap, _timeout, pileup, width = (
            adapter._camera.calls[-1]
        )
        assert (iterations, depth, width) == (3, 10, 128)
        assert (overlap, pileup) == (1, 0)
    finally:
        await adapter.disconnect()


@pytest.mark.parametrize(
    ("depth", "expected"),
    [(8, 10.0), (12, 10.0), (6, 10.0), (1, 10_000.0), (4, 10_000.0)],
)
async def test_the_integration_time_is_converted_for_the_bit_depth(
    library, depth, expected
):
    """Their library takes milliseconds at 6 bits and above and
    microseconds at 1 and 4. A 10 ms run must be 10 ms at every depth."""
    adapter = await _connected(library, bit_depth=depth, integration_time_ms=10.0)
    try:
        await adapter.read()
        assert adapter._camera.calls[-1][1] == pytest.approx(expected)
    finally:
        await adapter.disconnect()


async def test_settings_can_be_changed_at_runtime(library):
    adapter = await _connected(library)
    try:
        await adapter.write({"integration_time_ms": 2.5, "bit_depth": 12})
        await adapter.read()
        assert adapter._camera.calls[-1][1] == pytest.approx(2.5)
        assert adapter._camera.calls[-1][2] == 12
    finally:
        await adapter.disconnect()


async def test_a_bit_depth_the_camera_does_not_have_is_refused(library):
    adapter = await _connected(library)
    try:
        with pytest.raises(ChoiceError):
            adapter.validate_write({"bit_depth": 5})
    finally:
        await adapter.disconnect()


async def test_an_image_width_the_camera_does_not_have_is_refused(library):
    adapter = await _connected(library)
    try:
        with pytest.raises(ChoiceError):
            adapter.validate_write({"image_width": 100})
    finally:
        await adapter.disconnect()


async def test_fewer_than_one_iteration_is_brought_up_to_one(library):
    adapter = await _connected(library)
    try:
        await adapter.set_iterations(0)
        await adapter.read()
        assert adapter._camera.calls[-1][0] == 1
    finally:
        await adapter.disconnect()


# --- First-light diagnosis --------------------------------------------------


async def test_the_four_temperatures_come_back_as_numbers(library):
    """Their library returns them as strings, which plot as nothing and
    compare as text."""
    adapter = await _connected(library)
    try:
        reading = await adapter.read()
        assert reading["temperature_chip"] == pytest.approx(12.8)
        assert reading["temperature_master"] == pytest.approx(41.5)
        assert isinstance(reading["temperature_pcb"], float)
    finally:
        await adapter.disconnect()


async def test_the_laser_clock_is_reported(library):
    """Zero here means the laser's sync is not reaching the camera, which
    is the first thing to check before anything else."""
    adapter = await _connected(library)
    try:
        reading = await adapter.read()
        assert reading["laser_clock"] == pytest.approx(20e6)
        assert reading["frame_clock"] == pytest.approx(100.0)
    finally:
        await adapter.disconnect()


async def test_unparsable_temperatures_do_not_fail_the_frame(library):
    """A camera that cannot report one temperature can still take an
    image, and an image is what was asked for."""
    adapter = await _connected(library)
    try:
        adapter._camera.get_temps = lambda: ("--", "n/a")
        reading = await adapter.read()
        assert reading["temperature_master"] == 0.0
        assert reading["frame"].shape[0] == SENSOR_ROWS
    finally:
        await adapter.disconnect()


# --- Actions ----------------------------------------------------------------


async def test_hot_pixel_calibration_is_offered(library):
    adapter = await _connected(library)
    try:
        await adapter.calibrate_hot_pixels()
        assert adapter._camera.calibrations == 1
    finally:
        await adapter.disconnect()


async def test_cooling_can_be_switched(library):
    adapter = await _connected(library)
    try:
        await adapter.enable_cooling()
        await adapter.disable_cooling()
        assert adapter._camera.cooling == [1, 0]
    finally:
        await adapter.disconnect()


async def test_an_unexpected_array_rank_is_refused(library):
    """Rather than reshaped into something that looks like an image."""
    adapter = await _connected(library)
    try:
        adapter._camera.get_intensity = lambda *a: np.ones((2, 2, 2, 2))
        with pytest.raises(DeviceError, match="4-D array"):
            await adapter.read()
    finally:
        await adapter.disconnect()
