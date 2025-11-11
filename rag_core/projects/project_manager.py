"""Project management for multi-project RAG system.

Handles creating, reading, updating, and deleting projects,
as well as managing project configurations and databases.
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional

from rag_core.projects.database import MetadataDB, ProjectDB
from rag_core.projects.project_config import ProjectConfig


class ProjectManager:
    """Manage projects and their configurations."""

    def __init__(self, base_dir: Path = Path(".rag")):
        """Initialize project manager.

        Args:
            base_dir: Base directory for all RAG data (.rag)
        """
        self.base_dir = base_dir
        self.metadata_db = MetadataDB(base_dir / "metadata.db")

    def create_project(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        config: Optional[ProjectConfig] = None,
    ) -> ProjectConfig:
        """Create a new project.

        Args:
            user_id: ID of the user creating the project.
            name: Project name (must be unique per user).
            description: Optional project description.
            config: Optional ProjectConfig with custom settings.

        Returns:
            Created ProjectConfig instance.

        Raises:
            ValueError: If project name already exists for user.
        """
        # Generate project ID
        project_id = str(uuid.uuid4())

        # Validate project name is unique for user
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT id FROM projects WHERE user_id = ? AND name = ?",
                (user_id, name),
            )
            if cursor.fetchone():
                raise ValueError(f"Project '{name}' already exists for user")

            # Use provided config or create default
            if config is None:
                config = ProjectConfig(id=project_id, name=name, description=description)
            else:
                config.id = project_id
                config.name = name
                if description:
                    config.description = description

            # Create project directory and database
            config.data_dir = Path(f".rag/projects/{project_id}")
            config.vector_db_path = config.data_dir / "vectors.db"
            config.log_file = config.data_dir / "queries.log"

            # Initialize project database
            ProjectDB(config.vector_db_path)

            # Save configuration
            config_path = config.data_dir / "config.json"
            config.save_to_file(config_path)

            # Store in metadata database
            cursor = conn.execute(
                """
                INSERT INTO projects (id, user_id, name, description, config_json, data_dir)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    user_id,
                    name,
                    description,
                    json.dumps(config.to_dict(exclude_paths=True)),
                    str(config.data_dir),
                ),
            )
            conn.commit()

            return config

        finally:
            conn.close()

    def get_project(
        self,
        project_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[ProjectConfig]:
        """Get a project by ID.

        Args:
            project_id: ID of the project.
            user_id: Optional user ID to verify ownership.

        Returns:
            ProjectConfig if found, None otherwise.
        """
        conn = self.metadata_db.get_connection()
        try:
            if user_id:
                cursor = conn.execute(
                    "SELECT config_json FROM projects WHERE id = ? AND user_id = ?",
                    (project_id, user_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT config_json FROM projects WHERE id = ?",
                    (project_id,),
                )

            row = cursor.fetchone()
            if not row:
                return None

            config_dict = json.loads(row[0])
            return ProjectConfig.from_dict(config_dict)

        finally:
            conn.close()

    def list_projects(self, user_id: str) -> List[ProjectConfig]:
        """List all projects for a user.

        Args:
            user_id: ID of the user.

        Returns:
            List of ProjectConfig instances.
        """
        conn = self.metadata_db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT config_json FROM projects WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            projects = []
            for row in cursor.fetchall():
                config_dict = json.loads(row[0])
                projects.append(ProjectConfig.from_dict(config_dict))
            return projects

        finally:
            conn.close()

    def update_project(
        self,
        project_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        config_updates: Optional[dict] = None,
    ) -> ProjectConfig:
        """Update a project's configuration.

        Args:
            project_id: ID of the project.
            user_id: ID of the user (for verification).
            name: Optional new name.
            description: Optional new description.
            config_updates: Optional dict of config fields to update.

        Returns:
            Updated ProjectConfig instance.

        Raises:
            ValueError: If project not found or user doesn't own it.
        """
        conn = self.metadata_db.get_connection()
        try:
            # Get current project
            project = self.get_project(project_id, user_id)
            if not project:
                raise ValueError("Project not found or user doesn't own it")

            # Update fields
            if name:
                # Check new name is unique for user
                cursor = conn.execute(
                    "SELECT id FROM projects WHERE user_id = ? AND name = ? AND id != ?",
                    (user_id, name, project_id),
                )
                if cursor.fetchone():
                    raise ValueError(f"Project name '{name}' already exists for user")
                project.name = name

            if description is not None:
                project.description = description

            if config_updates:
                for key, value in config_updates.items():
                    if hasattr(project, key):
                        setattr(project, key, value)

            # Save configuration
            config_path = project.data_dir / "config.json"
            project.save_to_file(config_path)

            # Update metadata database
            cursor = conn.execute(
                """
                UPDATE projects
                SET name = ?, description = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    project.name,
                    project.description,
                    json.dumps(project.to_dict(exclude_paths=True)),
                    project_id,
                ),
            )
            conn.commit()

            return project

        finally:
            conn.close()

    def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete a project.

        Args:
            project_id: ID of the project.
            user_id: ID of the user (for verification).

        Returns:
            True if deleted, False if not found.
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return False

        conn = self.metadata_db.get_connection()
        try:
            # Delete from database
            cursor = conn.execute(
                "DELETE FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
            conn.commit()

            # Delete project directory
            if project.data_dir and project.data_dir.exists():
                import shutil

                shutil.rmtree(project.data_dir)

            return cursor.rowcount > 0

        finally:
            conn.close()

    def get_user_projects_size(self, user_id: str) -> int:
        """Get total size of all projects for a user.

        Args:
            user_id: ID of the user.

        Returns:
            Total size in bytes.
        """
        total_size = 0
        for project in self.list_projects(user_id):
            if project.data_dir and project.data_dir.exists():
                total_size += sum(
                    f.stat().st_size for f in project.data_dir.rglob("*") if f.is_file()
                )
        return total_size
