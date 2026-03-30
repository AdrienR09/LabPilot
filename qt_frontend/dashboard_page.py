#!/usr/bin/env python3
"""
Dashboard Page - System Status Overview
Converts React dashboard to Qt Material Design
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QScrollArea, QProgressBar, QListWidget, QListWidgetItem,
    QGroupBox, QPushButton, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor
import pyqtgraph as pg
from datetime import datetime
from typing import Dict, List, Any

class StatusCard(QFrame):
    """Material Design status card widget"""

    def __init__(self, title: str, value: str, icon: str = "", color: str = "#2196F3"):
        super().__init__()
        self.setup_ui(title, value, icon, color)

    def setup_ui(self, title: str, value: str, icon: str, color: str):
        """Setup card UI"""
        self.setObjectName("status_card")
        self.setFrameStyle(QFrame.Shape.Box)
        self.setMinimumHeight(120)
        self.setStyleSheet(f"""
            #status_card {{
                border: 1px solid #E5E7EB;  /* gray-200 */
                border-radius: 8px;  /* rounded-lg */
                background-color: #FFFFFF;  /* white */
                padding: 16px;  /* p-4 */
            }}
            #status_card:hover {{
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);  /* hover:shadow-lg */
            }}
        """)

        layout = QVBoxLayout(self)

        # Header with icon and title
        header_layout = QHBoxLayout()

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 24px; color: {color};")
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; color: #6B7280; font-weight: bold;")  # gray-500
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color};")
        layout.addWidget(self.value_label)

        layout.addStretch()

    def update_value(self, value: str):
        """Update card value"""
        self.value_label.setText(value)

class SystemMetricsWidget(QFrame):
    """Real-time system metrics display"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_plots()

    def setup_ui(self):
        """Setup metrics UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
        """)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("System Performance")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 12px;")
        layout.addWidget(title)

        # Metrics grid
        metrics_layout = QGridLayout()

        # CPU Usage
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setMaximum(100)
        self.cpu_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                background-color: #f5f5f5;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 3px;
            }
        """)
        metrics_layout.addWidget(QLabel("CPU Usage:"), 0, 0)
        metrics_layout.addWidget(self.cpu_progress, 0, 1)

        # Memory Usage
        self.memory_progress = QProgressBar()
        self.memory_progress.setMaximum(100)
        self.memory_progress.setStyleSheet(self.cpu_progress.styleSheet().replace("#2196F3", "#4CAF50"))
        metrics_layout.addWidget(QLabel("Memory:"), 1, 0)
        metrics_layout.addWidget(self.memory_progress, 1, 1)

        # Network Status
        self.network_label = QLabel("Disconnected")
        self.network_label.setStyleSheet("color: #f44336; font-weight: bold;")
        metrics_layout.addWidget(QLabel("Network:"), 2, 0)
        metrics_layout.addWidget(self.network_label, 2, 1)

        layout.addLayout(metrics_layout)

    def setup_plots(self):
        """Setup real-time plots"""
        # This would include pyqtgraph plots for real-time data
        # Implementation depends on what metrics you want to show
        pass

    def update_metrics(self, cpu: float, memory: float, network: bool):
        """Update system metrics"""
        self.cpu_progress.setValue(int(cpu))
        self.memory_progress.setValue(int(memory))
        self.network_label.setText("Connected" if network else "Disconnected")
        self.network_label.setStyleSheet(f"color: {'#4CAF50' if network else '#f44336'}; font-weight: bold;")

class RecentEventsWidget(QFrame):
    """Recent system events display"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup events UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
        """)

        layout = QVBoxLayout(self)

        # Title
        header_layout = QHBoxLayout()
        title = QLabel("Recent Events")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("clear_button")
        clear_btn.clicked.connect(self.clear_events)
        header_layout.addWidget(clear_btn)

        layout.addLayout(header_layout)

        # Events list
        self.events_list = QListWidget()
        self.events_list.setStyleSheet("""
            QListWidget {
                border: none;
                background: transparent;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.events_list)

        # Add some sample events
        self.add_event("System started", "info")
        self.add_event("Backend connected", "success")

    def add_event(self, message: str, event_type: str = "info"):
        """Add an event to the list"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Color coding based on event type
        colors = {
            "info": "#2196F3",
            "success": "#4CAF50",
            "warning": "#FF9800",
            "error": "#f44336"
        }
        color = colors.get(event_type, "#2196F3")

        item = QListWidgetItem(f"[{timestamp}] {message}")
        item.setData(Qt.ItemDataRole.UserRole, event_type)

        # Style the item
        font = QFont()
        font.setPointSize(11)
        item.setFont(font)

        self.events_list.insertItem(0, item)  # Insert at top

        # Limit to 50 events
        if self.events_list.count() > 50:
            self.events_list.takeItem(50)

    def clear_events(self):
        """Clear all events"""
        self.events_list.clear()

class DashboardPage(QWidget):
    """Dashboard page implementation"""

    # Signals for communication with main window
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.setup_ui()
        self.setup_auto_refresh()

    def setup_ui(self):
        """Setup dashboard UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)  # Match React page padding
        layout.setSpacing(24)  # Match React space-y-6

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #111827;")  # Match React text-2xl + gray-900
        header_layout.addWidget(title)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setObjectName("refresh_button")
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Status cards row with React-matching spacing
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)  # Match React gap-4

        self.device_card = StatusCard("Connected Devices", "0", "▣", "#4CAF50")
        self.workflow_card = StatusCard("Active Workflows", "0", "▷", "#FF9800")
        self.ai_card = StatusCard("AI Status", "Online", "◉", "#9C27B0")
        self.data_card = StatusCard("Data Points", "0", "▤", "#2196F3")

        cards_layout.addWidget(self.device_card)
        cards_layout.addWidget(self.workflow_card)
        cards_layout.addWidget(self.ai_card)
        cards_layout.addWidget(self.data_card)

        layout.addLayout(cards_layout)

        # Content row with metrics and events (React-matching spacing)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)  # Match React gap-4

        # System metrics (left side)
        self.metrics_widget = SystemMetricsWidget()
        content_layout.addWidget(self.metrics_widget, 1)

        # Recent events (right side)
        self.events_widget = RecentEventsWidget()
        content_layout.addWidget(self.events_widget, 1)

        layout.addLayout(content_layout)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin: 10px 0;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        actions_layout = QHBoxLayout(actions_group)

        quick_actions = [
            ("▣ Connect All Devices", self.connect_all_devices),
            ("▷ Run Diagnostics", self.run_diagnostics),
            ("▤ Export Data", self.export_data),
            ("◉ Test AI Connection", self.test_ai_connection)
        ]

        for text, callback in quick_actions:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            actions_layout.addWidget(btn)

        layout.addWidget(actions_group)

        layout.addStretch()

    def setup_auto_refresh(self):
        """Setup auto-refresh timer"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(10000)  # 10 second refresh

    def set_api_client(self, client):
        """Set API client for backend communication"""
        self.api_client = client

    def refresh_data(self):
        """Refresh dashboard data"""
        if not self.api_client:
            # Mock data for development
            self.update_mock_data()
            return

        # TODO: Implement real API calls
        # self.fetch_device_count()
        # self.fetch_workflow_status()
        # self.fetch_ai_status()
        # self.fetch_system_metrics()

    def update_mock_data(self):
        """Update with mock data for development"""
        import random

        # Update status cards with mock data
        self.device_card.update_value(str(random.randint(0, 5)))
        self.workflow_card.update_value(str(random.randint(0, 3)))
        self.ai_card.update_value("Online" if random.choice([True, False]) else "Offline")
        self.data_card.update_value(f"{random.randint(100, 9999)}")

        # Update system metrics
        cpu = random.uniform(10, 80)
        memory = random.uniform(30, 70)
        network = random.choice([True, False])
        self.metrics_widget.update_metrics(cpu, memory, network)

        # Add random event
        events = [
            ("Device connected", "success"),
            ("Workflow completed", "info"),
            ("Warning: High CPU usage", "warning"),
            ("Data export finished", "success")
        ]
        event_msg, event_type = random.choice(events)
        if random.random() < 0.3:  # 30% chance to add event
            self.events_widget.add_event(event_msg, event_type)

    # Quick action callbacks
    def connect_all_devices(self):
        """Connect all available devices"""
        self.events_widget.add_event("Connecting all devices...", "info")
        # TODO: Implement device connection logic

    def run_diagnostics(self):
        """Run system diagnostics"""
        self.events_widget.add_event("Running system diagnostics...", "info")
        # TODO: Implement diagnostics

    def export_data(self):
        """Export current data"""
        self.events_widget.add_event("Exporting data...", "info")
        # TODO: Implement data export

    def test_ai_connection(self):
        """Test AI assistant connection"""
        self.events_widget.add_event("Testing AI connection...", "info")
        # TODO: Implement AI connection test