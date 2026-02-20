"""API routes for the internship report assistant."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json
from ..models.report import (
    ReportData,
    ReportSection,
    ReportPlan,
    SectionStatus,
    AIProviderConfig,
    GenerateRequest,
    QuestionsRequest,
    RecommendationsRequest,
    WordGenerationRequest,
)
from ..services.report_service import ReportService
from ..services.word_service import WordService
from ..services.ai_service import AIService
from ..services.pdf_service import PDFService
from ..services.utc_guidelines import get_default_report_plan, UTC_GUIDELINES
from pydantic import BaseModel

router = APIRouter()


class CreateReportRequest(BaseModel):
    """Request to create a new report."""
    student_name: str
    student_firstname: str
    semester: str
    company_name: str
    company_location: str
    internship_start_date: str
    internship_end_date: str
    tutor_name: str


class UpdateSectionRequest(BaseModel):
    """Request to update a section."""
    content: str | None = None
    status: SectionStatus | None = None


class AddNoteRequest(BaseModel):
    """Request to add a note to a section."""
    content: str


class TestAIRequest(BaseModel):
    """Request to test AI connection."""
    ai_config: AIProviderConfig


# Health check
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "UTC Internship Report Assistant"}


# Guidelines
@router.get("/guidelines")
async def get_guidelines():
    """Get the UTC TN05 guidelines."""
    return {"guidelines": UTC_GUIDELINES}


# Report Plan
@router.get("/plan/default", response_model=ReportPlan)
async def get_default_plan():
    """Get the default UTC report plan structure."""
    return get_default_report_plan()


# Report Management
@router.post("/reports", response_model=ReportData)
async def create_report(request: CreateReportRequest):
    """Create a new internship report."""
    report = ReportService.create_new_report(
        student_name=request.student_name,
        student_firstname=request.student_firstname,
        semester=request.semester,
        company_name=request.company_name,
        company_location=request.company_location,
        internship_start_date=request.internship_start_date,
        internship_end_date=request.internship_end_date,
        tutor_name=request.tutor_name,
    )
    return report


@router.post("/reports/progress")
async def get_report_progress(report: ReportData):
    """Calculate the progress of a report."""
    progress = ReportService.calculate_progress(report.plan.sections)
    return progress


@router.post("/reports/update-section/{section_id}")
async def update_section(section_id: str, request: UpdateSectionRequest, report: ReportData):
    """Update a section's content or status."""
    section = ReportService.find_section(report.plan.sections, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if request.content is not None:
        section.content = request.content
    if request.status is not None:
        section.status = request.status

    return {"success": True, "section": section}


@router.post("/reports/add-note/{section_id}")
async def add_note(section_id: str, request: AddNoteRequest, report: ReportData):
    """Add a note to a section."""
    note = ReportService.add_note_to_section(
        report.plan.sections, section_id, request.content
    )
    if not note:
        raise HTTPException(status_code=404, detail="Section not found")

    return {"success": True, "note": note}


# AI Features
@router.post("/ai/test")
async def test_ai_connection(request: TestAIRequest):
    """Test the AI provider connection."""
    try:
        ai_service = AIService(request.ai_config)
        response = await ai_service.generate(
            system_prompt="Tu es un assistant utile.",
            user_prompt="Réponds simplement 'Connexion réussie' en français.",
            temperature=0.1,
        )
        return {"success": True, "message": response.strip()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AI connection failed: {str(e)}")


@router.post("/ai/questions")
async def generate_questions(request: QuestionsRequest):
    """Generate questions for a section."""
    try:
        ai_service = AIService(request.ai_config)
        questions = await ai_service.generate_questions(
            section_title=request.section_title,
            section_description=request.section_description,
            current_notes=request.current_notes,
            current_content=request.current_content,
            school_instructions=request.school_instructions,
        )
        return {"success": True, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")


@router.post("/ai/recommendations")
async def generate_recommendations(request: RecommendationsRequest):
    """Generate recommendations for a section."""
    try:
        ai_service = AIService(request.ai_config)
        recommendations = await ai_service.generate_recommendations(
            section_title=request.section_title,
            section_description=request.section_description,
            status=request.status,
            current_notes=request.current_notes,
            current_content=request.current_content,
            school_instructions=request.school_instructions,
        )
        return {"success": True, "recommendations": recommendations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


class GenerateContentRequest(BaseModel):
    """Request to generate content for a section."""
    section_title: str
    section_description: str
    notes: str
    company_context: str
    ai_config: AIProviderConfig


@router.post("/ai/generate-content")
async def generate_content(request: GenerateContentRequest):
    """Generate content for a section based on notes."""
    try:
        ai_service = AIService(request.ai_config)
        content = await ai_service.generate_section_content(
            section_title=request.section_title,
            section_description=request.section_description,
            notes=request.notes,
            company_context=request.company_context,
        )
        return {"success": True, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate content: {str(e)}")


class ImproveTextRequest(BaseModel):
    """Request to improve text."""
    text: str
    section_context: str
    notes: str = ""
    ai_config: AIProviderConfig


@router.post("/ai/improve-text")
async def improve_text(request: ImproveTextRequest):
    """Improve and proofread text."""
    try:
        ai_service = AIService(request.ai_config)
        improved = await ai_service.improve_text(
            text=request.text,
            section_context=request.section_context,
            notes=request.notes,
        )
        return {"success": True, "improved_text": improved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to improve text: {str(e)}")


class GenerateNotesRequest(BaseModel):
    """Request to generate notes from a prompt."""
    section_title: str
    section_description: str
    user_prompt: str
    existing_notes: str = ""
    ai_config: AIProviderConfig


@router.post("/ai/generate-notes")
async def generate_notes(request: GenerateNotesRequest):
    """Generate notes based on user prompt."""
    try:
        ai_service = AIService(request.ai_config)
        notes = await ai_service.generate_notes_from_prompt(
            section_title=request.section_title,
            section_description=request.section_description,
            user_prompt=request.user_prompt,
            existing_notes=request.existing_notes,
        )
        return {"success": True, "notes": notes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate notes: {str(e)}")


class AnalyzeComplianceRequest(BaseModel):
    """Request to analyze compliance with instructions."""
    report_content: str
    instructions_content: str
    ai_config: AIProviderConfig


@router.post("/ai/analyze-compliance")
async def analyze_compliance(request: AnalyzeComplianceRequest):
    """Analyze if the report complies with the given instructions."""
    try:
        ai_service = AIService(request.ai_config)
        result = await ai_service.analyze_compliance(
            report_content=request.report_content,
            instructions_content=request.instructions_content,
        )
        return {"success": True, "analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze compliance: {str(e)}")


@router.post("/pdf/extract-text")
async def extract_pdf_text(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF file."""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        content = await file.read()
        text = PDFService.extract_text_from_pdf(content)
        info = PDFService.get_pdf_info(content)

        return {
            "success": True,
            "text": text,
            "page_count": info["page_count"],
            "filename": file.filename,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract PDF text: {str(e)}")


@router.post("/pdf/analyze-compliance")
async def analyze_pdf_compliance(
    file: UploadFile = File(...),
    report_data: str = Form(...),
    ai_config: str = Form(...),
):
    """Upload a PDF with instructions and analyze report compliance."""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")

        # Parse JSON strings
        report = ReportData.model_validate_json(report_data)
        config = AIProviderConfig.model_validate_json(ai_config)

        # Extract text from PDF
        pdf_content = await file.read()
        instructions_text = PDFService.extract_text_from_pdf(pdf_content)

        # Build report content from sections
        def get_section_content(sections: List[ReportSection], level: int = 1) -> str:
            content_parts = []
            for section in sections:
                prefix = "#" * level
                content_parts.append(f"{prefix} {section.title}")
                if section.content:
                    content_parts.append(section.content)
                elif section.notes:
                    notes_text = "\n".join([n.content for n in section.notes])
                    content_parts.append(f"Notes: {notes_text}")
                if section.subsections:
                    content_parts.append(get_section_content(section.subsections, level + 1))
            return "\n\n".join(content_parts)

        report_content = f"""
Rapport de stage de {report.student_firstname} {report.student_name}
Entreprise: {report.company_name}
Période: {report.internship_start_date} - {report.internship_end_date}

{get_section_content(report.plan.sections)}
"""

        # Analyze compliance
        ai_service = AIService(config)
        result = await ai_service.analyze_compliance(
            report_content=report_content,
            instructions_content=instructions_text,
        )

        return {
            "success": True,
            "analysis": result,
            "instructions_filename": file.filename,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze compliance: {str(e)}")


# Word Document Generation
@router.post("/generate-word")
async def generate_word_document(request: WordGenerationRequest):
    """Generate a Word document from the report data."""
    try:
        file_stream = await WordService.generate_document_with_ai(
            report=request.report_data,
            ai_config=request.ai_config,
        )

        filename = f"rapport_stage_{request.report_data.student_name}_{request.report_data.student_firstname}.docx"

        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Word document: {str(e)}")


@router.post("/generate-word-simple")
async def generate_word_document_simple(report_data: ReportData):
    """Generate a Word document without AI enhancement."""
    try:
        file_stream = await WordService.generate_document(report_data)

        filename = f"rapport_stage_{report_data.student_name}_{report_data.student_firstname}.docx"

        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Word document: {str(e)}")


class ReviewGrammarRequest(BaseModel):
    """Request to review grammar and spelling of the report."""
    report_content: str
    ai_config: AIProviderConfig


@router.post("/ai/review-grammar")
async def review_grammar(request: ReviewGrammarRequest):
    """Review the entire report for grammar, spelling, and conjugation errors."""
    try:
        ai_service = AIService(request.ai_config)
        result = await ai_service.review_grammar_and_spelling(
            report_content=request.report_content,
        )
        return {"success": True, "review": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to review grammar: {str(e)}")


class CustomPromptRequest(BaseModel):
    """Request to execute a custom prompt on content."""
    content: str
    user_prompt: str
    section_title: str
    ai_config: AIProviderConfig


@router.post("/ai/custom-prompt")
async def execute_custom_prompt(request: CustomPromptRequest):
    """Execute a custom user prompt on the content."""
    try:
        ai_service = AIService(request.ai_config)
        result = await ai_service.execute_custom_prompt(
            content=request.content,
            user_prompt=request.user_prompt,
            section_title=request.section_title,
        )
        return {"success": True, "content": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute custom prompt: {str(e)}")


class AdjustLengthRequest(BaseModel):
    """Request to adjust content length to target pages."""
    content: str
    section_title: str
    target_pages: float
    target_words: int
    ai_config: AIProviderConfig


@router.post("/ai/adjust-length")
async def adjust_content_length(request: AdjustLengthRequest):
    """Adjust the content length to match target pages."""
    try:
        ai_service = AIService(request.ai_config)
        result = await ai_service.adjust_content_length(
            content=request.content,
            section_title=request.section_title,
            target_pages=request.target_pages,
            target_words=request.target_words,
        )
        return {"success": True, "content": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to adjust content length: {str(e)}")
