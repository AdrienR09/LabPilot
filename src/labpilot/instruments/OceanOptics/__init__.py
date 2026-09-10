"""Ocean Optics / Ocean Insight spectrometers.

One adapter (`ocean_optics`) for every model, with the model chosen in
its settings and its detector and exposure limits coming from
`models.toml` — transcribed from python-seabreeze's own per-model table.
"""

from labpilot.instruments.OceanOptics.models import (
    OceanModel,
    find_model,
    load_models,
    model_names,
)
from labpilot.instruments.OceanOptics.spectrometer import OceanOpticsAdapter

__all__ = [
    "OceanModel",
    "OceanOpticsAdapter",
    "find_model",
    "load_models",
    "model_names",
]
