#!/usr/bin/env python3
"""
LabPilot Manager - Qt Window with Embedded React Frontend
Uses QWebEngineView to display the React app you already built
Includes QtBridge for React-Qt communication
"""

import sys
from pathlib import Path
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel

from qt_bridge import QtBridge


class LabPilotManagerWindow(QMainWindow):
    """Main Qt window embedding the React frontend with Qt bridge"""

    def __init__(self, react_url: str = "http://localhost:3000"):
        super().__init__()
        self.react_url = react_url
        self.setup_bridge()
        self.setup_ui()

    def setup_bridge(self):
        """Setup Qt-React communication bridge"""
        self.bridge = QtBridge(self)
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

    def on_load_progress(self, progress: int):
        """Called when page loading progresses"""
        if progress % 25 == 0:
            print(f"📊 Page loading progress: {progress}%")
        self.setWindowTitle(f"LabPilot Manager - Loading {progress}%")

    def on_load_finished(self, success: bool):
        """Called when page finishes loading"""
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
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="LabPilot Manager with embedded React frontend")
    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="URL of the React frontend (default: http://localhost:3000)"
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="URL of the backend API (default: http://localhost:8000)"
    )

    args = parser.parse_args()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Manager")
    app.setOrganizationName("Laboratory Automation")

    # Create and show manager window
    window = LabPilotManagerWindow(react_url=args.url)
    window.show()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  LabPilot Manager Started                    ║
╠══════════════════════════════════════════════════════════════╣
║  React Frontend: {args.url:44} ║
║  Backend API:    {args.backend_url:44} ║
╠══════════════════════════════════════════════════════════════╣
║  The React frontend is embedded in this Qt window.           ║
║  Instrument UIs will open as separate Qt windows.            ║
╚══════════════════════════════════════════════════════════════╝
    """)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
