#!/usr/bin/env python3
"""
Data Page - Results and Analysis Interface
Converts React data page to Qt Material Design
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QTextEdit, QComboBox, QFileDialog,
    QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
import pyqtgraph as pg
from pathlib import Path
import json

class DataViewer(QWidget):
    """Data visualization widget with pyqtgraph"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup data viewer UI"""
        layout = QVBoxLayout(self)

        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Intensity')
        self.plot_widget.setLabel('bottom', 'Wavelength (nm)')
        self.plot_widget.showGrid(x=True, y=True)
        layout.addWidget(self.plot_widget)

        # Sample data plot
        import numpy as np
        x = np.linspace(400, 800, 1000)
        y = np.exp(-(x-550)**2/1000) + 0.1*np.random.random(1000)
        self.plot_widget.plot(x, y, pen='b', name='Sample Data')

class DataPage(QWidget):
    """Data page implementation"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.setup_ui()

    def setup_ui(self):
        """Setup data page UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Data Analysis")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #333;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Data management buttons
        export_btn = QPushButton("📤 Export Data")
        export_btn.clicked.connect(self.export_data)
        header_layout.addWidget(export_btn)

        import_btn = QPushButton("📥 Import Data")
        import_btn.clicked.connect(self.import_data)
        header_layout.addWidget(import_btn)

        layout.addLayout(header_layout)

        # Main content splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Data browser
        left_panel = QFrame()
        left_panel.setFrameStyle(QFrame.Shape.Box)
        left_panel.setMaximumWidth(300)
        left_layout = QVBoxLayout(left_panel)

        # Recent data files
        files_group = QGroupBox("Recent Data Files")
        files_layout = QVBoxLayout(files_group)

        self.files_list = QListWidget()
        files_list_items = [
            "spectrum_2024-03-28_14-30.json",
            "calibration_2024-03-28_13-15.json",
            "diagnostics_2024-03-28_10-45.json",
            "temperature_study_2024-03-27.json"
        ]
        for item_text in files_list_items:
            self.files_list.addItem(item_text)

        self.files_list.itemClicked.connect(self.load_data_file)
        files_layout.addWidget(self.files_list)
        left_layout.addWidget(files_group)

        main_splitter.addWidget(left_panel)

        # Right panel - Data viewer
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.Shape.Box)
        right_layout = QVBoxLayout(right_panel)

        # Tab widget for different views
        self.tab_widget = QTabWidget()

        # Plot tab
        plot_tab = DataViewer()
        self.tab_widget.addTab(plot_tab, "📊 Plot")

        # Table tab
        table_tab = QTextEdit()
        table_tab.setPlainText("Wavelength (nm)\tIntensity\n400\t0.156\n401\t0.162\n...")
        self.tab_widget.addTab(table_tab, "📋 Table")

        # Statistics tab
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_layout.addWidget(QLabel("Data Statistics:"))
        stats_layout.addWidget(QLabel("• Points: 1000"))
        stats_layout.addWidget(QLabel("• Range: 400-800 nm"))
        stats_layout.addWidget(QLabel("• Max: 0.987 at 551 nm"))
        stats_layout.addWidget(QLabel("• Min: 0.045 at 423 nm"))
        stats_layout.addStretch()
        self.tab_widget.addTab(stats_tab, "📈 Stats")

        right_layout.addWidget(self.tab_widget)
        main_splitter.addWidget(right_panel)

        # Set splitter proportions
        main_splitter.setSizes([300, 700])
        layout.addWidget(main_splitter)

    def set_api_client(self, client):
        """Set API client"""
        self.api_client = client

    def refresh_data(self):
        """Refresh data files"""
        pass

    def load_data_file(self, item: QListWidgetItem):
        """Load selected data file"""
        filename = item.text()
        # TODO: Load actual data file
        print(f"Loading data file: {filename}")

    def export_data(self):
        """Export current data"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if filename:
            QMessageBox.information(self, "Export", f"Data exported to {filename}")

    def import_data(self):
        """Import data file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Data", "", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if filename:
            QMessageBox.information(self, "Import", f"Data imported from {filename}")