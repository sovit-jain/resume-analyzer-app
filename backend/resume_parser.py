import tempfile
import os
import re

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

from config import get_logger, OPENAI_API_KEY

logger = get_logger(__name__)


# =========================================================
# IMPORTANT FIX
# ChromaDB does not allow None metadata values
# =========================================================
def clean_metadata(metadata):
    """
    Clean metadata for Chroma compatibility.
    """

    if metadata is None:
        return {}

    cleaned = {}

    for key, value in metadata.items():

        if value is None:
            cleaned[key] = ""

        elif isinstance(value, (str, int, float, bool)):
            cleaned[key] = value

        else:
            cleaned[key] = str(value)

    return cleaned


# =========================================================
# DOCUMENT LOADERS
# =========================================================
def load_pdf_document(file):
    """Load PDF file from uploaded file object."""

    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            temp_file_path = tmp.name

        loader = PyPDFLoader(temp_file_path)
        documents = loader.load()

        logger.info(
            "PDF loaded successfully | docs=%d total_chars=%d",
            len(documents),
            sum(len(doc.page_content) for doc in documents),
        )

        return documents

    except Exception:
        logger.exception("PDF loading failed")
        raise

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def load_docx_document(file):
    """Load DOCX file from uploaded file object."""

    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            temp_file_path = tmp.name

        loader = Docx2txtLoader(temp_file_path)
        documents = loader.load()

        logger.info(
            "DOCX loaded successfully | docs=%d total_chars=%d",
            len(documents),
            sum(len(doc.page_content) for doc in documents),
        )

        return documents

    except Exception:
        logger.exception("DOCX loading failed")
        raise

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


# =========================================================
# SPACY LOADING
# =========================================================
try:
    import spacy

    try:
        _nlp = spacy.load("en_core_web_sm")
        logger.info("spaCy model loaded")

    except Exception:
        _nlp = None
        logger.info("spaCy model unavailable")

except Exception:
    _nlp = None
    logger.info("spaCy not installed")


# =========================================================
# METADATA EXTRACTION
# =========================================================
def extract_resume_metadata(text: str) -> dict:
    """
    Extract metadata from resume.
    """

    meta = {
        "email": "",
        "years_experience": 0,
        "current_title": "",
        "location": "",
    }

    try:

        # EMAIL
        email_match = re.search(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            text
        )

        if email_match:
            meta["email"] = email_match.group(0)

        # YEARS OF EXPERIENCE
        years_match = re.search(
            r"(\d{1,2})\s*\+?\s*(?:years|yrs)",
            text,
            re.IGNORECASE
        )

        if years_match:
            try:
                meta["years_experience"] = int(years_match.group(1))
            except Exception:
                meta["years_experience"] = 0

        # SPACY BASED EXTRACTION
        if _nlp:

            doc = _nlp(text)

            # LOCATION
            gpes = [
                ent.text
                for ent in doc.ents
                if ent.label_ in ("GPE", "LOC")
            ]

            if gpes:
                meta["location"] = gpes[0]

            # CURRENT TITLE
            lines = [l.strip() for l in text.splitlines() if l.strip()]

            keywords = [
                "engineer",
                "developer",
                "manager",
                "lead",
                "director",
                "architect",
                "consultant",
                "analyst",
                "scientist",
            ]

            for line in lines[:8]:

                if 2 <= len(line.split()) <= 7:

                    if any(k in line.lower() for k in keywords):
                        meta["current_title"] = line
                        break

        else:
            # FALLBACK HEURISTICS

            lines = [l.strip() for l in text.splitlines() if l.strip()]

            keywords = [
                "engineer",
                "developer",
                "manager",
                "lead",
                "director",
                "architect",
                "consultant",
                "analyst",
            ]

            for line in lines[:6]:

                if 2 <= len(line.split()) <= 6:

                    if any(k in line.lower() for k in keywords):
                        meta["current_title"] = line
                        break

    except Exception:
        logger.exception("Metadata extraction failed")

    return clean_metadata(meta)


# =========================================================
# LOAD DOCUMENT
# =========================================================
def load_document(file, filename: str) -> str:

    filename = filename.lower()

    try:

        if filename.endswith(".pdf"):
            documents = load_pdf_document(file)

        elif filename.endswith(".docx"):
            documents = load_docx_document(file)

        else:
            raise ValueError(f"Unsupported file format: {filename}")

        text = "\n".join(doc.page_content for doc in documents)

        logger.info(
            "Document loaded successfully | type=%s chars=%d",
            filename.split(".")[-1],
            len(text)
        )

        return text.strip()

    except Exception:
        logger.exception("Document loading failed")
        raise


# =========================================================
# TEXT SPLITTING
# =========================================================
def split_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200
):

    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        keep_separator=True,
    )

    chunks = splitter.split_text(text)

    logger.info(
        "Text split into %d chunks",
        len(chunks)
    )

    return chunks


# =========================================================
# VECTOR STORE CREATION
# =========================================================
def create_vector_store_from_documents(
    documents: list[Document],
    collection_name: str = "resume_chunks",
    persist_directory: str = None,
) -> Chroma:

    embeddings = OpenAIEmbeddings(
        api_key=OPENAI_API_KEY,
        model="text-embedding-3-small"
    )

    # =====================================================
    # IMPORTANT FIX
    # CLEAN METADATA BEFORE CHROMA INSERT
    # =====================================================
    for doc in documents:
        doc.metadata = clean_metadata(doc.metadata)

    logger.info(
        "Creating vector store with %d documents",
        len(documents)
    )

    # DEBUGGING
    for i, doc in enumerate(documents[:3]):
        logger.info(
            "Sample metadata %d: %s",
            i,
            str(doc.metadata)
        )

    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=persist_directory
    )

    if persist_directory:
        vector_store.persist()
        logger.info("Vector store persisted")

    else:
        logger.info("In-memory vector store created")

    return vector_store


# =========================================================
# BACKWARD COMPATIBILITY WRAPPER
# =========================================================
def create_vector_store(
    documents: list,
    collection_name: str = "resume_chunks",
    persist_directory: str = None,
) -> Chroma:

    wrapped = []

    for i, d in enumerate(documents or []):

        if isinstance(d, Document):

            d.metadata = clean_metadata(d.metadata)
            wrapped.append(d)

        elif isinstance(d, str):

            wrapped.append(
                Document(
                    page_content=d,
                    metadata={"chunk_index": i}
                )
            )

        else:

            wrapped.append(
                Document(
                    page_content=str(d),
                    metadata={"chunk_index": i}
                )
            )

    return create_vector_store_from_documents(
        wrapped,
        collection_name=collection_name,
        persist_directory=persist_directory
    )


# =========================================================
# INDEX RESUMES
# =========================================================
def index_resumes(
    resumes: list[dict],
    collection_name: str = "resumes_global",
    persist_directory: str = None,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> Chroma:

    all_documents = []

    for r in resumes:

        resume_id = str(r.get("resume_id", ""))

        filename = r.get("filename", "")

        text = r.get("text", "")

        # EXTRACT METADATA
        resume_meta = extract_resume_metadata(text)

        resume_meta.update({
            "resume_id": resume_id,
            "filename": filename
        })

        resume_meta = clean_metadata(resume_meta)

        # SPLIT INTO CHUNKS
        chunks = split_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        # CREATE DOCUMENTS
        for i, chunk in enumerate(chunks):

            meta = dict(resume_meta)

            meta.update({
                "chunk_index": i
            })

            meta = clean_metadata(meta)

            all_documents.append(
                Document(
                    page_content=chunk,
                    metadata=meta
                )
            )

    logger.info(
        "Indexing %d resumes (%d chunks)",
        len(resumes),
        len(all_documents)
    )

    return create_vector_store_from_documents(
        all_documents,
        collection_name=collection_name,
        persist_directory=persist_directory
    )