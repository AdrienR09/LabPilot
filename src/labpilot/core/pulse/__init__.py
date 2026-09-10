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

from labpilot.core.pulse.analyse import (
    ANALYSES,
    Analysis,
    AnalysisError,
    analyse,
    analysis_parameters,
    analysis_units,
    default_analysis,
)
from labpilot.core.pulse.extract import (
    EXTRACTORS,
    Extraction,
    ExtractionError,
    extract,
    extractor_parameters,
)
from labpilot.core.pulse.sampling import (
    Interval,
    Sampled,
    SamplingError,
    Segment,
    check_activation,
    expand,
    sample,
    shots,
    timing_diagram,
)
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
from labpilot.core.pulse.store import (
    SavedSequence,
    delete_sequence,
    ensure_default_sequences,
    list_sequences,
    load_sequence,
    save_sequence,
)

__all__ = [
    "ANALYSES",
    "DC",
    "EXTRACTORS",
    "SHAPES",
    "Analysis",
    "AnalysisError",
    "ChannelMap",
    "Chirp",
    "Extraction",
    "ExtractionError",
    "Gauss",
    "Idle",
    "Interval",
    "PulseBlock",
    "PulseElement",
    "PulseSequence",
    "Sampled",
    "SamplingError",
    "SavedSequence",
    "Segment",
    "SequenceError",
    "Shape",
    "Sin",
    "Sweep",
    "analyse",
    "analysis_parameters",
    "analysis_units",
    "check_activation",
    "default_analysis",
    "delete_sequence",
    "ensure_default_sequences",
    "expand",
    "extract",
    "extractor_parameters",
    "linear_sweep",
    "list_sequences",
    "load_sequence",
    "log_sweep",
    "register_shape",
    "sample",
    "save_sequence",
    "shape_from_dict",
    "shape_to_dict",
    "shots",
    "timing_diagram",
]
