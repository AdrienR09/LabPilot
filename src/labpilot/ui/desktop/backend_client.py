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
    Q_ARG,
    QCoreApplication,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWebSockets import QWebSocket

from labpilot.core.api_client import LabPilotClient

# The Qt-free HTTP client body used to live here directly; it's now
# core.api_client.LabPilotClient (also used by notebook_api.py, so
# notebook/IPython kernels don't need to pull in PyQt6 just to talk to
# the backend). Re-exported under this name since every desktop-app
# caller (instrument_windows.py, workflow_window.py, ...) imports
# BackendClient from here.
BackendClient = LabPilotClient


class _WriteWorker(QObject):
    """Runs on AsyncWriter's own thread — an httpx.Client isn't
    thread-safe to share, so this gets its own BackendClient, same
    reasoning as _PollWorker above."""

    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._client: BackendClient | None = None

    @pyqtSlot(str, dict)
    def write(self, instrument_id: str, values: dict) -> None:
        if self._client is None:
            self._client = BackendClient(self._base_url)
        try:
            self._client.write(instrument_id, values)
        except Exception as e:
            self.errorOccurred.emit(str(e))

    @pyqtSlot()
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


class AsyncWriter(QObject):
    """Fire-and-forget instrument writes off the GUI thread.

    A crosshair/slider drag calls write() on every debounced move tick
    (~30ms). A direct, synchronous `self.client.write(...)` call from
    that handler blocks the ENTIRE window — no repaint, no input — for
    the whole HTTP round trip, every tick: that was the actual reason
    dragging the crosshair and watching the axes-control slider "move
    synchronously" never worked, and the reason a drag itself felt
    laggy. The widget on the other end of a drag's `on_change` callback
    (`AxesControlWidget.set_target`/`NDScanResultView.set_position`) is
    already a plain, instant, local Qt update with no network in it —
    what stalled everything was the blocking write call sitting on the
    same call stack, one GUI-thread freeze per tick. Same off-GUI-thread
    rationale as InstrumentPoller/_PollWorker above, just fire-and-forget
    (nothing to poll for or wait on) instead of a repeating read.
    """

    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _WriteWorker(base_url)
        self._worker.moveToThread(self._thread)
        self._worker.errorOccurred.connect(self.errorOccurred)
        self._thread.start()

    def write(self, instrument_id: str, values: dict) -> None:
        QMetaObject.invokeMethod(
            self._worker, "write", Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, instrument_id), Q_ARG(dict, values),
        )

    def stop(self) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "close", Qt.ConnectionType.BlockingQueuedConnection)
        self._thread.quit()
        self._thread.wait(1000)


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


class _SnapshotFetchWorker(QObject):
    """Runs GET /workflows/{id}/execution_state on its own thread, on
    demand (not a fixed-interval poll — see WorkflowStatePoller, which
    calls `fetch()` only when it actually needs a fresh snapshot: on
    (re)connect, once early in a reading-less run, and periodically as a
    resync safety net).

    WorkflowStatePoller's whole reason to prefer small WORKFLOW_PROGRESS/
    READING events over refetching this snapshot is that the snapshot
    carries the FULL accumulated result — up to tens of megabytes of JSON
    for a large ND scan (measured: ~31MB / ~0.55s for a modest 30-point,
    (32,32,64)-cube scan; a longer scan or a bigger detector is worse).
    Every call site that still needs one every now and then was, until
    now, calling it directly from a QTimer/QWebSocket callback — i.e. on
    the GUI thread — so each such fetch froze the whole window solid for
    however long that GET took. Same rationale as _PollWorker/
    InstrumentPoller above (a blocking HTTP call from a GUI-thread
    callback stalls painting/input for its whole duration); this is that
    same fix applied to WorkflowStatePoller's own remaining fetch calls."""

    #: `purpose` is opaque here — just echoed back alongside the result so
    #: the caller (WorkflowStatePoller has two independent fetch call
    #: sites with different staleness-tracking needs — see its own
    #: `_state_fetch_seq`/`_resync_fetch_seq`) knows which of its own
    #: pending requests this reply answers.
    resultReady = pyqtSignal(dict, int, str)
    errorOccurred = pyqtSignal(str)

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._client: BackendClient | None = None

    @pyqtSlot(str, int, str)
    def fetch(self, workflow_id: str, seq: int, purpose: str) -> None:
        if self._client is None:
            # Created here (not in __init__) so the httpx.Client is built
            # on the thread that will actually use it — same reasoning as
            # _PollWorker.start().
            self._client = BackendClient(self._base_url)
        try:
            data = self._client.get_workflow_execution_state(workflow_id)
            self.resultReady.emit(data, seq, purpose)
        except Exception as e:
            self.errorOccurred.emit(str(e))

    @pyqtSlot()
    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


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
    rest of Qt's socket I/O), so no background QThread is needed for THAT
    part — connecting/receiving doesn't block the GUI thread.

    A handful of GET /execution_state calls still happen — on (re)connect,
    once early in a run before any reading has arrived, and periodically
    as a resync safety net (_resync_live_data) — since some information
    (a workflow that finished before this window even opened, or a
    dropped event) only a fresh GET can recover. Every one of those goes
    through `_fetch_worker` (a `_SnapshotFetchWorker` on its own QThread),
    never called directly from a QTimer/QWebSocket callback: measured at
    ~0.55s for a modest 30-point ND-detector scan's full snapshot (tens
    of megabytes of JSON for anything bigger), a direct call would freeze
    the whole window solid for that long, every time one fired — this
    was the actual remaining cause of "the workflow window still lags/
    freezes" after the rest of this class had already stopped fixed-
    interval polling. Every update besides those few on-demand fetches is
    push, not poll.

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
        self._state: dict[str, Any] = {
            "running": False, "execution_id": None, "progress": None,
            "last_status": None, "last_started_at": None,
            "last_completed_at": None, "last_results": None,
        }
        # Every GET /execution_state call this class still makes goes
        # through this worker's own thread — see _SnapshotFetchWorker's
        # docstring for why a direct call would freeze the GUI thread.
        # `fetch()` calls are fire-and-forget (QueuedConnection, never
        # blocked on), so more than one can be in flight if a slow one is
        # still out when the next timer fires; two independent "latest
        # requested" sequence counters (one per call site/purpose — full-
        # state-replace vs merge-into-_live_data, handled completely
        # differently below) let a stale reply be dropped instead of
        # clobbering newer state that arrived (via the websocket, or a
        # newer fetch of the same purpose) in the meantime.
        self._fetch_thread = QThread()
        self._fetch_worker = _SnapshotFetchWorker(base_url)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_worker.resultReady.connect(self._on_snapshot_fetched)
        self._fetch_worker.errorOccurred.connect(self.errorOccurred)
        self._fetch_thread.start()
        self._state_fetch_seq = 0
        self._resync_fetch_seq = 0
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
        # It's a "something changed" signal; a template with no READING
        # events at all (_run_hardware_timed — no per-point actuator write
        # to piggyback a reading on) relies on this as its ONLY live-refresh
        # path. A REPEATING timer with a "pending" flag, not a single-shot
        # one restarted on every event: that used to be a single-shot timer
        # re-`start()`ed here on every WORKFLOW_PROGRESS, which is exactly
        # the "debounce that resets on every tick can starve indefinitely
        # under a steady stream" trap `_redraw_timer` below was deliberately
        # built to avoid — a hardware-timed scan reports progress roughly
        # every 100ms (HardwareTimedScanCapability.POLL_INTERVAL_S), faster
        # than the old 150ms debounce, so it never fired until the stream
        # stopped, i.e. until the scan finished (the plot sitting frozen for
        # the whole run, then jumping straight to the complete image). This
        # throttles instead: fires on a fixed cadence, fetching at most once
        # per tick but at least once per tick whenever progress arrived
        # since the last one.
        self._progress_pending = False
        self._progress_refresh_timer = QTimer(self)
        self._progress_refresh_timer.setInterval(self._PROGRESS_REFRESH_MS)
        self._progress_refresh_timer.timeout.connect(self._maybe_fetch_progress_snapshot)
        self._progress_refresh_timer.start()

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
        QMetaObject.invokeMethod(self._fetch_worker, "close", Qt.ConnectionType.BlockingQueuedConnection)
        self._fetch_thread.quit()
        self._fetch_thread.wait(1000)

    def _request_snapshot(self, purpose: str) -> None:
        """Fire off one GET /execution_state on `_fetch_worker`'s own
        thread — never blocks; the result (if it's still the latest one
        requested for this `purpose`) arrives later via
        `_on_snapshot_fetched`. `purpose` is "state" (_connect/
        _fetch_progress_snapshot: replace self._state wholesale) or
        "resync" (_resync_live_data: merge into self._live_data only)."""
        if purpose == "state":
            self._state_fetch_seq += 1
            seq = self._state_fetch_seq
        else:
            self._resync_fetch_seq += 1
            seq = self._resync_fetch_seq
        QMetaObject.invokeMethod(
            self._fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, self._workflow_id), Q_ARG(int, seq), Q_ARG(str, purpose),
        )

    def _on_snapshot_fetched(self, data: dict, seq: int, purpose: str) -> None:
        if purpose == "state":
            if seq != self._state_fetch_seq:
                return  # superseded by a newer request already in flight
            self._state = data
            self.stateReady.emit(dict(self._state))
        else:
            if seq != self._resync_fetch_seq:
                return
            self._apply_resync(data)

    def _maybe_fetch_progress_snapshot(self) -> None:
        if not self._progress_pending:
            return
        self._progress_pending = False
        self._request_snapshot("state")

    def _connect(self) -> None:
        # Runs before every (re)connect, not just the first: a workflow
        # that finished (or an event that fired) while we were never
        # connected yet, or briefly disconnected, has no future event to
        # replay it — only a fresh GET can recover it. Fired off
        # concurrently with opening the socket (not awaited first) since
        # the two are independent and the fetch may take a while for a
        # large snapshot.
        self._request_snapshot("state")
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
                self._progress_pending = True
            return
        elif kind == "WORKFLOW_COMPLETED":
            self._state.update({
                "running": False, "last_status": "completed",
                "last_completed_at": time.time(), "last_results": data.get("results"),
            })
            # server.py's _event_broadcaster strips any oversized field
            # from EVERY event's data before broadcasting it (a large
            # scan's full result is exactly that — see its own docstring:
            # an un-thinned WORKFLOW_COMPLETED once produced a single
            # ~15MB frame that broke the WebSocket connection outright).
            # So "results" here may be missing its own bulky field(s)
            # (e.g. omniscan's "data") — this immediate update above is
            # just the fast, optimistic "it's done" signal (status label,
            # etc.); the authoritative complete result still needs a
            # real fetch, done here off the GUI thread exactly like
            # _connect's/_resync_live_data's own fetches.
            self._request_snapshot("state")
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
        self._request_snapshot("resync")

    def _apply_resync(self, state: dict) -> None:
        progress = state.get("progress") or {}
        data = progress.get("data")
        # Only trust it if it's still describing the run we think is live —
        # a stale/mismatched shape (e.g. a new run started between the
        # request and this reply) would corrupt _live_data worse than the
        # gap it's meant to fix.
        if not data or self._live_data is None or progress.get("shape") != self._live_meta.get("shape"):
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
