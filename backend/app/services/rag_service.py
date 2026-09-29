"""RAG knowledge base — chunking + retrieval (§11 of CONTRACT.md).

Embedding path is chosen honestly and always labeled:
- "pgvector" only when DATABASE_URL is Postgres AND the pgvector package is
  importable AND a query-embedding model is available AND chunks actually have
  embeddings. The seed never sets embeddings, so "tfidf" is the honest default.
- "tfidf": TF-IDF cosine similarity in Python (scikit-learn), fit on
  chunks + query.
"""

from __future__ import annotations

import math


def chunk_text(content: str, size: int = 600, overlap: int = 120) -> list[str]:
    """Split content into overlapping chunks (600 chars, 120 overlap)."""
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


def index_knowledge_doc(db, doc) -> None:
    """Chunk a KnowledgeDoc's content and store KnowledgeChunks (TF-IDF path).

    Embeddings are left None; the doc is marked INDEXED via the TF-IDF path
    (honest labeling — see embedding_status / embedding_path).
    """
    from app.models.models import KnowledgeChunk

    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
    chunks = chunk_text(doc.content or "")
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


def search(db, query: str, top_k: int = 5) -> dict:
    """Retrieve top-k chunks for a query.

    Returns {"results": [{doc_id, doc_title, chunk, score}], "embedding_path": ...}.
    """
    from app.models.models import KnowledgeChunk, KnowledgeDoc

    chunks = (
        db.query(KnowledgeChunk)
        .order_by(KnowledgeChunk.doc_id, KnowledgeChunk.chunk_index)
        .all()
    )
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
        results.append(
            {
                "doc_id": chunk.doc_id,
                "doc_title": d.title if d else "",
                "chunk": chunk.content,
                "score": round(float(score), 4),
            }
        )
    return {"results": results, "embedding_path": path}
