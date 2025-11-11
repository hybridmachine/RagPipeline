"""User management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from rag_core.auth.user_manager import UserManager
from web.dependencies import get_current_user, get_user_manager
from web.models import UserResponse


router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_profile(
    user_id: str = Depends(get_current_user),
    user_manager: UserManager = Depends(get_user_manager),
) -> UserResponse:
    """Get current user's profile.

    Args:
        user_id: Current authenticated user ID.
        user_manager: User manager instance.

    Returns:
        Current user's profile.

    Raises:
        HTTPException: If user not found.
    """
    user = user_manager.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
    )
