"""Report management service."""
import uuid
from datetime import datetime
from typing import Optional
from ..models.report import (
    ReportData,
    ReportSection,
    SectionNote,
    SectionStatus,
    AIProviderConfig,
)
from .utc_guidelines import get_default_report_plan
from .ai_service import AIService


class ReportService:
    """Service for managing internship reports."""

    @staticmethod
    def create_new_report(
        student_name: str,
        student_firstname: str,
        semester: str,
        company_name: str,
        company_location: str,
        internship_start_date: str,
        internship_end_date: str,
        tutor_name: str,
    ) -> ReportData:
        """Create a new report with the default UTC structure."""
        report_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        return ReportData(
            id=report_id,
            student_name=student_name,
            student_firstname=student_firstname,
            semester=semester,
            company_name=company_name,
            company_location=company_location,
            internship_start_date=internship_start_date,
            internship_end_date=internship_end_date,
            tutor_name=tutor_name,
            plan=get_default_report_plan(),
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def find_section(
        sections: list[ReportSection], section_id: str
    ) -> Optional[ReportSection]:
        """Find a section by ID in the report structure."""
        for section in sections:
            if section.id == section_id:
                return section
            if section.subsections:
                found = ReportService.find_section(section.subsections, section_id)
                if found:
                    return found
        return None

    @staticmethod
    def update_section_status(
        sections: list[ReportSection], section_id: str, status: SectionStatus
    ) -> bool:
        """Update the status of a section."""
        section = ReportService.find_section(sections, section_id)
        if section:
            section.status = status
            return True
        return False

    @staticmethod
    def add_note_to_section(
        sections: list[ReportSection], section_id: str, note_content: str
    ) -> Optional[SectionNote]:
        """Add a note to a section."""
        section = ReportService.find_section(sections, section_id)
        if section:
            note = SectionNote(
                id=str(uuid.uuid4()),
                content=note_content,
                created_at=datetime.now().isoformat(),
            )
            section.notes.append(note)
            return note
        return None

    @staticmethod
    def update_section_content(
        sections: list[ReportSection], section_id: str, content: str
    ) -> bool:
        """Update the content of a section."""
        section = ReportService.find_section(sections, section_id)
        if section:
            section.content = content
            return True
        return False

    @staticmethod
    def calculate_progress(sections: list[ReportSection]) -> dict:
        """Calculate the overall progress of the report."""
        total = 0
        completed = 0
        in_progress = 0

        def count_sections(secs: list[ReportSection]):
            nonlocal total, completed, in_progress
            for section in secs:
                if section.required:
                    total += 1
                    if section.status == SectionStatus.COMPLETED:
                        completed += 1
                    elif section.status == SectionStatus.IN_PROGRESS:
                        in_progress += 1
                if section.subsections:
                    count_sections(section.subsections)

        count_sections(sections)

        return {
            "total_sections": total,
            "completed": completed,
            "in_progress": in_progress,
            "not_started": total - completed - in_progress,
            "progress_percentage": round((completed / total * 100) if total > 0 else 0, 1),
        }

    @staticmethod
    async def generate_section_questions(
        section: ReportSection, ai_config: AIProviderConfig
    ) -> list[str]:
        """Generate questions for a section using AI."""
        ai_service = AIService(ai_config)
        notes_text = "\n".join([note.content for note in section.notes])

        questions = await ai_service.generate_questions(
            section_title=section.title,
            section_description=section.description,
            current_notes=notes_text,
        )

        section.generated_questions = questions
        return questions

    @staticmethod
    async def generate_section_recommendations(
        section: ReportSection, ai_config: AIProviderConfig
    ) -> list[str]:
        """Generate recommendations for a section using AI."""
        ai_service = AIService(ai_config)
        notes_text = "\n".join([note.content for note in section.notes])

        recommendations = await ai_service.generate_recommendations(
            section_title=section.title,
            section_description=section.description,
            status=section.status,
            current_notes=notes_text,
            current_content=section.content,
        )

        section.recommendations = recommendations
        return recommendations
