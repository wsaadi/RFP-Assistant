"""Workspace API routes."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.user import User
from ..models.workspace import Workspace, WorkspaceMember, MemberRole
from ..models.project import RFPProject
from ..schemas.workspace import WorkspaceCreate, WorkspaceUpdate, WorkspaceOut, WorkspaceMemberOut, AddMemberRequest
from .deps import get_current_user

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workspaces the current user has access to."""
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == current_user.id)
        .order_by(Workspace.updated_at.desc())
    )
    workspaces = result.scalars().all()

    workspace_list = []
    for ws in workspaces:
        # Count members
        member_count_result = await db.execute(
            select(func.count()).where(WorkspaceMember.workspace_id == ws.id)
        )
        member_count = member_count_result.scalar() or 0

        # Count projects
        project_count_result = await db.execute(
            select(func.count()).where(RFPProject.workspace_id == ws.id)
        )
        project_count = project_count_result.scalar() or 0

        workspace_list.append(WorkspaceOut(
            id=str(ws.id),
            name=ws.name,
            description=ws.description,
            created_by=str(ws.created_by),
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            member_count=member_count,
            project_count=project_count,
        ))

    return workspace_list


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspace."""
    workspace = Workspace(
        name=request.name,
        description=request.description,
        created_by=current_user.id,
    )
    db.add(workspace)
    await db.flush()

    # Add creator as owner
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role=MemberRole.OWNER,
    )
    db.add(member)
    await db.commit()
    await db.refresh(workspace)

    return WorkspaceOut(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        created_by=str(workspace.created_by),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        member_count=1,
        project_count=0,
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workspace details."""
    # Check access
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace non trouvé")

    member_count_result = await db.execute(
        select(func.count()).where(WorkspaceMember.workspace_id == workspace_id)
    )
    project_count_result = await db.execute(
        select(func.count()).where(RFPProject.workspace_id == workspace_id)
    )

    return WorkspaceOut(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        created_by=str(workspace.created_by),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        member_count=member_count_result.scalar() or 0,
        project_count=project_count_result.scalar() or 0,
    )


@router.put("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: uuid.UUID,
    request: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update workspace details."""
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace non trouvé")

    if request.name is not None:
        workspace.name = request.name
    if request.description is not None:
        workspace.description = request.description

    await db.commit()
    await db.refresh(workspace)

    return WorkspaceOut(
        id=str(workspace.id),
        name=workspace.name,
        description=workspace.description,
        created_by=str(workspace.created_by),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
async def list_members(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workspace members."""
    result = await db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    rows = result.all()

    return [
        WorkspaceMemberOut(
            id=str(member.id),
            user_id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=member.role.value,
            joined_at=member.joined_at,
        )
        for member, user in rows
    ]


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: uuid.UUID,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a member to the workspace."""
    # Check user exists
    result = await db.execute(select(User).where(User.id == uuid.UUID(request.user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Check not already member
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == uuid.UUID(request.user_id))
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Utilisateur déjà membre")

    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=uuid.UUID(request.user_id),
        role=MemberRole(request.role) if request.role in [r.value for r in MemberRole] else MemberRole.EDITOR,
    )
    db.add(member)
    await db.commit()

    return {"success": True, "message": "Membre ajouté"}


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the workspace."""
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Membre non trouvé")

    await db.delete(member)
    await db.commit()
