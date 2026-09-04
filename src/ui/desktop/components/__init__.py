"""UI component library for native instrument windows.

Importing this package registers every built-in component (via
`ComponentMeta` in `base.py`) into `COMPONENT_REGISTRY`, so
`instrument_window.py` can build a window purely from the block list in
`ui_blocks.toml` without importing each component module by name.
"""

from components.base import COMPONENT_REGISTRY, ComponentMeta, UIComponent
from components import (  # noqa: F401 — import for registration side effect
    toolbar,
    viewer,
    settings_tree,
    move_controls,
    poll_rate,
    time_series,
    hyperspectral_viewer,
    actions,
    pulse_sequence,
)

__all__ = ["COMPONENT_REGISTRY", "ComponentMeta", "UIComponent"]
