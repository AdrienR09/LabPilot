"""RAG (Retrieval-Augmented Generation) system for LabPilot.

This package provides vector storage and retrieval for improving AI code generation:

- RAGStore: ChromaDB-based vector store with multiple collections
- Embedder: nomic-embed-text via Ollama for local embeddings
- ExampleCollector: Automatic collection of approved examples
- Seed documents: Pre-built examples for immediate AI improvement

Collections:
- dsl_examples: Approved GUI panels and DSL code
- instrument_docs: Instrument parameter references
- workflow_patterns: Common experiment templates
- error_corrections: Failed → fixed code pairs

Usage:
    >>> from labpilot_core.ai.rag import RAGStore, Embedder
    >>> embedder = Embedder("http://localhost:11434")
    >>> store = RAGStore("./rag_data", embedder)
    >>> await store.initialize()
    >>> await store.initialise_from_documents("./seed_docs")
"""

from __future__ import annotations

__all__ = ["Embedder", "EmbedderError", "ExampleCollector", "RAGStore", "RAGStoreError"]

# Import components with error handling
try:
    from labpilot_core.ai.rag.collector import ExampleCollector
    from labpilot_core.ai.rag.embedder import Embedder, EmbedderError
    from labpilot_core.ai.rag.store import RAGStore, RAGStoreError
except ImportError:
    # ChromaDB or httpx not available
    RAGStore = None
    RAGStoreError = None
    Embedder = None
    EmbedderError = None
    ExampleCollector = None
