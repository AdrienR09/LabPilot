"""Thin synchronous HTTP client for the LabPilot backend, plus a background
poller that keeps its blocking calls off the Qt GUI thread.

Used by the native Qt instrument windows (instrument_windows.py) to read
real instrument data and write real settings — the same backend the React
frontend talks to over `@/api`, just called from Python instead of JS.
"""

from __future__ import annotations

import json
import time
from typing import Any

from PyQt6.QtCore import (
    QCoreApplication, QObject, QThread, QTimer, QUrl, Qt, QMetaObject, Q_ARG, pyqtSignal, pyqtSlot,
)
from PyQt6.QtWebSockets import QWebSocket

from core.api_client import LabPilotClient

# The Qt-free HTTP client body used to live here directly; it's now
# core.api_client.LabPilotClient (also used by notebook_api.py, so
# notebook/IPython kernels don't need to pull in PyQt6 just to talk to
# the backend). Re-exported under this name since every desktop-app
# caller (instrument_windows.py, workflow_window.py, ...) imports
# BackendClient from here.
BackendClient = LabPilotClient


class _PollWorker(QObject):
    """Runs on the poller's background thread. Owns its own QTimer + its
    own BackendClient (an httpx.Client isn't thread-safe to share), so
    every read happens off the GUI thread."""

    dataReady = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str, instrument_id: str, interval_ms: int) -> None:
        super().__init__()
        self._base_url = base_url
        self._instrument_id = instrument_id
        self._interval_ms = interval_ms
        self._client: BackendClient | None = None
        self._timer: QTimer | None = None

    @pyqtSlot()
    def start(self) -> None:
        # Constructed here (not in __init__) so the httpx.Client is created
        # on the thread that will actually use it.
        self._client = BackendClient(self._base_url)
        self._timer = QTimer(self)  # parented so its lifetime is tied to ours
        self._timer.timeout.connect(self._poll)
        self._timer.start(self._interval_ms)
        self._poll()

    @pyqtSlot()
    def stop(self) -> None:
        # Invoked via BlockingQueuedConnection (see InstrumentPoller.stop),
        # so this runs synchronously on this worker's own thread while its
        # event loop is still active — destroying the timer anywhere else
        # trips Qt's "timer stopped from another thread" check.
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
            # deleteLater() only schedules destruction for the next event
            # loop pass; process it now, still on this thread, so the
            # QTimer is actually gone before the caller (blocked on us)
            # goes on to quit() this thread.
            QCoreApplication.processEvents()
        if self._client is not None:
            self._client.close()
            self._client = None

    @pyqtSlot(int)
    def set_interval(self, ms: int) -> None:
        self._interval_ms = ms
        if self._timer is not None:
            self._timer.setInterval(ms)

    def _poll(self) -> None:
        try:
            data = self._client.read(self._instrument_id)
            self.dataReady.emit(data)
        except Exception as e:
            self.errorOccurred.emit(str(e))


class InstrumentPoller(QObject):
    """Polls GET /instruments/{id}/data on a background QThread and emits
    the result back on the GUI thread via queued Qt signals.

    PyQt is single-threaded for GUI work: a blocking HTTP call made
    directly from a QTimer callback on the main thread stalls every open
    window for the round-trip duration. With several native instrument
    windows open at once, each polling every ~200ms, those stalls stack up
    into visible lag/jank. Running the request on its own thread keeps the
    GUI thread free to paint and handle input regardless of how long a poll
    takes.
    """

    dataReady = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str, instrument_id: str, interval_ms: int = 200, parent=None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _PollWorker(base_url, instrument_id, interval_ms)
        self._worker.moveToThread(self._thread)
        self._worker.dataReady.connect(self.dataReady)
        self._worker.errorOccurred.connect(self.errorOccurred)
        self._thread.started.connect(self._worker.start)

    def start(self) -> None:
        self._thread.start()

    def set_interval(self, ms: int) -> None:
        # Never touch the worker's QTimer directly from here (wrong
        # thread) — BlockingQueuedConnection runs it on the worker thread
        # and only returns once it's actually done.
        QMetaObject.invokeMethod(
            self._worker, "set_interval", Qt.ConnectionType.BlockingQueuedConnection,
            Q_ARG(int, ms),
        )

    def stop(self) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
        self._thread.quit()
        self._thread.wait(1000)


class WorkflowStatePoller(QObject):
    """Drives workflow_window.py's live result view + status label —
    genuinely event-based now, not polling.

    Used to be a QThread + QTimer hitting GET /workflows/{id}/execution_state
    every `interval_ms`. For an ND scan, that response carries the FULL
    accumulated flat data array (up to millions of floats, growing every
    point — session.report_progress() sends the whole thing, not a delta),
    so re-fetching/re-parsing it 2-3x/second for the whole duration of a
    scan was real, unnecessary work on both ends — the root of "why does
    scanner acquisition also take that much time... synchronous polling".

    The backend already had a real event pipeline for this
    (session.report_progress emits WORKFLOW_PROGRESS on the event bus,
    server.py's /ws endpoint broadcasts it) that this class just wasn't
    using. QWebSocket is itself Qt-signal/slot/event-loop-driven (like the
    rest of Qt's socket I/O), so no background QThread is needed here
    either — connecting/receiving doesn't block the GUI thread.

    One HTTP GET still happens, exactly once, in start(): a workflow that
    finished before this window even opened has no future event to tell us
    that — its last_results only exist in already-past events nothing will
    re-emit. Every update after that is push, not poll.

    A template that also calls session.report_reading() per point (see
    omniscan.py) additionally gets EventKind.READING events here — small
    and the same size on every call, unlike WORKFLOW_PROGRESS (which
    carries the full accumulated result, thinned before broadcast — see
    server.py). Those get applied to a buffer this class maintains itself
    (_live_data), the same way qudi/pyMoDAQ's GUI modules hold and mutate
    their own array in place rather than having it resent whole each
    time — matching how those projects actually do live scan display,
    which is the point of building this the way it is. Every reading is
    applied to that buffer the instant it arrives, with nothing dropped
    or delayed. Only the resulting *redraw* (reshaping the buffer into a
    numpy array and repainting — measured at ~60ms for a ~5M-element ND
    scan) is paced by a short local timer: at 20-30 scan points/second
    (typical for real hardware) redrawing on literally every single one
    would spend more wall-clock time reshaping arrays than the scan
    itself takes, the same reason qudi's own scanner logic redraws once
    per line rather than once per pixel. Unlike the old design, this
    pacing costs no network round trip and no JSON parse of a huge
    payload — it was exactly that (a debounced GET of a multi-megabyte
    REST snapshot) that could exceed the 5s httpx timeout during a long
    scan; this class no longer refetches anything mid-scan for a
    reading-emitting template.
    """

    stateReady = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    _RECONNECT_DELAY_MS = 1500
    _PROGRESS_REFRESH_MS = 150
    _REDRAW_MS = 50
    _LIVE_RESYNC_MS = 3000

    def __init__(self, base_url: str, workflow_id: str, interval_ms: int = 400, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._workflow_id = workflow_id
        self._client = BackendClient(base_url)
        self._state: dict[str, Any] = {
            "running": False, "execution_id": None, "progress": None,
            "last_status": None, "last_started_at": None,
            "last_completed_at": None, "last_results": None,
        }
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
        self._socket = QWebSocket()
        self._socket.textMessageReceived.connect(self._on_message)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(lambda _err: self.errorOccurred.emit(self._socket.errorString()))
        self._url = QUrl(ws_url)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(self._RECONNECT_DELAY_MS)
        self._reconnect_timer.timeout.connect(self._connect)
        # A WORKFLOW_PROGRESS event itself no longer carries the full data
        # array (server.py's _event_broadcaster strips it before
        # broadcasting — re-serializing/re-sending the whole, ever-growing
        # array on every single reported point was the real cost behind
        # "scan acquisition takes a long time", independent of transport).
        # It's a "something changed" signal; this timer coalesces a burst
        # of them into one GET execution_state ~150ms after the last one,
        # the same debounce pattern workflow_result.py's crosshair refresh
        # uses — so a fast scan (many points/sec) still only re-fetches
        # the heavy snapshot at a bounded rate, while a slow scan still
        # updates promptly after each point.
        self._progress_refresh_timer = QTimer(self)
        self._progress_refresh_timer.setSingleShot(True)
        self._progress_refresh_timer.setInterval(self._PROGRESS_REFRESH_MS)
        self._progress_refresh_timer.timeout.connect(self._fetch_progress_snapshot)

        # Local buffer for EventKind.READING-driven templates (omniscan.py) —
        # allocated on the first reading of a run, spliced into on every
        # one after that. None means "no reading-based live data for this
        # run yet" (either not started, or this template doesn't emit
        # readings at all — WORKFLOW_PROGRESS's existing debounced-refetch
        # path above still covers that case untouched).
        self._live_data: list | None = None
        self._live_meta: dict[str, Any] = {}
        # A repeating (not single-shot) timer: a debounce that resets on
        # every tick can starve indefinitely under a steady stream of
        # readings arriving faster than its interval (never fires until
        # the stream pauses) — exactly the "every point" case this needs
        # to handle well. This is a throttle instead: runs continuously,
        # redraws at most once per tick but at LEAST once per tick
        # whenever a reading arrived since the last one (_redraw_pending).
        self._redraw_pending = False
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setInterval(self._REDRAW_MS)
        self._redraw_timer.timeout.connect(self._maybe_redraw)
        self._redraw_timer.start()

        # Safety net against a dropped READING event: core/events.py's
        # EventBus.emit() does queue.put_nowait() into a bounded (1000)
        # per-subscriber queue and silently discards the event on
        # asyncio.QueueFull — which a fast/large scan can hit, since
        # _event_broadcaster does one real network send per event,
        # serially, and omniscan.py emits two events per point (progress +
        # reading). A dropped READING event leaves a permanent gap in
        # _live_data (nothing else ever re-fills that index — see
        # _on_message's WORKFLOW_PROGRESS branch, which skips its own
        # resync once reading data is flowing). session.report_progress()'s
        # sink write is synchronous/in-process and bypasses the event bus
        # entirely, so it's always current regardless of any drop — this
        # timer periodically re-fetches it and heals any gap. Rare enough
        # (every few seconds, not every point) to not reintroduce the
        # per-point refetch cost this class exists to avoid.
        self._live_resync_timer = QTimer(self)
        self._live_resync_timer.setInterval(self._LIVE_RESYNC_MS)
        self._live_resync_timer.timeout.connect(self._resync_live_data)
        self._live_resync_timer.start()

        self._stopped = True

    def start(self) -> None:
        self._stopped = False
        self._connect()

    def stop(self) -> None:
        self._stopped = True
        self._reconnect_timer.stop()
        self._progress_refresh_timer.stop()
        self._redraw_timer.stop()
        self._live_resync_timer.stop()
        self._socket.close()
        self._client.close()

    def _fetch_progress_snapshot(self) -> None:
        try:
            self._state = self._client.get_workflow_execution_state(self._workflow_id)
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return
        self.stateReady.emit(dict(self._state))

    def _connect(self) -> None:
        # Runs before every (re)connect, not just the first: a workflow
        # that finished (or an event that fired) while we were never
        # connected yet, or briefly disconnected, has no future event to
        # replay it — only a fresh GET can recover it.
        try:
            self._state = self._client.get_workflow_execution_state(self._workflow_id)
            self.stateReady.emit(dict(self._state))
        except Exception as e:
            self.errorOccurred.emit(str(e))
        self._socket.open(self._url)

    def _on_disconnected(self) -> None:
        # A dropped connection mid-scan (network hiccup, backend restart)
        # would otherwise freeze the UI on its last-seen frame forever.
        if self._stopped:
            return
        self._reconnect_timer.start()

    def _on_message(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except (ValueError, TypeError):
            return
        if msg.get("type") != "event":
            return
        event = msg.get("event") or {}
        data = event.get("data") or {}
        if data.get("workflow_id") != self._workflow_id:
            return

        kind = event.get("kind")
        if kind == "WORKFLOW_STARTED":
            self._state.update({
                "running": True, "execution_id": data.get("execution_id"), "progress": None,
            })
            # Fresh run — don't carry over a previous run's reading buffer.
            # Whether this run emits readings at all is discovered from the
            # first one that actually arrives, if any.
            self._live_data = None
            self._live_meta = {}
        elif kind == "READING":
            self._on_reading(data)
            return
        elif kind == "WORKFLOW_PROGRESS":
            self._state["running"] = True
            # A reading-emitting template already has fresher data flowing
            # through _on_reading/_do_redraw at a fraction of the cost —
            # re-fetching the full REST snapshot here too would reintroduce
            # exactly the network-round-trip + huge-JSON-parse cost (and
            # the resulting timeout risk) that path exists to avoid.
            if self._live_data is None:
                self._progress_refresh_timer.start()
            return
        elif kind == "WORKFLOW_COMPLETED":
            self._state.update({
                "running": False, "last_status": "completed",
                "last_completed_at": time.time(), "last_results": data.get("results"),
            })
        elif kind == "WORKFLOW_ERROR":
            self._state.update({
                "running": False, "last_status": "failed",
                "last_completed_at": time.time(), "last_results": {"error": data.get("error")},
            })
        elif kind == "WORKFLOW_STOPPED":
            self._state.update({"running": False, "last_status": "cancelled"})
        else:
            return
        self._redraw_pending = False
        self.stateReady.emit(dict(self._state))

    def _on_reading(self, data: dict) -> None:
        shape = data.get("shape")
        if shape is None:
            return
        total = 1
        for n in shape:
            total *= n
        if self._live_data is None or self._live_meta.get("shape") != shape:
            # First reading of a run (or the shape changed — a new run
            # started without a WORKFLOW_STARTED getting through, e.g. a
            # reconnect): (re)allocate. None-filled like omniscan.py's own
            # server-side buffer, so unfilled points render as gaps, not 0.
            self._live_data = [None] * total
        self._live_meta = {
            "shape": shape,
            "axis_names": data.get("axis_names"),
            "axis_positions": data.get("axis_positions"),
            "actuator_axis_count": data.get("actuator_axis_count"),
            "completed": data.get("completed"),
            "total": data.get("total"),
        }
        index = data.get("index")
        values = data.get("values")
        if index is not None and values is not None:
            self._live_data[index:index + len(values)] = values
        self._state["running"] = True
        self._redraw_pending = True

    def _maybe_redraw(self) -> None:
        if not self._redraw_pending or self._live_data is None:
            return
        self._redraw_pending = False
        self._state["progress"] = {"data": self._live_data, **self._live_meta}
        self.stateReady.emit(dict(self._state))

    def _resync_live_data(self) -> None:
        if not self._state.get("running") or self._live_data is None:
            return
        try:
            state = self._client.get_workflow_execution_state(self._workflow_id)
        except Exception:
            return
        progress = state.get("progress") or {}
        data = progress.get("data")
        # Only trust it if it's still describing the run we think is live —
        # a stale/mismatched shape (e.g. a new run started between the
        # request and this reply) would corrupt _live_data worse than the
        # gap it's meant to fix.
        if not data or progress.get("shape") != self._live_meta.get("shape"):
            return
        self._live_data = list(data)
        self._redraw_pending = True


class _OptimizePollWorker(QObject):
    """Same off-GUI-thread rationale as _PollWorker above, calling
    get_optimize_state(workflow_id) instead of read(instrument_id) — a
    faster default interval than WorkflowStatePoller's since an optimize
    run is deliberately quick and its dock should feel live while
    watching it happen."""

    stateReady = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str, workflow_id: str, interval_ms: int) -> None:
        super().__init__()
        self._base_url = base_url
        self._workflow_id = workflow_id
        self._interval_ms = interval_ms
        self._client: BackendClient | None = None
        self._timer: QTimer | None = None

    @pyqtSlot()
    def start(self) -> None:
        self._client = BackendClient(self._base_url)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self._interval_ms)
        self._poll()

    @pyqtSlot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
            QCoreApplication.processEvents()
        if self._client is not None:
            self._client.close()
            self._client = None

    def _poll(self) -> None:
        try:
            state = self._client.get_optimize_state(self._workflow_id)
            self.stateReady.emit(state)
        except Exception as e:
            self.errorOccurred.emit(str(e))


class OptimizePoller(QObject):
    """Polls GET /workflows/{id}/optimize/state on a background QThread —
    see InstrumentPoller above for the full threading rationale, identical
    here. Drives the OptimizerDockWidget's live grid + best-position
    marker while an optimize run is in progress."""

    stateReady = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str, workflow_id: str, interval_ms: int = 150, parent=None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _OptimizePollWorker(base_url, workflow_id, interval_ms)
        self._worker.moveToThread(self._thread)
        self._worker.stateReady.connect(self.stateReady)
        self._worker.errorOccurred.connect(self.errorOccurred)
        self._thread.started.connect(self._worker.start)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
        self._thread.quit()
        self._thread.wait(1000)
