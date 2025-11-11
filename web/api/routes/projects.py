"""Project management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from rag_core.projects.project_manager import ProjectManager
from web.dependencies import get_current_user, get_current_project, get_project_manager
from web.models import (
    CreateProjectRequest,
    ProjectListResponse,
    ProjectResponse,
    UpdateProjectRequest,
)


router = APIRouter()


@router.post("", response_model=ProjectResponse)
async def create_project(
    request: CreateProjectRequest,
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectResponse:
    """Create a new project.

    Args:
        request: Project creation details.
        user_id: Current authenticated user ID.
        project_manager: Project manager instance.

    Returns:
        Created project details.

    Raises:
        HTTPException: If project creation fails.
    """
    try:
        project = project_manager.create_project(
            user_id=user_id,
            name=request.name,
            description=request.description,
        )

        # Update config if provided
        if request.embed_model_id or request.llm_model_id:
            updates = {}
            if request.embed_model_id:
                updates["embed_model_id"] = request.embed_model_id
            if request.llm_model_id:
                updates["llm_model_id"] = request.llm_model_id
            project = project_manager.update_project(
                project.id, user_id, config_updates=updates
            )

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            embed_model_id=project.embed_model_id,
            llm_model_id=project.llm_model_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectListResponse:
    """List all projects for current user.

    Args:
        user_id: Current authenticated user ID.
        project_manager: Project manager instance.

    Returns:
        List of user's projects.
    """
    projects = project_manager.list_projects(user_id)
    return ProjectListResponse(
        projects=[
            ProjectResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                embed_model_id=p.embed_model_id,
                llm_model_id=p.llm_model_id,
            )
            for p in projects
        ],
        total=len(projects),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectResponse:
    """Get project details.

    Args:
        project_id: Project ID.
        user_id: Current authenticated user ID.
        project_manager: Project manager instance.

    Returns:
        Project details.

    Raises:
        HTTPException: If project not found.
    """
    project = project_manager.get_project(project_id, user_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        embed_model_id=project.embed_model_id,
        llm_model_id=project.llm_model_id,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ProjectResponse:
    """Update project configuration.

    Args:
        project_id: Project ID.
        request: Update details.
        user_id: Current authenticated user ID.
        project_manager: Project manager instance.

    Returns:
        Updated project details.

    Raises:
        HTTPException: If update fails.
    """
    try:
        # Build config updates dict
        updates = {}
        for key in [
            "embed_model_id",
            "hf_endpoint_url",
            "hf_api_token",
            "llm_model_id",
            "llm_endpoint_url",
            "llm_api_token",
            "chunk_target_tokens",
            "chunk_overlap_tokens",
        ]:
            value = getattr(request, key, None)
            if value is not None:
                updates[key] = value

        project = project_manager.update_project(
            project_id,
            user_id,
            name=request.name,
            description=request.description,
            config_updates=updates if updates else None,
        )

        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            embed_model_id=project.embed_model_id,
            llm_model_id=project.llm_model_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> None:
    """Delete a project.

    Args:
        project_id: Project ID.
        user_id: Current authenticated user ID.
        project_manager: Project manager instance.

    Raises:
        HTTPException: If project not found.
    """
    if not project_manager.delete_project(project_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
