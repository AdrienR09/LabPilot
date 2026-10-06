"""Finding a vendor library that does not come from PyPI.

Three adapters here talk to hardware through a DLL that arrives with the
manufacturer's driver installation: both Mad City Labs stages (`Madlib.dll`,
`MicroDrive.dll`) and the PicoHarp 300 (`phlib64.dll`). Each already accepts
a `library=` path for an installation in an unusual place, and each already
searches the usual places itself at connect time.

What was missing is answering the question *before* connecting. A failed
connect is an exception from inside ctypes, and the two things a person needs
to know — is the file there, and is it the right word size — are exactly what
that exception is worst at saying. So this module answers both from the file
on disk, without loading it.

## Why the architecture is read rather than tested by loading

The commonest mistake with any of these is a 32-bit library and a 64-bit
Python. Loading is the obvious test, and it is the wrong one here: it fails
with `WinError 193`, "not a valid Win32 application", which reads like file
corruption, and it has whatever side effects the vendor put in the library's
entry point. A PE file states its target machine in a header field, so
reading four bytes answers the question exactly, with no side effects and on
any platform — a Linux or macOS box can tell you which Windows build of a
DLL you copied over.
"""

from __future__ import annotations

import ntpath
import os
import posixpath
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "LibraryLocation",
    "VendorLibrary",
    "find_library",
    "pe_machine",
]

#: IMAGE_FILE_MACHINE values, from the PE specification. Only the two that a
#: scientific-instrument DLL is realistically built for.
_MACHINES = {0x8664: "64-bit", 0x014C: "32-bit", 0xAA64: "64-bit (ARM)"}

#: The DOS header's `e_lfanew`: where the PE header starts.
_E_LFANEW_OFFSET = 0x3C


def _is_absolute(candidate: str) -> bool:
    r"""Whether a candidate names a place rather than a file to search for.

    Judged under both path conventions, not the running platform's. These
    lists are full of Windows paths, and `os.path.isabs` calls
    r"C:\Program Files\..." relative on POSIX — so classifying with it put
    every one of them in the search-the-PATH bucket anywhere but Windows,
    which is both wrong and invisible on the machine that matters.
    """
    return ntpath.isabs(candidate) or posixpath.isabs(candidate)


@dataclass(frozen=True)
class VendorLibrary:
    """What an adapter needs, and where it is usually installed.

    `parameter` is the connection parameter a found path should be written
    to, which is what lets one UI control serve every adapter here.
    """

    parameter: str
    product: str
    vendor: str
    #: Everything the adapter itself would try, in its own order. Entries are
    #: classified here rather than at the declaration: an absolute path is
    #: checked as a file, a bare name is looked for on the library search
    #: path. Passing the adapter's own list unchanged is what keeps the place
    #: this reports and the place a connect loads from the same place.
    candidates: tuple[str, ...] = ()
    #: Where it comes from, for an error message that has to be actionable.
    installer: str = ""

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(c for c in self.candidates if _is_absolute(c))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c for c in self.candidates if not _is_absolute(c))


@dataclass(frozen=True)
class LibraryLocation:
    """The answer, shaped so a UI can render it without interpreting it."""

    found: bool
    path: str = ""
    #: "64-bit", "32-bit", or "" when it could not be determined.
    architecture: str = ""
    #: This interpreter's word size, so a mismatch is self-evident.
    interpreter: str = ""
    #: True only when the file was found *and* its word size is wrong.
    mismatched: bool = False
    searched: tuple[str, ...] = field(default_factory=tuple)
    message: str = ""


def interpreter_word_size() -> str:
    return "64-bit" if struct.calcsize("P") == 8 else "32-bit"


def pe_machine(path: Path) -> str:
    """The word size a Windows DLL was built for, or "" if not readable.

    Returns "" rather than raising for anything that is not a PE file — an
    `.so`, a text file someone renamed, a truncated download. The caller
    treats an unknown architecture as "cannot tell", never as a mismatch,
    because refusing a library over an unreadable header would be worse
    than letting the load attempt speak for itself.
    """
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"MZ":
                return ""
            handle.seek(_E_LFANEW_OFFSET)
            raw = handle.read(4)
            if len(raw) < 4:
                return ""
            handle.seek(struct.unpack("<I", raw)[0])
            if handle.read(4) != b"PE\0\0":
                return ""
            machine = handle.read(2)
            if len(machine) < 2:
                return ""
    except OSError:
        return ""
    return _MACHINES.get(struct.unpack("<H", machine)[0], "")


def _search_path_hits(names: tuple[str, ...]) -> list[Path]:
    """Where on the library search path each bare name actually resolves.

    `ctypes.util.find_library` is deliberately not used: on Windows it only
    tries the name itself, so it answers the same question as attempting the
    load, and gives no path back to show the user.
    """
    directories = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if sys.platform == "win32":
        directories = [Path.cwd(), *directories]
    return [
        candidate
        for directory in directories
        for name in names
        if (candidate := directory / name).is_file()
    ]


def find_library(spec: VendorLibrary) -> LibraryLocation:
    """Look for `spec`'s library, reporting every place that was tried.

    The search order is the adapter's own: the known installation paths
    first, then the library search path. Which matters, because a machine
    can have both, and the one the adapter will load is the one reported.
    """
    searched: list[str] = []
    word_size = interpreter_word_size()

    found: Path | None = None
    for candidate in spec.paths:
        searched.append(candidate)
        if found is None and Path(candidate).is_file():
            found = Path(candidate)

    hits = _search_path_hits(spec.names)  # bare names, resolved against PATH
    for hit in hits:
        searched.append(str(hit))
        if found is None:
            found = hit
    if spec.names and not hits:
        searched.append(f"{', '.join(spec.names)} (not on PATH)")

    if found is None:
        return LibraryLocation(
            found=False,
            interpreter=word_size,
            searched=tuple(searched),
            message=(
                f"{spec.product}: no {spec.vendor} library found. It comes with "
                f"{spec.installer or 'the vendor driver installation'} rather than "
                f"from PyPI — there is no package to pip-install. Install it, or "
                f"give the full path in the '{spec.parameter}' connection parameter."
            ),
        )

    architecture = pe_machine(found)
    mismatched = bool(architecture) and architecture != word_size
    if mismatched:
        message = (
            f"Found {found}, but it is {architecture} and this Python is "
            f"{word_size}, so it cannot be loaded. {spec.vendor} ship both — "
            f"install the {word_size} build, or run LabPilot under a "
            f"{architecture} Python."
        )
    else:
        message = f"Found {found}."

    return LibraryLocation(
        found=True,
        path=str(found),
        architecture=architecture,
        interpreter=word_size,
        mismatched=mismatched,
        searched=tuple(searched),
        message=message,
    )
