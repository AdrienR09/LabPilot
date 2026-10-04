"""Pi Imaging SPAD512 / SPAD512S — the photon-counting camera array.

A 512-row SPAD array: every pixel is its own single-photon detector, so a
frame is a photon count per pixel rather than an integrated charge. The
SwissSPAD lineage, sold as the SPAD512 series.

## The connection is to their software, not to the camera

Unusually, and worth knowing before anyone goes looking for a cable:
**Pi Imaging's own desktop application is the server.** It owns the
camera and exposes a TCP command port on `127.0.0.1`, and
`SPAD512S.py` — the library that ships with it — is a client of that
port. So this adapter connects to localhost, their software must be
running, and the port is the one their application shows.

That has a consequence worth stating: this will never work headless or
from another machine, and the camera cannot be shared with their live
view while a measurement runs.

## It wraps their library rather than their protocol

The wire protocol is short commands — `I` for an intensity run, `G` for a
gated one, `R` for temperatures, `PU` for pile-up correction — but the
framing, the reshape order and the 16-bit byte interleaving are all
theirs, and all easy to get subtly wrong in ways that produce an image
rather than an error. So this calls `SPAD512S.get_intensity(...)` and
lets their library own that, the same choice made for the PicoHarp's
`phlib` and the SuperK's register map.

## The integration time's unit depends on the bit depth

Their library documents `intTime` as "in ms for 6, 7, 8 bits and in us
for 1, 4 bits". That is a real trap: the same number means a thousandfold
different exposure depending on another setting. This adapter takes
milliseconds always and converts, so a 1-bit run at 10 ms is 10 ms.

## Gated imaging is not adapted yet, on purpose

The SPAD512's gated mode is the interesting one — a stack of images, each
shifted a known number of picoseconds from the laser clock — and it is
deliberately left out rather than guessed at. Two reasons:

1. Its natural output is `(gate_step, row, column)`, a time-resolved
   *image* stack. That is neither the 2-D frame a `detector` returns nor
   the `(gate, time_bin)` of `GatedCounterMixin`, which describes a
   single-pixel counter. It wants a contract that does not exist yet, and
   inventing one from a datasheet is how a contract comes out wrong.
2. The only copy of `get_gated_intensity` available to check against is
   one a third party had patched — its own comments describe fixing the
   streaming mode and the reshape — so it is not a reliable reference for
   what the vendor's version does.

Intensity imaging, the camera's identity, its four temperatures and both
clock frequencies are here and are the whole of a first-light
diagnosis. Gated imaging comes after someone has run this against the
camera.

Needs `SPAD512S.py` from Pi Imaging's software installation; there is no
PyPI package, so `library_path` points at the folder holding it. Imported
inside `_connect_sync`, so this adapter registers, describes itself and
is probeable without it. **Not run against hardware.**
"""

from __future__ import annotations

import contextlib
import sys
from typing import Any

import numpy as np

from labpilot.core.device.parameter import (
    INTEGRATION_TIME,
    Parameter,
    ParamRole,
)
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry

__all__ = ["BIT_DEPTHS", "IMAGE_WIDTHS", "SPAD512Adapter"]

#: The sensor is always 512 rows; only the width is selectable.
SENSOR_ROWS = 512

#: Their library's `intBitDepths`. 1-bit is a single photon per pixel per
#: frame — the array's native mode — and 12-bit counts in hardware.
BIT_DEPTHS = (1, 4, 6, 7, 8, 9, 10, 11, 12)

#: Their library's `col`. A narrower window reads out faster.
IMAGE_WIDTHS = (4, 8, 16, 32, 64, 128, 256, 512)

#: Bit depths whose `intTime` their library takes in microseconds rather
#: than milliseconds. The reason this adapter converts.
MICROSECOND_DEPTHS = (1, 4)


class SPAD512Adapter(AdapterBase):
    """A SPAD512 in intensity mode, as a photon-counting 2-D detector.

    Args:
        port: The TCP port Pi Imaging's application is listening on, which
            that application shows. There is no sensible default: a wrong
            port connects to whatever else is on it.
        library_path: Folder containing `SPAD512S.py` from their
            installation, prepended to `sys.path` if given.
        bit_depth / integration_time_ms / iterations / image_width:
            Acquisition settings, all also settable at runtime.
        pileup_correction: Corrects counts for the photons a SPAD cannot
            see because it was already recovering. On at high flux, and
            the reason a 16-bit frame comes back from an 8-bit run.
        overlap: Overlap readout with the next exposure. Faster, and not
            always wanted when the light is gated.
    """

    def __init__(
        self,
        port: int = 0,
        library_path: str = "",
        bit_depth: int = 8,
        integration_time_ms: float = 10.0,
        iterations: int = 1,
        image_width: int = 512,
        pileup_correction: bool = True,
        overlap: bool = False,
        name: str = "spad512",
    ) -> None:
        super().__init__()
        self.port = int(port)
        self.library_path = str(library_path)
        self._bit_depth = int(bit_depth)
        self._integration_ms = float(integration_time_ms)
        self._iterations = int(iterations)
        self._image_width = int(image_width)
        self._pileup = bool(pileup_correction)
        self._overlap = bool(overlap)
        self._name = name

        self._camera: Any = None
        self._info: list[str] = []
        self._detector_type = ""

    # --- What it is --------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            parameters=(
                Parameter(
                    "frame", shape=(SENSOR_ROWS, None), unit="counts",
                    description=(
                        "Photon counts per pixel, summed over the "
                        "iterations — summing is the right reduction for "
                        "counts, where averaging would throw away the "
                        "Poisson statistics the error bars come from."
                    ),
                ),
                Parameter(
                    "integration_time_ms", unit="ms", settable=True,
                    role=ParamRole.SETTING, limits=(0.0, None),
                    tags=frozenset({INTEGRATION_TIME}),
                    description=(
                        "Always milliseconds here; converted to the "
                        "microseconds their library wants at 1 and 4 bits."
                    ),
                ),
                Parameter(
                    "bit_depth", dtype="i8", settable=True,
                    role=ParamRole.SETTING, choices=BIT_DEPTHS,
                ),
                Parameter(
                    "iterations", dtype="i8", settable=True,
                    role=ParamRole.SETTING, limits=(1, None),
                    description="Frames per read, summed into one image",
                ),
                Parameter(
                    "image_width", dtype="i8", unit="px", settable=True,
                    role=ParamRole.SETTING, choices=IMAGE_WIDTHS,
                    description="Columns read out; the 512 rows are fixed",
                ),
                Parameter(
                    "pileup_correction", dtype="bool", settable=True,
                    role=ParamRole.SETTING,
                    description=(
                        "Corrects for photons a recovering SPAD could not "
                        "see. On at high flux."
                    ),
                ),
                Parameter(
                    "overlap", dtype="bool", settable=True,
                    role=ParamRole.SETTING,
                    description="Overlap readout with the next exposure",
                ),
                Parameter(
                    "temperature_chip", unit="degC", role=ParamRole.STATUS,
                    description="The sensor itself — what dark counts follow",
                ),
                Parameter("temperature_pcb", unit="degC", role=ParamRole.STATUS),
                Parameter("temperature_master", unit="degC", role=ParamRole.STATUS),
                Parameter("temperature_slave", unit="degC", role=ParamRole.STATUS),
                Parameter(
                    "laser_clock", unit="Hz", role=ParamRole.STATUS,
                    description=(
                        "The excitation clock the camera sees. Zero means "
                        "the laser's sync is not reaching it, which is the "
                        "first thing to check before anything else."
                    ),
                ),
                Parameter("frame_clock", unit="Hz", role=ParamRole.STATUS),
                Parameter("detector_type", dtype="str", role=ParamRole.STATUS),
                Parameter(
                    "system_info", dtype="str", role=ParamRole.STATUS,
                    description=(
                        "Serials and versions as their software reports "
                        "them, joined — the provenance of a frame"
                    ),
                ),
            ),
            actions=["calibrate_hot_pixels", "enable_cooling", "disable_cooling"],
            tags=[
                "Pi Imaging", "SPAD512", "SPAD512S", "SwissSPAD", "SPAD",
                "camera", "photon-counting", "array",
            ],
        )

    # --- Connection --------------------------------------------------------

    def _import(self) -> Any:
        if self.library_path and self.library_path not in sys.path:
            sys.path.insert(0, self.library_path)
        try:
            from SPAD512S import SPAD512S
        except ImportError as exc:
            raise ImportError(
                "Talking to a SPAD512 needs `SPAD512S.py` from Pi Imaging's "
                "own software installation — there is no package to "
                "pip-install. Pass library_path=<folder containing it>. "
                "Their application must also be running: it owns the camera "
                "and this connects to the TCP port it serves."
            ) from exc
        return SPAD512S

    def _connect_sync(self) -> None:
        if not self.port:
            raise DeviceError(
                "A SPAD512 is reached through Pi Imaging's own application, "
                "which serves a TCP port on this machine. Pass the port it "
                "shows; there is no safe default, because a wrong port "
                "connects to whatever else is listening.",
                device=self._name,
            )
        cls = self._import()
        camera = cls(self.port)
        # Their constructor swallows a refused connection and returns
        # `None` from `__init__` rather than raising, which leaves a
        # half-built object. So the handshake it performs is what gets
        # checked, not the call.
        if getattr(camera, "detType", None) is None:
            raise DeviceError(
                f"Nothing answered the SPAD512 handshake on port {self.port}. "
                f"Pi Imaging's application has to be running and showing "
                f"this port.",
                device=self._name,
            )
        self._camera = camera
        self._detector_type = str(camera.detType)
        with contextlib.suppress(Exception):
            self._info = [str(line).strip() for line in camera.get_info()]

    def _disconnect_sync(self) -> None:
        if self._camera is not None:
            with contextlib.suppress(Exception):
                self._camera.t.close()
        self._camera = None

    def _require(self) -> Any:
        if self._camera is None:
            raise DeviceError(f"{self._name} is not connected", device=self._name)
        return self._camera

    # --- Reading ------------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        camera = self._require()
        master, slave, pcb, chip = self._temperatures()
        laser_clock, frame_clock = self._clocks()
        return {
            "frame": self._frame(camera),
            "integration_time_ms": self._integration_ms,
            "bit_depth": self._bit_depth,
            "iterations": self._iterations,
            "image_width": self._image_width,
            "pileup_correction": self._pileup,
            "overlap": self._overlap,
            "temperature_master": master,
            "temperature_slave": slave,
            "temperature_pcb": pcb,
            "temperature_chip": chip,
            "laser_clock": laser_clock,
            "frame_clock": frame_clock,
            "detector_type": self._detector_type,
            "system_info": "; ".join(self._info),
        }

    def _frame(self, camera: Any) -> np.ndarray:
        """One image, summed over the iterations.

        Their `get_intensity` returns `(rows, width, iterations)`. Summing
        rather than averaging is the right reduction for photon counts: it
        is what makes the result Poisson-distributed, which is what the
        error bars downstream are computed from.
        """
        stack = camera.get_intensity(
            self._iterations,
            self._integration_time(),
            self._bit_depth,
            int(self._overlap),
            1,                      # timeout: retry a failed measurement
            int(self._pileup),
            self._image_width,
        )
        values = np.asarray(stack)
        if values.ndim == 3:
            return values.sum(axis=2)
        if values.ndim == 2:
            return values
        raise DeviceError(
            f"The SPAD512 returned a {values.ndim}-D array; a frame stack is "
            f"(rows, width, iterations).",
            device=self._name,
        )

    def _integration_time(self) -> float:
        """Their library's unit for the current bit depth.

        Milliseconds at 6 bits and above, microseconds at 1 and 4 — see
        the module docstring. Converting here is what makes the schema's
        single `integration_time_ms` honest.
        """
        if self._bit_depth in MICROSECOND_DEPTHS:
            return self._integration_ms * 1000.0
        return self._integration_ms

    def _temperatures(self) -> tuple[float, float, float, float]:
        """Master FPGA, slave FPGA, PCB and chip, as numbers.

        Their library returns them as strings, which plot as nothing and
        compare as text. Best effort per value: a camera that cannot
        report one temperature can still take a frame.
        """
        try:
            values = self._require().get_temps()
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)
        numbers = []
        for value in values:
            try:
                numbers.append(float(str(value).strip()))
            except (TypeError, ValueError):
                numbers.append(0.0)
        numbers += [0.0] * (4 - len(numbers))
        return (numbers[0], numbers[1], numbers[2], numbers[3])

    def _clocks(self) -> tuple[float, float]:
        try:
            values = self._require().get_freq()
        except Exception:
            return (0.0, 0.0)
        numbers = []
        for value in values[:2]:
            try:
                numbers.append(float(str(value).strip()))
            except (TypeError, ValueError):
                numbers.append(0.0)
        numbers += [0.0] * (2 - len(numbers))
        return (numbers[0], numbers[1])

    # --- Settings -----------------------------------------------------------

    async def set_integration_time_ms(self, value: float) -> None:
        self._integration_ms = float(value)

    async def set_bit_depth(self, value: int) -> None:
        self._bit_depth = int(value)

    async def set_iterations(self, value: int) -> None:
        self._iterations = max(int(value), 1)

    async def set_image_width(self, value: int) -> None:
        self._image_width = int(value)

    async def set_pileup_correction(self, value: bool) -> None:
        self._pileup = bool(value)

    async def set_overlap(self, value: bool) -> None:
        self._overlap = bool(value)

    # --- Actions -------------------------------------------------------------

    async def calibrate_hot_pixels(self) -> None:
        """Their hot-pixel calibration. **The sensor must be dark** — their
        library says so, and running it with light on the array calibrates
        the light away."""
        await self._to_thread(lambda: self._require().calib_noise())

    async def enable_cooling(self) -> None:
        await self._to_thread(lambda: self._require().enable_cooling(1))

    async def disable_cooling(self) -> None:
        await self._to_thread(lambda: self._require().enable_cooling(0))


adapter_registry.register("spad512", SPAD512Adapter)
