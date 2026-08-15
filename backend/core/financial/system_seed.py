"""P3.2 — System reference-data seed (concepts + i18n + jurisdictions + templates).

Deterministic, idempotent, versioned, SYSTEM-managed. Running the seed twice
never duplicates concepts, labels, jurisdiction profiles or template versions,
and NEVER silently overwrites the semantic meaning of a published concept or an
already-published template. Writes only system-scoped reference data; creates
NO client data (no account_mappings, no custom templates, no report_runs) and
never touches Phase 2 / legacy collections.

Concept labels use the dedicated P3.1 i18n table. Template-line labels are
embedded on the line doc (system templates) for compactness; internal codes stay
language-neutral. No calculation engine — formulas are the P3.1 skeleton only,
but the seed validates that every formula reference resolves to a line in the
same template and that every concept_ref is a valid, non-aggregate concept.
"""
from datetime import datetime, timezone
import re

from fastapi import HTTPException

from ..permissions import require_platform_manager

SEED_VERSION = "2026.06.0"
_now = lambda: datetime.now(timezone.utc).isoformat()
_ID_RE = re.compile(r"[A-Z_][A-Z0-9_]*")

# ---- Canonical concept taxonomy -------------------------------------------
# (code, parent_code, concept_type, statement_type, natural_balance,
#  is_aggregate, cash_flow_category, {en, fr, de, it})
BS = "balance_sheet"
IS = "income_statement"
CONCEPTS = [
    # ASSETS
    ("ASSETS", None, "asset", BS, "debit", True, "none",
     {"en": "Assets", "fr": "Actifs", "de": "Aktiven", "it": "Attivi"}),
    ("CURRENT_ASSETS", "ASSETS", "asset", BS, "debit", True, "none",
     {"en": "Current assets", "fr": "Actifs courants", "de": "Umlaufvermögen", "it": "Attivo circolante"}),
    ("CASH_AND_CASH_EQUIVALENTS", "CURRENT_ASSETS", "asset", BS, "debit", False, "none",
     {"en": "Cash and cash equivalents", "fr": "Trésorerie et équivalents", "de": "Flüssige Mittel", "it": "Liquidità"}),
    ("ACCOUNTS_RECEIVABLE", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Accounts receivable", "fr": "Comptes clients", "de": "Forderungen aus L+L", "it": "Crediti da forniture"}),
    ("RELATED_PARTY_RECEIVABLES", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Related-party receivables", "fr": "Créances parties liées", "de": "Forderungen nahestehende", "it": "Crediti parti correlate"}),
    ("OTHER_RECEIVABLES", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Other receivables", "fr": "Autres créances", "de": "Übrige Forderungen", "it": "Altri crediti"}),
    ("INVENTORY", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Inventory", "fr": "Stocks", "de": "Vorräte", "it": "Scorte"}),
    ("PREPAID_EXPENSES", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Prepaid expenses", "fr": "Charges payées d'avance", "de": "Aktive Rechnungsabgrenzung", "it": "Ratei e risconti attivi"}),
    ("OTHER_CURRENT_ASSETS", "CURRENT_ASSETS", "asset", BS, "debit", False, "operating",
     {"en": "Other current assets", "fr": "Autres actifs courants", "de": "Übriges Umlaufvermögen", "it": "Altri attivi circolanti"}),
    ("NON_CURRENT_ASSETS", "ASSETS", "asset", BS, "debit", True, "none",
     {"en": "Non-current assets", "fr": "Actifs non courants", "de": "Anlagevermögen", "it": "Attivo fisso"}),
    ("PROPERTY_PLANT_EQUIPMENT", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "investing",
     {"en": "Property, plant & equipment", "fr": "Immobilisations corporelles", "de": "Sachanlagen", "it": "Immobilizzazioni materiali"}),
    ("ACCUMULATED_DEPRECIATION", "NON_CURRENT_ASSETS", "contra_asset", BS, "credit", False, "investing",
     {"en": "Accumulated depreciation", "fr": "Amortissements cumulés", "de": "Kumulierte Abschreibungen", "it": "Ammortamenti cumulati"}),
    ("RIGHT_OF_USE_ASSETS", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "investing",
     {"en": "Right-of-use assets", "fr": "Actifs au titre du droit d'utilisation", "de": "Nutzungsrechte", "it": "Attività per diritto d'uso"}),
    ("INTANGIBLE_ASSETS", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "investing",
     {"en": "Intangible assets", "fr": "Immobilisations incorporelles", "de": "Immaterielle Anlagen", "it": "Immobilizzazioni immateriali"}),
    ("ACCUMULATED_AMORTIZATION", "NON_CURRENT_ASSETS", "contra_asset", BS, "credit", False, "investing",
     {"en": "Accumulated amortization", "fr": "Amortissements cumulés (incorporels)", "de": "Kumulierte Amortisationen", "it": "Ammortamenti cumulati (immateriali)"}),
    ("INVESTMENTS", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "investing",
     {"en": "Investments", "fr": "Placements", "de": "Finanzanlagen", "it": "Partecipazioni"}),
    ("DEFERRED_TAX_ASSET", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "none",
     {"en": "Deferred tax asset", "fr": "Actif d'impôt différé", "de": "Latente Steueransprüche", "it": "Attività fiscali differite"}),
    ("OTHER_NON_CURRENT_ASSETS", "NON_CURRENT_ASSETS", "asset", BS, "debit", False, "investing",
     {"en": "Other non-current assets", "fr": "Autres actifs non courants", "de": "Übriges Anlagevermögen", "it": "Altri attivi fissi"}),
    # LIABILITIES
    ("LIABILITIES", None, "liability", BS, "credit", True, "none",
     {"en": "Liabilities", "fr": "Passifs", "de": "Fremdkapital", "it": "Passivi"}),
    ("CURRENT_LIABILITIES", "LIABILITIES", "liability", BS, "credit", True, "none",
     {"en": "Current liabilities", "fr": "Passifs courants", "de": "Kurzfristiges Fremdkapital", "it": "Passivo corrente"}),
    ("ACCOUNTS_PAYABLE", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Accounts payable", "fr": "Comptes fournisseurs", "de": "Verbindlichkeiten aus L+L", "it": "Debiti da forniture"}),
    ("RELATED_PARTY_PAYABLES", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Related-party payables", "fr": "Dettes parties liées", "de": "Verbindlichkeiten nahestehende", "it": "Debiti parti correlate"}),
    ("ACCRUED_LIABILITIES", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Accrued liabilities", "fr": "Charges à payer", "de": "Passive Rechnungsabgrenzung", "it": "Ratei e risconti passivi"}),
    ("TAX_PAYABLE", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Tax payable", "fr": "Impôts à payer", "de": "Steuerverbindlichkeiten", "it": "Debiti fiscali"}),
    ("SHORT_TERM_DEBT", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "financing",
     {"en": "Short-term debt", "fr": "Dettes à court terme", "de": "Kurzfristige Finanzverbindlichkeiten", "it": "Debiti finanziari a breve"}),
    ("LEASE_LIABILITIES_CURRENT", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "financing",
     {"en": "Lease liabilities (current)", "fr": "Dettes de location (courant)", "de": "Leasingverbindlichkeiten (kurzfristig)", "it": "Debiti leasing (correnti)"}),
    ("DEFERRED_REVENUE", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Deferred revenue", "fr": "Produits différés", "de": "Erhaltene Anzahlungen", "it": "Ricavi differiti"}),
    ("OTHER_CURRENT_LIABILITIES", "CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Other current liabilities", "fr": "Autres passifs courants", "de": "Übriges kurzfristiges Fremdkapital", "it": "Altri passivi correnti"}),
    ("NON_CURRENT_LIABILITIES", "LIABILITIES", "liability", BS, "credit", True, "none",
     {"en": "Non-current liabilities", "fr": "Passifs non courants", "de": "Langfristiges Fremdkapital", "it": "Passivo a lungo termine"}),
    ("LONG_TERM_DEBT", "NON_CURRENT_LIABILITIES", "liability", BS, "credit", False, "financing",
     {"en": "Long-term debt", "fr": "Dettes à long terme", "de": "Langfristige Finanzverbindlichkeiten", "it": "Debiti finanziari a lungo"}),
    ("LEASE_LIABILITIES_NON_CURRENT", "NON_CURRENT_LIABILITIES", "liability", BS, "credit", False, "financing",
     {"en": "Lease liabilities (non-current)", "fr": "Dettes de location (non courant)", "de": "Leasingverbindlichkeiten (langfristig)", "it": "Debiti leasing (non correnti)"}),
    ("PROVISIONS", "NON_CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Provisions", "fr": "Provisions", "de": "Rückstellungen", "it": "Accantonamenti"}),
    ("DEFERRED_TAX_LIABILITY", "NON_CURRENT_LIABILITIES", "liability", BS, "credit", False, "none",
     {"en": "Deferred tax liability", "fr": "Passif d'impôt différé", "de": "Latente Steuerschulden", "it": "Passività fiscali differite"}),
    ("OTHER_NON_CURRENT_LIABILITIES", "NON_CURRENT_LIABILITIES", "liability", BS, "credit", False, "operating",
     {"en": "Other non-current liabilities", "fr": "Autres passifs non courants", "de": "Übriges langfristiges Fremdkapital", "it": "Altri passivi a lungo"}),
    # EQUITY
    ("EQUITY", None, "equity", BS, "credit", True, "none",
     {"en": "Equity", "fr": "Capitaux propres", "de": "Eigenkapital", "it": "Capitale proprio"}),
    ("SHARE_CAPITAL", "EQUITY", "equity", BS, "credit", False, "financing",
     {"en": "Share capital", "fr": "Capital-actions", "de": "Aktienkapital", "it": "Capitale azionario"}),
    ("LEGAL_RESERVES", "EQUITY", "equity", BS, "credit", False, "none",
     {"en": "Legal reserves", "fr": "Réserves légales", "de": "Gesetzliche Reserven", "it": "Riserve legali"}),
    ("OTHER_RESERVES", "EQUITY", "equity", BS, "credit", False, "none",
     {"en": "Other reserves", "fr": "Autres réserves", "de": "Übrige Reserven", "it": "Altre riserve"}),
    ("RETAINED_EARNINGS", "EQUITY", "equity", BS, "credit", False, "none",
     {"en": "Retained earnings", "fr": "Résultats reportés", "de": "Gewinnvortrag", "it": "Utili riportati"}),
    ("CURRENT_YEAR_RESULT", "EQUITY", "equity", BS, "credit", False, "none",
     {"en": "Current-year result", "fr": "Résultat de l'exercice", "de": "Jahresergebnis", "it": "Risultato d'esercizio"}),
    ("OTHER_EQUITY", "EQUITY", "equity", BS, "credit", False, "none",
     {"en": "Other equity", "fr": "Autres capitaux propres", "de": "Übriges Eigenkapital", "it": "Altro capitale proprio"}),
    # INCOME
    ("INCOME", None, "income", IS, "credit", True, "none",
     {"en": "Income", "fr": "Produits", "de": "Ertrag", "it": "Ricavi"}),
    ("OPERATING_REVENUE", "INCOME", "income", IS, "credit", False, "operating",
     {"en": "Operating revenue", "fr": "Chiffre d'affaires", "de": "Betrieblicher Ertrag", "it": "Ricavi operativi"}),
    ("OTHER_OPERATING_INCOME", "INCOME", "income", IS, "credit", False, "operating",
     {"en": "Other operating income", "fr": "Autres produits d'exploitation", "de": "Übriger betrieblicher Ertrag", "it": "Altri ricavi operativi"}),
    ("FINANCIAL_INCOME", "INCOME", "income", IS, "credit", False, "none",
     {"en": "Financial income", "fr": "Produits financiers", "de": "Finanzertrag", "it": "Proventi finanziari"}),
    ("FOREIGN_EXCHANGE_GAIN", "INCOME", "income", IS, "credit", False, "none",
     {"en": "Foreign exchange gain", "fr": "Gain de change", "de": "Kursgewinn", "it": "Utile su cambi"}),
    ("OTHER_INCOME", "INCOME", "income", IS, "credit", False, "none",
     {"en": "Other income", "fr": "Autres produits", "de": "Übriger Ertrag", "it": "Altri ricavi"}),
    # EXPENSES
    ("EXPENSES", None, "expense", IS, "debit", True, "none",
     {"en": "Expenses", "fr": "Charges", "de": "Aufwand", "it": "Costi"}),
    ("COST_OF_GOODS_SOLD", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Cost of goods sold", "fr": "Coût des marchandises vendues", "de": "Waren-/Materialaufwand", "it": "Costo del venduto"}),
    ("PERSONNEL_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Personnel expense", "fr": "Charges de personnel", "de": "Personalaufwand", "it": "Costi del personale"}),
    ("OCCUPANCY_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Occupancy expense", "fr": "Charges de locaux", "de": "Raumaufwand", "it": "Costi immobiliari"}),
    ("MARKETING_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Marketing expense", "fr": "Charges de marketing", "de": "Marketingaufwand", "it": "Costi di marketing"}),
    ("DEPRECIATION_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Depreciation", "fr": "Amortissements (corporels)", "de": "Abschreibungen", "it": "Ammortamenti (materiali)"}),
    ("AMORTIZATION_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Amortization", "fr": "Amortissements (incorporels)", "de": "Amortisationen", "it": "Ammortamenti (immateriali)"}),
    ("FINANCIAL_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "none",
     {"en": "Financial expense", "fr": "Charges financières", "de": "Finanzaufwand", "it": "Oneri finanziari"}),
    ("FOREIGN_EXCHANGE_LOSS", "EXPENSES", "expense", IS, "debit", False, "none",
     {"en": "Foreign exchange loss", "fr": "Perte de change", "de": "Kursverlust", "it": "Perdita su cambi"}),
    ("TAX_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Tax expense", "fr": "Charge d'impôt", "de": "Steueraufwand", "it": "Imposte"}),
    ("NON_RECURRING_ITEMS", "EXPENSES", "expense", IS, "debit", False, "none",
     {"en": "Non-recurring items", "fr": "Éléments non récurrents", "de": "Ausserordentliche Posten", "it": "Elementi non ricorrenti"}),
    ("OTHER_OPERATING_EXPENSE", "EXPENSES", "expense", IS, "debit", False, "operating",
     {"en": "Other operating expense", "fr": "Autres charges d'exploitation", "de": "Übriger betrieblicher Aufwand", "it": "Altri costi operativi"}),
]

_CODE_TO_SPEC = {c[0]: c for c in CONCEPTS}


def _fc_id(code: str) -> str:
    return f"fc_{code.lower()}"


def _level(code: str) -> int:
    lvl, parent = 0, _CODE_TO_SPEC[code][1]
    while parent:
        lvl += 1
        parent = _CODE_TO_SPEC[parent][1]
    return lvl


# ---- Template structures (shared CA/CH; terminology via line labels) ------
# line dict: code, type, concepts[], formula, display_sign, parent, labels{}
def _L(code, ltype, concepts=None, formula=None, sign="natural", parent=None, labels=None):
    return {"line_code": code, "line_type": ltype, "concepts": concepts or [],
            "formula": formula, "display_sign": sign, "parent": parent, "labels": labels or {}}


def _lbls(en, fr, de, it):
    return {"en": en, "fr": fr, "de": de, "it": it}


BS_SPEC = [
    _L("SEC_ASSETS", "section", labels=_lbls("ASSETS", "ACTIFS", "AKTIVEN", "ATTIVI")),
    _L("HDR_CURRENT_ASSETS", "section", parent="SEC_ASSETS", labels=_lbls("Current assets", "Actifs courants", "Umlaufvermögen", "Attivo circolante")),
    _L("BS_CASH", "concept", ["CASH_AND_CASH_EQUIVALENTS"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Cash", "Trésorerie", "Flüssige Mittel", "Liquidità")),
    _L("BS_AR", "concept", ["ACCOUNTS_RECEIVABLE"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Accounts receivable", "Comptes clients", "Forderungen aus L+L", "Crediti da forniture")),
    _L("BS_RPR", "concept", ["RELATED_PARTY_RECEIVABLES"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Related-party receivables", "Créances parties liées", "Forderungen nahestehende", "Crediti parti correlate")),
    _L("BS_INV", "concept", ["INVENTORY"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Inventory", "Stocks", "Vorräte", "Scorte")),
    _L("BS_PREPAID", "concept", ["PREPAID_EXPENSES"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Prepaid expenses", "Charges payées d'avance", "Aktive Rechnungsabgrenzung", "Ratei attivi")),
    _L("BS_OTHER_CA", "concept", ["OTHER_RECEIVABLES", "OTHER_CURRENT_ASSETS"], parent="HDR_CURRENT_ASSETS", labels=_lbls("Other current assets", "Autres actifs courants", "Übriges Umlaufvermögen", "Altri attivi circolanti")),
    _L("ST_CURRENT_ASSETS", "subtotal", formula="BS_CASH+BS_AR+BS_RPR+BS_INV+BS_PREPAID+BS_OTHER_CA", parent="SEC_ASSETS", labels=_lbls("Total current assets", "Total actifs courants", "Total Umlaufvermögen", "Totale attivo circolante")),
    _L("HDR_NON_CURRENT_ASSETS", "section", parent="SEC_ASSETS", labels=_lbls("Non-current assets", "Actifs non courants", "Anlagevermögen", "Attivo fisso")),
    _L("BS_PPE", "concept", ["PROPERTY_PLANT_EQUIPMENT"], parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Property, plant & equipment", "Immobilisations corporelles", "Sachanlagen", "Immobilizzazioni materiali")),
    _L("BS_ACCDEP", "concept", ["ACCUMULATED_DEPRECIATION"], sign="negative", parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Accumulated depreciation", "Amortissements cumulés", "Kumulierte Abschreibungen", "Ammortamenti cumulati")),
    _L("BS_ROU", "concept", ["RIGHT_OF_USE_ASSETS"], parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Right-of-use assets", "Actifs droit d'utilisation", "Nutzungsrechte", "Attività diritto d'uso")),
    _L("BS_INTAN", "concept", ["INTANGIBLE_ASSETS"], parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Intangible assets", "Immobilisations incorporelles", "Immaterielle Anlagen", "Immobilizzazioni immateriali")),
    _L("BS_ACCAMORT", "concept", ["ACCUMULATED_AMORTIZATION"], sign="negative", parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Accumulated amortization", "Amortissements cumulés (incorp.)", "Kumulierte Amortisationen", "Ammortamenti cumulati (immat.)")),
    _L("BS_INVEST", "concept", ["INVESTMENTS"], parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Investments", "Placements", "Finanzanlagen", "Partecipazioni")),
    _L("BS_OTHER_NCA", "concept", ["DEFERRED_TAX_ASSET", "OTHER_NON_CURRENT_ASSETS"], parent="HDR_NON_CURRENT_ASSETS", labels=_lbls("Other non-current assets", "Autres actifs non courants", "Übriges Anlagevermögen", "Altri attivi fissi")),
    _L("ST_NON_CURRENT_ASSETS", "subtotal", formula="BS_PPE+BS_ACCDEP+BS_ROU+BS_INTAN+BS_ACCAMORT+BS_INVEST+BS_OTHER_NCA", parent="SEC_ASSETS", labels=_lbls("Total non-current assets", "Total actifs non courants", "Total Anlagevermögen", "Totale attivo fisso")),
    _L("ST_TOTAL_ASSETS", "subtotal", formula="ST_CURRENT_ASSETS+ST_NON_CURRENT_ASSETS", labels=_lbls("TOTAL ASSETS", "TOTAL ACTIFS", "TOTAL AKTIVEN", "TOTALE ATTIVI")),
    _L("SEC_LIABILITIES", "section", labels=_lbls("LIABILITIES", "PASSIFS", "FREMDKAPITAL", "PASSIVI")),
    _L("HDR_CURRENT_LIAB", "section", parent="SEC_LIABILITIES", labels=_lbls("Current liabilities", "Passifs courants", "Kurzfristiges Fremdkapital", "Passivo corrente")),
    _L("BS_AP", "concept", ["ACCOUNTS_PAYABLE"], parent="HDR_CURRENT_LIAB", labels=_lbls("Accounts payable", "Comptes fournisseurs", "Verbindlichkeiten aus L+L", "Debiti da forniture")),
    _L("BS_RPP", "concept", ["RELATED_PARTY_PAYABLES"], parent="HDR_CURRENT_LIAB", labels=_lbls("Related-party payables", "Dettes parties liées", "Verbindlichkeiten nahestehende", "Debiti parti correlate")),
    _L("BS_ACCRUED", "concept", ["ACCRUED_LIABILITIES"], parent="HDR_CURRENT_LIAB", labels=_lbls("Accrued liabilities", "Charges à payer", "Passive Rechnungsabgrenzung", "Ratei passivi")),
    _L("BS_TAXPAY", "concept", ["TAX_PAYABLE"], parent="HDR_CURRENT_LIAB", labels=_lbls("Tax payable", "Impôts à payer", "Steuerverbindlichkeiten", "Debiti fiscali")),
    _L("BS_STDEBT", "concept", ["SHORT_TERM_DEBT"], parent="HDR_CURRENT_LIAB", labels=_lbls("Short-term debt", "Dettes court terme", "Kurzfristige Finanzverbindl.", "Debiti finanziari a breve")),
    _L("BS_LEASE_C", "concept", ["LEASE_LIABILITIES_CURRENT"], parent="HDR_CURRENT_LIAB", labels=_lbls("Lease liabilities (current)", "Dettes location (courant)", "Leasingverbindl. (kurzfr.)", "Debiti leasing (correnti)")),
    _L("BS_DEFREV", "concept", ["DEFERRED_REVENUE"], parent="HDR_CURRENT_LIAB", labels=_lbls("Deferred revenue", "Produits différés", "Erhaltene Anzahlungen", "Ricavi differiti")),
    _L("BS_OTHER_CL", "concept", ["OTHER_CURRENT_LIABILITIES"], parent="HDR_CURRENT_LIAB", labels=_lbls("Other current liabilities", "Autres passifs courants", "Übriges kurzfr. Fremdkapital", "Altri passivi correnti")),
    _L("ST_CURRENT_LIAB", "subtotal", formula="BS_AP+BS_RPP+BS_ACCRUED+BS_TAXPAY+BS_STDEBT+BS_LEASE_C+BS_DEFREV+BS_OTHER_CL", parent="SEC_LIABILITIES", labels=_lbls("Total current liabilities", "Total passifs courants", "Total kurzfr. Fremdkapital", "Totale passivo corrente")),
    _L("HDR_NON_CURRENT_LIAB", "section", parent="SEC_LIABILITIES", labels=_lbls("Non-current liabilities", "Passifs non courants", "Langfristiges Fremdkapital", "Passivo a lungo termine")),
    _L("BS_LTDEBT", "concept", ["LONG_TERM_DEBT"], parent="HDR_NON_CURRENT_LIAB", labels=_lbls("Long-term debt", "Dettes long terme", "Langfristige Finanzverbindl.", "Debiti finanziari a lungo")),
    _L("BS_LEASE_NC", "concept", ["LEASE_LIABILITIES_NON_CURRENT"], parent="HDR_NON_CURRENT_LIAB", labels=_lbls("Lease liabilities (non-current)", "Dettes location (non courant)", "Leasingverbindl. (langfr.)", "Debiti leasing (non correnti)")),
    _L("BS_PROV", "concept", ["PROVISIONS"], parent="HDR_NON_CURRENT_LIAB", labels=_lbls("Provisions", "Provisions", "Rückstellungen", "Accantonamenti")),
    _L("BS_DTL", "concept", ["DEFERRED_TAX_LIABILITY"], parent="HDR_NON_CURRENT_LIAB", labels=_lbls("Deferred tax liability", "Passif d'impôt différé", "Latente Steuerschulden", "Passività fiscali differite")),
    _L("BS_OTHER_NCL", "concept", ["OTHER_NON_CURRENT_LIABILITIES"], parent="HDR_NON_CURRENT_LIAB", labels=_lbls("Other non-current liabilities", "Autres passifs non courants", "Übriges langfr. Fremdkapital", "Altri passivi a lungo")),
    _L("ST_NON_CURRENT_LIAB", "subtotal", formula="BS_LTDEBT+BS_LEASE_NC+BS_PROV+BS_DTL+BS_OTHER_NCL", parent="SEC_LIABILITIES", labels=_lbls("Total non-current liabilities", "Total passifs non courants", "Total langfr. Fremdkapital", "Totale passivo a lungo")),
    _L("ST_TOTAL_LIAB", "subtotal", formula="ST_CURRENT_LIAB+ST_NON_CURRENT_LIAB", labels=_lbls("Total liabilities", "Total passifs", "Total Fremdkapital", "Totale passivi")),
    _L("SEC_EQUITY", "section", labels=_lbls("EQUITY", "CAPITAUX PROPRES", "EIGENKAPITAL", "CAPITALE PROPRIO")),
    _L("BS_SHARECAP", "concept", ["SHARE_CAPITAL"], parent="SEC_EQUITY", labels=_lbls("Share capital", "Capital-actions", "Aktienkapital", "Capitale azionario")),
    _L("BS_LEGALRES", "concept", ["LEGAL_RESERVES"], parent="SEC_EQUITY", labels=_lbls("Legal reserves", "Réserves légales", "Gesetzliche Reserven", "Riserve legali")),
    _L("BS_OTHERRES", "concept", ["OTHER_RESERVES"], parent="SEC_EQUITY", labels=_lbls("Other reserves", "Autres réserves", "Übrige Reserven", "Altre riserve")),
    _L("BS_RE", "concept", ["RETAINED_EARNINGS"], parent="SEC_EQUITY", labels=_lbls("Retained earnings", "Résultats reportés", "Gewinnvortrag", "Utili riportati")),
    _L("BS_CYR", "concept", ["CURRENT_YEAR_RESULT"], parent="SEC_EQUITY", labels=_lbls("Current-year result", "Résultat de l'exercice", "Jahresergebnis", "Risultato d'esercizio")),
    _L("BS_OTHEREQ", "concept", ["OTHER_EQUITY"], parent="SEC_EQUITY", labels=_lbls("Other equity", "Autres capitaux propres", "Übriges Eigenkapital", "Altro capitale proprio")),
    _L("ST_TOTAL_EQUITY", "subtotal", formula="BS_SHARECAP+BS_LEGALRES+BS_OTHERRES+BS_RE+BS_CYR+BS_OTHEREQ", parent="SEC_EQUITY", labels=_lbls("Total equity", "Total capitaux propres", "Total Eigenkapital", "Totale capitale proprio")),
    _L("ST_TOTAL_LIAB_EQUITY", "subtotal", formula="ST_TOTAL_LIAB+ST_TOTAL_EQUITY", labels=_lbls("TOTAL LIABILITIES & EQUITY", "TOTAL PASSIFS & CAPITAUX PROPRES", "TOTAL PASSIVEN", "TOTALE PASSIVI E CAPITALE")),
]

PL_SPEC = [
    _L("PL_OPREV", "concept", ["OPERATING_REVENUE"], labels=_lbls("Operating revenue", "Chiffre d'affaires", "Betrieblicher Ertrag", "Ricavi operativi")),
    _L("PL_OTHEROPINC", "concept", ["OTHER_OPERATING_INCOME"], labels=_lbls("Other operating income", "Autres produits d'exploitation", "Übriger betrieblicher Ertrag", "Altri ricavi operativi")),
    _L("ST_REVENUE", "subtotal", formula="PL_OPREV+PL_OTHEROPINC", labels=_lbls("Net revenue", "Produits nets", "Nettoumsatz", "Ricavi netti")),
    _L("PL_COGS", "concept", ["COST_OF_GOODS_SOLD"], sign="negative", labels=_lbls("Cost of goods sold", "Coût des marchandises vendues", "Waren-/Materialaufwand", "Costo del venduto")),
    _L("ST_GROSS_PROFIT", "formula", formula="ST_REVENUE-PL_COGS", labels=_lbls("Gross profit", "Marge brute", "Bruttogewinn", "Utile lordo")),
    _L("PL_PERSONNEL", "concept", ["PERSONNEL_EXPENSE"], sign="negative", labels=_lbls("Personnel expense", "Charges de personnel", "Personalaufwand", "Costi del personale")),
    _L("PL_OCCUPANCY", "concept", ["OCCUPANCY_EXPENSE"], sign="negative", labels=_lbls("Occupancy expense", "Charges de locaux", "Raumaufwand", "Costi immobiliari")),
    _L("PL_MARKETING", "concept", ["MARKETING_EXPENSE"], sign="negative", labels=_lbls("Marketing expense", "Charges de marketing", "Marketingaufwand", "Costi di marketing")),
    _L("PL_OTHEROPEX", "concept", ["OTHER_OPERATING_EXPENSE"], sign="negative", labels=_lbls("Other operating expense", "Autres charges d'exploitation", "Übriger betrieblicher Aufwand", "Altri costi operativi")),
    _L("ST_EBITDA", "formula", formula="ST_GROSS_PROFIT-PL_PERSONNEL-PL_OCCUPANCY-PL_MARKETING-PL_OTHEROPEX", labels=_lbls("EBITDA", "EBITDA", "EBITDA", "EBITDA")),
    _L("PL_DEP", "concept", ["DEPRECIATION_EXPENSE"], sign="negative", labels=_lbls("Depreciation", "Amortissements (corporels)", "Abschreibungen", "Ammortamenti (materiali)")),
    _L("PL_AMORT", "concept", ["AMORTIZATION_EXPENSE"], sign="negative", labels=_lbls("Amortization", "Amortissements (incorporels)", "Amortisationen", "Ammortamenti (immateriali)")),
    _L("ST_EBIT", "formula", formula="ST_EBITDA-PL_DEP-PL_AMORT", labels=_lbls("EBIT", "EBIT", "EBIT", "EBIT")),
    _L("PL_FININC", "concept", ["FINANCIAL_INCOME"], labels=_lbls("Financial income", "Produits financiers", "Finanzertrag", "Proventi finanziari")),
    _L("PL_FINEXP", "concept", ["FINANCIAL_EXPENSE"], sign="negative", labels=_lbls("Financial expense", "Charges financières", "Finanzaufwand", "Oneri finanziari")),
    _L("PL_FXGAIN", "concept", ["FOREIGN_EXCHANGE_GAIN"], labels=_lbls("FX gain", "Gain de change", "Kursgewinn", "Utile su cambi")),
    _L("PL_FXLOSS", "concept", ["FOREIGN_EXCHANGE_LOSS"], sign="negative", labels=_lbls("FX loss", "Perte de change", "Kursverlust", "Perdita su cambi")),
    _L("PL_NONREC", "concept", ["NON_RECURRING_ITEMS"], sign="negative", labels=_lbls("Non-recurring items", "Éléments non récurrents", "Ausserordentliche Posten", "Elementi non ricorrenti")),
    _L("ST_PBT", "formula", formula="ST_EBIT+PL_FININC-PL_FINEXP+PL_FXGAIN-PL_FXLOSS-PL_NONREC", labels=_lbls("Profit before tax", "Résultat avant impôts", "Ergebnis vor Steuern", "Utile ante imposte")),
    _L("PL_TAX", "concept", ["TAX_EXPENSE"], sign="negative", labels=_lbls("Tax expense", "Charge d'impôt", "Steueraufwand", "Imposte")),
    _L("ST_NET_INCOME", "formula", formula="ST_PBT-PL_TAX", labels=_lbls("Net income", "Résultat net", "Jahresgewinn", "Utile netto")),
]

TEMPLATES = [
    {"template_code": "CA_PRIVATE_ENTERPRISE_STANDARD_BS", "statement_type": BS, "jurisdiction": "CA",
     "name": "Meelora Canada Private Enterprise Standard — Balance Sheet", "spec": BS_SPEC, "locales": ["en", "fr"]},
    {"template_code": "CA_PRIVATE_ENTERPRISE_STANDARD_PL", "statement_type": IS, "jurisdiction": "CA",
     "name": "Meelora Canada Private Enterprise Standard — Income Statement", "spec": PL_SPEC, "locales": ["en", "fr"]},
    {"template_code": "CH_CO_SME_STANDARD_BS", "statement_type": BS, "jurisdiction": "CH",
     "name": "Meelora Swiss CO SME Standard — Balance Sheet", "spec": BS_SPEC, "locales": ["en", "fr", "de", "it"]},
    {"template_code": "CH_CO_SME_STANDARD_PL", "statement_type": IS, "jurisdiction": "CH",
     "name": "Meelora Swiss CO SME Standard — Income Statement", "spec": PL_SPEC, "locales": ["en", "fr", "de", "it"]},
]

JURISDICTIONS = [
    {"jurisdiction_code": "CA", "supported_frameworks": ["CA_PRIVATE_ENTERPRISE"],
     "default_locales": ["en", "fr"],
     "default_template_codes": {"balance_sheet": "CA_PRIVATE_ENTERPRISE_STANDARD_BS",
                                "income_statement": "CA_PRIVATE_ENTERPRISE_STANDARD_PL"},
     "display_conventions": {"thousands_separator": " ", "decimal_separator": ".", "currency_display": "CAD"},
     "framework_label": "Meelora Canada Private Enterprise Standard — aligned with Canadian private-enterprise reporting conventions (not the accounting standard itself)"},
    {"jurisdiction_code": "CH", "supported_frameworks": ["CH_CO_SME"],
     "default_locales": ["fr", "de", "it", "en"],
     "default_template_codes": {"balance_sheet": "CH_CO_SME_STANDARD_BS",
                                "income_statement": "CH_CO_SME_STANDARD_PL"},
     "display_conventions": {"thousands_separator": "'", "decimal_separator": ".", "currency_display": "CHF"},
     "framework_label": "Meelora Swiss CO SME Standard — aligned with Swiss Code of Obligations presentation (not an exhaustive reproduction of Swiss law)"},
]


# ---- Seed engine (idempotent) ---------------------------------------------
def _empty_report():
    return {"created": [], "existing": [], "updated": [], "skipped": [], "errors": []}


def _validate_template_spec(spec):
    """Structural integrity: unique line codes, valid parents, formula refs and
    concept refs resolvable. No semantic_bypass, no account refs (system rule)."""
    codes = [l["line_code"] for l in spec]
    if len(codes) != len(set(codes)):
        raise ValueError("Codes de ligne dupliqués dans le template")
    code_set = set(codes)
    for l in spec:
        if l["parent"] and l["parent"] not in code_set:
            raise ValueError(f"parent inconnu: {l['parent']}")
        if l["line_type"] in ("subtotal", "formula"):
            if not l["formula"]:
                raise ValueError(f"formule manquante: {l['line_code']}")
            for tok in _ID_RE.findall(l["formula"]):
                if tok not in code_set:
                    raise ValueError(f"référence de formule invalide {tok} dans {l['line_code']}")
        if l["line_type"] == "concept":
            if not l["concepts"]:
                raise ValueError(f"concept_refs manquant: {l['line_code']}")
            for cc in l["concepts"]:
                spec_c = _CODE_TO_SPEC.get(cc)
                if not spec_c:
                    raise ValueError(f"concept inconnu: {cc}")
                if spec_c[5]:  # is_aggregate
                    raise ValueError(f"concept agrégat non mappable dans ligne: {cc}")


async def _seed_concepts(db, report):
    now = _now()
    for (code, parent, ctype, stype, nb, is_agg, cfc, _labels) in CONCEPTS:
        existing = await db.financial_concepts.find_one({"concept_code": code})
        semantic = {"concept_type": ctype, "statement_type": stype, "natural_balance": nb,
                    "is_aggregate": is_agg, "parent_concept_id": _fc_id(parent) if parent else None,
                    "cash_flow_category": cfc}
        if existing:
            drift = [k for k, v in semantic.items() if existing.get(k) != v]
            if drift:
                report["errors"].append({"concept": code, "reason": "semantic drift blocked", "fields": drift})
            else:
                report["existing"].append(code)
            continue
        doc = {"_id": _fc_id(code), "concept_code": code, **semantic, "level": _level(code),
               "sort_order": 0, "tags": [], "scope": "system", "version": 1, "status": "active",
               "replaced_by_concept_id": None, "introduced_version": SEED_VERSION,
               "created_at": now, "updated_at": now}
        await db.financial_concepts.insert_one(doc)
        report["created"].append(code)


async def _seed_i18n(db, entity_type, entity_id, labels, report):
    now = _now()
    for locale, label in labels.items():
        key = {"entity_type": entity_type, "entity_id": entity_id, "locale": locale, "scope": "system"}
        existing = await db.financial_i18n_labels.find_one(key)
        if existing:
            if existing.get("label") != label:
                await db.financial_i18n_labels.update_one({"_id": existing["_id"]},
                                                          {"$set": {"label": label, "updated_at": now}})
                report["updated"].append(f"i18n:{entity_type}:{entity_id}:{locale}")
            else:
                report["skipped"].append(f"i18n:{entity_type}:{entity_id}:{locale}")
            continue
        await db.financial_i18n_labels.insert_one(
            {"_id": f"i18n_{entity_type}_{entity_id}_{locale}", **key, "label": label,
             "created_at": now, "updated_at": now})
        report["created"].append(f"i18n:{entity_type}:{entity_id}:{locale}")


async def _seed_jurisdiction(db, spec, report):
    now = _now()
    code = spec["jurisdiction_code"]
    existing = await db.jurisdiction_profiles.find_one({"jurisdiction_code": code})
    payload = {"supported_frameworks": spec["supported_frameworks"], "default_locales": spec["default_locales"],
               "default_template_codes": spec["default_template_codes"],
               "display_conventions": spec["display_conventions"], "framework_label": spec["framework_label"]}
    if existing:
        drift = any(existing.get(k) != v for k, v in payload.items())
        if drift:
            await db.jurisdiction_profiles.update_one({"_id": existing["_id"]},
                                                      {"$set": {**payload, "updated_at": now}})
            report["updated"].append(f"jurisdiction:{code}")
        else:
            report["skipped"].append(f"jurisdiction:{code}")
        return
    await db.jurisdiction_profiles.insert_one(
        {"_id": f"jp_{code}", "jurisdiction_code": code, "scope": "system", **payload,
         "required_concepts": [], "optional_concepts": [], "version": 1, "status": "active",
         "introduced_version": SEED_VERSION, "created_at": now, "updated_at": now})
    report["created"].append(f"jurisdiction:{code}")


async def _seed_template(db, tpl, report):
    _validate_template_spec(tpl["spec"])
    now = _now()
    code = tpl["template_code"]
    version = 1
    existing = await db.reporting_templates.find_one({"template_code": code, "version": version})
    if existing:
        report["skipped"].append(f"template:{code}:v{version}")  # published → never mutated
        return
    tpl_id = f"rt_{code}_v{version}"
    await db.reporting_templates.insert_one({
        "_id": tpl_id, "template_code": code, "statement_type": tpl["statement_type"],
        "scope": "system", "jurisdiction": tpl["jurisdiction"], "workspace_id": None, "company_id": None,
        "name": tpl["name"], "based_on_template_id": None, "version": version, "status": "published",
        "introduced_version": SEED_VERSION, "created_by": "system", "created_at": now, "published_at": now})
    for i, l in enumerate(tpl["spec"]):
        line_labels = {loc: l["labels"][loc] for loc in tpl["locales"] if loc in l["labels"]}
        await db.reporting_template_lines.insert_one({
            "_id": f"rtl_{code}_{l['line_code']}", "template_id": tpl_id, "line_code": l["line_code"],
            "line_type": l["line_type"],
            "parent_line_id": (f"rtl_{code}_{l['parent']}" if l["parent"] else None),
            "parent_line_code": l["parent"],
            "concept_refs": [_fc_id(c) for c in l["concepts"]],
            "concept_codes": list(l["concepts"]),
            "account_refs": [], "semantic_bypass": False, "semantic_bypass_warning": None,
            "formula": l["formula"], "display_sign": l["display_sign"], "measure": "ytd",
            "labels": line_labels, "sort_order": i, "created_at": now})
    report["created"].append(f"template:{code}:v{version}")


async def run_system_seed(db) -> dict:
    """Idempotent system seed (system/background context). Returns a report."""
    report = _empty_report()
    report["seed_version"] = SEED_VERSION
    await _seed_concepts(db, report)
    for (code, *_rest, labels) in CONCEPTS:
        await _seed_i18n(db, "concept", _fc_id(code), labels, report)
    for jp in JURISDICTIONS:
        await _seed_jurisdiction(db, jp, report)
    for tpl in TEMPLATES:
        await _seed_template(db, tpl, report)
    report["totals"] = {k: len(report[k]) for k in ("created", "existing", "updated", "skipped", "errors")}
    report["counts"] = {
        "concepts": await db.financial_concepts.count_documents({"scope": "system"}),
        "i18n_labels": await db.financial_i18n_labels.count_documents({"scope": "system"}),
        "jurisdiction_profiles": await db.jurisdiction_profiles.count_documents({"scope": "system"}),
        "templates": await db.reporting_templates.count_documents({"scope": "system"}),
    }
    return report


async def run_system_seed_as(db, user) -> dict:
    """Platform-management seed path (write authorization). platform_role only;
    never grants client access."""
    require_platform_manager(user)
    return await run_system_seed(db)
