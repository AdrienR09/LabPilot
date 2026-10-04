"""The one shared defect on every camera's read path.

All nine hand-written pylablib camera adapters read a frame with
`read_oldest_image()`, which pylablib documents as returning **`None`**
when no un-read frame is available, and then wrapped it in
`np.array(...)` — producing a 0-d object array. So a camera that was
connected but not staged answered `read()` with a thing shaped like
nothing, declared in its own schema as a 2-D image.

That is not an exotic path. It is what `labpilot probe` does to a camera,
what a console `lp["cam"].read()` does, and what a live preview does
before anyone has started a scan. Fixing it in the shared mixin fixes all
nine at once, which is the same leverage `_generic_pymeasure.py` has over
its 183.

These tests use a stand-in with pylablib's documented behaviour — `snap`
when idle, `wait_for_frame` then `read_oldest_image` when acquiring, and
`None` when there is nothing to read.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from labpilot.instruments._pylablib_camera import PylablibCameraControls


class _FakeCamera:
    """pylablib's camera interface, as far as `frame_sync` relies on it."""

    def __init__(self, *, acquiring: bool = False, frames: int = 1) -> None:
        self._acquiring = acquiring
        self._frames = frames
        self.snaps = 0
        self.waits = 0
        self.reads = 0
        self.info: tuple[str, ...] | None = (
            "Hamamatsu", "C11440-22CU", "S/N 123456", "4.20",
        )
        self.size: tuple[int, int] | None = (2048, 2048)

    def acquisition_in_progress(self) -> bool:
        return self._acquiring

    def snap(self, timeout: float = 5.0):
        self.snaps += 1
        return None if self._frames == 0 else np.ones((4, 6))

    def wait_for_frame(self, timeout: float = 20.0) -> None:
        self.waits += 1

    def read_oldest_image(self):
        self.reads += 1
        if self._frames == 0:
            return None
        self._frames -= 1
        return np.full((4, 6), 7.0)

    def get_device_info(self):
        if self.info is None:
            raise RuntimeError("this vendor SDK has no such call")
        return self.info

    def get_detector_size(self):
        if self.size is None:
            raise RuntimeError("nor this one")
        return self.size


class _Adapter(PylablibCameraControls):
    """The host side of the mixin: a camera on `self._camera`."""

    def __init__(self, camera: Any = None) -> None:
        self._camera = camera


# --- Reading a frame --------------------------------------------------------


def test_an_idle_camera_is_snapped():
    """What makes a one-off read work on a camera nobody has staged — a
    probe, a console read, a preview before a scan."""
    camera = _FakeCamera(acquiring=False)
    frame = _Adapter(camera).frame_sync()

    assert camera.snaps == 1
    assert camera.waits == 0
    assert frame.shape == (4, 6)


def test_an_acquiring_camera_is_waited_for_then_read():
    """Reading the queue without waiting returns `None` whenever the read
    lands between frames, which at long exposures is most of the time."""
    camera = _FakeCamera(acquiring=True)
    frame = _Adapter(camera).frame_sync()

    assert (camera.waits, camera.reads, camera.snaps) == (1, 1, 0)
    assert frame.shape == (4, 6)
    assert frame[0, 0] == 7.0


def test_a_frame_is_always_a_real_array():
    """`np.array(None)` is a 0-d object array. It passes every downstream
    type check and fails at the plot, which is the worst place to find
    out."""
    frame = _Adapter(_FakeCamera()).frame_sync()
    assert isinstance(frame, np.ndarray)
    assert frame.dtype != object
    assert frame.ndim == 2


def test_no_frame_at_all_is_an_error_that_names_the_likely_cause():
    """Almost always an external trigger that never came."""
    camera = _FakeCamera(acquiring=True, frames=0)
    with pytest.raises(RuntimeError, match="trigger"):
        _Adapter(camera).frame_sync()


def test_an_idle_camera_that_snaps_nothing_is_also_an_error():
    camera = _FakeCamera(acquiring=False, frames=0)
    with pytest.raises(RuntimeError, match="returned no frame"):
        _Adapter(camera).frame_sync()


def test_reading_before_connecting_says_to_connect():
    with pytest.raises(RuntimeError, match="not connected"):
        _Adapter(None).frame_sync()


# --- Identifying the camera -------------------------------------------------


def test_the_camera_identifies_itself():
    """Every one of these is a question `labpilot probe` should be able to
    answer about a camera, and none of them was declared before."""
    status = _Adapter(_FakeCamera()).camera_status()
    assert status["vendor"] == "Hamamatsu"
    assert status["model"] == "C11440-22CU"
    assert status["serial_number"] == "S/N 123456"
    assert (status["sensor_width"], status["sensor_height"]) == (2048, 2048)


def test_a_vendor_sdk_without_an_info_call_still_reads():
    """Best effort on purpose: the information call is the one most likely
    to differ between SDKs, and a missing serial number is not a reason to
    fail a frame read."""
    camera = _FakeCamera()
    camera.info = None
    camera.size = None
    status = _Adapter(camera).camera_status()

    assert status["model"] == ""
    assert status["sensor_width"] == 0


def test_a_short_info_tuple_fills_what_it_can():
    camera = _FakeCamera()
    camera.info = ("Andor",)
    status = _Adapter(camera).camera_status()
    assert status["vendor"] == "Andor"
    assert status["serial_number"] == ""


# --- Every camera adapter goes through it -----------------------------------


def test_no_adapter_reads_the_queue_directly_any_more():
    """The regression guard for the whole point of this change: a new
    camera adapter copied from an old one would otherwise quietly
    reintroduce the same `None`."""
    import pathlib

    import labpilot.instruments as instruments

    root = pathlib.Path(instruments.__path__[0])
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.name != "_pylablib_camera.py"
        and "read_oldest_image" in path.read_text()
    ]
    assert offenders == []
