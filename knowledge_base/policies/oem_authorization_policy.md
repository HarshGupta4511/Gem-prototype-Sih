# OEM Authorization Policy — Reference (Demo)

> Demo document for the SIH26100 prototype knowledge base.

## 1. Why OEM authorization matters
- For equipment tenders, bidders who are not the Original Equipment Manufacturer must submit
  a valid authorization letter from the OEM to supply, install and support the equipment.

## 2. What a valid authorization contains
- OEM's legal name and the bidder's legal name (must match the bidding entity).
- Tender reference number and equipment scope.
- Validity period covering the bid due date.
- Authorised signatory with name, designation and contact.

## 3. Evaluation
- Missing OEM authorization where the tender mandates it is a **mandatory-requirement failure**,
  but the officer may seek clarification if the letter appears to exist with a minor defect
  (e.g. wrong tender number typo) — recorded as an officer override with evidence.
- Authorization letters naming a *different* bidder entity are an identity mismatch (high risk).

## 4. Platform behavior
- The rules engine checks for the *presence* of an OEM authorization document and key fields.
- Semantic checks (is the relationship genuine?) are left to officer review with AI assistance.
