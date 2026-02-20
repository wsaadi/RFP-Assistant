"""Report data models."""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SectionStatus(str, Enum):
    """Status of a report section."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class SectionNote(BaseModel):
    """A note within a section."""

    id: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReportSection(BaseModel):
    """A section of the internship report."""

    id: str
    title: str
    description: str
    required: bool = True
    order: int
    parent_id: Optional[str] = None
    min_pages: Optional[float] = None
    max_pages: Optional[float] = None
    status: SectionStatus = SectionStatus.NOT_STARTED
    notes: List[SectionNote] = Field(default_factory=list)
    content: str = ""
    generated_questions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    subsections: List["ReportSection"] = Field(default_factory=list)


class ReportPlan(BaseModel):
    """Complete report plan structure."""

    sections: List[ReportSection]
    total_min_pages: int = 10
    total_max_pages: int = 20


class ReportData(BaseModel):
    """Complete report data including metadata."""

    id: str
    student_name: str
    student_firstname: str
    semester: str
    company_name: str
    company_location: str
    internship_start_date: str
    internship_end_date: str
    tutor_name: str
    plan: ReportPlan
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AIProviderConfig(BaseModel):
    """AI provider configuration."""

    provider: str = Field(description="AI provider: 'openai' or 'mistral'")
    api_key: str = Field(description="API key for the selected provider")


class GenerateRequest(BaseModel):
    """Request to generate a report plan."""

    company_name: str
    company_sector: str
    internship_description: str
    ai_config: AIProviderConfig


class QuestionsRequest(BaseModel):
    """Request to generate questions for a section."""

    section_id: str
    section_title: str
    section_description: str
    current_notes: str = ""
    current_content: str = ""
    school_instructions: str = ""
    ai_config: AIProviderConfig


class RecommendationsRequest(BaseModel):
    """Request to get recommendations for a section."""

    section_id: str
    section_title: str
    section_description: str
    status: SectionStatus
    current_notes: str = ""
    current_content: str = ""
    school_instructions: str = ""
    ai_config: AIProviderConfig


class WordGenerationRequest(BaseModel):
    """Request to generate a Word document."""

    report_data: ReportData
    ai_config: AIProviderConfig
