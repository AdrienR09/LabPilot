"""Mad City Labs Nano-Drive — the closed-loop piezo stage.

The fine positioner a confocal scan actually moves. Closed-loop, so a
commanded position is read back from the stage's own sensor rather than
assumed, which is exactly what `move_and_settle`
(`core/device/motion.py`) is built to wait on: the scan's next point is
not taken until the stage says it has arrived.

## The stage says how far it goes

`MCL_GetCalibration(axis)` returns that axis's travel in microns, and
`MCL_GetProductInfo` returns a bitmap of which axes physically exist. So
the schema is built from the device: a 100 um XY stage declares
`(0, 100)` on x and y and **no z at all**, rather than offering a third
control that silently fails. Both come from the hardware, which is the
difference between a limit that protects the stage and a limit someone
typed from a datasheet.

That matters here more than on most instruments. A piezo's limits are its
whole safety story — there is no mechanical slip to absorb an over-travel
command — and `validate_write` enforces exactly these numbers.

## Positions are absolute, in microns

`MCL_SingleWriteN(position, axis, handle)` commands an absolute position
and `MCL_SingleReadN(axis, handle)` reads the sensor. Nothing is relative
and nothing needs homing, which is why this adapter is short: the
Nano-Drive's model and the framework's `Movable` contract are the same
model.

One trap, handled: `MCL_SingleReadN` returns a *double* that is either a
position or a negative error code. Travel starts at zero, so a negative
reading cannot be a position — but it has to be recognised rather than
recorded, where it would look like a stage that had travelled backwards
past its own home.

Driven through MCL's `Madlib.dll` via ctypes; there is no PyPI package, so
there is no extra to install, only their driver. Loaded inside
`_connect_sync`, so this adapter registers, describes itself and is
probeable on a machine that has never had one. **Not run against
hardware** — `labpilot probe mcl_nano_drive` is what settles the travel
ranges and the axis count.
"""

from __future__ import annotations

import ctypes
from typing import Any

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments._vendor_library import VendorLibrary
from labpilot.instruments.MadCityLabs._madlib import (
    AXIS_NUMBERS,
    MclLibrary,
    ProductInformation,
)

__all__ = ["NanoDriveAdapter"]

#: What the schema declares before the stage has been asked. Deliberately
#: the smallest common Nano-Drive travel rather than the largest: a limit
#: that is too small refuses a legal move with a clear error, while one
#: that is too large accepts a command the piezo cannot honour.
DEFAULT_TRAVEL_UM = 100.0


class _Madlib(MclLibrary):
    candidates = (
        r"C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll",
        r"C:\Program Files\Mad City Labs\NanoDrive\madlib.dll",
        # A 32-bit installation, which lands here on 64-bit Windows. Tried on
        # purpose even though it cannot load into 64-bit Python: finding it
        # and failing on the word size says what is wrong, where leaving it
        # out just says the file does not exist.
        r"C:\Program Files (x86)\Mad City Labs\NanoDrive\Madlib.dll",
        "Madlib.dll",
        "libmadlib.so",
    )
    product = "Mad City Labs Nano-Drive"
    doubles = ("MCL_SingleReadN", "MCL_GetCalibration", "MCL_MonitorN")


class NanoDriveAdapter(AdapterBase):
    """A Nano-Drive piezo stage, in microns, absolute.

    Args:
        axes: Which axes to expose, or empty to take whatever the stage
            reports. Naming them is for a rig where only two of a
            three-axis controller are wired.
        library: Path to `Madlib.dll`, when it is not where MCL's
            installer puts it.
    """

    def __init__(
        self,
        axes: str = "",
        library: str = "",
        name: str = "mcl_nano_drive",
    ) -> None:
        super().__init__()
        self._wanted = tuple(
            part.strip().lower() for part in axes.split(",") if part.strip()
        )
        self._library = library
        self._name = name

        self._mcl = _Madlib(library=library, device=name)
        self._axes: tuple[str, ...] = self._wanted or ("x", "y", "z")
        self._travel: dict[str, float] = dict.fromkeys(self._axes, DEFAULT_TRAVEL_UM)
        self._info = ProductInformation()
        self._serial = ""

    @classmethod
    def vendor_library(cls) -> VendorLibrary:
        """What `library=` wants, for the UI's "find it for me" control.

        The candidate list is `_Madlib`'s own, so the place the UI reports
        is the place a connect will actually load from.
        """
        return VendorLibrary(
            parameter="library",
            product="Mad City Labs Nano-Drive",
            vendor="Mad City Labs",
            candidates=_Madlib.candidates,
            installer="Mad City Labs' Nano-Drive driver installation",
        )

    # --- What it is --------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            parameters=(
                *(
                    Parameter(
                        axis, unit="um", role=ParamRole.POSITION, settable=True,
                        limits=(0.0, self._travel[axis]),
                        description=(
                            f"Closed-loop {axis} position. Travel read from "
                            f"the stage."
                        ),
                    )
                    for axis in self._axes
                ),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter("product_id", dtype="i8", role=ParamRole.STATUS),
                Parameter("firmware_version", dtype="i8", role=ParamRole.STATUS),
                Parameter(
                    "adc_bits", dtype="i8", role=ParamRole.STATUS,
                    description="Sensor resolution — what a read-back can resolve",
                ),
                Parameter(
                    "dac_bits", dtype="i8", role=ParamRole.STATUS,
                    description="Command resolution — the finest step that differs",
                ),
                Parameter("attached", dtype="bool", role=ParamRole.STATUS),
            ),
            tags=[
                "Mad City Labs", "MCL", "Nano-Drive", "piezo", "nanopositioner",
                "motor", "closed-loop", "confocal",
            ],
        )

    # --- Connection --------------------------------------------------------

    def _connect_sync(self) -> None:
        self._mcl.load()
        self._mcl.claim()
        try:
            self._mcl.check(
                self._mcl.dll.MCL_GetProductInfo(
                    ctypes.byref(self._info), self._mcl.handle
                ),
                "MCL_GetProductInfo",
            )
            self._serial = self._mcl.serial_number()
            self._learn_axes()
        except Exception:
            self._mcl.release()
            raise

    def _learn_axes(self) -> None:
        """Take the axis bitmap and the per-axis calibration seriously.

        A controller reports which axes exist; offering one it does not
        have is a control in the settings window that fails on use, and a
        scan axis a plan will happily try to step.
        """
        present = self._info.axes()
        if not present:
            raise DeviceError(
                "The Nano-Drive reports no axes at all, which means the "
                "product information did not come back — the handle is "
                "probably to a device that is attached but not ready.",
                device=self._name,
            )
        if self._wanted:
            missing = [axis for axis in self._wanted if axis not in present]
            if missing:
                raise DeviceError(
                    f"This Nano-Drive has axes {', '.join(present)}; "
                    f"{', '.join(missing)} was asked for and does not exist.",
                    device=self._name,
                )
            self._axes = self._wanted
        else:
            self._axes = present

        self._travel = {
            axis: self._mcl.checked_position(
                self._mcl.dll.MCL_GetCalibration(AXIS_NUMBERS[axis], self._mcl.handle),
                f"MCL_GetCalibration({axis})",
            )
            for axis in self._axes
        }

    def _disconnect_sync(self) -> None:
        self._mcl.release()

    def _self_test_sync(self) -> None:
        if not self._mcl.attached(100):
            raise DeviceError("The Nano-Drive stopped answering", device=self._name)

    # --- Reading and writing ----------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        reading: dict[str, Any] = {
            axis: self._position(axis) for axis in self._axes
        }
        reading.update(
            serial_number=self._serial,
            product_id=int(self._info.Product_id),
            firmware_version=int(self._info.FirmwareVersion),
            adc_bits=int(self._info.ADC_resolution),
            dac_bits=int(self._info.DAC_resolution),
            attached=self._mcl.attached(0),
        )
        return reading

    def _position(self, axis: str) -> float:
        return self._mcl.checked_position(
            self._mcl.dll.MCL_SingleReadN(AXIS_NUMBERS[axis], self._mcl.handle),
            f"MCL_SingleReadN({axis})",
        )

    def _write_axis(self, axis: str, value: float) -> None:
        self._mcl.check(
            self._mcl.dll.MCL_SingleWriteN(
                ctypes.c_double(float(value)),
                AXIS_NUMBERS[axis],
                self._mcl.handle,
            ),
            f"MCL_SingleWriteN({axis}={value:g} um)",
        )

    async def set_x(self, value: float) -> None:
        await self._to_thread(self._write_axis, "x", value)

    async def set_y(self, value: float) -> None:
        await self._to_thread(self._write_axis, "y", value)

    async def set_z(self, value: float) -> None:
        await self._to_thread(self._write_axis, "z", value)


adapter_registry.register("mcl_nano_drive", NanoDriveAdapter)
