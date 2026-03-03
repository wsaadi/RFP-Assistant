"""RFP Project schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    client_name: str = ""
    company_name: str = ""
    rfp_reference: str = ""
    deadline: str = ""
    ai_context: str = ""
    enabled_categories: List[str] = ["old_rfp", "old_response", "new_rfp", "inspiration"]
    context_mode: str = "rag"  # "rag" or "full"


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    client_name: Optional[str] = None
    company_name: Optional[str] = None
    rfp_reference: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None
    improvement_axes: Optional[str] = None
    ai_context: Optional[str] = None
    enabled_categories: Optional[List[str]] = None
    context_mode: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    client_name: str
    company_name: str
    rfp_reference: str
    deadline: str
    status: str
    improvement_axes: str
    ai_context: str
    enabled_categories: List[str] = ["old_rfp", "old_response", "new_rfp", "inspiration"]
    context_mode: str = "rag"
    created_by: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    chapter_count: int = 0

    model_config = {"from_attributes": True}


class AIConfigUpdate(BaseModel):
    provider: str = "mistral"  # "mistral" or "ollama"
    mistral_api_key: str = ""
    model_name: str = "mistral-large-latest"
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(4096, ge=256, le=32000)
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "mistral:latest"
    # Image processing providers
    ner_provider: str = "ollama"  # "ollama", "mistral", "scaleway"
    ner_model: str = "qwen2.5:14b"
    vision_provider: str = "ollama"  # "ollama", "mistral", "scaleway"
    vision_model: str = "llama3.2-vision:11b"
    scaleway_api_key: str = ""
    scaleway_base_url: str = "https://api.scaleway.ai/v1"


class AIConfigOut(BaseModel):
    provider: str = "mistral"
    model_name: str
    temperature: float
    max_tokens: int
    has_api_key: bool
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "mistral:latest"
    # Image processing providers
    ner_provider: str = "ollama"
    ner_model: str = "qwen2.5:14b"
    vision_provider: str = "ollama"
    vision_model: str = "llama3.2-vision:11b"
    has_scaleway_api_key: bool = False
    scaleway_base_url: str = "https://api.scaleway.ai/v1"

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
