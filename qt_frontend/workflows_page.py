#!/usr/bin/env python3
"""
Workflows Page - Experiment Management Interface
Minimalistic React-style workflows display with proper theming
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QPushButton, QProgressBar, QScrollArea,
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QTextEdit,
    QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Workflow:
    """Workflow data structure"""
    id: str
    name: str
    description: str
    status: str  # "ready", "running", "completed", "error"
    progress: float  # 0.0 to 1.0
    connected_devices: List[str]
    estimated_duration: str
    results_path: Optional[str] = None
    created_at: Optional[datetime] = None


class WorkflowCard(QFrame):
    """Minimalistic workflow card with theme support"""

    start_requested = pyqtSignal(str)
    stop_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    view_results_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, workflow: Workflow, dark_mode: bool = False):
        super().__init__()
        self.workflow = workflow
        self.dark_mode = dark_mode
        self.setup_ui()

    def setup_ui(self):
        """Setup minimalistic workflow card UI"""
        self.setObjectName("workflow_card")
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setMinimumHeight(160)
        self.setMaximumHeight(200)
        self.update_card_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        self.name_label = QLabel(self.workflow.name)
        self.update_name_style()
        header_layout.addWidget(self.name_label)
        header_layout.addStretch()

        # Status badge
        self.status_label = QLabel(self.workflow.status.upper())
        self.status_label.setStyleSheet(self.get_status_style())
        header_layout.addWidget(self.status_label)
        layout.addLayout(header_layout)

        # Description
        if self.workflow.description:
            self.desc_label = QLabel(self.workflow.description)
            self.desc_label.setWordWrap(True)
            self.desc_label.setMaximumHeight(40)
            self.update_description_style()
            layout.addWidget(self.desc_label)

        # Progress bar
        if self.workflow.status == "running":
            self.progress_bar = QProgressBar()
            self.progress_bar.setValue(int(self.workflow.progress * 100))
            self.progress_bar.setMaximumHeight(6)
            self.update_progress_style()
            layout.addWidget(self.progress_bar)

        # Devices info
        devices_text = f"Devices: {', '.join(self.workflow.connected_devices)}"
        self.devices_label = QLabel(devices_text)
        self.devices_label.setMaximumHeight(20)
        self.update_devices_style()
        layout.addWidget(self.devices_label)

        layout.addStretch()

        # Buttons
        buttons_layout = QHBoxLayout()

        if self.workflow.status == "ready":
            start_btn = QPushButton("Start")
            start_btn.setFixedHeight(32)
            start_btn.clicked.connect(lambda: self.start_requested.emit(self.workflow.id))
            start_btn.setStyleSheet("""
                background-color: #10B981;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            """)
            buttons_layout.addWidget(start_btn)

        if self.workflow.status == "running":
            stop_btn = QPushButton("Stop")
            stop_btn.setFixedHeight(32)
            stop_btn.clicked.connect(lambda: self.stop_requested.emit(self.workflow.id))
            stop_btn.setStyleSheet("""
                background-color: #EF4444;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            """)
            buttons_layout.addWidget(stop_btn)

        if self.workflow.status == "completed":
            results_btn = QPushButton("Results")
            results_btn.setFixedHeight(32)
            results_btn.clicked.connect(lambda: self.view_results_requested.emit(self.workflow.id))
            results_btn.setStyleSheet("""
                background-color: #8B5CF6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            """)
            buttons_layout.addWidget(results_btn)

        buttons_layout.addStretch()

        # Edit and remove
        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(32, 32)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.workflow.id))
        edit_btn.setStyleSheet("background-color: transparent; color: #6B7280; border: none; font-size: 14px;")
        buttons_layout.addWidget(edit_btn)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(32, 32)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.workflow.id))
        remove_btn.setStyleSheet("background-color: transparent; color: #6B7280; border: none; font-size: 16px;")
        buttons_layout.addWidget(remove_btn)

        layout.addLayout(buttons_layout)

    def update_card_style(self):
        """Update card background based on theme"""
        if self.dark_mode:
            bg = "#1F2937"
            border = "#374151"
        else:
            bg = "#FFFFFF"
            border = "#E5E7EB"

        self.setStyleSheet(f"""
            #workflow_card {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

    def update_name_style(self):
        """Update name label style"""
        color = "#F9FAFB" if self.dark_mode else "#111827"
        self.name_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {color};
            background: transparent;
            border: none;
        """)

    def update_description_style(self):
        """Update description style"""
        color = "#D1D5DB" if self.dark_mode else "#6B7280"
        self.desc_label.setStyleSheet(f"""
            font-size: 13px;
            color: {color};
            background: transparent;
            border: none;
        """)

    def update_devices_style(self):
        """Update devices label style"""
        color = "#D1D5DB" if self.dark_mode else "#9CA3AF"
        self.devices_label.setStyleSheet(f"""
            font-size: 11px;
            color: {color};
            background: transparent;
            border: none;
        """)

    def update_progress_style(self):
        """Update progress bar style"""
        if self.dark_mode:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #374151;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #3B82F6;
                    border-radius: 3px;
                }
            """)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E5E7EB;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #3B82F6;
                    border-radius: 3px;
                }
            """)

    def get_status_style(self) -> str:
        """Get status badge styling"""
        status_colors = {
            "ready": ("#DBEAFE", "#1D4ED8"),
            "running": ("#FEF3C7", "#D97706"),
            "completed": ("#D1FAE5", "#059669"),
            "error": ("#FEE2E2", "#DC2626"),
        }
        bg, text = status_colors.get(self.workflow.status, ("#F3F4F6", "#6B7280"))
        return f"""
            background-color: {bg};
            color: {text};
            border-radius: 12px;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: bold;
            border: none;
        """

    def set_theme(self, dark_mode: bool):
        """Update theme"""
        self.dark_mode = dark_mode
        self.update_card_style()
        self.update_name_style()
        if hasattr(self, 'desc_label'):
            self.update_description_style()
        if hasattr(self, 'progress_bar'):
            self.update_progress_style()
        if hasattr(self, 'devices_label'):
            self.update_devices_style()


class WorkflowsPage(QWidget):
    """Workflows page with minimalistic design"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.workflows: List[Workflow] = []
        self.workflow_cards: Dict[str, WorkflowCard] = {}
        self.dark_mode = False
        self.setup_ui()
        self.load_mock_workflows()

    def setup_ui(self):
        """Setup workflows page"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Workflows")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827; background: transparent; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Filter
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Workflows", "Ready", "Running", "Completed", "Error"])
        self.status_filter.currentTextChanged.connect(self.filter_workflows)
        self.status_filter.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                background-color: #FFFFFF;
                color: #374151;
            }
        """)
        header_layout.addWidget(self.status_filter)

        # Create button
        create_btn = QPushButton("+ Create Workflow")
        create_btn.clicked.connect(self.show_create_workflow_dialog)
        create_btn.setStyleSheet("""
            background-color: #3B82F6;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
        """)
        header_layout.addWidget(create_btn)

        layout.addLayout(header_layout)

        # Workflows grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameStyle(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        self.workflows_widget = QWidget()
        self.workflows_layout = QGridLayout(self.workflows_widget)
        self.workflows_layout.setSpacing(16)
        self.workflows_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area.setWidget(self.workflows_widget)
        layout.addWidget(scroll_area)

    def load_mock_workflows(self):
        """Load mock workflows"""
        mock_workflows = [
            Workflow(
                id="wf1",
                name="Spectroscopy Scan",
                description="Full spectrum acquisition from 400-800nm",
                status="ready",
                progress=0.0,
                connected_devices=["Spectrometer", "Laser"],
                estimated_duration="15 min"
            ),
            Workflow(
                id="wf2",
                name="Temperature Sweep",
                description="Measure device response across temperature",
                status="running",
                progress=0.65,
                connected_devices=["Thermocouple", "Multimeter"],
                estimated_duration="45 min"
            ),
            Workflow(
                id="wf3",
                name="Previous Experiment",
                description="Results from yesterday's measurement",
                status="completed",
                progress=1.0,
                connected_devices=["Camera"],
                estimated_duration="20 min",
                results_path="/data/experiment_20250328.csv"
            ),
        ]
        self.workflows = mock_workflows
        self.update_workflow_cards()

    def update_workflow_cards(self):
        """Update workflow display"""
        for card in self.workflow_cards.values():
            card.deleteLater()
        self.workflow_cards.clear()

        visible_workflows = self.get_filtered_workflows()
        for i, workflow in enumerate(visible_workflows):
            card = WorkflowCard(workflow, self.dark_mode)
            card.start_requested.connect(self.start_workflow)
            card.stop_requested.connect(self.stop_workflow)
            card.edit_requested.connect(self.edit_workflow)
            card.view_results_requested.connect(self.view_results)
            card.remove_requested.connect(self.remove_workflow)

            row = i // 3
            col = i % 3
            self.workflows_layout.addWidget(card, row, col)
            self.workflow_cards[workflow.id] = card

    def get_filtered_workflows(self) -> List[Workflow]:
        """Get filtered workflows based on status filter"""
        filter_text = self.status_filter.currentText()
        if filter_text == "All Workflows":
            return self.workflows
        status = filter_text.lower()
        return [w for w in self.workflows if w.status == status]

    def filter_workflows(self):
        """Filter workflows"""
        self.update_workflow_cards()

    def refresh_data(self):
        """Refresh workflows"""
        if self.api_client:
            # TODO: Fetch from API
            pass
        else:
            self.load_mock_workflows()

    def set_theme(self, dark_mode: bool):
        """Update theme for all cards"""
        self.dark_mode = dark_mode
        for card in self.workflow_cards.values():
            card.set_theme(dark_mode)

    def show_create_workflow_dialog(self):
        """Show create workflow dialog"""
        dialog = CreateWorkflowDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            workflow_data = dialog.get_workflow_data()
            new_workflow = Workflow(
                id=f"wf_{len(self.workflows) + 1}",
                name=workflow_data["name"],
                description=workflow_data["description"],
                status="ready",
                progress=0.0,
                connected_devices=workflow_data.get("devices", []),
                estimated_duration=workflow_data.get("duration", "Unknown")
            )
            self.workflows.append(new_workflow)
            self.update_workflow_cards()

    def start_workflow(self, workflow_id: str):
        """Start workflow"""
        workflow = next((w for w in self.workflows if w.id == workflow_id), None)
        if workflow:
            workflow.status = "running"
            workflow.progress = 0.0
            self.update_workflow_cards()
            print(f"Started workflow: {workflow.name}")

    def stop_workflow(self, workflow_id: str):
        """Stop workflow"""
        workflow = next((w for w in self.workflows if w.id == workflow_id), None)
        if workflow:
            workflow.status = "ready"
            self.update_workflow_cards()
            print(f"Stopped workflow: {workflow.name}")

    def edit_workflow(self, workflow_id: str):
        """Edit workflow"""
        print(f"Edit workflow: {workflow_id}")

    def view_results(self, workflow_id: str):
        """View workflow results"""
        workflow = next((w for w in self.workflows if w.id == workflow_id), None)
        if workflow and workflow.results_path:
            print(f"Viewing results: {workflow.results_path}")

    def remove_workflow(self, workflow_id: str):
        """Remove workflow"""
        reply = QMessageBox.question(
            self, "Remove Workflow",
            f"Are you sure you want to remove this workflow?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.workflows = [w for w in self.workflows if w.id != workflow_id]
            self.update_workflow_cards()
            print(f"Removed workflow: {workflow_id}")


class CreateWorkflowDialog(QDialog):
    """Dialog for creating workflows"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Workflow")
        self.setModal(True)
        self.resize(400, 250)
        self.setup_ui()

    def setup_ui(self):
        """Setup dialog"""
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Workflow name...")
        form_layout.addRow("Name:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Description...")
        form_layout.addRow("Description:", self.description_edit)

        self.duration_edit = QLineEdit()
        self.duration_edit.setPlaceholderText("e.g., 15 min")
        form_layout.addRow("Est. Duration:", self.duration_edit)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_workflow_data(self) -> dict:
        """Get workflow data"""
        return {
            "name": self.name_edit.text(),
            "description": self.description_edit.toPlainText(),
            "duration": self.duration_edit.text(),
            "devices": []
        }
