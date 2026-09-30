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

FOOTER_TEXT = "DEMO DOCUMENT \u2014 generated for prototype demonstration"

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
