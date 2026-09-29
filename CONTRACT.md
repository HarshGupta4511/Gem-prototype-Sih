# CONTRACT — SIH26100 Bid Compliance Verification Platform

Source of truth for the backend and frontend builds. Both tracks implement against this file.
Do not change endpoint paths, field names, or enum values without updating this file.

## 0. Principles (non-negotiable)

1. **VERIFY → EXPLAIN → ASSIST → HUMAN DECIDES.** The system never makes the final
   qualification/disqualification decision. Every AI output ends with:
   "Final decision remains with the Procurement Officer."
2. **Deterministic rules decide; AI explains.** Pass/fail comes from the Python rules engine.
   LLMs only extract ambiguous fields and generate explanations. Never show an unexplained "AI says PASS".
3. **Evidence for everything.** Every compliance result links to document, page, extracted value,
   rule applied, source, and confidence.
4. **Honest mocking.** All government portal data is MOCK and must be labeled
   `is_mock: true` / "MOCK GOVERNMENT VERIFICATION" in the UI. Never imply live government access.
5. **Compliance Score ≠ Risk Level.** Computed independently, displayed separately.
6. **Every major button does real work** — it calls the backend and persists results.

## 1. Runtime & tech decisions

| Concern | Decision |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), python-jose or PyJWT, passlib[bcrypt] |
| DB | `DATABASE_URL` env. Default `sqlite:///./bidverify.db` for local dev/demo. Docker uses `postgresql+psycopg2://bidverify:bidverify@postgres:5432/bidverify`. Schema created via `Base.metadata.create_all` on startup (prototype; documented in README). |
| Vector/RAG | pgvector only when Postgres+pgvector is configured. Otherwise the RAG service falls back to TF-IDF cosine similarity in Python. Retrieval API is identical either way. |
| Embeddings | Pluggable. Try `sentence-transformers` (BGE-M3) if installed, else TF-IDF fallback. Always label which path was used. |
| LLM | Pluggable `LLMProvider`. Default `mock` provider: deterministic heuristic extraction + template explanations, clearly labeled `"provider": "mock-llm-demo"`. If `OPENAI_API_KEY` is set, an OpenAI-compatible provider may be used; output still validated against Pydantic schemas. |
| OCR | PaddleOCR if installed. PyMuPDF is tried first; OCR only for image-based PDFs. If OCR is unavailable and a PDF has no selectable text → document marked FAILED with error `OCR_UNAVAILABLE`, compliance treats as REVIEW_REQUIRED (never silent PASS/FAIL). |
| PDF text | PyMuPDF (`fitz`) |
| Report PDF | reportlab |
| File storage | Local `backend/uploads/` (gitignored). Served via authenticated `GET /api/documents/{id}/file`. |
| Ports | Backend `8000`, frontend dev `5173`. API base path `/api`. Frontend uses `VITE_API_URL` (default `http://localhost:8000/api`). |
| CORS | Allow `http://localhost:5173` and `http://localhost:3000`. |
| Money | Integer INR (paise are overkill). `estimated_value_inr`, `turnover_inr` are integers. |
| Time | UTC ISO-8601. |

## 2. Auth & users

Roles: `PROCUREMENT_OFFICER`, `VERIFIER`, `AUDITOR`, `ADMIN`.

- `POST /api/auth/login` `{email, password}` → `{access_token, token_type: "bearer", user}`
- `POST /api/auth/demo` `{}` → logs in as the demo Procurement Officer (powers "Continue with Demo")
- `GET /api/auth/me` → current user (auth required)

`user = {id, name, email, role, department, created_at}`

Seed users (password `Demo@123`):
- `officer@demo.cpcl.in` — Demo Officer — PROCUREMENT_OFFICER — Procurement
- `verifier@demo.cpcl.in` — Demo Verifier — VERIFIER — Verification
- `auditor@demo.cpcl.in` — Demo Auditor — AUDITOR — Audit
- `admin@demo.cpcl.in` — Demo Admin — ADMIN — IT

Permissions: officer/admin → decisions, overrides, clarifications, tender CRUD.
verifier → run verification, process documents. auditor → read-only + audit verify.
Enforce on mutating endpoints; frontend hides actions by role.

## 3. Enums (exact strings)

- `RequirementStatus`: `PASS` `FAIL` `MISSING` `EXPIRED` `MISMATCH` `REVIEW_REQUIRED` `NOT_APPLICABLE`
- `RiskLevel`: `LOW` `MEDIUM` `HIGH` `CRITICAL`
- `VerificationStatus`: `VERIFIED` `MISMATCH` `NOT_FOUND` `EXPIRED` `UNAVAILABLE` `REVIEW_REQUIRED`
- `BidStatus`: `DRAFT` `SUBMITTED` `UNDER_REVIEW` `APPROVED` `REJECTED` `ESCALATED` `CLARIFICATION_REQUESTED`
- `DocProcessingStatus`: `UPLOADED` `PROCESSING` `PROCESSED` `FAILED`
- `DocumentType`: `PAN_CERTIFICATE` `GST_CERTIFICATE` `GST_RETURN` `UDYAM_CERTIFICATE` `ITR` `TURNOVER_CERTIFICATE` `EXPERIENCE_CERTIFICATE` `OEM_AUTHORIZATION` `EPFO_CERTIFICATE` `ESIC_CERTIFICATE` `MII_DECLARATION` `STARTUP_INDIA_CERTIFICATE` `NSIC_CERTIFICATE` `DIGILOCKER_DOCUMENT` `AUDITED_FINANCIAL_STATEMENT` `OTHER`
- `ExtractionMethod`: `REGEX` `OCR` `LLM` `MANUAL`
- `RuleType`: `EXISTENCE` `EQUALITY` `MATCH` `MINIMUM` `MAXIMUM` `DATE_VALIDITY` `DATE_RANGE` `CONTAINS` `BOOLEAN` `REGISTRATION_STATUS` `IDENTITY_MATCH` `DOCUMENT_REQUIRED` `CUSTOM_RULE`
- `OfficerDecision`: `APPROVE` `REJECT` `ESCALATE` `REQUEST_CLARIFICATION`
- `AdapterSource`: `GSTN` `UDYAM` `PAN_IT` `MCA21` `EPFO` `ESIC` `STARTUP_INDIA` `NSIC` `DIGILOCKER` `BLACKLIST`
- `AuditAction`: `LOGIN` `TENDER_CREATED` `BID_SUBMITTED` `DOCUMENT_UPLOADED` `DOCUMENT_PROCESSED` `CLASSIFICATION_CORRECTED` `VERIFICATION_RUN` `COMPLIANCE_EVALUATED` `RISK_ASSESSED` `RECOMMENDATION_GENERATED` `OFFICER_DECISION` `OVERRIDE_RECORDED` `CLARIFICATION_SENT` `REPORT_GENERATED` `AUDIT_VERIFIED` `KNOWLEDGE_UPDATED`

## 4. Data model

**users** — id, name, email (unique), password_hash, role, department, created_at

**tenders** — id, tender_number (unique), title, organization, department, description (text),
issue_date, closing_date, estimated_value_inr, status (`DRAFT`/`OPEN`/`CLOSED`/`AWARDED`), created_by, created_at

**tender_requirements** — id, tender_id (FK), requirement_name, category
(`STATUTORY`|`FINANCIAL`|`EXPERIENCE`|`TECHNICAL`|`REGISTRATION`|`LOCAL_CONTENT`|`OEM`|`INTEGRITY`|`DOCUMENT`),
description, mandatory (bool), rule_type, rule_config (JSON, see §7), threshold (string, display),
expected_value (string, display), verification_source (nullable AdapterSource),
weight (float), policy_reference (string, nullable), created_at

**bidders** — id, tender_id (FK), legal_name, trade_name, pan, gstin, udyam, cin,
registered_address, contact_name, contact_email, contact_phone, bid_status, created_at

**bid_submissions** — id, tender_id (FK), bidder_id (FK, unique per tender), submitted_at,
status, compliance_score (float, nullable), risk_level (nullable), risk_reasons (JSON list),
risk_score (float, nullable), recommendation (nullable: `PROCEED`|`PROCEED_WITH_CONDITIONS`|`REVIEW_REQUIRED`|`NOT_RECOMMENDED`),
recommendation_reason (text, nullable), recommendation_evidence (JSON, nullable),
officer_decision (nullable OfficerDecision), officer_decision_reason (text, nullable),
decided_by (nullable FK users), decided_at (nullable)

**documents** — id, bid_id (FK bid_submissions), document_type, filename, file_path,
file_hash (sha256), file_size, mime_type, upload_time, uploaded_by (FK users),
processing_status, extraction_confidence (float, nullable), page_count (nullable),
ocr_used (bool), error (nullable text)

**extracted_fields** — id, document_id (FK), field_name (canonical, see §8), field_value (raw),
normalized_value (string; canonical form), confidence, extraction_method, page_number (nullable)

**verification_checks** — id, bid_id (FK), requirement_id (nullable FK), source,
identifier, request_payload (JSON), response_payload (JSON), verification_status,
verified_at, confidence, is_mock (bool, always true for now), evidence_reference (nullable text)

**compliance_results** — id, bid_id (FK), requirement_id (FK), status, weight,
weighted_contribution (float), evidence (JSON list of `{document_id, filename, page, field, value}`),
explanation (text), rule_applied (string, e.g. `"turnover_inr 124000000 >= 100000000"`),
source (string, e.g. `"Bidder document + Mock GSTN"`), confidence,
overridden (bool default false), override_comment (nullable), original_status (nullable),
created_at

**risk_assessments** — id, bid_id (FK, unique), risk_level, risk_score, signals (JSON list of
`{code, message, severity}`), explanation (text), created_at. (Also mirrored onto bid_submissions.)

**knowledge_docs** — id, title, doc_type, version, content (text/markdown), uploaded_at,
chunk_count, embedding_status (`PENDING`|`INDEXED`|`FAILED`)
**knowledge_chunks** — id, doc_id (FK), chunk_index, content, embedding (nullable; pgvector only)

**clarifications** — id, bid_id (FK), subject, body, status (`DRAFT`|`SENT`|`RESPONDED`),
created_by (FK users), created_at, sent_at (nullable)

**overrides** — id, bid_id (FK), target_type (`COMPLIANCE_RESULT`|`VERIFICATION`),
target_id, original_status, officer_comment, supporting_document_id (nullable FK documents),
created_by (FK users), created_at

**reports** — id, bid_id (FK), generated_by (FK users), generated_at, file_path, summary (JSON)

**audit_logs** — id, user_id (nullable FK users; null = system), action, entity_type,
entity_id (string), timestamp, previous_hash, current_hash, metadata (JSON)
Hash: `sha256(f"{previous_hash}|{timestamp_iso}|{user_id or 'system'}|{action}|{entity_type}|{entity_id}|{canonical_json(metadata)}")`
Genesis `previous_hash = "GENESIS"`.

## 5. API reference

All responses are JSON. Auth via `Authorization: Bearer <jwt>`. Errors: `{detail: string}` with proper HTTP codes.

### Auth
- `POST /api/auth/login` `{email, password}` → `{access_token, token_type, user}`
- `POST /api/auth/demo` → demo officer login (no credentials)
- `GET /api/auth/me` → `user`

### Dashboard
- `GET /api/dashboard` → `{metrics: {total_tenders, active_tenders, total_bids, pending_reviews, high_risk_bids, documents_processed, avg_compliance_score, verification_issues}, charts: {compliance_distribution: [{range, count}], risk_distribution: [{level, count}], verification_status: [{status, count}], tender_bidder_comparison: [{tender, avg_score}], document_processing: [{status, count}]}}`
  `pending_reviews` = bids with status SUBMITTED/UNDER_REVIEW and no officer_decision.
- `GET /api/dashboard/providers` → `{llm_provider, ocr_available, db_dialect, embedding_path, mock_adapters: true}` — runtime provider status for the Settings page. `llm_provider` is the honest provider label (e.g. `"mock-llm-demo"`); `embedding_path` is `"pgvector"|"tfidf"`.

### Tenders
- `POST /api/tenders` (officer/admin) `{tender_number, title, organization, department, description, issue_date, closing_date, estimated_value_inr}` → tender
- `GET /api/tenders` → `[{tender fields..., bidder_count, pending_reviews, avg_compliance, high_risk_count, status}]`
- `GET /api/tenders/{id}` → `{tender, requirements: [...], bidders: [{bid_id, bidder fields..., compliance_score, risk_level, recommendation, status}], stats}` (`recommendation` null until generated; UI shows "Pending evaluation")
- `POST /api/tenders/{id}/requirements` (officer/admin) `{requirements: [{requirement_name, category, description, mandatory, rule_type, rule_config, threshold, expected_value, verification_source, weight, policy_reference}]}` → replaces/creates requirements
- `POST /api/tenders/{id}/analyze` (officer/admin) `{tender_text}` → `{requirements: [...]}` — tender intelligence: parses free text into structured requirement drafts (deterministic keyword/clause parser; LLM optional). Officer confirms before saving via the requirements endpoint.
- `GET /api/tenders/{id}/comparison` → `{requirements: [{id, requirement_name}], bidders: [{bid_id, legal_name, compliance_score, risk_level}], matrix: [{requirement_id, requirement_name, results: {bid_id: status}}]}`

### Bids
- `POST /api/bids` (officer/verifier) `{tender_id, legal_name, trade_name, pan, gstin, udyam, cin, registered_address, contact_name, contact_email, contact_phone}` → `{bid, bidder}` (creates bidder + bid_submission with status SUBMITTED, writes audit)
- `GET /api/bids?tender_id=` → list of `{bid_id, legal_name, bid_status, compliance_score, risk_level, recommendation, officer_decision, submitted_at}`
- `GET /api/bids/{bid_id}` → full detail: `{bid, bidder, tender: {id, tender_number, title}, documents: [...], compliance_results: [...with requirement...], risk: {...}, verification_checks: [...], recommendation: {recommendation, reason, evidence}, overrides: [...], clarifications: [...], audit: [...]}`

### Documents
- `POST /api/documents/upload` (multipart: `bid_id`, `document_type`, `file`) → document (status UPLOADED). Validates extension (pdf/jpg/jpeg/png), size ≤ 25 MB, magic bytes.
- `POST /api/documents/{id}/process` → runs the full pipeline (§9), returns `{document, extracted_fields: [...], classification}`
- `PATCH /api/documents/{id}` (officer/verifier) `{document_type}` → corrects classification (audit CLASSIFICATION_CORRECTED)
- `GET /api/documents/{id}` → `{document, extracted_fields: [...]}`
- `GET /api/documents/{id}/file` → file bytes (auth required via `Authorization: Bearer <jwt>` header — no cookie/session; correct content type)
- `GET /api/bids/{bid_id}/documents` → list
- `GET /api/documents?bid_id=&status=` → list all documents (filters optional), each with `legal_name` (bidder) + `tender_number` for display

### Verification
- `POST /api/verification/run` `{bid_id}` → runs every applicable adapter for identifiers found in extracted fields + declared bidder data; stores checks; returns `{checks: [...]}`. Each check records `is_mock: true`.
- `GET /api/verification/{bid_id}` → `{checks: [...]}`
- `GET /api/verification?bid_id=&status=` → list all verification checks (filters optional)

### Compliance & risk
- `POST /api/compliance/evaluate` `{bid_id}` → runs rules engine (§7) then risk engine (§8 in numbering below — risk), persists compliance_results + risk_assessment, updates bid_submission scores; returns `{results: [...], compliance_score, risk: {...}}`
- `GET /api/compliance/{bid_id}` → `{results: [...], compliance_score, evaluated_at}`
- `GET /api/risk/{bid_id}` → risk_assessment
- `GET /api/compliance?tender_id=` → overview of recent evaluations: `[{bid_id, legal_name, tender_number, compliance_score, evaluated_at}]` (newest first)
- `GET /api/risk?tender_id=` → overview list: `[{bid_id, legal_name, tender_number, risk_level, risk_score, top_signals: [codes]}]` (`top_signals` = up to 3 signal codes)

### Recommendation (AI-assisted)
- `POST /api/recommendation/{bid_id}` → `{recommendation, reason, evidence: [...], policy_context: [{title, chunk}], provider}` — uses stored compliance+risk results, never recomputes pass/fail. Always includes "Final decision remains with the Procurement Officer."

### RAG / knowledge base
- `POST /api/rag/search` `{query, top_k=5}` → `{results: [{doc_title, chunk, score}], embedding_path: "pgvector"|"tfidf"}`
- `GET /api/knowledge` → list of docs
- `POST /api/knowledge` (officer/admin) `{title, doc_type, version, content}` → creates + indexes
- `POST /api/knowledge/{id}/reindex` → re-chunk + re-index
- `DELETE /api/knowledge/{id}` (admin)

### Officer workflow
- `POST /api/officer/decision` (officer/admin) `{bid_id, decision, reason}` — reason required for REJECT/ESCALATE/REQUEST_CLARIFICATION. Updates bid_submission, writes audit. Returns updated bid.
- `POST /api/officer/override` (officer/admin) `{target_type, target_id, officer_comment, supporting_document_id?}` — records override; sets compliance_result.overridden=true, keeps original_status. Never deletes the original finding.
- `POST /api/officer/clarification` (officer/admin) `{bid_id, subject, body}` → creates DRAFT clarification (officer edits in UI before "sending")
- `POST /api/officer/clarification/{id}/send` → marks SENT (no real email in demo; records intent), audit CLARIFICATION_SENT
- `GET /api/officer/clarifications?bid_id=` → list

### Audit
- `GET /api/audit?entity_type=&entity_id=&limit=200` → `[{...audit fields..., user_name}]` newest first
- `POST /api/audit/verify` → `{valid, checked, broken_at: null | {id, expected, actual}}` — recomputes the whole hash chain

### Reports
- `POST /api/reports/generate` `{bid_id}` → `{report_id, download_url: "/api/reports/{id}/download"}` — builds PDF via reportlab (§12)
- `GET /api/reports/{id}/download` → PDF bytes
- `GET /api/reports?bid_id=` → list

### Seed (demo)
- `POST /api/seed` (admin) → runs full demo seed if tenders table is empty; returns `{tenders, bidders, documents}` counts. Also runnable via CLI: `cd backend && python -m app.seed.seed_data`.

## 6. Rules engine (deterministic — the ONLY thing that decides PASS/FAIL)

The engine builds an evaluation context per bid, then evaluates each tender requirement.

### Context
- `bidder`: declared bidder fields (legal_name, pan, gstin, udyam, cin, ...).
- `extracted`: canonical merged fields across all PROCESSED documents of the bid. Merge rule: highest-confidence value wins per canonical field. Also `extracted_by_doc`: `{document_type: {field: normalized_value}}`.
- `documents`: list of present document types (PROCESSED only).
- `verification`: `{source: {status, data}}` from latest verification_checks per source.

### Canonical extracted fields
`pan`, `gstin`, `udyam_number`, `cin`, `legal_name`, `trade_name`, `turnover_inr` (int),
`turnover_period` (string), `experience_years` (float), `incorporation_date` (ISO),
`valid_until` (ISO), `local_content_pct` (float), `oem_name`, `oem_authorization_valid` (bool),
`address`, `email`, `phone`, `epfo_code`, `esic_code`, `gst_status`, `udyam_status`.

Normalization: PAN/GSTIN/CIN uppercased; amounts like "₹12.4 crore"/"Rs 1,24,00,000" → int INR
(1 crore = 10,000,000; 1 lakh = 100,000); dates → ISO YYYY-MM-DD; percents → float.

### value_source syntax
`"extracted.<canonical>"` | `"bidder.<field>"` | `"verification.<SOURCE>.<json.path>"` (dot path into response_payload.data).

### Rule types and rule_config
- `EXISTENCE`: `{"value_source": "extracted.gstin"}` → PASS if non-empty.
- `DOCUMENT_REQUIRED`: `{"document_types": ["OEM_AUTHORIZATION"]}` → PASS if a PROCESSED doc of any listed type exists. Missing → MISSING.
- `EQUALITY`: `{"value_source": "...", "expected": "..."}` (case-insensitive for strings).
- `MATCH`: `{"value_source": "...", "pattern": "<regex>"}`.
- `MINIMUM`: `{"value_source": "...", "operator": ">=", "value": <number>}`.
- `MAXIMUM`: same with `<=`.
- `DATE_VALIDITY`: `{"value_source": "extracted.valid_until", "must_be_after": "today"}` → EXPIRED if date < today; MISSING if no date.
- `DATE_RANGE`: `{"value_source": "...", "min": "ISO", "max": "ISO"}`.
- `CONTAINS`: `{"value_source": "...", "substring": "..."}`.
- `BOOLEAN`: `{"value_source": "...", "expected": true}`.
- `REGISTRATION_STATUS`: `{"source": "GSTN", "identifier_field": "gstin", "require_status": "ACTIVE"}` → uses verification check for that source: VERIFIED→PASS, MISMATCH→MISMATCH, NOT_FOUND→FAIL, EXPIRED→EXPIRED, UNAVAILABLE→REVIEW_REQUIRED (never PASS/FAIL on unavailable).
- `IDENTITY_MATCH`: `{"fields": ["legal_name"], "compare": "bidder_vs_documents"}` → normalizes names (upper, strip Pvt/Ltd/Private/Limited/LLP/Inc/Corp/punctuation, collapse spaces); exact identifier (PAN/GSTIN/CIN) match across docs = strong pass; fuzzy name similarity via rapidfuzz (fallback difflib) token_set_ratio ≥ 85 → PASS else MISMATCH (HIGH risk signal).
- `CUSTOM_RULE`: `{"expression": "<python-safe expression over context keys>"}` — evaluate with a restricted eval (no builtins). Use sparingly.

### Confidence rule
If the minimum extraction confidence behind a result is < 0.70 and the computed status is PASS,
downgrade to REVIEW_REQUIRED with explanation "Low extraction confidence — officer review required."
FAIL/MISSING/EXPIRED/MISMATCH stand as computed (they are not "silent AI decisions").

### Evidence
Every result stores `evidence` list, `rule_applied` human-readable string (e.g. `"turnover_inr 124000000 >= 100000000"`),
`explanation` ("PASS because …"), `source`, `confidence`.

## 7. Compliance score (transparent, inspectable)

For applicable requirements (exclude NOT_APPLICABLE):
`factor`: PASS=1.0, REVIEW_REQUIRED=0.5, FAIL/MISSING/EXPIRED/MISMATCH=0.
`score = 100 * Σ(weight × factor) / Σ(weight)`.
`weighted_contribution = 100 * weight × factor / Σ(weight)` — shown per requirement.
The formula and every input are visible in the UI.

## 8. Risk engine (independent of score)

Signals (each `{code, message, severity: "critical"|"high"|"medium"|"low", weight}`):
- `BLACKLISTED` (critical, 100) — blacklist adapter hit
- `DEBARRED` (critical, 100)
- `PAN_MISMATCH` (high, 40), `GST_NAME_MISMATCH` (high, 40), `CIN_MISMATCH` (high, 40)
- `MISSING_MANDATORY_DOC` (high, 30 per requirement, cap 60)
- `EXPIRED_CERTIFICATE` (high, 30)
- `FAILED_MANDATORY_REQUIREMENT` (high, 25)
- `UNVERIFIED_SOURCE` (medium, 15) — adapter UNAVAILABLE
- `LOW_CONFIDENCE_EXTRACTION` (medium, 10)
- `LARGE_VALUE_DISCREPANCY` (medium, 15) — e.g. declared vs extracted turnover differs > 25%

Level: any critical signal → CRITICAL. Else score = Σ weights: ≥50 HIGH, ≥25 MEDIUM, else LOW.
`risk_reasons` = human-readable list; the UI shows each reason (never just "HIGH").

## 9. Document processing pipeline (`POST /api/documents/{id}/process`)

1. Read file; compute sha256; open with PyMuPDF → `page_count`.
2. Extract text per page. If total text < 50 chars → try OCR (PaddleOCR) if installed (`ocr_used=true`).
   If no OCR available → status FAILED, `error="OCR_UNAVAILABLE: scanned document requires OCR which is not installed"`.
3. **Classification**: score document_type by keyword rules over filename + text
   (e.g. "GSTIN"/"Goods and Services Tax" → GST_CERTIFICATE; "UDYAM" → UDYAM_CERTIFICATE;
   "Permanent Account Number" → PAN_CERTIFICATE; "turnover" → TURNOVER_CERTIFICATE;
   "authorized"/"OEM" → OEM_AUTHORIZATION; "Employees' Provident Fund" → EPFO_CERTIFICATE;
   "Employees' State Insurance" → ESIC_CERTIFICATE; "local content"/"Make in India" → MII_DECLARATION;
   "experience"/"completion certificate" → EXPERIENCE_CERTIFICATE; "Income Tax"/"ITR" → ITR).
   Keep the officer-selected type if the upload specified one explicitly? No — auto-detect, officer can correct via PATCH.
4. **Regex extraction** (method REGEX, confidence 0.95–0.99):
   - PAN: `\b[A-Z]{5}[0-9]{4}[A-Z]\b`
   - GSTIN: `\b\d{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b`
   - UDYAM: `\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b`
   - CIN: `\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b`
   - Email, Indian phone (`\b[6-9]\d{9}\b`), dates (DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD, "15 Jun 2021"),
     amounts (`₹`/`Rs\.?`/`INR` with optional `crore`/`lakh`), percentages.
5. **LLM extraction** (method LLM): provider extracts semantic fields per document type into a
   Pydantic schema (`legal_name`, `turnover_inr`, `turnover_period`, `experience_years`,
   `local_content_pct`, `oem_name`, `oem_authorization_valid`, `valid_until`, `address`, `confidence`).
   The default mock provider uses deterministic heuristics over labeled lines the demo PDFs contain
   (e.g. lines starting with `Legal Name:`, `Turnover:`, `Local Content:`), and returns
   `"provider": "mock-llm-demo"`. Real provider output is schema-validated; on failure → extraction
   error recorded, fields skipped (never crash the pipeline).
6. Persist `extracted_fields` with normalized values; set `extraction_confidence` = mean of field
   confidences; status PROCESSED. Write audit `DOCUMENT_PROCESSED` with counts per method.

## 10. Government verification adapters (ALL MOCK, labeled)

Common interface:
```python
class GovernmentVerificationAdapter(ABC):
    source: str  # AdapterSource value
    @abstractmethod
    def verify(self, identifier: str) -> dict:
        """Returns {source, status, data, timestamp, is_mock: True, confidence}"""
```
Adapters: `GSTNAdapter.verify_gst(gstin)`, `UdyamAdapter`, `PANAdapter` (PAN_IT), `MCAAdapter`,
`EPFOAdapter`, `ESICAdapter`, `StartupIndiaAdapter`, `NSICAdapter`, `DigiLockerAdapter`,
`BlacklistAdapter.verify_blacklist(company_name)`.

Mock DB lives in `backend/app/adapters/mock_data/*.json` (seeded from `mock_data/` at repo root).
`verify()` looks up the identifier; unknown identifier → `{status: "NOT_FOUND"}`.
Response shapes:
- GSTN: `{gstin, legal_name, status: ACTIVE|CANCELLED, registration_date, state}`
- UDYAM: `{udyam_number, enterprise_name, status, category: MICRO|SMALL|MEDIUM, registration_date}`
- PAN_IT: `{pan, name, status: ACTIVE, itr_filed_upto}`
- MCA21: `{cin, company_name, status, incorporation_date}`
- EPFO: `{epfo_code, employer_name, status}`
- ESIC: `{esic_code, employer_name, status}`
- BLACKLIST: `{company_name, blacklisted: bool, debarred: bool, authority, reason, period}`

`POST /api/verification/run` resolves identifiers from extracted fields + bidder declaration,
calls each relevant adapter once, stores `verification_checks` with `is_mock=true`.

## 11. RAG knowledge base

- Chunking: 600 chars, 120 overlap, on `knowledge_docs.content`.
- `POST /api/rag/search {query, top_k}` returns chunks with doc title + score and
  `embedding_path: "pgvector" | "tfidf"`.
- pgvector path: only when `DATABASE_URL` is Postgres and the `vector` extension is available;
  embeddings via sentence-transformers BGE-M3 if installed, else the doc is still indexed with
  `embedding_status=INDEXED` via TF-IDF. Honest labeling always.
- Seed policy docs (in `knowledge_base/policies/`): `gem_guidelines.md`, `make_in_india.md`,
  `msme_udyam.md`, `oem_authorization_policy.md`, `blacklist_debarment_policy.md`,
  `cpcl_tender_conditions.md`, `document_verification_sop.md`.
- Used by recommendation + AI explanation panel: retrieve top-3 chunks relevant to each
  non-PASS requirement; show quoted policy text with source title.

## 12. AI recommendation

Deterministic mapping + template text + RAG policy quotes:
- CRITICAL risk or blacklisted → `NOT_RECOMMENDED`
- Any FAIL on mandatory requirement → `NOT_RECOMMENDED` (with reasons)
- Any MISMATCH/EXPIRED/REVIEW_REQUIRED → `REVIEW_REQUIRED`
- All PASS → `PROCEED`; minor medium signals → `PROCEED_WITH_CONDITIONS`
`recommendation_reason` lists evidence-backed bullets. `recommendation_evidence` = requirement ids + check ids.
Response and UI always append: "Final decision remains with the Procurement Officer."

## 13. Compliance report (PDF)

`POST /api/reports/generate {bid_id}` builds with reportlab:
1. Cover: CPCL-style header, tender no + title, bidder, date, generated by.
2. Executive summary: score, risk, recommendation, officer decision (or "Pending").
3. Requirement matrix table: requirement | status | weight | contribution | confidence.
4. Evidence section per requirement: claim, evidence (doc + page), rule, source, confidence.
5. Risk assessment with reasons.
6. Verification summary (mock sources labeled).
7. AI explanation + policy references.
8. Officer comments/decisions/overrides.
9. Disclaimer (exact text): "This report is generated as an AI-assisted decision-support output. It does not constitute a final qualification or disqualification decision. Final procurement decision rests with the authorized Procurement Officer."
10. Audit reference: id + current_hash of the latest audit entry for this bid.

## 14. Seed data (what `POST /api/seed` / CLI must create)

Tender 1 — `CPCL-DEMO-2026-001` "Procurement of Industrial Pump Systems", CPCL, Materials Dept,
issue 2026-08-01, closing 2026-09-30, est. ₹4,50,00,000. 12 requirements:
| # | name | category | rule | weight |
|---|---|---|---|---|
| 1 | GST Registration | STATUTORY | REGISTRATION_STATUS GSTN ACTIVE | 15 |
| 2 | PAN Verification | STATUTORY | REGISTRATION_STATUS PAN_IT ACTIVE | 10 |
| 3 | Udyam/MSME Registration | REGISTRATION | REGISTRATION_STATUS UDYAM ACTIVE | 10 |
| 4 | Minimum Turnover ₹10 Crore | FINANCIAL | MINIMUM extracted.turnover_inr >= 100000000 | 15 |
| 5 | Minimum 5 Years Experience | EXPERIENCE | MINIMUM extracted.experience_years >= 5 | 10 |
| 6 | OEM Authorization | OEM | DOCUMENT_REQUIRED [OEM_AUTHORIZATION] | 10 |
| 7 | Make in India Local Content ≥ 50% | LOCAL_CONTENT | MINIMUM extracted.local_content_pct >= 50 | 10 |
| 8 | EPFO Registration | STATUTORY | REGISTRATION_STATUS EPFO ACTIVE | 5 |
| 9 | ESIC Registration | STATUTORY | REGISTRATION_STATUS ESIC ACTIVE | 5 |
| 10 | Income Tax Compliance | STATUTORY | EXISTENCE extracted.itr OR verification PAN_IT itr_filed_upto ≥ 2024 | 5 |
| 11 | Blacklisting / Debarment Check | INTEGRITY | CUSTOM: blacklist blacklisted==False | 5 |
| 12 | Bid Document Completeness | DOCUMENT | DOCUMENT_REQUIRED [PAN_CERTIFICATE, GST_CERTIFICATE, UDYAM_CERTIFICATE] | 0 (informational; weight 0 still evaluated) |

Wait — weight 0 breaks the formula display; instead give it weight 5 and reduce others? Keep 12 requirements, weights sum to 100:
GST 15, PAN 10, Udyam 10, Turnover 15, Experience 10, OEM 10, MII 10, EPFO 5, ESIC 5, ITR 5, Blacklist 5 → that's 100 across 11. Make #12 informational with weight 0 and EXCLUDE weight-0 from the score denominator (NOT_APPLICABLE-style handling: weight 0 → excluded from scoring but still shown). Simpler: keep 11 weighted requirements + document completeness as an unscored checklist. **Final: 11 requirements, weights sum to 100.**

Bidders on CPCL-DEMO-2026-001 (fictional!):
- **A — Apex Flow Systems Pvt Ltd** — PAN `AAFCA1234E`, GSTIN `27AAFCA1234E1Z5`, UDYAM `UDYAM-MH-19-0012345`, CIN `U28999MH2015PTC123456`. Turnover ₹12.4 cr, 9 yrs exp, OEM auth yes, local content 62%, all certs active. → ~90+, LOW. (One REVIEW: ESIC adapter UNAVAILABLE for its code → shows REVIEW_REQUIRED + honest handling.)
- **B — Bharat Mech Works** — turnover ₹8.2 cr (FAIL), no OEM authorization (MISSING), ITR missing (REVIEW). → ~65–70, MEDIUM.
- **C — Crestline Pumps Pvt Ltd** — docs show name "Crestline Pumps Pvt Ltd" but GSTN mock returns legal_name "Crestline Trading Co" (GST_NAME_MISMATCH → MISMATCH), PAN doc name differs too. → ~60, HIGH.
- **D — Deccan Industrial Traders** — blacklist adapter returns debarred by CPCL (2024–2027). → CRITICAL regardless of score.
- **E — Everest Engineering Co** — Udyam cert expired 2024 (EXPIRED), ESIC cert expired (EXPIRED). → HIGH.
- **F — Fusion Petro Equipment LLP** — strong docs (~85) but ESIC code not found in mock ESIC (NOT_FOUND → REVIEW_REQUIRED), turnover extraction low confidence (mock LLM 0.62 → REVIEW_REQUIRED). → MEDIUM, "requires officer review".

Tender 2 — `CPCL-DEMO-2026-002` "AMC for Refinery Instrumentation", 1 bidder (G — Ganesh Controls, mostly compliant).
Tender 3 — `CPCL-DEMO-2026-003` "Supply of Safety Helmets (MSE)", 1 bidder (H — Harsh Safety Gear, MSE startup, some MISSING).

Each bidder gets 6–9 generated PDFs (reportlab, selectable text, labeled lines for the mock LLM).
Seed runs the FULL pipeline for every document → verification → compliance → risk → recommendation,
so the demo works instantly. Idempotent: skip if `CPCL-DEMO-2026-001` exists.

Mock portal JSONs must include: positive records for A/B/E/F/G/H identifiers, mismatch record for C,
cancelled/expired variants, blacklist record for D, and NOT_FOUND for F's ESIC code.

## 15. Backend project structure

```
backend/
  requirements.txt
  app/
    main.py                 # FastAPI app, CORS, startup (create_all + optional seed), routers
    core/
      config.py             # pydantic-settings; DATABASE_URL, JWT_SECRET, upload dir, provider flags
      security.py           # password hashing, JWT create/verify
      deps.py               # get_db, get_current_user, require_roles
    api/
      auth.py tenders.py bids.py documents.py verification.py compliance.py
      recommendation.py rag.py knowledge.py officer.py audit.py reports.py dashboard.py seed.py
    services/
      document_service.py   # upload validation, storage
      pipeline_service.py   # orchestration of §9 steps
      extraction_service.py # PyMuPDF, OCR wrapper
      regex_service.py      # patterns + canonical normalization
      llm_service.py        # LLMProvider interface, MockLLMProvider, OpenAIProvider
      classification_service.py
      verification_service.py
      compliance_service.py # builds context, calls rules engine, persists results
      scoring_service.py
      risk_service.py
      rag_service.py        # chunking, TF-IDF/pgvector retrieval
      recommendation_service.py
      audit_service.py      # append + verify hash chain
      report_service.py     # reportlab PDF
      tender_intel_service.py # analyze tender text → requirement drafts
    engines/
      rules_engine.py       # §6
      risk_engine.py        # §8
      entity_resolution.py  # normalize + fuzzy match
    adapters/
      base.py               # GovernmentVerificationAdapter ABC
      gst_adapter.py udyam_adapter.py pan_adapter.py mca_adapter.py
      epfo_adapter.py esic_adapter.py startup_india_adapter.py nsic_adapter.py
      blacklist_adapter.py digilocker_adapter.py
      mock_data/*.json
    models/                 # SQLAlchemy models (one file per entity or single models.py)
    schemas/                # Pydantic request/response schemas
    database/
      base.py session.py
    seed/
      seed_data.py          # full seed; run via POST /api/seed or python -m app.seed.seed_data
      demo_docs.py          # reportlab PDF generator for bidder documents
    utils/
      validators.py         # PAN/GSTIN checksum-ish validation (format + structure)
      hashing.py pdf.py
  tests/
    test_regex_extraction.py test_validators.py test_entity_resolution.py
    test_rules_engine.py test_scoring.py test_risk_engine.py
    test_mock_adapters.py test_audit_chain.py test_pipeline_e2e.py
  uploads/                  # gitignored
```

Requirements (pin loosely): fastapi, uvicorn, sqlalchemy, pydantic>=2, pydantic-settings,
psycopg2-binary, python-jose or PyJWT, passlib[bcrypt], python-multipart, PyMuPDF, reportlab,
rapidfuzz, scikit-learn (TF-IDF fallback), python-dateutil, email-validator. Optional: paddleocr,
paddlepaddle, sentence-transformers, pgvector.

## 16. Frontend contract

Stack: React 18 + TypeScript + Vite + Tailwind CSS + shadcn-style components (hand-rolled in
`src/components/ui/`: button, card, badge, table, dialog, input, select, tabs, textarea,
tooltip, progress, separator, skeleton, sheet/drawer) + lucide-react + recharts +
react-router-dom + @tanstack/react-query + react-hook-form + zod. Axios API client with JWT
interceptor; `AuthContext`; `ProtectedRoute`; role-based UI gating.

Routes:
- `/` — landing: hero ("AI-Powered Bid Compliance Verification for Government Procurement"),
  CTAs [Launch Demo] [View Workflow], feature cards (Document Intelligence, Multi-Source
  Verification, Tender-Aware Compliance, Risk Intelligence, Evidence-Based Recommendations,
  Auditability), visual workflow Tender → Documents → Verification → Compliance → Risk → Officer Review.
- `/login` — email/password + prominent "Continue with Demo".
- `/app` layout with sidebar (Dashboard, Tenders, Bidders, Documents, Verification, Compliance,
  Risk Intelligence, Reports, Audit Trail, Knowledge Base, Settings, Profile) + topbar (user, role badge, logout).
- `/app/dashboard` — metric cards (8 metrics from §5) + charts (compliance distribution bar,
  risk distribution donut, verification status, tender-wise avg score bar, document processing status).
- `/app/tenders` — table (Tender ID, Title, Department, Closing Date, Bidders, Pending Reviews, Avg Compliance, Risk, Status, Actions).
- `/app/tenders/:id` — tabs: Overview | Requirements | Bidders | Compliance Matrix | Documents | Verification | Audit | Reports. Include [Analyze Tender] (tender intelligence), [Compare Bidders].
- `/app/tenders/:id/compare` — side-by-side requirement × bidder matrix (statuses only; never declare a "best bidder").
- `/app/bids/:id` — bidder detail: identity header (score ring + risk badge + recommendation),
  tabs/sections: Documents, Extracted Information, Verification, Compliance (matrix w/ evidence drawer),
  Risk (reasons list), AI Explanation (evidence + policy quotes + confidence + provider label),
  Audit Trail, Officer Decision panel ([Approve] [Reject] [Escalate] [Request Clarification] with
  confirmation + reason; [Override] on findings; [Generate Report]; [Request Clarification] editor).
- `/app/bidders` — all bidders table w/ filters.
- `/app/documents` — all documents table w/ filters; `/app/documents/:id` — viewer: left PDF
  (iframe via `/file` URL), right extracted fields (value, confidence chip, method badge REGEX/LLM,
  verification status), [Re-process], classification correction select.
- `/app/verification` — checks table w/ mock-source labels, filters by status.
- `/app/compliance` — overview of recent evaluations (or redirect into tender context; implement as
  filterable results table).
- `/app/risk` — risk cards/table with reason lists.
- `/app/reports` — generated reports list + download.
- `/app/audit` — audit timeline table + [Verify Audit Integrity] → shows valid/broken result.
- `/app/knowledge` — docs table (title, type, version, uploaded, chunks, embedding status),
  upload form, [Re-index], [Delete], RAG search box showing retrieved sources.
- `/app/settings`, `/app/profile` — functional basics (profile edit, password change; settings:
  API URL display, provider status: LLM provider, OCR available, DB dialect, embedding path).

Design: light neutral theme, slate/navy text, white cards, restrained indigo/blue accent.
Status colors: PASS green, FAIL red, REVIEW_REQUIRED/MISSING/EXPIRED/MISMATCH amber,
NOT_APPLICABLE gray. Risk: LOW green, MEDIUM amber, HIGH orange/red, CRITICAL dark red.
No gradients/glassmorphism/cartoon graphics. Cards, tables, badges, timelines, evidence drawer
(right-side sheet). Subtle transitions only. Responsive.

Every action button calls the real API and refreshes TanStack Query caches; show toasts on
success/error. Confirmations for officer decisions (dialog with reason field where required).

## 17. Testing

Backend pytest suite (sqlite in-memory/file): regex extraction, PAN/GSTIN validators,
entity resolution (incl. the C mismatch case), rules engine per rule type, scoring math,
risk engine (incl. D → CRITICAL despite decent score), mock adapters (hit/miss/mismatch),
audit hash chain (append 5, verify ok; tamper one, verify fails), pipeline e2e on one generated PDF.
Frontend: build must pass (`npm run build`); add a few vitest tests if practical for utils.

## 18. What the repo root must contain (built by the orchestrator, not the track agents)

`docker-compose.yml` (frontend, backend, postgres+pgvector, redis), `.env.example`, `README.md`,
`knowledge_base/policies/*.md`, `mock_data/` (source JSONs copied into backend adapters at seed).

## 19. Honesty labels (UI copy)

- Verification sections: "SOURCE: MOCK GOVERNMENT VERIFICATION — demo data, not live government systems."
- AI panels: "AI-assisted explanation" + provider label (`mock-llm-demo` or `openai`) + confidence.
- Report disclaimer: exact text from §13.
- Never render "AI disqualified the bidder" — always "System identified a potential non-compliance. Procurement Officer review required."
