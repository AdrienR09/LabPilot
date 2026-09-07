"""Hardware-timed scan.

The confocal-scanner acquisition pattern (rasters a 2D grid, records a
detector reading at every pixel, builds a 2D image), but driven by a
single hardware-timed scanning device (`instruments/hardware_scan_mixin.py`'s
`HardwareScanMixin`) instead of `confocal_scanner.py`'s generic
actuator-write + settle-poll + detector-read loop. Genuinely faster, not
just a smaller settle delay: the device's own hardware clock drives its
position waveform and reads its detector back in lockstep, so there is
no per-pixel software round-trip at all — a real NI DAQ card
(`instruments/NI/generic.py`'s `NIDAQScannerAdapter`) or the physically-
meaningful mock (`instruments/mock/hardware_scan.py`'s `MockNIScanner`)
both implement this the same way Qudi's own `ScanningProbeInterface`/NI
hardware module do (`configure_scan` once for the whole frame, `start_scan`,
poll `get_scan_data` — see `core/run/plans.py`'s
`HardwareTimedScanPlan`, which this template is built on).

References its instrument by *role* — a single "scanner" role, not
separate actuator/detector roles like `confocal_scanner.py`: this is
genuinely one device (position output + detector input, one hardware
clock), not two independent ones a script happens to coordinate. Bind
"scanner" (via the flowchart, or PUT /api/workflows/{id}/bindings/scanner)
to whichever real connected scanning device should play this part.

Only 1D/2D scans are supported (`HardwareScanMixin`'s own constraint —
only the fast, first axis is genuinely hardware-clocked).

Like every other scan here it returns the flat N-D convention rather than
`confocal_scanner.py`'s nested `image` — one convention for one kind of
thing, and `NDScanResultView` renders a 2-D scan as the same image the
`image2d` view did. The reshaping, the counters and the live streaming
belong to `Run`, so what is left below is which axes to scan and how fast.
"""

from labpilot.core.run import ScanAxis, execute
from labpilot.core.run.plans import HardwareTimedScanPlan
from labpilot.core.session import Session

REQUIRED_INSTRUMENTS = {
    "scanner": {"kind": "generic"},
}
SCANNER_ID = "scanner"

# Read by the native desktop window (workflow_window.py) to render a
# live, qudi-style image that fills in as the scan runs. Same declaration
# omniscan makes, because it is the same kind of result — `pick_view`
# would now infer an equivalent spec from the data itself, and this stays
# only to name the crosshair's role.
RESULT_UI = {
    "type": "ndscan",
    "value_key": "data",
    "shape_key": "shape",
    "axis_names_key": "axis_names",
    "axis_positions_key": "axis_positions",
    "actuator_axis_count_key": "actuator_axis_count",
    "value_label": "Counts",
    "crosshair": {"role": "scanner"},
}

# Which two axes to scan, fast axis first — only the fast (first) axis is
# genuinely hardware-clocked (see HardwareScanMixin).
SCAN_AXES: list = ["x", "y"]

# (lo, hi, num_points) per axis — same literal-tuple convention
# omniscan.py's AXIS_RANGES established (plain literals, so this is
# editable live via PUT /api/workflows/{id}/params/SCAN_RANGES).
SCAN_RANGES: dict = {"x": (-2.0, 2.0, 50), "y": (-2.0, 2.0, 50)}

# The fast axis' pixel rate, in Hz — a real NI card can typically manage
# hundreds to a few thousand Hz per axis (Qudi's own reference config
# example: 500-5000 Hz); this mock can go much faster since nothing
# physical actually has to move.
SCAN_FREQUENCY = 5000.0


async def run(session: Session) -> dict:
    # Declared fast-axis-first (only the fast axis is genuinely
    # hardware-clocked), while every plan takes its axes slowest-first —
    # so they are reversed here, once, at the one place that knows this
    # template's own convention.
    axes = [
        ScanAxis(name, SCANNER_ID, SCAN_RANGES[name][0], SCAN_RANGES[name][1],
                 points=int(SCAN_RANGES[name][2]))
        for name in reversed(SCAN_AXES)
    ]
    plan = HardwareTimedScanPlan(
        axes=axes, scanner=SCANNER_ID, frequency=SCAN_FREQUENCY,
        name="hardware_timed_scan",
    )
    return {"scanner": SCANNER_ID, **await execute(session, plan)}
