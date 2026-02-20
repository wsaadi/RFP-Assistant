"""Chapter schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ChapterCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    parent_id: Optional[str] = None
    order: int = 0
    chapter_type: str = "chapter"
    rfp_requirement: str = ""


class ChapterUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    order: Optional[int] = None
    notes: Optional[List[dict]] = None
    improvement_axes: Optional[List[dict]] = None
    rfp_requirement: Optional[str] = None


class ChapterOut(BaseModel):
    id: str
    project_id: str
    parent_id: Optional[str]
    title: str
    description: str
    order: int
    chapter_type: str
    content: str
    status: str
    notes: list
    improvement_axes: list
    source_references: list
    image_references: list
    rfp_requirement: str
    is_prefilled: bool
    numbering: str
    created_at: datetime
    updated_at: datetime
    children: List["ChapterOut"] = []

    model_config = {"from_attributes": True}


class ChapterContentRequest(BaseModel):
    """Request to generate/enrich content for a chapter."""
    action: str = Field(..., description="generate|enrich|custom")
    custom_prompt: str = ""
    use_old_response: bool = True
    include_improvement_axes: bool = True


class AddNoteRequest(BaseModel):
    content: str = Field(..., min_length=1)
    author: str = ""


class ReorderChaptersRequest(BaseModel):
    chapter_orders: List[dict] = Field(..., description="List of {id, order} dicts")
