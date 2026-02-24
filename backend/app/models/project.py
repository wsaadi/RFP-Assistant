"""RFP Project, Anonymization and AI Config models."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Enum as SAEnum, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    INDEXING = "indexing"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class EntityType(str, enum.Enum):
    COMPANY = "company"
    PERSON = "person"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    PROJECT_CODE = "project_code"
    RFP_CODE = "rfp_code"
    SOLUTION_NAME = "solution_name"
    DATE = "date"
    AMOUNT = "amount"
    OTHER = "other"


class RFPProject(Base):
    __tablename__ = "rfp_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    client_name: Mapped[str] = mapped_column(String(255), default="")
    rfp_reference: Mapped[str] = mapped_column(String(255), default="")
    deadline: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.DRAFT,
    )
    improvement_axes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workspace = relationship("Workspace", back_populates="projects")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")
    anonymization_mappings = relationship(
        "AnonymizationMapping", back_populates="project", cascade="all, delete-orphan"
    )
    response_documents = relationship(
        "ResponseDocument", back_populates="project", cascade="all, delete-orphan",
        order_by="ResponseDocument.order",
    )
    compliance_results = relationship(
        "ComplianceResult", back_populates="project", cascade="all, delete-orphan",
    )
    gap_analysis_results = relationship(
        "GapAnalysisResult", back_populates="project", cascade="all, delete-orphan",
    )


class AnonymizationMapping(Base):
    __tablename__ = "anonymization_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="entity_type"), nullable=False
    )
    original_value: Mapped[str] = mapped_column(Text, nullable=False)
    anonymized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="anonymization_mappings")


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    mistral_api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="mistral-large-latest")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    covered_requirements: Mapped[dict] = mapped_column(JSON, default=list)
    missing_elements: Mapped[dict] = mapped_column(JSON, default=list)
    recommendations: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="compliance_results")


class GapAnalysisResult(Base):
    __tablename__ = "gap_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    new_requirements: Mapped[dict] = mapped_column(JSON, default=list)
    removed_requirements: Mapped[dict] = mapped_column(JSON, default=list)
    modified_requirements: Mapped[dict] = mapped_column(JSON, default=list)
    unchanged_requirements: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="gap_analysis_results")
