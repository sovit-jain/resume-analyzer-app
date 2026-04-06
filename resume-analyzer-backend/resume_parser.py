import docx
from pypdf import PdfReader

from config import get_logger

logger = get_logger(__name__)


def extract_text_from_pdf(file):
    logger.info("log-27 resume_parser.py | Starting PDF text extraction.")
    try:
        reader = PdfReader(file)
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        logger.info("log-28 resume_parser.py | Completed PDF extraction | pages=%d chars=%d", len(reader.pages), len(text))
        return text
    except Exception:
        logger.exception("log-29 resume_parser.py | PDF extraction failed.")
        raise


def extract_text_from_docx(file):
    logger.info("log-30 resume_parser.py | Starting DOCX text extraction.")
    try:
        doc = docx.Document(file)
        paragraphs = [para.text for para in doc.paragraphs if para.text]
        text = "\n".join(paragraphs).strip()
        logger.info("log-31 resume_parser.py | Completed DOCX extraction | paragraphs=%d chars=%d", len(paragraphs), len(text))
        return text
    except Exception:
        logger.exception("log-32 resume_parser.py | DOCX extraction failed.")
        raise