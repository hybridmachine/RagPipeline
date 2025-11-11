"""JWT token management for API authentication.

Provides token creation, verification, and claims handling for FastAPI endpoints.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt


# Default JWT settings
DEFAULT_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRE_HOURS = 24


class JWTError(Exception):
    """Base exception for JWT errors."""

    pass


class TokenManager:
    """Manage JWT tokens for API authentication."""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = DEFAULT_ALGORITHM,
        expire_hours: int = DEFAULT_TOKEN_EXPIRE_HOURS,
    ):
        """Initialize token manager.

        Args:
            secret_key: Secret key for signing. Defaults to JWT_SECRET_KEY env var.
            algorithm: JWT algorithm to use (HS256 by default).
            expire_hours: Token expiration time in hours.

        Raises:
            JWTError: If secret key is not provided or in environment.
        """
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY")
        if not self.secret_key:
            raise JWTError(
                "JWT_SECRET_KEY not provided. Set environment variable or pass secret_key parameter."
            )
        self.algorithm = algorithm
        self.expire_hours = expire_hours

    def create_access_token(
        self,
        user_id: str,
        username: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT access token.

        Args:
            user_id: User ID to encode in token.
            username: Username to encode in token.
            expires_delta: Optional custom expiration time.

        Returns:
            Encoded JWT token.
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=self.expire_hours)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {
            "user_id": user_id,
            "username": username,
            "exp": expire,
        }
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> dict:
        """Verify a JWT token and return claims.

        Args:
            token: JWT token to verify.

        Returns:
            Dictionary with token claims (user_id, username, exp).

        Raises:
            JWTError: If token is invalid or expired.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("user_id")
            username: str = payload.get("username")

            if user_id is None or username is None:
                raise JWTError("Invalid token: missing user_id or username")

            return payload

        except jwt.ExpiredSignatureError:
            raise JWTError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise JWTError(f"Invalid token: {e}")

    def get_user_from_token(self, token: str) -> tuple[str, str]:
        """Extract user info from token.

        Args:
            token: JWT token to decode.

        Returns:
            Tuple of (user_id, username).

        Raises:
            JWTError: If token is invalid.
        """
        payload = self.verify_token(token)
        return payload["user_id"], payload["username"]
