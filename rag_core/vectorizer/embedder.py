"""Embedding generation using HuggingFace or OpenAI-compatible endpoints.

Supports:
- HuggingFace Inference API and Text Embeddings Inference (TEI)
- OpenAI-compatible embedding servers (LM Studio, vLLM, etc.)

Auto-detects endpoint format and handles retries, timeouts, and batch processing.
"""

import asyncio
import time
from typing import Optional

import httpx

from rag_core.config import Config


class EmbedderError(Exception):
    """Base exception for embedding generation errors."""

    pass


class Embedder:
    """Generate embeddings using HuggingFace or OpenAI-compatible endpoints.

    Supports:
    - HuggingFace Inference API (serverless)
    - HuggingFace Inference Endpoints (dedicated)
    - Text Embeddings Inference (TEI) servers
    - OpenAI-compatible servers (LM Studio, vLLM, etc.)

    Auto-detects endpoint format based on URL pattern (/v1/embeddings = OpenAI format).
    """

    def __init__(
        self,
        config: Config,
        endpoint_url: Optional[str] = None,
        api_token: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        """Initialize embedder.

        Args:
            config: Configuration instance
            endpoint_url: Override endpoint URL (from config if None)
            api_token: Override API token (from config if None)
            model_id: Override model ID (from config if None)
        """
        self.config = config
        self.endpoint_url = endpoint_url or config.hf_endpoint_url
        self.api_token = api_token or config.hf_api_token
        self.model_id = model_id or config.embed_model_id

        # If no endpoint URL, use HuggingFace Inference API
        if not self.endpoint_url:
            self.endpoint_url = (
                f"https://api-inference.huggingface.co/models/{self.model_id}"
            )

        self._client: Optional[httpx.AsyncClient] = None
        self._embedding_dim: Optional[int] = None

    async def __aenter__(self) -> "Embedder":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client."""
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout_seconds),
            headers=headers,
            limits=httpx.Limits(
                max_connections=self.config.max_concurrent_requests,
                max_keepalive_connections=self.config.max_concurrent_requests,
            ),
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get active client or raise error."""
        if self._client is None:
            raise EmbedderError("Embedder not connected. Use async context manager or call connect().")
        return self._client

    async def embed_batch(
        self,
        texts: list[str],
        normalize: bool = True,
        max_retries: int = 3,
    ) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed
            normalize: Whether to normalize embeddings to unit length
            max_retries: Maximum number of retry attempts

        Returns:
            List of embedding vectors

        Raises:
            EmbedderError: If embedding generation fails after retries
        """
        if not texts:
            return []

        client = self._get_client()

        # Prepare request payload based on endpoint type
        # OpenAI-compatible endpoints (LM Studio, etc.) use "input" + "model"
        # HuggingFace endpoints use "inputs" + "normalize"
        if "/v1/embeddings" in (self.endpoint_url or ""):
            # OpenAI-compatible format
            payload = {
                "input": texts,
                "model": self.model_id,
            }
        else:
            # HuggingFace format
            payload = {
                "inputs": texts,
                "normalize": normalize,
            }

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    self.endpoint_url or "",  # Should never be empty at this point
                    json=payload,
                )
                response.raise_for_status()

                result = response.json()

                # Handle different response formats
                # OpenAI: {"data": [{"embedding": [...]}, ...]}
                # HuggingFace TEI/Inference: [[...], [...]] or {"embeddings": [[...], [...]]}
                if isinstance(result, dict) and "data" in result:
                    # OpenAI-compatible format
                    embeddings = [item["embedding"] for item in result["data"]]
                elif isinstance(result, list):
                    # Direct list of embeddings (HuggingFace TEI)
                    embeddings = result
                elif isinstance(result, dict) and "embeddings" in result:
                    # Wrapped in embeddings key (HuggingFace Inference API)
                    embeddings = result["embeddings"]
                else:
                    raise EmbedderError(f"Unexpected response format: {result}")

                # Cache embedding dimension on first successful call
                if embeddings and self._embedding_dim is None:
                    self._embedding_dim = len(embeddings[0])

                return embeddings  # type: ignore

            except httpx.HTTPStatusError as e:
                last_error = e
                # Check if it's a rate limit or server error (retryable)
                if e.response.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                # Client errors (4xx except 429) are not retryable
                raise EmbedderError(
                    f"HTTP {e.response.status_code}: {e.response.text}"
                ) from e

            except httpx.RequestError as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise EmbedderError(f"Request failed: {e}") from e

            except Exception as e:
                raise EmbedderError(f"Unexpected error: {e}") from e

        # If we exhausted all retries
        raise EmbedderError(
            f"Failed after {max_retries} attempts. Last error: {last_error}"
        )

    async def embed(self, text: str, normalize: bool = True) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed
            normalize: Whether to normalize embedding to unit length

        Returns:
            Embedding vector

        Raises:
            EmbedderError: If embedding generation fails
        """
        result = await self.embed_batch([text], normalize=normalize)
        return result[0]

    @property
    def embedding_dim(self) -> Optional[int]:
        """Get embedding dimension (available after first successful embedding).

        Returns:
            Embedding dimension or None if not yet determined
        """
        return self._embedding_dim

    async def health_check(self) -> bool:
        """Check if the embedding endpoint is healthy.

        Returns:
            True if endpoint is responding, False otherwise
        """
        try:
            # Try to embed a test string
            await self.embed("test")
            return True
        except EmbedderError:
            return False
