"""Example collector for building self-improving AI system.

Saves approved examples to RAG store and training data files.
Called automatically when user clicks "Approve" on AI-generated code.
Builds fine-tuning dataset over time with zero manual effort.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from labpilot_core.ai.rag.store import RAGStore

__all__ = ["ExampleCollector"]

log = logging.getLogger(__name__)


class ExampleCollector:
    """Saves approved examples to RAG store and training data.

    Features:
    - Automatic collection when user approves AI-generated code
    - Stores examples in RAG for immediate improvement
    - Builds JSONL training datasets for future fine-tuning
    - Contextual metadata for better retrieval
    - Zero manual curation required

    Example:
        >>> collector = ExampleCollector(rag_store, "./training_data")
        >>> await collector.on_gui_approved(
        ...     prompt="show me a spectrum plot",
        ...     dsl_code="w = window(...); w.add(spectrum_plot(...))",
        ...     device_context="spectrometer connected"
        ... )
    """

    def __init__(self, rag_store: RAGStore, training_dir: str | Path) -> None:
        """Initialize example collector.

        Args:
            rag_store: RAG store for immediate example storage.
            training_dir: Directory for training data files.
        """
        self.rag_store = rag_store
        self.training_dir = Path(training_dir)
        self.training_dir.mkdir(parents=True, exist_ok=True)

        # Training data files
        self.dsl_file = self.training_dir / "dsl_gui.jsonl"
        self.analyse_file = self.training_dir / "analyse_functions.jsonl"
        self.corrections_file = self.training_dir / "error_corrections.jsonl"

    async def on_gui_approved(
        self,
        prompt: str,
        dsl_code: str,
        device_context: str,
        user_feedback: str | None = None
    ) -> None:
        """Handle approval of AI-generated GUI code.

        Args:
            prompt: User's original request.
            dsl_code: Approved DSL code.
            device_context: Description of connected devices.
            user_feedback: Optional user feedback on the result.
        """
        try:
            timestamp = time.time()
            doc_id = f"gui_{int(timestamp)}_{hash(dsl_code) % 10000}"

            # Extract metadata from DSL code
            metadata = self._extract_dsl_metadata(dsl_code, device_context)
            metadata.update({
                "timestamp": timestamp,
                "prompt": prompt[:200],  # Truncated for metadata
                "type": "gui_panel",
                "approved": True,
                "user_feedback": user_feedback or ""
            })

            # Add to RAG store for immediate use
            await self.rag_store.add(
                collection="dsl_examples",
                doc_id=doc_id,
                text=f"Prompt: {prompt}\n\nCode:\n{dsl_code}",
                metadata=metadata
            )

            # Add to training dataset
            await self._append_training_data(
                self.dsl_file,
                {
                    "prompt": prompt,
                    "completion": dsl_code,
                    "context": device_context,
                    "metadata": metadata,
                    "timestamp": timestamp
                }
            )

            log.info(f"Collected GUI example: {doc_id}")

        except Exception as e:
            log.error(f"Failed to collect GUI example: {e}")

    async def on_analyse_approved(
        self,
        prompt: str,
        code: str,
        node_context: str,
        execution_result: dict | None = None
    ) -> None:
        """Handle approval of AI-generated analysis code.

        Args:
            prompt: User's original analysis request.
            code: Approved Python analysis function.
            node_context: Context of the workflow node.
            execution_result: Optional result from test execution.
        """
        try:
            timestamp = time.time()
            doc_id = f"analyse_{int(timestamp)}_{hash(code) % 10000}"

            # Extract metadata from analysis code
            metadata = self._extract_analysis_metadata(code, node_context)
            metadata.update({
                "timestamp": timestamp,
                "prompt": prompt[:200],
                "type": "analysis_function",
                "approved": True,
                "execution_success": execution_result is not None
            })

            # Add to RAG store
            await self.rag_store.add(
                collection="workflow_patterns",
                doc_id=doc_id,
                text=f"Analysis Request: {prompt}\n\nFunction:\n{code}",
                metadata=metadata
            )

            # Add to training dataset
            await self._append_training_data(
                self.analyse_file,
                {
                    "prompt": prompt,
                    "completion": code,
                    "context": node_context,
                    "result": execution_result,
                    "metadata": metadata,
                    "timestamp": timestamp
                }
            )

            log.info(f"Collected analysis example: {doc_id}")

        except Exception as e:
            log.error(f"Failed to collect analysis example: {e}")

    async def on_correction_saved(
        self,
        original_code: str,
        corrected_code: str,
        errors: list[str],
        correction_type: str
    ) -> None:
        """Handle saving of error corrections.

        Args:
            original_code: Original code that had errors.
            corrected_code: AI-corrected version.
            errors: List of validation errors.
            correction_type: Type of correction ("dsl_gui" or "analyse_function").
        """
        try:
            timestamp = time.time()
            doc_id = f"correction_{int(timestamp)}_{hash(original_code) % 10000}"

            # Create correction metadata
            metadata = {
                "timestamp": timestamp,
                "correction_type": correction_type,
                "error_count": len(errors),
                "error_types": self._categorize_errors(errors),
                "correction_success": len(corrected_code.strip()) > 0
            }

            # Format correction text
            correction_text = f"""Original (with errors):
{original_code}

Errors:
{chr(10).join(f"- {error}" for error in errors)}

Corrected:
{corrected_code}"""

            # Add to RAG store
            await self.rag_store.add(
                collection="error_corrections",
                doc_id=doc_id,
                text=correction_text,
                metadata=metadata
            )

            # Add to training dataset
            await self._append_training_data(
                self.corrections_file,
                {
                    "original": original_code,
                    "corrected": corrected_code,
                    "errors": errors,
                    "type": correction_type,
                    "metadata": metadata,
                    "timestamp": timestamp
                }
            )

            log.info(f"Collected correction example: {doc_id}")

        except Exception as e:
            log.error(f"Failed to collect correction: {e}")

    def _extract_dsl_metadata(self, dsl_code: str, device_context: str) -> dict[str, Any]:
        """Extract metadata from DSL code."""
        metadata = {"language": "dsl"}

        # Extract DSL functions used
        dsl_functions = [
            "window", "spectrum_plot", "image_view", "waveform_plot", "scatter_plot",
            "volume_view", "slider", "button", "toggle", "dropdown",
            "value_display", "text_display", "row", "column", "tabs"
        ]

        used_functions = []
        for func in dsl_functions:
            if f"{func}(" in dsl_code:
                used_functions.append(func)

        metadata["dsl_functions"] = used_functions

        # Categorize by primary widget type
        if any(f in used_functions for f in ["spectrum_plot", "image_view", "waveform_plot"]):
            metadata["category"] = "visualization"
        elif any(f in used_functions for f in ["slider", "button", "toggle", "dropdown"]):
            metadata["category"] = "control"
        else:
            metadata["category"] = "mixed"

        # Estimate complexity
        lines = len(dsl_code.splitlines())
        widget_count = len(used_functions)

        if lines < 10 and widget_count < 3:
            metadata["complexity"] = "simple"
        elif lines < 30 and widget_count < 6:
            metadata["complexity"] = "medium"
        else:
            metadata["complexity"] = "complex"

        # Extract device types from context
        device_keywords = ["camera", "spectrometer", "laser", "motor", "detector", "lockin"]
        detected_devices = [kw for kw in device_keywords if kw in device_context.lower()]
        if detected_devices:
            metadata["device_types"] = detected_devices

        return metadata

    def _extract_analysis_metadata(self, code: str, node_context: str) -> dict[str, Any]:
        """Extract metadata from analysis code."""
        metadata = {"language": "python", "type": "analysis"}

        # Extract imported libraries
        imports = []
        for line in code.splitlines():
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line)

        if imports:
            metadata["imports"] = imports[:5]  # Limit to first 5

        # Extract analysis type based on function content
        code_lower = code.lower()
        if any(term in code_lower for term in ["peak", "find_peaks", "argmax"]):
            metadata["analysis_type"] = "peak_finding"
        elif any(term in code_lower for term in ["fit", "curve_fit", "optimize"]):
            metadata["analysis_type"] = "curve_fitting"
        elif any(term in code_lower for term in ["mean", "std", "average", "statistics"]):
            metadata["analysis_type"] = "statistics"
        elif any(term in code_lower for term in ["fourier", "fft", "frequency"]):
            metadata["analysis_type"] = "spectral_analysis"
        else:
            metadata["analysis_type"] = "general"

        # Estimate complexity
        lines = len([line for line in code.splitlines() if line.strip()])
        if lines < 10:
            metadata["complexity"] = "simple"
        elif lines < 25:
            metadata["complexity"] = "medium"
        else:
            metadata["complexity"] = "complex"

        return metadata

    def _categorize_errors(self, errors: list[str]) -> list[str]:
        """Categorize error types for metadata."""
        categories = []

        for error in errors:
            error_lower = error.lower()
            if "syntax" in error_lower:
                categories.append("syntax")
            elif "import" in error_lower:
                categories.append("import")
            elif "source" in error_lower:
                categories.append("source_format")
            elif "show" in error_lower:
                categories.append("missing_show")
            elif "qt" in error_lower:
                categories.append("raw_qt")
            else:
                categories.append("other")

        return list(set(categories))  # Remove duplicates

    async def _append_training_data(self, file_path: Path, data: dict) -> None:
        """Append data to JSONL training file.

        Args:
            file_path: Path to JSONL file.
            data: Data dictionary to append.
        """
        try:
            # Ensure file exists
            file_path.touch(exist_ok=True)

            # Append as JSONL
            with file_path.open("a", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
                f.write("\n")

            log.debug(f"Appended training data to {file_path.name}")

        except Exception as e:
            log.error(f"Failed to append training data: {e}")

    async def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about collected examples.

        Returns:
            Dictionary with collection statistics.
        """
        stats = {}

        # Count documents in each RAG collection
        for collection in ["dsl_examples", "workflow_patterns", "error_corrections"]:
            try:
                count = await self.rag_store.count_documents(collection)
                stats[f"{collection}_count"] = count
            except Exception as e:
                log.warning(f"Failed to count {collection}: {e}")
                stats[f"{collection}_count"] = 0

        # Count training data files
        for file_path, name in [
            (self.dsl_file, "dsl_training"),
            (self.analyse_file, "analysis_training"),
            (self.corrections_file, "corrections_training")
        ]:
            try:
                if file_path.exists():
                    line_count = len(file_path.read_text().splitlines())
                    stats[f"{name}_count"] = line_count
                else:
                    stats[f"{name}_count"] = 0
            except Exception as e:
                log.warning(f"Failed to count {name}: {e}")
                stats[f"{name}_count"] = 0

        stats["total_examples"] = sum(
            v for k, v in stats.items() if k.endswith("_count")
        )

        return stats
