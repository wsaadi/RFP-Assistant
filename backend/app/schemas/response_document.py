"""ResponseDocument schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ResponseDocumentOut(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    expected_format: str
    content_type: str = "redaction"
    is_selected: bool
    order: int
    rfp_source: str
    fill_content: str = ""
    fill_status: str = "pending"
    source_document_ids: List[str] = []
    custom_notes: str = ""
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0

    model_config = {"from_attributes": True}


class ResponseDocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    expected_format: Optional[str] = None
    content_type: Optional[str] = None
    is_selected: Optional[bool] = None
    order: Optional[int] = None
    source_document_ids: Optional[List[str]] = None
    custom_notes: Optional[str] = None


class BulkUpdateSelectionRequest(BaseModel):
    """Confirm which documents to work on."""
    selections: List[dict] = Field(
        ...,
        description="List of {id: str, is_selected: bool}",
    )
