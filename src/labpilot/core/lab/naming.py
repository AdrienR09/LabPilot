"""Turning the name someone typed into the id everything else uses.

An instrument has two strings: a `name`, which is a label for a human, and
an `id`, which is how every other part of the system refers to it —
`lp["my_APD"]`, a workflow's instrument binding, the REST path
`/instruments/<id>/connect`, the key under which a spec is saved.

Those two used to be unrelated. The Devices dialog required a name, sent
it as `name`, and the id was invented from a counter, so naming a detector
`my_APD` produced the id `mock_basic_detector_0d_3` and there was no way
to reach the instrument by the name you had just given it. The name was
stored, displayed, and ignored by everything that mattered.

So the id is now derived from the name. Two properties are worth stating
because they are the reason this is a function and not an f-string:

- **Case is preserved.** Someone who types `my_APD` means `my_APD`, and
  that is also what makes `lp.my_APD` possible later. A name that starts
  with a digit (`532 laser` -> `532_laser`) is a valid id and a valid dict
  key, but not a Python identifier, so it is reachable as `lp["532_laser"]`
  and not as an attribute.
- **Ids are allocated against what already exists**, not from a count.
  The counter it replaces was `len(lab) + 1`, which collides after a
  delete: remove one of three instruments and the next one created is
  offered the id of a survivor, and the create fails with "already
  exists".

Renaming an instrument deliberately does *not* change its id. The id is
what saved configs, workflow bindings and scripts hold; a label is cheap
to change and an identity is not.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Container

__all__ = ["MAX_ID_LENGTH", "slug", "unique_id"]

#: Long enough for any name a person types, short enough to stay readable
#: in a URL, a filename and an HDF5 attribute.
MAX_ID_LENGTH = 64

_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9_]+")


def slug(text: str) -> str:
    """`text` as an id: letters, digits and underscores, case intact.

    Returns `""` for a name with nothing usable in it (`"???"`), which the
    caller resolves — there is no sensible universal fallback here, and
    inventing one would hide the fact that the name was unusable.
    """
    cleaned = _NOT_ALLOWED.sub("_", text.strip())
    cleaned = re.sub(r"_{2,}", "_", cleaned).strip("_")
    return cleaned[:MAX_ID_LENGTH].strip("_")


def unique_id(preferred: str, taken: Container[str], *, fallback: str = "instrument") -> str:
    """`preferred` as an id that is not in `taken`, suffixing if it is.

    `fallback` is used when `preferred` slugs to nothing. Suffixes start at
    2, so the first instrument called `APD` is `APD` rather than `APD_1` —
    the numbering only appears once there is something to distinguish.
    """
    base = slug(preferred) or slug(fallback) or "instrument"
    if base not in taken:
        return base
    stem = base[: MAX_ID_LENGTH - 4].strip("_") or base
    for number in range(2, 1000):
        candidate = f"{stem}_{number}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"cannot find a free id based on {base!r}")
