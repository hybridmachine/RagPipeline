"""Unit tests for batch_processor module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from rag_core.config import Config
from rag_core.vectorizer.batch_processor import (
    BatchProcessor,
    embed_texts_batch,
)
from rag_core.vectorizer.embedder import Embedder


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        hf_endpoint_url="https://test-endpoint.example.com",
        hf_api_token="test-token",
        embed_model_id="test-model",
        embedding_batch_size=2,
        max_concurrent_requests=2,
    )


@pytest.fixture
def mock_embedder(config: Config) -> Embedder:
    """Create a mock embedder."""
    # Create a mock instead of real embedder
    mock = Mock(spec=Embedder)
    mock.config = config
    mock.embed_batch = AsyncMock()
    return mock  # type: ignore


class TestBatchCreation:
    """Tests for batch creation."""

    def test_create_batches_empty_list(self, config: Config, mock_embedder: Embedder) -> None:
        """Test creating batches from empty list."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)
        batches = processor.create_batches([])
        assert batches == []

    def test_create_batches_single_batch(self, config: Config, mock_embedder: Embedder) -> None:
        """Test creating single batch."""
        processor = BatchProcessor(mock_embedder, config, batch_size=5)
        items = [1, 2, 3]
        batches = processor.create_batches(items)
        assert len(batches) == 1
        assert batches[0] == [1, 2, 3]

    def test_create_batches_multiple_batches(self, config: Config, mock_embedder: Embedder) -> None:
        """Test creating multiple batches."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)
        items = [1, 2, 3, 4, 5]
        batches = processor.create_batches(items)
        assert len(batches) == 3
        assert batches[0] == [1, 2]
        assert batches[1] == [3, 4]
        assert batches[2] == [5]

    def test_create_batches_exact_multiple(self, config: Config, mock_embedder: Embedder) -> None:
        """Test creating batches when items are exact multiple of batch size."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)
        items = [1, 2, 3, 4]
        batches = processor.create_batches(items)
        assert len(batches) == 2
        assert batches[0] == [1, 2]
        assert batches[1] == [3, 4]

    def test_batch_size_override(self, config: Config, mock_embedder: Embedder) -> None:
        """Test that batch_size parameter overrides config."""
        processor = BatchProcessor(mock_embedder, config, batch_size=3)
        assert processor.batch_size == 3

        items = list(range(10))
        batches = processor.create_batches(items)
        assert len(batches) == 4
        assert batches[0] == [0, 1, 2]


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.mark.asyncio
    async def test_process_batches_empty_list(self, config: Config, mock_embedder: Embedder) -> None:
        """Test processing empty list."""
        processor = BatchProcessor(mock_embedder, config)
        result = await processor.process_batches([])
        assert result == []

    @pytest.mark.asyncio
    async def test_process_batches_single_batch(self, config: Config, mock_embedder: Embedder) -> None:
        """Test processing single batch."""
        processor = BatchProcessor(mock_embedder, config, batch_size=5)

        mock_embeddings = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]

        mock_embedder.embed_batch.return_value = mock_embeddings  # type: ignore

        texts = ["text1", "text2"]
        result = await processor.process_batches(texts)

        assert result == mock_embeddings
        mock_embedder.embed_batch.assert_called_once_with(texts, normalize=True)  # type: ignore

    @pytest.mark.asyncio
    async def test_process_batches_multiple_batches(self, config: Config, mock_embedder: Embedder) -> None:
        """Test processing multiple batches."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)

        # Mock different embeddings for each batch
        batch_results = {
            0: [[0.1, 0.2], [0.3, 0.4]],  # First batch
            1: [[0.5, 0.6], [0.7, 0.8]],  # Second batch
            2: [[0.9, 1.0]],               # Third batch
        }

        call_count = 0

        async def mock_embed_batch(texts: list[str], normalize: bool = True) -> list[list[float]]:
            nonlocal call_count
            # Determine batch index based on texts
            if texts == ["text1", "text2"]:
                batch_idx = 0
            elif texts == ["text3", "text4"]:
                batch_idx = 1
            else:  # ["text5"]
                batch_idx = 2

            call_count += 1
            return batch_results[batch_idx]

        mock_embedder.embed_batch.side_effect = mock_embed_batch  # type: ignore

        texts = ["text1", "text2", "text3", "text4", "text5"]
        result = await processor.process_batches(texts)

        # Results should be flattened and in order
        assert len(result) == 5
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]
        assert result[2] == [0.5, 0.6]
        assert result[3] == [0.7, 0.8]
        assert result[4] == [0.9, 1.0]

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_process_batches_normalize_parameter(self, config: Config, mock_embedder: Embedder) -> None:
        """Test that normalize parameter is passed through."""
        processor = BatchProcessor(mock_embedder, config)

        mock_embedder.embed_batch.return_value = [[0.1, 0.2, 0.3]]  # type: ignore

        await processor.process_batches(["text"], normalize=False)

        mock_embedder.embed_batch.assert_called_once()  # type: ignore
        call_kwargs = mock_embedder.embed_batch.call_args[1]  # type: ignore
        assert call_kwargs["normalize"] is False

    @pytest.mark.asyncio
    async def test_process_batches_progress_callback(self, config: Config, mock_embedder: Embedder) -> None:
        """Test progress callback is called correctly."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)

        progress_calls = []

        def progress_callback(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        mock_embedder.embed_batch.return_value = [[0.1, 0.2]]  # type: ignore

        texts = ["text1", "text2", "text3"]
        await processor.process_batches(texts, progress_callback=progress_callback)

        # Should have 2 batches total
        assert len(progress_calls) == 2
        # Check that we got progress updates
        assert (1, 2) in progress_calls or (2, 2) in progress_calls


class TestProcessWithMetadata:
    """Tests for processing with metadata."""

    @pytest.mark.asyncio
    async def test_process_with_metadata_empty(self, config: Config, mock_embedder: Embedder) -> None:
        """Test processing empty list with metadata."""
        processor = BatchProcessor(mock_embedder, config)
        result = await processor.process_with_metadata([])
        assert result == []

    @pytest.mark.asyncio
    async def test_process_with_metadata_preserves_order(self, config: Config, mock_embedder: Embedder) -> None:
        """Test that metadata is correctly paired with embeddings."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)

        mock_embeddings = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]

        # Return different embeddings for each batch
        call_count = 0

        async def mock_embed_side_effect(texts: list[str], normalize: bool = True) -> list[list[float]]:
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return [mock_embeddings[0], mock_embeddings[1]]
            else:
                return [mock_embeddings[2]]

        mock_embedder.embed_batch.side_effect = mock_embed_side_effect  # type: ignore

        items = [
            ("text1", {"id": 1}),
            ("text2", {"id": 2}),
            ("text3", {"id": 3}),
        ]
        result = await processor.process_with_metadata(items)

        assert len(result) == 3
        assert result[0] == ([0.1, 0.2, 0.3], {"id": 1})
        assert result[1] == ([0.4, 0.5, 0.6], {"id": 2})
        assert result[2] == ([0.7, 0.8, 0.9], {"id": 3})

    @pytest.mark.asyncio
    async def test_process_with_metadata_progress_callback(self, config: Config, mock_embedder: Embedder) -> None:
        """Test progress callback with metadata processing."""
        processor = BatchProcessor(mock_embedder, config, batch_size=2)

        progress_calls = []

        def progress_callback(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        mock_embedder.embed_batch.return_value = [[0.1, 0.2]]  # type: ignore

        items = [
            ("text1", 1),
            ("text2", 2),
            ("text3", 3),
        ]
        await processor.process_with_metadata(items, progress_callback=progress_callback)

        assert len(progress_calls) == 2


class TestEmbedTextsBatch:
    """Tests for convenience function."""

    @pytest.mark.asyncio
    async def test_embed_texts_batch_basic(self, config: Config) -> None:
        """Test basic usage of convenience function."""
        mock_embeddings = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]

        with patch("rag_core.vectorizer.batch_processor.Embedder") as MockEmbedder:
            mock_embedder_instance = AsyncMock()
            mock_embedder_instance.embed_batch = AsyncMock(return_value=mock_embeddings)

            # Setup context manager
            mock_embedder_instance.__aenter__ = AsyncMock(return_value=mock_embedder_instance)
            mock_embedder_instance.__aexit__ = AsyncMock(return_value=None)

            MockEmbedder.return_value = mock_embedder_instance

            texts = ["text1", "text2"]
            result = await embed_texts_batch(texts, config)

            assert result == mock_embeddings
            MockEmbedder.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_texts_batch_with_overrides(self, config: Config) -> None:
        """Test convenience function with parameter overrides."""
        with patch("rag_core.vectorizer.batch_processor.Embedder") as MockEmbedder:
            mock_embedder_instance = AsyncMock()
            mock_embedder_instance.embed_batch = AsyncMock(return_value=[[0.1, 0.2]])

            mock_embedder_instance.__aenter__ = AsyncMock(return_value=mock_embedder_instance)
            mock_embedder_instance.__aexit__ = AsyncMock(return_value=None)

            MockEmbedder.return_value = mock_embedder_instance

            await embed_texts_batch(
                ["text"],
                config,
                endpoint_url="https://custom.example.com",
                api_token="custom-token",
                model_id="custom-model",
                batch_size=10,
                normalize=False,
            )

            # Verify Embedder was called with overrides
            call_kwargs = MockEmbedder.call_args[1]
            assert call_kwargs["endpoint_url"] == "https://custom.example.com"
            assert call_kwargs["api_token"] == "custom-token"
            assert call_kwargs["model_id"] == "custom-model"

            # Verify embed_batch was called with normalize=False
            embed_call_kwargs = mock_embedder_instance.embed_batch.call_args[1]
            assert embed_call_kwargs["normalize"] is False

    @pytest.mark.asyncio
    async def test_embed_texts_batch_empty_list(self, config: Config) -> None:
        """Test convenience function with empty list."""
        with patch("rag_core.vectorizer.batch_processor.Embedder") as MockEmbedder:
            mock_embedder_instance = AsyncMock()
            mock_embedder_instance.embed_batch = AsyncMock(return_value=[])

            mock_embedder_instance.__aenter__ = AsyncMock(return_value=mock_embedder_instance)
            mock_embedder_instance.__aexit__ = AsyncMock(return_value=None)

            MockEmbedder.return_value = mock_embedder_instance

            result = await embed_texts_batch([], config)

            assert result == []
