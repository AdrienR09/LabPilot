"""Saved sequences on disk — the file the editor writes and a measurement reads.

The authoring/execution split turns on this being a *file*. The sequence
editor binds no instruments and its whole output is one of these; the
pulsed measurement workflow's input is a name that resolves to one. So a
sequence is named, versioned, diffable, shareable, and reusable across
every experiment that wants it — rather than a blob inside one
measurement's parameters, which is what happens when the editor and the
measurement are the same window.

**JSON, never pickle.** Qudi pickles its pulse objects and pays across
~300 lines of loader: migration shims, a `ModuleNotFoundError` guard for
sequences saved under an older package layout, and a `# FIXME` repairing
an object its own pickle had destroyed. A dict of numbers survives a
version change, a machine change and a text editor.

**Device-independent by construction.** What is stored is the abstract
sequence — symbolic channels, seconds, volts. Nothing here knows a sample
rate or a channel number, because the editor that wrote the file did not
know which pulser would play it. See `sampling.py` for who does.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from labpilot.core.config.paths import sequence_dir
from labpilot.core.pulse.sequence import PulseSequence, SequenceError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "SavedSequence",
    "delete_sequence",
    "ensure_default_sequences",
    "list_sequences",
    "load_sequence",
    "save_sequence",
    "slug",
]

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def slug(name: str) -> str:
    """A sequence name as a filename.

    A sequence's display name is the physicist's ("Hahn echo, sample B"),
    and it is not a filename. The file gets a slug; the display name is
    kept inside the JSON and is what the library view shows.
    """
    cleaned = _UNSAFE.sub("_", name.strip()).strip("_")
    if not cleaned:
        raise SequenceError(
            f"Sequence name {name!r} has no characters usable in a filename"
        )
    return cleaned.lower()


@dataclass(frozen=True, slots=True)
class SavedSequence:
    """One entry in the sequence library.

    Summary facts only — enough to populate a list without parsing every
    file's blocks, and all of them derived rather than stored, so a
    hand-edited file cannot claim a point count it does not have.
    """

    slug: str
    name: str
    path: Path
    description: str = ""
    points: int = 0
    readouts: int = 0
    duration: float = 0.0
    channels: tuple[str, ...] = ()
    valid: bool = True
    problem: str = ""
    """Why this file will not load or will not play. A broken sequence is
    listed and marked, not hidden — otherwise a typo makes a file vanish
    and the user goes looking for it on disk."""


def save_sequence(sequence: PulseSequence, directory: Path | None = None) -> Path:
    """Write a sequence to `~/.labpilot/sequences/<slug>.json`.

    Validated first, so an unplayable sequence never becomes a file that
    someone loads a month later and blames the hardware for.
    """
    sequence.validate()
    target = directory or sequence_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{slug(sequence.name)}.json"
    path.write_text(json.dumps(sequence.to_dict(), indent=2) + "\n")
    return path


#: The experiments a fresh install can run without authoring anything.
#: Names match the four presets of `pulsed_measurement`.
DEFAULTS = ("rabi", "ramsey", "hahn_echo", "t1")


def ensure_default_sequences(directory: Path | None = None) -> list[Path]:
    """Write the four standard experiments, if they are not there already.

    A fresh install has an empty sequence library, so the Rabi preset
    would fail on a missing file before it ever reached hardware. These
    are generated from `library.py` against the default rig profile —
    which is the same thing the editor's Generate button does, written to
    the same place, so they are ordinary files to open and edit rather
    than anything special.

    Never overwrites: an edited `rabi.json` is the user's, and silently
    restoring the shipped one would undo an afternoon of calibration.
    """
    from labpilot.core.pulse.library import RigProfile, build

    target = directory or sequence_dir()
    written: list[Path] = []
    profile = RigProfile()
    for name in DEFAULTS:
        if (target / f"{slug(name)}.json").exists():
            continue
        written.append(save_sequence(build(name, profile), target))
    return written


def load_sequence(name: str, directory: Path | None = None) -> PulseSequence:
    """Read a saved sequence by name or slug.

    Not validated on load: a file may predate a rule, and refusing to open
    it would leave the user no way to see or fix what is wrong. The pulser
    validates before it uploads, which is where it matters.
    """
    source = directory or sequence_dir()
    path = source / f"{slug(name)}.json"
    if not path.exists():
        known = ", ".join(entry.slug for entry in list_sequences(source)) or "none"
        raise SequenceError(f"No saved sequence named {name!r} — saved: {known}")
    return PulseSequence.from_dict(json.loads(path.read_text()))


def delete_sequence(name: str, directory: Path | None = None) -> None:
    source = directory or sequence_dir()
    path = source / f"{slug(name)}.json"
    if not path.exists():
        raise SequenceError(f"No saved sequence named {name!r}")
    path.unlink()


def list_sequences(directory: Path | None = None) -> list[SavedSequence]:
    """Every saved sequence, summarised, sorted by name.

    A file that will not parse is returned with `valid=False` and the
    reason, rather than raising — one bad file must not make the library
    unopenable.
    """
    source = directory or sequence_dir()
    if not source.is_dir():
        return []

    entries: list[SavedSequence] = []
    for path in sorted(source.glob("*.json")):
        entries.append(_summarise(path))
    return sorted(entries, key=lambda entry: entry.name.lower())


def _summarise(path: Path) -> SavedSequence:
    try:
        sequence = PulseSequence.from_dict(json.loads(path.read_text()))
    except Exception as error:  # any malformed file: reported, never raised
        return SavedSequence(
            slug=path.stem, name=path.stem, path=path,
            valid=False, problem=f"{type(error).__name__}: {error}",
        )

    problem = ""
    try:
        sequence.validate()
    except SequenceError as error:
        problem = str(error)

    return SavedSequence(
        slug=path.stem,
        name=sequence.name,
        path=path,
        description=sequence.description,
        points=sequence.points,
        readouts=sequence.readouts(),
        duration=sequence.duration,
        channels=tuple(sorted(sequence.channels)),
        valid=not problem,
        problem=problem,
    )
