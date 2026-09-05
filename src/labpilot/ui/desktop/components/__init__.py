"""UI component library for native instrument windows.

Importing this package registers every built-in component (via
`ComponentMeta` in `base.py`) into `COMPONENT_REGISTRY`, so
`instrument_window.py` can build a window purely from the block list in
`ui_blocks.toml` without importing each component module by name.
"""

from components import (  # noqa: F401 — import for registration side effect
    actions,
    hyperspectral_viewer,
    move_controls,
    poll_rate,
    pulse_sequence,
    settings_tree,
    time_series,
    toolbar,
    viewer,
)
from components.base import COMPONENT_REGISTRY, ComponentMeta, UIComponent

__all__ = ["COMPONENT_REGISTRY", "ComponentMeta", "UIComponent"]
