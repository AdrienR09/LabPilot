"""National Instruments DAQ cards.

One adapter (`ni_card`), one model table (`models.toml`), one wiring
format (`channels.py`). It replaces the two adapters that were here
before — `ni_daq` for analog I/O and `ni_daq_scanner` for hardware-timed
scanning — which forced a card that does both to be loaded twice, as two
DAQmx sessions against one physical device.
"""

from labpilot.instruments.NI.card import NICardAdapter
from labpilot.instruments.NI.channels import Channel, parse_channels
from labpilot.instruments.NI.models import NICardModel, find_model, load_models

__all__ = [
    "Channel",
    "NICardAdapter",
    "NICardModel",
    "find_model",
    "load_models",
    "parse_channels",
]
