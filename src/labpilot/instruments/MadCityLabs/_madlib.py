"""Shared plumbing for Mad City Labs' two libraries.

MCL ship two separate DLLs with two separate APIs — `Madlib.dll` for the
closed-loop Nano-Drive piezo controllers and `MicroDrive.dll` for the
stepper stages — but they share their handle model, their error codes and
their axis numbering, so those live here and the two adapters differ only
where the hardware does.

## Error codes are negative returns, not exceptions

Every call returns `MCL_SUCCESS` (0) or one of eight negative codes, and
some calls return a *position* as a double where a negative value is
instead an error code. That ambiguity is real and is the reason
`checked_position` exists: a travel range always starts at 0, so a
negative reading can only be a code — but it has to be recognised rather
than plotted.

## Axes are 1-based

X=1, Y=2, Z=3, and the Nano-Drive reports which of them physically exist
as a bitmap. Taking that bitmap seriously is what stops a two-axis stage
from advertising a Z it does not have — which would otherwise be a
settable control that silently fails.

## Handles are claimed, and `MCL_ReleaseAllHandles` is not called

Both of the open wrappers this was checked against call
`MCL_ReleaseAllHandles()` before taking their own handle. That is
convenient for a single-stage rig and wrong in general: it releases the
handle any *other* process or adapter is holding on the same library, so
two Nano-Drives cannot be used at once and a second window silently steals
the first one's stage. This takes one handle and releases only that one.

Verified against MCL's error codes and product-information layout as used
by two independent open implementations (ScopeFoundry's `HW_mcl_stage` and
ZhuangLab's `storm-control`), which agree on the signatures, the 1-based
axes and the packed `ProductInformation` struct. **Not run against
hardware** — `labpilot probe` is what settles that.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from typing import Any

from labpilot.core.errors import DeviceError

__all__ = [
    "AXIS_NUMBERS",
    "ERROR_CODES",
    "MclLibrary",
    "ProductInformation",
    "describe_code",
]

#: X, Y, Z as the libraries number them. Not an implementation detail: a
#: 0-based call moves the wrong axis, or none.
AXIS_NUMBERS = {"x": 1, "y": 2, "z": 3}

ERROR_CODES = {
    0: "MCL_SUCCESS",
    -1: "MCL_GENERAL_ERROR",
    -2: "MCL_DEV_ERROR",
    -3: "MCL_DEV_NOT_ATTACHED",
    -4: "MCL_USAGE_ERROR",
    -5: "MCL_DEV_NOT_READY",
    -6: "MCL_ARGUMENT_ERROR",
    -7: "MCL_INVALID_AXIS",
    -8: "MCL_INVALID_HANDLE",
}

_EXPLAIN = {
    -3: "the controller is not attached — check it is powered on and the USB cable",
    -4: "the library was used in a way it does not allow (often two handles to one device)",
    -5: "the controller is attached but not ready yet",
    -7: "that axis does not exist on this stage",
    -8: "the handle is stale — the device was released or disconnected",
}


def describe_code(code: int) -> str:
    """An MCL return code as something worth reading."""
    name = ERROR_CODES.get(int(code), f"unknown code {code}")
    reason = _EXPLAIN.get(int(code))
    return f"{name}: {reason}" if reason else name


class ProductInformation(ctypes.Structure):
    """`MCL_GetProductInfo`'s output.

    `_pack_ = 1` matters: a `c_ubyte` followed by five `c_short`s is
    padded by default, and the unpacked reading puts every field after the
    first one byte late — so the axis bitmap survives and everything else
    is nonsense.
    """

    _pack_ = 1
    _fields_ = [
        ("axis_bitmap", ctypes.c_ubyte),
        ("ADC_resolution", ctypes.c_short),
        ("DAC_resolution", ctypes.c_short),
        ("Product_id", ctypes.c_short),
        ("FirmwareVersion", ctypes.c_short),
        ("FirmwareProfile", ctypes.c_short),
    ]

    def axes(self) -> tuple[str, ...]:
        """Which of x, y, z this unit actually has."""
        return tuple(
            name for name, number in AXIS_NUMBERS.items()
            if self.axis_bitmap & (1 << (number - 1))
        )


class MclLibrary:
    """One loaded MCL library plus one claimed handle.

    Subclassed rather than parameterised because the two libraries'
    *calls* differ; what they share is everything in here.
    """

    #: Where MCL's installer puts it, plus the bare name for a DLL that is
    #: already on the search path.
    candidates: tuple[str, ...] = ()
    product: str = "Mad City Labs device"
    #: Functions returning a double rather than an int. ctypes assumes
    #: `int`, so a position read without this comes back as garbage —
    #: silently, and in roughly the right order of magnitude.
    doubles: tuple[str, ...] = ()

    def __init__(self, library: str = "", device: str = "") -> None:
        self.device = device or self.product
        self._path = library
        self._dll: Any = None
        self._handle = 0

    # --- Loading ----------------------------------------------------------

    def load(self) -> None:
        paths = [self._path] if self._path else list(self.candidates)
        errors = []
        for path in paths:
            try:
                # cdecl, not stdcall: both of MCL's libraries are cdecl and
                # both open wrappers load them with `cdll`.
                self._dll = ctypes.CDLL(path)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            for name in self.doubles:
                getattr(self._dll, name).restype = ctypes.c_double
            return
        raise ImportError(
            f"Talking to a {self.product} needs Mad City Labs' own library, "
            f"which comes with their driver installation rather than from "
            f"PyPI — there is no package to pip-install. Pass library=<path> "
            f"if it is installed somewhere else.\n  " + "\n  ".join(errors)
            + ("" if sys.platform == "win32" else
               "\n  MCL ship Windows libraries; this is not Windows.")
        )

    # --- Handles ----------------------------------------------------------

    def claim(self) -> None:
        handle = int(self._dll.MCL_InitHandle())
        if handle <= 0:
            raise DeviceError(
                f"No {self.product} answered. It is either powered off, "
                f"unplugged, or already claimed by another program — MCL's "
                f"library allows one handle per device.",
                device=self.device,
            )
        self._handle = handle

    def release(self) -> None:
        """Only our own handle — see the module docstring."""
        if self._dll is not None and self._handle:
            with contextlib.suppress(Exception):
                self._dll.MCL_ReleaseHandle(self._handle)
        self._handle = 0

    @property
    def handle(self) -> int:
        if not self._handle:
            raise DeviceError(f"{self.device} is not connected", device=self.device)
        return self._handle

    @property
    def dll(self) -> Any:
        if self._dll is None:
            raise DeviceError(f"{self.device} is not connected", device=self.device)
        return self._dll

    # --- Calls ------------------------------------------------------------

    def check(self, code: int, what: str) -> None:
        """Raise unless `code` is `MCL_SUCCESS`."""
        if int(code) == 0:
            return
        raise DeviceError(
            f"{what} failed — {describe_code(int(code))}", device=self.device
        )

    def checked_position(self, value: float, what: str) -> float:
        """A double that is either a position or an error code.

        Several MCL calls overload their return this way. Travel starts at
        zero, so a negative value cannot be a position — but it has to be
        *recognised* rather than carried into a dataset, where it would
        look like a stage that had travelled backwards past its own home.
        """
        number = float(value)
        if number < 0 and int(number) in ERROR_CODES:
            raise DeviceError(
                f"{what} failed — {describe_code(int(number))}", device=self.device
            )
        return number

    def serial_number(self) -> str:
        try:
            return str(int(self.dll.MCL_GetSerialNumber(self.handle)))
        except Exception:
            return ""

    def attached(self, wait_ms: int = 0) -> bool:
        """Whether the controller is answering, waiting up to `wait_ms`."""
        try:
            return bool(self.dll.MCL_DeviceAttached(ctypes.c_uint(wait_ms), self.handle))
        except Exception:
            return False
