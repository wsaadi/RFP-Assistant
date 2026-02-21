"""Main FastAPI application for RFP Response Assistant."""
import os
import warnings
from contextlib import asynccontextmanager

# Suppress noisy third-party warnings
warnings.filterwarnings("ignore", message=".*resume_download.*is deprecated.*", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*resume_download.*is deprecated.*", category=UserWarning)
os.environ.setdefault("ORT_LOG_LEVEL", "ERROR")  # Suppress ONNX Runtime CPU vendor warnings

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import init_db, engine
from .security import hash_password
from .models.user import User, UserRole

# Import all models to ensure they are registered
from .models import (
    User, Workspace, WorkspaceMember,
    Document, DocumentChunk, DocumentImage,
    RFPProject, AnonymizationMapping, AIConfig,
    Chapter,
)

from .api.auth import router as auth_router
from .api.admin import router as admin_router
from .api.workspaces import router as workspaces_router
from .api.projects import router as projects_router
from .api.documents import router as documents_router
from .api.chapters import router as chapters_router
from .api.export import router as export_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Configure HuggingFace token if provided
    if settings.hf_token:
        os.environ["HF_TOKEN"] = settings.hf_token

    # Startup
    await init_db()

    # Ensure 'DOC' value exists in file_type enum (for .doc support)
    # SQLAlchemy persists enum member names (uppercase), not values
    # Use AUTOCOMMIT isolation since ALTER TYPE ADD VALUE cannot run in a transaction
    from sqlalchemy import text
    conn = await engine.connect()
    conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
    try:
        await conn.execute(text("ALTER TYPE file_type ADD VALUE IF NOT EXISTS 'DOC'"))
    finally:
        await conn.close()

    # Create data directories
    for dir_path in [settings.upload_dir, settings.export_dir, settings.images_dir, settings.chroma_persist_dir]:
        os.makedirs(dir_path, exist_ok=True)

    # Create default admin if not exists
    from .database import async_session
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        admin = result.scalar_one_or_none()
        if not admin:
            admin = User(
                email=settings.admin_email,
                username="admin",
                hashed_password=hash_password(settings.admin_password),
                full_name="Administrateur",
                role=UserRole.ADMIN,
            )
            db.add(admin)
            await db.commit()
            print(f"Default admin created: {settings.admin_email}")

    yield

    # Shutdown
    await engine.dispose()


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.app_name,
    description="Assistant IA pour la rédaction de réponses aux appels d'offres",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response

# CORS
cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(chapters_router, prefix="/api")
app.include_router(export_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "RFP Response Assistant API",
        "docs": "/api/docs",
        "version": "2.0.0",
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.app_name}
