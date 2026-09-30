"""Source-grounded RAG knowledge base: integrity, chunking, traceability.

- Manifest completeness: every document carries title, issuing authority,
  source URL, publication/effective dates, version, retrieval date and
  AUTHORITATIVE level; every file exists on disk.
- Structural chunking: one chunk per Rule/Clause/Paragraph section; each
  chunk starts with its section header (Document -> Section -> Text).
- Seeding: fictional demo policy documents are removed from the DB and
  never re-seeded; only manifest documents are indexed (idempotent).
- Retrieval: citable records trace title -> authority -> section ->
  excerpt -> official source URL; the retrieval path is honestly labeled.
"""
from app.models.models import KnowledgeChunk, KnowledgeDoc
from app.seed.seed_data import OLD_FICTIONAL_POLICY_TITLES, _seed_knowledge
from app.services import rag_service
from app.services.rag_service import (
    chunk_structured,
    doc_metadata,
    load_manifest,
    parse_section,
)

MII_TITLE = (
    "Public Procurement (Preference to Make in India), Order 2017 — "
    "Revision dated 19.07.2024"
)
GFR_TITLE = "General Financial Rules, 2017 — Procurement Provisions"
UDYAM_TITLE = "Udyam Registration — MSME Classification (Ministry of MSME)"
DEBAR_TITLE = "Debarment of Firms from Bidding — DoE Guidelines"

REQUIRED_META_KEYS = {
    "title",
    "authority",
    "source_url",
    "document_type",
    "publication_date",
    "effective_date",
    "version",
    "retrieval_date",
    "authority_level",
}


def test_manifest_complete_and_authoritative():
    manifest = load_manifest()
    assert len(manifest) == 4, f"expected 4 authoritative docs, got {len(manifest)}"
    for filename, meta in manifest.items():
        missing = REQUIRED_META_KEYS - set(meta.keys())
        assert not missing, f"{filename} missing metadata: {missing}"
        assert meta["authority_level"] == "AUTHORITATIVE", filename
        assert meta["source_url"].startswith("https://"), filename
        assert (rag_service._policies_dir() / filename).is_file(), filename
        assert meta.get("sections"), f"{filename} has no section descriptions"


def test_structural_chunking_one_chunk_per_section():
    from pathlib import Path

    policies = rag_service._policies_dir()
    for filename in load_manifest():
        content = (policies / filename).read_text(encoding="utf-8")
        expected_sections = content.count("\n## ")
        chunks = chunk_structured(content)
        assert len(chunks) == expected_sections, (
            f"{filename}: {len(chunks)} chunks != {expected_sections} sections"
        )
        for chunk in chunks:
            assert chunk.startswith("## "), f"{filename}: chunk lost its header"
            section, excerpt = parse_section(chunk)
            assert section, f"{filename}: empty section ref"
            assert excerpt, f"{filename}: empty excerpt for {section!r}"
            # No disconnected provisions merged: one section per chunk.
            assert chunk.count("\n## ") == 0, f"{filename}: merged sections"


def test_seed_removes_fictional_and_indexes_authoritative(db):
    # Simulate a database seeded with the old fictional demo policies.
    for title in list(OLD_FICTIONAL_POLICY_TITLES)[:3]:
        doc = KnowledgeDoc(title=title, doc_type="POLICY", version="1.0",
                           content="## Fake section\nFictional demo text.")
        db.add(doc)
    db.commit()

    assert _seed_knowledge(db) == 4

    remaining = [d.title for d in db.query(KnowledgeDoc).all()]
    for title in OLD_FICTIONAL_POLICY_TITLES:
        assert title not in remaining, f"fictional doc survived seeding: {title}"
    for title in (MII_TITLE, GFR_TITLE, UDYAM_TITLE, DEBAR_TITLE):
        assert title in remaining, f"authoritative doc missing: {title}"

    for doc in db.query(KnowledgeDoc).all():
        assert doc.embedding_status == "INDEXED"
        n = db.query(KnowledgeChunk).filter_by(doc_id=doc.id).count()
        assert n == doc.chunk_count > 0
        for chunk in db.query(KnowledgeChunk).filter_by(doc_id=doc.id).all():
            assert chunk.content.startswith("## ")
            assert chunk.embedding is None  # TF-IDF path: no embeddings

    # Idempotent: second run changes nothing.
    assert _seed_knowledge(db) == 0


def test_search_mii_traceability(db):
    _seed_knowledge(db)
    res = rag_service.search(
        db,
        "local content minimum 50 percent Class-I local supplier",
        top_k=3,
        doc_titles=[MII_TITLE],
    )
    assert res["embedding_path"] == "tfidf"
    hit = res["results"][0]
    assert hit["doc_title"] == MII_TITLE
    assert "DPIIT" in hit["authority"]
    assert hit["section"].startswith("Para 5"), hit["section"]
    assert "dpiit.gov.in" in hit["source_url"]
    assert "19.07.2024" in hit["version"]
    assert hit["excerpt"], "excerpt must be non-empty"
    assert hit["why_relevant"], "why_relevant must be non-empty"
    assert hit["score"] >= 0.10


def test_search_debarment_traceability(db):
    _seed_knowledge(db)
    res = rag_service.search(
        db,
        "bidder debarred convicted offence code of integrity breach",
        top_k=3,
        doc_titles=[GFR_TITLE, DEBAR_TITLE],
    )
    hit = res["results"][0]
    assert "Department of Expenditure" in hit["authority"]
    assert hit["source_url"].startswith("https://")
    assert any("Rule 151" in r["section"] for r in res["results"]), [
        r["section"] for r in res["results"]
    ]
    # Citation traces: UI -> chunk -> doc -> official URL -> exact clause.
    meta = doc_metadata(hit["doc_title"])
    assert meta["authority_level"] == "AUTHORITATIVE"


def test_search_scoped_to_configured_docs(db):
    _seed_knowledge(db)
    res = rag_service.search(db, "local content supplier", doc_titles=[UDYAM_TITLE])
    assert res["results"], "scoped search returned nothing"
    assert {r["doc_title"] for r in res["results"]} == {UDYAM_TITLE}
    # Unknown documents never leak into scoped retrieval.
    res = rag_service.search(db, "anything", doc_titles=["No Such Document"])
    assert res["results"] == []


def test_embedding_path_honestly_labeled(db):
    _seed_knowledge(db)
    res = rag_service.search(db, "procurement")
    # SQLite has no embeddings and no pgvector — the honest label is tfidf.
    assert res["embedding_path"] == "tfidf"
