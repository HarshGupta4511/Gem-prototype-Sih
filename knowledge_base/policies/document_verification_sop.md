# Document Verification SOP — Reference (Demo)

> Demo standard operating procedure for the SIH26100 prototype knowledge base.

## 1. Pipeline order
1. Upload & integrity (file type, size, hash).
2. Classification (document type detection; officer may correct).
3. Text extraction (native PDF text first; OCR only for scanned documents).
4. Regex extraction for structured identifiers (PAN, GSTIN, Udyam, CIN, dates, amounts).
5. LLM extraction for semantic fields (names, turnover statements, relationships).
6. Schema validation of all extracted data.
7. Entity resolution across documents (identifier match → normalized name match → fuzzy match).
8. Portal/source verification (mock adapters in demo; authorized APIs in production).
9. Cross-document validation (document vs portal vs declared).
10. Tender-aware rules, scoring, risk, explanation, officer review.

## 2. Confidence handling
- Extraction confidence ≥ 0.85: high. 0.70–0.84: medium. < 0.70: low.
- Low-confidence findings that would otherwise PASS are escalated to REVIEW_REQUIRED.
- Low confidence is always surfaced to the officer; it is never silently converted into a decision.

## 3. Source outages
- If a verification source is unavailable, mark the check UNAVAILABLE and the requirement
  REVIEW_REQUIRED. Never mark PASS or FAIL on an unavailable source.

## 4. Auditability
- Every step writes a hash-chained audit entry. The chain can be verified at any time.
- Officer overrides preserve the original finding and record the officer's reason and evidence.
