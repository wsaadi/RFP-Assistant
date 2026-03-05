"""RFP Project, Anonymization and AI Config models."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Enum as SAEnum, Boolean, JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class EncryptedPII(TypeDecorator):
    """SQLAlchemy type that transparently encrypts/decrypts PII values.

    Values are stored encrypted in the database (prefixed with 'pii:').
    Legacy plaintext values are read transparently and will be encrypted
    on the next write.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        from ..security import encrypt_pii
        return encrypt_pii(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        from ..security import decrypt_pii
        return decrypt_pii(value)


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
    company_name: Mapped[str] = mapped_column(String(255), default="")
    rfp_reference: Mapped[str] = mapped_column(String(255), default="")
    deadline: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.DRAFT,
    )
    improvement_axes: Mapped[str] = mapped_column(Text, default="")
    ai_context: Mapped[str] = mapped_column(Text, default="")
    enabled_categories: Mapped[list] = mapped_column(
        JSON, default=lambda: ["old_rfp", "old_response", "new_rfp", "inspiration"]
    )
    context_mode: Mapped[str] = mapped_column(String(20), default="rag")  # "rag" or "full"
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
    members = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan",
    )
    content_reuse_results = relationship(
        "ContentReuseResult", back_populates="project", cascade="all, delete-orphan",
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), default="editor")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="members")
    user = relationship("User")


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
    original_value: Mapped[str] = mapped_column(EncryptedPII(), nullable=False)
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
    provider: Mapped[str] = mapped_column(String(20), default="mistral")  # "mistral" or "ollama"
    mistral_api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=True, default="")
    model_name: Mapped[str] = mapped_column(String(100), default="mistral-large-latest")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    ollama_base_url: Mapped[str] = mapped_column(String(500), default="http://host.docker.internal:11434")
    ollama_model: Mapped[str] = mapped_column(String(100), default="mistral:latest")

    # NER (anonymization) provider config
    ner_provider: Mapped[str] = mapped_column(String(20), default="ollama")  # "ollama", "mistral", "scaleway"
    ner_model: Mapped[str] = mapped_column(String(100), default="qwen2.5:14b")

    # Vision (image analysis) provider config
    vision_provider: Mapped[str] = mapped_column(String(20), default="ollama")  # "ollama", "mistral", "scaleway"
    vision_model: Mapped[str] = mapped_column(String(100), default="llama3.2-vision:11b")

    # Scaleway Generative APIs key (shared for NER + Vision when provider is "scaleway")
    scaleway_api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=True, default="")
    scaleway_project_id: Mapped[str] = mapped_column(String(100), nullable=True, default="")

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


class ContentReuseResult(Base):
    """Persisted content reuse statistics between old response and generated chapters."""
    __tablename__ = "content_reuse_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    has_old_response: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_reuse_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    chapters: Mapped[dict] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="content_reuse_results")


class AIUsageLog(Base):
    """Tracks each AI API call with token counts for cost monitoring."""
    __tablename__ = "ai_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "generate_chapter", "gap_analysis"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "mistral", "ollama", "scaleway"
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject")


class AIModelPricing(Base):
    """Editable pricing table for AI models (token costs per 1K tokens)."""
    __tablename__ = "ai_model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_per_1k_input: Mapped[float] = mapped_column(Float, default=0.0)
    price_per_1k_output: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
