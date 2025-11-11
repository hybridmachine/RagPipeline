"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# Auth models
class RegisterRequest(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """User login request."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User profile response."""

    id: str
    username: str
    email: str


# Project models
class CreateProjectRequest(BaseModel):
    """Create project request."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    embed_model_id: Optional[str] = None
    llm_model_id: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    """Update project request."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    embed_model_id: Optional[str] = None
    hf_endpoint_url: Optional[str] = None
    hf_api_token: Optional[str] = None
    llm_model_id: Optional[str] = None
    llm_endpoint_url: Optional[str] = None
    llm_api_token: Optional[str] = None
    chunk_target_tokens: Optional[int] = None
    chunk_overlap_tokens: Optional[int] = None


class ProjectResponse(BaseModel):
    """Project details response."""

    id: str
    name: str
    description: Optional[str]
    created_at: Optional[datetime] = None
    embed_model_id: str
    llm_model_id: str


class ProjectListResponse(BaseModel):
    """List of projects response."""

    projects: list[ProjectResponse]
    total: int


# File models
class UploadFileResponse(BaseModel):
    """File upload response."""

    file_path: str
    sha256: str
    size_bytes: int


class FileInfo(BaseModel):
    """File information in project."""

    path: str
    sha256: str
    size_bytes: int
    scanned_at: datetime


class FileListResponse(BaseModel):
    """List of files in project."""

    files: list[FileInfo]
    total: int


# Query models
class QueryRequest(BaseModel):
    """RAG query request."""

    query: str = Field(..., min_length=1, max_length=1000)
    k: Optional[int] = Field(8, ge=1, le=50)
    rerank: Optional[int] = None


class CitationReference(BaseModel):
    """Citation reference in answer."""

    path: str
    chunk_id: int
    text: Optional[str] = None


class QueryResponse(BaseModel):
    """RAG query response."""

    answer: str
    citations: list[CitationReference]
    num_retrieved: int
    elapsed_seconds: float


# Embedding models
class EmbedRequest(BaseModel):
    """Embedding generation request."""

    batch_size: Optional[int] = Field(64, ge=1, le=256)


class EmbedResponse(BaseModel):
    """Embedding generation response."""

    embedded_chunks: int
    total_chunks: int
    elapsed_seconds: float


# Health models
class HealthResponse(BaseModel):
    """System health status."""

    status: str = "ok"
    version: str = "1.0.0"


class ProjectHealthResponse(BaseModel):
    """Project-specific health status."""

    status: str = "ok"
    embedding_status: dict
    total_chunks: int
    total_files: int
