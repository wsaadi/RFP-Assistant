"""Service for reading PDF files."""
import fitz  # PyMuPDF
from typing import Optional


class PDFService:
    """Service for extracting text from PDF files."""

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Extract text content from a PDF file."""
        text_content = []

        try:
            # Open PDF from bytes
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            # Extract text from each page
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text.strip():
                    text_content.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()

            return "\n\n".join(text_content)

        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")

    @staticmethod
    def get_pdf_info(pdf_bytes: bytes) -> dict:
        """Get information about a PDF file."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            info = {
                "page_count": len(doc),
                "metadata": doc.metadata,
            }

            doc.close()
            return info

        except Exception as e:
            raise ValueError(f"Failed to get PDF info: {str(e)}")
