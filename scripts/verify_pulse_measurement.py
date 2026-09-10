#!/usr/bin/env python3
"""Verify the pulsed measurement's UI — the control dock and the result view.

The editor's harness (`verify_pulse_editor.py`) covers authoring with no
hardware. This covers the other half: playing a saved sequence, and
showing what came back.

Two claims:

1. **The dock offers what exists, not what was typed.** The sequence list
   comes from the library on disk, with a file that will not play marked
   and its reason attached rather than hidden; the extraction and analysis
   combos come from the registries, so a method added to `core/pulse/`
   appears here with no change to the widget.

2. **The result view shows the extraction, not only the curve.** A window
   that starts fifty nanoseconds early costs contrast and raises nothing —
   the curve just comes out flatter — so being able to see where
   extraction decided the laser pulse was is the only defence, and it has
   to survive an empty first frame and a fit that did not converge.

Run it:

    QT_QPA_PLATFORM=offscreen python scripts/verify_pulse_measurement.py

Not a pytest test, deliberately — same reason as `verify_pulse_editor.py`:
`tests/` is the headless, Qt-free suite, and importing pymodaq_gui's Qt
stack into it crashes collection with a metaclass conflict.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "src" / "labpilot" / "ui" / "desktop"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DESKTOP))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import labpilot.ui.qt_api  # noqa: F401, E402  (pins QT_API before Qt loads)
from labpilot.core.pulse import analyse, extract  # noqa: E402
from labpilot.core.pulse.analyse import ANALYSES  # noqa: E402
from labpilot.core.pulse.extract import EXTRACTORS  # noqa: E402

failures: list[str] = []


def drawn(item) -> int:
    """How many points a pyqtgraph curve is showing — it hands back
    `(None, None)` rather than empty arrays when it is showing none."""
    xs, _ = item.getData()
    return 0 if xs is None else len(xs)


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label}{f' ({detail})' if detail else ''}")


DEFAULTS = {
    "SEQUENCE": "rabi",
    "CHANNELS": {"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"},
    "SWEEPS": 2000,
    "CHECKPOINTS": 20,
    "BIN_WIDTH": 1e-9,
    "RECORD_LENGTH": 0.0,
    "EXTRACT": "conv_deriv",
    "ANALYSE": "auto",
    "FIT": "none",
}

LIBRARY = [
    {"name": "rabi", "valid": True, "problem": "", "points": 50,
     "readouts": 50, "duration": 2.6e-4},
    {"name": "ramsey", "valid": True, "problem": "", "points": 50,
     "readouts": 100, "duration": 7.3e-4},
    {"name": "half_edited", "valid": False, "points": 0, "readouts": 0,
     "duration": 0.0, "problem": "Block 'b' has no readout"},
]


def synthetic_result(*, fit: bool = True, empty: bool = False) -> dict:
    """A pulsed result of the shape `pulsed_measurement.py` returns."""
    record = 4500
    delay, length = 300, 3000
    bins = np.arange(record, dtype=float)
    lit = (bins >= delay) & (bins < delay + length)
    profile = 2.0 + np.where(lit, 200 * (0.35 + 0.65 * np.exp(-(bins - delay) / 300)), 0.0)
    counts = np.tile(profile, (40, 1))

    found = extract(counts, 1e-9, "conv_deriv")
    reduced = analyse(found, 1e-9, "mean_norm")
    tau = (np.arange(40) + 1) * 1e-8
    curve = 1.0 + 0.2 * np.exp(-tau / 8e-7) * np.cos(2 * np.pi * tau / 2e-7)

    result: dict = {
        "sequence": "rabi",
        "completed": 20,
        "total": 20,
        "tau": tau.tolist(),
        "curve": curve.tolist(),
        "errors": reduced.to_dict()["errors"],
        "extraction": found.to_dict(),
        "analysis": reduced.to_dict(),
        "fit_model": "rabi" if fit else "none",
        "fit": None,
    }
    if fit:
        from labpilot.core.analysis.fits import evaluate_rabi, fit_rabi

        fitted = fit_rabi(tau, curve)
        fitted["curve"] = evaluate_rabi(fitted, tau)
        result["fit"] = fitted
    if empty:
        result.update(
            curve=[None] * 40, errors=[],
            extraction=extract(np.zeros((40, record)), 1e-9).to_dict(),
            completed=0, fit=None,
        )
    return result


def main() -> int:
    from components.pulse_control import PulseMeasurementControlWidget
    from components.workflow_result import PulsedResultView

    app = QApplication.instance() or QApplication([])

    print("1. The dock builds from parameters alone — no client, no schema")
    dock = PulseMeasurementControlWidget(
        DEFAULTS, sequences=LIBRARY,
        extractors=sorted(EXTRACTORS), analyses=sorted(ANALYSES),
    )
    app.processEvents()
    check("it holds no client", not hasattr(dock, "client"))
    check("sweeps came from the parameters", dock.sweeps.value() == 2000,
          str(dock.sweeps.value()))
    check("checkpoints too", dock.checkpoints.value() == 20)
    check("and the bin width", dock.bin_width.value() == 1e-9, str(dock.bin_width.value()))

    print("\n2. The sequence list is the library on disk")
    names = [dock.sequence.itemData(i) for i in range(dock.sequence.count())]
    check("every saved sequence is offered", names == ["rabi", "ramsey", "half_edited"],
          f"{names}")
    check("the stored one is selected", dock.sequence.currentData() == "rabi",
          str(dock.sequence.currentData()))
    check("its summary states the shape",
          "50 points" in dock.summary.text(), dock.summary.text())

    print("\n3. A sequence that will not play is marked, not hidden")
    labels = [dock.sequence.itemText(i) for i in range(dock.sequence.count())]
    check("it is listed", any("half_edited" in label for label in labels), f"{labels}")
    check("and marked unplayable", any("unplayable" in label for label in labels),
          f"{labels}")
    dock.sequence.setCurrentIndex(2)
    app.processEvents()
    check("choosing it says why", "no readout" in dock.summary.text(),
          dock.summary.text())
    dock.sequence.setCurrentIndex(0)

    print("\n4. Editing a control reports the parameter, and only that one")
    seen: list[tuple[str, object]] = []
    dock.sigParamChanged.connect(lambda name, value: seen.append((name, value)))
    dock.sweeps.setValue(5000)
    dock.checkpoints.setValue(4)
    app.processEvents()
    check("both edits were reported", [n for n, _ in seen] == ["SWEEPS", "CHECKPOINTS"],
          f"{seen}")
    check("with the values typed", [v for _, v in seen] == [5000, 4], f"{seen}")

    print("\n5. The channel map is parsed, not stored as text")
    seen.clear()
    dock.channels.setText("laser=d_ch3, mw = a_ch2 ,gate=d_ch4")
    dock.channels.editingFinished.emit()
    app.processEvents()
    check("it became a mapping",
          seen == [("CHANNELS", {"laser": "d_ch3", "mw": "a_ch2", "gate": "d_ch4"})],
          f"{seen}")

    seen.clear()
    dock.channels.setText("")
    dock.channels.editingFinished.emit()
    check("an empty map is empty, not a parse error", seen == [("CHANNELS", {})],
          f"{seen}")

    print("\n6. The method combos come from the registries")
    extractors = [dock.extract.itemText(i) for i in range(dock.extract.count())]
    analyses = [dock.analyse.itemText(i) for i in range(dock.analyse.count())]
    check("every extraction method is offered", extractors == sorted(EXTRACTORS),
          f"{extractors}")
    check("every analysis method too, with auto first",
          analyses == ["auto", *sorted(ANALYSES)], f"{analyses}")
    check("auto is the stored choice", dock.analyse.currentText() == "auto")

    print("\n7. The fit is named rather than inferred")
    fits = [dock.fit.itemData(i) for i in range(dock.fit.count())]
    check("none, rabi and decay are offered", fits == ["none", "rabi", "decay"], f"{fits}")
    seen.clear()
    dock.fit.setCurrentIndex(1)
    app.processEvents()
    check("choosing one reports its value", seen == [("FIT", "rabi")], f"{seen}")

    print("\n8. Refreshing re-reads the library without losing the selection")
    dock.set_sequences([*LIBRARY, {"name": "t1", "valid": True, "points": 20,
                                   "readouts": 20, "duration": 1.4e-2}])
    app.processEvents()
    check("the new one appears", dock.sequence.count() == 4, str(dock.sequence.count()))
    check("the selection survived", dock.sequence.currentData() == "rabi",
          str(dock.sequence.currentData()))

    print("\n9. The result view draws the curve, its errors and the fit")
    view = PulsedResultView()
    result = synthetic_result()
    view.update_data(result)
    app.processEvents()

    check("one point per swept tau", drawn(view._points) == 40, str(drawn(view._points)))
    check("the fit is drawn over it", drawn(view._fit_curve) == 40)
    check("error bars are shown", view._errors.isVisible())
    check("the summary names the pi pulse", "pi =" in view.summary.text(),
          view.summary.text())
    check("and how far the run got", "20/20" in view.summary.text(), view.summary.text())

    print("\n10. And the record the curve was extracted from")
    check("the raw record is drawn", drawn(view._record) == 4500, str(drawn(view._record)))
    check("the extracted window is shaded", view._window.isVisible())
    low, high = view._window.getRegion()
    check("it covers the laser pulse", 2.5e-7 < low < 3.5e-7 and 3.0e-6 < high < 3.6e-6,
          f"{low}..{high}")
    check("the summary names the extraction method",
          "conv_deriv" in view.summary.text(), view.summary.text())

    print("\n11. The first frame of a run is legible rather than broken")
    blank = PulsedResultView()
    blank.update_data(synthetic_result(empty=True))
    app.processEvents()
    check("no points are plotted yet", drawn(blank._points) == 0)
    check("the window is not shown", not blank._window.isVisible())
    check("and it says nothing was found",
          "nothing found yet" in blank.summary.text(), blank.summary.text())

    print("\n12. A fit that did not converge says so")
    unfitted = synthetic_result(fit=False)
    unfitted["fit_model"] = "rabi"
    view.update_data(unfitted)
    app.processEvents()
    check("the fit line is cleared", drawn(view._fit_curve) == 0)
    check("and the summary says why the fit is missing",
          "did not converge" in view.summary.text(), view.summary.text())

    print("\n13. A result with no measurement at all does not crash the view")
    PulsedResultView().update_data({})
    app.processEvents()
    check("an empty result is survivable", True)

    print("\n14. The axis labels come from the analysis, not from this file")
    view.update_data(result)
    app.processEvents()
    left = view.curve_plot.getAxis("left").labelText
    check("the value axis is the analysis method's own label",
          left == result["analysis"]["label"], f"{left!r}")

    print("\n" + "=" * 70)
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All pulsed-measurement checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
