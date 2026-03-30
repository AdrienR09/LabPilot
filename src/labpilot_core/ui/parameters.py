"""
LabPilot Parameter System - PyMoDAQ-style parameter definitions
Enables AI-friendly, configuration-driven GUI generation

Based on PyMoDAQ's parameter-centric approach where:
- Parameters define UI structure and behavior
- JSON schema auto-generated for AI introspection
- Clean, minimal Qt widgets created automatically
- Validation and type safety built-in
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParameterType(str, Enum):
    """Parameter types that map to Qt widgets."""
    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    LIST = "list"  # Dropdown/combo box
    ACTION = "action"  # Button
    GROUP = "group"  # Collapsible group
    TEXT = "text"  # Multi-line text
    FILE = "file"  # File selector
    COLOR = "color"  # Color picker
    SLIDER = "slider"  # Slider widget


@dataclass
class ParameterDefinition:
    """
    Single parameter definition - PyMoDAQ style.

    Examples:
        # Float with limits and unit
        exposure = ParameterDefinition(
            name='exposure',
            type=ParameterType.FLOAT,
            value=100.0,
            limits=(1.0, 10000.0),
            unit='ms',
            tip='Integration time for acquisition'
        )

        # Boolean toggle
        live_mode = ParameterDefinition(
            name='live_mode',
            type=ParameterType.BOOL,
            value=False,
            label='Live View'
        )

        # Dropdown list
        colormap = ParameterDefinition(
            name='colormap',
            type=ParameterType.LIST,
            value='viridis',
            options=['viridis', 'hot', 'cool', 'gray'],
            label='Color Map'
        )

        # Action button
        acquire = ParameterDefinition(
            name='acquire',
            type=ParameterType.ACTION,
            label='Start Acquisition',
            callback=start_acquisition_callback
        )
    """

    name: str  # Parameter identifier
    type: ParameterType  # Widget type
    value: Any = None  # Current value
    label: str | None = None  # Display label (defaults to name if None)
    limits: tuple | None = None  # (min, max) for numeric types
    unit: str | None = None  # Physical unit (nm, ms, etc.)
    options: list[Any] | None = None  # For LIST type
    tip: str | None = None  # Tooltip
    icon: str | None = None  # Icon (emoji or path)
    readonly: bool = False  # Read-only parameter
    visible: bool = True  # Visibility
    decimals: int = 2  # Decimal places for float
    step: float | None = None  # Step size for numeric
    callback: Callable | None = None  # For ACTION type
    group: str | None = None  # Group this parameter belongs to

    # Conditional visibility
    show_if: dict[str, Any] | None = None  # Show if condition met

    # Metadata for AI
    description: str | None = None  # Long description for AI
    ai_hint: str | None = None  # Hint for AI about when to use this

    def __post_init__(self):
        """Set defaults."""
        if self.label is None:
            # Convert snake_case to Title Case
            self.label = self.name.replace('_', ' ').title()

        if self.tip is None and self.description:
            self.tip = self.description[:100]  # First 100 chars

    @property
    def display_value(self) -> str:
        """Format value for display."""
        if self.type == ParameterType.FLOAT:
            if self.unit:
                return f"{self.value:.{self.decimals}f} {self.unit}"
            return f"{self.value:.{self.decimals}f}"
        elif self.type == ParameterType.INT:
            if self.unit:
                return f"{self.value} {self.unit}"
            return str(self.value)
        elif self.type == ParameterType.BOOL:
            return "On" if self.value else "Off"
        else:
            return str(self.value)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON schema for AI introspection."""
        schema = {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
        }

        if self.label != self.name:
            schema["label"] = self.label

        if self.limits:
            schema["limits"] = {"min": self.limits[0], "max": self.limits[1]}

        if self.unit:
            schema["unit"] = self.unit

        if self.options:
            schema["options"] = self.options

        if self.description:
            schema["description"] = self.description

        if self.ai_hint:
            schema["ai_hint"] = self.ai_hint

        if self.readonly:
            schema["readonly"] = True

        return schema

    def validate(self, value: Any) -> bool:
        """Validate a value for this parameter."""
        if self.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False
            if self.limits:
                return self.limits[0] <= value <= self.limits[1]

        elif self.type == ParameterType.INT:
            if not isinstance(value, int):
                return False
            if self.limits:
                return self.limits[0] <= value <= self.limits[1]

        elif self.type == ParameterType.BOOL:
            return isinstance(value, bool)

        elif self.type == ParameterType.STRING:
            return isinstance(value, str)

        elif self.type == ParameterType.LIST:
            return value in self.options if self.options else True

        return True


@dataclass
class ParameterGroup:
    """
    Group of related parameters - hierarchical organization.

    Example:
        acquisition = ParameterGroup(
            name='acquisition',
            label='Acquisition Settings',
            parameters=[
                ParameterDefinition(name='exposure', ...),
                ParameterDefinition(name='gain', ...),
            ],
            collapsible=True,
            collapsed=False
        )
    """

    name: str
    label: str | None = None
    parameters: list[ParameterDefinition | ParameterGroup] = field(default_factory=list)
    collapsible: bool = False  # Can be collapsed in UI
    collapsed: bool = False  # Initially collapsed
    tip: str | None = None
    icon: str | None = None

    def __post_init__(self):
        if self.label is None:
            self.label = self.name.replace('_', ' ').title()

    def add_parameter(self, param: ParameterDefinition | ParameterGroup):
        """Add a parameter or sub-group."""
        self.parameters.append(param)

    def get_parameter(self, name: str) -> ParameterDefinition | None:
        """Get parameter by name (searches recursively)."""
        for param in self.parameters:
            if isinstance(param, ParameterDefinition) and param.name == name:
                return param
            elif isinstance(param, ParameterGroup):
                result = param.get_parameter(name)
                if result:
                    return result
        return None

    def get_all_parameters(self) -> list[ParameterDefinition]:
        """Get all parameters (flattened, recursive)."""
        result = []
        for param in self.parameters:
            if isinstance(param, ParameterDefinition):
                result.append(param)
            elif isinstance(param, ParameterGroup):
                result.extend(param.get_all_parameters())
        return result

    def to_json_schema(self) -> dict[str, Any]:
        """Convert group to JSON schema for AI."""
        schema = {
            "name": self.name,
            "type": "group",
            "label": self.label,
            "parameters": [p.to_json_schema() for p in self.parameters],
        }

        if self.tip:
            schema["description"] = self.tip

        if self.collapsible:
            schema["collapsible"] = True
            schema["collapsed"] = self.collapsed

        return schema

    def get_values(self) -> dict[str, Any]:
        """Get all parameter values as dict."""
        values = {}
        for param in self.parameters:
            if isinstance(param, ParameterDefinition):
                values[param.name] = param.value
            elif isinstance(param, ParameterGroup):
                values[param.name] = param.get_values()
        return values

    def set_values(self, values: dict[str, Any]):
        """Set parameter values from dict."""
        for key, value in values.items():
            param = self.get_parameter(key)
            if param and param.validate(value):
                param.value = value


class ParameterTree:
    """
    Top-level parameter tree for an instrument or workflow.

    Example usage:
        # Define instrument parameters
        tree = ParameterTree(name="Camera Settings")

        tree.add_group(ParameterGroup(
            name='acquisition',
            parameters=[
                ParameterDefinition(name='exposure', type=ParameterType.FLOAT,
                                  value=100, limits=(0.1, 10000), unit='ms'),
                ParameterDefinition(name='gain', type=ParameterType.FLOAT,
                                  value=1.0, limits=(1.0, 16.0)),
            ]
        ))

        tree.add_group(ParameterGroup(
            name='display',
            parameters=[
                ParameterDefinition(name='colormap', type=ParameterType.LIST,
                                  options=['viridis', 'hot', 'cool', 'gray']),
                ParameterDefinition(name='autoscale', type=ParameterType.BOOL, value=True),
            ]
        ))

        # Generate UI
        widget = tree.create_qt_widget()

        # For AI introspection
        schema = tree.to_json_schema()
    """

    def __init__(self, name: str, label: str | None = None):
        self.name = name
        self.label = label or name
        self.groups: list[ParameterGroup] = []

    def add_group(self, group: ParameterGroup):
        """Add a parameter group."""
        self.groups.append(group)

    def add_parameter(self, param: ParameterDefinition, group_name: str = "main"):
        """Add a parameter to a group (creates group if needed)."""
        # Find existing group
        for group in self.groups:
            if group.name == group_name:
                group.add_parameter(param)
                return

        # Create new group
        new_group = ParameterGroup(name=group_name)
        new_group.add_parameter(param)
        self.groups.append(new_group)

    def get_parameter(self, name: str) -> ParameterDefinition | None:
        """Get parameter by name."""
        for group in self.groups:
            result = group.get_parameter(name)
            if result:
                return result
        return None

    def get_all_parameters(self) -> list[ParameterDefinition]:
        """Get all parameters (flattened)."""
        result = []
        for group in self.groups:
            result.extend(group.get_all_parameters())
        return result

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON schema for AI introspection."""
        return {
            "name": self.name,
            "label": self.label,
            "groups": [g.to_json_schema() for g in self.groups],
        }

    def get_values(self) -> dict[str, Any]:
        """Get all parameter values."""
        return {group.name: group.get_values() for group in self.groups}

    def set_values(self, values: dict[str, Any]):
        """Set parameter values."""
        for group_name, group_values in values.items():
            for group in self.groups:
                if group.name == group_name:
                    group.set_values(group_values)

    def create_qt_widget(self):
        """Create Qt widget from parameter tree."""
        # Import here to avoid circular dependency
        from labpilot_core.ui.parameter_ui import ParameterTreeWidget
        return ParameterTreeWidget(self)


# ===== Helper Functions =====

def create_instrument_parameters(schema: dict[str, Any]) -> ParameterTree:
    """
    Create parameter tree from instrument schema.

    Converts instrument schema (settable/readable) to parameter definitions.
    """
    tree = ParameterTree(name=schema.get('name', 'Instrument'))

    # Settable parameters
    if 'settable' in schema:
        settable_group = ParameterGroup(name='settings', label='Settings')

        for param_name, param_type in schema['settable'].items():
            # Determine parameter type
            if param_type in ('float64', 'float32'):
                ptype = ParameterType.FLOAT
            elif param_type in ('int32', 'int64', 'uint32', 'uint64'):
                ptype = ParameterType.INT
            elif param_type == 'bool':
                ptype = ParameterType.BOOL
            else:
                ptype = ParameterType.STRING

            # Get limits if available
            limits = None
            if 'limits' in schema and param_name in schema['limits']:
                limit_data = schema['limits'][param_name]
                limits = (limit_data.get('min'), limit_data.get('max'))

            # Get unit if available
            unit = None
            if 'units' in schema and param_name in schema['units']:
                unit = schema['units'][param_name]

            # Create parameter
            param = ParameterDefinition(
                name=param_name,
                type=ptype,
                value=0.0 if ptype == ParameterType.FLOAT else 0,
                limits=limits,
                unit=unit,
            )

            settable_group.add_parameter(param)

        tree.add_group(settable_group)

    # Readable parameters (read-only display)
    if 'readable' in schema:
        readable_group = ParameterGroup(name='status', label='Status', collapsible=True)

        for param_name, param_type in schema['readable'].items():
            if param_name not in schema.get('settable', {}):  # Skip if already in settable
                param = ParameterDefinition(
                    name=param_name,
                    type=ParameterType.STRING,  # Display as string
                    value='---',
                    readonly=True,
                )
                readable_group.add_parameter(param)

        tree.add_group(readable_group)

    return tree


def create_workflow_parameters(workflow_spec: dict[str, Any]) -> ParameterTree:
    """
    Create parameter tree from workflow specification.

    Workflow spec should include parameter definitions for the workflow UI.
    """
    tree = ParameterTree(
        name=workflow_spec.get('name', 'Workflow'),
        label=workflow_spec.get('label', workflow_spec.get('name', 'Workflow'))
    )

    # Add parameter groups from spec
    for group_spec in workflow_spec.get('parameter_groups', []):
        group = ParameterGroup(
            name=group_spec['name'],
            label=group_spec.get('label'),
            collapsible=group_spec.get('collapsible', False),
        )

        for param_spec in group_spec.get('parameters', []):
            param = ParameterDefinition(
                name=param_spec['name'],
                type=ParameterType(param_spec['type']),
                value=param_spec.get('value'),
                limits=tuple(param_spec['limits']) if 'limits' in param_spec else None,
                unit=param_spec.get('unit'),
                options=param_spec.get('options'),
                label=param_spec.get('label'),
                tip=param_spec.get('tip'),
                description=param_spec.get('description'),
            )
            group.add_parameter(param)

        tree.add_group(group)

    return tree
