import tempfile
import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

from config import get_logger, OPENAI_API_KEY

logger = get_logger(__name__)


def load_pdf_document(file):
    """Load PDF file from an uploaded file object."""
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            temp_file_path = tmp.name
        loader = PyPDFLoader(temp_file_path)
        documents = loader.load()
        logger.info(
            "log-30 resume_parser.py | Completed PDF loading | docs=%d total_chars=%d",
            len(documents),
            sum(len(doc.page_content) for doc in documents),
        )
        return documents
    except Exception:
        logger.exception("log-31 resume_parser.py | PDF loading failed.")
        raise
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def load_docx_document(file):
    """Load DOCX file from an uploaded file object."""
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            temp_file_path = tmp.name
        loader = Docx2txtLoader(temp_file_path)
        documents = loader.load()
        logger.info(
            "log-32 resume_parser.py | Completed DOCX loading | docs=%d total_chars=%d",
            len(documents),
            sum(len(doc.page_content) for doc in documents),
        )
        return documents
    except Exception:
        logger.exception("log-33 resume_parser.py | DOCX loading failed.")
        raise
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


# Try to initialize spaCy model for richer metadata extraction; fall back if unavailable
try:
    import spacy
    try:
        _nlp = spacy.load("en_core_web_sm")
        logger.info("log-40 resume_parser.py | spaCy model loaded for metadata extraction")
    except Exception:
        _nlp = None
        logger.info("log-41 resume_parser.py | spaCy model not available; falling back to heuristics")
except Exception:
    _nlp = None
    logger.info("log-42 resume_parser.py | spaCy not installed; using heuristic metadata extraction")


def extract_resume_metadata(text: str) -> dict:
    """Extract lightweight metadata from resume text: email, years_experience, current_title, location.

    Uses spaCy NER when available, otherwise falls back to simple regex/heuristics.
    """
    meta = {"email": None, "years_experience": None, "current_title": None, "location": None}

    try:
        # email (regex is reliable)
        m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if m:
            meta["email"] = m.group(0)

        # years of experience: pattern like '5 years', '5+ years'
        ym = re.search(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", text, re.IGNORECASE)
        if ym:
            try:
                meta["years_experience"] = int(ym.group(1))
            except Exception:
                meta["years_experience"] = None

        # If spaCy available, use entities to extract location/title candidates
        if _nlp:
            doc = _nlp(text)
            # location: GPE/LOC
            gpes = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
            if gpes:
                meta["location"] = gpes[0]

            # Try to detect a current title from early document lines or ORG/PERSON context
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for l in lines[:8]:
                if 2 <= len(l.split()) <= 7:
                    keywords = ["engineer", "developer", "manager", "lead", "director", "architect", "consultant", "analyst", "scientist"]
                    if any(k in l.lower() for k in keywords):
                        meta["current_title"] = l
                        break

            # fallback: look for strong noun chunks or ORG as title if not found
            if not meta.get("current_title"):
                for ent in doc.ents:
                    if ent.label_ in ("ORG", "PERSON") and 1 < len(ent.text.split()) <= 6:
                        meta["current_title"] = ent.text
                        break

        else:
            # fallback heuristics when spaCy not available
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                for l in lines[:6]:
                    if 2 <= len(l.split()) <= 6:
                        keywords = ["engineer", "developer", "manager", "lead", "director", "architect", "consultant", "analyst"]
                        if any(k in l.lower() for k in keywords):
                            meta["current_title"] = l
                            break

            loc = None
            for l in lines[:20]:
                if l.lower().startswith("location:"):
                    loc = l.split(":", 1)[1].strip()
                    break
            if not loc:
                lm = re.search(r"([A-Za-z .'-]+),\s*([A-Za-z]{2}|[A-Za-z .'-]+)", text)
                if lm:
                    loc = lm.group(0)
            meta["location"] = loc

    except Exception:
        pass

    return meta


def load_document(file, filename: str) -> str:
    """
    Unified document loading interface.
    Returns extracted text as string for backward compatibility.
    """
    filename = filename.lower()

    try:
        if filename.endswith('.pdf'):
            documents = load_pdf_document(file)
        elif filename.endswith('.docx'):
            documents = load_docx_document(file)
        else:
            raise ValueError(f"Unsupported file format: {filename}")

        # Combine all document pages into single text
        text = "\n".join(doc.page_content for doc in documents)
        logger.info("log-33 resume_parser.py | Document loaded successfully | format=%s chars=%d",
                   filename.split('.')[-1], len(text))
        return text.strip()

    except Exception as exc:
        logger.exception("log-34 resume_parser.py | Document loading failed | filename=%s error=%s",
                        filename, str(exc))
        raise


def split_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[str]:
    """Split long text into smaller chunks using LangChain splitters."""
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        keep_separator=True,
    )
    chunks = splitter.split_text(text)
    logger.info(
        "log-35 resume_parser.py | Split text into %d chunks | chunk_size=%d chunk_overlap=%d total_chars=%d",
        len(chunks),
        chunk_size,
        chunk_overlap,
        len(text),
    )
    return chunks


def create_vector_store_from_documents(documents: list[Document], collection_name: str = "resume_chunks", persist_directory: str = None) -> Chroma:
    """Create and return a Chroma vector store from LangChain Documents.

    Documents should already include metadata (e.g., resume_id, filename).
    """
    embeddings = OpenAIEmbeddings(
        api_key=OPENAI_API_KEY,
        model="text-embedding-3-small"
    )

    vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=persist_directory
    )

    if persist_directory:
        vector_store.persist()
        logger.info("log-36 resume_parser.py | Persisted vector store to %s", persist_directory)
    else:
        logger.info("log-36 resume_parser.py | Created in-memory vector store")

    logger.info(
        "log-36.1 resume_parser.py | Vector store created with %d documents",
        len(documents)
    )
    return vector_store


def create_vector_store(documents: list, collection_name: str = "resume_chunks", persist_directory: str = None) -> Chroma:
    """Create a vector store from either a list of LangChain `Document` objects or plain text chunks.

    For backward compatibility, this will wrap plain string chunks into `Document` instances with
    minimal metadata before delegating to `create_vector_store_from_documents`.
    """
    # If caller passed plain strings (chunks), wrap them into Document objects
    wrapped = []
    for i, d in enumerate(documents or []):
        if isinstance(d, Document):
            wrapped.append(d)
        elif isinstance(d, str):
            wrapped.append(Document(page_content=d, metadata={"chunk_index": i}))
        else:
            # Attempt to coerce dict-like objects with page_content
            try:
                pc = d.get("page_content") if hasattr(d, "get") else None
                if pc:
                    wrapped.append(Document(page_content=pc, metadata=d.get("metadata") if hasattr(d, "get") else {}))
                else:
                    # Fallback: convert to string
                    wrapped.append(Document(page_content=str(d), metadata={"chunk_index": i}))
            except Exception:
                wrapped.append(Document(page_content=str(d), metadata={"chunk_index": i}))

    return create_vector_store_from_documents(wrapped, collection_name=collection_name, persist_directory=persist_directory)


def index_resumes(resumes: list[dict], collection_name: str = "resumes_global", persist_directory: str = None, chunk_size: int = 1200, chunk_overlap: int = 200) -> Chroma:
    """Index multiple resumes into a single Chroma collection.

    `resumes` is a list of dicts: {"resume_id": str, "filename": str, "text": str}
    Returns the created Chroma vector store.
    """
    all_documents = []
    for r in resumes:
        resume_id = str(r.get("resume_id"))
        filename = r.get("filename", "")
        text = r.get("text", "")
        # extract lightweight metadata from the full resume text
        resume_meta = extract_resume_metadata(text)
        resume_meta.update({"resume_id": resume_id, "filename": filename})
        chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for i, chunk in enumerate(chunks):
            meta = dict(resume_meta)
            meta.update({"chunk_index": i})
            all_documents.append(Document(page_content=chunk, metadata=meta))

    logger.info("log-36.2 resume_parser.py | Indexing %d resumes (%d chunks total)", len(resumes), len(all_documents))
    return create_vector_store_from_documents(all_documents, collection_name=collection_name, persist_directory=persist_directory)


def inspect_vector_store(vector_store: Chroma) -> dict:
    """Inspect contents of the vector store for debugging."""
    try:
        # Get collection info
        collection = vector_store._collection
        count = collection.count()
        
        # Get sample documents (first 3)
        results = collection.get(limit=3, include=["documents", "metadatas"])
        sample_docs = results.get("documents", [])[:3]
        
        info = {
            "total_chunks": count,
            "collection_name": collection.name,
            "sample_chunks": [doc[:100] + "..." if len(doc) > 100 else doc for doc in sample_docs]
        }
        
        logger.info("log-38 resume_parser.py | Vector store inspection: %d chunks", count)
        return info
    except Exception as e:
        logger.error("log-39 resume_parser.py | Failed to inspect vector store: %s", str(e))
        return {"error": str(e)}


def retrieve_relevant_chunks(vector_store: Chroma, query: str, k: int = 5) -> list[str]:
    """Retrieve top-k relevant chunks from vector store based on query."""
    docs = vector_store.similarity_search(query, k=k)
    chunks = [doc.page_content for doc in docs]

    logger.info(
        "log-37 resume_parser.py | Retrieved %d chunks for query: %s",
        len(chunks),
        query[:50] + "..." if len(query) > 50 else query
    )
    return chunks


def retrieve_relevant_resumes(
    vector_store: Chroma,
    query: str,
    top_n: int = 10,
    top_k_per_resume: int = 3,
    top_k_total: int = 200,
    min_years: int | None = None,
    location_contains: str | None = None,
    role_contains: str | None = None,
    semantic_weight: float = 0.7,
    years_weight: float = 0.2,
    role_weight: float = 0.05,
    location_weight: float = 0.05,
    min_chunk_score: float = 0.15,
) -> list[dict]:
    """Retrieve and rank resumes from a vector store for a given query.

    Returns a list of resume dicts: {resume_id, filename, score, top_snippets}
    """
    def _matches_filters(meta: dict) -> bool:
        if not meta:
            return True
        if min_years is not None:
            y = meta.get("years_experience")
            if y is None:
                return False
            try:
                if int(y) < int(min_years):
                    return False
            except Exception:
                return False
        if location_contains:
            loc = (meta.get("location") or "")
            if location_contains.lower() not in loc.lower():
                return False
        if role_contains:
            title = (meta.get("current_title") or "")
            if role_contains.lower() not in title.lower():
                return False
        return True

    try:
        # Try to get documents with relevance scores
        results = vector_store.similarity_search_with_relevance_scores(query, k=top_k_total)
        # results: list of (Document, score)
        scored = []
        for doc, score in results:
            meta = doc.metadata or {}
            # Apply filters at chunk level (skip chunks whose resume metadata does not match)
            if not _matches_filters(meta):
                continue
            # Ignore low-similarity chunks to reduce noise
            if score is None:
                continue
            try:
                if float(score) < float(min_chunk_score):
                    continue
            except Exception:
                pass
            scored.append({
                "resume_id": meta.get("resume_id"),
                "filename": meta.get("filename"),
                "text": doc.page_content,
                "score": float(score),
                "chunk_score": float(score),
                "metadata": meta,
            })
    except Exception:
        # Fallback: no scores available, perform plain similarity search and assign equal score
        docs = vector_store.similarity_search(query, k=top_k_total)
        scored = []
        for d in docs:
            meta = d.metadata or {}
            if not _matches_filters(meta):
                continue
            # For similarity_search fallback, treat score as 1.0 but still apply min_chunk_score
            if 1.0 < float(min_chunk_score):
                continue
            scored.append({
                "resume_id": meta.get("resume_id"),
                "filename": meta.get("filename"),
                "text": d.page_content,
                "score": 1.0,
                "chunk_score": 1.0,
                "metadata": meta,
            })

    # Group by resume_id and aggregate top scores
    groups = {}
    for item in scored:
        rid = str(item.get("resume_id") or "")
        if rid not in groups:
            groups[rid] = {"filename": item.get("filename"), "scores": [], "snippets": [], "resume_metadata": item.get("metadata", {})}
        groups[rid]["scores"].append(item.get("score", 0.0))
        groups[rid]["snippets"].append({
            "text": item.get("text"),
            "chunk_score": item.get("chunk_score", item.get("score", 0.0)),
            "metadata": item.get("metadata", {}),
        })

    ranked = []
    for rid, data in groups.items():
        top_scores = sorted(data["scores"], reverse=True)[:top_k_per_resume]
        semantic_agg = float(sum(top_scores) / len(top_scores)) if top_scores else 0.0
        top_snippets = data["snippets"][0:top_k_per_resume]
        ranked.append({
            "resume_id": rid,
            "filename": data.get("filename"),
            "semantic_score": semantic_agg,
            "top_snippets": top_snippets,
            "resume_metadata": data.get("resume_metadata", {}),
        })

    # Normalize semantic scores to 0-1
    sem_scores = [r["semantic_score"] for r in ranked]
    min_s = min(sem_scores) if sem_scores else 0.0
    max_s = max(sem_scores) if sem_scores else 1.0
    span = max_s - min_s if max_s - min_s > 0 else 1.0

    # Prepare years normalization
    years_vals = []
    for r in ranked:
        y = (r.get("resume_metadata") or {}).get("years_experience")
        try:
            years_vals.append(int(y))
        except Exception:
            years_vals.append(0)
    max_year = max(years_vals) if years_vals else 0
    if max_year <= 0:
        max_year = 1

    # Compute final weighted score
    for r in ranked:
        sem_norm = (r["semantic_score"] - min_s) / span
        meta = r.get("resume_metadata") or {}
        try:
            y = int(meta.get("years_experience") or 0)
        except Exception:
            y = 0
        years_norm = (y / max_year) if max_year > 0 else 0.0
        role_match = 0.0
        if role_contains and meta.get("current_title"):
            if role_contains.lower() in (meta.get("current_title") or "").lower():
                role_match = 1.0
        location_match = 0.0
        if location_contains and meta.get("location"):
            if location_contains.lower() in (meta.get("location") or "").lower():
                location_match = 1.0

        final = (
            semantic_weight * sem_norm
            + years_weight * years_norm
            + role_weight * role_match
            + location_weight * location_match
        )
        r["final_score"] = final
        r["score"] = final

    ranked_sorted = sorted(ranked, key=lambda x: x["final_score"], reverse=True)[:top_n]

    # Detailed debug logging to help diagnose unexpected high scores
    for r in ranked_sorted:
        try:
            snippets_info = []
            for s in (r.get('top_snippets') or []):
                text = s.get('text', '')[:80].replace('\n', ' ')
                snippets_info.append(
                  f"score={s.get('chunk_score', 0.0):.4f} text={text}"
    )
        except Exception:
            snippets_info = []
        logger.debug(
            "log-37.1 resume_parser.py | Resume %s (%s) semantic=%.4f final=%.4f snippets=%s",
            r.get('resume_id'),
            r.get('filename'),
            float(r.get('semantic_score', 0.0)),
            float(r.get('final_score', r.get('score', 0.0))),
            snippets_info,
        )
    logger.info("log-37.1 resume_parser.py | Ranked %d resumes for query", len(ranked_sorted))
    return ranked_sorted


def load_vector_store(collection_name: str = "resumes_global", persist_directory: str = None) -> Chroma:
    """Load an existing Chroma vector store from disk (persist_directory).

    Returns a Chroma vector store instance connected to the persisted collection.
    """
    embeddings = OpenAIEmbeddings(
        api_key=OPENAI_API_KEY,
        model="text-embedding-3-small",
    )

    # Construct Chroma using the same persist directory and collection name
    vector_store = Chroma(
        persist_directory=persist_directory,
        collection_name=collection_name,
        embedding=embeddings,
    )
    logger.info("log-36.3 resume_parser.py | Loaded vector store %s from %s", collection_name, persist_directory)
    return vector_store