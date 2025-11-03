"""Unit tests for embedder module."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from rag_core.config import Config
from rag_core.vectorizer.embedder import Embedder, EmbedderError


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        hf_endpoint_url="https://test-endpoint.example.com",
        hf_api_token="test-token",
        embed_model_id="test-model",
        request_timeout_seconds=10.0,
        max_concurrent_requests=5,
    )


@pytest.fixture
def config_no_endpoint() -> Config:
    """Create a config without explicit endpoint URL."""
    return Config(
        hf_api_token="test-token",
        embed_model_id="BAAI/bge-m3",
    )


class TestEmbedderInitialization:
    """Tests for Embedder initialization."""

    def test_init_with_config(self, config: Config) -> None:
        """Test initialization with config."""
        embedder = Embedder(config)
        assert embedder.endpoint_url == "https://test-endpoint.example.com"
        assert embedder.api_token == "test-token"
        assert embedder.model_id == "test-model"

    def test_init_with_overrides(self, config: Config) -> None:
        """Test initialization with parameter overrides."""
        embedder = Embedder(
            config,
            endpoint_url="https://override.example.com",
            api_token="override-token",
            model_id="override-model",
        )
        assert embedder.endpoint_url == "https://override.example.com"
        assert embedder.api_token == "override-token"
        assert embedder.model_id == "override-model"

    def test_init_without_endpoint_url(self, config_no_endpoint: Config) -> None:
        """Test initialization without explicit endpoint URL uses HF API."""
        embedder = Embedder(config_no_endpoint)
        assert embedder.endpoint_url == "https://api-inference.huggingface.co/models/BAAI/bge-m3"

    def test_embedding_dim_initially_none(self, config: Config) -> None:
        """Test that embedding_dim is None before first embedding."""
        embedder = Embedder(config)
        assert embedder.embedding_dim is None


class TestEmbedderConnection:
    """Tests for Embedder connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, config: Config) -> None:
        """Test that connect() creates HTTP client."""
        embedder = Embedder(config)
        assert embedder._client is None

        await embedder.connect()
        assert embedder._client is not None
        assert isinstance(embedder._client, httpx.AsyncClient)

        await embedder.close()

    @pytest.mark.asyncio
    async def test_connect_sets_authorization_header(self, config: Config) -> None:
        """Test that API token is set in Authorization header."""
        embedder = Embedder(config)
        await embedder.connect()

        assert embedder._client is not None
        assert "Authorization" in embedder._client.headers
        assert embedder._client.headers["Authorization"] == "Bearer test-token"

        await embedder.close()

    @pytest.mark.asyncio
    async def test_close_removes_client(self, config: Config) -> None:
        """Test that close() removes client."""
        embedder = Embedder(config)
        await embedder.connect()
        assert embedder._client is not None

        await embedder.close()
        assert embedder._client is None

    @pytest.mark.asyncio
    async def test_context_manager(self, config: Config) -> None:
        """Test async context manager."""
        async with Embedder(config) as embedder:
            assert embedder._client is not None

        assert embedder._client is None

    @pytest.mark.asyncio
    async def test_operations_without_connect_raise_error(self, config: Config) -> None:
        """Test that operations without connect() raise error."""
        embedder = Embedder(config)

        with pytest.raises(EmbedderError, match="not connected"):
            await embedder.embed_batch(["test"])


class TestEmbedderEmbedding:
    """Tests for embedding generation."""

    @pytest.mark.asyncio
    async def test_embed_batch_success(self, config: Config) -> None:
        """Test successful batch embedding."""
        embedder = Embedder(config)
        await embedder.connect()

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            result = await embedder.embed_batch(["text1", "text2"])

            assert len(result) == 2
            assert result[0] == [0.1, 0.2, 0.3]
            assert result[1] == [0.4, 0.5, 0.6]

            # Verify request
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["inputs"] == ["text1", "text2"]
            assert call_kwargs["json"]["normalize"] is True

        await embedder.close()

    @pytest.mark.asyncio
    async def test_embed_batch_wrapped_format(self, config: Config) -> None:
        """Test batch embedding with wrapped response format."""
        embedder = Embedder(config)
        await embedder.connect()

        # Mock response with embeddings key
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embeddings": [
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
            ]
        }

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            result = await embedder.embed_batch(["text1", "text2"])

            assert len(result) == 2
            assert result[0] == [0.1, 0.2, 0.3]

        await embedder.close()

    @pytest.mark.asyncio
    async def test_embed_single_text(self, config: Config) -> None:
        """Test single text embedding."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3]]

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            result = await embedder.embed("test text")

            assert result == [0.1, 0.2, 0.3]

        await embedder.close()

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self, config: Config) -> None:
        """Test embedding empty list returns empty list."""
        embedder = Embedder(config)
        await embedder.connect()

        result = await embedder.embed_batch([])

        assert result == []

        await embedder.close()

    @pytest.mark.asyncio
    async def test_embed_batch_sets_dimension(self, config: Config) -> None:
        """Test that embedding dimension is cached after first call."""
        embedder = Embedder(config)
        await embedder.connect()

        assert embedder.embedding_dim is None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3, 0.4]]

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            await embedder.embed_batch(["test"])

            assert embedder.embedding_dim == 4

        await embedder.close()

    @pytest.mark.asyncio
    async def test_embed_batch_normalize_parameter(self, config: Config) -> None:
        """Test normalize parameter is passed correctly."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3]]

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            await embedder.embed_batch(["test"], normalize=False)

            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["normalize"] is False

        await embedder.close()


class TestEmbedderErrorHandling:
    """Tests for error handling and retries."""

    @pytest.mark.asyncio
    async def test_http_error_client_error(self, config: Config) -> None:
        """Test that 4xx errors are not retried."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response
            mock_post.return_value.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "400", request=MagicMock(), response=mock_response
                )
            )

            with pytest.raises(EmbedderError, match="HTTP 400"):
                await embedder.embed_batch(["test"], max_retries=3)

            # Should only be called once (no retries for 4xx)
            assert mock_post.call_count == 1

        await embedder.close()

    @pytest.mark.asyncio
    async def test_http_error_rate_limit_retry(self, config: Config) -> None:
        """Test that 429 errors are retried."""
        embedder = Embedder(config)
        await embedder.connect()

        call_count = 0

        async def mock_post_impl(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                # Fail first 2 attempts
                mock_response = MagicMock()
                mock_response.status_code = 429
                mock_response.text = "Rate Limited"
                mock_response.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "429", request=MagicMock(), response=mock_response
                    )
                )
                return mock_response
            else:
                # Succeed on 3rd attempt
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = [[0.1, 0.2, 0.3]]
                return mock_response

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
                mock_post.side_effect = mock_post_impl

                result = await embedder.embed_batch(["test"], max_retries=3)

                assert result == [[0.1, 0.2, 0.3]]
                assert call_count == 3

        await embedder.close()

    @pytest.mark.asyncio
    async def test_http_error_exhausted_retries(self, config: Config) -> None:
        """Test that error is raised after exhausting retries."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        # Need to patch asyncio.sleep to avoid actual delays
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
                mock_post.return_value = mock_response
                mock_post.return_value.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "500", request=MagicMock(), response=mock_response
                    )
                )

                with pytest.raises(EmbedderError, match="HTTP 500"):
                    await embedder.embed_batch(["test"], max_retries=3)

                assert mock_post.call_count == 3
                # Should sleep between retries: 1s and 2s (2 sleeps for 3 attempts)
                assert mock_sleep.call_count == 2

        await embedder.close()

    @pytest.mark.asyncio
    async def test_request_error_retry(self, config: Config) -> None:
        """Test that network errors are retried."""
        embedder = Embedder(config)
        await embedder.connect()

        call_count = 0

        async def mock_post_impl(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1

            if call_count < 2:
                raise httpx.RequestError("Network error")
            else:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = [[0.1, 0.2, 0.3]]
                return mock_response

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
                mock_post.side_effect = mock_post_impl

                result = await embedder.embed_batch(["test"], max_retries=3)

                assert result == [[0.1, 0.2, 0.3]]
                assert call_count == 2

        await embedder.close()

    @pytest.mark.asyncio
    async def test_unexpected_response_format(self, config: Config) -> None:
        """Test handling of unexpected response format."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            with pytest.raises(EmbedderError, match="Unexpected response format"):
                await embedder.embed_batch(["test"])

        await embedder.close()


class TestEmbedderHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, config: Config) -> None:
        """Test successful health check."""
        embedder = Embedder(config)
        await embedder.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3]]

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.return_value = mock_response

            result = await embedder.health_check()

            assert result is True

        await embedder.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, config: Config) -> None:
        """Test health check failure."""
        embedder = Embedder(config)
        await embedder.connect()

        with patch.object(embedder._client, "post", new_callable=AsyncMock) as mock_post:  # type: ignore
            mock_post.side_effect = httpx.RequestError("Network error")

            result = await embedder.health_check()

            assert result is False

        await embedder.close()
