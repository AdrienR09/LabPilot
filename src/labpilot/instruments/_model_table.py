"""Shipped tables of device models, with the user's file merged over them.

Some instruments are not one device but a family of them: every NI DAQ
card is `ni_card` and every Ocean Optics spectrometer is `ocean_optics`,
with the model chosen in the settings. That needs a table of models, and a
table shipped inside a package needs a way for a lab to correct or extend
it — a card NI released last month, a spectrometer whose entry has a typo
in it.

The rule is the one `ui/desktop/block_config.py` arrived at the hard way:
**the packaged file is the base and the user's is merged over it**, entry
by entry and field by field. A user file that *replaced* the packaged one
would silently lose every model added by a later release, and the symptom
would read as "my device isn't supported" rather than as a stale file.
That bug shipped once here already, in the block config, where it hid
every UI block added after a user's first run.

Two smaller rules, both learned from the same place:

- **Nothing is written to the user's path.** A file that exists only to be
  overridden should not appear until someone means to override something.
- **A family carries defaults.** Series-wide facts (an X Series card's
  100 MHz timebase) are stated once and inherited, because a fact repeated
  forty times is a fact that will disagree with itself.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["load_table", "merge_entries"]


def load_table(
    packaged: Path,
    user: Path | None,
    *,
    section: str,
    key: str,
    normalise=str,
) -> dict[str, dict[str, Any]]:
    """Every entry in a model table, keyed and merged, as plain dicts.

    Args:
        packaged: The shipped table.
        user: The lab's overrides. Missing is normal and means "none".
        section: The array-of-tables name — `card`, `spectrometer`.
        key: The field identifying an entry — `number`, `model`.
        normalise: Applied to the key, so `"PCIe-6363"` and `"6363"` are
            the same entry.

    Returns dicts rather than built objects because each caller's model
    class knows its own fields; this only knows the merge rule.
    """
    base = _read(packaged)
    over = _read(user) if user is not None and user.exists() else {}

    merged = merge_entries(
        base.get(section) or (), over.get(section) or (), key=key, normalise=normalise
    )
    families = {**_families(base, key), **_families(over, key)}
    return {
        name: {**families.get(str(entry.get("family", "")), {}), **entry}
        for name, entry in merged.items()
    }


def merge_entries(
    base: Any, over: Any, *, key: str, normalise=str
) -> dict[str, dict[str, Any]]:
    """Packaged entries, with the user's fields written over them.

    An entry the user did not mention survives untouched — that is the
    whole point — and one they invented is kept.
    """
    merged: dict[str, dict[str, Any]] = {}
    for entry in base:
        merged[normalise(entry[key])] = dict(entry)
    for entry in over:
        name = normalise(entry.get(key, ""))
        merged[name] = {**merged.get(name, {}), **entry}
    return merged


def _families(config: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        name: {k: v for k, v in body.items() if k != key}
        for name, body in (config.get("family") or {}).items()
    }


def _read(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)
