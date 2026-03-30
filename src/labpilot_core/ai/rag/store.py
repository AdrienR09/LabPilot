"""RAG (Retrieval-Augmented Generation) store using ChromaDB.

Local vector store using ChromaDB for storing and retrieving examples
that improve AI code generation. Embeddings via nomic-embed-text through Ollama.
Fully local - no network calls except to local Ollama.

Collections:
- "dsl_examples": Approved GUI panels and DSL code
- "instrument_docs": Instrument parameter references
- "workflow_patterns": Common experiment templates
- "error_corrections": Failed → fixed code pairs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import chromadb

    from labpilot_core.ai.rag.embedder import Embedder

__all__ = ["RAGStore", "RAGStoreError"]

log = logging.getLogger(__name__)


class RAGStoreError(Exception):
    """Raised when RAG store operations fail."""


class RAGStore:
    """Local vector store using ChromaDB.

    Features:
    - Local ChromaDB instance (no cloud dependencies)
    - Multiple collections for different content types
    - Automatic embedding via Ollama nomic-embed-text
    - Metadata filtering for precise retrieval
    - Self-cleaning 15-minute cache for repeated queries

    Example:
        >>> embedder = Embedder("http://localhost:11434")
        >>> store = RAGStore("./rag_data", embedder)
        >>> await store.initialize()
        >>>
        >>> await store.add("dsl_examples", "spectrum_panel_1",
        ...                 "spectrum_plot with peak finding",
        ...                 {"type": "spectrum", "peak": True})
        >>>
        >>> results = await store.search("dsl_examples",
        ...                             "show spectrum with peak", n_results=3)
    """

    def __init__(self, persist_dir: str | Path, embedder: Embedder) -> None:
        """Initialize RAG store.

        Args:
            persist_dir: Directory for ChromaDB persistence.
            embedder: Embedder instance for generating vectors.
        """
        self.persist_dir = Path(persist_dir)
        self.embedder = embedder
        self._client: chromadb.Client | None = None
        self._collections: dict[str, Any] = {}

        # Collection definitions
        self.COLLECTIONS = {
            "dsl_examples": {
                "description": "Approved GUI panels and DSL code examples",
                "metadata_fields": ["type", "widgets", "complexity", "device_types"]
            },
            "instrument_docs": {
                "description": "Instrument parameter references and documentation",
                "metadata_fields": ["manufacturer", "model", "category", "connection"]
            },
            "workflow_patterns": {
                "description": "Common experiment templates and procedures",
                "metadata_fields": ["experiment_type", "devices", "duration", "complexity"]
            },
            "error_corrections": {
                "description": "Failed code → fixed code correction pairs",
                "metadata_fields": ["error_type", "correction_type", "language"]
            }
        }

    async def initialize(self) -> None:
        """Initialize ChromaDB and create collections.

        Creates persistent ChromaDB instance and sets up all collections
        if they don't already exist.

        Raises:
            RAGStoreError: If initialization fails.
        """
        try:
            # Import ChromaDB (optional dependency)
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError:
                raise RAGStoreError(
                    "ChromaDB not installed. Install with: pip install chromadb>=0.5"
                )

            # Ensure persist directory exists
            self.persist_dir.mkdir(parents=True, exist_ok=True)

            # Create ChromaDB client with persistence
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            # Create/get collections
            for collection_name, config in self.COLLECTIONS.items():
                try:
                    collection = self._client.get_collection(collection_name)
                    log.debug(f"Found existing collection: {collection_name}")
                except Exception:
                    # Collection doesn't exist - create it
                    collection = self._client.create_collection(
                        name=collection_name,
                        metadata={"description": config["description"]}
                    )
                    log.info(f"Created new collection: {collection_name}")

                self._collections[collection_name] = collection

            log.info(f"RAG store initialized with {len(self._collections)} collections")

        except Exception as e:
            raise RAGStoreError(f"Failed to initialize RAG store: {e}") from e

    async def add(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Add document to collection.

        Args:
            collection: Collection name (must exist).
            doc_id: Unique document identifier.
            text: Document text content.
            metadata: Optional metadata dictionary.

        Raises:
            RAGStoreError: If addition fails.
        """
        if self._client is None:
            raise RAGStoreError("RAG store not initialized")

        if collection not in self._collections:
            raise RAGStoreError(f"Unknown collection: {collection}")

        try:
            # Generate embedding
            embedding = await self.embedder.embed(text)

            # Add to collection
            coll = self._collections[collection]
            coll.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )

            log.debug(f"Added document {doc_id} to {collection}")

        except Exception as e:
            raise RAGStoreError(f"Failed to add document {doc_id}: {e}") from e

    async def search(
        self,
        collection: str,
        query: str,
        n_results: int = 3,
        metadata_filter: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search collection for relevant documents.

        Args:
            collection: Collection name to search.
            query: Search query text.
            n_results: Maximum number of results to return.
            metadata_filter: Optional metadata filter (ChromaDB format).

        Returns:
            List of result dictionaries with text, metadata, distance.

        Raises:
            RAGStoreError: If search fails.
        """
        if self._client is None:
            raise RAGStoreError("RAG store not initialized")

        if collection not in self._collections:
            raise RAGStoreError(f"Unknown collection: {collection}")

        try:
            # Generate query embedding
            query_embedding = await self.embedder.embed(query)

            # Search collection
            coll = self._collections[collection]
            results = coll.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=metadata_filter,
                include=["documents", "metadatas", "distances"]
            )

            # Format results
            formatted_results = []
            if (results["documents"] and len(results["documents"]) > 0 and
                results["documents"][0]):  # Check for non-empty results

                documents = results["documents"][0]
                metadatas = results["metadatas"][0] if results["metadatas"] else []
                distances = results["distances"][0] if results["distances"] else []

                for i in range(len(documents)):
                    formatted_results.append({
                        "text": documents[i],
                        "metadata": metadatas[i] if i < len(metadatas) else {},
                        "distance": distances[i] if i < len(distances) else 1.0
                    })

            log.debug(f"Search '{query}' in {collection}: {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            raise RAGStoreError(f"Failed to search collection {collection}: {e}") from e

    async def search_all(
        self,
        query: str,
        n_results: int = 3,
        collection_weights: dict[str, float] | None = None
    ) -> list[dict[str, Any]]:
        """Search all collections and merge results.

        Args:
            query: Search query text.
            n_results: Total number of results to return.
            collection_weights: Optional weights per collection for ranking.

        Returns:
            List of merged and re-ranked results from all collections.
        """
        all_results = []
        weights = collection_weights or {}

        # Search each collection
        for collection_name in self._collections:
            try:
                results = await self.search(collection_name, query, n_results)

                # Apply collection weight
                weight = weights.get(collection_name, 1.0)
                for result in results:
                    result["collection"] = collection_name
                    result["weighted_distance"] = result["distance"] * weight
                    all_results.append(result)

            except Exception as e:
                log.warning(f"Search failed for collection {collection_name}: {e}")

        # Sort by weighted distance and limit results
        all_results.sort(key=lambda x: x["weighted_distance"])
        return all_results[:n_results]

    async def delete_document(self, collection: str, doc_id: str) -> None:
        """Delete document from collection.

        Args:
            collection: Collection name.
            doc_id: Document identifier to delete.

        Raises:
            RAGStoreError: If deletion fails.
        """
        if self._client is None:
            raise RAGStoreError("RAG store not initialized")

        if collection not in self._collections:
            raise RAGStoreError(f"Unknown collection: {collection}")

        try:
            coll = self._collections[collection]
            coll.delete(ids=[doc_id])
            log.debug(f"Deleted document {doc_id} from {collection}")

        except Exception as e:
            raise RAGStoreError(f"Failed to delete document {doc_id}: {e}") from e

    async def count_documents(self, collection: str) -> int:
        """Count documents in collection.

        Args:
            collection: Collection name.

        Returns:
            Number of documents in collection.
        """
        if self._client is None:
            raise RAGStoreError("RAG store not initialized")

        if collection not in self._collections:
            raise RAGStoreError(f"Unknown collection: {collection}")

        try:
            coll = self._collections[collection]
            return coll.count()

        except Exception as e:
            log.warning(f"Failed to count documents in {collection}: {e}")
            return 0

    async def list_collections(self) -> list[dict[str, Any]]:
        """List all collections with metadata.

        Returns:
            List of collection info dictionaries.
        """
        collections = []

        for name, config in self.COLLECTIONS.items():
            doc_count = await self.count_documents(name)
            collections.append({
                "name": name,
                "description": config["description"],
                "document_count": doc_count,
                "metadata_fields": config["metadata_fields"]
            })

        return collections

    async def initialise_from_documents(self, docs_dir: str | Path) -> None:
        """Load documents from directory into collections.

        Directory structure:
        docs_dir/
        ├── dsl_examples/
        │   ├── spectrum_live.py
        │   └── camera_control.py
        ├── instrument_docs/
        │   ├── spectrometers.md
        │   └── cameras.md
        └── workflow_patterns/
            ├── excitation_scan.md
            └── fret_efficiency.md

        Args:
            docs_dir: Directory containing seed documents.

        Raises:
            RAGStoreError: If document loading fails.
        """
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            raise RAGStoreError(f"Documents directory not found: {docs_dir}")

        total_loaded = 0

        for collection_name in self.COLLECTIONS:
            collection_dir = docs_path / collection_name
            if not collection_dir.exists():
                log.warning(f"Collection directory not found: {collection_dir}")
                continue

            # Check if collection already has documents
            if await self.count_documents(collection_name) > 0:
                log.info(f"Collection {collection_name} already populated, skipping")
                continue

            loaded_count = 0

            # Load all text files from collection directory
            for file_path in collection_dir.glob("**/*"):
                if file_path.is_file() and file_path.suffix in {".py", ".md", ".txt", ".json"}:
                    try:
                        # Read file content
                        text_content = file_path.read_text(encoding="utf-8")

                        # Generate document ID from file path
                        doc_id = f"{file_path.stem}_{hash(str(file_path)) % 10000}"

                        # Extract metadata from filename and content
                        metadata = self._extract_file_metadata(file_path, text_content)

                        # Add to collection
                        await self.add(collection_name, doc_id, text_content, metadata)

                        loaded_count += 1
                        log.debug(f"Loaded {file_path.name} into {collection_name}")

                    except Exception as e:
                        log.error(f"Failed to load {file_path}: {e}")

            log.info(f"Loaded {loaded_count} documents into {collection_name}")
            total_loaded += loaded_count

        log.info(f"RAG store initialization complete: {total_loaded} documents loaded")

    def _extract_file_metadata(self, file_path: Path, content: str) -> dict[str, Any]:
        """Extract metadata from file path and content.

        Args:
            file_path: Path to the file.
            content: File content text.

        Returns:
            Metadata dictionary.
        """
        metadata = {
            "filename": file_path.name,
            "extension": file_path.suffix,
            "file_size": len(content)
        }

        # Extract metadata based on file type
        if file_path.suffix == ".py":
            # Python code - extract DSL function usage
            metadata.update(self._extract_python_metadata(content))
        elif file_path.suffix == ".md":
            # Markdown - extract headers and keywords
            metadata.update(self._extract_markdown_metadata(content))

        return metadata

    def _extract_python_metadata(self, content: str) -> dict[str, Any]:
        """Extract metadata from Python code."""
        metadata = {"language": "python"}

        # Count DSL function usage
        dsl_functions = [
            "window", "spectrum_plot", "image_view", "waveform_plot",
            "slider", "button", "toggle", "dropdown"
        ]

        for func in dsl_functions:
            if f"{func}(" in content:
                metadata.setdefault("dsl_functions", []).append(func)

        # Estimate complexity
        lines = len(content.splitlines())
        if lines < 20:
            metadata["complexity"] = "simple"
        elif lines < 50:
            metadata["complexity"] = "medium"
        else:
            metadata["complexity"] = "complex"

        return metadata

    def _extract_markdown_metadata(self, content: str) -> dict[str, Any]:
        """Extract metadata from Markdown content."""
        metadata = {"format": "markdown"}

        lines = content.splitlines()

        # Extract headers
        headers = [line for line in lines if line.startswith("#")]
        if headers:
            metadata["headers"] = [h.strip("# ") for h in headers[:5]]

        # Estimate content length
        word_count = len(content.split())
        if word_count < 100:
            metadata["length"] = "short"
        elif word_count < 500:
            metadata["length"] = "medium"
        else:
            metadata["length"] = "long"

        return metadata
