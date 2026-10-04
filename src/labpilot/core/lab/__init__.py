"""The lab model: which instruments exist, and which of them are live.

Two records where there used to be one untyped dict:

- `InstrumentSpec` — persistent. Adapter key, address, startup settings.
  This is what a config file holds.
- `InstrumentHandle` — ephemeral. The live adapter, connected or not, what
  it is doing, how it last failed. This exists only while the process does.

`Lab` holds one handle per spec and is the single answer to "which
instruments does this system have". See `lab.py` for what that ownership
fixes.
"""

from labpilot.core.lab.handle import InstrumentHandle
from labpilot.core.lab.lab import Lab, UnknownInstrumentError
from labpilot.core.lab.naming import slug, unique_id
from labpilot.core.lab.spec import InstrumentSpec

__all__ = [
    "InstrumentHandle",
    "InstrumentSpec",
    "Lab",
    "UnknownInstrumentError",
    "slug",
    "unique_id",
]
