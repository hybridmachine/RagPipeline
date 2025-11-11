"""File upload and management endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from rag_core.projects.project_config import ProjectConfig
from rag_core.projects.file_store import FileStore
from web.dependencies import get_current_project, get_current_user
from web.models import FileListResponse, UploadFileResponse


router = APIRouter()


@router.post("/{project_id}/files/upload", response_model=UploadFileResponse)
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    project: ProjectConfig = Depends(get_current_project),
) -> UploadFileResponse:
    """Upload a file to a project.

    Args:
        project_id: Project ID.
        file: File to upload.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        Upload result with file hash and path.

    Raises:
        HTTPException: If upload fails.
    """
    try:
        # Read file content
        content = await file.read()

        # Validate file size (100MB limit)
        max_size = 100 * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large (max {max_size} bytes)",
            )

        # Store file in shared store
        file_store = FileStore()
        file_hash, storage_path = file_store.store_file(content=content)

        # Create symlink in project directory
        relative_path = file.filename or "file"
        project_file_path = project.data_dir / "files" / relative_path
        file_store.create_symlink(file_hash, project_file_path)

        return UploadFileResponse(
            file_path=str(relative_path),
            sha256=file_hash,
            size_bytes=len(content),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}",
        )


@router.get("/{project_id}/files", response_model=FileListResponse)
async def list_project_files(
    project_id: str,
    user_id: str = Depends(get_current_user),
    project: ProjectConfig = Depends(get_current_project),
) -> FileListResponse:
    """List files in a project.

    Args:
        project_id: Project ID.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Returns:
        List of files in project.
    """
    # For now, return empty list - would implement actual file listing
    # by reading from file_scan_history table
    return FileListResponse(files=[], total=0)


@router.delete("/{project_id}/files/{file_path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_file(
    project_id: str,
    file_path: str,
    user_id: str = Depends(get_current_user),
    project: ProjectConfig = Depends(get_current_project),
) -> None:
    """Delete a file from project.

    Args:
        project_id: Project ID.
        file_path: Path to file in project.
        user_id: Current authenticated user ID.
        project: Project configuration.

    Raises:
        HTTPException: If deletion fails.
    """
    try:
        file_store = FileStore()
        symlink_path = project.data_dir / "files" / file_path

        if not symlink_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        file_store.remove_symlink(symlink_path)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File deletion failed: {str(e)}",
        )
