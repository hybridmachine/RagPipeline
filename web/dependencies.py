"""Dependency injection for FastAPI endpoints.

Provides shared dependencies for authentication, authorization, and
resource access across all API endpoints.
"""

from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rag_core.auth.jwt_utils import JWTError, TokenManager
from rag_core.auth.user_manager import UserManager
from rag_core.projects.project_manager import ProjectManager


# Global instances (initialized on app startup)
_token_manager: Optional[TokenManager] = None
_user_manager: Optional[UserManager] = None
_project_manager: Optional[ProjectManager] = None

security = HTTPBearer()


def init_managers(base_dir: Path = Path(".rag")) -> None:
    """Initialize global managers.

    Must be called once on app startup.

    Args:
        base_dir: Base directory for RAG data.

    Raises:
        RuntimeError: If JWT_SECRET_KEY environment variable is not set.
    """
    import os

    global _token_manager, _user_manager, _project_manager

    # Verify JWT_SECRET_KEY is set
    if not os.getenv("JWT_SECRET_KEY"):
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable not set. "
            "Set it in .env file or as an environment variable."
        )

    _token_manager = TokenManager()
    _user_manager = UserManager(base_dir)
    _project_manager = ProjectManager(base_dir)


def get_token_manager() -> TokenManager:
    """Get token manager instance."""
    if _token_manager is None:
        raise RuntimeError("Managers not initialized. Call init_managers() on app startup.")
    return _token_manager


def get_user_manager() -> UserManager:
    """Get user manager instance."""
    if _user_manager is None:
        raise RuntimeError("Managers not initialized. Call init_managers() on app startup.")
    return _user_manager


def get_project_manager() -> ProjectManager:
    """Get project manager instance."""
    if _project_manager is None:
        raise RuntimeError("Managers not initialized. Call init_managers() on app startup.")
    return _project_manager


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    token_manager: TokenManager = Depends(get_token_manager),
    user_manager: UserManager = Depends(get_user_manager),
) -> str:
    """Extract and verify current user from JWT token.

    Args:
        credentials: Bearer token from request.
        token_manager: Token manager instance.
        user_manager: User manager instance.

    Returns:
        User ID of authenticated user.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    try:
        user_id, username = token_manager.get_user_from_token(credentials.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists
    user = user_manager.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_current_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
):
    """Verify user has access to project.

    Args:
        project_id: Project ID to access.
        user_id: Current user ID.
        project_manager: Project manager instance.

    Returns:
        ProjectConfig instance.

    Raises:
        HTTPException: If project not found or user doesn't have access.
    """
    project = project_manager.get_project(project_id, user_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project
