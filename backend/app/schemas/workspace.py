"""Workspace schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class WorkspaceMemberOut(BaseModel):
    id: str
    user_id: str
    username: str
    email: str
    full_name: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    project_count: int = 0

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "editor"
