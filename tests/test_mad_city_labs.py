"""The Mad City Labs stages, against stand-ins for MCL's two libraries.

The Nano-Drive is short because its model and the framework's are the same
model: absolute microns, closed-loop, read back from the stage's own
sensor. The Micro-Drive is not, and that difference is what most of these
tests are about — `MCL_MDMove` moves a *distance*, so every absolute move
is read-encoder, compute-delta, move, wait, and a stepper that stalled or
was nudged by hand is somewhere nothing in this process remembers.

Two things here would be plausible-looking bugs rather than errors, so
they are pinned explicitly: the axis numbering is 1-based (a 0-based call
moves the wrong axis or none), and `MCL_MDStatus`'s limit bits are active
*low* (reading them the obvious way round reports every axis as
permanently jammed).

MCL's libraries ship with their driver installation, not from PyPI, and
there is no stage on this machine — so what the stand-ins assume about the
API is written into them, and if MCL ever change it these tests keep
passing and the adapters break. That is the one failure mode a stand-in
cannot cover, and why both module docstrings say they have not been run
against hardware.
"""

from __future__ import annotations

import ctypes

import pytest

from labpilot.core.errors import DeviceError, LimitError
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.MadCityLabs._madlib import (
    AXIS_NUMBERS,
    ProductInformation,
    describe_code,
)
from labpilot.instruments.MadCityLabs.micro_drive import (
    DEFAULT_TRAVEL_MM,
    MicroDriveAdapter,
    limits_reached,
)
from labpilot.instruments.MadCityLabs.nano_drive import NanoDriveAdapter

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- Shared plumbing --------------------------------------------------------


def test_axes_are_one_based():
    """A 0-based call moves the wrong axis, or none, and reports success."""
    assert AXIS_NUMBERS == {"x": 1, "y": 2, "z": 3}


def test_the_product_struct_is_packed():
    """A `c_ubyte` followed by five `c_short`s is padded by default, which
    leaves the axis bitmap right and every later field one byte late."""
    assert ctypes.sizeof(ProductInformation) == 1 + 5 * 2


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        (-3, "powered on"),
        (-7, "does not exist on this stage"),
        (-8, "stale"),
        (-1, "MCL_GENERAL_ERROR"),
    ],
)
def test_an_error_code_explains_itself(code, fragment):
    assert fragment in describe_code(code)


@pytest.mark.parametrize(
    ("bitmap", "axes"),
    [
        (0b111, ("x", "y", "z")),
        (0b011, ("x", "y")),
        (0b100, ("z",)),
        (0b000, ()),
    ],
)
def test_the_axis_bitmap_says_which_axes_exist(bitmap, axes):
    info = ProductInformation()
    info.axis_bitmap = bitmap
    assert info.axes() == axes


# --- The Nano-Drive ---------------------------------------------------------


class _FakeMadlib:
    """`Madlib.dll`'s calls, and the contract relied on.

    Positions are absolute microns; `MCL_SingleReadN` and
    `MCL_GetCalibration` return doubles, where a negative value is an
    error code rather than a position.
    """

    def __init__(self, bitmap: int = 0b111, travel: float = 100.0) -> None:
        self.bitmap = bitmap
        self.travel = travel
        self.positions = {1: 0.0, 2: 0.0, 3: 0.0}
        self.handles = 0
        self.released = 0
        self.fail: dict[str, int] = {}

    def MCL_InitHandle(self):  # noqa: N802
        if "handle" in self.fail:
            return 0
        self.handles += 1
        return 42

    def MCL_ReleaseHandle(self, handle):  # noqa: N802
        self.released += 1
        return 0

    def MCL_GetProductInfo(self, info, handle):  # noqa: N802
        if "info" in self.fail:
            return self.fail["info"]
        target = info._obj
        target.axis_bitmap = self.bitmap
        target.ADC_resolution = 20
        target.DAC_resolution = 20
        target.Product_id = 2200
        target.FirmwareVersion = 3
        target.FirmwareProfile = 1
        return 0

    def MCL_GetSerialNumber(self, handle):  # noqa: N802
        return 2201

    def MCL_GetCalibration(self, axis, handle):  # noqa: N802
        return self.travel

    def MCL_SingleReadN(self, axis, handle):  # noqa: N802
        if "read" in self.fail:
            return float(self.fail["read"])
        return self.positions[int(axis)]

    def MCL_SingleWriteN(self, position, axis, handle):  # noqa: N802
        if "write" in self.fail:
            return self.fail["write"]
        self.positions[int(axis)] = float(position.value)
        return 0

    def MCL_DeviceAttached(self, wait, handle):  # noqa: N802
        return 1


@pytest.fixture
def madlib(monkeypatch):
    fake = _FakeMadlib()
    monkeypatch.setattr(
        "labpilot.instruments.MadCityLabs.nano_drive._Madlib.load",
        lambda self: setattr(self, "_dll", fake),
    )
    return fake


async def _nano(madlib, **kwargs) -> NanoDriveAdapter:
    adapter = NanoDriveAdapter(**kwargs)
    await adapter.connect()
    return adapter


def test_both_stages_are_registered_and_catalogued():
    for key in ("mcl_nano_drive", "mcl_micro_drive"):
        assert key in adapter_registry.list()
        assert any(m.adapter_key == key for m in INSTRUMENT_CATALOG)


def test_they_describe_themselves_with_no_library_installed():
    for cls in (NanoDriveAdapter, MicroDriveAdapter):
        schema = cls.describe()
        assert schema is not None and schema.kind == "motor"


async def test_the_travel_comes_from_the_stage(madlib):
    """A piezo's limits are its whole safety story — there is no
    mechanical slip to absorb an over-travel command — so they are the
    stage's own numbers, not a datasheet's."""
    madlib.travel = 75.0
    adapter = await _nano(madlib)
    try:
        assert adapter.schema.require("x").limits == (0.0, 75.0)
    finally:
        await adapter.disconnect()


async def test_an_axis_the_stage_does_not_have_is_not_offered(madlib):
    """Otherwise it is a control in the settings window that fails on use,
    and a scan axis a plan will happily try to step."""
    madlib.bitmap = 0b011
    adapter = await _nano(madlib)
    try:
        assert tuple(p.name for p in adapter.schema.find(settable=True)) == ("x", "y")
        assert adapter.schema.get("z") is None
    finally:
        await adapter.disconnect()


async def test_asking_for_an_axis_that_does_not_exist_says_which_do(madlib):
    madlib.bitmap = 0b011
    adapter = NanoDriveAdapter(axes="x,z")
    with pytest.raises(DeviceError, match="has axes x, y"):
        await adapter.connect()


async def test_naming_a_subset_of_the_axes_is_respected(madlib):
    """For a rig where only two of a three-axis controller are wired."""
    adapter = await _nano(madlib, axes="x,y")
    try:
        assert tuple(p.name for p in adapter.schema.find(settable=True)) == ("x", "y")
    finally:
        await adapter.disconnect()


async def test_a_stage_reporting_no_axes_is_refused(madlib):
    madlib.bitmap = 0
    with pytest.raises(DeviceError, match="reports no axes"):
        await NanoDriveAdapter().connect()


async def test_a_position_is_written_and_read_back(madlib):
    adapter = await _nano(madlib)
    try:
        await adapter.write({"x": 12.5, "z": 40.0})
        reading = await adapter.read()
        assert reading["x"] == pytest.approx(12.5)
        assert reading["z"] == pytest.approx(40.0)
        assert reading["y"] == pytest.approx(0.0)
    finally:
        await adapter.disconnect()


async def test_each_axis_is_written_on_its_own_number(madlib):
    """The test that would catch an off-by-one in the axis map: moving x
    and finding y somewhere new."""
    adapter = await _nano(madlib)
    try:
        await adapter.write({"y": 30.0})
        assert madlib.positions == {1: 0.0, 2: 30.0, 3: 0.0}
    finally:
        await adapter.disconnect()


async def test_a_move_past_the_stages_travel_is_refused(madlib):
    madlib.travel = 50.0
    adapter = await _nano(madlib)
    try:
        with pytest.raises(LimitError):
            adapter.validate_write({"x": 60.0})
    finally:
        await adapter.disconnect()


async def test_a_negative_reading_is_an_error_code_not_a_position(madlib):
    """`MCL_SingleReadN` overloads its return. Travel starts at zero, so a
    negative value cannot be a position — but carried into a dataset it
    would look like a stage that went backwards past its own home."""
    madlib.fail["read"] = -7
    adapter = await _nano(madlib)
    try:
        with pytest.raises(DeviceError, match="does not exist on this stage"):
            await adapter.read()
    finally:
        await adapter.disconnect()


async def test_a_failed_write_names_the_axis_and_the_value(madlib):
    madlib.fail["write"] = -5
    adapter = await _nano(madlib)
    try:
        with pytest.raises(DeviceError, match=r"MCL_SingleWriteN\(x=5 um\)"):
            await adapter.write({"x": 5.0})
    finally:
        await adapter.disconnect()


async def test_a_stage_that_will_not_answer_says_it_may_be_claimed(madlib):
    """MCL's library allows one handle per device, so the commonest cause
    of this is a second window, not a fault."""
    madlib.fail["handle"] = 0
    with pytest.raises(DeviceError, match="already claimed"):
        await NanoDriveAdapter().connect()


async def test_a_failure_after_claiming_releases_the_handle_again(madlib):
    """Otherwise the device stays claimed and the next attempt cannot open
    it — which looks exactly like a hardware fault."""
    madlib.fail["info"] = -2
    with pytest.raises(DeviceError):
        await NanoDriveAdapter().connect()
    assert madlib.released == 1


async def test_disconnecting_releases_only_our_handle(madlib):
    """Not `MCL_ReleaseAllHandles`, which both open wrappers call and
    which would release the handle another adapter or process is using."""
    adapter = await _nano(madlib)
    await adapter.disconnect()
    assert madlib.released == 1
    assert not hasattr(madlib, "all_released")


# --- The Micro-Drive --------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (0b111111, {}),                       # nothing at a limit
        (0b111110, {"x": "reverse"}),         # bit 0 clear
        (0b111101, {"x": "forward"}),
        (0b111011, {"y": "reverse"}),
        (0b011111, {"z": "forward"}),
        (0b111100, {"x": "forward"}),         # both x bits clear: the later wins
    ],
)
def test_the_limit_bits_are_active_low(status, expected):
    """Reading them the obvious way round reports every axis as
    permanently jammed, which is why the convention is tested rather than
    only commented."""
    assert limits_reached(status, ("x", "y", "z")) == expected


class _FakeMicroDrive:
    """`MicroDrive.dll`'s calls, and the contract relied on.

    The important one: `MCL_MDMove` takes a **distance**, and the encoders
    are the only thing that knows where the stage is.
    """

    def __init__(self) -> None:
        self.encoders = [0.0, 0.0, 0.0, 0.0]
        self.moves: list[tuple[int, float, float]] = []
        self.waits = 0
        self.stops = 0
        self.zeroed = 0
        self.status = 0b111111
        self.released = 0
        self.information = (1e-5, 9.525e-5, 3.0, 2.0, 1.5, 0.01905)
        self.fail: dict[str, int] = {}

    def MCL_InitHandle(self):  # noqa: N802
        return 7

    def MCL_ReleaseHandle(self, handle):  # noqa: N802
        self.released += 1
        return 0

    def MCL_GetSerialNumber(self, handle):  # noqa: N802
        return 1234

    def MCL_DeviceAttached(self, wait, handle):  # noqa: N802
        return 1

    def MCL_MDInformation(self, *args):  # noqa: N802
        if "information" in self.fail:
            return self.fail["information"]
        *pointers, _handle = args
        for pointer, value in zip(pointers, self.information, strict=False):
            pointer._obj.value = value
        return 0

    def MCL_MDReadEncoders(self, e1, e2, e3, e4, handle):  # noqa: N802
        for pointer, value in zip((e1, e2, e3, e4), self.encoders, strict=False):
            pointer._obj.value = value
        return 0

    def MCL_MDStatus(self, status, handle):  # noqa: N802
        status._obj.value = self.status
        return 0

    def MCL_MicroDriveMoveStatus(self, moving, handle):  # noqa: N802
        moving._obj.value = 0
        return 0

    def MCL_MDMove(self, axis, velocity, distance, handle):  # noqa: N802
        if "move" in self.fail:
            return self.fail["move"]
        self.moves.append((int(axis.value), float(velocity.value), float(distance.value)))
        self.encoders[int(axis.value) - 1] += float(distance.value)
        return 0

    def MCL_MicroDriveWait(self, handle):  # noqa: N802
        self.waits += 1
        return 0

    def MCL_MDStop(self, status, handle):  # noqa: N802
        self.stops += 1
        return 0

    def MCL_MDResetEncoders(self, status, handle):  # noqa: N802
        self.zeroed += 1
        self.encoders = [0.0, 0.0, 0.0, 0.0]
        return 0


@pytest.fixture
def microdrive(monkeypatch):
    fake = _FakeMicroDrive()
    monkeypatch.setattr(
        "labpilot.instruments.MadCityLabs.micro_drive._MicroDriveLib.load",
        lambda self: setattr(self, "_dll", fake),
    )
    return fake


async def _micro(microdrive, **kwargs) -> MicroDriveAdapter:
    adapter = MicroDriveAdapter(**kwargs)
    await adapter.connect()
    return adapter


def test_an_axis_name_the_libraries_do_not_know_is_refused():
    with pytest.raises(ValueError, match="must be one of x, y, z"):
        MicroDriveAdapter(axes="x,theta")


async def test_the_resolution_and_velocity_bounds_come_from_the_controller(microdrive):
    adapter = await _micro(microdrive)
    try:
        reading = await adapter.read()
        assert reading["step_size"] == pytest.approx(9.525e-5)
        assert reading["encoder_resolution"] == pytest.approx(1e-5)
        assert adapter.schema.require("velocity_mm_s").limits == (0.01905, 3.0)
    finally:
        await adapter.disconnect()


async def test_a_requested_speed_above_the_controllers_is_brought_down(microdrive):
    """Rather than erroring on the first move, far from where the number
    was typed."""
    adapter = await _micro(microdrive, velocity_mm_s=10.0)
    try:
        assert (await adapter.read())["velocity_mm_s"] == pytest.approx(3.0)
    finally:
        await adapter.disconnect()


async def test_an_absolute_move_is_sent_as_the_delta_from_the_encoder(microdrive):
    """The adapter's whole job here: an absolute contract over a library
    that only moves distances."""
    microdrive.encoders = [2.0, 0.0, 0.0, 0.0]
    adapter = await _micro(microdrive)
    try:
        await adapter.write({"x": 5.0})
        axis, _velocity, distance = microdrive.moves[-1]
        assert axis == 1
        assert distance == pytest.approx(3.0)
        assert microdrive.waits == 1, "the move is waited for, not fired and forgotten"
        assert (await adapter.read())["x"] == pytest.approx(5.0)
    finally:
        await adapter.disconnect()


async def test_the_delta_is_measured_not_remembered(microdrive):
    """A stepper that stalled, or that someone nudged by hand, is at a
    position nothing in this process knows — so the encoder is asked
    every time rather than a setpoint being tracked."""
    adapter = await _micro(microdrive)
    try:
        await adapter.write({"x": 1.0})
        microdrive.encoders[0] = 0.4          # it stalled, or was nudged
        await adapter.write({"x": 1.0})
        assert microdrive.moves[-1][2] == pytest.approx(0.6)
    finally:
        await adapter.disconnect()


async def test_a_move_smaller_than_one_microstep_is_not_sent(microdrive):
    """The controller would either refuse it or move a whole step, and a
    whole step is not what was asked for."""
    adapter = await _micro(microdrive)
    try:
        await adapter.write({"x": 1e-6})
        assert microdrive.moves == []
    finally:
        await adapter.disconnect()


async def test_each_axis_moves_on_its_own_number(microdrive):
    adapter = await _micro(microdrive)
    try:
        await adapter.write({"z": 1.0})
        assert microdrive.moves[-1][0] == 3
    finally:
        await adapter.disconnect()


async def test_a_move_past_the_declared_travel_is_refused(microdrive):
    adapter = await _micro(microdrive, travel_mm=10.0)
    try:
        with pytest.raises(LimitError):
            adapter.validate_write({"x": 11.0})
    finally:
        await adapter.disconnect()


async def test_the_declared_travel_is_the_default_when_not_given(microdrive):
    adapter = await _micro(microdrive)
    try:
        assert adapter.schema.require("x").limits == (0.0, DEFAULT_TRAVEL_MM)
    finally:
        await adapter.disconnect()


async def test_a_limit_switch_is_reported_by_axis_and_direction(microdrive):
    microdrive.status = 0b111011   # axis 2 reverse
    adapter = await _micro(microdrive)
    try:
        assert (await adapter.read())["at_limit"] == "y reverse"
    finally:
        await adapter.disconnect()


async def test_nothing_at_a_limit_reports_nothing(microdrive):
    adapter = await _micro(microdrive)
    try:
        assert (await adapter.read())["at_limit"] == ""
    finally:
        await adapter.disconnect()


async def test_stopping_halts_the_stage(microdrive):
    """On a stepper this is the difference between an abort and an abort
    that keeps travelling."""
    adapter = await _micro(microdrive)
    try:
        await adapter.stop()
        assert microdrive.stops == 1
    finally:
        await adapter.disconnect()


async def test_zeroing_the_encoders_moves_nothing(microdrive):
    """Not a home: the stage's relationship to its mechanical limits is
    unchanged. It is how a stage with no absolute reference gets one."""
    microdrive.encoders = [3.0, 0.0, 0.0, 0.0]
    adapter = await _micro(microdrive)
    try:
        await adapter.zero_encoders()
        assert microdrive.zeroed == 1
        assert microdrive.moves == []
        assert (await adapter.read())["x"] == pytest.approx(0.0)
    finally:
        await adapter.disconnect()


async def test_a_failed_move_names_the_axis_and_the_distance(microdrive):
    microdrive.fail["move"] = -5
    adapter = await _micro(microdrive)
    try:
        with pytest.raises(DeviceError, match=r"MCL_MDMove\(x by \+1 mm\)"):
            await adapter.write({"x": 1.0})
    finally:
        await adapter.disconnect()


async def test_a_failure_reading_the_information_releases_the_handle(microdrive):
    microdrive.fail["information"] = -2
    with pytest.raises(DeviceError, match="MCL_MDInformation failed"):
        await MicroDriveAdapter().connect()
    assert microdrive.released == 1


async def test_reading_a_disconnected_stage_is_refused(microdrive):
    adapter = await _micro(microdrive)
    await adapter.disconnect()
    with pytest.raises(DeviceError, match="not connected"):
        adapter._read_sync()
