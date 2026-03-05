"""Admin API routes for user management and settings."""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..security import hash_password, encrypt_api_key
from ..models.user import User, UserRole
from ..models.workspace import Workspace, WorkspaceMember
from ..models.project import AIConfig
from ..schemas.user import UserOut, UserCreate, UserUpdate
from ..schemas.project import AIConfigUpdate, AIConfigOut
from .deps import get_admin_user

router = APIRouter(prefix="/admin", tags=["Administration"])
audit_log = logging.getLogger("security.audit")


@router.get("/users", response_model=list[UserOut])
async def list_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        UserOut(
            id=str(u.id),
            email=u.email,
            username=u.username,
            full_name=u.full_name,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)."""
    # Check uniqueness
    result = await db.execute(
        select(User).where((User.email == request.email) | (User.username == request.username))
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email ou nom d'utilisateur déjà utilisé",
        )

    # Validate password strength
    from .auth import validate_password_strength
    validate_password_strength(request.password)

    user = User(
        email=request.email,
        username=request.username,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        role=UserRole(request.role) if request.role in [r.value for r in UserRole] else UserRole.USER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    audit_log.info("User created: email=%s role=%s by admin=%s", user.email, user.role.value, admin.email)

    return UserOut(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    request: UserUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if request.email is not None:
        user.email = request.email
    if request.username is not None:
        user.username = request.username
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.is_active is not None:
        user.is_active = request.is_active
        if not request.is_active:
            audit_log.warning("User deactivated: email=%s by admin=%s", user.email, admin.email)
    if request.role is not None and request.role in [r.value for r in UserRole]:
        user.role = UserRole(request.role)
        audit_log.info("User role changed: email=%s new_role=%s by admin=%s", user.email, request.role, admin.email)

    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (admin only)."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer son propre compte admin",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    audit_log.warning("User deleted: email=%s (id=%s) by admin=%s", user.email, user_id, admin.email)
    await db.delete(user)
    await db.commit()


@router.put("/ai-config/{workspace_id}", response_model=AIConfigOut)
async def update_ai_config(
    workspace_id: uuid.UUID,
    request: AIConfigUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update AI configuration for a workspace (admin only)."""
    result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == workspace_id)
    )
    config = result.scalar_one_or_none()

    if config:
        config.provider = request.provider
        # Only update API keys when a non-empty value is provided,
        # so reloading the settings page doesn't wipe stored keys.
        # Keys are encrypted before storage.
        if request.mistral_api_key:
            config.mistral_api_key_encrypted = encrypt_api_key(request.mistral_api_key)
        config.model_name = request.model_name
        config.temperature = request.temperature
        config.max_tokens = request.max_tokens
        config.ollama_base_url = request.ollama_base_url
        config.ollama_model = request.ollama_model
        config.ner_provider = request.ner_provider
        config.ner_model = request.ner_model
        config.vision_provider = request.vision_provider
        config.vision_model = request.vision_model
        if request.scaleway_api_key:
            config.scaleway_api_key_encrypted = encrypt_api_key(request.scaleway_api_key)
        config.scaleway_project_id = request.scaleway_project_id
    else:
        config = AIConfig(
            workspace_id=workspace_id,
            provider=request.provider,
            mistral_api_key_encrypted=encrypt_api_key(request.mistral_api_key) if request.mistral_api_key else "",
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            ollama_base_url=request.ollama_base_url,
            ollama_model=request.ollama_model,
            ner_provider=request.ner_provider,
            ner_model=request.ner_model,
            vision_provider=request.vision_provider,
            vision_model=request.vision_model,
            scaleway_api_key_encrypted=encrypt_api_key(request.scaleway_api_key) if request.scaleway_api_key else "",
            scaleway_project_id=request.scaleway_project_id,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    audit_log.info("AI config updated: workspace=%s provider=%s by admin=%s", workspace_id, request.provider, admin.email)

    return _config_to_out(config)


def _config_to_out(config: AIConfig) -> AIConfigOut:
    """Convert an AIConfig DB row to the response schema."""
    return AIConfigOut(
        provider=config.provider or "mistral",
        model_name=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        has_api_key=bool(config.mistral_api_key_encrypted),
        ollama_base_url=config.ollama_base_url or "http://host.docker.internal:11434",
        ollama_model=config.ollama_model or "mistral:latest",
        ner_provider=config.ner_provider or "ollama",
        ner_model=config.ner_model or "qwen2.5:14b",
        vision_provider=config.vision_provider or "ollama",
        vision_model=config.vision_model or "llama3.2-vision:11b",
        has_scaleway_key=bool(config.scaleway_api_key_encrypted),
        scaleway_project_id=config.scaleway_project_id or "",
    )


@router.get("/ai-config/{workspace_id}", response_model=AIConfigOut)
async def get_ai_config(
    workspace_id: uuid.UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get AI configuration for a workspace."""
    result = await db.execute(
        select(AIConfig).where(AIConfig.workspace_id == workspace_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        return AIConfigOut(
            provider="mistral",
            model_name="mistral-large-latest",
            temperature=0.3,
            max_tokens=4096,
            has_api_key=False,
            ollama_base_url="http://host.docker.internal:11434",
            ollama_model="mistral:latest",
            ner_provider="ollama",
            ner_model="qwen2.5:14b",
            vision_provider="ollama",
            vision_model="llama3.2-vision:11b",
            has_scaleway_key=False,
        )

    return _config_to_out(config)
