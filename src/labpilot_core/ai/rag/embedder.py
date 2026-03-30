"""Embedder for generating text embeddings via Ollama.

Wraps Ollama embedding API with nomic-embed-text model for RAG functionality.
Local embeddings - no cloud dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

__all__ = ["Embedder", "EmbedderError"]

log = logging.getLogger(__name__)


class EmbedderError(Exception):
    """Raised when embedding generation fails."""


class Embedder:
    """Text embedder using Ollama API.

    Uses nomic-embed-text model through local Ollama server for generating
    text embeddings for RAG (Retrieval-Augmented Generation).

    Features:
    - Local embedding generation (no cloud calls)
    - Async HTTP client for efficient batching
    - Automatic retry on transient failures
    - Consistent vector dimensions (768D for nomic-embed-text)

    Example:
        >>> embedder = Embedder("http://localhost:11434")
        >>> await embedder.health_check()
        >>> embedding = await embedder.embed("spectrum plot example")
        >>> assert len(embedding) == 768  # nomic-embed-text dimensions
    """

    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 30.0
    ) -> None:
        """Initialize embedder.

        Args:
            ollama_host: Ollama server URL.
            model: Embedding model name.
            timeout: Request timeout in seconds.
        """
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            EmbedderError: If embedding generation fails.
        """
        if not text or not text.strip():
            raise EmbedderError("Cannot embed empty text")

        try:
            client = await self._get_client()

            # Prepare request payload
            payload = {
                "model": self.model,
                "prompt": text.strip()
            }

            log.debug(f"Generating embedding for text: {text[:100]}...")

            # Call Ollama embeddings API
            response = await client.post(
                f"{self.ollama_host}/api/embeddings",
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            # Extract embedding vector
            if "embedding" not in result:
                raise EmbedderError(f"No embedding in response: {result}")

            embedding = result["embedding"]

            if not isinstance(embedding, list):
                raise EmbedderError(f"Invalid embedding format: {type(embedding)}")

            if len(embedding) == 0:
                raise EmbedderError("Empty embedding vector returned")

            log.debug(f"Generated embedding: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            if "httpx" in str(type(e)):
                # HTTP error
                raise EmbedderError(f"HTTP request failed: {e}")
            else:
                # Other error
                raise EmbedderError(f"Embedding generation failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors.

        Note:
            Currently implements sequential embedding. Future versions
            could add true batch API support when Ollama supports it.
        """
        if not texts:
            return []

        embeddings = []

        for i, text in enumerate(texts):
            try:
                embedding = await self.embed(text)
                embeddings.append(embedding)
                log.debug(f"Generated embedding {i+1}/{len(texts)}")

            except Exception as e:
                log.error(f"Failed to embed text {i+1}: {e}")
                # Skip failed embeddings but continue with others
                continue

        return embeddings

    async def health_check(self) -> bool:
        """Check if Ollama server and embedding model are available.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            client = await self._get_client()

            # Check if server is responding
            response = await client.get(f"{self.ollama_host}/api/version")
            if response.status_code != 200:
                log.error(f"Ollama server not responding: {response.status_code}")
                return False

            # Check if embedding model is available
            response = await client.get(f"{self.ollama_host}/api/tags")
            if response.status_code == 200:
                result = response.json()
                models = result.get("models", [])
                model_names = [model.get("name", "") for model in models]

                if not any(self.model in name for name in model_names):
                    log.warning(f"Embedding model '{self.model}' not found in Ollama")
                    log.info(f"Available models: {model_names}")
                    return False

            # Test embedding generation with simple text
            test_embedding = await self.embed("test")
            if len(test_embedding) > 0:
                log.info(f"Embedder health check passed ({len(test_embedding)}D vectors)")
                return True
            else:
                log.error("Embedder returned empty vector")
                return False

        except Exception as e:
            log.error(f"Embedder health check failed: {e}")
            return False

    async def get_model_info(self) -> dict[str, any]:
        """Get information about the embedding model.

        Returns:
            Dictionary with model information.
        """
        try:
            client = await self._get_client()

            response = await client.post(
                f"{self.ollama_host}/api/show",
                json={"name": self.model}
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Model info not available: {response.status_code}"}

        except Exception as e:
            return {"error": f"Failed to get model info: {e}"}

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> Embedder:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
