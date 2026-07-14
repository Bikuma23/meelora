"""Moteur comptable : reproduit fidèlement un modèle Excel (Bilan / États des résultats)
en ré-évaluant son graphe de formules à partir d'une balance de vérification (BV).

Approche fiable :
- Les valeurs feuilles proviennent de la BV, indexées par NUMÉRO DE COMPTE (robuste à l'ordre).
- La structure du rapport (lignes, sous-totaux SUM, arithmétique de section) provient du modèle importé.
- Support VLOOKUP (compte -> valeur BV), SUM(plages/cellules), références inter-feuilles, arithmétique.
"""
import re
import openpyxl

VLOOKUP_RE = re.compile(r"VLOOKUP\([A-Z]*(\d+),\s*'BV Détaillée'!A\d+:M\d+,\s*(\d+),\s*FALSE\)")
XREF_RE = re.compile(r"'([^']+)'!([A-Z]+)(\d+)")
SUM_RE = re.compile(r"SUM\(([^)]*)\)")
CELLREF_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{1,3})(\d+)(?![A-Za-z0-9_(])")

# VLOOKUP index -> champ BV. BV cols: C=3 réel mois, D=4 budget rév2, E=5 budget rév1, F=6 budget CA,
# G=7 réel année préc., I=9 réel cumulatif, J=10 rév2 cum, K=11 rév1 cum, L=12 CA cum, M=13 préc. cum.
IDX_FIELD = {3: "c", 4: "d", 5: "e", 6: "f", 7: "g", 9: "i", 10: "j", 11: "k", 12: "l", 13: "m"}
BV_VALUE_COLS = {"C": "c", "D": "d", "E": "e", "F": "f", "G": "g", "I": "i", "J": "j", "K": "k", "L": "l", "M": "m"}


def col_letter_to_idx(letter):
    return openpyxl.utils.column_index_from_string(letter)


class ReportEngine:
    def __init__(self):
        # sheets[name] = {"rows": {row: {colLetter: formula_or_value}}, "acct": {row: account_int}}
        self.sheets = {}

    @classmethod
    def from_template(cls, path):
        eng = cls()
        wb = openpyxl.load_workbook(path, data_only=False)
        for name, acc_col in (("BV Détaillée", "A"), ("Bilan Détaillé", "B"), ("Resultats internes", "C")):
            if name not in wb.sheetnames:
                continue
            ws = wb[name]
            acc_i = col_letter_to_idx(acc_col)
            rows, acct = {}, {}
            for r in range(1, ws.max_row + 1):
                a = ws.cell(r, acc_i).value
                if isinstance(a, (int, float)) and float(a).is_integer():
                    acct[r] = int(a)
                cells = {}
                for c in range(1, ws.max_column + 1):
                    v = ws.cell(r, c).value
                    if v is not None:
                        cells[openpyxl.utils.get_column_letter(c)] = v
                if cells:
                    rows[r] = cells
            eng.sheets[name] = {"rows": rows, "acct": acct, "acc_col": acc_col}
        return eng

    def to_dict(self):
        sheets = {}
        for name, sd in self.sheets.items():
            sheets[name] = {
                "rows": {str(r): cells for r, cells in sd["rows"].items()},
                "acct": {str(r): a for r, a in sd["acct"].items()},
                "acc_col": sd["acc_col"],
            }
        return {"sheets": sheets}

    @classmethod
    def from_dict(cls, d):
        eng = cls()
        # JSON keys are strings -> normalise row keys to int
        for name, sd in d["sheets"].items():
            rows = {int(r): cells for r, cells in sd["rows"].items()}
            acct = {int(r): a for r, a in sd["acct"].items()}
            eng.sheets[name] = {"rows": rows, "acct": acct, "acc_col": sd["acc_col"]}
        return eng

    def compute_all(self, bv):
        """bv: {account_int: {'mov': float, 'cum': float}}. Retourne evaluator memoïsé."""
        memo = {}

        def bvval(acct, idx):
            if acct is None:
                return 0.0
            rec = bv.get(acct)
            if not rec:
                return 0.0
            f = IDX_FIELD.get(idx)
            return float(rec.get(f, 0.0)) if f else 0.0

        def comp(sheet, col, row, depth=0):
            key = (sheet, col, row)
            if key in memo:
                return memo[key]
            if depth > 400:
                return 0.0
            memo[key] = 0.0  # guard cycles
            sd = self.sheets.get(sheet)
            if not sd:
                return 0.0
            cell = (sd["rows"].get(row) or {}).get(col)
            # Feuille BV : cellule feuille (compte présent) -> valeur BV par compte
            if sheet == "BV Détaillée" and row in sd["acct"] and col in BV_VALUE_COLS:
                v = bvval(sd["acct"][row], next(i for i, f in IDX_FIELD.items() if f == BV_VALUE_COLS[col]))
                memo[key] = v
                return v
            if cell is None:
                return 0.0
            if isinstance(cell, (int, float)):
                memo[key] = float(cell)
                return float(cell)
            s = str(cell)
            if not s.startswith("="):
                return 0.0
            expr = s[1:].replace("$", "").replace("\xa0", "")
            # VLOOKUP -> valeur BV (compte = celui de la ligne référencée dans la feuille courante)
            def vlk(m):
                keyrow = int(m.group(1)); idx = int(m.group(2))
                acct = sd["acct"].get(keyrow)
                return repr(bvval(acct, idx))
            expr = VLOOKUP_RE.sub(vlk, expr)
            # Références inter-feuilles 'Sheet'!Cell
            def xref(m):
                sh, cl, rr = m.group(1), m.group(2), int(m.group(3))
                return repr(comp(sh, cl, rr, depth + 1))
            expr = XREF_RE.sub(xref, expr)
            # SUM(args) : plages ou cellules, dans la feuille/colonne courante
            def sum_sub(m):
                total_terms = []
                for arg in m.group(1).split(","):
                    arg = arg.strip()
                    rng = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", arg)
                    if rng:
                        c1, r1, c2, r2 = rng.group(1), int(rng.group(2)), rng.group(3), int(rng.group(4))
                        lo, hi = min(r1, r2), max(r1, r2)
                        for rr in range(lo, hi + 1):
                            total_terms.append(repr(comp(sheet, c1, rr, depth + 1)))
                    else:
                        single = re.match(r"([A-Z]+)(\d+)", arg)
                        if single:
                            total_terms.append(repr(comp(sheet, single.group(1), int(single.group(2)), depth + 1)))
                return "(" + "+".join(total_terms or ["0"]) + ")"
            expr = SUM_RE.sub(sum_sub, expr)
            # Références de cellule simples -> comp
            def ref_sub(m):
                return repr(comp(sheet, m.group(1), int(m.group(2)), depth + 1))
            expr = CELLREF_RE.sub(ref_sub, expr)
            expr = expr.replace("+-", "-")
            try:
                val = eval(expr, {"__builtins__": {}}, {})
            except Exception:
                val = 0.0
            if not isinstance(val, (int, float)):
                val = 0.0
            memo[key] = float(val)
            return float(val)

        return comp

    def template_accounts(self):
        """Ensemble des comptes présents dans les feuilles de rapport (Bilan + Résultats)."""
        accs = set()
        for name in ("Bilan Détaillé", "Resultats internes"):
            sd = self.sheets.get(name)
            if sd:
                accs.update(sd["acct"].values())
        return accs

    def account_names(self):
        names = {}
        for name, lbl_col in (("Bilan Détaillé", "C"), ("Resultats internes", "D")):
            sd = self.sheets.get(name)
            if not sd:
                continue
            for r, acct in sd["acct"].items():
                lbl = (sd["rows"].get(r) or {}).get(lbl_col)
                if acct is not None and isinstance(lbl, str) and acct not in names:
                    names[acct] = lbl.strip()
        return names

    def build_report(self, bv, sheet, value_cols, account_col, label_col, stop_after=None, stop_at=None):
        """stop_after: préfixes de libellé après lesquels arrêter (inclus). stop_at: préfixes de libellé
        à partir desquels arrêter (exclu — la ligne et tout ce qui suit sont retirés)."""
        comp = self.compute_all(bv)
        sd = self.sheets[sheet]
        ai = account_col
        out = []
        max_row = max(sd["rows"].keys())
        for r in range(1, max_row + 1):
            cells = sd["rows"].get(r)
            if not cells:
                continue
            acct = sd["acct"].get(r)
            label = cells.get(label_col)
            if label is None and acct is None:
                label = cells.get(ai)
            if isinstance(label, (int, float)):
                label = str(label)
            values = {}
            has_val = False
            for key, col in value_cols.items():
                v = comp(sheet, col, r)
                values[key] = round(v, 2)
                if abs(v) > 0.005:
                    has_val = True
            is_data = acct is not None
            first_col = value_cols[list(value_cols)[0]]
            raw = cells.get(first_col)
            is_formula = isinstance(raw, str) and raw.startswith("=")
            kind = "data" if is_data else ("total" if is_formula else "header")
            lbl_str = (label or "").strip() if isinstance(label, str) else label
            if stop_at and isinstance(lbl_str, str) and any(lbl_str.lower().startswith(s) for s in stop_at):
                break
            if label is None and not has_val:
                continue
            out.append({"row": r, "account": acct, "label": lbl_str, "kind": kind, "values": values})
            if stop_after and isinstance(lbl_str, str) and any(lbl_str.lower().startswith(s) for s in stop_after):
                break
        return out


if __name__ == "__main__":
    import sys
    P = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ef.xlsx"
    eng = ReportEngine.from_template(P)
    # charge BV depuis le fichier (valeurs mises en cache)
    wbc = openpyxl.load_workbook(P, data_only=True)
    ws = wbc["BV Détaillée"]
    bv = {}
    for r in range(3, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if isinstance(a, (int, float)) and float(a).is_integer():
            bv[int(a)] = {"c": float(ws.cell(r, 3).value or 0), "d": float(ws.cell(r, 4).value or 0),
                          "e": float(ws.cell(r, 5).value or 0), "f": float(ws.cell(r, 6).value or 0),
                          "g": float(ws.cell(r, 7).value or 0), "i": float(ws.cell(r, 9).value or 0),
                          "j": float(ws.cell(r, 10).value or 0), "k": float(ws.cell(r, 11).value or 0),
                          "l": float(ws.cell(r, 12).value or 0), "m": float(ws.cell(r, 13).value or 0)}
    comp = eng.compute_all(bv)

    def validate(sheet, tgt_col, label_col, acc_col, crit_max):
        ws2 = wbc[sheet]
        ti = col_letter_to_idx(tgt_col); li = col_letter_to_idx(label_col); aci = col_letter_to_idx(acc_col)
        checked = crit = 0; worst = []
        for r in range(3, ws2.max_row + 1):
            cached = ws2.cell(r, ti).value
            if not isinstance(cached, (int, float)):
                continue
            got = comp(sheet, tgt_col, r)
            checked += 1
            if abs(got - float(cached)) > 0.05:
                lbl = ws2.cell(r, li).value or ws2.cell(r, aci).value
                critical = r <= crit_max
                if critical:
                    crit += 1
                worst.append((r, lbl, round(float(cached), 2), round(got, 2), "CRIT" if critical else "annex"))
        print(f"== {sheet} col {tgt_col}: checked={checked} critical_mismatch={crit} total_mismatch={len(worst)}")
        for w in worst:
            print("   ", w)

    validate("Bilan Détaillé", "I", "C", "B", 174)
    validate("Resultats internes", "E", "D", "C", 556)
    validate("Resultats internes", "Q", "D", "C", 556)
