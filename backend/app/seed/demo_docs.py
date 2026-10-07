"""Demo document PDF generator (CONTRACT §14).

``generate_pdf(document_type, data) -> bytes`` builds one realistic,
single-page PDF with selectable text for each supported document type.

The mock LLM (``llm_service.MockLLMProvider``) parses labeled lines of the
form ``Label: value``; templates therefore emit exactly the labels it
recognizes. Each template also carries its classification keywords so the
pipeline's keyword classifier re-detects the intended document type.

All content is fictional demo data — no real personal data.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

FOOTER_TEXT = "SAMPLE \u2014 FOR DEMONSTRATION ONLY \u2014 fictional data, not a government-issued certificate"

# document_type -> centered bold title (also carries classification keywords)
_TITLES = {
    "PAN_CERTIFICATE": "Permanent Account Number Card",
    "GST_CERTIFICATE": "Goods and Services Tax Registration Certificate",
    "UDYAM_CERTIFICATE": "Udyam Registration Certificate",
    "ITR": "Income Tax Return Acknowledgement",
    "TURNOVER_CERTIFICATE": "Turnover Certificate",
    "EXPERIENCE_CERTIFICATE": "Experience / Completion Certificate",
    "OEM_AUTHORIZATION": "OEM Authorization Certificate",
    "EPFO_CERTIFICATE": "Employees\u2019 Provident Fund Registration Certificate",
    "ESIC_CERTIFICATE": "Employees\u2019 State Insurance Registration Certificate",
    "MII_DECLARATION": "Make in India \u2014 Local Content Declaration",
    "STARTUP_INDIA_CERTIFICATE": "Startup India Recognition Certificate",
    "EMD_PAYMENT": "Earnest Money Deposit (EMD) \u2014 Payment Proof",
    "PAST_PERFORMANCE_CERTIFICATE": "Past Performance Certificate",
    "NON_DEBARMENT_DECLARATION": "Non-Debarment Declaration",
    "BALANCE_SHEET": "Balance Sheet Summary \u2014 Financial Year",
    "ISO_9001_CERTIFICATE": "ISO 9001:2015 \u2014 Quality Management System Certificate",
    "MCA21_CERTIFICATE": "MCA21 \u2014 Certificate of Incorporation",
    "ITR_DOCUMENT": "Income Tax Return \u2014 Financial Year",
    "EMD_RECEIPT": "EMD Receipt \u2014 Deposit Confirmation",
}


def _paragraphs(document_type: str, data: dict) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Return (title, labeled_lines, body_paragraphs) for a document type."""
    d = data
    name = d.get("legal_name", "")
    if document_type == "PAN_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("PAN", d.get("pan", "")),
                ("Incorporation Date", d.get("incorporation_date", "")),
                ("Address", d.get("address", "")),
                ("Email", d.get("email", "")),
                ("Phone", d.get("phone", "")),
            ],
            [
                "This is to certify that the Permanent Account Number shown above "
                "has been allotted to the named entity and is recorded as active."
            ],
        )
    if document_type == "GST_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Trade Name", d.get("trade_name", "")),
                ("GSTIN", d.get("gstin", "")),
                ("PAN", d.get("pan", "")),
                ("Registration Date", d.get("registration_date", "")),
                ("Address", d.get("address", "")),
            ],
            [
                "This certificate confirms registration under the Goods and Services "
                "Tax Act. The registration is active as on the date of issue of this "
                "demo certificate."
            ],
        )
    if document_type == "UDYAM_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("UDYAM", d.get("udyam", "")),
                ("Valid Until", d.get("valid_until", "")),
                ("Address", d.get("address", "")),
            ],
            [
                "This UDYAM registration certificate is issued to the enterprise "
                "named above and remains valid until the date shown, subject to "
                "continued compliance."
            ],
        )
    if document_type == "ITR":
        return (
            _TITLES[document_type],
            [
                ("Acknowledgement Number", d.get("acknowledgement_number", "")),
                ("Legal Name", name),
                ("PAN", d.get("pan", "")),
            ],
            [
                "This acknowledgement confirms receipt of the income tax return "
                "filed by the named entity for the relevant assessment year."
            ],
        )
    if document_type == "TURNOVER_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Turnover", d.get("turnover", "")),
                ("Turnover Period", d.get("turnover_period", "")),
            ],
            [
                "This is to certify that the annual turnover of the entity for the "
                "stated period is as mentioned above, as per the books of account "
                "maintained by the entity."
            ],
        )
    if document_type == "EXPERIENCE_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Experience", d.get("experience", "")),
            ],
            [
                "This completion certificate is issued to confirm that the entity "
                "named above has experience in the supply of industrial goods, and "
                "has executed similar orders to the satisfaction of its clients."
            ],
        )
    if document_type == "OEM_AUTHORIZATION":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("OEM Name", d.get("oem_name", "")),
                ("OEM Authorization", d.get("oem_authorization", "")),
                ("Valid Until", d.get("valid_until", "")),
            ],
            [
                f"{d.get('oem_name', '')}, an Original Equipment Manufacturer, "
                "hereby authorizes the bidder named above to quote and supply its "
                "products. The undersigned manufacturer confirms this authorization "
                "is genuine and current."
            ],
        )
    if document_type == "EPFO_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("EPFO Code", d.get("epfo_code", "")),
                ("Address", d.get("address", "")),
            ],
            [
                "This certificate confirms registration of the establishment with "
                "the Employees\u2019 Provident Fund Organisation under the code "
                "shown above."
            ],
        )
    if document_type == "ESIC_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("ESIC Code", d.get("esic_code", "")),
                ("Valid Until", d.get("valid_until", "")),
                ("Address", d.get("address", "")),
            ],
            [
                "This certificate confirms registration of the establishment with "
                "the Employees\u2019 State Insurance Corporation under the code "
                "shown above."
            ],
        )
    if document_type == "MII_DECLARATION":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Local Content", d.get("local_content", "")),
            ],
            [
                "We hereby declare under the Make in India policy that the local "
                "content in the goods offered is as stated above, with value "
                "addition carried out at our Indian manufacturing facility."
            ],
        )
    if document_type == "STARTUP_INDIA_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Certificate Number", d.get("certificate_number", "")),
                ("DPIIT Recognition", d.get("dpiit_recognition", "")),
            ],
            [
                "This certificate recognizes the entity named above as a startup "
                "under the Startup India initiative of DPIIT."
            ],
        )
    if document_type == "EMD_PAYMENT":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("EMD Amount", d.get("emd_amount", "")),
                ("Payment Reference", d.get("emd_reference", "")),
                ("Payment Date", d.get("emd_date", "")),
                ("Beneficiary", d.get("emd_beneficiary", "")),
            ],
            [
                "This section evidences payment of the Earnest Money Deposit for "
                "the bid. The deposit is held in favour of the beneficiary named "
                "above, as required by the bid document."
            ],
        )
    if document_type == "PAST_PERFORMANCE_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Past Performance", d.get("past_performance", "")),
                ("Client", d.get("past_performance_client", "")),
            ],
            [
                "This certificate confirms the supply performance of the entity "
                "named above against earlier government / PSU orders, stated as "
                "a percentage of the bid quantity."
            ],
        )
    if document_type == "NON_DEBARMENT_DECLARATION":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Debarment Declaration", d.get("debarment_declaration", "")),
            ],
            [
                "The bidder declares the debarment status stated above as on the "
                "date of this bid. Any debarment or blacklisting by a government "
                "authority would render this declaration false."
            ],
        )
    if document_type == "BALANCE_SHEET":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("Balance Sheet Year", d.get("financial_year", "")),
                ("Turnover", d.get("turnover", "")),
                ("Auditor Name", d.get("auditor_name", "")),
            ],
            [
                "This balance sheet summary for the financial year stated above "
                "has been audited by the statutory auditor named above. The "
                "statutory auditor certifies that the turnover and financial "
                "position are as per the audited books of account."
            ],
        )
    if document_type == "ISO_9001_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("ISO Certificate Number", d.get("iso_certificate_number", "")),
                ("ISO Valid From", d.get("iso_valid_from", "")),
                ("ISO Valid Until", d.get("iso_valid_until", "")),
                ("Certification Scope", d.get("iso_scope", "")),
            ],
            [
                "This ISO 9001 certificate is issued to the organization named "
                "above. The quality management system has been assessed and "
                "found to conform to ISO 9001:2015 requirements for the scope "
                "stated in the annexure to this certificate."
            ],
        )
    if document_type == "MCA21_CERTIFICATE":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("CIN", d.get("cin", "")),
                ("Incorporation Date", d.get("incorporation_date", "")),
                ("Company Status", d.get("company_status", "")),
            ],
            [
                "This certificate of incorporation is issued through the MCA21 "
                "portal of the Ministry of Corporate Affairs. The Corporate "
                "Identity Number (CIN) shown above is recorded as active in "
                "the MCA21 registry."
            ],
        )
    if document_type == "ITR_DOCUMENT":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("PAN", d.get("pan", "")),
                ("Financial Year", d.get("itr_financial_year", "")),
                ("Assessment Year", d.get("assessment_year", "")),
                ("Total Income", d.get("total_income", "")),
            ],
            [
                "This income tax return was filed for the financial year stated "
                "above, corresponding to the assessment year shown. The total "
                "income declared is as given above."
            ],
        )
    if document_type == "EMD_RECEIPT":
        return (
            _TITLES[document_type],
            [
                ("Legal Name", name),
                ("EMD Amount", d.get("emd_amount", "")),
                ("Payment Reference", d.get("emd_reference", "")),
                ("Payment Date", d.get("emd_date", "")),
                ("Beneficiary", d.get("emd_beneficiary", "")),
            ],
            [
                "This receipt confirms the deposit of the amount shown above "
                "towards the bid security requirement. This deposit "
                "confirmation is issued in favour of the beneficiary named "
                "above and the amount is held as per the bid document."
            ],
        )
    raise ValueError(f"Unsupported document_type: {document_type}")


def generate_pdf(document_type: str, data: dict) -> bytes:
    """Generate a one-page demo PDF for ``document_type`` with ``data``.

    Returns the PDF bytes. Text is selectable (reportlab Paragraph flowables).
    """
    title, lines, paras = _paragraphs(document_type, data)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DemoTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=17, leading=22, spaceAfter=6 * mm,
    )
    line_style = ParagraphStyle(
        "DemoLine", parent=styles["Normal"], fontSize=11, leading=16,
        spaceAfter=2 * mm, leftIndent=6 * mm,
    )
    body_style = ParagraphStyle(
        "DemoBody", parent=styles["Normal"], fontSize=10.5, leading=15,
        spaceBefore=4 * mm, alignment=4,  # justified
    )
    footer_style = ParagraphStyle(
        "DemoFooter", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=8, leading=10, textColor="#666666", spaceBefore=10 * mm,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=22 * mm, bottomMargin=20 * mm,
        title=title, author="BidVerify Demo",
    )
    story = [Paragraph(title, title_style), HRFlowable(width="100%", thickness=1)]
    for label, value in lines:
        story.append(Paragraph(f"<b>{label}:</b> {value}", line_style))
    for para in paras:
        story.append(Paragraph(para, body_style))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5))
    story.append(Paragraph(FOOTER_TEXT, footer_style))
    doc.build(story)
    return buf.getvalue()


SUPPORTED_TYPES = tuple(_TITLES)


# --------------------------------------------------------------------------
# Consolidated bid dossier — the bidder's SINGLE upload.
# --------------------------------------------------------------------------

DOSSIER_TITLE = "Consolidated Bid Dossier"


def dossier_section_title(template_type: str, data: dict) -> str:
    """Rendered heading of one dossier section.

    Used as the document title when a section is seeded as its own
    standalone evidence document (e.g. the Nova cross-document identity
    scenario) instead of inside the consolidated dossier.
    """
    return _paragraphs(template_type, data)[0]


def generate_dossier_pdf(legal_name: str, sections: list[tuple[str, dict]],
                         banner: str | None = None,
                         title: str | None = None,
                         subtitle: str | None = None) -> bytes:
    """Generate ONE multi-section PDF: the bidder's single consolidated upload.

    ``sections`` is a list of ``(template_type, section_data)`` pairs — the
    same labeled-line templates as the standalone documents, so the
    extraction pipeline pulls all fields from this one file.

    ``banner`` (optional) renders a centered notice under the title, e.g. to
    mark synthetic demo data.

    ``title`` / ``subtitle`` optionally replace the dossier heading and the
    "Single consolidated submission ..." line — used when one section is
    rendered as its own standalone evidence document (e.g. the Nova
    cross-document identity scenario).
    """
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DossierTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=18, leading=23, spaceAfter=3 * mm,
    )
    subtitle_style = ParagraphStyle(
        "DossierSub", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=10, leading=14, textColor="#444444", spaceAfter=6 * mm,
    )
    section_style = ParagraphStyle(
        "DossierSection", parent=styles["Heading2"],
        fontSize=13, leading=17, spaceBefore=6 * mm, spaceAfter=3 * mm,
        textColor="#1b3a7a",
    )
    line_style = ParagraphStyle(
        "DossierLine", parent=styles["Normal"], fontSize=11, leading=16,
        spaceAfter=2 * mm, leftIndent=6 * mm,
    )
    body_style = ParagraphStyle(
        "DossierBody", parent=styles["Normal"], fontSize=10.5, leading=15,
        spaceBefore=3 * mm, alignment=4,  # justified
    )
    footer_style = ParagraphStyle(
        "DossierFooter", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=8, leading=10, textColor="#666666", spaceBefore=10 * mm,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=title or DOSSIER_TITLE, author="BidVerify Demo",
    )
    name = legal_name or ""
    story = [
        Paragraph(title or DOSSIER_TITLE, title_style),
    ]
    if banner:
        banner_style = ParagraphStyle(
            "DossierBanner", parent=styles["Normal"], alignment=TA_CENTER,
            fontSize=9, leading=12, textColor="#8a1f1f", spaceAfter=3 * mm,
            borderWidth=1, borderColor="#8a1f1f", backColor="#fdf0f0",
            borderPadding=(4, 4, 4),
        )
        story.append(Paragraph(f"<b>{banner}</b>", banner_style))
    story += [
        Paragraph(
            subtitle if subtitle is not None else
            f"Single consolidated submission by <b>{name}</b> — all bidder "
            "information is extracted from this one document.",
            subtitle_style,
        ),
        HRFlowable(width="100%", thickness=1),
    ]
    for section, section_data in sections:
        sec_title, lines, paras = _paragraphs(section, section_data)
        story.append(Paragraph(sec_title, section_style))
        for label, value in lines:
            story.append(Paragraph(f"<b>{label}:</b> {value}", line_style))
        for para in paras:
            story.append(Paragraph(para, body_style))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5))
    story.append(Paragraph(FOOTER_TEXT, footer_style))
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------- demo logos
def generate_demo_logo(legal_name: str) -> bytes:
    """Generate a small fictional demo logo: company initials on a neutral
    background, returned as PNG bytes.

    This is clearly fictional demo art for the bidder's display avatar. It
    is display-only — no verification, compliance, risk or recommendation
    code path ever reads it. Deterministic per legal name (fixed-seed
    palette choice) so replays reproduce the same image.
    """
    import hashlib

    from PIL import Image, ImageDraw, ImageFont

    words = [w for w in (legal_name or "").split() if w and w[0].isalpha()]
    initials = "".join(w[0] for w in words[:2]).upper() or "CO"
    # Neutral slate palettes; deterministic per legal name.
    palettes = [
        ("#334155", "#f1f5f9"),  # slate
        ("#1e3a5f", "#e8eef5"),  # navy
        ("#3f3f46", "#f4f4f5"),  # zinc
        ("#44403c", "#f5f5f4"),  # stone
        ("#4a3728", "#faf6f0"),  # warm brown
    ]
    digest = hashlib.sha256(legal_name.encode("utf-8")).digest()
    bg, fg = palettes[digest[0] % len(palettes)]

    size = 256
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)
    # Subtle inner ring for a badge feel.
    draw.ellipse([14, 14, size - 14, size - 14], outline=fg, width=6)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 96)
    except OSError:
        try:
            font = ImageFont.load_default(size=96)
        except TypeError:  # very old Pillow without size support
            font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        initials,
        font=font,
        fill=fg,
    )
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
