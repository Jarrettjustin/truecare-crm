"""
fill_packet.py
Burns the agent's typed values + drawn signature onto the EXACT onboarding
packet (onboarding_packet.pdf) at calibrated coordinates, then appends a short
execution/audit page. Runtime deps: pypdf + reportlab only.

Coordinates are in PDF points (origin = bottom-left), calibrated against the
31-page packet (US Letter, 612x792). Page 9 (ACH/SSN/bank) is intentionally
left untouched — that data is never collected here.
"""
import io
import base64
from datetime import datetime

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

PAGE_W, PAGE_H = 612, 792
FONT = "Helvetica"
FONT_SIZE = 10

# field -> (page_index, x, y)  for typed text
TEXT_FIELDS = {
    # Page 2 — Independent Contractor Agreement
    "agent_name_p2":     (1, 228, 651),
    "npn":               (1, 118, 559),
    # Page 8 — Agent signature block (company side already executed)
    "agent_print_name":  (7, 346, 472),
    "agent_title":       (7, 315, 460),
    "agent_date":        (7, 317, 449),
    # Page 16 — Employee (Confidentiality/IP/Restrictive Covenants)
    "emp_name":          (15, 112, 555),
    "emp_date":          (15, 106, 540),
    "init_2_13":         (15, 250, 513),
    # Page 18 — Exhibit A
    "exhibit_a_initials":(17, 222, 343),
    "exhibit_a_date":    (17, 300, 343),
    # Page 19 — Handbook effective date
    "handbook_eff_date": (18, 156, 347),
    # Page 30 — Handbook acknowledgment name
    "handbook_name":     (29, 168, 81),
    # Page 31 — Handbook date
    "handbook_date":     (30, 105, 710),
}

# signature image placements: page_index, x, y, width, height
SIG_FIELDS = [
    (7,  305, 474, 120, 12),   # Page 8  "By:" (agent)
    (15, 128, 560, 150, 14),   # Page 16 "Signature:" (employee)
    (30, 142, 674, 150, 16),   # Page 31 "E-Signature:"
]


def _overlay_for_page(page_idx, text_items, sig_reader):
    """Build a single-page overlay PDF (in-memory) for one packet page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont(FONT, FONT_SIZE)
    c.setFillColorRGB(0.05, 0.05, 0.2)  # dark ink-blue
    for (x, y, value) in text_items:
        c.drawString(x, y, str(value))
    if sig_reader is not None:
        for (idx, x, y, w, h) in SIG_FIELDS:
            if idx == page_idx:
                c.drawImage(sig_reader, x, y, width=w, height=h,
                            mask="auto", preserveAspectRatio=True, anchor="sw")
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def _audit_page(meta):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = PAGE_H - 90
    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(0.07, 0.30, 0.38)  # TrueCare teal
    c.drawString(72, y, "Electronic Signature Certificate")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    y -= 28
    c.drawString(72, y, "This page records the electronic execution of the attached TrueCare onboarding packet.")
    y -= 30
    rows = [
        ("Signer name", meta.get("full_name", "")),
        ("Signer email", meta.get("email", "")),
        ("National Producer Number (NPN)", meta.get("npn", "")),
        ("Executed (UTC)", meta.get("timestamp", "")),
        ("Signer IP address", meta.get("ip", "")),
        ("Applicant record ID", str(meta.get("aid", ""))),
        ("Consent", "Signer agreed to use electronic records and signatures."),
    ]
    for label, val in rows:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(250, y, str(val))
        y -= 20
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def _decode_signature(sig_data_url):
    if not sig_data_url:
        return None
    try:
        b64 = sig_data_url.split(",", 1)[1] if "," in sig_data_url else sig_data_url
        png = base64.b64decode(b64)
        return ImageReader(io.BytesIO(png))
    except Exception:
        return None


def fill_packet(template_path, out_path, data, meta):
    """
    template_path: path to onboarding_packet.pdf
    out_path: where to write the signed PDF
    data: dict of field values (see TEXT_FIELDS keys; names are auto-fanned out)
    meta: dict with full_name, email, npn, timestamp, ip, aid, signature(dataURL)
    """
    sig_reader = _decode_signature(meta.get("signature"))

    # Fan a single "full_name" / "date" / "initials" into the right blanks.
    full_name = data.get("full_name", "")
    exec_date = data.get("date", datetime.utcnow().strftime("%m/%d/%Y"))
    values = {
        "agent_name_p2": full_name,
        "npn": data.get("npn", ""),
        "agent_print_name": full_name,
        "agent_title": "Independent Agent",
        "agent_date": exec_date,
        "emp_name": full_name,
        "emp_date": exec_date,
        "init_2_13": data.get("init_2_13", ""),
        "exhibit_a_initials": data.get("init_exhibit", ""),
        "exhibit_a_date": exec_date,
        "handbook_eff_date": exec_date,
        "handbook_name": full_name,
        "handbook_date": exec_date,
    }

    # group text items per page
    per_page = {}
    for field, (pidx, x, y) in TEXT_FIELDS.items():
        v = values.get(field, "")
        if v == "" and field not in ("agent_title",):
            continue
        per_page.setdefault(pidx, []).append((x, y, v))

    reader = PdfReader(template_path)
    writer = PdfWriter()
    sig_pages = {f[0] for f in SIG_FIELDS}

    for i, page in enumerate(reader.pages):
        if i in per_page or (sig_reader is not None and i in sig_pages):
            overlay = _overlay_for_page(i, per_page.get(i, []), sig_reader)
            page.merge_page(overlay)
        writer.add_page(page)

    writer.add_page(_audit_page(meta))

    with open(out_path, "wb") as fh:
        writer.write(fh)
    return out_path
