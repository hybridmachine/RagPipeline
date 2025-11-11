"""Query and RAG embedding endpoints."""

import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, status

from rag_core.database.file_tracker import FileTracker
from rag_core.database.vector_store import VectorStore
from rag_core.logging_config import get_query_logger, get_embed_logger
from rag_core.llm.openai_client import OpenAIClient
from rag_core.projects.project_config import ProjectConfig
from rag_core.retrieval.query_engine import QueryEngine
from rag_core.scanner.chunker import Chunker, ChunkStrategy
from rag_core.scanner.file_scanner import FileScanner
from rag_core.vectorizer.embedder import Embedder
from web.dependencies import get_current_project, get_current_user
from web.models import (
    CitationReference,
    EmbedRequest,
    EmbedResponse,
    QueryRequest,
    QueryResponse,
)


router = APIRouter()


@router.post("/{project_id}/query", response_model=QueryResponse)
async def query_project(
    project_id: str,
    request: QueryRequest,
    user_id: str = Depends(get_current_user),
    project: ProjectConfig = Depends(get_current_project),
) -> QueryResponse:
    """Execute a RAG query against a project.

    Embeds query, searches vectors, retrieves context, and generates answer via LLM.

    Args:
        project_id: Project ID.
        request: Query request containing query text and optional parameters.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        Query result with answer and citations.

    Raises:
        HTTPException: If query fails.
    """
    query_logger = get_query_logger(project_id=project_id)
    span_id: str | None = None
    start_time = time.perf_counter()

    try:
        # Initialize query logger with project context
        span_id = query_logger.log_query_start(request.query, user_id=user_id)

        # Convert project config to core config
        config = project.to_core_config()

        # Initialize components
        query_engine = QueryEngine(config)

        # Execute RAG query (embedding + vector search)
        query_result = await query_engine.query(
            query_text=request.query,
            k=request.k,
            rerank_top_n=request.rerank,
            project_id=project_id,
            user_id=user_id,
        )

        # Log retrieved chunks
        chunks_for_log = [
            {
                "doc_path": c.doc_path,
                "chunk_id": c.chunk_id,
                "score": c.score,
                "text": c.text,
            }
            for c in query_result.citations
        ]
        search_time_ms = (time.perf_counter() - start_time) * 1000
        query_logger.log_retrieved_chunks(span_id, chunks_for_log, search_time_ms)

        # Generate answer using LLM
        llm_start = time.perf_counter()
        openai_client = OpenAIClient(config)

        answer = await openai_client.generate_answer(
            query_text=request.query,
            context=query_result.context,
            citations=query_result.citations,
        )

        llm_time_ms = (time.perf_counter() - llm_start) * 1000

        # Log answer generation
        query_logger.log_answer(
            span_id,
            answer=answer.text,
            model=answer.model,
            total_tokens=answer.total_tokens,
            llm_time_ms=llm_time_ms,
        )

        # Close query engine
        await query_engine.close()

        # Convert citations to response model
        citations = [
            CitationReference(
                path=c.doc_path,
                chunk_id=c.chunk_id,
                text=c.text,
            )
            for c in answer.citations
        ]

        elapsed_seconds = time.perf_counter() - start_time

        return QueryResponse(
            answer=answer.text,
            citations=citations,
            num_retrieved=query_result.total_chunks,
            elapsed_seconds=elapsed_seconds,
        )

    except Exception as e:
        if span_id:
            query_logger.log_error(span_id, f"Query failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}",
        )


@router.post("/{project_id}/embed", response_model=EmbedResponse)
async def embed_project(
    project_id: str,
    request: EmbedRequest,
    user_id: str = Depends(get_current_user),
    project: ProjectConfig = Depends(get_current_project),
) -> EmbedResponse:
    """Generate embeddings for pending chunks in a project.

    Scans project files, chunks them, generates embeddings, and stores vectors.

    Args:
        project_id: Project ID.
        request: Embedding request.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        Embedding generation result with counts and elapsed time.

    Raises:
        HTTPException: If embedding fails.
    """
    start_time = time.perf_counter()
    embed_logger = get_embed_logger(project_id=project_id)
    span_id = embed_logger.log_embed_start(user_id=user_id)

    # Initialize components outside try block for cleanup in finally
    config = project.to_core_config()
    file_scanner = FileScanner(config)
    chunker = Chunker(config, strategy=ChunkStrategy.RECURSIVE)
    embedder = Embedder(config)
    vector_store = VectorStore(config)
    file_tracker = FileTracker(config.db_path)

    try:
        # Connect to vector store
        vector_store.connect()

        # Connect file tracker
        file_tracker.connect()

        # Connect embedder
        await embedder.connect()

        # Scan project files directory
        files_dir = project.data_dir / "files"
        scanned_files = await file_scanner.scan_directory(
            root=files_dir,
            tracker=file_tracker,
            limit=config.max_files_per_run
        )

        # Filter for changed files
        changed_files = [f for f in scanned_files if f.is_changed]

        total_chunks = 0
        embedded_chunks = 0
        processed_files = 0

        # Process each changed file
        for scanned_file in changed_files:
            file_path = str(scanned_file.relative_path)
            file_size = scanned_file.size_bytes

            # Read file content
            try:
                content = scanned_file.absolute_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError) as e:
                embed_logger.log_file_error(
                    span_id, file_path, f"Failed to read file: {e}"
                )
                continue

            # Chunk the file
            chunks = chunker.chunk(
                content, doc_path=scanned_file.relative_path
            )

            chunk_count = len(chunks)
            total_chunks += chunk_count

            # Log file start
            embed_logger.log_file_start(
                span_id,
                file_path,
                file_size,
                chunk_count,
            )

            # Generate embeddings for chunks in batches
            chunk_texts = [chunk.text for chunk in chunks]
            batch_size = request.batch_size or 64
            batch_num = 0

            try:
                for i in range(0, len(chunk_texts), batch_size):
                    batch_num += 1
                    batch_texts = chunk_texts[i : i + batch_size]
                    batch_chunk_objects = chunks[i : i + batch_size]

                    # Time the embedding
                    embed_start = time.perf_counter()
                    embeddings = await embedder.embed_batch(batch_texts)
                    embed_time_ms = (time.perf_counter() - embed_start) * 1000

                    # Time the storage
                    storage_start = time.perf_counter()
                    vector_store.insert_chunks(batch_chunk_objects, embeddings)
                    storage_time_ms = (time.perf_counter() - storage_start) * 1000

                    # Log batch completion
                    embed_logger.log_batch_complete(
                        span_id,
                        file_path,
                        batch_num,
                        len(batch_texts),
                        embed_time_ms,
                        storage_time_ms,
                    )

                    embedded_chunks += len(batch_texts)

                # Update file tracker after all batches for this file are done
                file_tracker.record_file(
                    path=scanned_file.absolute_path,
                    sha256=scanned_file.sha256,
                    size_bytes=scanned_file.size_bytes,
                    mtime_ns=scanned_file.mtime_ns,
                )

                # Log file completion
                file_time_ms = (time.perf_counter() - start_time) * 1000
                embed_logger.log_file_complete(
                    span_id, file_path, chunk_count, file_time_ms
                )

                processed_files += 1

            except Exception as e:
                # Log batch/file error but continue processing other files
                embed_logger.log_batch_error(
                    span_id, file_path, batch_num, f"Embedding failed: {str(e)}"
                )
                continue

        elapsed_seconds = time.perf_counter() - start_time
        elapsed_ms = elapsed_seconds * 1000

        # Log embedding completion
        embed_logger.log_embed_complete(
            span_id, processed_files, embedded_chunks, elapsed_ms
        )

        return EmbedResponse(
            embedded_chunks=embedded_chunks,
            total_chunks=total_chunks,
            elapsed_seconds=elapsed_seconds,
        )

    except Exception as e:
        embed_logger.log_file_error(
            span_id, "unknown", f"Embedding process failed: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding failed: {str(e)}",
        )
    finally:
        # Ensure cleanup happens even on error
        await embedder.close()
        vector_store.close()
        file_tracker.close()
