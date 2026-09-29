# Document Verification SOP — Demo Reference

> DEMO DOCUMENT — fictional content for prototype demonstration.

## 1. Purpose
Standard operating procedure for verifying bidder documents in the demo
platform. Fictional; for prototype demonstration only.

## 2. Intake
- Accept PDF/JPEG/PNG up to 25 MB; reject other types with a clear error.
- Compute SHA-256 of every uploaded file for tamper evidence.

## 3. Text extraction
- Use PyMuPDF first; fall back to OCR only for image-based PDFs.
- If OCR is unavailable and no text is extractable, mark the document FAILED.

## 4. Classification
- Auto-classify by keyword rules (e.g. "GSTIN" → GST certificate).
- Officers may correct the classification; corrections are audited.

## 5. Field extraction
- Regex pass first (identifiers, dates, amounts, percentages).
- Mock-LLM pass over labeled lines ("Legal Name:", "Turnover:", ...).
- Highest confidence wins per field; ties prefer regex.

## 6. Portal verification
- Verify identifiers against mock government portals; label every check
  "MOCK GOVERNMENT VERIFICATION".
- UNAVAILABLE or NOT_FOUND never becomes an automatic PASS/FAIL.

## 7. Evidence and audit
- Every compliance result links document, page, field value, rule and source.
- All processing steps write hash-chained audit entries.

*End of demo document.*
