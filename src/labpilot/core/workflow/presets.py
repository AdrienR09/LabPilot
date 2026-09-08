"""Named presets of a template — a configuration, not a second program.

Four of the workflow templates were near-duplicates of `omniscan`: a
1-D sweep, a 2-D raster, a confocal map and a hyperspectral cube. Each had
its own file with its own hand-written loop, and what actually
distinguished them was the ranges they defaulted to and the names they gave
their result keys. `ARCHITECTURE_NOTES` put it plainly: they existed
*because* a result could not describe itself, so every variant needed its
own `RESULT_UI` and therefore its own module.

Once `Run` owned the loop and `Dataset` made a result self-describing, what
was left of each was a params dict. A preset is that dict, plus a name and
a description, declared in `workflow_templates/presets.toml`.

It needs no machinery of its own because loading a template already
produces a *row* rather than a copy of the source (see
`POST /api/workflows/templates/{name}/load`): a workflow instance is a
script path, a parameters dict and a bindings dict. A preset supplies a
different parameters dict against the same script path. That is the whole
mechanism.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Preset", "load_presets", "presets_path"]


class Preset:
    """One named configuration of a template."""

    __slots__ = ("description", "name", "params", "template")

    def __init__(
        self, name: str, template: str, description: str, params: Mapping[str, Any]
    ) -> None:
        self.name = name
        self.template = template
        self.description = description.strip()
        self.params = dict(params)

    def __repr__(self) -> str:
        return f"<Preset {self.name!r} of {self.template!r}>"


def presets_path() -> Path:
    """The packaged preset declarations."""
    import labpilot.core.workflow_templates as templates

    return Path(templates.__path__[0]) / "presets.toml"


def load_presets(path: Path | None = None) -> dict[str, Preset]:
    """Every declared preset, by name.

    A malformed entry is skipped with a warning rather than raised on: one
    bad preset must not cost you the template library. `tests/test_presets.py`
    is where a bad entry is meant to be caught.
    """
    path = path or presets_path()
    if not path.exists():
        return {}
    try:
        declared = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        print(f"⚠️  Could not read workflow presets: {e}")
        return {}

    presets: dict[str, Preset] = {}
    for name, entry in declared.items():
        template = entry.get("template") if isinstance(entry, dict) else None
        if not template:
            print(f"⚠️  Preset {name!r} names no base template — skipped")
            continue
        presets[name] = Preset(
            name=name,
            template=str(template),
            description=str(entry.get("description", "")),
            params=entry.get("params") or {},
        )
    return presets
