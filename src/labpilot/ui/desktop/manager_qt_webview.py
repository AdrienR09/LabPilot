#!/usr/bin/env python3
"""
LabPilot Manager - Qt Window with Embedded React Frontend
Uses QWebEngineView to display the React app you already built
Includes QtBridge for React-Qt communication
"""

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QVBoxLayout, QWidget

from labpilot.ui.desktop.console_window import ConsoleWindow
from labpilot.ui.desktop.main import LabPilotStyle
from labpilot.ui.desktop.managed_server import ManagedServer
from labpilot.ui.desktop.qt_bridge import QtBridge

# Long enough that a slow first paint is not reported as a fault, short
# enough to beat someone's patience with a dark window.
LOAD_STALL_WARNING_S = 20.0

# QtWebEngine is a full Chromium, and it picks up the machine's system proxy
# configuration — which on a managed lab PC is usually a corporate proxy, often
# via an auto-detected (WPAD) or PAC script. The page this window loads is
# served by a backend on this same machine, so a proxy is never the right route
# for it, and routing it through one that cannot answer stalls the load
# indefinitely: the window stays dark and its title sits at "Loading 0%". An
# ordinary browser escapes this because its own proxy settings bypass local
# addresses, which is why the same URL opens there and not here.
#
# --disable-gpu is NOT in this list: it costs real rendering performance and is
# only needed on a machine whose graphics driver QtWebEngine cannot use (or
# over a remote-desktop session). `--safe-graphics` adds it on request.
BASE_CHROMIUM_FLAGS = ("--no-proxy-server",)
SAFE_GRAPHICS_FLAGS = ("--disable-gpu", "--disable-gpu-compositing", "--disable-software-rasterizer")
CHROMIUM_FLAGS_ENV = "QTWEBENGINE_CHROMIUM_FLAGS"


def apply_chromium_flags(*, safe_graphics: bool = False) -> str:
    """Set the Chromium flags, and return what they ended up as.

    Must run before anything constructs a `QApplication`: QtWebEngine reads
    this variable once, while it initialises. Flags the caller already put in
    the environment are kept and placed last, so an explicit setting wins over
    every default here.
    """
    flags = [*BASE_CHROMIUM_FLAGS]
    if safe_graphics:
        flags += SAFE_GRAPHICS_FLAGS
    inherited = os.environ.get(CHROMIUM_FLAGS_ENV, "").strip()
    if inherited:
        flags.append(inherited)
    composed = " ".join(flags)
    os.environ[CHROMIUM_FLAGS_ENV] = composed
    return composed


class LabPilotManagerWindow(QMainWindow):
    """Main Qt window embedding the React frontend with Qt bridge"""

    def __init__(self, react_url: str = "http://localhost:3000", backend_url: str = "http://localhost:8000"):
        super().__init__()
        self.react_url = react_url
        self.backend_url = backend_url
        # Kept open here (rather than being purely local to
        # _open_console) so the window and its IPython kernel survive
        # for as long as this Manager window does, not just until the
        # toolbar-click handler returns.
        self._console_window: ConsoleWindow | None = None
        self.setup_bridge()
        self.setup_ui()
        self.setup_toolbar()

    def setup_toolbar(self):
        """A small native toolbar alongside the embedded React app — for
        things that open a separate native window rather than living
        inside the web page itself (see console_window.py)."""
        toolbar = QToolBar("Manager", self)
        self.addToolBar(toolbar)

        console_action = QAction(LabPilotStyle.icon("utilities-terminal"), "Console", self)
        console_action.setToolTip("Open an IPython console connected to this session (like Qudi's).")
        console_action.triggered.connect(self._open_console)
        toolbar.addAction(console_action)

    def _open_console(self):
        if self._console_window is not None:
            self._console_window.show()
            self._console_window.raise_()
            self._console_window.activateWindow()
            return
        self._console_window = ConsoleWindow(backend_url=self.backend_url)
        self._console_window.destroyed.connect(lambda: setattr(self, "_console_window", None))
        self._console_window.show()

    def setup_bridge(self):
        """Setup Qt-React communication bridge"""
        self.bridge = QtBridge(self, backend_url=self.backend_url)
        self.channel = QWebChannel()
        self.channel.registerObject("qtBridge", self.bridge)

    def setup_ui(self):
        """Setup Qt window with embedded web view"""
        self.setWindowTitle("LabPilot Manager")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Web engine view
        self.web_view = QWebEngineView()

        # Set web channel BEFORE loading the page
        self.web_view.page().setWebChannel(self.channel)

        # Configure web engine settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)

        # Say so when a load never finishes, rather than sitting dark.
        # Chromium reports no error for a request that hangs — it just
        # stops making progress — so a page whose first paint waits on an
        # unreachable host looks identical to a crashed app. That happened
        # for real: the built index.html loaded two render-blocking
        # webfont stylesheets from fonts.googleapis.com, and on a lab PC
        # with no internet the window stayed dark with its title at
        # "Loading 0%" and nothing anywhere said why.
        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.setInterval(int(LOAD_STALL_WARNING_S * 1000))
        self._stall_timer.timeout.connect(self.on_load_stalled)

        # Load React app
        self.web_view.setUrl(QUrl(self.react_url))

        # Monitor loading
        self.web_view.loadStarted.connect(self.on_load_started)
        self.web_view.loadFinished.connect(self.on_load_finished)
        self.web_view.loadProgress.connect(self.on_load_progress)

        layout.addWidget(self.web_view)

    def on_load_started(self):
        """Called when page loading starts"""
        print(f"📱 Page loading started: {self.react_url}")
        self.setWindowTitle("LabPilot Manager - Loading...")
        self._stall_timer.start()

    def on_load_stalled(self):
        """The page has been loading for an implausibly long time."""
        print(
            f"\n⚠️  {self.react_url} has not finished loading after "
            f"{LOAD_STALL_WARNING_S:.0f}s. The window will stay blank until it does.\n"
            "   Usually one of:\n"
            "   • the page is waiting on a host it cannot reach — a resource served "
            "from the internet on a machine that has none, which hangs rather than "
            "failing when a firewall drops the connection;\n"
            f"   • nothing is listening at {self.react_url} (check the backend started);\n"
            "   • the front-end bundle is there but incomplete.\n"
            "   Open the same URL in a browser. If it loads there, the server and the "
            "bundle are fine and the problem is this embedded browser — on a managed PC "
            "usually a system proxy it routes localhost through, or security software "
            "blocking QtWebEngineProcess. Try:\n"
            "     labpilot app --safe-graphics\n"
            "   and, failing that, work in a browser with `labpilot app --no-window`.",
            flush=True,
        )
        self.setWindowTitle("LabPilot Manager - still loading… (see the terminal)")

    def on_load_progress(self, progress: int):
        """Called when page loading progresses"""
        if progress % 25 == 0:
            print(f"📊 Page loading progress: {progress}%")
        self.setWindowTitle(f"LabPilot Manager - Loading {progress}%")

    def on_load_finished(self, success: bool):
        """Called when page finishes loading"""
        self._stall_timer.stop()
        if success:
            print("✅ React app loaded successfully")
            print("📡 Qt Bridge object is registered")
            print("🔧 Initializing Qt Bridge communication...")

            # Combined initialization script that handles everything
            setup_script = """
            (function() {
                console.log('🚀 Qt Bridge initialization starting...');

                // Step 1: Try loading QWebChannel if needed
                console.log('Step 1: Checking for QWebChannel...');
                if (typeof QWebChannel === 'undefined') {
                    console.log('  Loading qwebchannel.js from Qt resources...');
                    const script = document.createElement('script');
                    script.src = 'qrc:///qtwebchannel/qwebchannel.js';
                    script.onload = function() {
                        console.log('  ✅ qwebchannel.js loaded');
                    };
                    script.onerror = function() {
                        console.warn('  ⚠️  Could not load qwebchannel.js from qrc');
                    };
                    document.head.appendChild(script);
                } else {
                    console.log('  ✅ QWebChannel already available');
                }

                // Step 2: Wait a bit for everything to be ready, then initialize
                setTimeout(function() {
                    console.log('Step 2: Initializing after delay...');
                    console.log('  typeof QWebChannel:', typeof QWebChannel);
                    console.log('  typeof qt:', typeof qt);

                    if (typeof qt === 'undefined' || typeof qt.webChannelTransport === 'undefined') {
                        console.warn('  ⚠️  Qt WebEngine not available');
                        return;
                    }

                    if (typeof QWebChannel === 'undefined') {
                        console.warn('  ⚠️  QWebChannel not available');
                        return;
                    }

                    console.log('Step 3: Creating QWebChannel...');
                    try {
                        new QWebChannel(qt.webChannelTransport, function(channel) {
                            console.log('  ✅ QWebChannel initialized');
                            console.log('  Available objects:', Object.keys(channel.objects));

                            if (channel.objects && channel.objects.qtBridge) {
                                window.qtBridge = channel.objects.qtBridge;
                                console.log('  ✅ window.qtBridge set successfully');
                                console.log('  launchInstrumentUI type:', typeof window.qtBridge.launchInstrumentUI);

                                // Dispatch event for React
                                window.dispatchEvent(new CustomEvent('qt-bridge-ready'));
                                console.log('  ✅ qt-bridge-ready event dispatched');
                            } else {
                                console.error('  ❌ qtBridge not found in channel');
                            }
                        });
                    } catch (e) {
                        console.error('  ❌ QWebChannel error:', e.message);
                    }
                }, 300);
            })();
            """

            self.web_view.page().runJavaScript(setup_script)
            self.setWindowTitle("LabPilot Manager ✅")
            print("✅ Qt Bridge setup injected")
        else:
            print("❌ Failed to load React app")
            self.setWindowTitle("LabPilot Manager - Load Failed ❌")

    def reload(self):
        """Reload the React app"""
        self.web_view.reload()


def main():
    """Main entry point.

    By default, this manager now OWNS the LabPilot server's lifecycle —
    it spawns `labpilot start` itself as a separate OS process
    (`managed_server.ManagedServer`, same "launch a subprocess, log to a
    file, own its lifetime" convention as
    `launch_instrument.py`/`launch_workflow.py`), instead of assuming one
    is already running at `--backend-url`. It's a genuinely separate
    process rather than an in-process thread deliberately: that was
    tried first and reliably crashed (SIGBUS) as soon as `QWebEngineView`
    actually rendered anything, on both an offscreen test environment
    and real hardware — the same fork()-safety hazard the OS-process
    isolation for instrument/workflow windows already exists to avoid,
    now also applied to the server. The REST/WebSocket API itself is
    unaffected either way (same routes, same behavior) — everything
    downstream (the React frontend embedded below, QtBridge, spawned
    instrument/workflow windows, any remote client) only ever talks to
    "a server at host:port," not who's hosting it. Pass
    --external-backend to keep the old behavior (connect to an
    already-running, possibly remote, server instead).
    """
    import argparse

    parser = argparse.ArgumentParser(description="LabPilot Manager with embedded React frontend")
    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="URL of the React frontend (default: http://localhost:3000)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to run the managed backend server on (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the managed backend server on (default: 8000)",
    )
    parser.add_argument(
        "--external-backend",
        action="store_true",
        help="Don't launch a server — connect to an already-running one at --backend-url instead "
             "(e.g. a standalone `labpilot start`, possibly on a different machine).",
    )
    parser.add_argument(
        "--safe-graphics",
        action="store_true",
        help="Render without the GPU. For a machine whose graphics driver QtWebEngine "
             "cannot use, or a remote-desktop session, where the window is otherwise "
             "blank or black.",
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="URL of an already-running backend API — only used with --external-backend "
             "(default: http://localhost:8000)",
    )

    args = parser.parse_args()

    flags = apply_chromium_flags(safe_graphics=args.safe_graphics)
    print(f"🧭 QtWebEngine flags: {flags}", flush=True)

    managed_server: ManagedServer | None = None
    if args.external_backend:
        backend_url = args.backend_url
    else:
        managed_server = ManagedServer(host=args.host, port=args.port)
        managed_server.start()
        try:
            managed_server.wait_until_ready()
        except RuntimeError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        backend_url = managed_server.base_url

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Manager")
    app.setOrganizationName("Laboratory Automation")
    if managed_server is not None:
        app.aboutToQuit.connect(managed_server.stop)

    # Create and show manager window
    window = LabPilotManagerWindow(react_url=args.url, backend_url=backend_url)
    window.show()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  LabPilot Manager Started                    ║
╠══════════════════════════════════════════════════════════════╣
║  React Frontend: {args.url:44} ║
║  Backend API:    {backend_url:44} ║
║  Backend mode:   {"external (--external-backend)" if args.external_backend else "managed subprocess":44} ║
╠══════════════════════════════════════════════════════════════╣
║  The React frontend is embedded in this Qt window.           ║
║  Instrument UIs will open as separate Qt windows.            ║
╚══════════════════════════════════════════════════════════════╝
    """)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
