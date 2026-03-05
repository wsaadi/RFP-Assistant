"""API dependencies for authentication and authorization."""
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..security import decode_access_token
from ..models.user import User, UserRole
from ..models.workspace import WorkspaceMember, MemberRole
from ..models.project import ProjectMember

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user from JWT token."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé ou inactif",
        )

    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis",
        )
    return current_user


async def check_workspace_access(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    """Check that the current user has access to the workspace."""
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == current_user.id)
    )
    member = result.scalar_one_or_none()

    if not member and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au workspace non autorisé",
        )

    return member


async def require_workspace_owner_or_admin(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> WorkspaceMember | None:
    """Require that the user is a workspace owner or system admin."""
    if user.role == UserRole.ADMIN:
        result = await db.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if not member or member.role != MemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un administrateur ou le propriétaire du workspace peut effectuer cette action",
        )
    return member


async def require_project_owner_or_admin(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> ProjectMember | None:
    """Require that the user is a project owner or system admin."""
    if user.role == UserRole.ADMIN:
        result = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.user_id == user.id)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .where(ProjectMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if not member or member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un administrateur ou le propriétaire du projet peut effectuer cette action",
        )
    return member


async def get_workspace_membership(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> WorkspaceMember | None:
    """Get the user's workspace membership (or None if admin without membership)."""
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if not member and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au workspace non autorisé",
        )
    return member


async def get_project_membership(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> ProjectMember | None:
    """Get the user's project membership. Raises 403 if no access."""
    from ..models.project import RFPProject

    if user.role == UserRole.ADMIN:
        result = await db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.user_id == user.id)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .where(ProjectMember.user_id == user.id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé à ce projet",
        )
    return member
