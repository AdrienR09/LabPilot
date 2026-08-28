"""
Workflow Template Library

Collection of common workflow patterns for AI learning.
AI uses these as examples to understand workflow structure and generate new workflows.
"""

from typing import Any

# ===== WORKFLOW TEMPLATES =====

WORKFLOW_TEMPLATES = {
    "spectrum_acquisition": {
        "name": "Spectrum Acquisition",
        "description": "Scan wavelength and acquire spectrum at each point",
        "use_cases": [
            "record emission spectrum",
            "measure absorption spectrum",
            "scan laser wavelength",
        ],
        "required_instruments": {
            "laser": {"kind": "motor", "dimensionality": "1D", "tags": ["Tunable-Laser"]},
            "detector": {"kind": "detector", "dimensionality": "0D"},
        },
        "parameters": [
            {
                "name": "start_wavelength",
                "type": "float",
                "value": 600.0,
                "limits": (400.0, 1000.0),
                "unit": "nm",
                "description": "Starting wavelength for scan",
            },
            {
                "name": "end_wavelength",
                "type": "float",
                "value": 800.0,
                "limits": (400.0, 1000.0),
                "unit": "nm",
                "description": "Ending wavelength for scan",
            },
            {
                "name": "step_size",
                "type": "float",
                "value": 1.0,
                "limits": (0.1, 10.0),
                "unit": "nm",
                "description": "Wavelength step size",
            },
            {
                "name": "integration_time",
                "type": "float",
                "value": 100.0,
                "limits": (1.0, 10000.0),
                "unit": "ms",
                "description": "Integration time per point",
            },
        ],
        "nodes": [
            {
                "id": "scan_wavelength",
                "node_type": "scan",
                "instrument": "laser",
                "parameter": "wavelength",
                "scan_config": {
                    "start": "{{start_wavelength}}",
                    "end": "{{end_wavelength}}",
                    "step": "{{step_size}}",
                },
            },
            {
                "id": "acquire_signal",
                "node_type": "acquire",
                "instrument": "detector",
                "config": {
                    "integration_time": "{{integration_time}}",
                },
            },
        ],
        "connections": [["scan_wavelength", "acquire_signal"]],
        "outputs": ["wavelength", "intensity"],
    },

    "camera_live_view": {
        "name": "Camera Live View",
        "description": "Continuous camera acquisition with live display",
        "use_cases": [
            "live camera feed",
            "real-time imaging",
            "camera alignment",
        ],
        "required_instruments": {
            "camera": {"kind": "detector", "dimensionality": "2D", "tags": ["Camera"]},
        },
        "parameters": [
            {
                "name": "exposure_time",
                "type": "float",
                "value": 100.0,
                "limits": (0.1, 10000.0),
                "unit": "ms",
                "description": "Camera exposure time",
            },
            {
                "name": "gain",
                "type": "float",
                "value": 1.0,
                "limits": (1.0, 16.0),
                "description": "Camera gain",
            },
            {
                "name": "frame_rate",
                "type": "float",
                "value": 10.0,
                "limits": (0.1, 100.0),
                "unit": "fps",
                "description": "Target frame rate",
            },
        ],
        "nodes": [
            {
                "id": "acquire_frames",
                "node_type": "acquire_continuous",
                "instrument": "camera",
                "config": {
                    "exposure": "{{exposure_time}}",
                    "gain": "{{gain}}",
                    "rate": "{{frame_rate}}",
                },
            },
        ],
        "connections": [],
        "outputs": ["frame", "timestamp"],
    },

    "xy_scan": {
        "name": "XY Raster Scan",
        "description": "2D raster scan with detector acquisition at each point",
        "use_cases": [
            "image a sample",
            "map a surface",
            "confocal microscopy",
        ],
        "required_instruments": {
            "stage": {"kind": "motor", "dimensionality": "2D"},
            "detector": {"kind": "detector", "dimensionality": "0D"},
        },
        "parameters": [
            {
                "name": "x_start",
                "type": "float",
                "value": 0.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
                "description": "X start position",
            },
            {
                "name": "x_end",
                "type": "float",
                "value": 10.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
                "description": "X end position",
            },
            {
                "name": "x_points",
                "type": "int",
                "value": 50,
                "limits": (2, 1000),
                "description": "Number of X points",
            },
            {
                "name": "y_start",
                "type": "float",
                "value": 0.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
                "description": "Y start position",
            },
            {
                "name": "y_end",
                "type": "float",
                "value": 10.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
                "description": "Y end position",
            },
            {
                "name": "y_points",
                "type": "int",
                "value": 50,
                "limits": (2, 1000),
                "description": "Number of Y points",
            },
            {
                "name": "integration_time",
                "type": "float",
                "value": 10.0,
                "limits": (0.1, 10000.0),
                "unit": "ms",
                "description": "Integration time per pixel",
            },
        ],
        "nodes": [
            {
                "id": "scan_xy",
                "node_type": "scan_2d",
                "instrument": "stage",
                "scan_config": {
                    "x_start": "{{x_start}}",
                    "x_end": "{{x_end}}",
                    "x_points": "{{x_points}}",
                    "y_start": "{{y_start}}",
                    "y_end": "{{y_end}}",
                    "y_points": "{{y_points}}",
                },
            },
            {
                "id": "acquire_pixel",
                "node_type": "acquire",
                "instrument": "detector",
                "config": {
                    "integration_time": "{{integration_time}}",
                },
            },
        ],
        "connections": [["scan_xy", "acquire_pixel"]],
        "outputs": ["x", "y", "intensity"],
    },

    "time_series": {
        "name": "Time Series Acquisition",
        "description": "Acquire data continuously over time",
        "use_cases": [
            "monitor signal over time",
            "record time trace",
            "track changes",
        ],
        "required_instruments": {
            "detector": {"kind": "detector", "dimensionality": "0D"},
        },
        "parameters": [
            {
                "name": "duration",
                "type": "float",
                "value": 60.0,
                "limits": (1.0, 3600.0),
                "unit": "s",
                "description": "Total acquisition duration",
            },
            {
                "name": "sample_rate",
                "type": "float",
                "value": 10.0,
                "limits": (0.1, 1000.0),
                "unit": "Hz",
                "description": "Sampling rate",
            },
        ],
        "nodes": [
            {
                "id": "acquire_timeseries",
                "node_type": "acquire_timeseries",
                "instrument": "detector",
                "config": {
                    "duration": "{{duration}}",
                    "rate": "{{sample_rate}}",
                },
            },
        ],
        "connections": [],
        "outputs": ["time", "signal"],
    },

    "photoluminescence_map": {
        "name": "Photoluminescence Mapping",
        "description": "Scan XY stage and acquire PL spectrum at each point",
        "use_cases": [
            "map photoluminescence",
            "hyperspectral imaging",
            "emission mapping",
        ],
        "required_instruments": {
            "stage": {"kind": "motor", "dimensionality": "2D"},
            "spectrometer": {"kind": "detector", "dimensionality": "1D", "tags": ["Spectrometer"]},
        },
        "parameters": [
            {
                "name": "x_start",
                "type": "float",
                "value": 0.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
            },
            {
                "name": "x_end",
                "type": "float",
                "value": 10.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
            },
            {
                "name": "x_points",
                "type": "int",
                "value": 20,
                "limits": (2, 100),
            },
            {
                "name": "y_start",
                "type": "float",
                "value": 0.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
            },
            {
                "name": "y_end",
                "type": "float",
                "value": 10.0,
                "limits": (0.0, 100.0),
                "unit": "mm",
            },
            {
                "name": "y_points",
                "type": "int",
                "value": 20,
                "limits": (2, 100),
            },
            {
                "name": "integration_time",
                "type": "float",
                "value": 500.0,
                "limits": (10.0, 10000.0),
                "unit": "ms",
            },
        ],
        "nodes": [
            {
                "id": "scan_position",
                "node_type": "scan_2d",
                "instrument": "stage",
                "scan_config": {
                    "x_start": "{{x_start}}",
                    "x_end": "{{x_end}}",
                    "x_points": "{{x_points}}",
                    "y_start": "{{y_start}}",
                    "y_end": "{{y_end}}",
                    "y_points": "{{y_points}}",
                },
            },
            {
                "id": "acquire_spectrum",
                "node_type": "acquire",
                "instrument": "spectrometer",
                "config": {
                    "integration_time": "{{integration_time}}",
                },
            },
        ],
        "connections": [["scan_position", "acquire_spectrum"]],
        "outputs": ["x", "y", "wavelength", "intensity"],
    },
}


def get_template_by_use_case(user_query: str) -> str:
    """
    Match user query to workflow template by use case.

    Args:
        user_query: User's natural language request

    Returns:
        Template key that best matches the query
    """
    query_lower = user_query.lower()

    # Score each template based on keyword matches
    scores = {}
    for template_key, template in WORKFLOW_TEMPLATES.items():
        score = 0

        # Check name match
        if template["name"].lower() in query_lower:
            score += 10

        # Check description match
        if any(word in query_lower for word in template["description"].lower().split()):
            score += 3

        # Check use cases
        for use_case in template["use_cases"]:
            if use_case in query_lower:
                score += 5

        # Check instrument keywords
        for inst_info in template["required_instruments"].values():
            for tag in inst_info.get("tags", []):
                if tag.lower() in query_lower:
                    score += 4

        scores[template_key] = score

    # Return template with highest score
    if scores:
        best_template = max(scores, key=scores.get)
        if scores[best_template] > 0:
            return best_template

    return None


def get_template(template_key: str) -> dict[str, Any]:
    """Get workflow template by key."""
    return WORKFLOW_TEMPLATES.get(template_key)


def list_templates() -> list[dict[str, Any]]:
    """List all available workflow templates."""
    return [
        {
            "key": key,
            "name": template["name"],
            "description": template["description"],
            "use_cases": template["use_cases"],
        }
        for key, template in WORKFLOW_TEMPLATES.items()
    ]


def get_templates_for_instruments(available_instruments: list[dict[str, Any]]) -> list[str]:
    """
    Find templates that can be run with available instruments.

    Args:
        available_instruments: List of instrument metadata dicts

    Returns:
        List of template keys that match available instruments
    """
    matching_templates = []

    for template_key, template in WORKFLOW_TEMPLATES.items():
        required = template["required_instruments"]

        # Check if we have all required instrument types
        can_run = True
        for inst_name, inst_reqs in required.items():
            # Try to match an available instrument
            matched = False
            for avail in available_instruments:
                # Check kind
                if avail.get("kind") != inst_reqs.get("kind"):
                    continue

                # Check dimensionality
                if "dimensionality" in inst_reqs:
                    if avail.get("dimensionality") != inst_reqs["dimensionality"]:
                        continue

                # Check tags if specified
                if "tags" in inst_reqs:
                    avail_tags = set(avail.get("tags", []))
                    req_tags = set(inst_reqs["tags"])
                    if not req_tags.intersection(avail_tags):
                        continue

                # Found a match
                matched = True
                break

            if not matched:
                can_run = False
                break

        if can_run:
            matching_templates.append(template_key)

    return matching_templates
