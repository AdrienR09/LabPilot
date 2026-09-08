"""Pulse sequences — device-independent description, authored offline.

A sequence says what should happen when, on named channels, with one
quantity swept. It deliberately knows nothing about sample rates, memory
granularity or channel wiring: those belong to whichever pulser
eventually plays it, and a sequence is meant to be written at a desk with
no hardware present.

Compiling to a device's own format is the pulser adapter's job
(`PulserMixin.upload_sequence`) — a digital sequencer emits
`(level, duration)` instructions directly and never samples anything,
while a true AWG calls `core/pulse/sampling.py` because it genuinely needs
dense float arrays.
"""

from labpilot.core.pulse.sequence import (
    ChannelMap,
    PulseBlock,
    PulseElement,
    PulseSequence,
    SequenceError,
    Sweep,
    linear_sweep,
    log_sweep,
)
from labpilot.core.pulse.shapes import (
    DC,
    SHAPES,
    Chirp,
    Gauss,
    Idle,
    Shape,
    Sin,
    register_shape,
    shape_from_dict,
    shape_to_dict,
)

__all__ = [
    "DC",
    "SHAPES",
    "ChannelMap",
    "Chirp",
    "Gauss",
    "Idle",
    "PulseBlock",
    "PulseElement",
    "PulseSequence",
    "SequenceError",
    "Shape",
    "Sin",
    "Sweep",
    "linear_sweep",
    "log_sweep",
    "register_shape",
    "shape_from_dict",
    "shape_to_dict",
]
