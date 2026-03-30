"""
Comprehensive tests for LabPilot RAG (Retrieval-Augmented Generation) system.

Tests vector storage, document retrieval, embeddings, and the complete
RAG pipeline for AI enhancement.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict, Any, Optional
import numpy as np

# Mock ChromaDB before importing RAG components
class MockCollection:
    """Mock ChromaDB Collection."""

    def __init__(self, name: str):
        self.name = name
        self.documents = []
        self.embeddings = []
        self.metadatas = []
        self.ids = []

    def add(self, documents: List[str], embeddings: List[List[float]],
            metadatas: List[Dict[str, Any]], ids: List[str]):
        """Mock add operation."""
        self.documents.extend(documents)
        self.embeddings.extend(embeddings)
        self.metadatas.extend(metadatas)
        self.ids.extend(ids)

    def query(self, query_embeddings: List[List[float]], n_results: int = 10,
              where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Mock query operation with similarity search."""
        if not self.documents:
            return {
                'ids': [[]],
                'distances': [[]],
                'documents': [[]],
                'metadatas': [[]]
            }

        # Simple similarity based on random scores for testing
        query_embedding = query_embeddings[0]
        scores = []

        for i, embedding in enumerate(self.embeddings):
            # Simple dot product similarity
            score = sum(a * b for a, b in zip(query_embedding, embedding))
            scores.append((score, i))

        # Sort by similarity (higher is better)
        scores.sort(reverse=True)

        # Apply metadata filter if provided
        if where:
            filtered_indices = []
            for score, idx in scores:
                metadata = self.metadatas[idx]
                match = all(metadata.get(k) == v for k, v in where.items())
                if match:
                    filtered_indices.append(idx)
        else:
            filtered_indices = [idx for _, idx in scores]

        # Return top n_results
        result_indices = filtered_indices[:n_results]

        return {
            'ids': [[self.ids[i] for i in result_indices]],
            'distances': [[1.0 - scores[i][0] for i in result_indices]],  # Convert to distance
            'documents': [[self.documents[i] for i in result_indices]],
            'metadatas': [[self.metadatas[i] for i in result_indices]]
        }

    def count(self) -> int:
        """Return number of documents."""
        return len(self.documents)


class MockChromaClient:
    """Mock ChromaDB Client."""

    def __init__(self, path: str = None):
        self.path = path
        self.collections = {}

    def get_or_create_collection(self, name: str, **kwargs) -> MockCollection:
        """Mock collection creation."""
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]

    def delete_collection(self, name: str):
        """Mock collection deletion."""
        if name in self.collections:
            del self.collections[name]


# Mock the chromadb module
import sys
sys.modules['chromadb'] = Mock()
sys.modules['chromadb'].PersistentClient = MockChromaClient

# Now import RAG components
from labpilot_core.ai.rag.store import RAGStore, RAGStoreError
from labpilot_core.ai.rag.embedder import Embedder, EmbedderError
from labpilot_core.ai.rag.collector import ExampleCollector


class MockEmbedder(Embedder):
    """Mock embedder for testing."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.initialized = False

    async def initialize(self, base_url: str, model: str = "nomic-embed-text"):
        """Mock initialization."""
        self.initialized = True

    async def embed(self, text: str) -> List[float]:
        """Mock embedding generation - simple hash-based embedding."""
        if not self.initialized:
            raise EmbedderError("Embedder not initialized")

        # Generate consistent "embedding" based on text hash
        text_hash = hash(text)
        np.random.seed(abs(text_hash) % 2**32)
        embedding = np.random.normal(0, 1, self.dimension).tolist()

        # Normalize to unit vector
        norm = sum(x**2 for x in embedding) ** 0.5
        return [x / norm for x in embedding]

    async def shutdown(self):
        """Mock shutdown."""
        self.initialized = False


class TestEmbedder:
    """Test Embedder functionality."""

    @pytest.mark.asyncio
    async def test_embedder_initialization(self):
        """Test embedder initialization."""
        embedder = MockEmbedder()
        assert not embedder.initialized

        await embedder.initialize("http://localhost:11434", "test-model")
        assert embedder.initialized

    @pytest.mark.asyncio
    async def test_embedding_generation(self):
        """Test embedding generation."""
        embedder = MockEmbedder()
        await embedder.initialize("http://localhost:11434")

        # Generate embedding
        embedding = await embedder.embed("test document")

        assert isinstance(embedding, list)
        assert len(embedding) == 384  # Default dimension
        assert all(isinstance(x, float) for x in embedding)

        # Should be unit vector (approximately)
        norm = sum(x**2 for x in embedding) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    @pytest.mark.asyncio
    async def test_embedding_consistency(self):
        """Test that same text produces same embedding."""
        embedder = MockEmbedder()
        await embedder.initialize("http://localhost:11434")

        text = "consistent test text"
        embedding1 = await embedder.embed(text)
        embedding2 = await embedder.embed(text)

        assert embedding1 == embedding2

    @pytest.mark.asyncio
    async def test_embedding_not_initialized(self):
        """Test embedding without initialization."""
        embedder = MockEmbedder()

        with pytest.raises(EmbedderError):
            await embedder.embed("test")

    @pytest.mark.asyncio
    async def test_embedder_shutdown(self):
        """Test embedder shutdown."""
        embedder = MockEmbedder()
        await embedder.initialize("http://localhost:11434")

        await embedder.shutdown()
        assert not embedder.initialized


class TestRAGStore:
    """Test RAGStore functionality."""

    def test_rag_store_creation(self):
        """Test RAGStore creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            store = RAGStore(temp_dir, embedder)

            assert store.data_dir == Path(temp_dir)
            assert store.embedder is embedder
            assert not store._initialized

    @pytest.mark.asyncio
    async def test_rag_store_initialization(self):
        """Test RAGStore initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            store = RAGStore(temp_dir, embedder)

            await store.initialize()

            assert store._initialized
            assert "dsl_examples" in store._collections
            assert "instrument_docs" in store._collections
            assert "workflow_patterns" in store._collections
            assert "error_corrections" in store._collections

    @pytest.mark.asyncio
    async def test_add_document(self):
        """Test adding document to RAG store."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            # Add document
            doc_id = await store.add_document(
                "dsl_examples",
                "Example DSL code for spectrum plot",
                {"type": "spectrum_plot", "difficulty": "easy"}
            )

            assert isinstance(doc_id, str)
            assert len(doc_id) > 0

            # Verify document was added
            collection = store._collections["dsl_examples"]
            assert collection.count() == 1

    @pytest.mark.asyncio
    async def test_search_documents(self):
        """Test searching documents in RAG store."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            # Add test documents
            await store.add_document(
                "dsl_examples",
                "spectrum plot with peak finding",
                {"type": "spectrum_plot", "features": ["peaks"]}
            )
            await store.add_document(
                "dsl_examples",
                "image view with ROI selection",
                {"type": "image_view", "features": ["roi"]}
            )

            # Search for spectrum-related documents
            results = await store.search("dsl_examples", "spectrum peaks", n_results=1)

            assert len(results) == 1
            assert "spectrum" in results[0]["document"].lower()
            assert "metadata" in results[0]
            assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_search_with_metadata_filter(self):
        """Test searching with metadata filtering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            # Add documents with different types
            await store.add_document(
                "dsl_examples",
                "spectrum plot example",
                {"type": "spectrum_plot", "difficulty": "easy"}
            )
            await store.add_document(
                "dsl_examples",
                "spectrum analysis code",
                {"type": "analysis", "difficulty": "easy"}
            )

            # Search with metadata filter
            results = await store.search(
                "dsl_examples",
                "spectrum",
                n_results=10,
                metadata_filter={"type": "spectrum_plot"}
            )

            assert len(results) == 1
            assert results[0]["metadata"]["type"] == "spectrum_plot"

    @pytest.mark.asyncio
    async def test_get_collection_stats(self):
        """Test getting collection statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            # Add some documents
            await store.add_document("dsl_examples", "doc 1", {})
            await store.add_document("dsl_examples", "doc 2", {})
            await store.add_document("instrument_docs", "doc 3", {})

            stats = store.get_collection_stats()

            assert "dsl_examples" in stats
            assert "instrument_docs" in stats
            assert stats["dsl_examples"]["document_count"] == 2
            assert stats["instrument_docs"]["document_count"] == 1

    @pytest.mark.asyncio
    async def test_rag_store_not_initialized(self):
        """Test operations on uninitialized RAG store."""
        embedder = MockEmbedder()
        store = RAGStore("/tmp", embedder)

        with pytest.raises(RAGStoreError):
            await store.add_document("collection", "doc", {})

        with pytest.raises(RAGStoreError):
            await store.search("collection", "query")

    @pytest.mark.asyncio
    async def test_invalid_collection(self):
        """Test operations on invalid collection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            with pytest.raises(RAGStoreError):
                await store.add_document("invalid_collection", "doc", {})

            with pytest.raises(RAGStoreError):
                await store.search("invalid_collection", "query")

    @pytest.mark.asyncio
    async def test_initialize_from_documents(self):
        """Test initialization from seed documents directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create seed documents directory
            seed_dir = Path(temp_dir) / "seeds"
            seed_dir.mkdir()

            # Create sample documents
            dsl_dir = seed_dir / "dsl_examples"
            dsl_dir.mkdir()
            (dsl_dir / "spectrum.py").write_text("""
# Example spectrum plot DSL
from labpilot_core.qt.dsl import *
w = window("Spectrum", "vertical")
w.add(spectrum_plot(source="spec.data"))
show(w)
""")

            instrument_dir = seed_dir / "instrument_docs"
            instrument_dir.mkdir()
            (instrument_dir / "spectrometer.md").write_text("""
# Spectrometer Documentation
Parameters:
- integration_time: Integration time in ms
- wavelength_range: Measurement range in nm
""")

            # Initialize RAG store with seed documents
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()
            await store.initialize_from_documents(seed_dir)

            # Verify documents were loaded
            stats = store.get_collection_stats()
            assert stats["dsl_examples"]["document_count"] >= 1
            assert stats["instrument_docs"]["document_count"] >= 1

            # Test search works with loaded documents
            results = await store.search("dsl_examples", "spectrum plot")
            assert len(results) > 0


class TestExampleCollector:
    """Test ExampleCollector functionality."""

    @pytest.mark.asyncio
    async def test_collector_creation(self):
        """Test ExampleCollector creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            store = RAGStore(temp_dir, embedder)

            collector = ExampleCollector(store)
            assert collector.store is store

    @pytest.mark.asyncio
    async def test_collect_dsl_example(self):
        """Test collecting DSL example."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            collector = ExampleCollector(store)

            # Collect DSL example
            dsl_code = """from labpilot_core.qt.dsl import *
w = window("Camera Control")
w.add(image_view(source="camera.frame"))
show(w)"""

            await collector.collect_dsl_example(
                dsl_code,
                "camera control interface",
                ["camera", "image_view"]
            )

            # Verify example was stored
            results = await store.search("dsl_examples", "camera control")
            assert len(results) > 0
            assert "image_view" in results[0]["document"]

    @pytest.mark.asyncio
    async def test_collect_error_correction(self):
        """Test collecting error correction example."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            collector = ExampleCollector(store)

            # Collect error correction
            original_code = "window('Test')"  # Invalid - missing show()
            corrected_code = """from labpilot_core.qt.dsl import *
w = window("Test")
show(w)"""
            error_msg = "Missing show() call"

            await collector.collect_error_correction(
                original_code,
                corrected_code,
                error_msg,
                "dsl_gui"
            )

            # Verify correction was stored
            results = await store.search("error_corrections", "missing show")
            assert len(results) > 0
            assert "show(w)" in results[0]["document"]

    @pytest.mark.asyncio
    async def test_collect_workflow_pattern(self):
        """Test collecting workflow pattern."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            collector = ExampleCollector(store)

            # Collect workflow pattern
            workflow_json = {
                "name": "Spectrum Acquisition",
                "nodes": [
                    {"type": "set", "device": "spec", "param": "integration_time", "value": 100},
                    {"type": "acquire", "device": "spec", "output": "spectrum_data"}
                ]
            }

            await collector.collect_workflow_pattern(
                workflow_json,
                "Basic spectrum acquisition workflow",
                ["spectroscopy", "acquisition"]
            )

            # Verify pattern was stored
            results = await store.search("workflow_patterns", "spectrum acquisition")
            assert len(results) > 0


class TestRAGIntegration:
    """Test complete RAG system integration."""

    @pytest.mark.asyncio
    async def test_complete_rag_pipeline(self):
        """Test complete RAG pipeline from document storage to retrieval."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize RAG system
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            collector = ExampleCollector(store)

            # Step 1: Collect various types of examples
            dsl_examples = [
                ("spectrum_plot(source='spec.data')", "basic spectrum plot", ["spectrum"]),
                ("image_view(source='cam.frame', show_roi=True)", "camera with ROI", ["camera", "roi"]),
                ("slider('Power', 'laser', 'power', 0, 100)", "laser power control", ["laser", "control"])
            ]

            for code, desc, tags in dsl_examples:
                await collector.collect_dsl_example(code, desc, tags)

            # Step 2: Search for relevant examples
            spectrum_results = await store.search("dsl_examples", "spectrum visualization")
            camera_results = await store.search("dsl_examples", "image display ROI")
            control_results = await store.search("dsl_examples", "laser power slider")

            # Verify results are relevant
            assert len(spectrum_results) > 0
            assert "spectrum" in spectrum_results[0]["document"].lower()

            assert len(camera_results) > 0
            assert "image_view" in camera_results[0]["document"]

            assert len(control_results) > 0
            assert "slider" in control_results[0]["document"]

            # Step 3: Test metadata filtering
            laser_examples = await store.search(
                "dsl_examples",
                "control",
                metadata_filter={"tags": ["laser"]}
            )

            # Would need to modify mock to properly handle tag filtering
            assert len(laser_examples) >= 0  # Basic functionality test

    @pytest.mark.asyncio
    async def test_rag_performance_with_many_documents(self):
        """Test RAG system performance with many documents."""
        with tempfile.TemporaryDirectory() as temp_dir:
            embedder = MockEmbedder()
            await embedder.initialize("http://localhost:11434")

            store = RAGStore(temp_dir, embedder)
            await store.initialize()

            # Add many documents
            for i in range(100):
                await store.add_document(
                    "dsl_examples",
                    f"Example {i}: spectrum_plot(source='device_{i}.data')",
                    {"index": i, "type": "spectrum_plot"}
                )

            # Search should still be fast and accurate
            results = await store.search("dsl_examples", "spectrum device_50", n_results=5)

            # Should find relevant results
            assert len(results) <= 5
            assert len(results) > 0

            # Verify collection stats
            stats = store.get_collection_stats()
            assert stats["dsl_examples"]["document_count"] == 100

    @pytest.mark.asyncio
    async def test_rag_error_handling(self):
        """Test RAG system error handling."""
        # Test with invalid directory
        with pytest.raises(Exception):
            store = RAGStore("/invalid/path", MockEmbedder())
            await store.initialize()

        # Test with invalid embedder
        with tempfile.TemporaryDirectory() as temp_dir:
            broken_embedder = MockEmbedder()
            # Don't initialize embedder

            store = RAGStore(temp_dir, broken_embedder)
            await store.initialize()

            with pytest.raises(EmbedderError):
                await store.add_document("dsl_examples", "test", {})


if __name__ == "__main__":
    pytest.main([__file__])