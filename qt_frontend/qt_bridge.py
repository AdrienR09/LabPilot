#!/usr/bin/env python3
"""
Qt Bridge for React-Qt Communication
Allows React app to control Qt (launch windows, etc.)
"""

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import QMainWindow
from typing import Dict, Optional
import json


class QtBridge(QObject):
    """Bridge object exposed to JavaScript for React-Qt communication"""

    # Signals that can be emitted to JavaScript
    instrumentUpdated = pyqtSignal(str, dict)  # instrument_id, data
    workflowUpdated = pyqtSignal(str, dict)    # workflow_id, data
    sessionUpdated = pyqtSignal(dict)          # session data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instrument_windows: Dict[str, QMainWindow] = {}
        self.mock_instruments = self._create_mock_instruments()
        self.mock_workflows = self._create_mock_workflows()

    def _create_mock_instruments(self) -> Dict[str, dict]:
        """Create mock instruments for testing - MUST MATCH React catalog IDs"""
        return {
            "thorlabs-pm100-001": {
                "id": "thorlabs-pm100-001",
                "name": "Power Meter 1",
                "type": "Power Meter",
                "category": "Power Meter",
                "kind": "detector",
                "dimensionality": "0D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"power": 12.5, "wavelength": 633, "autorange": True}
            },
            "newport-2835-001": {
                "id": "newport-2835-001",
                "name": "Power Meter 2",
                "type": "Power Meter",
                "category": "Power Meter",
                "kind": "detector",
                "dimensionality": "0D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"power": 8.3, "wavelength": 1550}
            },
            "srs-sr844-001": {
                "id": "srs-sr844-001",
                "name": "Lock-in Amplifier",
                "type": "Lock-in Amplifier",
                "category": "Lock-in Amplifier",
                "kind": "detector",
                "dimensionality": "0D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"frequency": 100000, "sensitivity": "100 nV", "phase": 0, "xOutput": 125.3, "yOutput": 23.1}
            },
            "ocean-opticsusb2000-001": {
                "id": "ocean-opticsusb2000-001",
                "name": "USB Spectrometer",
                "type": "Spectrometer",
                "category": "Spectrometer",
                "kind": "detector",
                "dimensionality": "1D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"wavelength_min": 200, "wavelength_max": 850, "integration_time": 50, "averages": 1}
            },
            "thorlabs-dcc3260c-001": {
                "id": "thorlabs-dcc3260c-001",
                "name": "RGB Camera",
                "type": "Camera",
                "category": "Camera",
                "kind": "detector",
                "dimensionality": "2D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"exposure_time": 10, "gain": 50, "binning": "1x1"}
            },
            "newport-esp301-001": {
                "id": "newport-esp301-001",
                "name": "Motor Controller",
                "type": "Motion Controller",
                "category": "Motor Controller",
                "kind": "motor",
                "dimensionality": "0D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"position_x": 0.0, "position_y": 0.0, "velocity": 5.0}
            },
            "thorlabs-kdc101-001": {
                "id": "thorlabs-kdc101-001",
                "name": "DC Servo Motor",
                "type": "Motor",
                "category": "Motor",
                "kind": "motor",
                "dimensionality": "0D",
                "connected": True,
                "status": "Ready",
                "has_ui": True,
                "parameters": {"position": 0.0, "velocity": 2.0, "acceleration": 1.0}
            },
        }

    def _create_mock_workflows(self) -> Dict[str, dict]:
        """Create mock workflows for testing"""
        return {
            "workflow_001": {
                "id": "workflow_001",
                "name": "Spectroscopy Scan",
                "description": "Full spectrum acquisition from 400-800nm",
                "status": "ready",
                "progress": 0.0,
                "connected_instruments": ["spectrometer_001", "laser_001"],
                "steps": [
                    {"id": "step1", "name": "Initialize Spectrometer", "status": "pending"},
                    {"id": "step2", "name": "Set Laser Wavelength", "status": "pending"},
                    {"id": "step3", "name": "Acquire Spectrum", "status": "pending"},
                    {"id": "step4", "name": "Save Results", "status": "pending"}
                ]
            },
            "workflow_002": {
                "id": "workflow_002",
                "name": "Temperature Sweep",
                "description": "Measure device response across temperature",
                "status": "running",
                "progress": 0.65,
                "connected_instruments": ["camera_001", "motor_001"],
                "steps": [
                    {"id": "step1", "name": "Initialize Camera", "status": "completed"},
                    {"id": "step2", "name": "Set Temperature", "status": "running"},
                    {"id": "step3", "name": "Capture Images", "status": "pending"},
                    {"id": "step4", "name": "Analyze Data", "status": "pending"}
                ]
            },
            "workflow_003": {
                "id": "workflow_003",
                "name": "Lock-in Measurement",
                "description": "Precision phase-sensitive detection",
                "status": "ready",
                "progress": 0.0,
                "connected_instruments": ["lockin_001", "motor_001"],
                "steps": [
                    {"id": "step1", "name": "Configure Lock-in", "status": "pending"},
                    {"id": "step2", "name": "Scan Position", "status": "pending"},
                    {"id": "step3", "name": "Record Signal", "status": "pending"}
                ]
            }
        }

    @pyqtSlot(result=str)
    def getInstruments(self) -> str:
        """Get all mock instruments as JSON"""
        instruments = list(self.mock_instruments.values())
        return json.dumps(instruments)

    @pyqtSlot(result=str)
    def getWorkflows(self) -> str:
        """Get all mock workflows as JSON"""
        workflows = list(self.mock_workflows.values())
        return json.dumps(workflows)

    @pyqtSlot(str, result=str)
    def getInstrument(self, instrument_id: str) -> str:
        """Get single instrument by ID"""
        instrument = self.mock_instruments.get(instrument_id)
        return json.dumps(instrument) if instrument else json.dumps(None)

    @pyqtSlot(str)
    def launchInstrumentUI(self, instrument_id: str):
        """Launch Qt instrument window from React"""
        print(f"[QtBridge] 🚀 Launching UI for instrument: {instrument_id}")

        instrument = self.mock_instruments.get(instrument_id)
        if not instrument:
            print(f"[QtBridge] ❌ Instrument not found: {instrument_id}")
            print(f"[QtBridge] Available instruments: {list(self.mock_instruments.keys())}")
            return

        if not instrument["connected"]:
            print(f"[QtBridge] ⚠️ Instrument not connected: {instrument_id}")
            return

        # Check if window already exists
        if instrument_id in self.instrument_windows:
            window = self.instrument_windows[instrument_id]
            window.show()
            window.raise_()
            window.activateWindow()
            print(f"[QtBridge] ↻ Reusing existing window for: {instrument_id}")
            return

        # Create new instrument window
        try:
            print(f"[QtBridge] 📂 Importing hybrid_instrument_windows...")
            import sys
            from pathlib import Path

            # Add current directory to path for imports
            current_dir = Path(__file__).parent
            if str(current_dir) not in sys.path:
                sys.path.insert(0, str(current_dir))

            from hybrid_instrument_windows import create_hybrid_instrument_window

            print(f"[QtBridge] ✅ Successfully imported hybrid_instrument_windows")
            print(f"[QtBridge] 🔨 Creating window for: {instrument['name']}")

            window = create_hybrid_instrument_window(instrument)

            # Store window reference
            self.instrument_windows[instrument_id] = window

            # Clean up when window closes
            def on_close():
                if instrument_id in self.instrument_windows:
                    del self.instrument_windows[instrument_id]
                    print(f"[QtBridge] 🗑️ Closed window for: {instrument_id}")

            window.destroyed.connect(on_close)
            window.show()

            print(f"[QtBridge] ✨ Successfully created window for: {instrument['name']}")

        except ImportError as ie:
            print(f"[QtBridge] ❌ Import Error launching UI: {ie}")
            print(f"[QtBridge] Module search path: {sys.path}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"[QtBridge] ❌ Error launching UI: {e}")
            print(f"[QtBridge] Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()

    @pyqtSlot(str, str)
    def connectInstrument(self, instrument_id: str, params: str):
        """Connect an instrument"""
        if instrument_id in self.mock_instruments:
            self.mock_instruments[instrument_id]["connected"] = True
            self.mock_instruments[instrument_id]["status"] = "Ready"
            print(f"[QtBridge] Connected instrument: {instrument_id}")
            self.instrumentUpdated.emit(instrument_id, self.mock_instruments[instrument_id])

    @pyqtSlot(str)
    def disconnectInstrument(self, instrument_id: str):
        """Disconnect an instrument"""
        if instrument_id in self.mock_instruments:
            self.mock_instruments[instrument_id]["connected"] = False
            self.mock_instruments[instrument_id]["status"] = "Disconnected"
            print(f"[QtBridge] Disconnected instrument: {instrument_id}")
            self.instrumentUpdated.emit(instrument_id, self.mock_instruments[instrument_id])

    @pyqtSlot(str)
    def startWorkflow(self, workflow_id: str):
        """Start a workflow"""
        if workflow_id in self.mock_workflows:
            self.mock_workflows[workflow_id]["status"] = "running"
            self.mock_workflows[workflow_id]["progress"] = 0.0
            print(f"[QtBridge] Started workflow: {workflow_id}")
            self.workflowUpdated.emit(workflow_id, self.mock_workflows[workflow_id])

    @pyqtSlot(str)
    def stopWorkflow(self, workflow_id: str):
        """Stop a workflow"""
        if workflow_id in self.mock_workflows:
            self.mock_workflows[workflow_id]["status"] = "ready"
            print(f"[QtBridge] Stopped workflow: {workflow_id}")
            self.workflowUpdated.emit(workflow_id, self.mock_workflows[workflow_id])

    @pyqtSlot(result=str)
    def saveSession(self) -> str:
        """Save current session state"""
        session = {
            "instruments": self.mock_instruments,
            "workflows": self.mock_workflows,
            "timestamp": None  # Will be set by frontend
        }
        from pathlib import Path
        import json
        from datetime import datetime

        session["timestamp"] = datetime.now().isoformat()

        # Save to file
        sessions_dir = Path.home() / ".labpilot" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        session_file = sessions_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(session_file, 'w') as f:
            json.dump(session, f, indent=2)

        print(f"[QtBridge] Saved session to: {session_file}")
        return str(session_file)

    @pyqtSlot(str)
    def loadSession(self, session_path: str):
        """Load session from file"""
        from pathlib import Path
        import json

        session_file = Path(session_path)
        if not session_file.exists():
            print(f"[QtBridge] Session file not found: {session_path}")
            return

        with open(session_file, 'r') as f:
            session = json.load(f)

        self.mock_instruments = session.get("instruments", {})
        self.mock_workflows = session.get("workflows", {})

        print(f"[QtBridge] Loaded session from: {session_path}")
        self.sessionUpdated.emit(session)

    @pyqtSlot(result=str)
    def listSessions(self) -> str:
        """List all saved sessions"""
        from pathlib import Path

        sessions_dir = Path.home() / ".labpilot" / "sessions"
        if not sessions_dir.exists():
            return json.dumps([])

        sessions = []
        for session_file in sorted(sessions_dir.glob("session_*.json"), reverse=True):
            sessions.append({
                "path": str(session_file),
                "name": session_file.stem,
                "modified": session_file.stat().st_mtime
            })

        return json.dumps(sessions)

    @pyqtSlot(result=str)
    def getBlockDiagram(self) -> str:
        """Get block diagram data for visualization"""
        # Create nodes for instruments and workflows
        nodes = []
        edges = []

        # Add instrument nodes
        for inst_id, inst in self.mock_instruments.items():
            nodes.append({
                "id": inst_id,
                "type": "instrument",
                "label": inst["name"],
                "kind": inst["kind"],
                "connected": inst["connected"],
                "position": {"x": 0, "y": 0}  # Will be laid out by frontend
            })

        # Add workflow nodes and connections
        for wf_id, wf in self.mock_workflows.items():
            nodes.append({
                "id": wf_id,
                "type": "workflow",
                "label": wf["name"],
                "status": wf["status"],
                "position": {"x": 0, "y": 0}
            })

            # Add edges from instruments to workflow
            for inst_id in wf["connected_instruments"]:
                edges.append({
                    "id": f"{inst_id}_{wf_id}",
                    "source": inst_id,
                    "target": wf_id
                })

        return json.dumps({"nodes": nodes, "edges": edges})
