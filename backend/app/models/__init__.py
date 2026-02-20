"""Data models for the application."""
from .report import (
    ReportSection,
    ReportPlan,
    SectionNote,
    SectionStatus,
    ReportData,
    GenerateRequest,
    QuestionsRequest,
    RecommendationsRequest,
    WordGenerationRequest,
    AIProviderConfig,
)

__all__ = [
    "ReportSection",
    "ReportPlan",
    "SectionNote",
    "SectionStatus",
    "ReportData",
    "GenerateRequest",
    "QuestionsRequest",
    "RecommendationsRequest",
    "WordGenerationRequest",
    "AIProviderConfig",
]
