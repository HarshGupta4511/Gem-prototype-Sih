"""Small PDF helpers shared by seed scripts and tests."""
from __future__ import annotations


def pdf_page_count(path: str) -> int:
    """Return the number of pages in the PDF at *path*."""
    import fitz  # lazy: PyMuPDF

    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()
