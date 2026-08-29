"""Auto-generated PyMeasure adapters for velleman instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.velleman classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.velleman.velleman_k8090 import VellemanK8090
except ImportError:
    VellemanK8090 = None

if VellemanK8090 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class VellemanK8090Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.velleman.velleman_k8090.VellemanK8090."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=VellemanK8090, resource=resource, name=name or "pymeasure_velleman_k8090", **kwargs)

    adapter_registry.register("pymeasure_velleman_k8090", VellemanK8090Adapter)

