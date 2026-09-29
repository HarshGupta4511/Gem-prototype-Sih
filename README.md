# AI-Powered Integrated Bid Compliance Verification Platform
### SIH26100 · Ministry of Petroleum & Natural Gas — CPCL · GeM Procurement

An AI-assisted decision-support platform that helps Procurement Officers verify bidder
documents, cross-check statutory information against (mock) government sources, evaluate
tender-specific requirements with a deterministic rules engine, score compliance and risk
**independently**, and record an evidence-backed final decision — with a tamper-evident
audit trail.

> **Product philosophy: VERIFY → EXPLAIN → ASSIST → HUMAN DECIDES.**
> The system never makes the final qualification/disqualification decision.
> The Procurement Officer always does.

---

## 30-second pitch

Instead of a Procurement Officer manually checking hundreds of documents across portals,
this platform extracts information from bid documents (PDF text → regex → LLM, schema-validated),
verifies it against mock government adapters, evaluates it against the *specific tender's*
requirements, surfaces evidence-backed compliance and risk insights, and lets the officer
make — and record — the final decision.

## Architecture

```
DOCUMENT → EXTRACTION → VERIFICATION → EVIDENCE → DETERMINISTIC RULES
→ SCORE/RISK → RAG EXPLANATION → AI RECOMMENDATION → PROCUREMENT OFFICER → FINAL DECISION
```

- **Frontend**: React 18 + TypeScript + Vite + Tailwind + shadcn-style components + Recharts
- **Backend**: FastAPI + Pydantic v2 + SQLAlchemy 2.0
- **DB**: PostgreSQL + pgvector (Docker) · SQLite fallback for local dev
- **Docs/RAG**: LangChain-style chunking; BGE-M3 embeddings when available, TF-IDF fallback otherwise
- **Reports**: reportlab PDFs with the decision-support disclaimer

Full API/architecture contract: [`CONTRACT.md`](CONTRACT.md).

---

## Quick start — Docker (recommended for judges)

```bash
cp .env.example .env
# put a long random JWT_SECRET in .env
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API + Swagger: http://localhost:8000/docs

Then click **Continue with Demo** (or log in as `officer@demo.cpcl.in` / `Demo@123`),
open tender **CPCL-DEMO-2026-001**, and walk the full demo flow below.

## Quick start — local dev (no Docker)

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed.seed_data      # creates demo data + runs the full pipeline
uvicorn app.main:app --reload     # http://localhost:8000/docs
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

## Demo walkthrough (16 steps, ~5 minutes)

1. **Continue with Demo** on the login page (demo Procurement Officer).
2. **Dashboard** — metrics + charts.
3. Open tender **CPCL-DEMO-2026-001** ("Procurement of Industrial Pump Systems").
4. Review the 11 tender requirements and weights.
5. Open **Bidder A — Apex Flow Systems** (mostly compliant, LOW risk).
6. **Documents** — open a PDF, see classification + extracted fields (Regex/LLM badges + confidence).
7. **Run Verification** — mock GSTN/Udyam/PAN/MCA/EPFO/ESIC/Blacklist responses (labeled MOCK).
8. **Evaluate Compliance** — deterministic rules engine; PASS/FAIL/MISSING/REVIEW matrix.
9. Open the **evidence drawer** on any row (document, page, value, rule, source, confidence).
10. **Risk** — independent level with human-readable reasons (note: score ≠ risk).
11. **AI Explanation** — evidence + retrieved policy quotes; "Final decision remains with the Procurement Officer."
12. **Compare Bidders** — side-by-side matrix (informational; no auto "best bidder").
13. Try **Bidder D** (blacklisted → CRITICAL) and **Bidder C** (GST name mismatch → HIGH).
14. **Request Clarification** / **Override** a finding (officer comment + evidence preserved).
15. **Record the officer decision** (Approve/Reject/Escalate/Clarification) with confirmation.
16. **Audit Trail → Verify Audit Integrity**, then **Generate Report** (PDF download).

---

## Demo accounts

| Email | Password | Role |
|---|---|---|
| officer@demo.cpcl.in | Demo@123 | PROCUREMENT_OFFICER |
| verifier@demo.cpcl.in | Demo@123 | VERIFIER |
| auditor@demo.cpcl.in | Demo@123 | AUDITOR |
| admin@demo.cpcl.in | Demo@123 | ADMIN |

## Demo scenarios (all fictional)

| Bidder | Story | Score | Risk |
|---|---|---|---|
| A · Apex Flow Systems | Mostly compliant | ~90 | LOW |
| B · Bharat Mech Works | Low turnover, missing OEM + ITR | ~70 | MEDIUM |
| C · Crestline Pumps | GST/PAN name mismatch | ~60 | HIGH |
| D · Deccan Industrial Traders | Debarred (blacklist hit) | — | CRITICAL |
| E · Everest Engineering | Expired Udyam + ESIC | — | HIGH |
| F · Fusion Petro Equipment | Strong docs, ESIC unverifiable | ~85 | MEDIUM |

Two more tenders with additional bidders are seeded for the tender list views.

## Key design decisions

- **Deterministic rules decide; AI explains.** LLMs extract ambiguous fields and write
  explanations; pass/fail comes from the Python rules engine. Low-confidence PASS →
  REVIEW_REQUIRED, never silent.
- **Compliance score ≠ risk level.** A 90%-compliant blacklisted bidder is still CRITICAL risk.
- **Honest mocking.** Every portal response carries `is_mock: true` and the UI labels
  "MOCK GOVERNMENT VERIFICATION". Adapters share one interface so authorized real
  integrations can replace mocks later.
- **Tamper-evident audit.** Hash-chained audit log with a one-click integrity verifier.
- **Officer supremacy.** Overrides preserve the original finding; decisions require
  confirmation + reason; reports carry the decision-support disclaimer.

## Testing

```bash
cd backend && .venv/bin/pytest -q     # rules, scoring, risk, adapters, audit chain, e2e
cd frontend && npm run build          # typecheck + production build
```

## Project layout

```
cpcl-bidverify/
├── CONTRACT.md            # API + architecture source of truth
├── README.md
├── docker-compose.yml  /  .env.example
├── backend/               # FastAPI app (api/services/engines/adapters/models/...)
├── frontend/              # React + TS + Vite app
├── knowledge_base/policies/  # RAG seed documents
└── mock_data/             # pointer to adapter fixtures
```

## Disclaimer

Demo prototype for SIH26100. All companies, identifiers, and portal responses are fictional.
The compliance report states: *"This report is generated as an AI-assisted decision-support
output. It does not constitute a final qualification or disqualification decision. Final
procurement decision rests with the authorized Procurement Officer."*
