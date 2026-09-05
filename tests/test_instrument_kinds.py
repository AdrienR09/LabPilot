"""Tests for core.device.kinds — the kind-typed Session.get() wrappers."""

from __future__ import annotations

import pytest

from labpilot.core.device.kinds import (
    Detector,
    GenericInstrument,
    Motor,
    Scanner,
    Source,
    wrap,
)
from labpilot.core.session import Session
from labpilot.instruments.mock.hardware_scan import MockNIScanner
from labpilot.instruments.mock.microwave_sources import MockMicrowaveSource
from labpilot.instruments.mock.motors import MockMotor, MockXYZStage
from labpilot.instruments.MockBasic.simple import (
    MockBasicActuator0D,
    MockBasicDetector0D,
    MockBasicDetector1D,
)


@pytest.fixture
async def motor():
    m = MockMotor()
    await m.connect()
    return wrap(m)


@pytest.fixture
async def xyz_stage():
    m = MockXYZStage()
    await m.connect()
    return wrap(m)


class TestMotor:
    async def test_wraps_as_motor(self, motor):
        assert isinstance(motor, Motor)

    async def test_single_axis_axes(self, motor):
        assert motor.axes == ["position"]

    async def test_single_axis_get_position_returns_float(self, motor):
        pos = await motor.get_position()
        assert isinstance(pos, float)

    async def test_single_axis_move_abs_single_value(self, motor):
        result = await motor.move_abs(5.0)
        assert result == pytest.approx(5.0)
        assert await motor.get_position() == pytest.approx(5.0)

    async def test_single_axis_move_rel(self, motor):
        await motor.move_abs(5.0)
        result = await motor.move_rel(1.0)
        assert result == pytest.approx(6.0)

    async def test_get_position_named_axis(self, motor):
        await motor.move_abs(3.0)
        assert await motor.get_position("position") == pytest.approx(3.0)

    async def test_get_position_unknown_axis_raises(self, motor):
        with pytest.raises(KeyError):
            await motor.get_position("nonexistent")

    async def test_multi_axis_axes(self, xyz_stage):
        assert xyz_stage.axes == ["x", "y", "z"]

    async def test_multi_axis_get_position_returns_dict(self, xyz_stage):
        pos = await xyz_stage.get_position()
        assert set(pos) == {"x", "y", "z"}

    async def test_multi_axis_move_abs_kwargs(self, xyz_stage):
        result = await xyz_stage.move_abs(x=1.0, y=2.0)
        assert result == {"x": pytest.approx(1.0), "y": pytest.approx(2.0)}
        pos = await xyz_stage.get_position()
        assert pos["x"] == pytest.approx(1.0)
        assert pos["y"] == pytest.approx(2.0)
        assert pos["z"] == pytest.approx(0.0)  # untouched

    async def test_multi_axis_move_abs_axis_value_pair(self, xyz_stage):
        result = await xyz_stage.move_abs("x", 4.0)
        assert result == pytest.approx(4.0)

    async def test_multi_axis_move_abs_single_positional_ambiguous(self, xyz_stage):
        with pytest.raises(TypeError):
            await xyz_stage.move_abs(1.0)

    async def test_no_axis_device_degrades_cleanly(self):
        adapter = MockBasicActuator0D()
        await adapter.connect()
        m = wrap(adapter)
        assert isinstance(m, Motor)
        assert m.axes == []
        assert await m.get_position() == {}
        with pytest.raises(TypeError):
            await m.move_abs(1.0)

    async def test_passthrough_read_write_still_work(self, motor):
        await motor.write({"position": 7.0})
        data = await motor.read()
        assert data["position"] == pytest.approx(7.0)


class TestDetector:
    async def test_wraps_as_detector(self):
        d = MockBasicDetector0D()
        await d.connect()
        wrapped = wrap(d)
        assert isinstance(wrapped, Detector)

    async def test_read_value_scalar(self):
        d = MockBasicDetector0D()
        await d.connect()
        wrapped = wrap(d)
        value = await wrapped.read_value()
        assert isinstance(value, float)

    async def test_read_value_non_scalar_raises(self):
        d = MockBasicDetector1D()
        await d.connect()
        wrapped = wrap(d)
        with pytest.raises(ValueError):
            await wrapped.read_value()

    async def test_acquire_once_stages_and_unstages(self):
        d = MockBasicDetector0D()
        await d.connect()
        wrapped = wrap(d)
        data = await wrapped.acquire_once()
        assert "value" in data


class TestSource:
    async def test_wraps_as_source_and_actions_passthrough(self):
        s = MockMicrowaveSource()
        await s.connect()
        wrapped = wrap(s)
        assert isinstance(wrapped, Source)
        assert "cw_on" in wrapped.actions
        await wrapped.cw_on()  # passthrough to the real adapter method


class TestScanner:
    async def test_wraps_as_scanner_and_methods_delegate(self):
        adapter = MockNIScanner()
        wrapped = wrap(adapter)
        assert isinstance(wrapped, Scanner)
        await wrapped.configure_scan(["x"], {"x": (0.0, 1.0)}, {"x": 4}, 100.0)
        await wrapped.start_scan()
        data = await wrapped.get_scan_data()
        assert "data" in data
        await wrapped.stop_scan()


class TestSessionIntegration:
    async def test_get_returns_wrapper(self):
        session = Session()
        adapter = MockXYZStage()
        await adapter.connect()
        session.register(adapter, name="xyz")
        wrapped = session.get("xyz")
        assert isinstance(wrapped, Motor)

    async def test_get_raw_returns_unwrapped_adapter(self):
        session = Session()
        adapter = MockXYZStage()
        await adapter.connect()
        session.register(adapter, name="xyz")
        assert session.get_raw("xyz") is adapter
