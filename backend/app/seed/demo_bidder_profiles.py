"""Fictional demo-bidder profiles for the Create-Tender Stage-3 demo modal.

Each profile defines the identifiers, contact details and evidence-generation
policy for one of the four selectable demo bidders. Dossier sections are built
**requirement-driven**: for every TenderRequirement on the tender, the builder
emits the matching evidence section (registration certificates, financial /
experience certificates, EMD, OEM, MII, ...), so the demo works against any
officer-configured tender — not just a fixed template.

Scenario intent (every identifier below is fictional and every portal record
it matches is a mock-labelled entry in ``adapters/mock_data``):

- ``apex``:      Mostly Compliant — valid evidence everywhere; one deliberate
  minor item on a NON-mandatory requirement when the tender has one.
- ``vertex``:    Missing Evidence — only turnover + experience evidence; all
  registration / financial extras are deliberately omitted.
- ``nova``:      Verification Mismatch — full evidence, but the GSTN / PAN_IT
  mock portal records carry a different legal name, so the existing
  cross-check produces MISMATCH.
- ``primetech``: High Risk — full valid evidence, but a mock blacklist record
  exists, so the risk engine reports CRITICAL while the compliance score
  stays high (score and risk are separate concepts).
"""

from __future__ import annotations

import math

PROFILE_KEYS = ("apex", "vertex", "nova", "primetech")

PROFILES: dict[str, dict] = {
    "apex": {
        "legal_name": "Apex Flow Systems Pvt. Ltd.",
        "trade_name": "Apex Industrial Solutions",
        "identifiers": {
            "pan": "AAFCA1234E",
            "gstin": "27AAFCA1234E1Z5",
            "udyam": "UDYAM-MH-19-0012345",
            "cin": "U28999MH2015PTC123456",
            "epfo_code": "MH/123456/001",
        },
        "address": "Plot 42, MIDC Industrial Area, Bhosari, Pune - 411026",
        "contact_name": "R. Ramanathan, Director",
        "contact_email": "contracts@apexflow-demo.in",
        "contact_phone": "+91 98400 10001",
        # Multi-document evidence: one standalone PDF per certificate, like a
        # real multi-upload bid (Nova already used this path).
        "split_dossier_sections": True,
    },
    "vertex": {
        "legal_name": "Vertex Industrial Solutions Pvt. Ltd.",
        "trade_name": "Vertex Engineering",
        "identifiers": {},  # deliberately no identifiers: missing evidence
        "address": "14/B, TTC Industrial Area, MIDC, Navi Mumbai - 400705",
        "contact_name": "S. Iyer, Partner",
        "contact_email": "tenders@vertex-demo.in",
        "contact_phone": "+91 98410 20002",
        # Multi-document evidence (only turnover + experience sections exist
        # for this missing-evidence profile).
        "split_dossier_sections": True,
    },
    "nova": {
        "legal_name": "Nova Engineering Works Pvt. Ltd.",
        "trade_name": "Nova Works",
        "identifiers": {
            # Mock GSTN / PAN_IT records for these identifiers carry the legal
            # name "Nova Infra Projects Private Limited" -> name MISMATCH.
            "pan": "AANNE5678P",
            "gstin": "27AANNE5678P1Z5",
            "udyam": "UDYAM-MH-27-0099887",
            "cin": "U28999MH2021PTC445566",
        },
        # Cross-document identity scenario: the PAN dossier section carries a
        # different legal name than the GST/UDYAM sections -> a real
        # ENTITY_NAME MISMATCH emerges from extraction, on top of the portal
        # verification mismatch. The sections are seeded as SEPARATE evidence
        # documents (one per certificate, like a real multi-upload bid) so the
        # cross-document consistency engine has genuinely distinct documents
        # to compare — a single consolidated PDF would collapse the names into
        # one extracted value and the mismatch could never emerge honestly.
        "document_name_overrides": {
            "PAN_CERTIFICATE": "Nova Industrial Enterprises",
        },
        "split_dossier_sections": True,
        "address": "Gat 154, Chakan Industrial Area Phase II, Pune - 410501",
        "contact_name": "N. Kulkarni, Proprietor",
        "contact_email": "bids@nova-demo.in",
        "contact_phone": "+91 98200 30003",
    },
    "primetech": {
        "legal_name": "PrimeTech Industrial Systems Pvt. Ltd.",
        "trade_name": "PrimeTech Systems",
        "identifiers": {
            # All portal records ACTIVE + name-matching; the risk signal comes
            # from the mock blacklist entry for this exact legal name.
            "pan": "AAPCP9876Q",
            "gstin": "29AAPCP9876Q1Z5",
            "udyam": "UDYAM-KA-03-0076543",
            "cin": "U28999KA2018PTC334455",
            "epfo_code": "KA/987654/002",
        },
        "address": "Plot 88, MIDC Waluj, Aurangabad - 431136",
        "contact_name": "P. Deshmukh, Director",
        "contact_email": "contact@primetech-demo.in",
        "contact_phone": "+91 98400 40004",
        # Scenario: submits a false non-debarment declaration while the mock
        # blacklist carries this exact legal name — the debarment-declaration
        # consistency check is built to catch exactly this contradiction.
        "debarment_declaration": (
            "Not debarred or blacklisted by any government authority."
        ),
        # Multi-document evidence: one standalone PDF per certificate, like a
        # real multi-upload bid (Nova already used this path).
        "split_dossier_sections": True,
    },
}

# Fields whose dossier sections Vertex deliberately omits (missing evidence).
# Only turnover + experience evidence is generated for Vertex.
_VERTEX_ALLOWED_SOURCES = {"extracted.turnover_inr", "extracted.experience_years"}

_DEMO_BANNER = (
    "SAMPLE \u2014 FOR DEMONSTRATION ONLY \u2014 fictional bidder evidence; "
    "not a government-issued certificate"
)


def _evidence_value(profile_key: str, field: str, threshold, mandatory: bool):
    """Return an evidence value for ``extracted.<field>``.

    Passing values carry a comfortable margin over the requirement threshold.
    For ``apex`` one deliberate minor item is produced: a below-threshold
    value on a NON-mandatory requirement (it can never sink a mandatory
    requirement).
    """
    t = threshold if isinstance(threshold, (int, float)) and threshold > 0 else None
    if field == "turnover_inr":
        base = t or 25_000_000
        # INR; the formatter renders "Rs N lakh"
        return math.ceil(base * 1.5 / 100_000) * 100_000
    if field == "experience_years":
        base = int(t) if t else 3
        return base + 2
    if field == "past_performance_pct":
        base = float(t) if t else 40.0
        return min(98, int(base + 15))
    if field == "local_content_pct":
        base = float(t) if t else 50.0
        # Deliberate minor item: a below-threshold value on a NON-mandatory
        # requirement. Flag-based so generated bulk-demo profiles can opt in;
        # the "apex" key keeps its historic behaviour.
        prof = PROFILES.get(profile_key, {})
        if (profile_key == "apex" or prof.get("deliberate_minor_item")) and not mandatory:
            return max(5, int(base - 15))  # deliberate minor item
        return int(base + 12)
    if field == "emd_amount_inr":
        return int(t) if t else 500_000
    return None


def _add_registration(add, source: str, identifiers: dict, legal_name: str,
                      trade_name: str) -> None:
    """Registration evidence sections.

    Key names and value formats match the real ``demo_docs`` templates (and
    therefore the MockLLM/regex extractors), e.g. turnover as "Rs 375 lakh",
    percentages as "62%", EMD as "Rs 5,00,000".
    """
    if source == "GSTN" and identifiers.get("gstin"):
        add(
            "GST_CERTIFICATE",
            trade_name=trade_name,
            gstin=identifiers["gstin"],
            pan=identifiers.get("pan", ""),
            registration_date="15-06-2021",
        )
    elif source == "PAN_IT" and identifiers.get("pan"):
        add(
            "PAN_CERTIFICATE",
            pan=identifiers["pan"],
            incorporation_date="12-03-2015",
        )
    elif source == "UDYAM" and identifiers.get("udyam"):
        add(
            "UDYAM_CERTIFICATE",
            udyam=identifiers["udyam"],
            valid_until="31-12-2030",
        )
    elif source == "MCA21" and identifiers.get("cin"):
        add(
            "MCA21_CERTIFICATE",
            cin=identifiers["cin"],
            incorporation_date="12-03-2015",
            company_status="Active",
        )
    elif source == "EPFO" and identifiers.get("epfo_code"):
        add(
            "EPFO_CERTIFICATE",
            epfo_code=identifiers["epfo_code"],
        )
    elif source == "ESIC" and identifiers.get("esic_code"):
        add(
            "ESIC_CERTIFICATE",
            esic_code=identifiers["esic_code"],
            valid_until="31-12-2030",
        )
    # Unknown registration sources: no section — the engine will report
    # REVIEW_REQUIRED/MISSING honestly instead of us inventing evidence.


def _add_minimum(add, profile_key: str, field: str, threshold, mandatory: bool,
                 emd_beneficiary: str, below_threshold: bool = False) -> None:
    value = _evidence_value(profile_key, field, threshold, mandatory)
    if value is None:
        return
    if below_threshold:
        # Scenario mutation: a genuine below-threshold value (the engine will
        # FAIL it honestly — nothing is hardcoded).
        t = threshold if isinstance(threshold, (int, float)) and threshold > 0 else value
        value = int(t * 0.6)
    if field == "turnover_inr":
        lakh = value / 100000
        lakh_str = str(int(lakh)) if float(lakh).is_integer() else f"{lakh:.1f}"
        add(
            "BALANCE_SHEET",
            turnover=f"Rs {lakh_str} lakh",
            financial_year="2023-24",
            turnover_period="FY 2023-24",
            auditor_name="Shah & Associates, Chartered Accountants (demo)",
        )
    elif field == "experience_years":
        add("EXPERIENCE_CERTIFICATE", experience=f"{value} years")
    elif field == "past_performance_pct":
        add(
            "PAST_PERFORMANCE_CERTIFICATE",
            past_performance=f"{value}%",
            past_performance_client="Demo PSU Client Ltd.",
        )
    elif field == "local_content_pct":
        add("MII_DECLARATION", local_content=f"{value}%")
    elif field == "emd_amount_inr":
        add(
            "EMD_RECEIPT",
            emd_amount=f"Rs {value:,}",
            emd_reference="DEMO-UTR-20260920",
            emd_date="20-09-2026",
            emd_beneficiary=emd_beneficiary,
        )
    # Unknown extracted fields: no section — honest MISSING downstream.


def build_dossier_sections(requirements, profile_key: str,
                            emd_beneficiary: str = "Demo Tendering Authority",
                            plan=None,
                            ) -> list[tuple[str, dict]]:
    """Build ``(template_type, data)`` dossier sections for a tender.

    Iterates the tender's actual requirements and emits the evidence section
    each requirement type needs. Unknown rule types / sources are skipped so
    the compliance engine reports them honestly (MISSING / REVIEW_REQUIRED)
    instead of the demo inventing evidence.

    ``plan`` is an optional :class:`ScenarioPlan
    <app.seed.demo_scenarios.ScenarioPlan>` carrying per-template field
    mutations, name overrides and omit lists for mismatch-focused scenarios.
    """
    if profile_key not in PROFILES:
        raise ValueError(f"Unknown demo profile '{profile_key}'")
    profile = PROFILES[profile_key]
    identifiers = dict(profile["identifiers"])
    legal_name = profile["legal_name"]
    if plan is not None:
        # Scenario identities carry their own seeded identifiers; the plan's
        # legal name is the bidder's declared name.
        identifiers.update(plan.identifiers)
        legal_name = plan.legal_name
    base = {
        "legal_name": legal_name,
        "address": profile["address"],
        "email": profile["contact_email"],
        "phone": profile["contact_phone"],
    }
    sections: dict[str, dict] = {}
    omit_templates = set(getattr(plan, "omit_templates", None) or ())

    def add(template_type: str, **kw) -> None:
        if template_type in (profile.get("omit_sections") or ()):
            return  # scenario: this evidence section is deliberately missing
        if template_type in omit_templates:
            return  # scenario plan: deliberately missing evidence
        if template_type not in sections:  # first wins; dedupes EXPERIENCE etc.
            data = {**base, **kw}
            if plan is not None:
                data.update((plan.doc_mutations.get(template_type) or {}))
                # drop sentinel keys used only for value computation
                data.pop("_turnover_below_threshold", None)
                data.pop("_emd_below_threshold", None)
            sections[template_type] = data
            override = (profile.get("document_name_overrides") or {}).get(
                template_type
            )
            if plan is not None and template_type in plan.doc_name_overrides:
                override = plan.doc_name_overrides[template_type]
            if override:
                sections[template_type]["legal_name"] = override

    # Scenario: missing-evidence profiles (e.g. "vertex") deliberately omit
    # everything except turnover + experience. Flag-based so generated
    # bulk-demo profiles can opt in; the "vertex" key keeps historic behaviour.
    omit_evidence = profile_key == "vertex" or bool(profile.get("omit_evidence"))
    allowlist = profile.get("evidence_allowlist") or _VERTEX_ALLOWED_SOURCES

    for req in sorted(requirements, key=lambda r: r.id or 0):
        rule_type = (req.rule_type or "").upper()
        cfg = req.rule_config or {}
        source = str(cfg.get("source") or req.verification_source or "").upper()
        value_source = str(cfg.get("value_source") or "")
        mandatory = bool(req.mandatory)

        if omit_evidence and not (
            rule_type in ("MINIMUM", "EXISTENCE")
            and value_source in allowlist
        ) and not (
            # Missing-evidence profiles keep the experience certificate too
            # (DOCUMENT_REQUIRED on the new template).
            rule_type == "DOCUMENT_REQUIRED"
            and "EXPERIENCE_CERTIFICATE" in (cfg.get("document_types") or [])
        ):
            continue  # deliberately omitted evidence

        if rule_type == "REGISTRATION_STATUS":
            _add_registration(add, source, identifiers, legal_name,
                              profile.get("trade_name", legal_name))
        elif rule_type in ("MINIMUM", "EXISTENCE") and value_source.startswith("extracted."):
            field = value_source.split(".", 1)[1]
            mut = (plan.doc_mutations.get(
                "BALANCE_SHEET" if field == "turnover_inr"
                else "EMD_RECEIPT" if field == "emd_amount_inr" else ""
            ) or {}) if plan else {}
            below = bool(mut.get("_turnover_below_threshold") or
                         mut.get("_emd_below_threshold"))
            _add_minimum(add, profile_key, field, cfg.get("value"), mandatory,
                         emd_beneficiary, below_threshold=below)
        elif rule_type == "MATCH" and value_source == "extracted.itr_financial_year":
            fy = "2023-24"
            if plan and (plan.doc_mutations.get("ITR_DOCUMENT") or {}).get("itr_financial_year"):
                fy = plan.doc_mutations["ITR_DOCUMENT"]["itr_financial_year"]
            add(
                "ITR_DOCUMENT",
                pan=identifiers.get("pan", ""),
                itr_financial_year=fy,
                assessment_year="2024-25" if fy == "2023-24" else "2023-24",
                total_income="Rs 42,50,000",
            )
        elif rule_type == "DATE_VALIDITY" and value_source == "extracted.iso_valid_until":
            valid_until = "31-03-2028"
            if plan and (plan.doc_mutations.get("ISO_9001_CERTIFICATE") or {}).get("iso_valid_until"):
                valid_until = plan.doc_mutations["ISO_9001_CERTIFICATE"]["iso_valid_until"]
            add(
                "ISO_9001_CERTIFICATE",
                iso_certificate_number="ISO-2024-88412",
                iso_valid_from="01-04-2024",
                iso_valid_until=valid_until,
            )
        elif rule_type == "BOOLEAN" and value_source == "extracted.oem_authorization_valid":
            add(
                "OEM_AUTHORIZATION",
                oem_name="Kirloskar Brothers Ltd. (demo)",
                oem_authorization="Yes",
                valid_until="31-03-2028",
            )
        elif rule_type == "DOCUMENT_REQUIRED":
            for doc_type in cfg.get("document_types") or []:
                if doc_type == "STARTUP_INDIA_CERTIFICATE" and profile_key == "apex":
                    add(
                        "STARTUP_INDIA_CERTIFICATE",
                        certificate_number="DIPP-D-2026001234",
                        dpiit_recognition="Yes",
                    )
                elif doc_type == "EXPERIENCE_CERTIFICATE":
                    add(
                        "EXPERIENCE_CERTIFICATE",
                        experience="5 years",
                        project_name="Demo Pumping Station Package (demo)",
                        client_name="Demo Municipal Corp (demo)",
                        completion_date="15-03-2024",
                    )
                # BID_DOSSIER is satisfied by this dossier itself; unknown
                # document types are left MISSING honestly.
        # CUSTOM_RULE / IDENTITY_MATCH / verification-backed EXISTENCE need no
        # dossier section (portal data / cross-checks).

    # Non-debarment undertaking: a standard bid declaration, emitted for every
    # profile except missing-evidence scenarios. The declaration text is the
    # bidder's own claim; the consistency engine compares it against the
    # BLACKLIST verification source (a false declaration is the scenario the
    # check is built to catch).
    if not omit_evidence and not omit_templates:
        add(
            "NON_DEBARMENT_DECLARATION",
            debarment_declaration=profile.get(
                "debarment_declaration",
                "Not debarred or blacklisted by any government authority.",
            ),
        )

    return list(sections.items())

    return list(sections.items())


def demo_banner() -> str:
    return _DEMO_BANNER


# Historic scenario flags, now explicit (behaviour unchanged).
PROFILES["apex"]["deliberate_minor_item"] = True
PROFILES["vertex"]["omit_evidence"] = True


def register_generated_profile(key: str, profile: dict) -> None:
    """Register a generated bulk-demo profile (seed-only, not business logic).

    The profile dict uses the same shape as the entries in ``PROFILES`` and
    may additionally set:

    - ``omit_evidence``: bool — emit only turnover + experience sections
      (missing-evidence scenario).
    - ``evidence_allowlist``: set of ``extracted.*`` value sources kept when
      ``omit_evidence`` is set.
    - ``omit_sections``: iterable of dossier template types to skip
      (partial-evidence scenario, e.g. a forgotten EMD receipt).
    - ``deliberate_minor_item``: bool — below-threshold value on a
      non-mandatory requirement.

    Idempotent per key: re-registering the same key is a no-op.
    """
    if key in PROFILES:
        return
    required = (
        "legal_name", "identifiers", "address",
        "contact_name", "contact_email", "contact_phone",
    )
    missing = [k for k in required if k not in profile]
    if missing:
        raise ValueError(
            f"Generated profile '{key}' missing keys: {missing}"
        )
    PROFILES[key] = profile
