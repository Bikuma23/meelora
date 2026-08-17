"""Frozen PDF renderers for AR source documents (invoice + dunning reminder).

Self-contained reportlab builders (no cross-import to server.py). The output is
byte-stable given identical inputs so the SHA-256 of an approved invoice is a
faithful fingerprint of the approved version.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage)

NAVY = colors.HexColor("#063044")
GREY = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")


def _accent(accent):
    """Company brand accent → reportlab color; falls back to NAVY on any issue."""
    try:
        if accent and isinstance(accent, str) and accent.strip().startswith("#") and len(accent.strip()) in (4, 7):
            return colors.HexColor(accent.strip())
    except Exception:
        pass
    return NAVY


def _logo_flowable(logo_bytes, max_h=18 * mm, max_w=48 * mm):
    """Canonical company logo as a ratio-preserving flowable (None on failure)."""
    if not logo_bytes:
        return None
    try:
        ir = ImageReader(BytesIO(logo_bytes))
        iw, ih = ir.getSize()
        if not iw or not ih:
            return None
        r = min(max_w / iw, max_h / ih)
        img = RLImage(BytesIO(logo_bytes), width=iw * r, height=ih * r)
        img.hAlign = "LEFT"
        return img
    except Exception:
        return None



def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("arTitle", parent=ss["Title"], fontSize=18, textColor=NAVY, spaceAfter=2))
    ss.add(ParagraphStyle("arMeta", parent=ss["Normal"], fontSize=8.5, textColor=GREY, leading=12))
    ss.add(ParagraphStyle("arLbl", parent=ss["Normal"], fontSize=7.5, textColor=GREY))
    ss.add(ParagraphStyle("arVal", parent=ss["Normal"], fontSize=9.5, textColor=NAVY))
    ss.add(ParagraphStyle("arSmall", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#334155"), leading=11))
    return ss


def _fmt(v, cur):
    return f"{float(v or 0):,.2f} {cur}".replace(",", " ")


def _addr_block(ss, title, name, lines):
    out = [Paragraph(title, ss["arLbl"]), Paragraph(f"<b>{name or ''}</b>", ss["arVal"])]
    for ln in (lines or []):
        if ln:
            out.append(Paragraph(str(ln), ss["arSmall"]))
    return out


def build_invoice_pdf(*, company, customer, invoice, logo_bytes=None, accent=None) -> bytes:
    ss = _styles()
    acc = _accent(accent)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title=f"Facture {invoice.get('number') or ''}")
    cur = invoice.get("currency") or (company or {}).get("functional_currency") or ""
    el = []
    logo = _logo_flowable(logo_bytes)
    if logo is not None:
        el.append(logo)
        el.append(Spacer(1, 3 * mm))
    title_style = ParagraphStyle("arTitleAcc", parent=ss["arTitle"], textColor=acc)
    el.append(Paragraph((company or {}).get("name") or "Société", title_style))
    seller_meta = []
    for k in ("address", "city", "postal_code", "country"):
        if (company or {}).get(k):
            seller_meta.append(str(company[k]))
    tax_ids = (company or {}).get("tax_ids") or {}
    for k, v in tax_ids.items():
        if v:
            seller_meta.append(f"{k}: {v}")
    if seller_meta:
        el.append(Paragraph(" · ".join(seller_meta), ss["arMeta"]))
    el.append(Spacer(1, 8 * mm))

    # Title + meta box
    status = invoice.get("status")
    head = Table([[Paragraph("<b>FACTURE</b>", ss["arVal"]),
                   Paragraph(f"N° <b>{invoice.get('number') or '(brouillon)'}</b>", ss["arVal"])],
                  [Paragraph(f"Date : {invoice.get('issue_date') or ''}", ss["arSmall"]),
                   Paragraph(f"Échéance : {invoice.get('due_date') or '—'}", ss["arSmall"])],
                  [Paragraph(f"Devise : {cur}", ss["arSmall"]),
                   Paragraph(f"Statut : {status}", ss["arSmall"])]],
                 colWidths=[90 * mm, 88 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    ref_bits = []
    if invoice.get("customer_po"):
        ref_bits.append(f"Réf. / PO client : <b>{invoice.get('customer_po')}</b>")
    if invoice.get("reference"):
        ref_bits.append(f"Référence : {invoice.get('reference')}")
    el.append(head)
    if ref_bits:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(" · ".join(ref_bits), ss["arSmall"]))
    el.append(Spacer(1, 6 * mm))

    # Customer block
    cust = customer or {}
    cust_lines = [cust.get("billing_address"), cust.get("billing_email") or (cust.get("emails") or [None])[0],
                  cust.get("phone")]
    for tk, tv in (cust.get("tax_ids") or {}).items():
        if tv:
            cust_lines.append(f"{tk}: {tv}")
    el += _addr_block(ss, "FACTURÉ À", cust.get("name"), cust_lines)
    if cust.get("shipping_address"):
        el.append(Spacer(1, 2 * mm))
        el += _addr_block(ss, "LIVRÉ À", cust.get("name"), [cust.get("shipping_address")])
    el.append(Spacer(1, 6 * mm))

    # Lines table
    rows = [["Description", "Qté", "P.U.", "Net", "Taxe", "Total ligne"]]
    for ln in invoice.get("lines", []):
        tax_amt = ln.get("tax_amount", (ln.get("tax") or {}).get("tax_total", 0))
        line_total = round(float(ln.get("line_net") or 0) + float(tax_amt or 0), 2)
        rows.append([ln.get("description") or "",
                     f"{float(ln.get('qty') or 0):g}", _fmt(ln.get("unit_price"), cur),
                     _fmt(ln.get("line_net"), cur), _fmt(tax_amt, cur), _fmt(line_total, cur)])
    tbl = Table(rows, colWidths=[70 * mm, 14 * mm, 24 * mm, 24 * mm, 22 * mm, 24 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(tbl)
    el.append(Spacer(1, 4 * mm))

    # Tax summary by component
    comps = {}
    for ln in invoice.get("lines", []):
        for c in (ln.get("tax") or {}).get("components", []):
            k = f"{c.get('name')} ({float(c.get('rate') or 0) * 100:g}%)"
            comps[k] = round(comps.get(k, 0) + float(c.get("amount") or 0), 2)
    tot_rows = [["Sous-total", _fmt(invoice.get("subtotal"), cur)]]
    for k, v in comps.items():
        tot_rows.append([k, _fmt(v, cur)])
    tot_rows.append(["Taxes", _fmt(invoice.get("tax_total"), cur)])
    tot_rows.append(["TOTAL", _fmt(invoice.get("total"), cur)])
    tt = Table(tot_rows, colWidths=[120 * mm, 58 * mm])
    tt.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, NAVY), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), NAVY), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    el.append(tt)

    fx = invoice.get("fx") or {}
    if fx.get("rate") and fx.get("rate") != 1.0:
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph(f"Taux de change figé : 1 {fx.get('from_currency')} = {fx.get('rate')} "
                            f"{fx.get('to_currency')} (au {fx.get('rate_date')})", ss["arMeta"]))
    terms = (customer or {}).get("payment_terms") or invoice.get("payment_terms")
    if terms:
        el.append(Spacer(1, 4 * mm))
        el.append(Paragraph(f"Conditions de paiement : {terms}", ss["arSmall"]))
    if invoice.get("customer_notes"):
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(invoice["customer_notes"], ss["arSmall"]))
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph("Document comptable figé — généré automatiquement à l'approbation.", ss["arMeta"]))
    doc.build(el)
    return buf.getvalue()


def build_reminder_pdf(*, company, customer, invoice, level, message, logo_bytes=None, accent=None) -> bytes:
    ss = _styles()
    acc = _accent(accent)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    cur = invoice.get("currency") or ""
    labels = {1: "Premier rappel", 2: "Deuxième rappel", 3: "Rappel final"}
    title_style = ParagraphStyle("arTitleAccR", parent=ss["arTitle"], textColor=acc)
    el = []
    logo = _logo_flowable(logo_bytes)
    if logo is not None:
        el.append(logo)
        el.append(Spacer(1, 3 * mm))
    el += [Paragraph((company or {}).get("name") or "Société", title_style),
          Spacer(1, 6 * mm),
          Paragraph(f"<b>{labels.get(level, 'Rappel')}</b>", ss["arVal"]),
          Spacer(1, 4 * mm),
          Paragraph(f"À l'attention de <b>{(customer or {}).get('name') or ''}</b>", ss["arSmall"]),
          Spacer(1, 4 * mm)]
    if message:
        el.append(Paragraph(message, ss["arSmall"]))
        el.append(Spacer(1, 4 * mm))
    rows = [["Facture", "Date", "Échéance", "Solde dû"],
            [invoice.get("number") or invoice.get("id") or "", invoice.get("issue_date") or "",
             invoice.get("due_date") or "—", _fmt(invoice.get("balance"), cur)]]
    t = Table(rows, colWidths=[45 * mm, 40 * mm, 40 * mm, 49 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el.append(t)
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph("Nous vous remercions de bien vouloir régulariser le solde dû dans les meilleurs délais. "
                        "Si le règlement a déjà été effectué, veuillez ne pas tenir compte de ce rappel.", ss["arSmall"]))
    doc.build(el)
    return buf.getvalue()
