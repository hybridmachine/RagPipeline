"""User management for multi-project RAG system.

Handles user registration, authentication, and profile management.
"""

import uuid
from pathlib import Path
from typing import Optional

from rag_core.auth.password_utils import hash_password, verify_password
from rag_core.projects.database import MetadataDB


class User:
    """Represents a user account."""

    def __init__(
        self,
        id: str,
        username: str,
        email: str,
        password_hash: Optional[str] = None,
    ):
        """Initialize User.

        Args:
            id: Unique user ID.
            username: Username (unique).
            email: Email address (unique).
            password_hash: Hashed password.
        """
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash

    def to_dict(self, include_password: bool = False) -> dict:
        """Convert user to dictionary.

        Args:
            include_password: If True, include password hash (not recommended).

        Returns:
            Dictionary representation of user.
        """
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
        }
        if include_password:
            data["password_hash"] = self.password_hash
        return data


class UserManager:
    """Manage user accounts and authentication."""

    def __init__(self, base_dir: Path = Path(".rag")):
        """Initialize user manager.

        Args:
            base_dir: Base directory for RAG data (.rag).
        """
        self.base_dir = base_dir
        self.metadata_db = MetadataDB(base_dir / "metadata.db")

    def create_user(self, username: str, email: str, password: str) -> User:
        """Create a new user account.

        Args:
            username: Desired username (must be unique).
            email: Email address (must be unique).
            password: Plain text password to hash.

        Returns:
            Created User instance.

        Raises:
            ValueError: If username or email already exists.
        """
        conn = self.metadata_db.get_connection()
        try:
            # Check if username exists
            cursor = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            )
            if cursor.fetchone():
                raise ValueError(f"Username '{username}' already exists")

            # Check if email exists
            cursor = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            )
            if cursor.fetchone():
                raise ValueError(f"Email '{email}' already registered")

            # Create user
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password)

            cursor = conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, username, email, password_hash),
            )
            conn.commit()

            return User(user_id, username, email, password_hash)

        finally:
            conn.close()

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password.

        Args:
            username: Username to authenticate.
            password: Plain text password to verify.

        Returns:
            User instance if authentication succeeds, None otherwise.
        """
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, username, email, password_hash FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, password_hash = row
            if not verify_password(password, password_hash):
                return None

            return User(user_id, username, email, password_hash)

        finally:
            conn.close()

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: User ID to retrieve.

        Returns:
            User instance if found, None otherwise.
        """
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, username, email, password_hash FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, password_hash = row
            return User(user_id, username, email, password_hash)

        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username.

        Args:
            username: Username to retrieve.

        Returns:
            User instance if found, None otherwise.
        """
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, username, email, password_hash FROM users WHERE username = ?",
                (username,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, password_hash = row
            return User(user_id, username, email, password_hash)

        finally:
            conn.close()

    def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> User:
        """Update a user's information.

        Args:
            user_id: User ID to update.
            email: Optional new email address.
            password: Optional new password (plain text).

        Returns:
            Updated User instance.

        Raises:
            ValueError: If user not found or email already in use.
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found")

        conn = self.metadata_db.get_connection()
        try:
            updates = []
            params = []

            if email and email != user.email:
                # Check if new email is unique
                cursor = conn.execute(
                    "SELECT id FROM users WHERE email = ? AND id != ?",
                    (email, user_id),
                )
                if cursor.fetchone():
                    raise ValueError(f"Email '{email}' already in use")
                updates.append("email = ?")
                params.append(email)
                user.email = email

            if password:
                password_hash = hash_password(password)
                updates.append("password_hash = ?")
                params.append(password_hash)
                user.password_hash = password_hash

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(user_id)

                query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
                conn.execute(query, params)
                conn.commit()

            return user

        finally:
            conn.close()

    def delete_user(self, user_id: str) -> bool:
        """Delete a user account.

        Args:
            user_id: User ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()
