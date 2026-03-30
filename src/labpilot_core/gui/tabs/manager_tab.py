"""
Manager Tab - Enhanced Block Diagram View

Visual manager with two zones (instruments and interfaces), interactive blocks,
and comprehensive functionality.
"""
import importlib
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Import working dialogs
from labpilot_core.gui.dialogs import SimpleAddInstrumentDialog, SimpleAddInterfaceDialog


class InstrumentBlock(QGraphicsRectItem):
    """Interactive graphical block representing an instrument."""

    def __init__(self, name: str, device_info: dict[str, Any], x: float, y: float, manager_tab):
        super().__init__(0, 0, 250, 100)
        self.name = name
        self.device_info = device_info
        self.manager_tab = manager_tab
        self.setPos(x, y)

        # Styling
        self._update_style()

        # Set flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Create labels
        self._create_labels()

    def _update_style(self):
        """Update block styling based on connection status."""
        connected = self.device_info.get('connected', False)
        if connected:
            self.setBrush(QBrush(QColor("#3c7eff")))  # Blue for connected
            self.setPen(QPen(QColor("#1a5ed9"), 3))
        else:
            self.setBrush(QBrush(QColor("#6c6c6c")))  # Gray for disconnected
            self.setPen(QPen(QColor("#4c4c4c"), 2))

    def _create_labels(self):
        """Create text labels for the block."""
        # Title
        self.label = QGraphicsTextItem(self)
        self.label.setPlainText(f"🔌 {self.name}")
        self.label.setDefaultTextColor(QColor("#ffffff"))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        self.label.setFont(font)
        self.label.setPos(10, 10)

        # Type
        device_type = self.device_info.get('type', 'Unknown')
        self.type_label = QGraphicsTextItem(self)
        self.type_label.setPlainText(f"Type: {device_type}")
        self.type_label.setDefaultTextColor(QColor("#dddddd"))
        self.type_label.setFont(QFont("Arial", 8))
        self.type_label.setPos(10, 40)

        # Status
        self.status_label = QGraphicsTextItem(self)
        self.update_status()
        self.status_label.setDefaultTextColor(QColor("#dddddd"))
        self.status_label.setFont(QFont("Arial", 8))
        self.status_label.setPos(10, 60)

        # Connection info
        self.conn_label = QGraphicsTextItem(self)
        conn_str = self.device_info.get('settings', {}).get('connection', 'No connection')
        self.conn_label.setPlainText(f"Conn: {conn_str[:20]}")
        self.conn_label.setDefaultTextColor(QColor("#aaaaaa"))
        self.conn_label.setFont(QFont("Arial", 7))
        self.conn_label.setPos(10, 80)

    def update_status(self):
        """Update status label."""
        connected = self.device_info.get('connected', False)
        status = "✓ Connected" if connected else "○ Disconnected"
        self.status_label.setPlainText(f"Status: {status}")
        self._update_style()

    def contextMenuEvent(self, event):
        """Show context menu on right-click."""
        menu = QMenu()

        # Connect/Disconnect
        if self.device_info.get('connected', False):
            disconnect_action = QAction("🔌 Disconnect", None)
            disconnect_action.triggered.connect(self._disconnect)
            menu.addAction(disconnect_action)
        else:
            connect_action = QAction("🔌 Connect", None)
            connect_action.triggered.connect(self._connect)
            menu.addAction(connect_action)

        menu.addSeparator()

        # Settings
        settings_action = QAction("⚙️ Settings", None)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        # Reload
        reload_action = QAction("🔄 Reload", None)
        reload_action.triggered.connect(self._reload)
        menu.addAction(reload_action)

        menu.addSeparator()

        # Remove
        remove_action = QAction("🗑️ Remove", None)
        remove_action.triggered.connect(self._remove)
        menu.addAction(remove_action)

        # Show menu at cursor position
        menu.exec(event.screenPos())

    def _connect(self):
        """Connect to instrument."""
        instance = self.device_info.get('instance')
        connection_str = self.device_info.get('settings', {}).get('connection', '')

        try:
            if connection_str:
                success = instance.connect(connection_str)
            else:
                success = instance.connect()

            if success:
                self.device_info['connected'] = True
                self.update_status()
                self.manager_tab.status_label.setText(f"✓ Connected: {self.name}")
            else:
                QMessageBox.warning(None, "Connection Failed", f"Failed to connect to {self.name}")
        except Exception as e:
            QMessageBox.critical(None, "Connection Error", f"Error connecting to {self.name}:\n{e}")

    def _disconnect(self):
        """Disconnect from instrument."""
        instance = self.device_info.get('instance')

        try:
            success = instance.disconnect()
            if success:
                self.device_info['connected'] = False
                self.update_status()
                self.manager_tab.status_label.setText(f"✓ Disconnected: {self.name}")
        except Exception as e:
            QMessageBox.critical(None, "Disconnection Error", f"Error disconnecting from {self.name}:\n{e}")

    def _show_settings(self):
        """Show settings dialog."""
        dialog = QDialog()
        dialog.setWindowTitle(f"Settings - {self.name}")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # Settings form
        form = QFormLayout()

        # Connection
        conn_edit = QLineEdit(self.device_info.get('settings', {}).get('connection', ''))
        form.addRow("Connection:", conn_edit)

        # Other settings
        for key, value in self.device_info.get('settings', {}).items():
            if key != 'connection':
                edit = QLineEdit(str(value))
                form.addRow(f"{key}:", edit)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update settings
            self.device_info.setdefault('settings', {})['connection'] = conn_edit.text()
            self.conn_label.setPlainText(f"Conn: {conn_edit.text()[:20]}")
            self.manager_tab.status_label.setText(f"✓ Settings updated: {self.name}")

    def _reload(self):
        """Reload instrument."""
        # Disconnect if connected
        if self.device_info.get('connected', False):
            self._disconnect()

        # Reload device class
        try:
            device_data = self.device_info.get('data')
            mod = importlib.import_module(device_data['module_path'])
            importlib.reload(mod)

            device_class = getattr(mod, device_data['wrapper_name'])
            new_instance = device_class()

            self.device_info['instance'] = new_instance
            self.manager_tab.status_label.setText(f"✓ Reloaded: {self.name}")

        except Exception as e:
            QMessageBox.critical(None, "Reload Error", f"Error reloading {self.name}:\n{e}")

    def _remove(self):
        """Remove instrument from manager."""
        reply = QMessageBox.question(None, "Remove Instrument",
                                     f"Remove instrument '{self.name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Disconnect first
            if self.device_info.get('connected', False):
                self._disconnect()

            # Remove from manager
            self.manager_tab.instruments.pop(self.name, None)
            self.scene().removeItem(self)
            self.manager_tab.status_label.setText(f"✓ Removed: {self.name}")
            self.manager_tab.update_connections()

    def itemChange(self, change, value):
        """Handle item changes (e.g., position)."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.manager_tab.update_connections()
        return super().itemChange(change, value)


class InterfaceBlock(QGraphicsRectItem):
    """Interactive graphical block representing a measurement interface."""

    def __init__(self, name: str, interface_info: dict[str, Any], x: float, y: float, manager_tab):
        super().__init__(0, 0, 250, 100)
        self.name = name
        self.interface_info = interface_info
        self.manager_tab = manager_tab
        self.setPos(x, y)

        # Styling
        self.setBrush(QBrush(QColor("#ff7f3c")))
        self.setPen(QPen(QColor("#d95f1a"), 3))

        # Set flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Create labels
        self._create_labels()

    def _create_labels(self):
        """Create text labels for the block."""
        # Title
        self.label = QGraphicsTextItem(self)
        icon = self.interface_info.get('icon', '📊')
        self.label.setPlainText(f"{icon} {self.name}")
        self.label.setDefaultTextColor(QColor("#ffffff"))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        self.label.setFont(font)
        self.label.setPos(10, 10)

        # Type
        interface_type = self.interface_info.get('display_name', 'Interface')
        self.type_label = QGraphicsTextItem(self)
        self.type_label.setPlainText(interface_type)
        self.type_label.setDefaultTextColor(QColor("#dddddd"))
        self.type_label.setFont(QFont("Arial", 8))
        self.type_label.setPos(10, 40)

        # Status
        self.status_label = QGraphicsTextItem(self)
        self.status_label.setPlainText("Status: Ready")
        self.status_label.setDefaultTextColor(QColor("#dddddd"))
        self.status_label.setFont(QFont("Arial", 8))
        self.status_label.setPos(10, 60)

        # Instrument count
        inst_count = len(self.interface_info.get('instrument_mapping', {}))
        self.inst_label = QGraphicsTextItem(self)
        self.inst_label.setPlainText(f"Instruments: {inst_count}")
        self.inst_label.setDefaultTextColor(QColor("#aaaaaa"))
        self.inst_label.setFont(QFont("Arial", 7))
        self.inst_label.setPos(10, 80)

    def mouseDoubleClickEvent(self, event):
        """Open interface GUI on double-click."""
        self._open_interface()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu on right-click."""
        menu = QMenu()

        # Open
        open_action = QAction("📂 Open Interface", None)
        open_action.triggered.connect(self._open_interface)
        menu.addAction(open_action)

        menu.addSeparator()

        # Settings
        settings_action = QAction("⚙️ Settings", None)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Remove
        remove_action = QAction("🗑️ Remove", None)
        remove_action.triggered.connect(self._remove)
        menu.addAction(remove_action)

        menu.exec(event.screenPos())

    def _open_interface(self):
        """Open the interface GUI window."""
        # Create interface widget if needed
        metadata = self.interface_info.get('metadata')
        if metadata:
            interface_class_name = metadata.name

            try:
                # Try to get the interface class and create widget
                from labpilot_interfaces.base import InterfaceRegistry

                interface_class = InterfaceRegistry.get_interface(interface_class_name)
                if interface_class:
                    # Get mapped instruments
                    instruments = {}
                    for role, inst_name in self.interface_info.get('instrument_mapping', {}).items():
                        if inst_name in self.manager_tab.instruments:
                            instruments[role] = self.manager_tab.instruments[inst_name]['instance']

                    # Create interface instance
                    interface = interface_class(
                        name=self.name,
                        instruments=instruments,
                        parameters=self.interface_info.get('parameters', {})
                    )

                    # Create and show widget
                    widget = interface.create_widget()
                    widget.setWindowTitle(f"{metadata.display_name} - {self.name}")
                    widget.resize(1000, 700)
                    widget.show()

                    # Store widget reference
                    self.interface_info['widget'] = widget

                    self.manager_tab.status_label.setText(f"✓ Opened: {self.name}")

            except Exception as e:
                QMessageBox.critical(None, "Error", f"Failed to open interface:\n{e}")

    def _show_settings(self):
        """Show settings dialog."""
        dialog = QDialog()
        dialog.setWindowTitle(f"Settings - {self.name}")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # Settings form
        form = QFormLayout()

        # Show parameters
        for param_name, param_value in self.interface_info.get('parameters', {}).items():
            edit = QLineEdit(str(param_value))
            form.addRow(f"{param_name}:", edit)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.manager_tab.status_label.setText(f"✓ Settings updated: {self.name}")

    def _remove(self):
        """Remove interface from manager."""
        reply = QMessageBox.question(None, "Remove Interface",
                                     f"Remove interface '{self.name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Remove from manager
            self.manager_tab.interfaces.pop(self.name, None)
            self.scene().removeItem(self)
            self.manager_tab.status_label.setText(f"✓ Removed: {self.name}")
            self.manager_tab.update_connections()

    def itemChange(self, change, value):
        """Handle item changes (e.g., position)."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.manager_tab.update_connections()
        return super().itemChange(change, value)


class ConnectionLine(QGraphicsLineItem):
    """Line connecting interface to instrument."""

    def __init__(self, interface_block: InterfaceBlock, instrument_block: InstrumentBlock):
        super().__init__()
        self.interface_block = interface_block
        self.instrument_block = instrument_block
        self.setPen(QPen(QColor("#888888"), 2, Qt.PenStyle.DashLine))
        self.setZValue(-1)  # Draw behind blocks
        self.update_position()

    def update_position(self):
        """Update line position based on block positions."""
        interface_center = self.interface_block.sceneBoundingRect().center()
        instrument_center = self.instrument_block.sceneBoundingRect().center()
        self.setLine(interface_center.x(), interface_center.y(),
                     instrument_center.x(), instrument_center.y())


class ManagerTab(QWidget):
    """
    Enhanced Manager Tab with two zones, interactive blocks, and full functionality.
    """

    instrument_added = pyqtSignal(str, object)
    interface_added = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.instruments: dict[str, Any] = {}
        self.interfaces: dict[str, Any] = {}
        self.connections: list[ConnectionLine] = []

        self._setup_ui()

        # Auto-layout timer
        self._layout_timer = QTimer()
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._auto_layout)

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = self._create_header()
        layout.addWidget(header)

        # Graphics view for block diagram
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, 3000, 2000)
        self.scene.setBackgroundBrush(QBrush(QColor("#1e1e1e")))

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.view)

        # Add zone labels
        self._add_zone_labels()

        # Status bar
        self.status_label = QLabel("Ready - Add instruments and interfaces to begin")
        self.status_label.setStyleSheet("padding: 8px; color: #ccc; background: #2b2b2b;")
        layout.addWidget(self.status_label)

    def _create_header(self) -> QWidget:
        """Create header with buttons."""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("🎛️ System Manager")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        layout.addStretch()

        # Buttons
        self.btn_add_instrument = QPushButton("➕ Add Instrument")
        self.btn_add_instrument.clicked.connect(self._on_add_instrument_clicked)
        self.btn_add_instrument.setMinimumHeight(40)
        layout.addWidget(self.btn_add_instrument)

        self.btn_add_interface = QPushButton("➕ Add Interface")
        self.btn_add_interface.clicked.connect(self._on_add_interface_clicked)
        self.btn_add_interface.setMinimumHeight(40)
        layout.addWidget(self.btn_add_interface)

        # Styling
        for btn in [self.btn_add_instrument, self.btn_add_interface]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: #ffffff;
                    border: none;
                    padding: 10px 25px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #3a8eef;
                }
            """)

        header.setStyleSheet("background-color: #2b2b2b;")
        return header

    def _add_zone_labels(self):
        """Add zone labels to scene."""
        # Instruments zone label
        inst_label = QGraphicsTextItem("INSTRUMENTS ZONE")
        inst_label.setDefaultTextColor(QColor("#666666"))
        inst_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        inst_label.setPos(50, 20)
        self.scene.addItem(inst_label)

        # Interfaces zone label
        int_label = QGraphicsTextItem("INTERFACES ZONE")
        int_label.setDefaultTextColor(QColor("#666666"))
        int_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        int_label.setPos(50, 670)
        self.scene.addItem(int_label)

    def _on_add_instrument_clicked(self):
        """Handle add instrument button."""
        dialog = SimpleAddInstrumentDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_instrument_config()
            if config:
                self._add_instrument(config)

    def _on_add_interface_clicked(self):
        """Handle add interface button."""
        dialog = SimpleAddInterfaceDialog(self.instruments, self)
        dialog.exec()  # Just show the "not implemented" message

    def _add_test_instrument(self, config: dict[str, Any]):
        """Add a test instrument to manager (temporary method)."""
        instance_name = config['instance_name']
        device_data = config['device_data']
        settings = config['settings']

        # Create a mock device info for testing
        device_info = {
            'instance': None,  # No real device instance
            'data': device_data,
            'settings': settings,
            'connected': False,
            'type': f"{device_data['category']}.{device_data['manufacturer']}.{device_data['name']}"
        }

        # Position in instruments zone
        num = len(self.instruments)
        col = num % 4
        row = num // 4
        x = 80 + col * 270
        y = 80 + row * 120

        # Create block
        block = InstrumentBlock(instance_name, device_info, x, y, self)
        self.scene.addItem(block)

        device_info['block'] = block
        self.instruments[instance_name] = device_info

        self.view.ensureVisible(block)
        self.status_label.setText(f"✓ Added test instrument: {instance_name}")
        self.instrument_added.emit(instance_name, None)

    def _add_instrument(self, config: dict[str, Any]):
        """Add instrument to manager."""
        instance_name = config['instance_name']
        device_data = config['device_data']
        settings = config['settings']

        try:
            # Import and instantiate
            mod = importlib.import_module(device_data['module_path'])
            device_class = getattr(mod, device_data['wrapper_name'])
            device_instance = device_class()

            # Try to connect
            connection_str = settings.get('connection', '')
            connected = False
            if connection_str:
                try:
                    connected = device_instance.connect(connection_str)
                except Exception:
                    pass  # Silently fail connection

            # Store
            device_info = {
                'instance': device_instance,
                'data': device_data,
                'settings': settings,
                'connected': connected,
                'type': f"{device_data['category']}.{device_data['manufacturer']}.{device_data['name']}"
            }

            # Position in instruments zone (top half)
            num = len(self.instruments)
            col = num % 4
            row = num // 4
            x = 80 + col * 300
            y = 80 + row * 130

            # Create block
            block = InstrumentBlock(instance_name, device_info, x, y, self)
            self.scene.addItem(block)

            device_info['block'] = block
            self.instruments[instance_name] = device_info

            # Scroll to show new item
            self.view.ensureVisible(block)

            self.status_label.setText(f"✓ Added instrument: {instance_name}")
            self.instrument_added.emit(instance_name, device_instance)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add instrument:\n{e}")

    def _add_interface(self, config: dict[str, Any]):
        """Add interface to manager."""
        instance_name = config['instance_name']
        metadata = config['interface_metadata']
        instrument_mapping = config['instrument_mapping']
        parameters = config['parameters']

        try:
            # Store interface info
            interface_info = {
                'metadata': metadata,
                'instrument_mapping': instrument_mapping,
                'parameters': parameters,
                'display_name': metadata.display_name,
                'icon': metadata.icon,
            }

            # Position in interfaces zone (bottom half)
            num = len(self.interfaces)
            col = num % 4
            row = num // 4
            x = 80 + col * 300
            y = 730 + row * 130

            # Create block
            block = InterfaceBlock(instance_name, interface_info, x, y, self)
            self.scene.addItem(block)

            interface_info['block'] = block
            self.interfaces[instance_name] = interface_info

            # Create connection lines
            for role, inst_name in instrument_mapping.items():
                if inst_name in self.instruments:
                    line = ConnectionLine(block, self.instruments[inst_name]['block'])
                    self.scene.addItem(line)
                    self.connections.append(line)

            # Scroll to show new item
            self.view.ensureVisible(block)

            self.status_label.setText(f"✓ Added interface: {instance_name}")
            self.interface_added.emit(instance_name, interface_info)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add interface:\n{e}")

    def update_connections(self):
        """Update all connection lines."""
        for conn in self.connections:
            conn.update_position()

    def _auto_layout(self):
        """Auto-layout blocks in zones."""
        # Layout instruments
        for i, (name, info) in enumerate(self.instruments.items()):
            col = i % 4
            row = i // 4
            x = 80 + col * 300
            y = 80 + row * 130
            if 'block' in info:
                info['block'].setPos(x, y)

        # Layout interfaces
        for i, (name, info) in enumerate(self.interfaces.items()):
            col = i % 4
            row = i // 4
            x = 80 + col * 300
            y = 730 + row * 130
            if 'block' in info:
                info['block'].setPos(x, y)

        self.update_connections()
