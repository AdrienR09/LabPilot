"""Which Ocean Optics spectrometer this is, and what it can be asked for.

## Where the numbers come from

`python-seabreeze` (Andreas Poehlmann, **MIT**) carries a real per-model
table — `seabreeze/pyseabreeze/devices.py` defines one class per
spectrometer with its pixel count, ADC full scale and integration-time
limits, because the USB protocol differs per model and the library has no
choice but to know. Those are facts, they are published under a licence
that permits reuse, and they are transcribed here verbatim rather than
re-derived from datasheets.

The other two references have no such table. qudi's
`oceanoptics_spectrometer.py` is thirty lines around
`seabreeze.Spectrometer.from_serial_number` — a serial number, an
integration time, and `wavelengths()`/`intensities()`. pyMoDAQ's
`pymodaq_plugins_oceaninsight` offers two backends (OmniDriver, and
seabreeze when OmniDriver is missing) and points at Ocean's product page
for the model list. Both ask the connected device, which is right when one
is connected.

## Why a table here as well

Same reason as `instruments/NI/models.py`: so a spectrometer can be
configured, and a workflow written against it, with nothing plugged in.
Knowing that a QE Pro has 1044 pixels and cannot integrate for less than
8 ms is what lets an acquisition be set up correctly before anyone is
standing at the bench — and 8 ms versus the USB2000+'s 1 ms is the
difference between a working exposure and a driver error.

It is not authoritative. `seabreeze` reports the model, the pixel count
and the real integration limits from the device itself, and on connect
those win — `OceanOpticsAdapter` reads them and reports any disagreement.

## Names

The `model` field is what seabreeze reports (`USB2000PLUS`, `QEPRO`,
`FLAMES`), because that is what a connected device will call itself.
Nobody says that out loud, so every entry also carries the marketing name
and the spellings people actually type, and lookup ignores case,
punctuation and spaces: `"QE Pro"`, `"qe-pro"` and `"QEPRO"` are one
spectrometer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from labpilot.core.device.constraints import Constraints, ScalarConstraint
from labpilot.instruments._model_table import load_table

__all__ = [
    "OceanModel",
    "find_model",
    "load_models",
    "model_names",
    "normalise_name",
]

_PACKAGED = Path(__file__).parent / "models.toml"
_USER = Path.home() / ".labpilot" / "config" / "ocean_models.toml"

_PUNCTUATION = re.compile(r"[\s_\-.]+")


def normalise_name(name: str) -> str:
    """The comparison form of a model name.

    `"QE Pro"`, `"qe-pro"` and `"QEPRO"` are the same spectrometer;
    `"USB2000+"` keeps its plus, because `USB2000` and `USB2000+` are
    genuinely different instruments with different ADCs.
    """
    return _PUNCTUATION.sub("", str(name).strip().lower())


@dataclass(frozen=True, slots=True)
class OceanModel:
    """One spectrometer model: its detector, and what it will accept."""

    model: str
    """The name the device reports through seabreeze — `USB2000PLUS`."""
    label: str = ""
    """What it is called in the catalogue — `USB2000+`."""
    aliases: tuple[str, ...] = ()
    family: str = ""

    pixels: int = 0
    """Spectrum length. Some of these include optical-black pixels that
    are read out and then used for the dark correction rather than being
    signal — which is why `dark_pixels` is here too."""
    max_counts: int = 0
    """ADC full scale. Anything at or above it is saturated and its value
    means nothing, which is worth knowing before fitting a peak to it."""
    integration_min_us: float = 0.0
    integration_max_us: float = 0.0
    dark_pixels: tuple[tuple[int, int], ...] = ()
    """Half-open index ranges of the optically masked pixels."""
    cooled: bool = False
    """Has a thermo-electric cooler, so it gains a temperature setpoint."""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(
            self, "dark_pixels", tuple(tuple(pair) for pair in self.dark_pixels)
        )
        if not self.label:
            object.__setattr__(self, "label", self.model)

    @property
    def names(self) -> tuple[str, ...]:
        """Every spelling this model answers to."""
        return (self.model, self.label, *self.aliases)

    @property
    def integration_ms(self) -> tuple[float, float]:
        """The integration-time limits in milliseconds, which is the unit
        the schema uses — Ocean's own API is microseconds, and every other
        detector in this repo is `integration_time_ms`."""
        return (self.integration_min_us / 1e3, self.integration_max_us / 1e3)

    def dark_indices(self) -> tuple[int, ...]:
        return tuple(
            index for start, stop in self.dark_pixels for index in range(start, stop)
        )

    def constraints(self) -> Constraints:
        """What this spectrometer will really do with a requested exposure.

        Clipping rather than raising is the right behaviour here: asking a
        QE Pro for 1 ms is a misunderstanding of the instrument, not a
        typo, and the useful answer is "it will give you 8".
        """
        low, high = self.integration_ms
        scalars = []
        if high > 0:
            scalars.append(
                ScalarConstraint("integration_time_ms", bounds=(low, high), unit="ms")
            )
        return Constraints(scalars=tuple(scalars), extra={"model": self.model})


_cache: dict[tuple[Path, Path], dict[str, OceanModel]] = {}


def load_models(
    packaged: Path | None = None, user: Path | None = None, *, refresh: bool = False
) -> dict[str, OceanModel]:
    """Every known spectrometer, keyed by its normalised reported name.

    `~/.labpilot/config/ocean_models.toml` is merged over the packaged
    table — see `instruments/_model_table.py`.
    """
    key = (packaged or _PACKAGED, user or _USER)
    if refresh:
        _cache.pop(key, None)
    if key in _cache:
        return _cache[key]

    models = {
        name: OceanModel(**entry)
        for name, entry in load_table(
            key[0], key[1], section="spectrometer", key="model",
            normalise=normalise_name,
        ).items()
    }
    _cache[key] = models
    return models


def find_model(name: str, models: dict[str, OceanModel] | None = None) -> OceanModel:
    """The model for whatever someone typed, or the device reported.

    Raises `KeyError` listing the nearest names. A wrong model would set
    an integration limit the device does not have, so guessing is worse
    than refusing.
    """
    table = models if models is not None else load_models()
    wanted = normalise_name(name)

    for model in table.values():
        if any(normalise_name(spelling) == wanted for spelling in model.names):
            return model

    near = sorted(
        {m.label for m in table.values() if normalise_name(m.label)[:3] == wanted[:3]}
    ) or sorted({m.label for m in table.values()})
    raise KeyError(
        f"No Ocean Optics model {name!r} in the table. Nearest: "
        f"{', '.join(near[:6])}. Add it to ~/.labpilot/config/ocean_models.toml, "
        f"or leave the model unset to take whatever the connected device says "
        f"it is."
    )


def model_names() -> tuple[str, ...]:
    """Every model's catalogue name, sorted — for a settings dropdown."""
    return tuple(sorted({m.label for m in load_models().values()}))
