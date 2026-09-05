"""Time series acquisition.

Repeatedly reads a single 0D detector at a fixed position, once per
`SAMPLE_INTERVAL_S`, for `DURATION_S` — a storable, scripted version of
what qudi's time_series_gui shows live (a rolling trend), useful for
recording a fixed-length trace of e.g. a photon-counting rate rather than
just watching it.

References its instrument by *role*, not a specific instrument id — bind
"detector" (via the flowchart, or PUT /api/workflows/{id}/bindings/{role})
to whichever real connected instrument should play that part before
running. Rebind it at any time; the script itself never needs editing.
"""

import asyncio
import time

from labpilot.core.session import Session

REQUIRED_INSTRUMENTS = {
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# curve that grows as the trace is recorded — see session.report_progress()
# below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "times_s",
    "y_key": "values",
    "x_label": "Time (s)",
    "y_label": "Detector reading",
}

DURATION_S = 10.0
SAMPLE_INTERVAL_S = 0.2


async def run(session: Session) -> dict:
    detector = session.get(DETECTOR_ID)
    value_key = next(iter(detector.schema.readable.keys()))

    times_s: list[float] = []
    values: list[float] = []
    total = max(1, int(DURATION_S / SAMPLE_INTERVAL_S))
    start = time.monotonic()
    await detector.stage()
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= DURATION_S:
                break

            data = await detector.read()
            times_s.append(elapsed)
            values.append(float(data[value_key]))
            await session.report_progress({
                "times_s": times_s,
                "values": values,
                "completed": len(times_s),
                "total": total,
            })

            # Sleep out the remainder of this sample's interval, not the
            # whole interval unconditionally — keeps the actual sample
            # spacing close to SAMPLE_INTERVAL_S regardless of how long the
            # read() itself took.
            next_sample_at = start + len(times_s) * SAMPLE_INTERVAL_S
            remaining = next_sample_at - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
    finally:
        await detector.unstage()

    return {
        "detector": DETECTOR_ID,
        "times_s": times_s,
        "values": values,
    }
