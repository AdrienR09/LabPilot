"""Async scan generators for coordinated device motion and data acquisition.

All scan functions are async generators that emit Event objects via EventBus
and also yield them to the caller. This enables both local iteration and
remote subscription to the same event stream.
"""

from __future__ import annotations

import time
import traceback
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import anyio
import numpy as np

from labpilot_core.core.events import Event, EventBus, EventKind
from labpilot_core.device.protocols import Movable, Readable
from labpilot_core.plans.base import ScanPlan

__all__ = ["grid_scan", "scan", "time_scan"]


async def scan(
    plan: ScanPlan,
    motor: Movable,
    detector: Readable,
    bus: EventBus,
) -> AsyncGenerator[Event, None]:
    """Execute 1D scan with coordinated motion and acquisition.

    Generates events:
    - DESCRIPTOR: Full schema at start (device metadata, plan info)
    - READING: Data point per position (motor position + detector readings)
    - PROGRESS: Fraction complete + ETA after each point
    - STOP: Clean completion
    - ERROR: Fatal error with traceback

    Args:
        plan: Scan plan with motor/detector names, positions, dwell time.
        motor: Movable device for motion control.
        detector: Readable device for data acquisition.
        bus: EventBus for event broadcasting.

    Yields:
        Events as they are generated (also emitted to bus).

    Example:
        >>> async for event in scan(plan, motor, detector, session.bus):
        ...     if event.kind == EventKind.READING:
        ...         print(f"pos={event.data['pos']} val={event.data['reading']}")
    """
    run_uid = str(uuid.uuid4())
    positions = np.linspace(plan.start, plan.stop, plan.num)
    start_time = time.time()

    # Emit descriptor event with full metadata
    descriptor = Event(
        kind=EventKind.DESCRIPTOR,
        run_uid=run_uid,
        data={
            "plan": plan.model_dump(),
            "motor_schema": motor.schema.model_dump(),
            "detector_schema": detector.schema.model_dump(),
            "num_points": plan.num,
        },
    )
    await bus.emit(descriptor)
    yield descriptor

    try:
        # Stage all devices before scan
        await motor.stage()
        await detector.stage()

        for i, pos in enumerate(positions):
            # Check for cancellation
            with anyio.CancelScope() as cancel_scope:
                if cancel_scope.cancel_called:
                    break

            # Move motor to position
            await motor.set(float(pos), timeout=30.0)

            # Dwell time
            await anyio.sleep(plan.dwell)

            # Acquire detector data
            detector_data = await detector.read()

            # Emit reading event
            reading = Event(
                kind=EventKind.READING,
                run_uid=run_uid,
                data={
                    "point_index": i,
                    "motor_position": float(pos),
                    "motor_name": motor.schema.name,
                    "detector_name": detector.schema.name,
                    **detector_data,
                },
            )
            await bus.emit(reading)
            yield reading

            # Emit progress event
            fraction = (i + 1) / plan.num
            elapsed = time.time() - start_time
            eta_seconds = (elapsed / fraction) - elapsed if fraction > 0 else 0.0

            progress = Event(
                kind=EventKind.PROGRESS,
                run_uid=run_uid,
                data={
                    "fraction": fraction,
                    "eta_seconds": eta_seconds,
                    "point_index": i,
                    "total_points": plan.num,
                },
            )
            await bus.emit(progress)
            yield progress

        # Emit stop event on clean completion
        stop = Event(
            kind=EventKind.STOP,
            run_uid=run_uid,
            data={"message": "Scan completed successfully"},
        )
        await bus.emit(stop)
        yield stop

    except Exception as e:
        # Emit error event with traceback
        error = Event(
            kind=EventKind.ERROR,
            run_uid=run_uid,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        await bus.emit(error)
        yield error
        raise

    finally:
        # Always unstage devices, even on abort/error
        try:
            await motor.unstage()
        except Exception as e:
            # Log but don't raise during cleanup
            warning = Event(
                kind=EventKind.WARNING,
                run_uid=run_uid,
                data={
                    "message": f"Motor unstage failed: {e}",
                    "device": motor.schema.name,
                },
            )
            await bus.emit(warning)

        try:
            await detector.unstage()
        except Exception as e:
            warning = Event(
                kind=EventKind.WARNING,
                run_uid=run_uid,
                data={
                    "message": f"Detector unstage failed: {e}",
                    "device": detector.schema.name,
                },
            )
            await bus.emit(warning)


async def grid_scan(
    motor_x: Movable,
    motor_y: Movable,
    detector: Readable,
    x_start: float,
    x_stop: float,
    x_num: int,
    y_start: float,
    y_stop: float,
    y_num: int,
    dwell: float,
    bus: EventBus,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[Event, None]:
    """Execute 2D grid scan with snake pattern.

    Scans in row-major order (y outer loop, x inner loop) with snake pattern
    to minimize total motion time.

    Args:
        motor_x: X-axis motor.
        motor_y: Y-axis motor.
        detector: Detector device.
        x_start: X scan start position.
        x_stop: X scan stop position.
        x_num: Number of X points.
        y_start: Y scan start position.
        y_stop: Y scan stop position.
        y_num: Number of Y points.
        dwell: Dwell time per point (seconds).
        bus: EventBus for broadcasting.
        metadata: Optional user metadata dict.

    Yields:
        Events (DESCRIPTOR, READING, PROGRESS, STOP, ERROR).
    """
    run_uid = str(uuid.uuid4())
    x_positions = np.linspace(x_start, x_stop, x_num)
    y_positions = np.linspace(y_start, y_stop, y_num)
    total_points = x_num * y_num
    start_time = time.time()

    # Emit descriptor
    descriptor = Event(
        kind=EventKind.DESCRIPTOR,
        run_uid=run_uid,
        data={
            "scan_type": "grid_scan_2d",
            "motor_x_schema": motor_x.schema.model_dump(),
            "motor_y_schema": motor_y.schema.model_dump(),
            "detector_schema": detector.schema.model_dump(),
            "x_points": x_num,
            "y_points": y_num,
            "total_points": total_points,
            "metadata": metadata or {},
        },
    )
    await bus.emit(descriptor)
    yield descriptor

    try:
        await motor_x.stage()
        await motor_y.stage()
        await detector.stage()

        point_index = 0
        for j, y_pos in enumerate(y_positions):
            # Move Y axis
            await motor_y.set(float(y_pos), timeout=30.0)

            # Snake pattern: reverse X direction on odd rows
            x_scan = x_positions if j % 2 == 0 else x_positions[::-1]

            for x_pos in x_scan:
                # Check for cancellation
                with anyio.CancelScope() as cancel_scope:
                    if cancel_scope.cancel_called:
                        break

                # Move X axis
                await motor_x.set(float(x_pos), timeout=30.0)

                # Dwell
                await anyio.sleep(dwell)

                # Acquire
                detector_data = await detector.read()

                # Emit reading
                reading = Event(
                    kind=EventKind.READING,
                    run_uid=run_uid,
                    data={
                        "point_index": point_index,
                        "x_position": float(x_pos),
                        "y_position": float(y_pos),
                        "x_index": int(np.where(x_positions == x_pos)[0][0]),
                        "y_index": j,
                        **detector_data,
                    },
                )
                await bus.emit(reading)
                yield reading

                # Emit progress
                point_index += 1
                fraction = point_index / total_points
                elapsed = time.time() - start_time
                eta_seconds = (elapsed / fraction) - elapsed if fraction > 0 else 0.0

                progress = Event(
                    kind=EventKind.PROGRESS,
                    run_uid=run_uid,
                    data={
                        "fraction": fraction,
                        "eta_seconds": eta_seconds,
                        "point_index": point_index,
                        "total_points": total_points,
                    },
                )
                await bus.emit(progress)
                yield progress

        # Stop event
        stop = Event(
            kind=EventKind.STOP,
            run_uid=run_uid,
            data={"message": "Grid scan completed successfully"},
        )
        await bus.emit(stop)
        yield stop

    except Exception as e:
        error = Event(
            kind=EventKind.ERROR,
            run_uid=run_uid,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        await bus.emit(error)
        yield error
        raise

    finally:
        for device in [motor_x, motor_y, detector]:
            try:
                await device.unstage()
            except Exception as e:
                warning = Event(
                    kind=EventKind.WARNING,
                    run_uid=run_uid,
                    data={
                        "message": f"Device unstage failed: {e}",
                        "device": device.schema.name,
                    },
                )
                await bus.emit(warning)


async def time_scan(
    detector: Readable,
    duration: float,
    interval: float,
    bus: EventBus,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[Event, None]:
    """Execute time-series acquisition at fixed intervals.

    Args:
        detector: Detector device.
        duration: Total scan duration (seconds).
        interval: Time between acquisitions (seconds).
        bus: EventBus for broadcasting.
        metadata: Optional user metadata dict.

    Yields:
        Events (DESCRIPTOR, READING, PROGRESS, STOP, ERROR).

    Example:
        >>> # Acquire photodiode reading every 0.5s for 60s
        >>> async for event in time_scan(photodiode, 60.0, 0.5, bus):
        ...     if event.kind == EventKind.READING:
        ...         print(event.data)
    """
    run_uid = str(uuid.uuid4())
    num_points = int(duration / interval)
    start_time = time.time()

    # Emit descriptor
    descriptor = Event(
        kind=EventKind.DESCRIPTOR,
        run_uid=run_uid,
        data={
            "scan_type": "time_scan",
            "detector_schema": detector.schema.model_dump(),
            "duration": duration,
            "interval": interval,
            "num_points": num_points,
            "metadata": metadata or {},
        },
    )
    await bus.emit(descriptor)
    yield descriptor

    try:
        await detector.stage()

        point_index = 0
        next_acquisition = start_time + interval

        while (time.time() - start_time) < duration:
            # Sleep until next acquisition time
            sleep_duration = next_acquisition - time.time()
            if sleep_duration > 0:
                await anyio.sleep(sleep_duration)

            # Check for cancellation
            with anyio.CancelScope() as cancel_scope:
                if cancel_scope.cancel_called:
                    break

            # Acquire
            detector_data = await detector.read()
            elapsed = time.time() - start_time

            # Emit reading
            reading = Event(
                kind=EventKind.READING,
                run_uid=run_uid,
                data={
                    "point_index": point_index,
                    "elapsed_time": elapsed,
                    **detector_data,
                },
            )
            await bus.emit(reading)
            yield reading

            # Emit progress
            point_index += 1
            fraction = elapsed / duration
            eta_seconds = duration - elapsed

            progress = Event(
                kind=EventKind.PROGRESS,
                run_uid=run_uid,
                data={
                    "fraction": fraction,
                    "eta_seconds": eta_seconds,
                    "point_index": point_index,
                    "elapsed_time": elapsed,
                },
            )
            await bus.emit(progress)
            yield progress

            # Update next acquisition time
            next_acquisition += interval

        # Stop event
        stop = Event(
            kind=EventKind.STOP,
            run_uid=run_uid,
            data={"message": "Time scan completed successfully"},
        )
        await bus.emit(stop)
        yield stop

    except Exception as e:
        error = Event(
            kind=EventKind.ERROR,
            run_uid=run_uid,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        await bus.emit(error)
        yield error
        raise

    finally:
        try:
            await detector.unstage()
        except Exception as e:
            warning = Event(
                kind=EventKind.WARNING,
                run_uid=run_uid,
                data={
                    "message": f"Detector unstage failed: {e}",
                    "device": detector.schema.name,
                },
            )
            await bus.emit(warning)
