"""RFP Project schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    client_name: str = ""
    rfp_reference: str = ""
    deadline: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    client_name: Optional[str] = None
    rfp_reference: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None
    improvement_axes: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    client_name: str
    rfp_reference: str
    deadline: str
    status: str
    improvement_axes: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    chapter_count: int = 0

    model_config = {"from_attributes": True}


class AIConfigUpdate(BaseModel):
    mistral_api_key: str = Field(..., min_length=1)
    model_name: str = "mistral-large-latest"
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(4096, ge=256, le=32000)


class AIConfigOut(BaseModel):
    model_name: str
    temperature: float
    max_tokens: int
    has_api_key: bool

    model_config = {"from_attributes": True}


class ImprovementAxisRequest(BaseModel):
    content: str = Field(..., min_length=1)
    source: str = ""


class GapAnalysisRequest(BaseModel):
    pass


class GenerateStructureRequest(BaseModel):
    pass


class PrefillRequest(BaseModel):
    chapter_ids: List[str] = []


class ComplianceAnalysisRequest(BaseModel):
    pass
