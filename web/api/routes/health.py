"""Health check endpoints."""

from fastapi import APIRouter

from web.models import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        System health status.
    """
    return HealthResponse(status="ok", version="1.0.0")
