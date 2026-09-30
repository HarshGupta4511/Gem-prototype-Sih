"""RAG knowledge base — structural chunking + retrieval.

Chunking is structural, never random: policy documents are authored with one
markdown ``## `` section per Rule / Sub-rule / Clause / Paragraph, and each
chunk preserves Document -> Rule/Section/Clause -> Text so citations always
point at the actual provision.

Embedding path is chosen honestly and always labeled:
- "pgvector" only when DATABASE_URL is Postgres AND the pgvector package is
  importable AND a query-embedding model is available AND chunks actually have
  embeddings. The seed never sets embeddings, so "tfidf" is the honest default.
- "tfidf": TF-IDF cosine similarity in Python (scikit-learn), fit on
  chunks + query.

The architecture stays extensible: adding an embedding model later only needs
the chunk ``embedding`` column populated — ``search()`` already branches on it.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


def chunk_text(content: str, size: int = 600, overlap: int = 120) -> list[str]:
    """Legacy char-based chunker (kept as fallback for unstructured docs)."""
    text = content or ""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(size - overlap, 1)
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += step
    return chunks


def chunk_structured(content: str) -> list[str]:
    """Split on markdown ``## `` section headers (Rule / Clause / Paragraph).

    Each returned chunk starts with its section header line, so the chunk
    itself preserves Document -> Section -> Text. Documents without any
    ``## `` header fall back to :func:`chunk_text`.
    """
    text = (content or "").strip()
    if not text:
        return []
    parts = re.split(r"(?m)^## ", text)
    chunks = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if i == 0:
            # Preamble before the first section (doc title / source note) is
            # metadata, not a citable provision — skip it as a chunk.
            continue
        chunks.append("## " + part)
    if not chunks:
        return chunk_text(text)
    return chunks


def parse_section(chunk_content: str) -> tuple[str, str]:
    """Split a structural chunk into (section_ref, excerpt)."""
    text = (chunk_content or "").strip()
    if text.startswith("## "):
        header, _, body = text.partition("\n")
        return header[3:].strip(), body.strip()
    first, _, rest = text.partition("\n")
    return first.strip(), rest.strip()


_MANIFEST_CACHE: dict | None = None


def _policies_dir() -> Path:
    # Same authoritative collection as the seeder (backend/app/seed/policies).
    # The stale ~/workspace/cpcl-bidverify copy is deliberately not consulted.
    return Path(__file__).resolve().parent.parent / "seed" / "policies"


def load_manifest() -> dict:
    """Load policies/manifest.json (metadata for every authoritative document).

    Cached per process. Returns {} when the manifest is absent.
    """
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    _MANIFEST_CACHE = {}
    try:
        path = _policies_dir() / "manifest.json"
        if path.is_file():
            _MANIFEST_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _MANIFEST_CACHE = {}
    return _MANIFEST_CACHE


def doc_metadata(doc_title: str) -> dict:
    """Metadata for a document title from the manifest ({} when unknown)."""
    for meta in load_manifest().values():
        if meta.get("title") == doc_title:
            return meta
    return {}


def index_knowledge_doc(db, doc) -> None:
    """Chunk a KnowledgeDoc's content and store KnowledgeChunks (TF-IDF path).

    Uses structural chunking (one chunk per Rule/Clause/Paragraph section).
    Embeddings are left None; the doc is marked INDEXED via the TF-IDF path
    (honest labeling — see embedding_status / embedding_path).
    """
    from app.models.models import KnowledgeChunk

    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
    chunks = chunk_structured(doc.content or "")
    for i, text in enumerate(chunks):
        db.add(
            KnowledgeChunk(doc_id=doc.id, chunk_index=i, content=text, embedding=None)
        )
    doc.chunk_count = len(chunks)
    doc.embedding_status = "INDEXED"
    db.commit()


def _embedding_path(db, chunks) -> str:
    """Decide the retrieval path, honestly labeled."""
    try:
        from app.core.config import settings

        db_url = str(getattr(settings, "DATABASE_URL", "") or "")
    except Exception:
        db_url = ""
    if not db_url.startswith("postgres"):
        return "tfidf"
    try:
        import pgvector  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        return "tfidf"
    if any(getattr(c, "embedding", None) for c in chunks):
        return "pgvector"
    return "tfidf"


def _tfidf_search(chunks, query: str):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [c.content for c in chunks] + [query]
    matrix = TfidfVectorizer().fit_transform(corpus)
    sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    return list(zip(chunks, (float(s) for s in sims)))


def _pgvector_search(chunks, query: str):
    """Cosine similarity in Python between the query embedding and stored
    chunk embeddings (pgvector column read as a list)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-m3")
    qv = model.encode(query).tolist()

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    scored = []
    for c in chunks:
        emb = c.embedding
        if emb is None:
            continue
        vec = list(emb) if not isinstance(emb, list) else emb
        if len(vec) != len(qv):
            continue
        scored.append((c, cosine(qv, vec)))
    return scored


def search(db, query: str, top_k: int = 5, doc_titles: list[str] | None = None) -> dict:
    """Retrieve top-k chunks for a query.

    ``doc_titles`` optionally scopes the corpus to specific documents (used
    to restrict retrieval to the authoritative sources configured for the
    finding's topic — topics with no verified source never reach retrieval).

    Returns {"results": [...], "embedding_path": ...} where each result is a
    citable record: policy title, issuing authority, rule/section/clause,
    excerpt, source URL, document/version dates, and relevance score.
    """
    from app.models.models import KnowledgeChunk, KnowledgeDoc

    q = (
        db.query(KnowledgeChunk)
        .order_by(KnowledgeChunk.doc_id, KnowledgeChunk.chunk_index)
    )
    if doc_titles:
        wanted = set(doc_titles)
        doc_ids = [
            d.id
            for d in db.query(KnowledgeDoc).filter(KnowledgeDoc.title.in_(wanted)).all()
        ]
        if not doc_ids:
            return {"results": [], "embedding_path": _embedding_path(db, [])}
        q = q.filter(KnowledgeChunk.doc_id.in_(doc_ids))
    chunks = q.all()
    path = _embedding_path(db, chunks)
    if not chunks:
        return {"results": [], "embedding_path": path}

    scored = _pgvector_search(chunks, query) if path == "pgvector" else _tfidf_search(chunks, query)
    scored.sort(key=lambda item: item[1], reverse=True)

    doc_ids = {c.doc_id for c, _ in scored}
    docs = {}
    if doc_ids:
        docs = {
            d.id: d
            for d in db.query(KnowledgeDoc).filter(KnowledgeDoc.id.in_(doc_ids)).all()
        }

    results = []
    for chunk, score in scored[: max(top_k, 0)]:
        d = docs.get(chunk.doc_id)
        title = d.title if d else ""
        meta = doc_metadata(title)
        section, excerpt = parse_section(chunk.content)
        why = (meta.get("sections") or {}).get(section, "")
        results.append(
            {
                "doc_id": chunk.doc_id,
                "doc_title": title,
                "title": title,
                "authority": meta.get("authority", ""),
                "source_url": meta.get("source_url", ""),
                "document_type": meta.get("document_type", ""),
                "version": meta.get("version", "") or (d.version if d else ""),
                "publication_date": meta.get("publication_date", ""),
                "effective_date": meta.get("effective_date", ""),
                "retrieval_date": meta.get("retrieval_date", ""),
                "section": section,
                "why_relevant": why,
                "excerpt": excerpt,
                "chunk": chunk.content,
                "score": round(float(score), 4),
            }
        )
    return {"results": results, "embedding_path": path}
