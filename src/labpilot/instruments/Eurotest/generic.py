"""Auto-generated PyMeasure adapters for eurotest instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.eurotest classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.eurotest.eurotestHPP120256 import EurotestHPP120256
except ImportError:
    EurotestHPP120256 = None

if EurotestHPP120256 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class EurotestHPP120256Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.eurotest.eurotestHPP120256.EurotestHPP120256."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=EurotestHPP120256, resource=resource, name=name or "pymeasure_eurotest_h_p_p120256", **kwargs)

    adapter_registry.register("pymeasure_eurotest_h_p_p120256", EurotestHPP120256Adapter)

