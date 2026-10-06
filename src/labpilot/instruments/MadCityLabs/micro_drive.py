"""Mad City Labs Micro-Drive — the coarse stepper stage.

The other half of a two-stage positioner: millimetres of travel under the
Nano-Drive's microns. A confocal rig uses the Micro-Drive to find the
region and the Nano-Drive to scan it.

## Its model is relative; ours is absolute

This is the whole reason this adapter is longer than the Nano-Drive's.
`MCL_MDMove(axis, velocity, distance)` moves a **distance**, not to a
position, and the encoders are what report where the stage actually is.
The framework's `Movable` contract is absolute, so each `move` here is
read the encoder, compute the delta, command it, and wait:

    MCL_MDReadEncoders -> delta -> MCL_MDMove -> MCL_MicroDriveWait

`MCL_MicroDriveWait` blocks for the library's own estimate of the move
time, so it runs on a worker thread like every other adapter call. The
read-back afterwards is the stage's own answer, which is what
`move_and_settle` then checks — and on a stepper that check is not
ceremony: a stalled axis reports the position it stalled at.

## Travel is the one number the device cannot be asked for

`MCL_MDInformation` reports the encoder resolution, the step size and the
velocity limits, so those come from the hardware. It does **not** report
the stage's travel, and nor does anything else in the library — so
`travel_mm` is a constructor argument, and it is the one limit in this
adapter that is a number someone typed. Get it wrong in the generous
direction and a move drives into the mechanical limit; the default is
deliberately 25.4 mm, MCL's common one-inch stage, and
`labpilot probe mcl_micro_drive` plus the limit switches below is how it
gets confirmed.

## The limit switches are active low

`MCL_MDStatus` returns a bitmask in which a **clear** bit means that
limit is reached — bit 0 is axis 1 reverse, bit 1 is axis 1 forward, and
so on up the axes. Reading it the obvious way round reports every axis as
permanently at its limit, which is why the convention is written down
here and tested.

Driven through MCL's `MicroDrive.dll` via ctypes; no PyPI package, so no
extra to install, only their driver. **Not run against hardware** — the
axis count, the travel and the status-bit order are exactly what
`labpilot probe` is for.
"""

from __future__ import annotations

import ctypes
from typing import Any

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.MadCityLabs._madlib import AXIS_NUMBERS, MclLibrary

__all__ = ["MicroDriveAdapter", "limits_reached"]

#: MCL's common one-inch stage. See the module docstring: this is the one
#: number the library cannot be asked for.
DEFAULT_TRAVEL_MM = 25.4

#: Two bits per axis, reverse then forward, and a bit is **clear** when
#: that limit is reached.
_LIMIT_BITS = 2


def limits_reached(status: int, axes: tuple[str, ...]) -> dict[str, str]:
    """Which axes are against a limit switch, and which way.

    `{"x": "reverse"}` means axis x cannot go further in -x. Pure and
    separate from the adapter because the active-low convention is the
    easy thing to invert, and inverting it reports every axis as jammed.
    """
    hit: dict[str, str] = {}
    for index, axis in enumerate(axes):
        for offset, direction in ((0, "reverse"), (1, "forward")):
            bit = 1 << (index * _LIMIT_BITS + offset)
            if not status & bit:
                hit[axis] = direction
    return hit


class _MicroDriveLib(MclLibrary):
    candidates = (
        r"C:\Program Files\Mad City Labs\MicroDrive\MicroDrive.dll",
        # See the Nano-Drive's list: a 32-bit install is tried so that the
        # failure names the word size rather than a missing file.
        r"C:\Program Files (x86)\Mad City Labs\MicroDrive\MicroDrive.dll",
        "MicroDrive.dll",
        "libmicrodrive.so",
    )
    product = "Mad City Labs Micro-Drive"


class MicroDriveAdapter(AdapterBase):
    """A Micro-Drive stepper stage, in millimetres, absolute.

    Args:
        axes: Which axes this controller drives, as a comma list. The
            library does not report a count, so this is declared.
        travel_mm: Travel per axis. The one limit the device cannot be
            asked for — see the module docstring.
        velocity_mm_s: Move speed. Clamped on connect to the limits the
            library reports, which do come from the hardware.
        library: Path to `MicroDrive.dll`, when it is not where MCL's
            installer puts it.
    """

    def __init__(
        self,
        axes: str = "x,y,z",
        travel_mm: float = DEFAULT_TRAVEL_MM,
        velocity_mm_s: float = 1.0,
        library: str = "",
        name: str = "mcl_micro_drive",
    ) -> None:
        super().__init__()
        self._axes = tuple(
            part.strip().lower() for part in axes.split(",") if part.strip()
        ) or ("x",)
        unknown = [axis for axis in self._axes if axis not in AXIS_NUMBERS]
        if unknown:
            raise ValueError(
                f"A Micro-Drive axis must be one of x, y, z; got {unknown}"
            )
        self._travel = float(travel_mm)
        self._velocity = float(velocity_mm_s)
        self._name = name

        self._mcl = _MicroDriveLib(library=library, device=name)
        self._serial = ""
        self._encoder_resolution = 0.0
        self._step_size = 0.0
        self._velocity_limits = (0.0, 0.0)

    # --- What it is --------------------------------------------------------

    @property
    def schema(self) -> DeviceSchema:
        low, high = self._velocity_limits
        return DeviceSchema(
            name=self._name,
            kind="motor",
            parameters=(
                *(
                    Parameter(
                        axis, unit="mm", role=ParamRole.POSITION, settable=True,
                        limits=(0.0, self._travel),
                        description=(
                            "Encoder position. The travel is declared, not "
                            "read — the library does not report it."
                        ),
                    )
                    for axis in self._axes
                ),
                Parameter(
                    "velocity_mm_s", unit="mm/s", settable=True,
                    role=ParamRole.SETTING,
                    limits=(low or None, high or None),
                    description="Move speed; bounds read from the controller",
                ),
                Parameter(
                    "at_limit", dtype="str", role=ParamRole.STATUS,
                    description=(
                        "Axes against a limit switch and which way, or empty"
                    ),
                ),
                Parameter("moving", dtype="bool", role=ParamRole.STATUS),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter(
                    "encoder_resolution", unit="mm", role=ParamRole.STATUS,
                    description="What a position read-back can resolve",
                ),
                Parameter(
                    "step_size", unit="mm", role=ParamRole.STATUS,
                    description="One microstep — the finest move that differs",
                ),
                Parameter("attached", dtype="bool", role=ParamRole.STATUS),
            ),
            actions=["stop", "zero_encoders"],
            tags=[
                "Mad City Labs", "MCL", "Micro-Drive", "stepper", "motor",
                "coarse", "confocal",
            ],
        )

    # --- Connection --------------------------------------------------------

    def _connect_sync(self) -> None:
        self._mcl.load()
        self._mcl.claim()
        try:
            self._serial = self._mcl.serial_number()
            self._read_information()
        except Exception:
            self._mcl.release()
            raise

    def _read_information(self) -> None:
        """Encoder resolution, step size and the velocity bounds.

        All six come back as doubles through pointers in one call. The
        velocity bounds are then applied to the requested speed, so a
        constructor default of 1 mm/s on a stage whose ceiling is 0.5
        becomes 0.5 rather than an error on the first move.
        """
        values = [ctypes.c_double(0) for _ in range(6)]
        self._mcl.check(
            self._mcl.dll.MCL_MDInformation(
                *(ctypes.byref(value) for value in values), self._mcl.handle
            ),
            "MCL_MDInformation",
        )
        encoder, step, max_one, _max_two, _max_three, minimum = (
            value.value for value in values
        )
        self._encoder_resolution = float(encoder)
        self._step_size = float(step)
        self._velocity_limits = (float(minimum), float(max_one))
        if max_one > 0:
            self._velocity = min(max(self._velocity, float(minimum)), float(max_one))

    def _disconnect_sync(self) -> None:
        self._mcl.release()

    def _self_test_sync(self) -> None:
        if not self._mcl.attached(100):
            raise DeviceError("The Micro-Drive stopped answering", device=self._name)

    # --- Reading ------------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        positions = self._encoders()
        at_limit = limits_reached(self._status(), self._axes)
        reading: dict[str, Any] = dict(zip(self._axes, positions, strict=False))
        reading.update(
            velocity_mm_s=self._velocity,
            at_limit=", ".join(
                f"{axis} {way}" for axis, way in sorted(at_limit.items())
            ),
            moving=self._moving(),
            serial_number=self._serial,
            encoder_resolution=self._encoder_resolution,
            step_size=self._step_size,
            attached=self._mcl.attached(0),
        )
        return reading

    def _encoders(self) -> list[float]:
        """All four encoders in one call; we keep the axes we declared.

        `MCL_MDReadEncoders` always fills four, whatever the stage has,
        which is why the axis list is declared rather than inferred from
        how many came back.
        """
        values = [ctypes.c_double(0) for _ in range(4)]
        self._mcl.check(
            self._mcl.dll.MCL_MDReadEncoders(
                *(ctypes.byref(value) for value in values), self._mcl.handle
            ),
            "MCL_MDReadEncoders",
        )
        return [value.value for value in values[: len(self._axes)]]

    def _status(self) -> int:
        status = ctypes.c_ushort(0)
        self._mcl.check(
            self._mcl.dll.MCL_MDStatus(ctypes.byref(status), self._mcl.handle),
            "MCL_MDStatus",
        )
        return int(status.value)

    def _moving(self) -> bool:
        moving = ctypes.c_int(0)
        try:
            code = self._mcl.dll.MCL_MicroDriveMoveStatus(
                ctypes.byref(moving), self._mcl.handle
            )
        except Exception:
            return False
        return bool(moving.value) if int(code) == 0 else False

    # --- Moving -------------------------------------------------------------

    def _move_to(self, axis: str, target: float) -> None:
        """Absolute, out of a library that only does relative.

        The delta is computed from the encoder rather than from a
        remembered setpoint: a stepper that stalled, or that someone
        nudged by hand, is at a position nothing in this process knows.
        """
        index = self._axes.index(axis)
        here = self._encoders()[index]
        delta = float(target) - here
        if abs(delta) < max(self._step_size, 0.0):
            # Smaller than one microstep: the controller would either
            # refuse it or move a whole step, and a whole step is not what
            # was asked for.
            return
        self._mcl.check(
            self._mcl.dll.MCL_MDMove(
                ctypes.c_uint(AXIS_NUMBERS[axis]),
                ctypes.c_double(self._velocity),
                ctypes.c_double(delta),
                self._mcl.handle,
            ),
            f"MCL_MDMove({axis} by {delta:+g} mm)",
        )
        self._mcl.check(
            self._mcl.dll.MCL_MicroDriveWait(self._mcl.handle),
            "MCL_MicroDriveWait",
        )

    async def set_x(self, value: float) -> None:
        await self._to_thread(self._move_to, "x", value)

    async def set_y(self, value: float) -> None:
        await self._to_thread(self._move_to, "y", value)

    async def set_z(self, value: float) -> None:
        await self._to_thread(self._move_to, "z", value)

    async def set_velocity_mm_s(self, value: float) -> None:
        low, high = self._velocity_limits
        speed = float(value)
        if high > 0:
            speed = min(max(speed, low), high)
        self._velocity = speed

    # --- Actions -------------------------------------------------------------

    async def stop(self) -> None:
        """Halt every axis now.

        What an aborted run calls, so it must be safe when nothing is
        moving — and on a stepper it is the difference between an abort
        and an abort that keeps travelling.
        """
        status = ctypes.c_ushort(0)
        await self._to_thread(
            lambda: self._mcl.check(
                self._mcl.dll.MCL_MDStop(ctypes.byref(status), self._mcl.handle),
                "MCL_MDStop",
            )
        )

    async def zero_encoders(self) -> None:
        """Call this position zero.

        Not a home: nothing moves, and the stage's relationship to its
        mechanical limits is unchanged. It is how an absolute coordinate
        system gets an origin on a stage that has no absolute reference.
        """
        status = ctypes.c_ushort(0)
        await self._to_thread(
            lambda: self._mcl.check(
                self._mcl.dll.MCL_MDResetEncoders(
                    ctypes.byref(status), self._mcl.handle
                ),
                "MCL_MDResetEncoders",
            )
        )


adapter_registry.register("mcl_micro_drive", MicroDriveAdapter)
