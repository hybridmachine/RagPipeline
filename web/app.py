"""FastAPI application for multi-project RAG system.

Provides REST API endpoints for user authentication, project management,
file uploads, and RAG queries.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.api import routes
from web.dependencies import init_managers

# Load environment variables before anything else
load_dotenv()


def create_app(base_dir: Path = Path(".rag")) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        base_dir: Base directory for RAG data (.rag).

    Returns:
        Configured FastAPI application instance.
    """

    # Define lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage app lifespan (startup and shutdown)."""
        # Startup
        init_managers(base_dir)
        yield
        # Shutdown (cleanup if needed)

    app = FastAPI(
        title="RAG Pipeline API",
        description="Multi-project Retrieval-Augmented Generation system",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # Development
            "http://localhost:5173",  # Vite dev server
            "http://localhost:8001",  # API server
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(routes.auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(routes.users.router, prefix="/api/users", tags=["users"])
    app.include_router(routes.projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(routes.files.router, prefix="/api/projects", tags=["files"])
    app.include_router(routes.query.router, prefix="/api/projects", tags=["query"])
    app.include_router(routes.health.router, prefix="/api", tags=["health"])

    # Serve static files (React frontend) if they exist
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


# Create app instance for module import and development
app = create_app()

# For development
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
