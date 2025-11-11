"""Query and RAG endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from rag_core.projects.project_config import ProjectConfig
from rag_core.logging_config import get_query_logger
from web.dependencies import get_current_project, get_current_user
from web.models import (
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

    Args:
        project_id: Project ID.
        request: Query request.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        Query result with answer and citations.

    Raises:
        HTTPException: If query fails.
    """
    query_logger = get_query_logger(project_id=project_id)
    span_id: str | None = None

    try:
        # Initialize query logger with project context
        span_id = query_logger.log_query_start(request.query, user_id=user_id)

        # TODO: Implement RAG query using:
        # - project.to_core_config() to get Config
        # - VectorStore for similarity search
        # - QueryEngine for RAG pipeline (pass project_id=project_id, user_id=user_id)
        # - OpenAI client for LLM call

        return QueryResponse(
            answer="This is a placeholder response. RAG implementation pending.",
            citations=[],
            num_retrieved=0,
            elapsed_seconds=0.0,
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

    Args:
        project_id: Project ID.
        request: Embedding request.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        Embedding generation result.

    Raises:
        HTTPException: If embedding fails.
    """
    try:
        # TODO: Implement embedding generation using:
        # - project.to_core_config() to get Config
        # - FileTracker to get files
        # - Chunker to split files
        # - Embedder to generate vectors
        # - VectorStore to store embeddings

        return EmbedResponse(
            embedded_chunks=0,
            total_chunks=0,
            elapsed_seconds=0.0,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding failed: {str(e)}",
        )
