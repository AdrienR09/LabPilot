"""
LabPilot Parameter UI Generator - Qt Widgets from Parameters

Creates clean, minimal Qt widgets from parameter definitions.
PyMoDAQ-style UI generation - configuration-driven, not hardcoded.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labpilot_core.ui.parameters import (
    ParameterDefinition,
    ParameterGroup,
    ParameterTree,
    ParameterType,
)


class ParameterWidget(QWidget):
    """
    Base class for parameter widgets.

    Emits value_changed signal when parameter value changes.
    """

    value_changed = pyqtSignal(str, object)  # (param_name, new_value)

    def __init__(self, param: ParameterDefinition, parent=None):
        super().__init__(parent)
        self.param = param
        self.setup_ui()

    def setup_ui(self):
        """Override in subclasses."""
        pass

    def get_value(self):
        """Get current widget value."""
        return self.param.value

    def set_value(self, value):
        """Set widget value."""
        self.param.value = value


class FloatParameterWidget(ParameterWidget):
    """Float parameter with spinbox - minimal design."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Icon (optional)
        if self.param.icon:
            icon_label = QLabel(self.param.icon)
            icon_label.setFont(QFont("", 14))
            layout.addWidget(icon_label)

        # Label - minimal, no colon
        label = QLabel(self.param.label)
        label.setMinimumWidth(120)
        layout.addWidget(label)

        # Spinbox
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setDecimals(self.param.decimals)

        if self.param.limits:
            self.spinbox.setRange(self.param.limits[0], self.param.limits[1])
        else:
            self.spinbox.setRange(-1e10, 1e10)

        if self.param.step:
            self.spinbox.setSingleStep(self.param.step)
        else:
            # Smart step based on range
            if self.param.limits:
                range_size = self.param.limits[1] - self.param.limits[0]
                self.spinbox.setSingleStep(range_size / 100)
            else:
                self.spinbox.setSingleStep(0.1)

        self.spinbox.setValue(self.param.value or 0.0)
        self.spinbox.setReadOnly(self.param.readonly)

        # Unit label (if provided) - minimal
        if self.param.unit:
            self.spinbox.setSuffix(f" {self.param.unit}")

        # Tooltip
        if self.param.tip:
            self.spinbox.setToolTip(self.param.tip)
            label.setToolTip(self.param.tip)

        self.spinbox.valueChanged.connect(lambda v: self.value_changed.emit(self.param.name, v))

        layout.addWidget(self.spinbox)
        layout.addStretch()

    def get_value(self):
        return self.spinbox.value()

    def set_value(self, value):
        self.spinbox.setValue(value)


class IntParameterWidget(ParameterWidget):
    """Integer parameter with spinbox."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if self.param.icon:
            icon_label = QLabel(self.param.icon)
            icon_label.setFont(QFont("", 14))
            layout.addWidget(icon_label)

        label = QLabel(self.param.label)
        label.setMinimumWidth(120)
        layout.addWidget(label)

        self.spinbox = QSpinBox()

        if self.param.limits:
            self.spinbox.setRange(int(self.param.limits[0]), int(self.param.limits[1]))
        else:
            self.spinbox.setRange(-1000000, 1000000)

        if self.param.step:
            self.spinbox.setSingleStep(int(self.param.step))

        self.spinbox.setValue(self.param.value or 0)
        self.spinbox.setReadOnly(self.param.readonly)

        if self.param.unit:
            self.spinbox.setSuffix(f" {self.param.unit}")

        if self.param.tip:
            self.spinbox.setToolTip(self.param.tip)
            label.setToolTip(self.param.tip)

        self.spinbox.valueChanged.connect(lambda v: self.value_changed.emit(self.param.name, v))

        layout.addWidget(self.spinbox)
        layout.addStretch()

    def get_value(self):
        return self.spinbox.value()

    def set_value(self, value):
        self.spinbox.setValue(int(value))


class BoolParameterWidget(ParameterWidget):
    """Boolean parameter with checkbox - minimal design."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(self.param.label)
        self.checkbox.setChecked(self.param.value or False)
        self.checkbox.setEnabled(not self.param.readonly)

        if self.param.tip:
            self.checkbox.setToolTip(self.param.tip)

        self.checkbox.stateChanged.connect(
            lambda state: self.value_changed.emit(self.param.name, state == Qt.CheckState.Checked.value)
        )

        layout.addWidget(self.checkbox)
        layout.addStretch()

    def get_value(self):
        return self.checkbox.isChecked()

    def set_value(self, value):
        self.checkbox.setChecked(bool(value))


class ListParameterWidget(ParameterWidget):
    """List parameter with combobox."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(self.param.label)
        label.setMinimumWidth(120)
        layout.addWidget(label)

        self.combobox = QComboBox()

        if self.param.options:
            for option in self.param.options:
                self.combobox.addItem(str(option))

            if self.param.value:
                index = self.combobox.findText(str(self.param.value))
                if index >= 0:
                    self.combobox.setCurrentIndex(index)

        self.combobox.setEnabled(not self.param.readonly)

        if self.param.tip:
            self.combobox.setToolTip(self.param.tip)
            label.setToolTip(self.param.tip)

        self.combobox.currentTextChanged.connect(
            lambda text: self.value_changed.emit(self.param.name, text)
        )

        layout.addWidget(self.combobox)
        layout.addStretch()

    def get_value(self):
        return self.combobox.currentText()

    def set_value(self, value):
        index = self.combobox.findText(str(value))
        if index >= 0:
            self.combobox.setCurrentIndex(index)


class ActionParameterWidget(ParameterWidget):
    """Action parameter - button with callback."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.button = QPushButton(self.param.label)

        if self.param.icon:
            self.button.setText(f"{self.param.icon} {self.param.label}")

        if self.param.tip:
            self.button.setToolTip(self.param.tip)

        if self.param.callback:
            self.button.clicked.connect(self.param.callback)
        else:
            self.button.clicked.connect(lambda: self.value_changed.emit(self.param.name, True))

        layout.addWidget(self.button)
        layout.addStretch()


class StringParameterWidget(ParameterWidget):
    """String parameter with line edit."""

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(self.param.label)
        label.setMinimumWidth(120)
        layout.addWidget(label)

        self.lineedit = QLineEdit()
        self.lineedit.setText(self.param.value or "")
        self.lineedit.setReadOnly(self.param.readonly)

        if self.param.tip:
            self.lineedit.setToolTip(self.param.tip)
            label.setToolTip(self.param.tip)

        self.lineedit.textChanged.connect(
            lambda text: self.value_changed.emit(self.param.name, text)
        )

        layout.addWidget(self.lineedit, 1)

    def get_value(self):
        return self.lineedit.text()

    def set_value(self, value):
        self.lineedit.setText(str(value))


class ParameterGroupWidget(QWidget):
    """Widget for a parameter group - collapsible if specified."""

    value_changed = pyqtSignal(str, object)

    def __init__(self, group: ParameterGroup, parent=None):
        super().__init__(parent)
        self.group = group
        self.param_widgets = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if self.group.collapsible:
            # Use QGroupBox for collapsible groups
            group_box = QGroupBox(self.group.label)
            group_box.setCheckable(True)
            group_box.setChecked(not self.group.collapsed)

            group_layout = QVBoxLayout()
            group_layout.setSpacing(4)

            self._add_parameters(group_layout)

            group_box.setLayout(group_layout)
            layout.addWidget(group_box)

        else:
            # Minimal: No group box, just label
            if self.group.label and len(self.group.parameters) > 1:
                label = QLabel(self.group.label)
                label.setStyleSheet("font-weight: bold; color: #666; margin-top: 8px;")
                layout.addWidget(label)

            self._add_parameters(layout)

    def _add_parameters(self, layout):
        """Add parameter widgets to layout."""
        for param in self.group.parameters:
            if isinstance(param, ParameterDefinition):
                widget = create_parameter_widget(param)
                widget.value_changed.connect(self.value_changed.emit)
                self.param_widgets[param.name] = widget
                layout.addWidget(widget)

            elif isinstance(param, ParameterGroup):
                sub_group_widget = ParameterGroupWidget(param)
                sub_group_widget.value_changed.connect(self.value_changed.emit)
                layout.addWidget(sub_group_widget)

    def get_values(self):
        """Get all parameter values."""
        return {name: widget.get_value() for name, widget in self.param_widgets.items()}

    def set_values(self, values):
        """Set parameter values."""
        for name, value in values.items():
            if name in self.param_widgets:
                self.param_widgets[name].set_value(value)


class ParameterTreeWidget(QWidget):
    """
    Main widget for displaying a parameter tree.

    Creates a clean, minimal UI from parameter definitions.
    """

    value_changed = pyqtSignal(str, object)

    def __init__(self, tree: ParameterTree, parent=None):
        super().__init__(parent)
        self.tree = tree
        self.group_widgets = []
        self.setup_ui()

    def setup_ui(self):
        # Scroll area for many parameters
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Content widget
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Add parameter groups
        for group in self.tree.groups:
            group_widget = ParameterGroupWidget(group)
            group_widget.value_changed.connect(self.value_changed.emit)
            self.group_widgets.append(group_widget)
            layout.addWidget(group_widget)

        layout.addStretch()

        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def get_values(self):
        """Get all parameter values."""
        return self.tree.get_values()

    def set_values(self, values):
        """Set parameter values."""
        self.tree.set_values(values)
        # Update widgets
        for group_widget in self.group_widgets:
            group_values = values.get(group_widget.group.name, {})
            group_widget.set_values(group_values)


def create_parameter_widget(param: ParameterDefinition) -> ParameterWidget:
    """
    Factory function to create appropriate widget for parameter type.

    Returns clean, minimal widget based on parameter type.
    """
    widget_map = {
        ParameterType.FLOAT: FloatParameterWidget,
        ParameterType.INT: IntParameterWidget,
        ParameterType.BOOL: BoolParameterWidget,
        ParameterType.STRING: StringParameterWidget,
        ParameterType.LIST: ListParameterWidget,
        ParameterType.ACTION: ActionParameterWidget,
    }

    widget_class = widget_map.get(param.type, StringParameterWidget)
    return widget_class(param)
