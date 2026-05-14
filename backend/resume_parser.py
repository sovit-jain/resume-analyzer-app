import tempfile
import os
import re

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

from config import get_logger, OPENAI_API_KEY
from typing import Optional

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


# =========================================================
# VECTOR STORE UTILITIES
# =========================================================
def retrieve_relevant_chunks(vector_store, query: str, k: int = 5) -> list[str]:
    """
    Retrieve the top-k most relevant chunks from the given vector store for `query`.
    Returns a list of chunk text strings.
    """
    try:
        docs = vector_store.similarity_search(query, k=k)
    except Exception:
        try:
            docs_with_score = vector_store.similarity_search_with_score(query, k=k)
            docs = [d for d, _ in docs_with_score]
        except Exception:
            logger.exception("Failed to run similarity search on vector store")
            return []

    results = []
    for d in docs or []:
        try:
            results.append(d.page_content)
        except Exception:
            results.append(str(d))

    return results


def inspect_vector_store(vector_store) -> dict:
    """Return a small inspection dict for debugging/logging purposes."""
    info = {"type": type(vector_store).__name__}
    try:
        if hasattr(vector_store, "_collection"):
            coll = getattr(vector_store, "_collection")
            try:
                info["doc_count"] = coll.count()
            except Exception:
                info["doc_count"] = getattr(coll, "get_count", lambda: None)()
        elif hasattr(vector_store, "persist_directory"):
            info["persist_directory"] = getattr(vector_store, "persist_directory")
    except Exception:
        logger.exception("inspect_vector_store failed")
    return info


# =========================================================
# LOAD & RANK UTILITIES
# =========================================================
def load_vector_store(collection_name: str = "resume_chunks", persist_directory: Optional[str] = None):
    """Load an existing Chroma vector store. Returns the vector store instance."""
    try:
        if persist_directory:
            return Chroma(collection_name=collection_name, persist_directory=persist_directory)
        return Chroma(collection_name=collection_name)
    except Exception:
        try:
            return Chroma(persist_directory=persist_directory, collection_name=collection_name)
        except Exception:
            logger.exception("Failed to load vector store for collection=%s persist=%s", collection_name, persist_directory)
            raise


def retrieve_relevant_resumes(
    vector_store,
    query: str,
    top_n: int = 10,
    min_years: Optional[int] = None,
    location_contains: Optional[str] = None,
    role_contains: Optional[str] = None,
    semantic_weight: float = 0.7,
    years_weight: float = 0.2,
    role_weight: float = 0.05,
    location_weight: float = 0.05,
    semantic_threshold: float = 0.0,
):
    """
    Rank resumes from an indexed vector store for a given query.

    Returns a list of dicts with keys: resume_id, filename, score, top_snippets, resume_metadata
    """
    try:
        try:
            results = vector_store.similarity_search_with_score(query, k=top_n * 5)
        except Exception:
            docs = vector_store.similarity_search(query, k=top_n * 5)
            results = [(d, None) for d in docs]

        # Aggregate per-resume but keep raw similarity values to allow different aggregation strategies
        agg = {}
        for doc, score in results or []:
            meta = getattr(doc, "metadata", {}) or {}
            resume_id = str(meta.get("resume_id", ""))
            filename = meta.get("filename") or meta.get("file") or ""
            if not resume_id:
                continue
            entry = agg.setdefault(resume_id, {
                "resume_id": resume_id,
                "filename": filename,
                "resume_metadata": meta,
                "sim_values": [],
                "hits": 0,
                "snippets": [],
            })

            # Convert distance-like scores to similarity in (0,1], fallback for None
            if score is None:
                entry["sim_values"].append(None)
            else:
                try:
                    val = float(score)
                    sim = 1.0 / (1.0 + abs(val))
                    entry["sim_values"].append(sim)
                except Exception:
                    entry["sim_values"].append(None)

            entry["hits"] += 1
            text = getattr(doc, "page_content", str(doc))
            if text not in entry["snippets"]:
                entry["snippets"].append(text)

        # Compute per-resume semantic signal using max(similarity) to avoid bias toward long resumes
        items = []
        per_resume_sim = {}
        for rid, v in agg.items():
            sims = [s for s in v.get("sim_values", []) if s is not None]
            if sims:
                best_sim = max(sims)
            else:
                # if no numeric similarities available, fall back to normalized hit-count heuristic
                best_sim = min(1.0, v.get("hits", 0) / 5.0) if v.get("hits", 0) > 0 else 0.0
            per_resume_sim[rid] = best_sim

        max_sim_across = max(per_resume_sim.values()) if per_resume_sim else 0.0

        for rid, v in agg.items():
            meta = v.get("resume_metadata") or {}
            # normalize semantic score
            raw_sim = per_resume_sim.get(rid, 0.0)
            sem = (raw_sim / max_sim_across) if max_sim_across > 0 else 0.0

            # Apply semantic threshold filtering early
            if sem < semantic_threshold:
                continue
            meta = v.get("resume_metadata") or {}
            if min_years is not None:
                try:
                    years = int(meta.get("years_experience") or 0)
                except Exception:
                    years = 0
                if years < min_years:
                    continue
            if location_contains:
                loc = (meta.get("location") or "")
                if location_contains.lower() not in loc.lower():
                    continue
            if role_contains:
                title = (meta.get("current_title") or "")
                if role_contains.lower() not in title.lower() and role_contains.lower() not in (v.get("filename") or "").lower():
                    continue
            # sem is already computed above
            try:
                years_val = float(meta.get("years_experience") or 0.0)
            except Exception:
                years_val = 0.0
            years_score = min(years_val / 10.0, 1.0)
            role_score = 1.0 if role_contains and role_contains.lower() in (meta.get("current_title") or "").lower() else 0.0
            location_score = 1.0 if location_contains and location_contains.lower() in (meta.get("location") or "").lower() else 0.0
            final_score = (
                semantic_weight * sem
                + years_weight * years_score
                + role_weight * role_score
                + location_weight * location_score
            )
            items.append({
                "resume_id": rid,
                "filename": v.get("filename"),
                "score": float(final_score),
                "top_snippets": [{"text": s, "metadata": v.get("resume_metadata")} for s in v.get("snippets")[:3]],
                "resume_metadata": v.get("resume_metadata"),
            })

        items.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return items[:top_n]

    except Exception:
        logger.exception("retrieve_relevant_resumes failed")
        return []
