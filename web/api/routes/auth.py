"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from rag_core.auth.user_manager import UserManager
from rag_core.auth.jwt_utils import TokenManager
from web.dependencies import get_token_manager, get_user_manager
from web.models import LoginRequest, RegisterRequest, TokenResponse


router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    user_manager: UserManager = Depends(get_user_manager),
    token_manager: TokenManager = Depends(get_token_manager),
) -> TokenResponse:
    """Register a new user and return access token.

    Args:
        request: Registration details (username, email, password).
        user_manager: User manager instance.
        token_manager: Token manager instance.

    Returns:
        Access token for new user.

    Raises:
        HTTPException: If registration fails (user exists, etc.).
    """
    try:
        user = user_manager.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Create and return token
    access_token = token_manager.create_access_token(user.id, user.username)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    user_manager: UserManager = Depends(get_user_manager),
    token_manager: TokenManager = Depends(get_token_manager),
) -> TokenResponse:
    """Authenticate user and return access token.

    Args:
        request: Login details (username, password).
        user_manager: User manager instance.
        token_manager: Token manager instance.

    Returns:
        Access token for authenticated user.

    Raises:
        HTTPException: If authentication fails.
    """
    user = user_manager.authenticate(
        username=request.username,
        password=request.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create and return token
    access_token = token_manager.create_access_token(user.id, user.username)
    return TokenResponse(access_token=access_token)
