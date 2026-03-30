"""
AI Workflow Generation Tools

Two approaches:
1. Template-based workflow generation (existing)
2. Direct Python code generation (new - for AI chatbot)
"""

import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from labpilot_core.core.session import Session
from labpilot_core.workflow.templates import (
    WORKFLOW_TEMPLATES,
    get_template,
    get_template_by_use_case,
    get_templates_for_instruments,
    list_templates,
)


class GenerateWorkflowTool:
    """
    AI tool to generate workflows from natural language requests.

    Uses workflow template library to match user intent to workflow patterns.

    Example usage by AI:
        User: "I want to scan the laser from 600 to 800nm and record the spectrum"

        AI calls: generate_workflow(
            request="scan laser from 600 to 800nm and record spectrum",
            parameters={
                "start_wavelength": 600,
                "end_wavelength": 800
            }
        )

        Returns: Complete workflow specification with:
        - Workflow nodes and connections
        - Parameter definitions for UI generation
        - Instrument requirements
        - Expected outputs
    """

    name = "generate_workflow"
    description = """Generate a workflow from natural language request.

    Use this when the user asks to create a workflow, measurement, scan, or acquisition.

    The tool will:
    1. Match the request to a workflow template
    2. Find appropriate instruments
    3. Generate parameter-based UI configuration
    4. Return complete workflow specification

    Examples:
    - "scan wavelength and record spectrum" → spectrum_acquisition template
    - "take pictures with the camera" → camera_live_view template
    - "map the sample" → xy_scan template
    - "monitor signal over time" → time_series template
    """

    class Parameters(BaseModel):
        request: str = Field(
            description="User's natural language request for workflow"
        )
        parameters: dict[str, Any] | None = Field(
            default=None,
            description="Optional parameter values specified by user (e.g. {'start_wavelength': 600})"
        )
        instrument_preferences: dict[str, str] | None = Field(
            default=None,
            description="Optional instrument preferences (e.g. {'laser': 'laser1'})"
        )

    @staticmethod
    async def execute(session: Session, params: Parameters) -> dict[str, Any]:
        """
        Generate workflow from natural language request.

        Args:
            session: LabPilot session
            params: GenerateWorkflowTool.Parameters

        Returns:
            Workflow specification with:
            - workflow_id: Generated workflow ID
            - name: Workflow name
            - template_used: Template key
            - parameters: Parameter definitions for UI
            - nodes: Workflow nodes
            - connections: Node connections
            - required_instruments: Instrument requirements
            - outputs: Expected data outputs
        """
        # 1. Match request to template
        template_key = get_template_by_use_case(params.request)

        if not template_key:
            # No template match - provide available templates
            templates = list_templates()
            return {
                "success": False,
                "error": "Could not match request to workflow template",
                "available_templates": templates,
                "suggestion": "Try one of: " + ", ".join([t["name"] for t in templates])
            }

        template = get_template(template_key)

        # 2. Check available instruments via adapter registry
        from labpilot_core.adapters import adapter_registry

        # Get available adapters (potential instruments)
        available_adapters = adapter_registry.list_with_schemas()

        # Convert to a more useful format for matching
        instruments = []
        for adapter_key, schema in available_adapters.items():
            # Infer dimensionality for motors based on settable parameters
            dimensionality = "0D"  # Default
            if schema.kind == "motor":
                settable_count = len(schema.settable)
                if settable_count >= 3:
                    dimensionality = "3D"
                elif settable_count >= 2:
                    dimensionality = "2D"
                elif settable_count >= 1:
                    dimensionality = "1D"
            elif schema.kind == "detector":
                # For detectors, check tags first for explicit dimensionality
                if any('0D' in tag for tag in schema.tags):
                    dimensionality = "0D"
                elif any('1D' in tag for tag in schema.tags):
                    dimensionality = "1D"
                elif any('2D' in tag for tag in schema.tags):
                    dimensionality = "2D"
                else:
                    # Fallback: infer from readable parameters
                    readable_count = len(schema.readable)
                    if readable_count >= 2:
                        dimensionality = "2D"
                    elif readable_count >= 1:
                        dimensionality = "1D"

            instruments.append({
                'id': adapter_key,
                'kind': schema.kind,
                'tags': schema.tags,
                'name': schema.name,
                'dimensionality': dimensionality,
            })

        # Find instruments that match template requirements
        instrument_mapping = {}
        missing_instruments = []

        for inst_name, inst_reqs in template["required_instruments"].items():
            # Find matching instrument
            matched = None
            for inst in instruments:
                # Check kind
                if inst['kind'] != inst_reqs.get("kind"):
                    continue

                # Check dimensionality
                if "dimensionality" in inst_reqs:
                    if inst['dimensionality'] != inst_reqs["dimensionality"]:
                        continue

                # Check tags if specified
                if "tags" in inst_reqs:
                    inst_tags = set(inst['tags'])
                    req_tags = set(inst_reqs["tags"])
                    if not req_tags.intersection(inst_tags):
                        continue

                # Found match
                matched = inst
                break

            if matched:
                instrument_mapping[inst_name] = matched['id']
            else:
                missing_instruments.append({
                    'name': inst_name,
                    'requirements': inst_reqs
                })

        if missing_instruments:
            return {
                "success": False,
                "error": "Missing required instruments",
                "missing": missing_instruments,
                "suggestion": f"Template '{template['name']}' requires: {', '.join([m['name'] for m in missing_instruments])}"
            }

        # 3. Build parameter definitions (for UI generation)
        parameter_defs = []
        for param_spec in template["parameters"]:
            # Override with user-provided values if available
            value = param_spec["value"]
            if params.parameters and param_spec["name"] in params.parameters:
                value = params.parameters[param_spec["name"]]

            param_def = {
                "name": param_spec["name"],
                "type": param_spec["type"],
                "value": value,
                "limits": tuple(param_spec["limits"]) if "limits" in param_spec else None,
                "unit": param_spec.get("unit"),
                "description": param_spec.get("description"),
            }
            parameter_defs.append(param_def)

        # 4. Build workflow nodes with instrument mapping
        nodes = []
        for node_spec in template["nodes"]:
            node = node_spec.copy()

            # Map template instrument names to actual instrument IDs
            if "instrument" in node and node["instrument"] in instrument_mapping:
                node["instrument_id"] = instrument_mapping[node["instrument"]]

            nodes.append(node)

        # 5. Generate workflow ID
        import time
        workflow_id = f"wf_{template_key}_{int(time.time())}"

        # 6. Return complete workflow specification
        return {
            "success": True,
            "workflow_id": workflow_id,
            "name": template["name"],
            "template_used": template_key,
            "description": template["description"],

            # For UI generation
            "parameter_definitions": parameter_defs,

            # For workflow execution
            "nodes": nodes,
            "connections": template["connections"],
            "instrument_mapping": instrument_mapping,

            # Metadata
            "required_instruments": template["required_instruments"],
            "outputs": template["outputs"],

            # AI hint
            "next_steps": [
                "Workflow parameters have been defined",
                "UI will be auto-generated from parameters",
                "User can modify parameters before running",
                "Click 'Run' to execute workflow"
            ]
        }


class ListWorkflowTemplatesTool:
    """AI tool to list available workflow templates."""

    name = "list_workflow_templates"
    description = """List all available workflow templates.

    Use this to show users what kinds of workflows are available,
    or to understand what workflow patterns exist.

    Returns list of templates with names, descriptions, and use cases.
    """

    @staticmethod
    async def execute(session: Session, params: None) -> dict[str, Any]:
        """List all workflow templates."""
        templates = list_templates()

        # Also show which templates can run with current instruments
        instruments = await session.list_instruments()
        instrument_info = [
            {
                "kind": inst.kind,
                "dimensionality": inst.dimensionality,
                "tags": inst.tags,
            }
            for inst in instruments
        ]

        runnable = get_templates_for_instruments(instrument_info)

        return {
            "success": True,
            "templates": templates,
            "total_templates": len(templates),
            "runnable_with_current_instruments": runnable,
            "suggestion": f"You can run these templates now: {', '.join(runnable)}" if runnable else "Connect instruments to enable workflows"
        }


class GetWorkflowTemplateTool:
    """AI tool to get detailed information about a specific template."""

    name = "get_workflow_template"
    description = """Get detailed information about a specific workflow template.

    Use this to understand the structure, parameters, and requirements
    of a specific workflow template.
    """

    class Parameters(BaseModel):
        template_key: str = Field(
            description="Template key (e.g. 'spectrum_acquisition', 'xy_scan')"
        )

    @staticmethod
    async def execute(session: Session, params: Parameters) -> dict[str, Any]:
        """Get workflow template details."""
        template = get_template(params.template_key)

        if not template:
            available = list(WORKFLOW_TEMPLATES.keys())
            return {
                "success": False,
                "error": f"Template '{params.template_key}' not found",
                "available_templates": available
            }

        return {
            "success": True,
            "template": template
        }


# ===== NEW AI TOOLS FOR DIRECT PYTHON CODE GENERATION =====

class GenerateWorkflowCodeTool:
    """
    AI tool to generate complete Python workflow code from natural language requests.

    This generates standalone Python code (not templates) that the user can review,
    modify, and save as a workflow.

    Example usage by AI:
        User: "Create a temperature sweep from 10K to 300K measuring conductivity"

        AI calls: generate_workflow_code(
            request="temperature sweep 10K to 300K measuring conductivity",
            workflow_name="TemperatureSweep"
        )

        Returns: Complete Python code for a temperature sweep workflow class
    """

    name = "generate_workflow_code"
    description = """Generate complete Python workflow code from natural language request.

    Use this when the user asks to create a workflow, measurement, or experiment.

    The tool will:
    1. Analyze the user's request
    2. Generate complete Python workflow code
    3. Include configuration class for parameters
    4. Include data class for results
    5. Include initialization, run, and cleanup methods
    6. Generate UI configuration for parameter input

    Types of workflows you can generate:
    - Spectroscopy: wavelength scans, power dependence
    - Temperature measurements: sweeps, monitoring
    - Imaging: camera acquisition, scanning microscopy
    - Motion control: stage scanning, positioning
    - Time series: monitoring over time
    - Power measurements: laser power, electrical power
    """

    class Parameters(BaseModel):
        request: str = Field(
            description="User's natural language request for the workflow"
        )
        workflow_name: str = Field(
            description="Name for the workflow class (e.g. 'TemperatureSweep')"
        )
        parameters: dict[str, Any] | None = Field(
            default=None,
            description="Optional specific parameters mentioned by user"
        )

    @staticmethod
    async def execute(session: Session, params: Parameters) -> dict[str, Any]:
        """
        Generate complete Python workflow code.

        Returns:
            - success: bool
            - workflow_code: str (complete Python code)
            - ui_config: dict (Qt UI configuration)
            - filename: str (suggested filename)
            - description: str
        """
        # Get available instruments from adapter registry
        from labpilot_core.adapters import adapter_registry
        available_adapters = adapter_registry.list_with_schemas()

        # Analyze request to determine workflow type and required instruments
        request_lower = params.request.lower()

        # Determine workflow type
        workflow_type = "generic"
        if any(word in request_lower for word in ["temperature", "temp", "heating", "cooling"]):
            workflow_type = "temperature"
        elif any(word in request_lower for word in ["spectrum", "wavelength", "spectroscopy", "laser"]):
            workflow_type = "spectroscopy"
        elif any(word in request_lower for word in ["image", "camera", "picture", "photo"]):
            workflow_type = "imaging"
        elif any(word in request_lower for word in ["scan", "map", "raster", "position"]):
            workflow_type = "scanning"
        elif any(word in request_lower for word in ["time", "monitor", "continuous", "series"]):
            workflow_type = "time_series"
        elif any(word in request_lower for word in ["power", "intensity", "brightness"]):
            workflow_type = "power"

        # Generate workflow code based on type
        code_templates = {
            "temperature": _generate_temperature_workflow,
            "spectroscopy": _generate_spectroscopy_workflow,
            "imaging": _generate_imaging_workflow,
            "scanning": _generate_scanning_workflow,
            "time_series": _generate_time_series_workflow,
            "power": _generate_power_workflow,
            "generic": _generate_generic_workflow
        }

        generator = code_templates[workflow_type]
        workflow_code, ui_config = generator(
            params.workflow_name,
            params.request,
            params.parameters or {},
            available_adapters
        )

        # Generate filename
        filename = f"{params.workflow_name.lower().replace(' ', '_')}.py"

        return {
            "success": True,
            "workflow_code": workflow_code,
            "ui_config": ui_config,
            "filename": filename,
            "description": f"Generated {workflow_type} workflow: {params.workflow_name}",
            "workflow_type": workflow_type
        }


class SaveWorkflowCodeTool:
    """
    AI tool to save generated workflow code to the workflows directory.

    Saves both the Python code and UI configuration file.
    """

    name = "save_workflow_code"
    description = """Save generated workflow code to the workflows directory.

    Use this after the user approves the generated workflow code.
    This will save both the Python file and UI configuration.
    """

    class Parameters(BaseModel):
        workflow_code: str = Field(description="Complete Python workflow code")
        filename: str = Field(description="Filename for the workflow (e.g. 'temperature_sweep.py')")
        ui_config: dict[str, Any] = Field(description="UI configuration dictionary")
        workflow_name: str = Field(description="Human-readable workflow name")
        description: str = Field(default="", description="Workflow description")

    @staticmethod
    async def execute(session: Session, params: Parameters) -> dict[str, Any]:
        """
        Save workflow code and configuration to workflows directory.
        """
        # Get workflows directory path
        from pathlib import Path
        workflows_dir = Path(__file__).parent.parent.parent / "workflows"
        workflows_dir.mkdir(exist_ok=True)

        # Save Python workflow code
        workflow_path = workflows_dir / params.filename
        with open(workflow_path, 'w', encoding='utf-8') as f:
            f.write(params.workflow_code)

        # Save UI configuration
        config_filename = params.filename.replace('.py', '_config.json')
        config_path = workflows_dir / config_filename

        import json
        config_data = {
            "name": params.workflow_name,
            "description": params.description,
            "ui": params.ui_config,
            "created_at": time.time(),
            "filename": params.filename
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)

        return {
            "success": True,
            "message": f"Workflow saved successfully as {params.filename}",
            "workflow_path": str(workflow_path),
            "config_path": str(config_path),
            "suggestion": f"Workflow '{params.workflow_name}' is now available in the manager list"
        }


class ShowWorkflowCodeTool:
    """
    AI tool to display workflow code to user for review and modification.
    """

    name = "show_workflow_code"
    description = """Display generated workflow code to the user for review.

    Use this to show the generated Python code in a formatted way
    so the user can review and potentially modify it before saving.
    """

    class Parameters(BaseModel):
        workflow_code: str = Field(description="Complete Python workflow code to display")
        workflow_name: str = Field(description="Name of the workflow")
        description: str = Field(default="", description="Workflow description")

    @staticmethod
    async def execute(session: Session, params: Parameters) -> dict[str, Any]:
        """
        Format and return workflow code for display.
        """
        return {
            "success": True,
            "display_code": params.workflow_code,
            "workflow_name": params.workflow_name,
            "description": params.description,
            "message": f"Generated workflow code for '{params.workflow_name}'. Review and let me know if you'd like any modifications before saving."
        }


# ===== CODE GENERATION FUNCTIONS =====

def _generate_temperature_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate temperature sweep/monitoring workflow code."""

    # Extract parameters from request
    start_temp = params.get("start_temperature", 10.0)  # K
    end_temp = params.get("end_temperature", 300.0)  # K
    temp_step = params.get("temperature_step", 10.0)  # K
    measurement_time = params.get("measurement_time", 1.0)  # seconds

    code = f'''"""Temperature workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    start_temperature: float = {start_temp}  # K
    end_temperature: float = {end_temp}  # K
    temperature_step: float = {temp_step}  # K
    measurement_time: float = {measurement_time}  # seconds per point
    stabilization_time: float = 5.0  # seconds to wait after setting temperature


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    temperatures: list[float]  # K
    measurements: list[float]  # Measurement values
    timestamps: list[float]  # Unix timestamps
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for temperature-dependent measurements.

    Usage:
        workflow = {name}(
            temperature_controller="temperature_controller_1",
            measurement_device="multimeter_1"
        )
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(
        self,
        temperature_controller: str = "fake_temperature_controller",
        measurement_device: str = "fake_multimeter",
    ):
        """Initialize workflow with device adapters.

        Args:
            temperature_controller: Adapter key for temperature controller
            measurement_device: Adapter key for measurement device
        """
        self.temp_controller_key = temperature_controller
        self.measurement_device_key = measurement_device
        self.temp_controller = None
        self.measurement_device = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize devices."""
        # Get adapter classes
        TempClass = adapter_registry.get(self.temp_controller_key)
        MeasurementClass = adapter_registry.get(self.measurement_device_key)

        # Instantiate
        self.temp_controller = TempClass()
        self.measurement_device = MeasurementClass()

        # Connect
        await self.temp_controller.connect()
        await self.measurement_device.connect()

    async def cleanup(self) -> None:
        """Disconnect devices."""
        if self.temp_controller:
            await self.temp_controller.disconnect()
        if self.measurement_device:
            await self.measurement_device.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run temperature sweep measurement.

        Args:
            config: Measurement configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with temperature sweep results
        """
        if config is None:
            config = {name}Config()

        self.running = True

        # Generate temperature points
        temperatures = np.arange(
            config.start_temperature,
            config.end_temperature + config.temperature_step,
            config.temperature_step
        ).tolist()

        measurements = []
        timestamps = []

        total_points = len(temperatures)

        for i, target_temp in enumerate(temperatures):
            if not self.running:
                break

            # Set temperature
            await self.temp_controller.set_temperature(target_temp)

            # Wait for stabilization
            await asyncio.sleep(config.stabilization_time)

            # Wait for measurement time
            await asyncio.sleep(config.measurement_time)

            # Take measurement
            measurement_data = await self.measurement_device.read()
            measurement_value = measurement_data.get("value", 0.0)

            measurements.append(measurement_value)
            timestamps.append(time.time())

            # Report progress
            if progress_callback:
                await progress_callback({{
                    "progress": (i + 1) / total_points * 100,
                    "temperature": target_temp,
                    "measurement": measurement_value,
                    "point": i + 1,
                    "total": total_points
                }})

        self.data = {name}Data(
            temperatures=temperatures[:len(measurements)],
            measurements=measurements,
            timestamps=timestamps,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop the running measurement."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "temp_controller_connected": self.temp_controller is not None,
            "measurement_device_connected": self.measurement_device is not None,
            "has_data": self.data is not None,
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "start_temperature",
                "label": "Start Temperature",
                "type": "float",
                "default": start_temp,
                "unit": "K",
                "description": "Starting temperature for the sweep"
            },
            {
                "name": "end_temperature",
                "label": "End Temperature",
                "type": "float",
                "default": end_temp,
                "unit": "K",
                "description": "Final temperature for the sweep"
            },
            {
                "name": "temperature_step",
                "label": "Temperature Step",
                "type": "float",
                "default": temp_step,
                "unit": "K",
                "description": "Temperature increment between measurements"
            },
            {
                "name": "measurement_time",
                "label": "Measurement Time",
                "type": "float",
                "default": measurement_time,
                "unit": "s",
                "description": "Time to spend at each temperature point"
            }
        ]
    }

    return code, ui_config


def _generate_spectroscopy_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate spectroscopy workflow code."""

    start_wavelength = params.get("start_wavelength", 500.0)  # nm
    end_wavelength = params.get("end_wavelength", 800.0)  # nm
    wavelength_step = params.get("wavelength_step", 1.0)  # nm
    integration_time = params.get("integration_time", 100.0)  # ms

    code = f'''"""Spectroscopy workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    start_wavelength: float = {start_wavelength}  # nm
    end_wavelength: float = {end_wavelength}  # nm
    wavelength_step: float = {wavelength_step}  # nm
    integration_time: float = {integration_time}  # ms
    averages: int = 1  # Number of spectra to average


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    wavelengths: list[float]  # nm
    intensities: list[float]  # Counts or normalized intensity
    timestamps: list[float]  # Unix timestamps
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for spectroscopic measurements.

    Usage:
        workflow = {name}(
            laser="tunable_laser_1",
            spectrometer="spectrometer_1"
        )
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(
        self,
        laser: str = "fake_tunable_laser",
        spectrometer: str = "fake_spectrometer",
    ):
        """Initialize workflow with device adapters.

        Args:
            laser: Adapter key for tunable laser
            spectrometer: Adapter key for spectrometer
        """
        self.laser_key = laser
        self.spectrometer_key = spectrometer
        self.laser = None
        self.spectrometer = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize devices."""
        # Get adapter classes
        LaserClass = adapter_registry.get(self.laser_key)
        SpectrometerClass = adapter_registry.get(self.spectrometer_key)

        # Instantiate
        self.laser = LaserClass()
        self.spectrometer = SpectrometerClass()

        # Connect
        await self.laser.connect()
        await self.spectrometer.connect()

    async def cleanup(self) -> None:
        """Disconnect devices."""
        if self.laser:
            await self.laser.disconnect()
        if self.spectrometer:
            await self.spectrometer.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run spectroscopic measurement.

        Args:
            config: Measurement configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with spectrum data
        """
        if config is None:
            config = {name}Config()

        self.running = True

        # Configure spectrometer
        await self.spectrometer.set_integration_time(config.integration_time)

        # Generate wavelength points
        wavelengths = np.arange(
            config.start_wavelength,
            config.end_wavelength + config.wavelength_step,
            config.wavelength_step
        ).tolist()

        intensities = []
        timestamps = []

        total_points = len(wavelengths)

        for i, wavelength in enumerate(wavelengths):
            if not self.running:
                break

            # Set laser wavelength
            await self.laser.set_wavelength(wavelength)
            await asyncio.sleep(0.1)  # Brief stabilization

            # Take spectrum measurement
            spectrum_data = await self.spectrometer.read()
            intensity = spectrum_data.get("intensity", 0.0)

            intensities.append(intensity)
            timestamps.append(time.time())

            # Report progress
            if progress_callback:
                await progress_callback({{
                    "progress": (i + 1) / total_points * 100,
                    "wavelength": wavelength,
                    "intensity": intensity,
                    "point": i + 1,
                    "total": total_points
                }})

        self.data = {name}Data(
            wavelengths=wavelengths[:len(intensities)],
            intensities=intensities,
            timestamps=timestamps,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop the running measurement."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "laser_connected": self.laser is not None,
            "spectrometer_connected": self.spectrometer is not None,
            "has_data": self.data is not None,
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "start_wavelength",
                "label": "Start Wavelength",
                "type": "float",
                "default": start_wavelength,
                "unit": "nm",
                "description": "Starting wavelength for the scan"
            },
            {
                "name": "end_wavelength",
                "label": "End Wavelength",
                "type": "float",
                "default": end_wavelength,
                "unit": "nm",
                "description": "Final wavelength for the scan"
            },
            {
                "name": "wavelength_step",
                "label": "Wavelength Step",
                "type": "float",
                "default": wavelength_step,
                "unit": "nm",
                "description": "Wavelength increment between measurements"
            },
            {
                "name": "integration_time",
                "label": "Integration Time",
                "type": "float",
                "default": integration_time,
                "unit": "ms",
                "description": "Spectrometer integration time"
            }
        ]
    }

    return code, ui_config


def _generate_imaging_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate imaging workflow code."""

    exposure_time = params.get("exposure_time", 50.0)  # ms
    num_images = params.get("num_images", 10)

    code = f'''"""Imaging workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    exposure_time: float = {exposure_time}  # ms
    num_images: int = {num_images}
    gain: str = "Medium"  # Low, Medium, High
    save_images: bool = True


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    images: list[np.ndarray]  # List of 2D image arrays
    timestamps: list[float]  # Unix timestamps
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for camera imaging.

    Usage:
        workflow = {name}(camera="camera_1")
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(self, camera: str = "fake_camera"):
        """Initialize workflow with camera adapter.

        Args:
            camera: Adapter key for camera
        """
        self.camera_key = camera
        self.camera = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize camera."""
        # Get adapter class
        CameraClass = adapter_registry.get(self.camera_key)

        # Instantiate and connect
        self.camera = CameraClass()
        await self.camera.connect()

    async def cleanup(self) -> None:
        """Disconnect camera."""
        if self.camera:
            await self.camera.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run image acquisition.

        Args:
            config: Acquisition configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with acquired images
        """
        if config is None:
            config = {name}Config()

        self.running = True

        # Configure camera
        await self.camera.set_exposure_time(config.exposure_time)
        await self.camera.set_gain(config.gain)

        images = []
        timestamps = []

        for i in range(config.num_images):
            if not self.running:
                break

            # Acquire image
            image_data = await self.camera.read()
            image = image_data.get("frame", np.zeros((100, 100)))

            images.append(image)
            timestamps.append(time.time())

            # Report progress
            if progress_callback:
                await progress_callback({{
                    "progress": (i + 1) / config.num_images * 100,
                    "image_count": i + 1,
                    "total": config.num_images,
                    "image_shape": image.shape
                }})

            # Brief pause between images
            await asyncio.sleep(0.1)

        self.data = {name}Data(
            images=images,
            timestamps=timestamps,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop image acquisition."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "camera_connected": self.camera is not None,
            "has_data": self.data is not None,
            "images_acquired": len(self.data.images) if self.data else 0
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "exposure_time",
                "label": "Exposure Time",
                "type": "float",
                "default": exposure_time,
                "unit": "ms",
                "description": "Camera exposure time"
            },
            {
                "name": "num_images",
                "label": "Number of Images",
                "type": "int",
                "default": num_images,
                "description": "Total number of images to acquire"
            },
            {
                "name": "gain",
                "label": "Camera Gain",
                "type": "dropdown",
                "options": ["Low", "Medium", "High"],
                "default": "Medium",
                "description": "Camera gain setting"
            }
        ]
    }

    return code, ui_config


def _generate_scanning_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate scanning workflow code."""

    x_range = params.get("x_range", 10.0)  # µm
    y_range = params.get("y_range", 10.0)  # µm
    num_points = params.get("num_points", 50)

    code = f'''"""Scanning workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    x_range: float = {x_range}  # µm
    y_range: float = {y_range}  # µm
    num_points_x: int = {num_points}
    num_points_y: int = {num_points}
    measurement_time: float = 0.1  # seconds per point


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    x_positions: list[float]  # µm
    y_positions: list[float]  # µm
    measurements: list[list[float]]  # 2D array of measurements
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for 2D scanning measurements.

    Usage:
        workflow = {name}(
            scanner="xy_scanner_1",
            detector="detector_1"
        )
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(
        self,
        scanner: str = "fake_xy_scanner",
        detector: str = "fake_detector",
    ):
        """Initialize workflow with scanner and detector.

        Args:
            scanner: Adapter key for XY scanner
            detector: Adapter key for detector
        """
        self.scanner_key = scanner
        self.detector_key = detector
        self.scanner = None
        self.detector = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize devices."""
        # Get adapter classes
        ScannerClass = adapter_registry.get(self.scanner_key)
        DetectorClass = adapter_registry.get(self.detector_key)

        # Instantiate
        self.scanner = ScannerClass()
        self.detector = DetectorClass()

        # Connect
        await self.scanner.connect()
        await self.detector.connect()

    async def cleanup(self) -> None:
        """Disconnect devices."""
        if self.scanner:
            await self.scanner.disconnect()
        if self.detector:
            await self.detector.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run 2D scanning measurement.

        Args:
            config: Scan configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with 2D scan results
        """
        if config is None:
            config = {name}Config()

        self.running = True

        # Generate scan positions
        x_positions = np.linspace(-config.x_range/2, config.x_range/2, config.num_points_x).tolist()
        y_positions = np.linspace(-config.y_range/2, config.y_range/2, config.num_points_y).tolist()

        measurements = []
        total_points = len(x_positions) * len(y_positions)
        point_count = 0

        for i, x_pos in enumerate(x_positions):
            if not self.running:
                break

            row_measurements = []

            for j, y_pos in enumerate(y_positions):
                if not self.running:
                    break

                # Move to position
                await self.scanner.set_x(x_pos)
                await self.scanner.set_y(y_pos)
                await asyncio.sleep(0.01)  # Settling time

                # Take measurement
                await asyncio.sleep(config.measurement_time)
                data = await self.detector.read()
                measurement = data.get("value", 0.0)

                row_measurements.append(measurement)
                point_count += 1

                # Report progress
                if progress_callback:
                    await progress_callback({{
                        "progress": point_count / total_points * 100,
                        "x_position": x_pos,
                        "y_position": y_pos,
                        "measurement": measurement,
                        "point": point_count,
                        "total": total_points
                    }})

            measurements.append(row_measurements)

        self.data = {name}Data(
            x_positions=x_positions,
            y_positions=y_positions,
            measurements=measurements,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop the scan."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "scanner_connected": self.scanner is not None,
            "detector_connected": self.detector is not None,
            "has_data": self.data is not None,
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "x_range",
                "label": "X Range",
                "type": "float",
                "default": x_range,
                "unit": "µm",
                "description": "Total X scan range"
            },
            {
                "name": "y_range",
                "label": "Y Range",
                "type": "float",
                "default": y_range,
                "unit": "µm",
                "description": "Total Y scan range"
            },
            {
                "name": "num_points_x",
                "label": "X Points",
                "type": "int",
                "default": num_points,
                "description": "Number of points along X axis"
            },
            {
                "name": "num_points_y",
                "label": "Y Points",
                "type": "int",
                "default": num_points,
                "description": "Number of points along Y axis"
            }
        ]
    }

    return code, ui_config


def _generate_time_series_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate time series monitoring workflow code."""

    duration = params.get("duration", 60.0)  # seconds
    interval = params.get("interval", 1.0)  # seconds

    code = f'''"""Time series workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    duration: float = {duration}  # seconds
    interval: float = {interval}  # seconds between measurements
    device_parameter: str = "value"  # parameter to monitor


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    timestamps: list[float]  # Unix timestamps
    values: list[float]  # Measured values
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for time series monitoring.

    Usage:
        workflow = {name}(device="sensor_1")
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(self, device: str = "fake_sensor"):
        """Initialize workflow with monitoring device.

        Args:
            device: Adapter key for monitoring device
        """
        self.device_key = device
        self.device = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize device."""
        # Get adapter class
        DeviceClass = adapter_registry.get(self.device_key)

        # Instantiate and connect
        self.device = DeviceClass()
        await self.device.connect()

    async def cleanup(self) -> None:
        """Disconnect device."""
        if self.device:
            await self.device.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run time series monitoring.

        Args:
            config: Monitoring configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with time series data
        """
        if config is None:
            config = {name}Config()

        self.running = True

        timestamps = []
        values = []

        start_time = time.time()
        next_measurement = start_time

        while self.running and (time.time() - start_time) < config.duration:
            current_time = time.time()

            if current_time >= next_measurement:
                # Take measurement
                data = await self.device.read()
                value = data.get(config.device_parameter, 0.0)

                timestamps.append(current_time)
                values.append(value)

                # Report progress
                elapsed = current_time - start_time
                progress = min(100.0, (elapsed / config.duration) * 100)

                if progress_callback:
                    await progress_callback({{
                        "progress": progress,
                        "elapsed_time": elapsed,
                        "current_value": value,
                        "measurements": len(values)
                    }})

                # Schedule next measurement
                next_measurement = current_time + config.interval

            # Brief sleep to prevent busy waiting
            await asyncio.sleep(0.01)

        self.data = {name}Data(
            timestamps=timestamps,
            values=values,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop monitoring."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "device_connected": self.device is not None,
            "has_data": self.data is not None,
            "measurements_count": len(self.data.values) if self.data else 0
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "duration",
                "label": "Duration",
                "type": "float",
                "default": duration,
                "unit": "s",
                "description": "Total monitoring duration"
            },
            {
                "name": "interval",
                "label": "Interval",
                "type": "float",
                "default": interval,
                "unit": "s",
                "description": "Time between measurements"
            }
        ]
    }

    return code, ui_config


def _generate_power_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate power measurement workflow code."""

    num_measurements = params.get("num_measurements", 10)
    measurement_time = params.get("measurement_time", 1.0)  # seconds

    code = f'''"""Power measurement workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    num_measurements: int = {num_measurements}
    measurement_time: float = {measurement_time}  # seconds per measurement
    wavelength: float = 633.0  # nm (for laser power measurements)


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    powers: list[float]  # Power values (mW or W)
    timestamps: list[float]  # Unix timestamps
    statistics: dict[str, float]  # Mean, std, etc.
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for power measurements.

    Usage:
        workflow = {name}(power_meter="power_meter_1")
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(self, power_meter: str = "fake_power_meter"):
        """Initialize workflow with power meter.

        Args:
            power_meter: Adapter key for power meter
        """
        self.power_meter_key = power_meter
        self.power_meter = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize power meter."""
        # Get adapter class
        PowerMeterClass = adapter_registry.get(self.power_meter_key)

        # Instantiate and connect
        self.power_meter = PowerMeterClass()
        await self.power_meter.connect()

    async def cleanup(self) -> None:
        """Disconnect power meter."""
        if self.power_meter:
            await self.power_meter.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run power measurements.

        Args:
            config: Measurement configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with power measurement results
        """
        if config is None:
            config = {name}Config()

        self.running = True

        powers = []
        timestamps = []

        for i in range(config.num_measurements):
            if not self.running:
                break

            # Take measurement
            await asyncio.sleep(config.measurement_time)
            data = await self.power_meter.read()
            power = data.get("power", 0.0)

            powers.append(power)
            timestamps.append(time.time())

            # Report progress
            if progress_callback:
                await progress_callback({{
                    "progress": (i + 1) / config.num_measurements * 100,
                    "power": power,
                    "measurement": i + 1,
                    "total": config.num_measurements
                }})

        # Calculate statistics
        import numpy as np
        powers_array = np.array(powers)
        statistics = {{
            "mean": float(np.mean(powers_array)),
            "std": float(np.std(powers_array)),
            "min": float(np.min(powers_array)),
            "max": float(np.max(powers_array))
        }}

        self.data = {name}Data(
            powers=powers,
            timestamps=timestamps,
            statistics=statistics,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop measurements."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "power_meter_connected": self.power_meter is not None,
            "has_data": self.data is not None,
            "measurements_count": len(self.data.powers) if self.data else 0
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "num_measurements",
                "label": "Number of Measurements",
                "type": "int",
                "default": num_measurements,
                "description": "Total number of power measurements"
            },
            {
                "name": "measurement_time",
                "label": "Measurement Time",
                "type": "float",
                "default": measurement_time,
                "unit": "s",
                "description": "Time for each power measurement"
            },
            {
                "name": "wavelength",
                "label": "Wavelength",
                "type": "float",
                "default": 633.0,
                "unit": "nm",
                "description": "Laser wavelength (if applicable)"
            }
        ]
    }

    return code, ui_config


def _generate_generic_workflow(name: str, request: str, params: dict, adapters: dict) -> tuple[str, dict]:
    """Generate generic workflow code."""

    code = f'''"""Generic workflow: {name}

{request}

Generated by LabPilot AI Workflow Generator
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from labpilot_core.adapters import adapter_registry


@dataclass
class {name}Config:
    """Configuration for {name.lower()} workflow."""

    num_steps: int = 10
    delay_between_steps: float = 1.0  # seconds


@dataclass
class {name}Data:
    """Results from {name.lower()} workflow."""

    results: list[dict[str, Any]]  # Generic results
    timestamps: list[float]
    config: {name}Config = field(default_factory={name}Config)


class {name}:
    """{name} workflow for generic measurements.

    Usage:
        workflow = {name}(device="device_1")
        await workflow.initialize()
        data = await workflow.run(config)
    """

    def __init__(self, device: str = "fake_device"):
        """Initialize workflow with device.

        Args:
            device: Adapter key for device
        """
        self.device_key = device
        self.device = None
        self.running = False
        self.data = None

    async def initialize(self) -> None:
        """Connect and initialize device."""
        # Get adapter class
        DeviceClass = adapter_registry.get(self.device_key)

        # Instantiate and connect
        self.device = DeviceClass()
        await self.device.connect()

    async def cleanup(self) -> None:
        """Disconnect device."""
        if self.device:
            await self.device.disconnect()

    async def run(
        self,
        config: {name}Config | None = None,
        progress_callback: Any = None,
    ) -> {name}Data:
        """Run generic workflow.

        Args:
            config: Workflow configuration
            progress_callback: Async callable for progress updates

        Returns:
            {name}Data with results
        """
        if config is None:
            config = {name}Config()

        self.running = True

        results = []
        timestamps = []

        for i in range(config.num_steps):
            if not self.running:
                break

            # Generic measurement/operation
            data = await self.device.read()
            results.append(data)
            timestamps.append(time.time())

            # Report progress
            if progress_callback:
                await progress_callback({{
                    "progress": (i + 1) / config.num_steps * 100,
                    "step": i + 1,
                    "total": config.num_steps,
                    "result": data
                }})

            # Delay between steps
            await asyncio.sleep(config.delay_between_steps)

        self.data = {name}Data(
            results=results,
            timestamps=timestamps,
            config=config
        )

        return self.data

    async def stop(self) -> None:
        """Stop workflow."""
        self.running = False

    def get_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return {{
            "running": self.running,
            "device_connected": self.device is not None,
            "has_data": self.data is not None,
            "steps_completed": len(self.data.results) if self.data else 0
        }}
'''

    ui_config = {
        "title": f"{name} Configuration",
        "description": f"Configure parameters for {name.lower()} workflow",
        "parameters": [
            {
                "name": "num_steps",
                "label": "Number of Steps",
                "type": "int",
                "default": 10,
                "description": "Number of workflow steps"
            },
            {
                "name": "delay_between_steps",
                "label": "Step Delay",
                "type": "float",
                "default": 1.0,
                "unit": "s",
                "description": "Delay between workflow steps"
            }
        ]
    }

    return code, ui_config
