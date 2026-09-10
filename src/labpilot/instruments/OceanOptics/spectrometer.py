"""Ocean Optics / Ocean Insight spectrometers, as one adapter.

Every model is `ocean_optics`: the model is a setting, and what the
instrument offers follows from it — a QE Pro gains a cooler setpoint and
an 8 ms exposure floor, a USB2000+ has neither.

## What this adds to the two existing implementations

qudi's `oceanoptics_spectrometer.py` is a serial number, an integration
time and `wavelengths()`/`intensities()`. pyMoDAQ's plugin is the same
surface with a choice of backend. Both are thin because seabreeze is
already good; what is missing is everything around the spectrum:

- **the exposure limits are known before connecting.** A QE Pro cannot
  integrate for less than 8 ms and a USB2000+ can do 1. Writing 1 ms to a
  QE Pro is refused here, by name and with the limits, rather than by a
  driver error code — and refused on a laptop with nothing plugged in,
  which is where acquisition settings actually get chosen.
  `quantise_exposure()` is the other half, for a caller that wants the
  nearest workable value rather than an error.
- **saturation is reported.** A pixel at ADC full scale carries no
  information, and a fit through a flat-topped peak is confidently wrong.
  The reading says whether any pixel reached it.
- **averaging and boxcar are here**, applied identically by the real
  adapter and the mock, because everyone writes them again otherwise.
- **the spectrum is a `Dataset` with a real axis.** `wavelengths` is
  declared `role=AXIS` and `intensities` names it, so a plot, an HDF5
  file and a workflow all know the x-scale without being told — this
  repo's own example schema has been an Ocean spectrometer since before
  one could be connected.

## Dark counts

Two different things share the word. `correct_dark` is seabreeze's
electric-dark correction, which uses the detector's own masked pixels and
is available only on models that have them. A *dark spectrum* — shutter
closed, subtract — is a measurement, not a device setting, and belongs in
a workflow rather than here.

Attribution: talks to the hardware through python-seabreeze (Andreas
Poehlmann, MIT), whose per-model table is transcribed in `models.toml`.
Built against seabreeze's documented API; **no spectrometer was attached
to the machine this was written on**, so the I/O paths should be checked
against real hardware. The model, schema and processing layers are
exercised headlessly by `tests/test_ocean_optics.py` and by
`mock_ocean_optics`.
"""

from __future__ import annotations

import contextlib
from typing import Any

import numpy as np

from labpilot.core.device.parameter import INTEGRATION_TIME, Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.OceanOptics.models import OceanModel, find_model

__all__ = ["OceanOpticsAdapter", "boxcar", "spectrometer_schema"]

#: seabreeze's trigger modes. Which of them a given model honours is a
#: property of its firmware, not of this table — an unsupported one is
#: refused by the device, which is the only authority on it.
TRIGGER_MODES = (0, 1, 2, 3, 4)
TRIGGER_LABELS = "0 normal, 1 software, 2 external level, 3 external sync, 4 external edge"


def boxcar(values: np.ndarray, width: int) -> np.ndarray:
    """Ocean's own smoothing: a moving average of `2*width + 1` pixels.

    Width is a half-width, as it is in OceanView, so `width=2` averages
    five pixels. Edges keep their own values rather than being averaged
    against pixels that do not exist — the alternative bends the ends of
    every spectrum inward, which looks like a real feature at the edge of
    a detector's range.
    """
    if width <= 0:
        return values
    window = 2 * int(width) + 1
    if window >= values.size:
        return values
    kernel = np.ones(window) / window
    smoothed = np.convolve(values, kernel, mode="same")
    smoothed[:width] = values[:width]
    smoothed[-width:] = values[-width:]
    return smoothed


def spectrometer_schema(
    name: str, model: OceanModel | None, pixels: int, *, tags: tuple[str, ...] = ()
) -> DeviceSchema:
    """What a configured spectrometer presents — shared with the mock.

    `model` may be None: a device that has not been opened and was not
    told which one it is still has wavelengths and intensities, just no
    exposure limits to enforce. That is the honest schema for it, and it
    keeps `describe()` working with nothing plugged in.
    """
    limits = model.integration_ms if model else (None, None)
    parameters = [
        Parameter(
            "wavelengths", shape=(pixels or None,), unit="nm", role=ParamRole.AXIS,
            description="Pixel wavelength calibration, read from the device.",
        ),
        Parameter(
            "intensities", shape=(pixels or None,), unit="counts",
            axes=("wavelengths",),
            description="One spectrum, after averaging and boxcar smoothing.",
        ),
        Parameter(
            "integration_time_ms", unit="ms", settable=True, role=ParamRole.SETTING,
            limits=limits, tags=frozenset({INTEGRATION_TIME}),
            description="Exposure, within what this model supports.",
        ),
        Parameter(
            "scans_to_average", dtype="i8", settable=True, role=ParamRole.SETTING,
            limits=(1, None),
            description="Spectra averaged per reading. Costs that much time.",
        ),
        Parameter(
            "boxcar_width", dtype="i8", settable=True, role=ParamRole.SETTING,
            limits=(0, None), unit="pixels",
            description="Moving-average half-width; 0 is off.",
        ),
        Parameter(
            "correct_dark", dtype="bool", settable=True, role=ParamRole.SETTING,
            description="Subtract the detector's own masked pixels.",
        ),
        Parameter(
            "correct_nonlinearity", dtype="bool", settable=True,
            role=ParamRole.SETTING,
            description="Apply the factory nonlinearity coefficients.",
        ),
        Parameter(
            "trigger_mode", dtype="i8", settable=True, role=ParamRole.SETTING,
            choices=TRIGGER_MODES, description=TRIGGER_LABELS,
        ),
        Parameter(
            "saturated", dtype="bool", readable=True, settable=False,
            role=ParamRole.STATUS,
            description="A pixel reached ADC full scale, so its value means nothing.",
        ),
        Parameter(
            "model", dtype="str", readable=True, settable=False, role=ParamRole.STATUS,
        ),
        Parameter(
            "serial_number", dtype="str", readable=True, settable=False,
            role=ParamRole.STATUS,
        ),
    ]
    if model is not None and model.cooled:
        parameters += [
            Parameter(
                "tec_setpoint_c", unit="degC", settable=True, role=ParamRole.SETTING,
                limits=(-40.0, 40.0),
                description="Detector cooling setpoint.",
            ),
            Parameter(
                "tec_temperature_c", unit="degC", readable=True, settable=False,
                role=ParamRole.STATUS,
            ),
        ]

    return DeviceSchema(
        name=name,
        kind="detector",
        parameters=tuple(parameters),
        trigger_modes=["software", "hardware"],
        tags=[
            "Ocean Optics", "Ocean Insight", "spectrometer", "spectroscopy",
            *( [model.label] if model else [] ),
            *( [f"{model.family} series"] if model and model.family else [] ),
            *tags,
        ],
    )


class _SpectrometerConfig:
    """The driver-free half: which model, and the acquisition settings.

    Shared with `mock_ocean_optics` so the mock cannot drift — choosing
    `QE Pro` on a laptop has to give the exposure limits the real one will
    enforce, or configuring offline is worthless.
    """

    def __init__(
        self,
        serial_number: str = "",
        model: str = "",
        integration_time_ms: float = 10.0,
        scans_to_average: int = 1,
        boxcar_width: int = 0,
        correct_dark: bool = False,
        correct_nonlinearity: bool = False,
        name: str = "ocean_optics",
    ) -> None:
        self._serial = str(serial_number or "")
        self._configured_model = str(model or "")
        self._model: OceanModel | None = find_model(model) if model else None
        self._integration_ms = float(integration_time_ms)
        self._average = max(int(scans_to_average), 1)
        self._boxcar = max(int(boxcar_width), 0)
        self._correct_dark = bool(correct_dark)
        self._correct_nonlinearity = bool(correct_nonlinearity)
        self._trigger_mode = 0
        self._tec_setpoint = 10.0
        self._name = name
        self._wavelengths: np.ndarray | None = None
        self._adjusted = ""
        """Set when the *configured* exposure had to be moved to fit the
        model, so `reconcile()` can say so instead of it being silent."""

    @property
    def model(self) -> OceanModel | None:
        return self._model

    @property
    def pixels(self) -> int:
        return self._model.pixels if self._model else 0

    @property
    def schema(self) -> DeviceSchema:
        return spectrometer_schema(self._name, self._model, self.pixels)

    def constraints(self):
        """What this model will really do with a requested exposure."""
        if self._model is None:
            from labpilot.core.device.constraints import Constraints

            return Constraints()
        return self._model.constraints()

    def quantise_exposure(self, milliseconds: float) -> tuple[float, str]:
        """The nearest exposure this model can hold, and why it changed.

        Not what `write()` does — a setpoint outside a parameter's limits
        raises, here as everywhere else in this repo. This is the other
        question, the one `core/device/constraints.py` exists for: given
        that you asked for 1 ms on a QE Pro, what would you actually get?
        A caller that wants "as fast as this thing goes" asks this; a
        caller that typed a number gets told it is out of range.

        It is also what settles the *configured* exposure at construction
        and connect, where raising would mean a saved config that names a
        slightly-too-short exposure cannot be opened at all.
        """
        result = self.constraints().quantise({"integration_time_ms": milliseconds})
        return float(result["integration_time_ms"]), result.report()

    def _finish(self, raw: np.ndarray) -> dict[str, Any]:
        """One averaged, smoothed spectrum plus what it says about itself."""
        values = np.asarray(raw, dtype=float)
        full_scale = self._model.max_counts if self._model else 0
        saturated = bool(full_scale and float(values.max(initial=0.0)) >= full_scale)
        return {
            "intensities": boxcar(values, self._boxcar).tolist(),
            "saturated": saturated,
        }

    def _settings(self) -> dict[str, Any]:
        return {
            "integration_time_ms": self._integration_ms,
            "scans_to_average": self._average,
            "boxcar_width": self._boxcar,
            "correct_dark": self._correct_dark,
            "correct_nonlinearity": self._correct_nonlinearity,
            "trigger_mode": self._trigger_mode,
            "model": self._model.label if self._model else "",
            "serial_number": self._serial,
        }


class OceanOpticsAdapter(_SpectrometerConfig, AdapterBase):
    """An Ocean Optics spectrometer, whichever model it is.

    Args:
        serial_number: Which unit, when more than one is plugged in. Empty
            takes the first one seabreeze finds.
        model: Optional. Naming it makes the exposure limits and pixel
            count known before connecting, which is the whole point of the
            model table; leaving it empty means "ask the device".
        integration_time_ms: Exposure, clipped to what the model supports.
        scans_to_average: Spectra averaged per reading.
        boxcar_width: Moving-average half-width, as in OceanView.
        correct_dark: seabreeze's electric-dark correction, using the
            detector's own masked pixels.
        correct_nonlinearity: Apply the factory nonlinearity coefficients.
    """

    def __init__(self, **kwargs: Any) -> None:
        AdapterBase.__init__(self)
        _SpectrometerConfig.__init__(self, **kwargs)
        self._spectrometer: Any = None
        self._mismatch = ""

    # --- Connection --------------------------------------------------------

    def _open(self) -> Any:
        try:
            import seabreeze.spectrometers as sb
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise ImportError(
                "Talking to an Ocean Optics spectrometer needs python-seabreeze: "
                "`pip install seabreeze` then `seabreeze_os_setup` for the USB "
                "permissions. Configuring one — model, exposure limits, schema "
                "— needs neither."
            ) from exc

        if self._serial:
            return sb.Spectrometer.from_serial_number(self._serial)
        found = sb.list_devices()
        if not found:
            raise ConnectionError(
                "seabreeze found no Ocean Optics spectrometer. Check the USB "
                "connection, and that `seabreeze_os_setup` has been run."
            )
        return sb.Spectrometer(found[0])

    def _connect_sync(self) -> None:
        self._spectrometer = self._open()
        reported = str(getattr(self._spectrometer, "model", "") or "")
        self._serial = str(getattr(self._spectrometer, "serial_number", "") or "")

        # The device is the authority. A configured model that disagrees is
        # kept as a warning rather than silently honoured: it usually means
        # the wrong unit was picked out of two on the bench.
        if reported:
            try:
                found = find_model(reported)
            except KeyError:
                found = None
            if found is not None:
                if self._model is not None and found.model != self._model.model:
                    self._mismatch = (
                        f"configured as {self._model.label} but the device "
                        f"reports {found.label}; using the device"
                    )
                self._model = found

        self._wavelengths = np.asarray(self._spectrometer.wavelengths(), dtype=float)
        self._apply_exposure()

    def _apply_exposure(self) -> str:
        exposure, report = self.quantise_exposure(self._integration_ms)
        if report:
            self._adjusted = report
        self._integration_ms = exposure
        if self._spectrometer is not None:
            self._spectrometer.integration_time_micros(round(exposure * 1000.0))
        return report

    def _disconnect_sync(self) -> None:
        if self._spectrometer is not None:
            with contextlib.suppress(Exception):
                self._spectrometer.close()
            self._spectrometer = None

    def _self_test_sync(self) -> None:
        if self._spectrometer is None:
            raise RuntimeError(f"{self._name} is not connected")
        self._spectrometer.wavelengths()

    # --- Reading -----------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        if self._spectrometer is None:
            raise RuntimeError(f"{self._name} is not connected")

        frames = [
            np.asarray(
                self._spectrometer.intensities(
                    correct_dark_counts=self._correct_dark,
                    correct_nonlinearity=self._correct_nonlinearity,
                ),
                dtype=float,
            )
            for _ in range(self._average)
        ]
        reading: dict[str, Any] = {
            "wavelengths": (
                self._wavelengths.tolist() if self._wavelengths is not None else []
            ),
            **self._finish(np.mean(frames, axis=0)),
            **self._settings(),
        }
        if self._model is not None and self._model.cooled:
            reading["tec_temperature_c"] = self._temperature()
            reading["tec_setpoint_c"] = self._tec_setpoint
        return reading

    def _temperature(self) -> float:
        feature = getattr(getattr(self._spectrometer, "f", None), "thermo_electric", None)
        if feature is None:
            return float("nan")
        try:
            return float(feature.read_temperature_degrees_celsius())
        except Exception:
            return float("nan")

    # --- Writing -----------------------------------------------------------

    async def write(self, values: dict[str, Any]) -> None:
        """Overridden because several settings are one driver call each and
        two of them are pure adapter-side processing."""
        for key, value in self.validate_write(values).items():
            await self._to_thread(self._set, key, value)

    def _set(self, key: str, value: Any) -> None:
        if key == "integration_time_ms":
            # Already validated against the model's limits by
            # `validate_write`, so this cannot be out of range.
            self._integration_ms = float(value)
            self._apply_exposure()
        elif key == "scans_to_average":
            self._average = max(int(value), 1)
        elif key == "boxcar_width":
            self._boxcar = max(int(value), 0)
        elif key == "correct_dark":
            self._correct_dark = bool(value)
        elif key == "correct_nonlinearity":
            self._correct_nonlinearity = bool(value)
        elif key == "trigger_mode":
            self._trigger_mode = int(value)
            if self._spectrometer is not None:
                self._spectrometer.trigger_mode(int(value))
        elif key == "tec_setpoint_c":
            self._tec_setpoint = float(value)
            feature = getattr(
                getattr(self._spectrometer, "f", None), "thermo_electric", None
            )
            if feature is not None:
                feature.enable_tec(True)
                feature.set_temperature_setpoint_degrees_celsius(float(value))

    # --- The table versus the device ---------------------------------------

    async def reconcile(self) -> dict[str, Any]:
        """What the device says about itself, against the table entry.

        The pixel count and the exposure limits are readable from the
        hardware, so a wrong entry in `models.toml` is discoverable rather
        than permanent.
        """
        if self._spectrometer is None:
            raise RuntimeError(f"{self._name} is not connected")

        live: dict[str, Any] = {
            "model": str(getattr(self._spectrometer, "model", "") or ""),
            "serial_number": self._serial,
        }
        for key, get in (
            ("pixels", lambda: int(self._spectrometer.pixels)),
            ("max_counts", lambda: int(self._spectrometer.max_intensity)),
            (
                "integration_us",
                lambda: tuple(
                    float(v) for v in self._spectrometer.integration_time_micros_limits
                ),
            ),
        ):
            with contextlib.suppress(Exception):
                live[key] = get()

        differences: dict[str, Any] = {}
        if self._model is not None:
            table = {
                "pixels": self._model.pixels,
                "max_counts": self._model.max_counts,
                "integration_us": (
                    self._model.integration_min_us, self._model.integration_max_us
                ),
            }
            differences = {
                key: {"table": table[key], "device": live[key]}
                for key in table
                if key in live and live[key] != table[key]
            }
        return {
            "model": self._model.model if self._model else "",
            "device": live,
            "differences": differences,
            "warning": "; ".join(filter(None, (self._mismatch, self._adjusted))),
        }


adapter_registry.register("ocean_optics", OceanOpticsAdapter)
