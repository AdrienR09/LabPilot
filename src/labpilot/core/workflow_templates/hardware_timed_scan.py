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
poll `get_scan_data` — see `core/workflow/capabilities.py`'s
`HardwareTimedScanCapability`, which this template is built on).

References its instrument by *role* — a single "scanner" role, not
separate actuator/detector roles like `confocal_scanner.py`: this is
genuinely one device (position output + detector input, one hardware
clock), not two independent ones a script happens to coordinate. Bind
"scanner" (via the flowchart, or PUT /api/workflows/{id}/bindings/scanner)
to whichever real connected scanning device should play this part.

Only 1D/2D scans are supported (`HardwareScanMixin`'s own constraint —
only the fast, first axis is genuinely hardware-clocked); this template
is scoped to the 2D case (`RESULT_UI["type"] == "image2d"`, reusing
`confocal_scanner.py`'s exact result shape so the native window needs no
new code at all). A 1D hardware-timed line scan is a plausible future
template built the same way, just not wired up here.
"""

from labpilot.core.session import Session
from labpilot.core.workflow.capabilities import HardwareTimedScanCapability

REQUIRED_INSTRUMENTS = {
    "scanner": {"kind": "generic"},
}
SCANNER_ID = "scanner"

# Read by the native desktop window (workflow_window.py) to render a
# live, qudi-style image view that fills in as the scan runs — same
# shape confocal_scanner.py's RESULT_UI declares, so Image2DResultView
# needs no changes to render this template's output.
RESULT_UI = {
    "type": "image2d",
    "value_key": "image",
    "x_key": "x_positions",
    "y_key": "y_positions",
    "value_label": "Counts",
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


def _reshape(data: list, n_fast: int, n_slow: int) -> list[list]:
    """`data` is flat, fast axis varying fastest (`build_scan_waveform`'s
    acquisition order: index = slow_idx * n_fast + fast_idx). Returns
    `image[fast_idx][slow_idx]` — a not-yet-acquired cell stays `None`
    (never converted to NaN here — Image2DResultView's own update_data
    does that on the frontend side, same convention confocal_scanner.py
    already relies on)."""
    image = [[None] * n_slow for _ in range(n_fast)]
    for slow_idx in range(n_slow):
        base = slow_idx * n_fast
        for fast_idx in range(n_fast):
            image[fast_idx][slow_idx] = data[base + fast_idx]
    return image


async def run(session: Session) -> dict:
    scanner = session.get(SCANNER_ID)

    ranges = {axis: (SCAN_RANGES[axis][0], SCAN_RANGES[axis][1]) for axis in SCAN_AXES}
    resolution = {axis: int(SCAN_RANGES[axis][2]) for axis in SCAN_AXES}
    n_fast = resolution[SCAN_AXES[0]]
    n_slow = resolution[SCAN_AXES[1]]

    async def on_progress(progress: dict) -> None:
        x_positions, y_positions = progress["positions"]
        await session.report_progress({
            "image": _reshape(progress["data"], n_fast, n_slow),
            "x_positions": x_positions.tolist(),
            "y_positions": y_positions.tolist(),
            "completed": progress["completed"],
            "total": progress["total"],
        })

    scan = HardwareTimedScanCapability(scanner)
    result = await scan.run_scan(SCAN_AXES, ranges, resolution, SCAN_FREQUENCY, on_progress=on_progress)

    x_positions, y_positions = result["positions"]
    return {
        "scanner": SCANNER_ID,
        "x_positions": list(x_positions),
        "y_positions": list(y_positions),
        "image": _reshape(result["data"], n_fast, n_slow),
    }
