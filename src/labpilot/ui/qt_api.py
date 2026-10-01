"""Pin the Qt binding, once, before anything can pick a different one.

`qtpy` chooses a binding the first time it is imported, and if `QT_API`
is unset it auto-picks — preferring PyQt5 where one happens to be
installed alongside our PyQt6, which silently mixes two incompatible Qt
bindings in one process and crashes. LabPilot uses PyQt6 and only PyQt6:
every widget module imports `PyQt6.*` directly.

Importing this module sets the variable. It is imported by
`labpilot/ui/__init__.py` and by `components/__init__.py`, which between
them are on the path of every way into this app, so it is no longer
possible to reach a Qt widget without having passed through here.

It used to be four copies of the same `setdefault` line, one per window
module that someone remembered to add it to. Everything else — the
component modules, which are what actually pull in the viewer toolkit and
therefore qtpy — relied on being imported *after* one of those four. That
held when the app started from its own entry point and failed the first
time anything imported a component directly.

`setdefault`, not assignment: someone running with a deliberately chosen
`QT_API` keeps it.
"""

from __future__ import annotations

import os
import warnings

__all__ = ["QT_API"]

QT_API = "pyqt6"

os.environ.setdefault("QT_API", QT_API)

# `pymodaq_gui` does not honour the variable: on import it *assigns*
# `os.environ["QT_API"]` from the first entry of its own config's backend
# list, which defaults to PyQt5, and only then imports qtpy. Where PyQt5
# is listed but not importable, qtpy warns and falls back — to PyQt6, the
# binding we require and the one already loaded.
#
# So the outcome is right and the warning is about how it got there. It is
# ignored by exact message rather than by category, because a fallback to
# any *other* binding is a genuine problem and must still be heard: two
# incompatible Qt bindings in one process is a crash, which is the whole
# reason this module exists.
warnings.filterwarnings(
    "ignore",
    message=r"Selected binding .* could not be found; falling back to 'pyqt6'",
)
