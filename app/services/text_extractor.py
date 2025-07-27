# app/services/text_extractor.py
import fitz  # PyMuPDF
# import docx # Add later if supporting docx
import logging
import os

log = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> str:
    """Extracts plain text from a PDF file using PyMuPDF (fitz)."""
    # (Keep implementation from previous phases - includes error handling)
    text = ""
    if not os.path.exists(file_path):
        log.error(f"PDF file not found at path: {file_path}")
        return ""
    try:
        with fitz.open(file_path) as pdf:
            for page_num, page in enumerate(pdf):
                try:
                    page_text = page.get_text("text", sort=True) # Added sort=True for potentially better reading order
                    text += page_text + "\n\n" # Double newline between pages
                except Exception as page_e:
                    log.error(f"Error extracting text from page {page_num + 1} in {file_path}: {page_e}", exc_info=True)
                    text += f"\n[Error processing page {page_num+1}]\n"
        log.info(f"Successfully extracted text from PDF: {file_path}")
        return text.strip()
    except fitz.fitz.FitzError as fitz_e:
        log.error(f"PyMuPDF error opening/processing PDF {file_path}: {fitz_e}", exc_info=True)
        return ""
    except Exception as e:
        log.error(f"Unexpected error extracting text from PDF {file_path}: {e}", exc_info=True)
        return ""

# Add extract_text_from_docx later if needed