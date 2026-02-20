"""Admin API routes for user management and settings."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..security import hash_password
from ..models.user import User, UserRole
from ..models.workspace import Workspace, WorkspaceMember
from ..models.project import AIConfig
from ..schemas.user import UserOut, UserCreate, UserUpdate
from ..schemas.project import AIConfigUpdate, AIConfigOut
from .deps import get_admin_user

router = APIRouter(prefix="/admin", tags=["Administration"])


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
    if request.role is not None and request.role in [r.value for r in UserRole]:
        user.role = UserRole(request.role)

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
        config.mistral_api_key_encrypted = request.mistral_api_key  # TODO: encrypt in production
        config.model_name = request.model_name
        config.temperature = request.temperature
        config.max_tokens = request.max_tokens
    else:
        config = AIConfig(
            workspace_id=workspace_id,
            mistral_api_key_encrypted=request.mistral_api_key,
            model_name=request.model_name,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return AIConfigOut(
        model_name=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        has_api_key=bool(config.mistral_api_key_encrypted),
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
            model_name="mistral-large-latest",
            temperature=0.3,
            max_tokens=4096,
            has_api_key=False,
        )

    return AIConfigOut(
        model_name=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        has_api_key=bool(config.mistral_api_key_encrypted),
    )
