"""Générateurs PDF « présentation » (ACCS) — États de Résultats & Bilan.
Reproduit la mise en page des modèles fournis (bandeaux marine, surlignage sarcelle,
% en sarcelle italique, colonnes mois + cumulatif + budget annuel).
Le logo sera ajouté dans une phase ultérieure (non intégré pour l'instant)."""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

NAVY = colors.HexColor("#0B3B4A")
TEAL = colors.HexColor("#1AA79A")
GREY = colors.HexColor("#E9EDEF")
LIGHTGREEN = colors.HexColor("#EAF1DE")
ORANGE = colors.HexColor("#C6862C")
RED = colors.HexColor("#C00000")
WHITE = colors.white
DARKTX = colors.HexColor("#1e293b")


def _fmt(v, dec=0):
    if v is None:
        v = 0.0
    if abs(v) < 0.5 and dec == 0:
        return "-"
    n = round(v, dec)
    s = f"{abs(n):,.{dec}f}"
    return f"({s})" if n < 0 else s


def _pct(v):
    if v is None:
        return ""
    return f"{v*100:,.1f}%"


def _find(lines, label):
    for ln in lines:
        if (ln.get("label") or "").strip() == label:
            return ln
    for ln in lines:
        if label and label.lower() in (ln.get("label") or "").strip().lower():
            return ln
    return {"values": {}, "label": label}


def _v(ln, k):
    return (ln.get("values") or {}).get(k) or 0.0


def build_presentation_pnl_pdf(data, year, month_label):
    """data = rapport pnl_sommaire (value_cols incl reel, bud_ca, ecart_ca, cumulatif, bud_ca_cum, ecart_ca_cum)."""
    lines = data["lines"]
    L = lambda lbl: _find(lines, lbl)
    rev = L("TOTAL DES REVENUS")
    month = int(data.get("month") or 6)

    def annual(ln, key_cum):
        cum = _v(ln, key_cum)
        return round(cum / month * 12, 0) if month else 0.0

    # colonnes: label | reel | budca | ecart | reel_cum | budca_cum | ecart_cum | annuel
    def row_vals(ln):
        return [_v(ln, "reel"), _v(ln, "bud_ca"), _v(ln, "ecart_ca"),
                _v(ln, "cumulatif"), _v(ln, "bud_ca_cum"), _v(ln, "ecart_ca_cum"),
                annual(ln, "bud_ca_cum")]

    def pct_vals(ln):
        rr = _v(rev, "reel") or 1; rb = _v(rev, "bud_ca") or 1
        cr = _v(rev, "cumulatif") or 1; cb = _v(rev, "bud_ca_cum") or 1
        ar = annual(rev, "bud_ca_cum") or 1
        p_reel = _v(ln, "reel") / rr
        p_bud = _v(ln, "bud_ca") / rb
        p_cum = _v(ln, "cumulatif") / cr
        p_bcum = _v(ln, "bud_ca_cum") / cb
        p_ann = annual(ln, "bud_ca_cum") / ar
        return [p_reel, p_bud, p_reel - p_bud, p_cum, p_bcum, p_cum - p_bcum, p_ann]

    styles = getSampleStyleSheet()
    lblS = ParagraphStyle("l", parent=styles["Normal"], fontSize=7.5, leading=9, textColor=DARKTX)

    # Spécification des lignes (type, label affiché, label source, %?)
    SPEC = [
        ("header", "REVENUS", None, False),
        ("data", "PROJETS", "PROJETS", False),
        ("data", "SERVICES", "SERVICES", False),
        ("data", "GESTION DE LA DEMANDE (GD)", "GESTION DE LA DEMANDE (GD)", False),
        ("grey", "TOTAL DES REVENUS", "TOTAL DES REVENUS", False),
        ("grey", "COUT DES MARCHANDISES VENDUES", "COUT DES MARCHANDISES VENDUES", False),
        ("navy", "BÉNÉFICE BRUT", "BÉNÉFICE BRUT", True),
        ("header", "CHARGES", None, False),
        ("data", "FRAIS DE VENTES, MARKETING ET COMM.", "FRAIS DE VENTES, MARKETING ET COMM.", False),
        ("data", "FRAIS INFORMATIQUE", "FRAIS INFORMATIQUE", False),
        ("data", "FRAIS RESSOURCES HUMAINES", "FRAIS RESSOURCES HUMAINES", False),
        ("data", "FRAIS D'ADMINISTRATION", "FRAIS D'ADMINISTRATION", False),
        ("grey", "TOTAL DES CHARGES", "TOTAL DES CHARGES", True),
        ("navy", "BAIIA", "BAIIA", True),
        ("data", "FRAIS FINANCIERS", "FRAIS FINANCIERS", False),
        ("data", "AMORTISSEMENT", "AMORTISSEMENT", False),
        ("navy", "BÉNÉFICE NET (PERTE NETTE) OPÉRATIONS", "BÉNÉFICE NET (PERTE NETTE) OPÉRATIONS", True),
        ("data", "AMORTISSEMENT - CARNET DE COMMANDES", "AMORTISSEMENT - CARNET DE COMMANDES", False),
        ("data", "AMORTISSEMENT - RELATIONS CLIENTS", "AMORTISSEMENT - RELATIONS CLIENTS", False),
        ("navy", "BÉNÉFICE NET (PERTE NETTE)", "BÉNÉFICE NET (PERTE NETTE)", False),
        ("gap", "", None, False),
        ("qp", "Q-P DES RÉSULTATS - COMMANDITÉ (0,01%)", "Q-P DES RÉSULTATS - COMMANDITÉ (0,01%)", False),
        ("qp", "Q-P DES RÉSULTATS - HILO (65%)", "Q-P DES RÉSULTATS - HILO (65%)", False),
        ("qp", "Q-P DES RÉSULTATS - ACCS (35%)", "Q-P DES RÉSULTATS - ACCS (35%)", False),
    ]

    # En-têtes (2 lignes de groupe)
    g1 = f"{month_label.upper()} {year}"
    g2 = f"{month_label.upper()} {year} - CUMULATIF"
    hdS = ParagraphStyle("hd", parent=styles["Normal"], fontSize=6, leading=7, alignment=1, fontName="Helvetica-Bold", textColor=NAVY)
    hdW = ParagraphStyle("hdw", parent=hdS, textColor=WHITE)
    hdT = ParagraphStyle("hdt", parent=hdS, textColor=TEAL)
    def hp(txt, white=False, teal=False):
        return Paragraph(txt, hdW if white else (hdT if teal else hdS))
    head1 = ["", Paragraph(g1, ParagraphStyle("g", parent=hdS, textColor=TEAL, fontSize=7)), "", "",
             Paragraph(g2, ParagraphStyle("g2", parent=hdS, textColor=TEAL, fontSize=7)), "", "",
             hp(f"BUDGET CA {year}", True)]
    head2 = ["", hp(f"REEL {year}"), hp(f"BUDGET<br/>CA {year}", teal=True), hp("ECART<br/>(REEL VS BUD. CA)"),
             hp("REEL A DATE"), hp(f"BUDGET<br/>CA {year}", teal=True), hp("ECART<br/>(REEL VS BUD. CA)"), hp("ANNUEL", True)]

    rows = [head1, head2]
    style = [
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (4, 0), (6, 0)),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (6, 0), TEAL),
        ("BACKGROUND", (7, 0), (7, 0), NAVY), ("TEXTCOLOR", (7, 0), (7, 1), WHITE),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (1, 1), (6, 1), 0.5, colors.HexColor("#94A3B8")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    r = 2
    for kind, disp, src, has_pct in SPEC:
        if kind == "gap":
            rows.append([""] * 8); r += 1; continue
        if kind == "header":
            rows.append([disp, "", "", "", "", "", "", ""])
            style += [("FONTNAME", (0, r), (0, r), "Helvetica-Bold"), ("TEXTCOLOR", (0, r), (0, r), NAVY)]
            r += 1; continue
        ln = L(src)
        vals = row_vals(ln)
        rows.append([disp] + [_fmt(v) for v in vals])
        # couleurs par type
        if kind == "navy":
            style += [("BACKGROUND", (0, r), (-1, r), NAVY), ("TEXTCOLOR", (0, r), (-1, r), WHITE),
                      ("FONTNAME", (0, r), (0, r), "Helvetica-Bold")]
        elif kind == "grey":
            style += [("BACKGROUND", (0, r), (6, r), GREY), ("FONTNAME", (0, r), (0, r), "Helvetica-BoldOblique"),
                      ("TEXTCOLOR", (0, r), (0, r), NAVY)]
        elif kind == "qp":
            style += [("BACKGROUND", (0, r), (6, r), GREY), ("FONTSIZE", (0, r), (-1, r), 6.5)]
        # colonnes BUDGET CA (2 & 5) en texte sarcelle (sauf bandeaux marine)
        if kind in ("data", "grey", "qp"):
            style += [("TEXTCOLOR", (2, r), (2, r), TEAL), ("TEXTCOLOR", (5, r), (5, r), TEAL)]
        # surlignage sarcelle colonne REEL (col1) + REEL A DATE (col4) pour lignes data
        if kind == "data":
            style += [("BACKGROUND", (1, r), (1, r), TEAL), ("TEXTCOLOR", (1, r), (1, r), WHITE),
                      ("BACKGROUND", (4, r), (4, r), TEAL), ("TEXTCOLOR", (4, r), (4, r), WHITE)]
        # colonne annuelle vert clair (sauf bandeaux marine où elle reste marine)
        if kind != "navy":
            style += [("BACKGROUND", (7, r), (7, r), LIGHTGREEN)]
        r += 1
        # ligne de % en sarcelle italique
        if has_pct:
            pv = pct_vals(ln)
            rows.append([""] + [_pct(p) for p in pv])
            style += [("TEXTCOLOR", (1, r), (-1, r), TEAL), ("FONTNAME", (1, r), (-1, r), "Helvetica-Oblique"),
                      ("FONTSIZE", (0, r), (-1, r), 6.5), ("BACKGROUND", (7, r), (7, r), LIGHTGREEN)]
            r += 1

    col_w = [70 * mm] + [17 * mm, 17 * mm, 20 * mm] + [17 * mm, 17 * mm, 20 * mm] + [20 * mm]
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle(style))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=10 * mm)
    hS = ParagraphStyle("h", parent=styles["Normal"], fontSize=11, textColor=DARKTX, fontName="Helvetica-Bold")
    subS = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=DARKTX)
    dateS = ParagraphStyle("d", parent=styles["Normal"], fontSize=8, textColor=ORANGE, fontName="Helvetica-Bold")
    confS = ParagraphStyle("c", parent=styles["Normal"], fontSize=8, textColor=ORANGE, fontName="Helvetica-Bold", alignment=2)
    header_tbl = Table([[
        [Paragraph("SOCIÉTÉ EN COMMANDITE ACCS", hS), Paragraph("États de Résultats", subS),
         Paragraph(f"{data.get('month_label','').upper()} {year}", dateS), Paragraph("En dollars canadiens (CAD)", subS)],
        Paragraph("CONFIDENTIEL", confS)]], colWidths=[210 * mm, 60 * mm])
    header_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    doc.build([header_tbl, Spacer(1, 5 * mm), tbl])
    buf.seek(0)
    return buf.getvalue()


def build_presentation_bilan_pdf(data, year, month_label, date_label):
    lines = data["lines"]
    L = lambda lbl: _find(lines, lbl)
    col = data.get("value_cols", ["cumulatif"])[0]
    val = lambda lbl: _v(L(lbl), col)

    ACTIF = [
        ("title", "ACTIF", None),
        ("header", "ACTIF COURT TERME", None),
        ("data", "Encaisse", "ENCAISSE"),
        ("data", "Comptes à recevoir", "COMPTES À RECEVOIR"),
        ("data", "Inventaire", "INVENTAIRE"),
        ("data", "Travaux en cours", "TRAVAUX EN COURS"),
        ("data", "Autres comptes à recevoir", "AUTRES COMPTES À RECEVOIR"),
        ("data", "Frais payé d'avance", "FRAIS PAYÉS D'AVANCE"),
        ("total", "Total de l'actif à court terme", "TOTAL DE L'ACTIF À COURT TERME"),
        ("gap", "", None),
        ("header", "IMMOBILISATIONS", None),
        ("data", "Actifs incorporel", "ACTIFS INCORPOREL"),
        ("data", "Amortissement - actifs incorporel", "AMORTISSEMENT CUMULÉ - ACTIFS INCORPORELS"),
        ("total", "Total - Actifs Incorporels", "TOTAL - ACTIFS INCORPOREL"),
        ("gap", "", None),
        ("header", "AUTRES IMMOBILISATIONS", None),
        ("data", "Autres Immobilisations", "IMMOBILISATIONS"),
        ("data", "Amortissement accumulé", "AMORTISSEMENT CUMULÉ - IMMOBILISATIONS"),
        ("total", "Total Autres immobilisations", "TOTAL -  IMMOBILISATIONS"),
    ]
    PASSIF = [
        ("title", "PASSIF", None),
        ("header", "PASSIF A COURT TERME", None),
        ("data", "Marge de crédit", "Marge de crédit - MC4"),
        ("data", "Crédit Rotatif", "Marge de crédit - MC5"),
        ("data", "Comptes fournisseurs", "COMPTES FOURNISSEURS"),
        ("data", "Dépôts clients Inter-co Service Hilo Inc.", "Dépôts Clients - Inter-Co - Hilo"),
        ("data", "Dépôts clients", "Dépôt clients"),
        ("data", "Autres comptes à payer (courus)", "AUTRES COMPTES À PAYER (COURUS)"),
        ("data", "Frais CCQ et avantages sociaux à payer", "FRAIS CCQ À PAYER"),
        ("data", "Comptes à payer - 9379 5599 Québec Inc", "COMPTES À PAYER - 9379 559 QUÉBEC INC."),
        ("data", "Salaires, vacances, commissions, RPBD à payer", "SALAIRES, VACANCES, COMMISSIONS"),
        ("data", "TPS/TVQ à payer", "TPS / TVQ À PAYER"),
        ("total", "Total du passif à court terme", "TOTAL PASSIF À COURT TERME"),
        ("gap", "", None),
        ("total", "PASSIF A LONG TERME", "TOTAL DU PASSIF À LONG TERME"),
        ("gap", "", None),
        ("total", "TOTAL PASSIF", "TOTAL DU PASSIF"),
        ("gap", "", None),
        ("header", "CAPITAUX", None),
        ("data", "Capital Actions - Parts ordinaires - Services Hilo", "Capital Actions - Parts ordinaires - Services Hilo"),
        ("data", "Capital Actions - Parts ordinaires - 9379-5599 Qc Inc", "Capital Actions - Parts ordinaires - 9379-5599 Qc Inc"),
        ("data", "Capital Actions - Part du commandité", "Capital Actions - Part du commandité"),
        ("data", "Bénéfice net (Perte nette)", "BÉNÉFICES NON-RÉPARTIS"),
        ("total", "Total Capitaux", "TOTAL AVOIR"),
    ]

    styles = getSampleStyleSheet()
    lblS = ParagraphStyle("l", parent=styles["Normal"], fontSize=8, leading=10, textColor=DARKTX)

    def build_side(spec):
        rows = []; st = []
        r = 0
        for kind, disp, src in spec:
            if kind == "gap":
                rows.append(["", ""]); r += 1; continue
            if kind == "header":
                rows.append([Paragraph(f"<b>{disp}</b>", lblS), ""])
                st += [("TEXTCOLOR", (0, r), (0, r), NAVY)]
                r += 1; continue
            if kind == "title":
                rows.append([Paragraph(f"<b>{disp}</b>", ParagraphStyle("t", parent=lblS, fontSize=11, textColor=TEAL)), ""])
                r += 1; continue
            v = val(src)
            rows.append([Paragraph(("  " + disp) if kind == "data" else f"<i>{disp}</i>", lblS), _fmt(v, 2)])
            if kind == "total":
                st += [("BACKGROUND", (0, r), (-1, r), GREY), ("FONTNAME", (1, r), (1, r), "Helvetica-BoldOblique"),
                       ("TEXTCOLOR", (0, r), (-1, r), NAVY)]
            else:
                st += [("BACKGROUND", (1, r), (1, r), TEAL), ("TEXTCOLOR", (1, r), (1, r), WHITE)]
                if v < 0:
                    st += [("TEXTCOLOR", (1, r), (1, r), colors.HexColor("#FCA5A5"))]
            r += 1
        st += [("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 8),
               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        t = Table(rows, colWidths=[75 * mm, 33 * mm]); t.setStyle(TableStyle(st))
        return t

    actif_t = build_side(ACTIF)
    passif_t = build_side(PASSIF)
    two_col = Table([[actif_t, passif_t]], colWidths=[112 * mm, 112 * mm])
    two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 8)]))

    # Bandeau total actif / passif
    tot_actif = val("TOTAL DE L'ACTIF")
    tot_pc = val("TOTAL PASSIF ET CAPITAUX")
    band = Table([["TOTAL ACTIF", _fmt(tot_actif, 2), "TOTAL PASSIF ET CAPITAUX", _fmt(tot_pc, 2)]],
                 colWidths=[50 * mm, 58 * mm, 62 * mm, 46 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
                              ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                              ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                              ("LEFTPADDING", (0, 0), (-1, -1), 6)]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=10 * mm)
    hS = ParagraphStyle("h", parent=styles["Normal"], fontSize=12, textColor=DARKTX, fontName="Helvetica-Bold")
    subS = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=DARKTX)
    dateS = ParagraphStyle("d", parent=styles["Normal"], fontSize=8, textColor=ORANGE, fontName="Helvetica-Bold")
    elems = [
        Paragraph("SOCIÉTÉ EN COMMANDITE ACCS", hS),
        Paragraph("BILAN À CE JOUR", subS),
        Paragraph(f"EN DATE DU {date_label.upper()}", dateS),
        Paragraph("En millions $ dollars canadiens (CAD)", subS),
        Spacer(1, 6 * mm), two_col, Spacer(1, 6 * mm), band,
    ]
    doc.build(elems)
    buf.seek(0)
    return buf.getvalue()
