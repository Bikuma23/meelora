from dotenv import load_dotenv
from pathlib import Path
import os
import json
import calendar

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, UploadFile, File, Form, Header
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Literal
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import logging
import bcrypt
import jwt
import io
import asyncio
import base64
import uuid
import requests
import presentation_reports
import openpyxl
from accounting import ReportEngine
from core.auth_context import load_workspace_for_user, build_auth_user, auth_me_payload
from core.companies import CompanyCreate, CompanyUpdate, list_companies_for_user, get_company_for_user, create_company_for_admin, update_company_for_admin
from core.mandates import MandateCreate, MandateUpdate, list_mandates_for_user, get_mandate_for_user, create_mandate_for_admin, update_mandate_for_admin
from core.logs import write_log, list_logs_for_admin
from core.access_management import UserCompanyAccessUpdate, list_user_company_access, replace_user_company_access
from core.permissions import require_tenant_context, require_company_access, require_workspace_admin, require_company_local_admin
from core.memberships import (
    WorkspaceMemberCreate, WorkspaceMemberUpdate, CompanyMemberCreate, CompanyMemberUpdate,
    list_workspace_members, upsert_workspace_membership, update_workspace_membership,
    list_company_members, create_company_membership, update_company_membership,
    validate_combo, ensure_indexes as _ensure_membership_indexes,
)
from core.company_imports import preview_company_import, commit_company_import
from core.financial.years import (
    FinancialYearCreate, FinancialYearUpdate,
    list_financial_years, get_financial_year, create_financial_year, update_financial_year,
    ensure_indexes as _ensure_financial_year_indexes,
)
from core.financial.periods import (
    FinancialPeriodCreate, FinancialPeriodUpdate,
    list_financial_periods, get_financial_period, create_financial_period,
    update_financial_period, generate_monthly_periods,
    ensure_indexes as _ensure_financial_period_indexes,
)
from core.financial.accounts import (
    AccountCreate, AccountUpdate,
    list_accounts, get_account, create_account, update_account,
    ensure_indexes as _ensure_account_indexes,
)
from core.financial.data_imports import (
    CommitRequest,
    preview_accounts_import, commit_accounts_import, list_imports, get_import,
    ensure_indexes as _ensure_data_import_indexes,
)
from core.financial.trial_balance import (
    TBCommitRequest,
    preview_trial_balance_import, commit_trial_balance_import, list_trial_balance,
    ensure_indexes as _ensure_trial_balance_indexes,
)
from core.financial.journal import (
    JournalCommitRequest,
    preview_journal_import, commit_journal_import, list_journal_entries, get_journal_entry,
    aggregate_journal, ensure_indexes as _ensure_journal_indexes,
)
from core.financial.compatibility import (
    FinancialSourceUpdate,
    get_financial_source, set_financial_source, financial_source_status,
    compat_accounts, compat_trial_balance, compat_journal,
    ensure_indexes as _ensure_financial_config_indexes,
)
from core.financial.reconciliation import (
    reconcile_accounts, reconcile_trial_balance, reconcile_journal_vs_tb, reconciliation_status,
    _LEGACY_COL_KEYS,
)
from core.financial.phase2_signoff import (
    create_signoff, list_signoffs, get_signoff, signoff_status,
    ensure_indexes as _ensure_phase2_signoff_indexes,
)
from core.financial.concepts import (
    ConceptCreate, ConceptUpdate,
    create_concept, update_concept, deprecate_concept, list_concepts, get_concept,
    ensure_indexes as _ensure_concept_indexes,
)
from core.financial.i18n import (
    LabelUpsert, set_label, get_labels,
    ensure_indexes as _ensure_i18n_indexes,
)
from core.financial.mappings import (
    MappingCreate, MappingUpdate, BulkConfirm,
    create_mapping, confirm_mapping, reject_mapping, update_mapping, bulk_confirm,
    list_mappings, get_mapping, mapping_coverage, mapping_readiness,
    ensure_indexes as _ensure_mapping_indexes,
)
from core.financial.mapping_import import (
    ImportCommit, parse_rows, import_preview, import_commit,
)
from core.financial.reporting_templates import (
    TemplateCreate, TemplateLineCreate, JurisdictionProfileCreate,
    create_template, add_template_line, publish_template, archive_template, new_template_version,
    list_system_templates, list_company_templates, get_template,
    create_jurisdiction_profile, list_jurisdiction_profiles, get_jurisdiction_profile,
    ensure_indexes as _ensure_reporting_template_indexes,
)
from core.financial.system_seed import run_system_seed_as
from core.financial.reporting_engine import (
    ReportRequest, preview_report, generate_report, list_reports, get_report,
    ensure_indexes as _ensure_report_runs_indexes,
)
from core.financial.custom_templates import (
    CustomTemplateCreate, DeriveRequest, TemplateLineUpsert, ReorderRequest,
    DefaultAssignment, UploadCommit,
    create_custom_template, derive_template, new_custom_version,
    add_line as ct_add_line, update_line as ct_update_line, remove_line as ct_remove_line,
    reorder_lines as ct_reorder_lines, validate_template as ct_validate_template,
    publish_template as ct_publish_template, archive_template as ct_archive_template,
    list_available_templates, set_default_template, get_default_templates,
    upload_preview as ct_upload_preview, upload_commit as ct_upload_commit,
    ensure_indexes as _ensure_custom_template_indexes,
)
from core.financial.cash_flow import (
    preview_cash_flow, generate_cash_flow, seed_cash_flow_templates,
)
from core.financial.comparatives import (
    preview_statement_comparative, generate_statement_comparative,
    preview_cash_flow_comparative, generate_cash_flow_comparative,
    preview_management_report, generate_management_report,
)


class ComparativeRequest(BaseModel):
    statement_type: str
    financial_period_id: str
    comparison_mode: str = "prior_period"
    template_id: Optional[str] = None
    template_code: Optional[str] = None
    locale: str = "fr"
    measure: Optional[str] = None
    normalized_import_id: Optional[str] = None


class CashFlowComparativeRequest(BaseModel):
    financial_period_id: str
    comparison_mode: str = "prior_year"
    template_id: Optional[str] = None
    template_code: Optional[str] = None
    locale: str = "fr"


class ManagementReportRequest(BaseModel):
    financial_period_id: str
    comparison_mode: str = "prior_period"
    sections: Optional[list] = None
    locale: str = "fr"


class CashFlowRequest(BaseModel):
    financial_period_id: str
    template_id: Optional[str] = None
    template_code: Optional[str] = None
    locale: str = "fr"
    normalized_import_id: Optional[str] = None


mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# --- company_id resolution (pont avant refonte multi-mandat complète) ---
_company_id_cache: dict = {}

async def _company_id(legacy_prefix: str) -> str:
    """Résout legacy_prefix ('acct' ou 'qc9434') -> company_id réel.
    Mis en cache après le premier appel. Si la compagnie n'existe pas
    encore (ex: seed_companies.py pas encore lancé), lève une erreur
    explicite plutôt que d'écrire un document orphelin."""
    if legacy_prefix not in _company_id_cache:
        doc = await db.companies.find_one({"legacy_prefix": legacy_prefix})
        if not doc:
            raise RuntimeError(
                f"Aucune compagnie avec legacy_prefix='{legacy_prefix}' — "
                f"lancer scripts/seed_companies.py --commit d'abord.")
        _company_id_cache[legacy_prefix] = doc["id"]
    return _company_id_cache[legacy_prefix]


def _pdf_logo(width_mm=38):
    """Logo Meelora (sans tagline) pour les en-têtes PDF (reportlab)."""
    try:
        import os as _os
        from reportlab.platypus import Image as _RLImage
        from reportlab.lib.units import mm as _mm
        p = _os.path.join(_os.path.dirname(__file__), "assets", "meelora-logo.png")
        img = _RLImage(p)
        img.drawWidth = width_mm * _mm
        img.drawHeight = width_mm * _mm * img.imageHeight / img.imageWidth
        img.hAlign = "LEFT"
        return img
    except Exception:
        from reportlab.platypus import Spacer as _Spacer
        return _Spacer(1, 0)


def _xlsx_logo(ws):
    """Réserve la 1re ligne et y insère le logo Meelora (en-tête Excel)."""
    try:
        from openpyxl.drawing.image import Image as _XLImage
        ws.append([])  # ligne 1 réservée au logo
        img = _XLImage(os.path.join(os.path.dirname(__file__), "assets", "meelora-logo.png"))
        img.height = 30
        img.width = 112
        ws.add_image(img, "A1")
        ws.row_dimensions[1].height = 26
    except Exception:
        pass

app = FastAPI(title="Budget Salaires Pro")
api = APIRouter(prefix="/api")

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False

def create_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_doc = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        if user_doc.get("status", "active") != "active":
            raise HTTPException(status_code=403, detail="Compte utilisateur inactif")

        workspace_doc = await load_workspace_for_user(db, user_doc)
        if user_doc.get("workspace_id") and not workspace_doc:
            # A migrated user pointing to a missing workspace is an integrity
            # error. Fail closed rather than silently losing tenant isolation.
            raise HTTPException(status_code=403, detail="Workspace utilisateur introuvable")

        return build_auth_user(user_doc, workspace_doc)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")

def _oid(v):
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=404, detail="Introuvable")

async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user

async def log_action(
    user, action, entity, label, details="", changes=None, *,
    company_id=None, mandate_id=None, entity_id=None, event_type=None,
    severity="info", metadata=None,
):
    """Compatibility wrapper during P1.6.

    New immutable events are written to ``logs``. We temporarily dual-write to
    the legacy ``journal`` collection so old deployments/UI remain compatible
    until the migration is committed and the legacy endpoint is retired.
    """
    event = await write_log(
        db, user, action=action, entity=entity, label=label, details=details,
        changes=changes, company_id=company_id, mandate_id=mandate_id,
        entity_id=entity_id, event_type=event_type, severity=severity,
        metadata=metadata,
    )
    await db.journal.insert_one({
        "timestamp": event["timestamp"],
        "workspace_id": event.get("workspace_id"),
        "user_id": event.get("user_id"),
        "user_email": event.get("user_email", "système"),
        "user_name": event.get("user_name", ""),
        "company_id": company_id,
        "mandate_id": mandate_id,
        "entity_id": entity_id,
        "event_type": event.get("event_type"),
        "severity": severity,
        "action": action, "entity": entity, "label": label, "details": details,
        "changes": changes or [],
        "metadata": {**(metadata or {}), "p1_6_log_id": event["_id"]},
    })
    return event

def _fmt_pct(v):
    try:
        return (f"{float(v) * 100:.4g}").replace(".", ",") + " %"
    except (TypeError, ValueError):
        return str(v)

def _fmt_money(v):
    try:
        return f"{float(v):,.0f}".replace(",", " ") + " $"
    except (TypeError, ValueError):
        return str(v)

def _fmt_kind(v, kind):
    if v is None or v == "":
        return "—"
    if kind == "pct":
        return _fmt_pct(v)
    if kind == "money":
        return _fmt_money(v)
    if kind == "bool":
        return "Oui" if v else "Non"
    return str(v)

_HYPO_PARAMS = [
    ("ccq_rate", "Avantages CCQ", "pct"), ("prime_halo_rate", "Prime HALO", "pct"),
    ("reer_rate", "REER", "pct"), ("assurance_annuelle", "Assurance ($/an)", "money"),
    ("alloc_securite_montant", "Alloc. sécurité ($/an)", "money"),
    ("prime_garde_cout_unitaire", "Garde — coût unitaire", "money"),
    ("prime_garde_nb_annuel", "Garde — nb/an", "num"),
    ("augmentation_ccq", "Augmentation CCQ", "pct"), ("augmentation_autres", "Augmentation standard", "pct"),
    ("csst_max_assurable", "CSST max. assurable", "money"),
]

def _diff_hypotheses(old, new):
    ch = []
    oldc = {c["code"]: c for c in (old.get("charges") or [])}
    for c in (new.get("charges") or []):
        o = oldc.get(c["code"]) or {}
        if abs(float(c.get("rate", 0) or 0) - float(o.get("rate", 0) or 0)) > 1e-9:
            ch.append({"label": f"{c['code']} · Taux", "old": _fmt_pct(o.get("rate", 0)), "new": _fmt_pct(c.get("rate", 0))})
        if abs(float(c.get("ceiling", 0) or 0) - float(o.get("ceiling", 0) or 0)) > 0.5:
            ch.append({"label": f"{c['code']} · Max. assurable", "old": _fmt_money(o.get("ceiling", 0)), "new": _fmt_money(c.get("ceiling", 0))})
        if abs(float(c.get("exemption", 0) or 0) - float(o.get("exemption", 0) or 0)) > 0.5:
            ch.append({"label": f"{c['code']} · Exemption", "old": _fmt_money(o.get("exemption", 0)), "new": _fmt_money(c.get("exemption", 0))})
    olds = {c["code"]: c for c in (old.get("security_classes") or [])}
    for c in (new.get("security_classes") or []):
        o = olds.get(c.get("code"))
        if o is None:
            ch.append({"label": f"Classe séc. {c.get('code')} (ajoutée)", "old": "—", "new": _fmt_pct(c.get("rate", 0))})
        elif abs(float(c.get("rate", 0) or 0) - float(o.get("rate", 0) or 0)) > 1e-9:
            ch.append({"label": f"Classe séc. {c['code']} · Taux", "old": _fmt_pct(o.get("rate", 0)), "new": _fmt_pct(c.get("rate", 0))})
    for key, lbl, kind in _HYPO_PARAMS:
        if key in new and key in old:
            try:
                if abs(float(new[key]) - float(old[key])) > (1e-9 if kind == "pct" else 0.005):
                    ch.append({"label": lbl, "old": _fmt_kind(old[key], kind), "new": _fmt_kind(new[key], kind)})
            except (TypeError, ValueError):
                pass
    return ch

_EMP_DIFF_FIELDS = [
    ("name", "Nom", "str"), ("department", "Département", "str"), ("title", "Titre", "str"),
    ("employment_type", "Type", "str"), ("current_annual_salary", "Salaire annuel", "money"),
    ("vacation_rate", "Taux vacances", "pct"), ("security_class", "Classe séc.", "str"),
    ("active", "Actif", "bool"), ("hire_date", "Embauche", "str"), ("end_date", "Fin d'emploi", "str"),
    ("prime_type", "Prime", "str"), ("sex_at_birth", "Sexe", "str"),
]

def _diff_employee(old, new):
    ch = []
    for key, lbl, kind in _EMP_DIFF_FIELDS:
        ov, nv = old.get(key), new.get(key)
        same = (ov == nv)
        if kind in ("money", "pct") and ov is not None and nv is not None:
            try:
                same = abs(float(ov) - float(nv)) < (1e-9 if kind == "pct" else 0.005)
            except (TypeError, ValueError):
                same = (ov == nv)
        if not same:
            ch.append({"label": lbl, "old": _fmt_kind(ov, kind), "new": _fmt_kind(nv, kind)})
    return ch

# ---------------------------------------------------------------------------
# Config / seed data
# ---------------------------------------------------------------------------
ANNUAL_HOURS = 2080
PRIME_PCT = {"Aucune Prime": 0.0, "Prime 8%": 0.08, "Prime 11%": 0.11, "Prime 12%": 0.12}

WD_CCQ = [22, 20, 22, 22, 21, 22, 13, 21, 22, 22, 21, 14]
WD_STD = [22, 20, 22, 22, 21, 22, 23, 21, 22, 22, 21, 23]
PAY_WEEKS = [5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 5]

def _first_saturday(year, month):
    d = datetime(year, month, 1)
    return d + timedelta(days=(5 - d.weekday()) % 7)

def _ccq_vacation_ranges(year):
    """Vacances de la construction (convention CCQ), calculées automatiquement.
    - Congé estival : période de 2 semaines se terminant le 1er samedi d'août.
    - Congé hivernal : période de 2 semaines se terminant le 1er samedi de janvier (année+1).
    On ne retient que la portion tombant dans l'année civile visée."""
    ranges = []
    summer_end = _first_saturday(year, 8)
    ranges.append((summer_end - timedelta(days=13), summer_end))
    winter_end = _first_saturday(year + 1, 1)
    ranges.append((winter_end - timedelta(days=13), winter_end))
    return ranges

def compute_working_days(year, ccq=False):
    """Jours ouvrables (lun-ven) par mois, SANS déduire les jours fériés officiels du Québec.
    Pour les employés CCQ, on déduit les jours des vacances de la construction (été + hiver)."""
    ranges = _ccq_vacation_ranges(year) if ccq else []
    out = []
    for m in range(1, 13):
        dim = calendar.monthrange(year, m)[1]
        count = 0
        for day in range(1, dim + 1):
            d = datetime(year, m, day)
            if d.weekday() >= 5:
                continue
            if ccq and d.year == year and any(s <= d <= e for s, e in ranges):
                continue
            count += 1
        out.append(count)
    return out

def _apply_working_days(hypo, year):
    """Recalcule les jours ouvrables (CCQ/standard) pour l'année donnée."""
    hypo["working_days_ccq"] = compute_working_days(int(year), ccq=True)
    hypo["working_days_std"] = compute_working_days(int(year), ccq=False)
    return hypo



DEFAULT_HYPOTHESES = {
    "key": "current", "year": 2026,
    "charges": [
        {"code": "RRQ", "name": "Régime de rentes du Québec", "rate": 0.064, "ceiling": 74600, "exemption": 3500},
        {"code": "AE", "name": "Assurance emploi", "rate": 0.0229, "ceiling": 68900, "exemption": 0},
        {"code": "RQAP", "name": "Régime québécois d'assurance parentale", "rate": 0.0069, "ceiling": 103000, "exemption": 0},
        {"code": "FSS", "name": "Fonds des services de santé", "rate": 0.0459, "ceiling": 0, "exemption": 0},
        {"code": "CSST", "name": "Commission de la santé et de la sécurité du travail", "rate": 0.0175, "ceiling": 103000, "exemption": 0},
    ],
    "assurance_annuelle": 3600, "reer_rate": 0.05,
    "ccq_rate": 0.3233,
    "prime_garde_cout_unitaire": 250, "prime_garde_nb_annuel": 2.08,
    "prime_halo_rate": 0.05, "alloc_securite_montant": 260,
    "augmentation_ccq": 0.0333, "augmentation_autres": 0.035,
    "csst_max_assurable": 103000,
    "security_classes": [
        {"code": "80190", "description": "Installation Eq. Contrôle", "rate": 0.0267},
        {"code": "80020", "description": "Bureau et Extérieur", "rate": 0.0061},
        {"code": "90010", "description": "Bureau", "rate": 0.0032},
        {"code": "80200", "description": "Frigoristes", "rate": 0.0357},
        {"code": "80170", "description": "Électriciens", "rate": 0.0412},
    ],
    "working_days_ccq": WD_CCQ, "working_days_std": WD_STD, "pay_weeks": PAY_WEEKS,
}

DEPARTMENTS_SEED = [
    {"code": "810", "description": "Électriciens", "superviseur": "Chef(fe) d'équipe-Électrique", "compte_gl": "5006003", "groupe_pl": "Projets", "csst": 0.030788},
    {"code": "500", "description": "Énergie", "superviseur": "Concepteur(rice) principal Efficacité Énergétique", "compte_gl": "5506005", "groupe_pl": "Services", "csst": 0.006092},
    {"code": "409", "description": "Entrepôt", "superviseur": "Directeur/trice Finances", "compte_gl": "5996000", "groupe_pl": "Opération Commun (FGF)", "csst": 0.006092},
    {"code": "406", "description": "Ventes", "superviseur": "Directeur(rice) des Ventes", "compte_gl": "6006000", "groupe_pl": "Ventes", "csst": 0.006092},
    {"code": "405", "description": "Informatique", "superviseur": "Directeur(rice) T.I.", "compte_gl": "7006000", "groupe_pl": "Informatique", "csst": 0.006092},
    {"code": "404", "description": "Gestion de service", "superviseur": "Directeur(rice) du Service et CVAC", "compte_gl": "5506004", "groupe_pl": "Services", "csst": 0.024390},
    {"code": "403", "description": "Marketing", "superviseur": "Directeur(rice) Marketing", "compte_gl": "8506000", "groupe_pl": "Marketing", "csst": 0.006092},
    {"code": "401", "description": "Ressources Humaines", "superviseur": "Président/e", "compte_gl": "8006000", "groupe_pl": "RH", "csst": 0.006092},
    {"code": "400", "description": "Administration", "superviseur": "Directeur/trice Finances", "compte_gl": "9006000", "groupe_pl": "Administration", "csst": 0.006092},
    {"code": "150", "description": "Télégestion", "superviseur": "Directeur(rice) du Service et CVAC", "compte_gl": "5506000", "groupe_pl": "Services", "csst": 0.006092},
    {"code": "120", "description": "Frigoristes", "superviseur": "Directeur(rice) du Service et CVAC", "compte_gl": "5506001", "groupe_pl": "Services", "csst": 0.036299},
    {"code": "110", "description": "Optimisation", "superviseur": "Directeur(rice) Optimisation", "compte_gl": "5506002", "groupe_pl": "Services", "csst": 0.023033},
    {"code": "100", "description": "Entr. Contrôles", "superviseur": "Directeur(rice) du Service et CVAC", "compte_gl": "5006001", "groupe_pl": "Projets", "csst": 0.023033},
    {"code": "30", "description": "Ingénierie", "superviseur": "Directeur(rice) Ingénierie", "compte_gl": "5006004", "groupe_pl": "Projets", "csst": 0.006092},
    {"code": "40", "description": "Charge de projets", "superviseur": "Directeur(rice) de Projets", "compte_gl": "5006005", "groupe_pl": "Projets", "csst": 0.006092},
    {"code": "50", "description": "Programmation", "superviseur": "Chef(fe) programmation", "compte_gl": "5006006", "groupe_pl": "Projets", "csst": 0.006092},
    {"code": "20", "description": "Mise en service", "superviseur": "Directeur(rice) Mise en service", "compte_gl": "5006002", "groupe_pl": "Projets", "csst": 0.023033},
]

EMPLOYEES_SEED = [
    {"name": "Marie Bouchère", "department": "810", "title": "Électricien", "employment_type": "CCQ", "ccq_category": "Électricien", "current_annual_salary": 100000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 12%", "prime_garde": True, "prime_halo": False, "alloc_securite": True, "hire_date": "2015-03-11", "birth_date": "1984-06-23"},
    {"name": "Sophie Roy", "department": "120", "title": "Frigoriste", "employment_type": "CCQ", "ccq_category": "Frigoriste", "current_annual_salary": 95000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 11%", "prime_garde": True, "prime_halo": False, "alloc_securite": True, "hire_date": "2019-09-02", "birth_date": "1990-02-14"},
    {"name": "Jean Tremblera", "department": "400", "title": "Comptable", "employment_type": "Régulier temps plein", "ccq_category": "N/A", "current_annual_salary": 91237.40, "vacation_rate": 0.08, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_halo": True, "alloc_securite": False, "hire_date": "2012-06-04", "birth_date": "1980-12-11"},
    {"name": "Pierre Soccer", "department": "406", "title": "Chargé d'affaires", "employment_type": "Régulier temps plein", "ccq_category": "N/A", "current_annual_salary": 100609.60, "vacation_rate": 0.10, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_halo": True, "alloc_securite": False, "hire_date": "2010-01-18", "birth_date": "1978-04-19"},
    {"name": "John Intern", "department": "110", "title": "Stagiaire", "employment_type": "Stagiaire", "ccq_category": "N/A", "current_annual_salary": 21000, "vacation_rate": 0.04, "sick_personal_days": 5, "holiday_days": 10, "is_ccq": False, "prime_type": "Aucune Prime", "prime_garde": False, "prime_halo": False, "alloc_securite": False, "hire_date": "2024-05-06", "birth_date": "2001-07-27"},
    {"name": "Isabelle Caron", "department": "401", "title": "Conseillère RH", "employment_type": "Régulier temps plein", "ccq_category": "N/A", "current_annual_salary": 72000, "vacation_rate": 0.08, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_halo": False, "alloc_securite": False, "hire_date": "2020-11-23", "birth_date": "1991-07-27"},
]

# ---------------------------------------------------------------------------
# Budget engine
# ---------------------------------------------------------------------------
def _capped(amount, rate, ceiling, exemption=0):
    base = amount if not ceiling else min(amount, ceiling)
    base = max(0.0, base - exemption)
    return base * rate

MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]

def _emp_scn(e, year, scenario):
    yd = (e.get("years") or {}).get(str(year), {}) if year else {}
    ov = (yd.get(scenario) or {}) if (scenario and scenario != "actuel") else {}
    base = ov.get("base_salary", yd.get("base_salary", e["current_annual_salary"]))
    return yd, ov, base

def _proration(e, year):
    """Retourne (fractions mensuelles [12], facteur annuel). Pro-rata au jour pour l'embauche
    et la fin d'emploi survenant en cours d'année."""
    frac = [1.0] * 12
    if not year:
        return frac, 1.0
    y = int(year)

    def _parse(d):
        try:
            p = str(d)[:10].split("-")
            return int(p[0]), int(p[1]), int(p[2])
        except Exception:
            return None
    hd = _parse(e.get("hire_date"))
    ed = _parse(e.get("end_date"))
    for m in range(1, 13):
        dim = calendar.monthrange(y, m)[1]
        start_day, end_day = 1, dim
        if hd:
            hy, hm, hday = hd
            if hy > y or (hy == y and hm > m):
                frac[m - 1] = 0.0
                continue
            if hy == y and hm == m:
                start_day = hday
        if ed:
            ey, em, eday = ed
            if ey < y or (ey == y and em < m):
                frac[m - 1] = 0.0
                continue
            if ey == y and em == m:
                end_day = min(end_day, eday)
        active = end_day - start_day + 1
        frac[m - 1] = 0.0 if active <= 0 else (1.0 if active >= dim else round(active / dim, 6))
    return frac, sum(frac) / 12

def _salary_change_weight(year, change_date):
    """Fraction (0..1) de l'année à partir de la date de changement de salaire (jours civils)."""
    try:
        p = str(change_date)[:10].split("-")
        cy, cm, cd = int(p[0]), int(p[1]), int(p[2])
    except Exception:
        return None
    y = int(year)
    if cy < y:
        return 1.0
    if cy > y:
        return 0.0
    start = datetime(y, 1, 1)
    end = datetime(y, 12, 31)
    change = datetime(y, cm, cd)
    total = (end - start).days + 1
    after = max(0, min(total, (end - change).days + 1))
    return round(after / total, 6)

def compute_budget(employees, hypo, depts, year=None, scenario="ca"):
    dept_csst = {d["code"]: d.get("csst", 0) for d in depts}
    class_rates = {c["code"]: c["rate"] for c in hypo.get("security_classes", [])}
    csst_ceiling = hypo.get("csst_max_assurable", 103000)
    dept_label = {d["code"]: d["description"] for d in depts}
    charges = {c["code"]: c for c in hypo["charges"]}
    aug_ccq = hypo["augmentation_ccq"]
    aug_autres = hypo["augmentation_autres"]
    is_actuel = scenario == "actuel"
    if not is_actuel and year:
        _ikey = f"{int(year)}:{scenario}"
        employees = [e for e in employees if _ikey not in (e.get("inactive_scenarios") or [])]

    def _garde_on(e):
        _, o, _ = _emp_scn(e, year, scenario)
        return e.get("is_ccq") and o.get("prime_garde", e.get("prime_garde"))
    eligible = [] if is_actuel else [e for e in employees if _garde_on(e)]
    garde_avg = hypo["prime_garde_cout_unitaire"] * hypo["prime_garde_nb_annuel"]

    lines = []
    tot = {"salaire_base": 0, "vacances": 0, "primes": 0, "avantages": 0,
           "csst": 0, "reer": 0, "assurance": 0, "budget_total": 0}
    for e in employees:
        ydata, ov, base = _emp_scn(e, year, scenario)
        manual = ov.get("manual", {}) if not is_actuel else {}
        def mval(key, computed):
            v = manual.get(key)
            if v is None or v == "":
                return computed
            try:
                return float(v)
            except Exception:
                return computed
        emp_type = ov.get("employment_type", e["employment_type"]) if not is_actuel else e["employment_type"]
        ccq = (emp_type == "CCQ")
        dept_code = ov.get("department", e["department"]) if not is_actuel else e["department"]
        emp_rate = 1.0
        if not is_actuel and emp_type == "Régulier temps partiel":
            try:
                emp_rate = float(ov.get("employment_rate", 1) or 1)
            except Exception:
                emp_rate = 1.0
            if emp_rate <= 0:
                emp_rate = 1.0
        aug = 0 if is_actuel else ov.get("augmentation", aug_ccq if ccq else aug_autres)
        new_salary = base * (1 + aug) * emp_rate
        # Proration selon la date de changement de salaire (portion avant = salaire de base actuel, non proratisé).
        new_salary_rate = new_salary
        scd = None if is_actuel else ov.get("salary_change_date")
        if scd:
            w = _salary_change_weight(year, scd)
            if w is not None:
                new_salary = base * emp_rate * (1 - w) + new_salary_rate * w
        new_salary = mval("new_salary", new_salary)
        taux_horaire = new_salary / ANNUAL_HOURS

        prime_type = ov.get("prime_type", e.get("prime_type", "Aucune Prime"))
        boni = tedy = telus = 0
        if is_actuel:
            # Salaires actuels : uniquement le salaire de base, sans prime ni charge.
            prime_type = "Aucune Prime"
            prime_amt = garde = halo = alloc = 0
        elif ccq:
            prime_amt = mval("prime_amount", new_salary * PRIME_PCT.get(prime_type, 0.0))
            garde = mval("garde", garde_avg * emp_rate if ov.get("prime_garde", e.get("prime_garde")) else 0)
            halo = mval("halo", new_salary * hypo["prime_halo_rate"] if ov.get("prime_halo", e.get("prime_halo")) else 0)
            alloc = mval("alloc", hypo["alloc_securite_montant"] * emp_rate if ov.get("alloc_securite", e.get("alloc_securite")) else 0)
        else:
            # Employés non-CCQ : pas de prime CCQ ni HALO/garde. Boni + Alloc. sécurité + REER/assurance possibles.
            prime_type = "Aucune Prime"
            prime_amt = garde = halo = 0
            alloc = mval("alloc", hypo["alloc_securite_montant"] * emp_rate if ov.get("alloc_securite", e.get("alloc_securite")) else 0)
            boni_mode = ov.get("boni_mode", "montant")
            if boni_mode == "pct":
                boni = new_salary * float(ov.get("boni_pct", 0) or 0) / 100
            else:
                boni = float(ov.get("boni", 0) or 0) * emp_rate
            boni = mval("boni", boni)
            # Primes Tedy / Telus (non-CCQ, montants fixes $) : incluses uniquement dans les bases RRQ/FSS/RQAP/CSST.
            tedy = mval("tedy", float(ov.get("tedy", 0) or 0) * emp_rate)
            telus = mval("telus", float(ov.get("telus", 0) or 0) * emp_rate)
        primes_core = prime_amt + garde + halo + alloc + boni
        primes_total = primes_core + tedy + telus

        vac_rate = ov.get("vacation_rate", e["vacation_rate"])
        vacation = 0 if is_actuel else mval("vacation", vac_rate * (new_salary + primes_core))

        boni_gl = 0.0
        if is_actuel:
            rrq = ae = rqap = fss = csst = gov = ccq_av = avantages = reer = assurance = 0
            total = new_salary
        else:
            gross_core = new_salary + vacation + primes_core
            gross_ext = gross_core + tedy + telus
            rrq = mval("rrq", _capped(gross_ext, charges["RRQ"]["rate"], charges["RRQ"]["ceiling"], charges["RRQ"]["exemption"]))
            ae = mval("ae", _capped(gross_core, charges["AE"]["rate"], charges["AE"]["ceiling"]))
            rqap = mval("rqap", _capped(gross_ext, charges["RQAP"]["rate"], charges["RQAP"]["ceiling"]))
            fss = mval("fss", _capped(gross_ext, charges["FSS"]["rate"], charges["FSS"]["ceiling"]))
            csst_rate = class_rates.get(e.get("security_class")) if e.get("security_class") in class_rates else 0
            csst = mval("csst", _capped(gross_ext, csst_rate, csst_ceiling))
            gov = rrq + ae + rqap + fss
            if ccq:
                ccq_av = mval("ccq_avantages", (new_salary + primes_core) * hypo["ccq_rate"])
                avantages = gov + ccq_av
                reer = 0
                assurance = 0
            else:
                ccq_av = 0
                avantages = gov
                reer = mval("reer", float(ov.get("reer", new_salary * hypo["reer_rate"])))
                assurance = mval("assurance", float(ov.get("assurance", hypo["assurance_annuelle"])))
            total = new_salary + vacation + primes_total + avantages + csst + reer + assurance
            # GL Boni : boni + charges sociales marginales (RRQ+AE+RQAP+FSS+CSST) attribuables au boni.
            if not ccq and boni > 0:
                base_wo = gross_ext - boni
                core_wo = gross_core - boni
                d_rrq = _capped(gross_ext, charges["RRQ"]["rate"], charges["RRQ"]["ceiling"], charges["RRQ"]["exemption"]) - _capped(base_wo, charges["RRQ"]["rate"], charges["RRQ"]["ceiling"], charges["RRQ"]["exemption"])
                d_ae = _capped(gross_core, charges["AE"]["rate"], charges["AE"]["ceiling"]) - _capped(core_wo, charges["AE"]["rate"], charges["AE"]["ceiling"])
                d_rqap = _capped(gross_ext, charges["RQAP"]["rate"], charges["RQAP"]["ceiling"]) - _capped(base_wo, charges["RQAP"]["rate"], charges["RQAP"]["ceiling"])
                d_fss = _capped(gross_ext, charges["FSS"]["rate"], charges["FSS"]["ceiling"]) - _capped(base_wo, charges["FSS"]["rate"], charges["FSS"]["ceiling"])
                d_csst = _capped(gross_ext, csst_rate, csst_ceiling) - _capped(base_wo, csst_rate, csst_ceiling)
                boni_gl = boni + d_rrq + d_ae + d_rqap + d_fss + d_csst
        frac, factor = _proration(e, year)
        months_active = sum(1 for x in frac if x > 0)
        hire_month = next((i + 1 for i, x in enumerate(frac) if x > 0), 0)
        prorated = factor < 0.9999
        wd = hypo["working_days_ccq"] if ccq else hypo["working_days_std"]
        wd_total = sum(wd) or 1
        monthly = [round(total * wd[m] * frac[m] / wd_total, 2) for m in range(12)]
        total_budgeted = round(total * factor, 2)
        lines.append({
            "employee_id": str(e.get("_id", "")), "employee_number": e["employee_number"],
            "name": e["name"], "title": e.get("title", ""), "department": dept_code,
            "department_label": dept_label.get(dept_code, dept_code),
            "employment_type": emp_type, "is_ccq": ccq, "overridden": bool(ov),
            "employment_rate": round(emp_rate, 4),
            "security_class": e.get("security_class") or "",
            "base_salary": round(base, 2), "augmentation": aug, "new_salary": round(new_salary, 2),
            "new_salary_rate": round(new_salary_rate, 2), "salary_change_date": scd or "",
            "taux_horaire": round(taux_horaire, 2), "vacation_rate": vac_rate, "vacation": round(vacation, 2),
            "prime_type": prime_type, "prime_amount": round(prime_amt, 2), "garde": round(garde, 2),
            "halo": round(halo, 2), "alloc": round(alloc, 2),
            "boni": round(boni, 2), "tedy": round(tedy, 2), "telus": round(telus, 2),
            "primes_total": round(primes_total, 2),
            "salaire_brut": round(new_salary + vacation + primes_total, 2),
            "boni_mode": (ov.get("boni_mode", "montant") if not ccq else "montant"),
            "boni_pct": float(ov.get("boni_pct", 0) or 0),
            "boni_gl": round(boni_gl * factor, 2), "manual": manual,
            "rrq": round(rrq, 2), "ae": round(ae, 2), "rqap": round(rqap, 2), "fss": round(fss, 2),
            "ccq_avantages": round(ccq_av, 2), "avantages": round(avantages, 2), "csst": round(csst, 2),
            "reer": round(reer, 2), "assurance": round(assurance, 2), "total_cost": round(total, 2),
            "monthly": monthly, "months_active": months_active, "hire_month": hire_month,
            "prorated": prorated, "proration_factor": round(factor, 4), "total_budgeted": total_budgeted,
        })
        tot["salaire_base"] += new_salary * factor
        tot["vacances"] += vacation * factor
        tot["primes"] += primes_total * factor
        tot["avantages"] += avantages * factor
        tot["csst"] += csst * factor
        tot["reer"] += reer * factor
        tot["assurance"] += assurance * factor
        tot["budget_total"] += total_budgeted

    totals = {k: round(v, 2) for k, v in tot.items()}
    # by department
    by_dept = {}
    for ln in lines:
        d = by_dept.setdefault(ln["department"], {"department": ln["department"], "label": ln["department_label"], "salaire": 0, "budget": 0})
        d["salaire"] += ln["new_salary"] * ln["proration_factor"]
        d["budget"] += ln["total_budgeted"]
    by_department = sorted([{**v, "salaire": round(v["salaire"], 2), "budget": round(v["budget"], 2)} for v in by_dept.values()], key=lambda x: -x["budget"])
    # répartition par sexe à la naissance, par département
    _label_map = {ln["department"]: ln["department_label"] for ln in lines}
    def _sexcat(e):
        s = e.get("sex_at_birth")
        return s if s in ("Masculin", "Féminin", "Autre") else "Non spécifié"
    sxd = {}
    for e in employees:
        dep = e.get("department", "")
        d = sxd.setdefault(dep, {"department": dep, "label": _label_map.get(dep, dep), "Masculin": 0, "Féminin": 0, "Autre": 0, "Non spécifié": 0, "total": 0})
        d[_sexcat(e)] += 1
        d["total"] += 1
    sex_by_department = sorted(sxd.values(), key=lambda x: -x["total"])
    # by type
    by_type_map = {}
    for ln in lines:
        by_type_map[ln["employment_type"]] = by_type_map.get(ln["employment_type"], 0) + ln["total_budgeted"]
    by_type = [{"type": k, "total": round(v, 2)} for k, v in by_type_map.items()]
    # monthly ventilation — distribution par jours ouvrables (CCQ/standard selon l'employé),
    # agrégée à partir des ventilations mensuelles individuelles pondérées par les jours ouvrables.
    sal_ratio = (totals["salaire_base"] + totals["vacances"] + totals["primes"]) / totals["budget_total"] if totals["budget_total"] else 0
    monthly = []
    for i, m in enumerate(MONTHS):
        mt = round(sum(ln["monthly"][i] for ln in lines), 2)
        sal = mt * sal_ratio
        monthly.append({"month": m, "sem_paie": hypo["pay_weeks"][i], "jours_std": hypo["working_days_std"][i],
                        "jours_ccq": hypo["working_days_ccq"][i], "salaires": round(sal, 2),
                        "charges": round(mt - sal, 2), "total": round(mt, 2)})
    # decomposition
    bt = totals["budget_total"] or 1
    decomposition = [
        {"label": "Salaire", "value": totals["salaire_base"], "pct": round(totals["salaire_base"] / bt * 100, 1), "color": "#2563EB"},
        {"label": "Vacances", "value": totals["vacances"], "pct": round(totals["vacances"] / bt * 100, 1), "color": "#22C55E"},
        {"label": "Primes & Boni", "value": totals["primes"], "pct": round(totals["primes"] / bt * 100, 1), "color": "#FBBF24"},
        {"label": "Avantages soc.", "value": totals["avantages"], "pct": round(totals["avantages"] / bt * 100, 1), "color": "#8B5CF6"},
        {"label": "CSST", "value": totals["csst"], "pct": round(totals["csst"] / bt * 100, 1), "color": "#EF4444"},
        {"label": "RPDB (REER)", "value": totals["reer"], "pct": round(totals["reer"] / bt * 100, 1), "color": "#22C55E"},
    ]
    top5 = sorted(lines, key=lambda x: -x["total_budgeted"])[:5]
    top5 = [{"name": l["name"], "title": l["title"], "department": l["department"],
             "total": l["total_budgeted"], "base": l["base_salary"], "rank": i + 1} for i, l in enumerate(top5)]
    kpis = {
        "headcount": len(employees),
        "masse_salariale": totals["salaire_base"],
        "budget_global": totals["budget_total"],
        "salaire_moyen": round(totals["salaire_base"] / len(employees), 2) if employees else 0,
        "ccq_count": sum(1 for e in employees if e.get("is_ccq")),
        "non_ccq_count": sum(1 for e in employees if not e.get("is_ccq") and e.get("employment_type") != "Stagiaire"),
        "stagiaire_count": sum(1 for e in employees if e.get("employment_type") == "Stagiaire"),
        "sex_counts": {
            "Masculin": sum(1 for e in employees if e.get("sex_at_birth") == "Masculin"),
            "Féminin": sum(1 for e in employees if e.get("sex_at_birth") == "Féminin"),
            "Autre": sum(1 for e in employees if e.get("sex_at_birth") == "Autre"),
            "Non spécifié": sum(1 for e in employees if e.get("sex_at_birth") in (None, "", "Préfère ne pas répondre")),
        },
        "garde_moyenne": round(garde_avg, 2),
    }
    return {"lines": lines, "totals": totals, "by_department": by_department, "by_type": by_type,
            "sex_by_department": sex_by_department,
            "monthly": monthly, "decomposition": decomposition, "top5": top5, "kpis": kpis}

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
class LoginPayload(BaseModel):
    email: str
    password: str
    remember: bool = True


@api.post("/auth/login")
async def login(payload: LoginPayload, response: Response):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Courriel ou mot de passe invalide")
    uid = str(user["_id"])
    token = create_token(uid, email)
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax",
                        max_age=(604800 if payload.remember else None), path="/")
    return {"token": token, "user": {"id": uid, "email": email, "name": user.get("name", ""), "role": _normalized_role(user.get("role", "user"))}}

@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"success": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return auth_me_payload(user)


# ---------------------------------------------------------------------------
# Emergent Google Auth (social login). Coexists with email/password.
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
# THIS BREAKS THE AUTH. The redirect_url is derived on the FRONTEND from
# window.location.origin; here we only exchange the session_id server-side.
# ---------------------------------------------------------------------------
_EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class GoogleSessionPayload(BaseModel):
    session_id: str


@api.post("/auth/session")
async def google_session(payload: GoogleSessionPayload, response: Response):
    sid = (payload.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id manquant")
    try:
        r = await asyncio.to_thread(
            requests.get, _EMERGENT_SESSION_URL, headers={"X-Session-ID": sid}, timeout=15)
    except Exception:
        raise HTTPException(status_code=502, detail="Service d'authentification Google indisponible")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Session Google invalide ou expirée")
    data = r.json()
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Compte Google sans courriel")
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one({"email": email})
    if existing:
        uid = str(existing["_id"])
        upd = {"last_login_at": now, "auth_provider": "google"}
        if data.get("name") and not existing.get("name"):
            upd["name"] = data.get("name")
        if data.get("picture"):
            prefs = {**(existing.get("preferences") or {})}
            prefs.setdefault("google_picture", data.get("picture"))
            upd["preferences"] = prefs
        await db.users.update_one({"_id": existing["_id"]}, {"$set": upd})
        role = _normalized_role(existing.get("role", "user"))
        name = upd.get("name", existing.get("name", ""))
    else:
        doc = {"email": email, "name": data.get("name") or email, "password_hash": None,
               "role": "user", "status": "active", "auth_provider": "google",
               "preferences": ({"google_picture": data.get("picture")} if data.get("picture") else {}),
               "created_at": now, "last_login_at": now}
        res = await db.users.insert_one(doc)
        uid = str(res.inserted_id)
        role, name = "user", doc["name"]
    token = create_token(uid, email)
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax",
                        max_age=604800, path="/")
    return {"token": token, "user": {"id": uid, "email": email, "name": name, "role": role}}


# ---------------------------------------------------------------------------
# Password reset (single-use, 1h token, delivered via Resend).
# ---------------------------------------------------------------------------
class ForgotPasswordPayload(BaseModel):
    email: str


class ResetPasswordPayload(BaseModel):
    token: str
    password: str


def _create_reset_token(user_id: str, email: str, jti: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "reset", "jti": jti,
               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def _send_reset_email(email: str, name: str, link: str) -> bool:
    if not os.environ.get("RESEND_API_KEY"):
        return False
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#0F172A">
      <h2 style="color:#0F172A">Réinitialisation de votre mot de passe</h2>
      <p>Bonjour {name or ''},</p>
      <p>Vous avez demandé à réinitialiser votre mot de passe Meelora. Ce lien est valable 1 heure.</p>
      <p style="margin:28px 0">
        <a href="{link}" style="background:#22C55E;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:600">Réinitialiser mon mot de passe</a>
      </p>
      <p style="color:#64748B;font-size:13px">Si vous n'êtes pas à l'origine de cette demande, ignorez ce courriel.</p>
      <p style="color:#94A3B8;font-size:12px;margin-top:24px">Meelora — Votre entreprise, clairement.</p>
    </div>"""
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
            "to": [email], "subject": "Réinitialisation de votre mot de passe Meelora", "html": html})
        return True
    except Exception as e:
        logger.error(f"Resend reset email échec: {e}")
        return False


@api.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordPayload):
    email = (payload.email or "").strip().lower()
    generic = {"success": True,
               "message": "Si un compte existe pour ce courriel, un lien de réinitialisation a été envoyé."}
    if not email:
        return generic
    user = await db.users.find_one({"email": email})
    # Only local (password) accounts can reset; never leak account existence.
    if user and user.get("password_hash"):
        jti = uuid.uuid4().hex
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"reset_token_jti": jti}})
        token = _create_reset_token(str(user["_id"]), email, jti)
        base = os.environ.get("FRONTEND_URL", "").rstrip("/")
        link = f"{base}/reset-password?token={token}"
        await _send_reset_email(email, user.get("name", ""), link)
    return generic


@api.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordPayload):
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=422, detail="Le mot de passe doit contenir au moins 6 caractères")
    try:
        claims = jwt.decode(payload.token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Lien expiré. Veuillez refaire une demande.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Lien invalide.")
    if claims.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Lien invalide.")
    user = await db.users.find_one({"_id": ObjectId(claims["sub"])})
    if not user or user.get("reset_token_jti") != claims.get("jti"):
        raise HTTPException(status_code=400, detail="Lien invalide ou déjà utilisé.")
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"password_hash": hash_password(payload.password)},
                               "$unset": {"reset_token_jti": ""}})
    return {"success": True, "message": "Mot de passe réinitialisé. Vous pouvez vous connecter."}

@api.get("/me/preferences")
async def get_preferences(user: dict = Depends(get_current_user)):
    return user.get("preferences", {}) or {}
@api.put("/me/preferences")
async def update_preferences(request: Request, user: dict = Depends(get_current_user)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corps JSON invalide")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Format invalide")
    prefs = {**(user.get("preferences") or {}), **payload}
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"preferences": prefs}})
    return prefs


@api.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (max 5 Mo)")
    ext = ((file.filename or "png").rsplit(".", 1)[-1] or "png").lower()
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        ext = "png"
    ct = file.content_type or "image/png"
    path = f"avatars/{user['id']}.{ext}"
    _qc_put_object(path, data, ct)
    prefs = {**(user.get("preferences") or {}), "avatar_path": path, "avatar_ct": ct}
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"preferences": prefs}})
    return {"ok": True, "avatar_path": path}


@api.delete("/me/avatar")
async def delete_avatar(user: dict = Depends(get_current_user)):
    prefs = {**(user.get("preferences") or {})}
    prefs.pop("avatar_path", None)
    prefs.pop("avatar_ct", None)
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"preferences": prefs}})
    return {"ok": True}


@api.get("/users/{uid}/avatar")
async def get_avatar(uid: str):
    from starlette.responses import Response
    try:
        u = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        u = None
    path = (u or {}).get("preferences", {}).get("avatar_path") if u else None
    if not path:
        raise HTTPException(status_code=404, detail="Aucune photo")
    content, ct = _qc_get_object(path)
    return Response(content=content, media_type=ct, headers={"Cache-Control": "no-cache"})


@api.get("/companies")
async def list_companies(user: dict = Depends(get_current_user)):
    """List only companies visible to the authenticated user (P1.4)."""
    return await list_companies_for_user(db, user)


@api.post("/companies/import/preview")
async def preview_companies_import(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")): raise HTTPException(status_code=422, detail="Format attendu: .xlsx")
    return await preview_company_import(db, user, await file.read())

@api.post("/companies/import/commit")
async def commit_companies_import(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")): raise HTTPException(status_code=422, detail="Format attendu: .xlsx")
    result = await commit_company_import(db, user, await file.read())
    # P1.9: journaliser chaque société créée (company.created) en plus de l'évènement batch.
    for item in result.get("items", []):
        company = item.get("company") or {}
        await log_action(user, "create", "company", company.get("name") or company.get("legal_name", ""),
                         details=f"Société créée via import: {company.get('id')}",
                         company_id=company.get("id"), entity_id=company.get("id"),
                         event_type="company.created")
    await log_action(user, "import", "company", file.filename, details=f"Import sociétés: {result['created']} créée(s)", event_type="company.bulk_imported")
    return result

@api.post("/companies", status_code=201)
async def create_company(payload: CompanyCreate, user: dict = Depends(require_admin)):
    company = await create_company_for_admin(db, user, payload)
    await log_action(user, "create", "company", company.get("name") or company.get("legal_name", ""),
                     details=f"Société créée: {company.get('id')}",
                     company_id=company.get("id"), entity_id=company.get("id"),
                     event_type="company.created")
    return company


@api.get("/companies/{company_id}")
async def get_company(company_id: str, user: dict = Depends(get_current_user)):
    return await get_company_for_user(db, company_id, user)


@api.patch("/companies/{company_id}")
async def update_company(company_id: str, payload: CompanyUpdate, user: dict = Depends(require_admin)):
    before = await get_company_for_user(db, company_id, user, admin_required=True)
    company = await update_company_for_admin(db, company_id, user, payload)
    await log_action(user, "update", "company", company.get("name") or company.get("legal_name", ""),
                     details=f"Société modifiée: {company_id}",
                     changes=[{"field": k, "before": before.get(k), "after": company.get(k)}
                              for k in payload.model_dump(exclude_unset=True).keys()],
                     company_id=company_id, entity_id=company_id, event_type="company.updated")
    return company


@api.get("/mandates")
async def list_mandates(user: dict = Depends(get_current_user)):
    return await list_mandates_for_user(db, user)


@api.post("/mandates", status_code=201)
async def create_mandate(payload: MandateCreate, user: dict = Depends(require_admin)):
    mandate = await create_mandate_for_admin(db, user, payload)
    await log_action(user, "create", "mandate", mandate.get("mandate_code", ""),
                     details=f"Mandat créé: {mandate.get('id')} · société {mandate.get('company_id')}",
                     company_id=mandate.get("company_id"), mandate_id=mandate.get("id"),
                     entity_id=mandate.get("id"), event_type="mandate.created")
    return mandate


@api.get("/mandates/{mandate_id}")
async def get_mandate(mandate_id: str, user: dict = Depends(get_current_user)):
    return await get_mandate_for_user(db, mandate_id, user)


@api.patch("/mandates/{mandate_id}")
async def update_mandate(mandate_id: str, payload: MandateUpdate, user: dict = Depends(require_admin)):
    before = await get_mandate_for_user(db, mandate_id, user)
    mandate = await update_mandate_for_admin(db, mandate_id, user, payload)
    await log_action(user, "update", "mandate", mandate.get("mandate_code", ""),
                     details=f"Mandat modifié: {mandate_id}",
                     changes=[{"field": k, "before": before.get(k), "after": mandate.get(k)}
                              for k in payload.model_dump(exclude_unset=True).keys()],
                     company_id=mandate.get("company_id"), mandate_id=mandate_id,
                     entity_id=mandate_id, event_type="mandate.updated")
    return mandate


# ---------------------------------------------------------------------------
# P2.1 — Financial Core : exercices financiers (financial_years)
# Routes fines déléguant au module core.financial.years (autorisation Phase 1).
# ---------------------------------------------------------------------------
@api.get("/companies/{company_id}/financial-years")
async def list_company_financial_years(company_id: str, user: dict = Depends(get_current_user)):
    return await list_financial_years(db, company_id, user)


@api.post("/companies/{company_id}/financial-years", status_code=201)
async def create_company_financial_year(company_id: str, payload: FinancialYearCreate, user: dict = Depends(require_admin)):
    fy = await create_financial_year(db, company_id, user, payload)
    await log_action(user, "create", "financial_year", fy.get("label", ""),
                     details=f"Exercice créé: {fy.get('id')} ({fy.get('start_date')} → {fy.get('end_date')})",
                     company_id=company_id, entity_id=fy.get("id"),
                     event_type="financial_year.created")
    return fy


@api.get("/companies/{company_id}/financial-years/{financial_year_id}")
async def get_company_financial_year(company_id: str, financial_year_id: str, user: dict = Depends(get_current_user)):
    return await get_financial_year(db, company_id, financial_year_id, user)


@api.patch("/companies/{company_id}/financial-years/{financial_year_id}")
async def update_company_financial_year(company_id: str, financial_year_id: str, payload: FinancialYearUpdate, user: dict = Depends(require_admin)):
    fy, prev_status = await update_financial_year(db, company_id, financial_year_id, user, payload)
    await log_action(user, "update", "financial_year", fy.get("label", ""),
                     details=f"Exercice modifié: {financial_year_id}",
                     changes=[{"field": k, "after": fy.get(k)} for k in payload.model_dump(exclude_unset=True).keys()],
                     company_id=company_id, entity_id=financial_year_id,
                     event_type="financial_year.updated")
    if prev_status is not None:
        new_status = fy.get("status")
        if new_status == "closed":
            await log_action(user, "close", "financial_year", fy.get("label", ""),
                             details=f"Exercice clôturé: {financial_year_id}",
                             company_id=company_id, entity_id=financial_year_id,
                             event_type="financial_year.closed")
        elif new_status == "open":
            await log_action(user, "reopen", "financial_year", fy.get("label", ""),
                             details=f"Exercice réouvert: {financial_year_id}",
                             company_id=company_id, entity_id=financial_year_id,
                             event_type="financial_year.reopened")
    return fy


# ---------------------------------------------------------------------------
# P2.2 — Financial Core : périodes financières (financial_periods)
# Routes fines déléguant au module core.financial.periods (autorisation Phase 1).
# ---------------------------------------------------------------------------
@api.get("/companies/{company_id}/financial-years/{financial_year_id}/periods")
async def list_year_periods(company_id: str, financial_year_id: str, user: dict = Depends(get_current_user)):
    return await list_financial_periods(db, company_id, financial_year_id, user)


@api.post("/companies/{company_id}/financial-years/{financial_year_id}/periods", status_code=201)
async def create_year_period(company_id: str, financial_year_id: str, payload: FinancialPeriodCreate, user: dict = Depends(require_admin)):
    p = await create_financial_period(db, company_id, financial_year_id, user, payload)
    await log_action(user, "create", "financial_period", p.get("period_code", ""),
                     details=f"Période créée: {p.get('id')} ({p.get('start_date')} → {p.get('end_date')})",
                     company_id=company_id, entity_id=p.get("id"),
                     event_type="financial_period.created")
    return p


@api.post("/companies/{company_id}/financial-years/{financial_year_id}/periods/generate-monthly")
async def generate_year_monthly_periods(company_id: str, financial_year_id: str, user: dict = Depends(require_admin)):
    result = await generate_monthly_periods(db, company_id, financial_year_id, user)
    await log_action(user, "generate", "financial_period", financial_year_id,
                     details=f"Génération mensuelle: {result['created']} créée(s), {result['skipped']} ignorée(s)",
                     company_id=company_id, entity_id=financial_year_id,
                     event_type="financial_periods.generated")
    return result


@api.get("/companies/{company_id}/financial-periods/{period_id}")
async def get_company_financial_period(company_id: str, period_id: str, user: dict = Depends(get_current_user)):
    return await get_financial_period(db, company_id, period_id, user)


@api.patch("/companies/{company_id}/financial-periods/{period_id}")
async def update_company_financial_period(company_id: str, period_id: str, payload: FinancialPeriodUpdate, user: dict = Depends(require_admin)):
    p, prev_status = await update_financial_period(db, company_id, period_id, user, payload)
    fy_id = p.get("financial_year_id")
    await log_action(user, "update", "financial_period", p.get("period_code", ""),
                     details=f"Période modifiée: {period_id}",
                     changes=[{"field": k, "after": p.get(k)} for k in payload.model_dump(exclude_unset=True).keys()],
                     company_id=company_id, entity_id=period_id,
                     event_type="financial_period.updated")
    if prev_status is not None:
        new_status = p.get("status")
        evt = None
        if new_status == "locked":
            evt = "financial_period.locked"
        elif new_status == "closed":
            evt = "financial_period.closed"
        elif new_status == "open" and prev_status == "locked":
            evt = "financial_period.unlocked"
        elif new_status == "open" and prev_status == "closed":
            evt = "financial_period.reopened"
        if evt:
            await log_action(user, "status", "financial_period", p.get("period_code", ""),
                             details=f"{prev_status} → {new_status} (période {period_id}, exercice {fy_id})",
                             company_id=company_id, entity_id=period_id, event_type=evt)
    return p


# ---------------------------------------------------------------------------
# P2.3 — Financial Core : comptes unifiés (accounts)
# Routes fines déléguant au module core.financial.accounts (autorisation Phase 1).
# ---------------------------------------------------------------------------
@api.get("/companies/{company_id}/accounts")
async def list_company_accounts(company_id: str, active: Optional[bool] = None,
                                account_type: Optional[str] = None, search: Optional[str] = None,
                                user: dict = Depends(get_current_user)):
    return await list_accounts(db, company_id, user, active=active, account_type=account_type, search=search)


@api.post("/companies/{company_id}/accounts", status_code=201)
async def create_company_account(company_id: str, payload: AccountCreate, user: dict = Depends(require_admin)):
    acc = await create_account(db, company_id, user, payload)
    await log_action(user, "create", "account", acc.get("account_code", ""),
                     details=f"Compte créé: {acc.get('id')} ({acc.get('account_type')}/{acc.get('normal_balance')})",
                     company_id=company_id, entity_id=acc.get("id"),
                     event_type="account.created")
    return acc


@api.get("/companies/{company_id}/accounts/{account_id}")
async def get_company_account(company_id: str, account_id: str, user: dict = Depends(get_current_user)):
    return await get_account(db, company_id, account_id, user)


@api.patch("/companies/{company_id}/accounts/{account_id}")
async def update_company_account(company_id: str, account_id: str, payload: AccountUpdate, user: dict = Depends(require_admin)):
    acc, active_changed_to = await update_account(db, company_id, account_id, user, payload)
    _acc_changes = payload.model_dump(exclude_unset=True)
    if _acc_changes:
        await log_action(user, "update", "account", acc.get("account_code", ""),
                         details=f"Compte modifié: {account_id}",
                         changes=[{"field": k, "after": acc.get(k)} for k in _acc_changes.keys()],
                         company_id=company_id, entity_id=account_id,
                         event_type="account.updated")
    if active_changed_to is True:
        await log_action(user, "reactivate", "account", acc.get("account_code", ""),
                         details=f"Compte réactivé: {account_id}", company_id=company_id,
                         entity_id=account_id, event_type="account.reactivated")
    elif active_changed_to is False:
        await log_action(user, "deactivate", "account", acc.get("account_code", ""),
                         details=f"Compte désactivé: {account_id}", company_id=company_id,
                         entity_id=account_id, event_type="account.deactivated")
    return acc


# ---------------------------------------------------------------------------
# P2.4 — Data Imports registry & lifecycle (accounts fully connected).
# Structural imports (preview/commit) = workspace admin only (aligné P2.3).
# History reads = tout membre société autorisé (require_company_access).
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/imports/accounts/preview")
async def preview_company_accounts_import(company_id: str, file: UploadFile = File(...),
                                          source_type: str = "excel",
                                          user: dict = Depends(require_admin)):
    content = await file.read()
    result = await preview_accounts_import(db, company_id, user, content, file.filename or "import", source_type)
    ev = "data_import.validated" if result.get("status") == "valid" else "data_import.previewed"
    await log_action(user, "preview", "data_import", result.get("id", ""),
                     details=f"Aperçu import comptes: {result.get('counts')}",
                     company_id=company_id, entity_id=result.get("id"),
                     event_type=ev,
                     metadata={"data_type": "accounts", "source_type": source_type})
    if result.get("status") == "failed":
        await log_action(user, "preview", "data_import", result.get("id", ""),
                         details="Aperçu import comptes: erreurs bloquantes",
                         company_id=company_id, entity_id=result.get("id"),
                         event_type="data_import.failed",
                         metadata={"data_type": "accounts", "source_type": source_type})
    return result


@api.post("/companies/{company_id}/imports/accounts/commit")
async def commit_company_accounts_import(company_id: str, payload: CommitRequest,
                                         user: dict = Depends(require_admin)):
    result = await commit_accounts_import(db, company_id, user, payload.import_id)
    ev = {"completed": "data_import.completed",
          "completed_with_warnings": "data_import.completed_with_warnings",
          "failed": "data_import.failed"}.get(result.get("status"), "data_import.completed")
    await log_action(user, "commit", "data_import", result.get("id", ""),
                     details=(f"Import comptes finalisé: +{result.get('records_created')} / "
                              f"~{result.get('records_updated')} / rejetés {result.get('records_rejected')}"),
                     company_id=company_id, entity_id=result.get("id"),
                     event_type=ev,
                     metadata={"data_type": "accounts", "source_type": result.get("source_type")})
    return result


@api.get("/companies/{company_id}/imports")
async def list_company_imports(company_id: str, data_type: Optional[str] = None,
                               source_type: Optional[str] = None, status: Optional[str] = None,
                               user: dict = Depends(get_current_user)):
    return await list_imports(db, company_id, user, data_type=data_type, source_type=source_type, status=status)


@api.get("/companies/{company_id}/imports/{import_id}")
async def get_company_import(company_id: str, import_id: str, user: dict = Depends(get_current_user)):
    return await get_import(db, company_id, import_id, user)


# ---------------------------------------------------------------------------
# P2.5 — Normalized Trial Balance (trial_balance_lines) via data_imports lifecycle.
# Structural TB import (preview/commit) = workspace admin only (aligné P2.4).
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/imports/trial-balance/preview")
async def preview_company_tb_import(company_id: str, financial_year_id: str = Form(...),
                                    financial_period_id: str = Form(...),
                                    source_type: str = Form("excel"),
                                    file: UploadFile = File(...),
                                    user: dict = Depends(require_admin)):
    content = await file.read()
    result = await preview_trial_balance_import(
        db, company_id, user, content, file.filename or "trial_balance",
        financial_year_id, financial_period_id, source_type)
    ev = "trial_balance.validated" if result.get("status") == "valid" else "trial_balance.previewed"
    await log_action(user, "preview", "trial_balance", result.get("id", ""),
                     details=f"Aperçu balance: {result.get('counts')} · contrôles {result.get('controls')}",
                     company_id=company_id, entity_id=result.get("id"), event_type=ev,
                     metadata={"data_type": "trial_balance", "source_type": source_type,
                               "financial_year_id": financial_year_id,
                               "financial_period_id": financial_period_id,
                               "controls": result.get("controls")})
    if result.get("status") == "failed":
        await log_action(user, "preview", "trial_balance", result.get("id", ""),
                         details=f"Aperçu balance en échec: {result.get('error_summary')}",
                         company_id=company_id, entity_id=result.get("id"),
                         event_type="trial_balance.failed",
                         metadata={"data_type": "trial_balance",
                                   "financial_period_id": financial_period_id})
    return result


@api.post("/companies/{company_id}/imports/trial-balance/commit")
async def commit_company_tb_import(company_id: str, payload: TBCommitRequest,
                                   user: dict = Depends(require_admin)):
    result = await commit_trial_balance_import(db, company_id, user, payload.import_id)
    ev = {"completed": "trial_balance.completed",
          "completed_with_warnings": "trial_balance.completed",
          "failed": "trial_balance.failed"}.get(result.get("status"), "trial_balance.completed")
    await log_action(user, "commit", "trial_balance", result.get("id", ""),
                     details=f"Balance finalisée: {result.get('records_created')} ligne(s)",
                     company_id=company_id, entity_id=result.get("id"), event_type=ev,
                     metadata={"data_type": "trial_balance",
                               "financial_year_id": result.get("financial_year_id"),
                               "financial_period_id": result.get("financial_period_id"),
                               "controls": result.get("controls")})
    return result


@api.get("/companies/{company_id}/trial-balance")
async def get_company_trial_balance(company_id: str, financial_period_id: Optional[str] = None,
                                    import_id: Optional[str] = None, account_id: Optional[str] = None,
                                    user: dict = Depends(get_current_user)):
    return await list_trial_balance(db, company_id, user, financial_period_id=financial_period_id,
                                    import_id=import_id, account_id=account_id)


@api.get("/companies/{company_id}/imports/{import_id}/trial-balance")
async def get_import_trial_balance(company_id: str, import_id: str, user: dict = Depends(get_current_user)):
    return await list_trial_balance(db, company_id, user, import_id=import_id)


# ---------------------------------------------------------------------------
# P2.6 — Normalized journal (journal_entries + journal_entry_lines) via data_imports.
# Structural journal import (preview/commit) = workspace admin only ; open period only.
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/imports/journal/preview")
async def preview_company_journal_import(company_id: str, financial_year_id: str = Form(...),
                                         financial_period_id: str = Form(...),
                                         source_type: str = Form("import"),
                                         file: UploadFile = File(...),
                                         user: dict = Depends(require_admin)):
    content = await file.read()
    result = await preview_journal_import(
        db, company_id, user, content, file.filename or "journal",
        financial_year_id, financial_period_id, source_type)
    ev = "journal.validated" if result.get("status") == "valid" else "journal.previewed"
    await log_action(user, "preview", "journal", result.get("id", ""),
                     details=f"Aperçu journal: {result.get('counts')} · contrôles {result.get('controls')}",
                     company_id=company_id, entity_id=result.get("id"), event_type=ev,
                     metadata={"data_type": "journal", "source_type": source_type,
                               "financial_year_id": financial_year_id,
                               "financial_period_id": financial_period_id,
                               "controls": result.get("controls")})
    if result.get("status") == "failed":
        await log_action(user, "preview", "journal", result.get("id", ""),
                         details=f"Aperçu journal en échec: {result.get('error_summary')}",
                         company_id=company_id, entity_id=result.get("id"),
                         event_type="journal.failed",
                         metadata={"data_type": "journal", "financial_period_id": financial_period_id})
    return result


@api.post("/companies/{company_id}/imports/journal/commit")
async def commit_company_journal_import(company_id: str, payload: JournalCommitRequest,
                                        user: dict = Depends(require_admin)):
    result = await commit_journal_import(db, company_id, user, payload.import_id)
    ev = {"completed": "journal.completed", "completed_with_warnings": "journal.completed",
          "failed": "journal.failed"}.get(result.get("status"), "journal.completed")
    await log_action(user, "commit", "journal", result.get("id", ""),
                     details=(f"Journal finalisé: {result.get('entry_count')} écriture(s) / "
                              f"{result.get('line_count')} ligne(s)"),
                     company_id=company_id, entity_id=result.get("id"), event_type=ev,
                     metadata={"data_type": "journal",
                               "financial_year_id": result.get("financial_year_id"),
                               "financial_period_id": result.get("financial_period_id"),
                               "entry_count": result.get("entry_count"),
                               "line_count": result.get("line_count"),
                               "controls": result.get("controls")})
    return result


@api.get("/companies/{company_id}/journal-entries")
async def list_company_journal_entries(company_id: str, financial_period_id: Optional[str] = None,
                                        import_id: Optional[str] = None, account_id: Optional[str] = None,
                                        date_from: Optional[str] = None, date_to: Optional[str] = None,
                                        reference: Optional[str] = None,
                                        user: dict = Depends(get_current_user)):
    return await list_journal_entries(db, company_id, user, financial_period_id=financial_period_id,
                                      import_id=import_id, account_id=account_id,
                                      date_from=date_from, date_to=date_to, reference=reference)


@api.get("/companies/{company_id}/journal-entries/aggregate")
async def aggregate_company_journal(company_id: str, financial_period_id: Optional[str] = None,
                                    import_id: Optional[str] = None,
                                    user: dict = Depends(get_current_user)):
    return await aggregate_journal(db, company_id, user, financial_period_id=financial_period_id, import_id=import_id)


@api.get("/companies/{company_id}/journal-entries/{entry_id}")
async def get_company_journal_entry(company_id: str, entry_id: str, user: dict = Depends(get_current_user)):
    return await get_journal_entry(db, company_id, entry_id, user)


# ---------------------------------------------------------------------------
# P2.8 — Legacy compatibility bridge (READ-ONLY). Company-scoped source flag,
# default legacy, reversible, admin-only change. No writes to legacy collections.
# ---------------------------------------------------------------------------
@api.get("/companies/{company_id}/financial-source/status")
async def get_company_financial_source_status(company_id: str, financial_period_id: Optional[str] = None,
                                               user: dict = Depends(get_current_user)):
    return await financial_source_status(db, company_id, user, financial_period_id=financial_period_id)


@api.put("/companies/{company_id}/financial-source")
async def set_company_financial_source(company_id: str, payload: FinancialSourceUpdate,
                                       user: dict = Depends(require_admin)):
    result = await set_financial_source(db, company_id, user, payload.source)
    await log_action(user, "update", "financial_source", company_id,
                     details=f"Source financière: {result['old_source']} → {result['new_source']}",
                     company_id=company_id, entity_id=company_id, event_type="financial_source.changed",
                     metadata={"old_source": result["old_source"], "new_source": result["new_source"]})
    return result


@api.get("/companies/{company_id}/compat/accounts")
async def compat_company_accounts(company_id: str, active_only: bool = False,
                                  user: dict = Depends(get_current_user)):
    return await compat_accounts(db, company_id, user, active_only=active_only)


@api.get("/companies/{company_id}/compat/trial-balance")
async def compat_company_trial_balance(company_id: str, financial_period_id: Optional[str] = None,
                                       user: dict = Depends(get_current_user)):
    return await compat_trial_balance(db, company_id, user, financial_period_id)


@api.get("/companies/{company_id}/compat/journal")
async def compat_company_journal(company_id: str, financial_period_id: Optional[str] = None,
                                 user: dict = Depends(get_current_user)):
    return await compat_journal(db, company_id, user, financial_period_id)


# ---------------------------------------------------------------------------
# P2.9 — Read-only reconciliation (diagnostic). Zero writes. Legacy BV read only
# when an explicit legacy_period_key + column mapping are supplied (no guessing).
# ---------------------------------------------------------------------------
def _legacy_cols(period_debit_col, period_credit_col, ytd_debit_col, ytd_credit_col):
    vals = {"period_debit": period_debit_col, "period_credit": period_credit_col,
            "ytd_debit": ytd_debit_col, "ytd_credit": ytd_credit_col}
    return vals if all(vals.get(k) for k in _LEGACY_COL_KEYS) else None


@api.get("/companies/{company_id}/reconciliation/accounts")
async def reconciliation_accounts(company_id: str, legacy_period_key: Optional[str] = None,
                                  user: dict = Depends(get_current_user)):
    return await reconcile_accounts(db, company_id, user, legacy_period_key=legacy_period_key)


@api.get("/companies/{company_id}/reconciliation/trial-balance")
async def reconciliation_trial_balance(company_id: str, financial_period_id: Optional[str] = None,
                                       normalized_import_id: Optional[str] = None,
                                       tolerance: float = 0.01, legacy_period_key: Optional[str] = None,
                                       period_debit_col: Optional[str] = None, period_credit_col: Optional[str] = None,
                                       ytd_debit_col: Optional[str] = None, ytd_credit_col: Optional[str] = None,
                                       user: dict = Depends(get_current_user)):
    return await reconcile_trial_balance(db, company_id, user, financial_period_id,
                                         normalized_import_id=normalized_import_id, tolerance=tolerance,
                                         legacy_period_key=legacy_period_key,
                                         legacy_cols=_legacy_cols(period_debit_col, period_credit_col,
                                                                  ytd_debit_col, ytd_credit_col))


@api.get("/companies/{company_id}/reconciliation/journal-vs-trial-balance")
async def reconciliation_journal_vs_tb(company_id: str, financial_period_id: Optional[str] = None,
                                       normalized_import_id: Optional[str] = None,
                                       tolerance: float = 0.01, ytd: bool = False,
                                       user: dict = Depends(get_current_user)):
    return await reconcile_journal_vs_tb(db, company_id, user, financial_period_id,
                                         normalized_import_id=normalized_import_id, tolerance=tolerance, ytd=ytd)


@api.get("/companies/{company_id}/reconciliation/status")
async def reconciliation_overall_status(company_id: str, financial_period_id: Optional[str] = None,
                                        normalized_import_id: Optional[str] = None, tolerance: float = 0.01,
                                        legacy_period_key: Optional[str] = None,
                                        period_debit_col: Optional[str] = None, period_credit_col: Optional[str] = None,
                                        ytd_debit_col: Optional[str] = None, ytd_credit_col: Optional[str] = None,
                                        user: dict = Depends(get_current_user)):
    return await reconciliation_status(db, company_id, user, financial_period_id,
                                       normalized_import_id=normalized_import_id, tolerance=tolerance,
                                       legacy_period_key=legacy_period_key,
                                       legacy_cols=_legacy_cols(period_debit_col, period_credit_col,
                                                                ytd_debit_col, ytd_credit_col))


# ---------------------------------------------------------------------------
# P2.10 — Phase 2 sign-off (validation evidence). Consumes REAL P2.9 output.
# Create/finalize = workspace admin only; reads = authorized company members.
# NO cutover here (readiness only); never mutates financial_data_source or
# legacy financial collections. Finalized sign-offs are audit evidence.
# ---------------------------------------------------------------------------
class Phase2SignoffCreate(BaseModel):
    financial_period_id: str
    decision: str
    conditions: Optional[List[str]] = None
    notes: Optional[str] = None
    normalized_import_id: Optional[str] = None
    tolerance: float = 0.01
    legacy_period_key: Optional[str] = None
    period_debit_col: Optional[str] = None
    period_credit_col: Optional[str] = None
    ytd_debit_col: Optional[str] = None
    ytd_credit_col: Optional[str] = None


@api.post("/companies/{company_id}/phase2-signoffs")
async def create_company_phase2_signoff(company_id: str, payload: Phase2SignoffCreate,
                                        user: dict = Depends(get_current_user)):
    record = await create_signoff(
        db, company_id, user, financial_period_id=payload.financial_period_id,
        decision=payload.decision, conditions=payload.conditions, notes=payload.notes,
        normalized_import_id=payload.normalized_import_id, tolerance=payload.tolerance,
        legacy_period_key=payload.legacy_period_key,
        legacy_cols=_legacy_cols(payload.period_debit_col, payload.period_credit_col,
                                 payload.ytd_debit_col, payload.ytd_credit_col))
    await log_action(user, "create", "phase2_signoff", record.get("id", ""),
                     details=f"Sign-off Phase 2 — décision {record.get('decision')}",
                     company_id=company_id, entity_id=record.get("id"),
                     event_type=f"phase2_signoff.{record.get('decision')}",
                     metadata={"financial_period_id": payload.financial_period_id,
                               "normalized_import_id": record.get("normalized_import_id"),
                               "decision": record.get("decision"),
                               "cutover_ready": record.get("cutover_ready")})
    return record


@api.get("/companies/{company_id}/phase2-signoffs")
async def list_company_phase2_signoffs(company_id: str, financial_period_id: Optional[str] = None,
                                       user: dict = Depends(get_current_user)):
    return await list_signoffs(db, company_id, user, financial_period_id=financial_period_id)


@api.get("/companies/{company_id}/phase2-signoff-status")
async def company_phase2_signoff_status(company_id: str, financial_period_id: Optional[str] = None,
                                        user: dict = Depends(get_current_user)):
    return await signoff_status(db, company_id, user, financial_period_id)


@api.get("/companies/{company_id}/phase2-signoffs/{signoff_id}")
async def get_company_phase2_signoff(company_id: str, signoff_id: str,
                                     user: dict = Depends(get_current_user)):
    return await get_signoff(db, company_id, user, signoff_id)


# ---------------------------------------------------------------------------
# P3.1 — Reporting semantic layer (DESIGN-approved). SYSTEM referential
# (financial_concepts / jurisdiction_profiles / system templates / i18n) is
# platform-managed & global; client mappings + custom templates are tenant
# scoped. No calculation engine here; no report_runs yet (P3.4). Never mutates
# Phase 2 collections or legacy acct_*/qc9434_*.
# ---------------------------------------------------------------------------
class ConceptDeprecate(BaseModel):
    replaced_by_concept_id: Optional[str] = None


class MappingReject(BaseModel):
    notes: Optional[str] = None


# ---- Financial concepts (system-managed) ----
@api.get("/financial-concepts")
async def list_financial_concepts(statement_type: Optional[str] = None, include_deprecated: bool = False,
                                  user: dict = Depends(get_current_user)):
    return await list_concepts(db, user, statement_type=statement_type, include_deprecated=include_deprecated)


@api.get("/financial-concepts/{concept_id}")
async def get_financial_concept(concept_id: str, user: dict = Depends(get_current_user)):
    return await get_concept(db, user, concept_id)


@api.post("/financial-concepts")
async def create_financial_concept(payload: ConceptCreate, user: dict = Depends(get_current_user)):
    record = await create_concept(db, user, payload)
    await log_action(user, "create", "financial_concept", record.get("concept_code", ""),
                     entity_id=record.get("id"), event_type="financial_concept.created")
    return record


@api.patch("/financial-concepts/{concept_id}")
async def update_financial_concept(concept_id: str, payload: ConceptUpdate,
                                   user: dict = Depends(get_current_user)):
    return await update_concept(db, user, concept_id, payload)


@api.post("/financial-concepts/{concept_id}/deprecate")
async def deprecate_financial_concept(concept_id: str, payload: ConceptDeprecate,
                                      user: dict = Depends(get_current_user)):
    record = await deprecate_concept(db, user, concept_id, payload.replaced_by_concept_id)
    await log_action(user, "deprecate", "financial_concept", record.get("concept_code", ""),
                     entity_id=record.get("id"), event_type="financial_concept.deprecated")
    return record


# ---- i18n labels (system-managed) ----
@api.post("/financial-i18n/labels")
async def upsert_i18n_label(payload: LabelUpsert, user: dict = Depends(get_current_user)):
    return await set_label(db, user, payload)


@api.get("/financial-i18n/labels")
async def get_i18n_labels(entity_type: str, entity_id: str, user: dict = Depends(get_current_user)):
    return await get_labels(db, user, entity_type, entity_id)


# ---- Jurisdiction profiles (system-managed) ----
@api.get("/jurisdiction-profiles")
async def list_jurisdictions(user: dict = Depends(get_current_user)):
    return await list_jurisdiction_profiles(db, user)


@api.get("/jurisdiction-profiles/{jurisdiction_code}")
async def get_jurisdiction(jurisdiction_code: str, user: dict = Depends(get_current_user)):
    return await get_jurisdiction_profile(db, user, jurisdiction_code)


@api.post("/jurisdiction-profiles")
async def create_jurisdiction(payload: JurisdictionProfileCreate, user: dict = Depends(get_current_user)):
    return await create_jurisdiction_profile(db, user, payload)


# ---- Account mappings (client-scoped) ----
@api.get("/companies/{company_id}/account-mappings")
async def list_company_account_mappings(company_id: str, status: Optional[str] = None,
                                         account_id: Optional[str] = None,
                                         financial_concept_id: Optional[str] = None,
                                         source: Optional[str] = None,
                                         effective_period_id: Optional[str] = None,
                                         include_superseded: bool = False,
                                         user: dict = Depends(get_current_user)):
    return await list_mappings(db, company_id, user, status=status, account_id=account_id,
                               financial_concept_id=financial_concept_id, source=source,
                               effective_period_id=effective_period_id,
                               include_superseded=include_superseded)


@api.get("/companies/{company_id}/mapping-coverage")
async def company_mapping_coverage(company_id: str, financial_period_id: Optional[str] = None,
                                   user: dict = Depends(get_current_user)):
    return await mapping_coverage(db, company_id, user, financial_period_id=financial_period_id)


@api.get("/companies/{company_id}/mapping-readiness")
async def company_mapping_readiness(company_id: str, financial_period_id: str,
                                    template_code: Optional[str] = None,
                                    user: dict = Depends(get_current_user)):
    return await mapping_readiness(db, company_id, user, financial_period_id, template_code=template_code)


@api.get("/companies/{company_id}/account-mappings/{mapping_id}")
async def get_company_account_mapping(company_id: str, mapping_id: str,
                                      user: dict = Depends(get_current_user)):
    return await get_mapping(db, company_id, user, mapping_id)


async def _log_mapping(user, company_id, record, event):
    await log_action(user, event.split(".")[-1], "account_mapping", record.get("id", ""),
                     company_id=company_id, entity_id=record.get("id"), event_type=event,
                     metadata={"account_id": record.get("account_id"),
                               "financial_concept_id": record.get("financial_concept_id"),
                               "effective_from_period_id": record.get("effective_from_period_id"),
                               "effective_to_period_id": record.get("effective_to_period_id"),
                               "superseded_ids": record.get("superseded_ids", [])})


@api.post("/companies/{company_id}/account-mappings")
async def create_company_account_mapping(company_id: str, payload: MappingCreate,
                                         user: dict = Depends(get_current_user)):
    record = await create_mapping(db, company_id, user, payload)
    await _log_mapping(user, company_id, record, f"account_mapping.{record.get('status')}")
    if record.get("superseded_ids"):
        await _log_mapping(user, company_id, record, "account_mapping.superseded")
    return record


@api.patch("/companies/{company_id}/account-mappings/{mapping_id}")
async def patch_company_account_mapping(company_id: str, mapping_id: str, payload: MappingUpdate,
                                        user: dict = Depends(get_current_user)):
    return await update_mapping(db, company_id, user, mapping_id, payload)


@api.post("/companies/{company_id}/account-mappings/{mapping_id}/confirm")
async def confirm_company_account_mapping(company_id: str, mapping_id: str,
                                          user: dict = Depends(get_current_user)):
    record = await confirm_mapping(db, company_id, user, mapping_id)
    await _log_mapping(user, company_id, record, "account_mapping.confirmed")
    if record.get("superseded_ids"):
        await _log_mapping(user, company_id, record, "account_mapping.superseded")
    return record


@api.post("/companies/{company_id}/account-mappings/{mapping_id}/reject")
async def reject_company_account_mapping(company_id: str, mapping_id: str, payload: MappingReject,
                                         user: dict = Depends(get_current_user)):
    record = await reject_mapping(db, company_id, user, mapping_id, notes=payload.notes)
    await log_action(user, "reject", "account_mapping", mapping_id, company_id=company_id,
                     entity_id=mapping_id, event_type="account_mapping.rejected")
    return record


@api.post("/companies/{company_id}/account-mappings/bulk-confirm")
async def bulk_confirm_company_account_mappings(company_id: str, payload: BulkConfirm,
                                                user: dict = Depends(get_current_user)):
    result = await bulk_confirm(db, company_id, user, payload)
    if not payload.dry_run:
        await log_action(user, "bulk_confirm", "account_mapping", company_id, company_id=company_id,
                         event_type="account_mapping.bulk_confirmed",
                         metadata={"summary": result.get("summary")})
    return result


@api.post("/companies/{company_id}/account-mappings/import/preview")
async def preview_company_mapping_import(company_id: str, file: UploadFile = File(...),
                                         user: dict = Depends(get_current_user)):
    content = await file.read()
    rows = parse_rows(content, file.filename)
    return await import_preview(db, company_id, user, rows)


@api.post("/companies/{company_id}/account-mappings/import/commit")
async def commit_company_mapping_import(company_id: str, as_confirmed: bool = False,
                                        file: UploadFile = File(...),
                                        user: dict = Depends(get_current_user)):
    content = await file.read()
    rows = parse_rows(content, file.filename)
    result = await import_commit(db, company_id, user, rows, as_confirmed=as_confirmed)
    await log_action(user, "import", "account_mapping", company_id, company_id=company_id,
                     event_type="account_mapping.imported",
                     metadata={"summary": result.get("summary"), "imported_status": result.get("imported_status")})
    return result


# ---- Reporting templates (system + custom skeleton) ----
@api.get("/reporting-templates")
async def list_reporting_templates(jurisdiction: Optional[str] = None, statement_type: Optional[str] = None,
                                   user: dict = Depends(get_current_user)):
    return await list_system_templates(db, user, jurisdiction=jurisdiction, statement_type=statement_type)


@api.post("/reporting-templates")
async def create_reporting_template(payload: TemplateCreate, company_id: Optional[str] = None,
                                    user: dict = Depends(get_current_user)):
    record = await create_template(db, user, payload, company_id=company_id)
    await log_action(user, "create", "reporting_template", record.get("template_code", ""),
                     company_id=company_id, entity_id=record.get("id"),
                     event_type="reporting_template.created")
    return record


@api.get("/reporting-templates/{template_id}")
async def get_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    return await get_template(db, user, template_id)


@api.post("/reporting-templates/{template_id}/lines")
async def add_reporting_template_line(template_id: str, payload: TemplateLineCreate,
                                      user: dict = Depends(get_current_user)):
    return await add_template_line(db, user, template_id, payload)


@api.post("/reporting-templates/{template_id}/publish")
async def publish_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    record = await publish_template(db, user, template_id)
    await log_action(user, "publish", "reporting_template", record.get("template_code", ""),
                     entity_id=record.get("id"), event_type="reporting_template.published")
    return record


@api.post("/reporting-templates/{template_id}/archive")
async def archive_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    return await archive_template(db, user, template_id)


@api.post("/reporting-templates/{template_id}/new-version")
async def version_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    return await new_template_version(db, user, template_id)


@api.get("/companies/{company_id}/reporting-templates")
async def list_company_reporting_templates(company_id: str, statement_type: Optional[str] = None,
                                           user: dict = Depends(get_current_user)):
    return await list_company_templates(db, company_id, user, statement_type=statement_type)


# ---------------------------------------------------------------------------
# P3.5 — Custom reporting-template governance (create / derive / edit / publish
# / upload / defaults). Reuses the P3.1 schema and P3.4 engine. Never mutates a
# published version; publishing runs full structural validation (fail closed).
# ---------------------------------------------------------------------------
@api.post("/reporting-templates/custom")
async def create_custom_reporting_template(payload: CustomTemplateCreate,
                                           user: dict = Depends(get_current_user)):
    rec = await create_custom_template(db, user, payload)
    await log_action(user, "create", "reporting_template", rec.get("template_code", ""),
                     company_id=rec.get("company_id"), entity_id=rec.get("id"),
                     event_type="reporting_template.created",
                     metadata={"scope": rec.get("scope"), "statement_type": rec.get("statement_type"),
                               "version": rec.get("version")})
    return rec


@api.post("/reporting-templates/derive")
async def derive_reporting_template(payload: DeriveRequest, user: dict = Depends(get_current_user)):
    rec = await derive_template(db, user, payload)
    await log_action(user, "derive", "reporting_template", rec.get("template_code", ""),
                     company_id=rec.get("company_id"), entity_id=rec.get("id"),
                     event_type="reporting_template.derived",
                     metadata={"scope": rec.get("scope"), "statement_type": rec.get("statement_type"),
                               "based_on_template_id": rec.get("based_on_template_id"),
                               "based_on_template_version": rec.get("based_on_template_version")})
    return rec


@api.post("/reporting-templates/{template_id}/custom-lines")
async def add_custom_line(template_id: str, payload: TemplateLineUpsert,
                          user: dict = Depends(get_current_user)):
    rec = await ct_add_line(db, user, template_id, payload)
    await log_action(user, "update", "reporting_template", template_id, entity_id=template_id,
                     event_type="reporting_template.updated", metadata={"line_added": rec.get("line_code")})
    return rec


@api.patch("/reporting-templates/{template_id}/custom-lines/{line_id}")
async def update_custom_line(template_id: str, line_id: str, payload: TemplateLineUpsert,
                             user: dict = Depends(get_current_user)):
    rec = await ct_update_line(db, user, template_id, line_id, payload)
    await log_action(user, "update", "reporting_template", template_id, entity_id=template_id,
                     event_type="reporting_template.updated", metadata={"line_updated": line_id})
    return rec


@api.delete("/reporting-templates/{template_id}/custom-lines/{line_id}")
async def delete_custom_line(template_id: str, line_id: str,
                             user: dict = Depends(get_current_user)):
    rec = await ct_remove_line(db, user, template_id, line_id)
    await log_action(user, "update", "reporting_template", template_id, entity_id=template_id,
                     event_type="reporting_template.updated", metadata={"line_removed": line_id})
    return rec


@api.post("/reporting-templates/{template_id}/reorder-lines")
async def reorder_custom_lines(template_id: str, payload: ReorderRequest,
                               user: dict = Depends(get_current_user)):
    rec = await ct_reorder_lines(db, user, template_id, payload)
    await log_action(user, "update", "reporting_template", template_id, entity_id=template_id,
                     event_type="reporting_template.updated", metadata={"reordered": rec.get("reordered")})
    return rec


@api.get("/reporting-templates/{template_id}/validate")
async def validate_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    return await ct_validate_template(db, user, template_id)


@api.post("/reporting-templates/{template_id}/publish-custom")
async def publish_custom_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    rec = await ct_publish_template(db, user, template_id)
    await log_action(user, "publish", "reporting_template", rec.get("template_code", ""),
                     company_id=rec.get("company_id"), entity_id=rec.get("id"),
                     event_type="reporting_template.published",
                     metadata={"scope": rec.get("scope"), "version": rec.get("version"),
                               "statement_type": rec.get("statement_type")})
    return rec


@api.post("/reporting-templates/{template_id}/new-custom-version")
async def new_custom_reporting_version(template_id: str, user: dict = Depends(get_current_user)):
    rec = await new_custom_version(db, user, template_id)
    await log_action(user, "derive", "reporting_template", rec.get("template_code", ""),
                     company_id=rec.get("company_id"), entity_id=rec.get("id"),
                     event_type="reporting_template.derived",
                     metadata={"scope": rec.get("scope"), "version": rec.get("version"),
                               "based_on_template_id": rec.get("based_on_template_id")})
    return rec


@api.post("/reporting-templates/{template_id}/archive-custom")
async def archive_custom_reporting_template(template_id: str, user: dict = Depends(get_current_user)):
    rec = await ct_archive_template(db, user, template_id)
    await log_action(user, "archive", "reporting_template", rec.get("template_code", ""),
                     company_id=rec.get("company_id"), entity_id=rec.get("id"),
                     event_type="reporting_template.archived",
                     metadata={"scope": rec.get("scope"), "version": rec.get("version")})
    return rec


@api.get("/companies/{company_id}/available-reporting-templates")
async def list_company_available_templates(company_id: str, statement_type: Optional[str] = None,
                                           user: dict = Depends(get_current_user)):
    return await list_available_templates(db, company_id, user, statement_type=statement_type)


@api.post("/companies/{company_id}/reporting-templates/upload/preview")
async def preview_reporting_template_upload(company_id: str, statement_type: str = Form(...),
                                            template_code: str = Form(...), name: str = Form(...),
                                            scope: str = Form("company"),
                                            jurisdiction: Optional[str] = Form(None),
                                            file: UploadFile = File(...),
                                            user: dict = Depends(get_current_user)):
    content = await file.read()
    rows = parse_rows(content, file.filename)
    meta = UploadCommit(template_code=template_code, statement_type=statement_type, scope=scope,
                        name=name, jurisdiction=jurisdiction, company_id=company_id, rows=rows)
    return await ct_upload_preview(db, user, meta)


@api.post("/companies/{company_id}/reporting-templates/upload/commit")
async def commit_reporting_template_upload(company_id: str, statement_type: str = Form(...),
                                           template_code: str = Form(...), name: str = Form(...),
                                           scope: str = Form("company"),
                                           jurisdiction: Optional[str] = Form(None),
                                           file: UploadFile = File(...),
                                           user: dict = Depends(get_current_user)):
    content = await file.read()
    rows = parse_rows(content, file.filename)
    meta = UploadCommit(template_code=template_code, statement_type=statement_type, scope=scope,
                        name=name, jurisdiction=jurisdiction, company_id=company_id, rows=rows)
    rec = await ct_upload_commit(db, user, meta)
    await log_action(user, "import", "reporting_template", rec.get("template_code", ""),
                     company_id=company_id, entity_id=rec.get("id"),
                     event_type="reporting_template.uploaded",
                     metadata={"scope": rec.get("scope"), "line_count": rec.get("line_count"),
                               "idempotent": rec.get("idempotent", False)})
    return rec


@api.get("/companies/{company_id}/reporting-template-defaults")
async def get_company_template_defaults(company_id: str, user: dict = Depends(get_current_user)):
    return await get_default_templates(db, user, company_id)


@api.put("/companies/{company_id}/reporting-template-defaults")
async def set_company_template_default(company_id: str, payload: DefaultAssignment,
                                       user: dict = Depends(get_current_user)):
    rec = await set_default_template(db, user, payload, company_id)
    await log_action(user, "update", "reporting_template", rec.get("template_code", ""),
                     company_id=company_id, entity_id=rec.get("template_id"),
                     event_type="reporting_template.default_changed",
                     metadata={"scope": rec.get("scope"), "statement_type": rec.get("statement_type")})
    return rec


# ---------------------------------------------------------------------------
# P3.6 — Cash Flow (indirect). Reuses TB + concepts + mappings; report_runs with
# statement_type=cash_flow. preview (no run) / generate (immutable run).
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/reports/cash-flow/preview")
async def preview_company_cash_flow(company_id: str, payload: CashFlowRequest,
                                    user: dict = Depends(get_current_user)):
    return await preview_cash_flow(
        db, company_id, user, payload.financial_period_id, template_id=payload.template_id,
        template_code=payload.template_code, locale=payload.locale,
        normalized_import_id=payload.normalized_import_id)


@api.post("/companies/{company_id}/reports/cash-flow/generate")
async def generate_company_cash_flow(company_id: str, payload: CashFlowRequest,
                                     user: dict = Depends(get_current_user)):
    rec = await generate_cash_flow(
        db, company_id, user, payload.financial_period_id, template_id=payload.template_id,
        template_code=payload.template_code, locale=payload.locale,
        normalized_import_id=payload.normalized_import_id)
    await log_action(user, "generate", "report_run", rec.get("template_code", ""),
                     company_id=company_id, entity_id=rec.get("id"),
                     event_type="report.generated",
                     metadata={"statement_type": "cash_flow", "template_version": rec.get("template_version"),
                               "status": rec.get("diagnostics", {}).get("status")})
    return rec


# ---------------------------------------------------------------------------
# P3.7 — Comparatives & Management Reporting. Recompute via P3.4/P3.6 per
# comparison context; objective variances; immutable runs on generate.
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/reports/comparative/preview")
async def preview_comparative(company_id: str, payload: ComparativeRequest,
                              user: dict = Depends(get_current_user)):
    if payload.statement_type == "cash_flow":
        return await preview_cash_flow_comparative(
            db, company_id, user, financial_period_id=payload.financial_period_id,
            mode=payload.comparison_mode, template_id=payload.template_id,
            template_code=payload.template_code, locale=payload.locale)
    return await preview_statement_comparative(
        db, company_id, user, statement_type=payload.statement_type,
        financial_period_id=payload.financial_period_id, mode=payload.comparison_mode,
        template_id=payload.template_id, template_code=payload.template_code, locale=payload.locale,
        measure=payload.measure, normalized_import_id=payload.normalized_import_id)


@api.post("/companies/{company_id}/reports/comparative/generate")
async def generate_comparative(company_id: str, payload: ComparativeRequest,
                               user: dict = Depends(get_current_user)):
    if payload.statement_type == "cash_flow":
        rec = await generate_cash_flow_comparative(
            db, company_id, user, financial_period_id=payload.financial_period_id,
            mode=payload.comparison_mode, template_id=payload.template_id,
            template_code=payload.template_code, locale=payload.locale)
    else:
        rec = await generate_statement_comparative(
            db, company_id, user, statement_type=payload.statement_type,
            financial_period_id=payload.financial_period_id, mode=payload.comparison_mode,
            template_id=payload.template_id, template_code=payload.template_code, locale=payload.locale,
            measure=payload.measure, normalized_import_id=payload.normalized_import_id)
    await log_action(user, "generate", "report_run", rec.get("template_code", "") or rec.get("report_kind", ""),
                     company_id=company_id, entity_id=rec.get("id"), event_type="report.generated",
                     metadata={"report_kind": rec.get("report_kind"), "comparison_mode": payload.comparison_mode,
                               "template_version": rec.get("template_version")})
    return rec


@api.post("/companies/{company_id}/reports/management/preview")
async def preview_management(company_id: str, payload: ManagementReportRequest,
                             user: dict = Depends(get_current_user)):
    return await preview_management_report(
        db, company_id, user, financial_period_id=payload.financial_period_id,
        mode=payload.comparison_mode, sections=payload.sections, locale=payload.locale)


@api.post("/companies/{company_id}/reports/management/generate")
async def generate_management(company_id: str, payload: ManagementReportRequest,
                              user: dict = Depends(get_current_user)):
    rec = await generate_management_report(
        db, company_id, user, financial_period_id=payload.financial_period_id,
        mode=payload.comparison_mode, sections=payload.sections, locale=payload.locale)
    await log_action(user, "generate", "report_run", rec.get("report_kind", ""),
                     company_id=company_id, entity_id=rec.get("id"), event_type="report.generated",
                     metadata={"report_kind": "management", "comparison_mode": payload.comparison_mode})
    return rec


@api.post("/system/reporting-seed")
async def system_reporting_seed(user: dict = Depends(get_current_user)):
    """P3.2 — platform-management seed of system reference data (idempotent)."""
    report = await run_system_seed_as(db, user)
    report["cash_flow_templates"] = await seed_cash_flow_templates(db)
    await log_action(user, "seed", "system_reporting", report.get("seed_version", ""),
                     event_type="system_reporting.seeded",
                     metadata={"totals": report.get("totals"), "counts": report.get("counts")})
    return report


# ---------------------------------------------------------------------------
# P3.4 — Core Reporting Engine (P&L + Balance Sheet) + immutable report_runs.
# Preview = read (company members); generate/finalize = workspace admin.
# ---------------------------------------------------------------------------
@api.post("/companies/{company_id}/reports/preview")
async def preview_company_report(company_id: str, payload: ReportRequest,
                                 user: dict = Depends(get_current_user)):
    return await preview_report(db, company_id, user, payload)


@api.post("/companies/{company_id}/reports")
async def generate_company_report(company_id: str, payload: ReportRequest,
                                  user: dict = Depends(get_current_user)):
    try:
        run = await generate_report(db, company_id, user, payload)
    except HTTPException as e:
        await log_action(user, "generate_failed", "report", company_id, company_id=company_id,
                         event_type="report.generation_failed",
                         metadata={"statement_type": payload.statement_type,
                                   "financial_period_id": payload.financial_period_id,
                                   "reason": str(e.detail)[:300]})
        raise
    await log_action(user, "generate", "report", run.get("id", ""), company_id=company_id,
                     entity_id=run.get("id"), event_type="report.generated",
                     metadata={"statement_type": run.get("statement_type"),
                               "financial_period_id": run.get("financial_period_id"),
                               "template_id": run.get("template_id"),
                               "template_version": run.get("template_version"),
                               "trial_balance_import_id": run.get("trial_balance_import_id")})
    return run


@api.get("/companies/{company_id}/reports")
async def list_company_reports(company_id: str, statement_type: Optional[str] = None,
                               financial_period_id: Optional[str] = None,
                               template_code: Optional[str] = None,
                               user: dict = Depends(get_current_user)):
    return await list_reports(db, company_id, user, statement_type=statement_type,
                              financial_period_id=financial_period_id, template_code=template_code)


@api.get("/companies/{company_id}/reports/{run_id}")
async def get_company_report(company_id: str, run_id: str, user: dict = Depends(get_current_user)):
    return await get_report(db, company_id, user, run_id)


# ---------------------------------------------------------------------------
# P1.12 — Multi-level identity: workspace members & company members
# ---------------------------------------------------------------------------
async def _resolve_or_create_user(email: str, name: Optional[str], password: Optional[str], actor: dict) -> str:
    """Return a global user_id, reusing the identity for a normalized email."""
    norm = (email or "").strip().lower()
    if not norm:
        raise HTTPException(status_code=422, detail="Email requis")
    existing = await db.users.find_one({"email": norm})
    if existing:
        return str(existing["_id"])
    if not password:
        raise HTTPException(status_code=422, detail="Mot de passe requis pour un nouvel utilisateur")
    doc = {"email": norm, "name": name or norm, "password_hash": hash_password(password),
           "role": "user", "status": "active", "platform_role": None,
           "workspace_id": actor.get("workspace_id"),
           "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    return str(res.inserted_id)


@api.get("/workspace/members")
async def list_ws_members(user: dict = Depends(get_current_user)):
    ws = await require_workspace_admin(db, user)
    return await list_workspace_members(db, ws)


@api.post("/workspace/members", status_code=201)
async def create_ws_member(payload: WorkspaceMemberCreate, user: dict = Depends(get_current_user)):
    ws = await require_workspace_admin(db, user)
    uid = await _resolve_or_create_user(payload.email, payload.name, payload.password, user)
    m = await upsert_workspace_membership(db, ws, uid, payload.role, user.get("id"))
    await log_action(user, "create", "workspace_member", payload.email, details=f"Membre workspace {payload.role}",
                     entity_id=m.get("id"), event_type="workspace_member.created")
    return m


@api.patch("/workspace/members/{membership_id}")
async def patch_ws_member(membership_id: str, payload: WorkspaceMemberUpdate, user: dict = Depends(get_current_user)):
    ws = await require_workspace_admin(db, user)
    m = await update_workspace_membership(db, ws, membership_id, payload, user.get("id"))
    evt = "workspace_member.deactivated" if payload.status == "inactive" else "workspace_member.updated"
    await log_action(user, "update", "workspace_member", m.get("email", ""), details=f"Membre workspace {membership_id}",
                     entity_id=membership_id, event_type=evt)
    return m


@api.get("/companies/{company_id}/members")
async def list_cmp_members(company_id: str, user: dict = Depends(get_current_user)):
    company = await require_company_local_admin(db, company_id, user)
    only_local = user.get("role") != "admin"  # company-local admin sees only company_user
    return await list_company_members(db, company.get("workspace_id"), company_id, only_company_user=only_local)


@api.post("/companies/{company_id}/members", status_code=201)
async def create_cmp_member(company_id: str, payload: CompanyMemberCreate, user: dict = Depends(get_current_user)):
    company = await require_company_local_admin(db, company_id, user)
    validate_combo(payload.membership_type, payload.role)
    # Only workspace admins may assign fiduciary staff; company-local admins are
    # restricted to company_user memberships of their own company.
    if payload.membership_type == "workspace_staff" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Seul un admin workspace peut affecter le personnel fiduciaire")
    uid = await _resolve_or_create_user(payload.email, payload.name, payload.password, user)
    m = await create_company_membership(db, company.get("workspace_id"), company_id, uid,
                                        payload.membership_type, payload.role, user.get("id"))
    evt = "company_admin.user_created" if user.get("role") != "admin" else "company_member.created"
    await log_action(user, "create", "company_member", payload.email,
                     details=f"Membre société {payload.membership_type}/{payload.role}",
                     company_id=company_id, entity_id=m.get("id"), event_type=evt)
    return m


@api.patch("/companies/{company_id}/members/{membership_id}")
async def patch_cmp_member(company_id: str, membership_id: str, payload: CompanyMemberUpdate, user: dict = Depends(get_current_user)):
    company = await require_company_local_admin(db, company_id, user)
    restrict = user.get("role") != "admin"
    m = await update_company_membership(db, company.get("workspace_id"), company_id, membership_id, payload, user.get("id"), restrict_to_company_user=restrict)
    if payload.status == "inactive":
        evt = "company_member.deactivated"
    elif restrict:
        evt = "company_admin.user_updated"
    else:
        evt = "company_member.updated"
    await log_action(user, "update", "company_member", m.get("email", ""), details=f"Membre société {membership_id}",
                     company_id=company_id, entity_id=membership_id, event_type=evt)
    return m



@api.get("/notifications")
async def notifications(user: dict = Depends(get_current_user)):
    """Alertes vivantes pour la cloche : factures échues / à échoir (entité 9434)."""
    from datetime import date, timedelta
    today = date.today()
    today_s = today.isoformat()
    soon_s = (today + timedelta(days=7)).isoformat()
    items = []
    try:
        cid = await _company_id("qc9434")
        invs = await db.qc9434_invoices.find({"type": "invoice", "status": "open", "company_id": cid}).to_list(3000)
    except Exception:
        invs = []
    for d in invs:
        bal = round((d.get("total", 0) or 0) - (d.get("paid_amount", 0) or 0) - (d.get("credited_amount", 0) or 0), 2)
        if bal <= 0:
            continue
        due = d.get("due_date")
        if not due:
            continue
        base = {"id": str(d["_id"]), "target": "acct_qc9434",
                "detail": f"{d.get('client_name', '')} · {bal:,.2f} $ · éch. {due}"}
        if due < today_s:
            items.append({**base, "type": "overdue", "severity": "high",
                          "title": f"Facture {d.get('number', '')} échue"})
        elif due <= soon_s:
            items.append({**base, "type": "soon", "severity": "medium",
                          "title": f"Facture {d.get('number', '')} à échoir"})
    items.sort(key=lambda x: 0 if x["type"] == "overdue" else 1)
    overdue = sum(1 for i in items if i["type"] == "overdue")
    return {"count": len(items), "overdue": overdue, "soon": len(items) - overdue, "items": items[:30]}


# ---------------------------------------------------------------------------
# Gestion des utilisateurs (admin uniquement)
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: Literal["admin", "user"] = "user"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["admin", "user"]] = None
    password: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


def _normalized_role(role: str) -> str:
    # P1.7 removes the legacy editor role from the product surface while
    # remaining compatible with rows not yet migrated in Mongo.
    return "user" if role == "editor" else (role or "user")


def _user_public(u, access_count=None):
    payload = {
        "id": str(u["_id"]),
        "email": u["email"],
        "name": u.get("name", ""),
        "role": _normalized_role(u.get("role", "user")),
        "status": u.get("status", "active"),
        "workspace_id": u.get("workspace_id"),
        "created_at": u.get("created_at", ""),
    }
    if access_count is not None:
        payload["access_count"] = access_count
    return payload


@api.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    workspace_id = require_tenant_context(user)
    docs = await db.users.find({"workspace_id": workspace_id}).sort("email", 1).to_list(1000)
    counts = {}
    async for row in db.company_access.aggregate([
        {"$match": {"workspace_id": workspace_id, "active": True}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
    ]):
        counts[str(row.get("_id"))] = row.get("count", 0)
    return [
        _user_public(u, access_count=(None if _normalized_role(u.get("role")) == "admin" else counts.get(str(u["_id"]), 0)))
        for u in docs
    ]


@api.post("/users")
async def create_user(payload: UserCreate, user: dict = Depends(require_admin)):
    workspace_id = require_tenant_context(user)
    email = payload.email.strip().lower()
    # Login is still email-only in the legacy auth route, so email remains
    # globally unique until a future identity-provider migration changes that.
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ce courriel existe déjà")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "email": email,
        "name": payload.name.strip(),
        "password_hash": hash_password(payload.password),
        "role": payload.role,
        "status": "active",
        "workspace_id": workspace_id,
        "created_at": now,
        "created_by": user.get("id"),
    }
    res = await db.users.insert_one(doc)
    await log_action(user, "create", "user", f"{payload.name} ({email})",
                     details=f"Utilisateur créé — rôle {payload.role}",
                     entity_id=str(res.inserted_id), event_type="user.created")
    u = await db.users.find_one({"_id": res.inserted_id})
    return _user_public(u, access_count=0 if payload.role != "admin" else None)


@api.put("/users/{uid}")
async def update_user(uid: str, payload: UserUpdate, user: dict = Depends(require_admin)):
    workspace_id = require_tenant_context(user)
    target = await db.users.find_one({"_id": _oid(uid), "workspace_id": workspace_id})
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    upd = {}
    if payload.name is not None:
        upd["name"] = payload.name.strip()
    if payload.password:
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
        upd["password_hash"] = hash_password(payload.password)
    if payload.role is not None and payload.role != _normalized_role(target.get("role")):
        if _normalized_role(target.get("role")) == "admin" and payload.role != "admin":
            admins = await db.users.count_documents({"workspace_id": workspace_id, "role": "admin", "status": {"$ne": "inactive"}})
            if admins <= 1:
                raise HTTPException(status_code=400, detail="Impossible de rétrograder le dernier administrateur")
        upd["role"] = payload.role
    if payload.status is not None and payload.status != target.get("status", "active"):
        if str(target["_id"]) == user["id"] and payload.status == "inactive":
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")
        if _normalized_role(target.get("role")) == "admin" and payload.status == "inactive":
            admins = await db.users.count_documents({"workspace_id": workspace_id, "role": "admin", "status": {"$ne": "inactive"}})
            if admins <= 1:
                raise HTTPException(status_code=400, detail="Impossible de désactiver le dernier administrateur")
        upd["status"] = payload.status
    if upd:
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        upd["updated_by"] = user.get("id")
        await db.users.update_one({"_id": _oid(uid), "workspace_id": workspace_id}, {"$set": upd})
    await log_action(user, "update", "user", f"{target.get('name')} ({target['email']})",
                     details="Utilisateur modifié", entity_id=uid, event_type="user.updated")
    u = await db.users.find_one({"_id": _oid(uid), "workspace_id": workspace_id})
    count = None if _normalized_role(u.get("role")) == "admin" else await db.company_access.count_documents({"workspace_id": workspace_id, "user_id": uid, "active": True})
    return _user_public(u, access_count=count)


@api.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(require_admin)):
    """P1.7 compatibility route: DELETE now soft-deactivates instead of erasing."""
    workspace_id = require_tenant_context(user)
    target = await db.users.find_one({"_id": _oid(uid), "workspace_id": workspace_id})
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if str(target["_id"]) == user["id"]:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")
    if _normalized_role(target.get("role")) == "admin":
        admins = await db.users.count_documents({"workspace_id": workspace_id, "role": "admin", "status": {"$ne": "inactive"}})
        if admins <= 1:
            raise HTTPException(status_code=400, detail="Impossible de désactiver le dernier administrateur")
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"_id": _oid(uid), "workspace_id": workspace_id}, {"$set": {"status": "inactive", "updated_at": now, "updated_by": user.get("id")}})
    await db.company_access.update_many({"workspace_id": workspace_id, "user_id": uid, "active": True, "access_role": "collaborator"}, {"$set": {"active": False, "updated_at": now, "updated_by": user.get("id")}})
    await log_action(user, "deactivate", "user", f"{target.get('name')} ({target['email']})",
                     details="Utilisateur désactivé", entity_id=uid, event_type="user.deactivated")
    return {"success": True, "status": "inactive"}


@api.get("/users/{uid}/company-access")
async def get_user_company_access(uid: str, user: dict = Depends(require_admin)):
    return await list_user_company_access(db, user, uid)


@api.put("/users/{uid}/company-access")
async def put_user_company_access(uid: str, payload: UserCompanyAccessUpdate, user: dict = Depends(require_admin)):
    result = await replace_user_company_access(db, user, uid, payload)
    await log_action(user, "update", "company_access", uid,
                     details=f"Affectations sociétés mises à jour ({len(payload.assignments)})",
                     entity_id=uid, event_type="company_access.user_replaced",
                     metadata={"assignments": [a.model_dump() for a in payload.assignments]})
    return result

# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
class Department(BaseModel):
    code: str
    description: str
    superviseur: str
    compte_gl: str
    groupe_pl: str
    gl_boni: str = ""
    csst: float = 0.0

@api.get("/departments")
async def list_departments(user: dict = Depends(get_current_user)):
    docs = await db.departments.find().to_list(1000)
    docs.sort(key=lambda d: d["code"])
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

@api.post("/departments")
async def create_department(payload: Department, user: dict = Depends(get_current_user)):
    if await db.departments.find_one({"code": payload.code}):
        raise HTTPException(status_code=400, detail="Ce code existe déjà")
    res = await db.departments.insert_one(payload.model_dump())
    await log_action(user, "Créer", "Département", f"{payload.code} — {payload.description}")
    d = await db.departments.find_one({"_id": res.inserted_id})
    d["id"] = str(d.pop("_id"))
    return d

@api.put("/departments/{dep_id}")
async def update_department(dep_id: str, payload: Department, user: dict = Depends(get_current_user)):
    res = await db.departments.update_one({"_id": _oid(dep_id)}, {"$set": payload.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Département introuvable")
    await log_action(user, "Modifier", "Département", f"{payload.code} — {payload.description}")
    d = await db.departments.find_one({"_id": _oid(dep_id)})
    d["id"] = str(d.pop("_id"))
    return d

@api.delete("/departments/{dep_id}")
async def delete_department(dep_id: str, user: dict = Depends(get_current_user)):
    d = await db.departments.find_one({"_id": _oid(dep_id)})
    res = await db.departments.delete_one({"_id": _oid(dep_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Département introuvable")
    await log_action(user, "Supprimer", "Département", f"{d['code']} — {d['description']}" if d else dep_id)
    return {"success": True}

# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
class EmployeeBase(BaseModel):
    name: str
    department: str
    title: str
    employment_type: Literal["CCQ", "Régulier temps plein", "Régulier temps partiel", "Stagiaire"]
    ccq_category: Literal["Électricien", "Frigoriste", "N/A"]
    current_annual_salary: float
    vacation_rate: float
    sick_personal_days: int
    holiday_days: int
    is_ccq: bool
    prime_type: Literal["Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"]
    prime_garde: bool
    prime_halo: bool
    alloc_securite: bool
    hire_date: str
    birth_date: str
    end_date: Optional[str] = None
    security_class: Optional[str] = None
    supervisor: Optional[str] = None
    active: bool = True
    sex_at_birth: Optional[Literal["Masculin", "Féminin", "Autre", "Préfère ne pas répondre"]] = None

def _active_q(base=None):
    q = dict(base or {})
    q["active"] = {"$ne": False}
    return q

async def _next_number():
    last = await db.employees.find_one(sort=[("employee_number", -1)])
    return (last["employee_number"] + 1) if last else 1

@api.get("/employees")
async def list_employees(q: Optional[str] = None, include_inactive: bool = False, user: dict = Depends(get_current_user)):
    query = {} if include_inactive else {"active": {"$ne": False}}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"department": {"$regex": q, "$options": "i"}},
                        {"title": {"$regex": q, "$options": "i"}}, {"employment_type": {"$regex": q, "$options": "i"}}]
    docs = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

@api.post("/employees")
async def create_employee(payload: EmployeeBase, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin" and await _any_locked():
        raise HTTPException(status_code=403, detail="Un budget est verrouillé. Seul un administrateur peut modifier les employés.")
    if not await db.departments.find_one({"code": payload.department}):
        raise HTTPException(status_code=400, detail=f"Département '{payload.department}' inexistant")
    doc = payload.model_dump()
    doc["employee_number"] = await _next_number()
    res = await db.employees.insert_one(doc)
    await log_action(user, "Créer", "Employé", payload.name)
    c = await db.employees.find_one({"_id": res.inserted_id})
    c["id"] = str(c.pop("_id"))
    return c

@api.put("/employees/{eid}")
async def update_employee(eid: str, payload: EmployeeBase, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin" and await _any_locked():
        raise HTTPException(status_code=403, detail="Un budget est verrouillé. Seul un administrateur peut modifier les employés.")
    if not await db.departments.find_one({"code": payload.department}):
        raise HTTPException(status_code=400, detail=f"Département '{payload.department}' inexistant")
    old = await db.employees.find_one({"_id": _oid(eid)})
    if not old:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    newd = payload.model_dump()
    await db.employees.update_one({"_id": _oid(eid)}, {"$set": newd})
    await log_action(user, "Modifier", "Employé", payload.name, changes=_diff_employee(old, newd))
    u = await db.employees.find_one({"_id": _oid(eid)})
    u["id"] = str(u.pop("_id"))
    return u

@api.delete("/employees/{eid}")
async def delete_employee(eid: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin" and await _any_locked():
        raise HTTPException(status_code=403, detail="Un budget est verrouillé. Seul un administrateur peut supprimer un employé.")
    e = await db.employees.find_one({"_id": _oid(eid)})
    res = await db.employees.delete_one({"_id": _oid(eid)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    await log_action(user, "Supprimer", "Employé", e["name"] if e else eid)
    return {"success": True}

class OverridePayload(BaseModel):
    override: dict

@api.post("/employees/{eid}/budget-preview")
async def budget_preview(eid: str, payload: OverridePayload, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"_id": _oid(eid)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    emp = dict(emp)
    ov = dict(payload.override or {})
    base = ov.pop("base_salary", None)
    yd = dict((emp.get("years") or {}).get(str(year), {}))
    if base is not None:
        yd["base_salary"] = base
    yd[scenario] = ov
    emp.setdefault("years", {})[str(year)] = yd
    return compute_budget([emp], hypo, depts, year=year, scenario=scenario)["lines"][0]

@api.put("/employees/{eid}/budget-override")
async def save_override(eid: str, payload: OverridePayload, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"_id": _oid(eid)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    year = year or await _active_year()
    if user.get("role") != "admin" and await _is_locked(year, scenario):
        raise HTTPException(status_code=403, detail=f"{SCEN_LABEL.get(scenario, scenario)} {year} est verrouillé. Seul un administrateur peut le modifier.")
    ov = dict(payload.override or {})
    base = ov.pop("base_salary", None)
    sets, unsets = {}, {}
    if ov:
        sets[f"years.{year}.{scenario}"] = ov
    else:
        unsets[f"years.{year}.{scenario}"] = ""
    if base is not None:
        sets[f"years.{year}.base_salary"] = base
    upd = {}
    if sets:
        upd["$set"] = sets
    if unsets:
        upd["$unset"] = unsets
    if ov:
        upd["$pull"] = {"inactive_scenarios": f"{int(year)}:{scenario}"}
    if upd:
        await db.employees.update_one({"_id": _oid(eid)}, upd)
    await log_action(user, "Modifier", "Budget", f"Fiche {SCEN_LABEL.get(scenario, scenario)} {year} — {emp['name']}")
    return {"success": True}

class BulkAugPayload(BaseModel):
    ccq_pct: float
    std_pct: float

@api.post("/budget/apply-augmentation")
async def apply_augmentation(payload: BulkAugPayload, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    """Applique une augmentation globale (%) à tous les employés pour l'année + scénario donnés."""
    year = year or await _active_year()
    if scenario not in BUDGET_SCENARIOS:
        raise HTTPException(status_code=400, detail="Scénario invalide")
    if user.get("role") != "admin" and await _is_locked(year, scenario):
        raise HTTPException(status_code=403, detail=f"{SCEN_LABEL.get(scenario, scenario)} {year} est verrouillé. Seul un administrateur peut le modifier.")
    ccq_aug = round(float(payload.ccq_pct) / 100, 6)
    std_aug = round(float(payload.std_pct) / 100, 6)
    employees = await db.employees.find(_active_q()).to_list(2000)
    for e in employees:
        aug = ccq_aug if e.get("is_ccq") else std_aug
        await db.employees.update_one({"_id": e["_id"]}, {"$set": {f"years.{year}.{scenario}.augmentation": aug}})
    if scenario == "ca":
        await db.hypotheses.update_one({"key": _hkey(year)}, {"$set": {"augmentation_ccq": ccq_aug, "augmentation_autres": std_aug}})
    await log_action(user, "Modifier", "Budget", f"Augmentation globale {SCEN_LABEL.get(scenario, scenario)} {year} — CCQ {payload.ccq_pct}% · Standard {payload.std_pct}%")
    return {"success": True, "updated": len(employees), "augmentation_ccq": ccq_aug, "augmentation_autres": std_aug}

# ---------------------------------------------------------------------------
# Hypotheses, années & budget
# ---------------------------------------------------------------------------
DEFAULT_YEAR = 2026
SCEN_LABEL = {"actuel": "Salaires actuels", "ca": "Budget CA", "revue1": "Revue Budgétaire 1", "revue2": "Revue Budgétaire 2"}
BUDGET_SCENARIOS = ["ca", "revue1", "revue2"]

async def _is_locked(year, scenario):
    return await db.locks.find_one({"key": f"{int(year)}:{scenario}", "locked": True}) is not None

async def _year_locked(year):
    return await db.locks.find_one({"key": {"$regex": f"^{int(year)}:"}, "locked": True}) is not None

async def _any_locked():
    return await db.locks.find_one({"locked": True}) is not None

async def _all_scenarios_locked(year):
    for sc in BUDGET_SCENARIOS:
        if not await _is_locked(year, sc):
            return False
    return True

def _hkey(year):
    return f"y{int(year)}"

async def _get_hypo(year):
    doc = await db.hypotheses.find_one({"key": _hkey(year)})
    if not doc:
        base = dict(DEFAULT_HYPOTHESES); base["key"] = _hkey(year); base["year"] = int(year)
        _apply_working_days(base, year)
        await db.hypotheses.insert_one(base)
        doc = await db.hypotheses.find_one({"key": _hkey(year)})
    else:
        patch = {}
        if "security_classes" not in doc:
            patch["security_classes"] = DEFAULT_HYPOTHESES["security_classes"]
        if "csst_max_assurable" not in doc:
            patch["csst_max_assurable"] = DEFAULT_HYPOTHESES["csst_max_assurable"]
        if patch:
            await db.hypotheses.update_one({"key": _hkey(year)}, {"$set": patch})
            doc.update(patch)
    return doc

async def _active_year():
    s = await db.settings.find_one({"key": "app"})
    return int((s or {}).get("active_year", DEFAULT_YEAR))

async def _fetch_qc_rates(year):
    """Best-effort : récupère en ligne les taux employeur publiés par Revenu Québec / RQAP pour l'année.
    Retourne {code:{"rate":float,"ceiling":float}} (possiblement partiel). Vide si échec réseau/parsing."""
    import re
    out = {}
    try:
        import httpx
    except Exception:
        return out
    y = int(year)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BudgetSalairesPro/1.0)"}

    def _num(s):
        return float(s.replace("\u00a0", "").replace(" ", "").replace(",", "."))

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as cx:
            try:
                r = await cx.get("https://www.rqap.gouv.qc.ca/fr/a-propos-du-regime/cotisations-et-revenu-maximal-assurable")
                if r.status_code == 200:
                    html = r.text
                    rr = {}
                    m_rate = re.search(rf"{y}[\s\S]{{0,600}}?employeur[\s\S]{{0,120}}?(\d[\d\s\u00a0]*,\d+)\s*%", html, re.I)
                    m_max = re.search(r"maximal\s+assurable[\s\S]{0,200}?(\d[\d\s\u00a0]{4,})\s*\$", html, re.I)
                    if m_rate:
                        rr["rate"] = round(_num(m_rate.group(1)) / 100, 6)
                    if m_max:
                        rr["ceiling"] = round(_num(m_max.group(1)), 0)
                    if rr:
                        out["RQAP"] = rr
            except Exception:
                pass
    except Exception:
        return out
    return out

async def _apply_qc_rates(newh, year):
    """Met à jour les charges sociales (sauf CSST) selon les taux Revenu Québec de l'année et lève
    le drapeau de révision (message rouge dans Hypothèses jusqu'à ce que l'utilisateur enregistre)."""
    fetched = await _fetch_qc_rates(year)
    updated = []
    diffs = []
    for c in newh.get("charges", []):
        code = c.get("code")
        if code == "CSST":
            continue
        f = fetched.get(code)
        if not f:
            continue
        if "rate" in f and abs(f["rate"] - (c.get("rate") or 0)) > 1e-9:
            diffs.append({"label": f"{code} · Taux", "old": _fmt_pct(c.get("rate", 0)), "new": _fmt_pct(f["rate"])})
            c["rate"] = f["rate"]
            if code not in updated:
                updated.append(code)
        if f.get("ceiling") and abs(f["ceiling"] - (c.get("ceiling") or 0)) > 0.5:
            diffs.append({"label": f"{code} · Max. assurable", "old": _fmt_money(c.get("ceiling", 0)), "new": _fmt_money(f["ceiling"])})
            c["ceiling"] = f["ceiling"]
            if code not in updated:
                updated.append(code)
    newh["rates_changed"] = True
    newh["rates_diff"] = diffs
    if updated:
        newh["rates_note"] = f"Les taux de charges sociales {year} ({', '.join(updated)}) ont été mis à jour automatiquement selon Revenu Québec. Vérifiez les valeurs puis cliquez sur Enregistrer pour les appliquer."
    else:
        newh["rates_note"] = f"Récupération automatique des taux de Revenu Québec pour {year} incomplète : les taux de l'année précédente ont été reportés. Vérifiez-les puis cliquez sur Enregistrer."
    return newh


@api.get("/years")
async def list_years(user: dict = Depends(get_current_user)):
    docs = await db.hypotheses.find().to_list(1000)
    years = sorted({int(d["year"]) for d in docs if d.get("year")})
    if not years:
        years = [DEFAULT_YEAR]
    return {"years": years, "active_year": await _active_year()}

class YearCreate(BaseModel):
    year: int
    source_year: int
    source_scenario: Literal["ca", "revue1", "revue2"]

@api.post("/years")
async def create_year(payload: YearCreate, user: dict = Depends(get_current_user)):
    ny = int(payload.year)
    if await db.hypotheses.find_one({"key": _hkey(ny)}):
        raise HTTPException(status_code=400, detail="Cette année existe déjà")
    if not await _all_scenarios_locked(payload.source_year):
        raise HTTPException(status_code=400, detail=f"Impossible de créer l'année {ny} : les 3 scénarios de {payload.source_year} (Budget CA, Revue Budgétaire 1 et 2) doivent tous être verrouillés avant le report du budget.")
    src = await _get_hypo(payload.source_year)
    newh = {k: v for k, v in src.items() if k != "_id"}
    newh["key"] = _hkey(ny); newh["year"] = ny
    _apply_working_days(newh, ny)
    await _apply_qc_rates(newh, ny)
    await db.hypotheses.insert_one(newh)
    # Report : le scénario source de l'année précédente devient le salaire actuel de la nouvelle année.
    depts = await db.departments.find().to_list(1000)
    employees = await db.employees.find(_active_q()).to_list(1000)
    data = compute_budget(employees, src, depts, year=payload.source_year, scenario=payload.source_scenario)
    by_num = {l["employee_number"]: l for l in data["lines"]}
    for e in employees:
        ln = by_num.get(e["employee_number"])
        newbase = round(ln["new_salary"], 2) if ln else e["current_annual_salary"]
        await db.employees.update_one({"_id": e["_id"]}, {"$set": {f"years.{ny}.base_salary": newbase}})
    await db.settings.update_one({"key": "app"}, {"$set": {"active_year": ny}, "$addToSet": {"years": ny}}, upsert=True)
    await log_action(user, "Créer", "Année", f"{ny} (report {SCEN_LABEL[payload.source_scenario]} {payload.source_year})")
    return {"success": True, "year": ny}

@api.put("/years/active")
async def set_active_year(payload: dict, user: dict = Depends(get_current_user)):
    await db.settings.update_one({"key": "app"}, {"$set": {"active_year": int(payload["year"])}}, upsert=True)
    return {"success": True}

@api.get("/hypotheses")
async def get_hypotheses(year: Optional[int] = None, user: dict = Depends(get_current_user)):
    year = year or await _active_year()
    doc = await _get_hypo(year)
    doc.pop("_id", None)
    return doc

@api.put("/hypotheses")
async def update_hypotheses(payload: dict, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    year = year or payload.get("year") or await _active_year()
    if user.get("role") != "admin" and await _year_locked(year):
        raise HTTPException(status_code=403, detail=f"Un budget {year} est verrouillé. Seul un administrateur peut modifier les hypothèses.")
    old = await db.hypotheses.find_one({"key": _hkey(year)}) or {}
    payload["key"] = _hkey(year); payload["year"] = int(year)
    payload["rates_changed"] = False
    payload["rates_note"] = ""
    payload["rates_diff"] = []
    changes = _diff_hypotheses(old, payload)
    await db.hypotheses.update_one({"key": _hkey(year)}, {"$set": payload}, upsert=True)
    await log_action(user, "Modifier", "Hypothèses", f"Taux & paramètres {year}", changes=changes)
    doc = await db.hypotheses.find_one({"key": _hkey(year)})
    doc.pop("_id", None)
    return doc

@api.get("/budget")
async def get_budget(year: Optional[int] = None, scenario: str = "ca", department: Optional[str] = None, user: dict = Depends(get_current_user)):
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(_active_q(query)).sort("employee_number", 1).to_list(1000)
    return compute_budget(employees, hypo, depts, year=year, scenario=scenario)

@api.get("/budget/compare")
async def budget_compare(year: Optional[int] = None, department: Optional[str] = None, user: dict = Depends(get_current_user)):
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(_active_q(query)).sort("employee_number", 1).to_list(1000)
    actuel_base = round(sum(_emp_scn(e, year, "actuel")[2] * _proration(e, year)[1] for e in employees), 2)
    out = {"year": year, "headcount": len(employees),
           "actuel": {"masse": actuel_base, "budget_total": actuel_base}}
    for scn in BUDGET_SCENARIOS:
        d = compute_budget(employees, hypo, depts, year=year, scenario=scn)
        out[scn] = {"masse": d["totals"]["salaire_base"], "budget_total": d["totals"]["budget_total"], "by_department": d["by_department"]}
    return out

# ---------------------------------------------------------------------------
# Verrouillage du budget (par année + scénario)
# ---------------------------------------------------------------------------
@api.get("/budget/locks")
async def get_locks(year: Optional[int] = None, user: dict = Depends(get_current_user)):
    q = {"key": {"$regex": f"^{int(year)}:"}} if year else {}
    docs = await db.locks.find(q).to_list(1000)
    return {d["key"]: {"locked": bool(d.get("locked")), "locked_by": d.get("locked_by", ""), "locked_at": d.get("locked_at", "")} for d in docs}

class LockPayload(BaseModel):
    year: int
    scenario: Literal["ca", "revue1", "revue2"]
    locked: bool

@api.post("/budget/lock")
async def set_lock(payload: LockPayload, user: dict = Depends(require_admin)):
    key = f"{int(payload.year)}:{payload.scenario}"
    await db.locks.update_one({"key": key}, {"$set": {
        "key": key, "year": int(payload.year), "scenario": payload.scenario, "locked": payload.locked,
        "locked_by": user.get("email"), "locked_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    await log_action(user, "Verrouiller" if payload.locked else "Déverrouiller", "Budget",
                     f"{SCEN_LABEL.get(payload.scenario, payload.scenario)} {payload.year}")
    if payload.locked:
        y, sc = int(payload.year), payload.scenario
        emps = await db.employees.find({f"years.{y}.{sc}.department": {"$exists": True}}).to_list(2000)
        for emp in emps:
            newdept = (((emp.get("years") or {}).get(str(y)) or {}).get(sc) or {}).get("department")
            if newdept and newdept != emp.get("department"):
                await db.employees.update_one({"_id": emp["_id"]}, {"$set": {"department": newdept}})
    return {"success": True, "locked": payload.locked}

def _has_scenario_entry(e, year, scenario):
    yd = (e.get("years") or {}).get(str(int(year))) or {}
    return bool(yd.get(scenario))

@api.get("/budget/no-entry")
async def budget_no_entry(year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    """Employés actifs sans budget saisi (aucun override) pour l'année + scénario donnés."""
    year = year or await _active_year()
    key = f"{int(year)}:{scenario}"
    emps = await db.employees.find(_active_q()).sort("employee_number", 1).to_list(2000)
    out = [{"id": str(e["_id"]), "employee_number": e["employee_number"], "name": e["name"],
            "department": e.get("department", "")} for e in emps
           if not _has_scenario_entry(e, year, scenario) and key not in (e.get("inactive_scenarios") or [])]
    return {"year": year, "scenario": scenario, "employees": out, "count": len(out)}

@api.post("/budget/inactivate-no-entry")
async def inactivate_no_entry(year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    """Inactive (pour CETTE année + CE scénario uniquement) les employés actifs sans budget saisi.
    L'historique des autres scénarios/années est conservé."""
    year = year or await _active_year()
    key = f"{int(year)}:{scenario}"
    emps = await db.employees.find(_active_q()).to_list(2000)
    ids = [e["_id"] for e in emps
           if not _has_scenario_entry(e, year, scenario) and key not in (e.get("inactive_scenarios") or [])]
    for _id in ids:
        await db.employees.update_one({"_id": _id}, {"$addToSet": {"inactive_scenarios": key}})
    await log_action(user, "Modifier", "Employé", f"Inactivation {SCEN_LABEL.get(scenario, scenario)} {year} — {len(ids)} employé(s) sans budget (scénario uniquement)")
    return {"success": True, "inactivated": len(ids)}

# ---------------------------------------------------------------------------
# Reports (Excel / PDF)
# ---------------------------------------------------------------------------
def _money(v):
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " $"

async def _budget_data(department=None, year=None, scenario="ca"):
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(_active_q(query)).sort("employee_number", 1).to_list(1000)
    data = compute_budget(employees, hypo, depts, year=year, scenario=scenario)
    return data, hypo

def _pnl_data(data, depts):
    """Rapport type P&L : coûts ventilés par mois, regroupés par compte GL (départements).
    Le boni (+ charges sociales associées) des employés est extrait vers le compte « GL Boni »
    du département et déduit du compte GL de salaire principal."""
    gl_map = {d["code"]: (d.get("compte_gl") or "").strip() for d in depts}
    boni_gl_map = {d["code"]: (d.get("gl_boni") or "").strip() for d in depts}
    rows = {}
    for ln in data["lines"]:
        gl = gl_map.get(ln["department"], "") or "—"
        boni_acct = boni_gl_map.get(ln["department"], "")
        bgl = ln.get("boni_gl", 0) or 0
        tb = ln["total_budgeted"] or 1
        split = bool(boni_acct) and bgl > 0
        boni_monthly = [ln["monthly"][i] * bgl / tb if split else 0.0 for i in range(12)]
        r = rows.setdefault(gl, {"gl": gl, "monthly": [0.0] * 12, "total": 0.0})
        for i in range(12):
            r["monthly"][i] += ln["monthly"][i] - boni_monthly[i]
        r["total"] += ln["total_budgeted"] - (bgl if split else 0)
        if split:
            rb = rows.setdefault(boni_acct, {"gl": boni_acct, "monthly": [0.0] * 12, "total": 0.0})
            for i in range(12):
                rb["monthly"][i] += boni_monthly[i]
            rb["total"] += bgl
    out = [{"gl": k, "monthly": [round(x, 2) for x in v["monthly"]], "total": round(v["total"], 2)} for k, v in sorted(rows.items())]
    totals = {"monthly": [round(sum(r["monthly"][i] for r in out), 2) for i in range(12)], "total": round(sum(r["total"] for r in out), 2)}
    return {"months": MONTHS, "rows": out, "totals": totals}

def _by_class_data(data, hypo):
    """Masse salariale par classe de sécurité CSST."""
    cls = {c["code"]: c for c in hypo.get("security_classes", [])}
    rows = {}
    for ln in data["lines"]:
        code = ln.get("security_class") or "—"
        r = rows.setdefault(code, {"code": code, "description": cls.get(code, {}).get("description", "Non assignée") if code != "—" else "Non assignée",
                                    "rate": cls.get(code, {}).get("rate", 0) if code != "—" else 0,
                                    "count": 0, "salaire_brut": 0.0, "csst": 0.0, "budget": 0.0})
        r["count"] += 1
        r["salaire_brut"] += ln["salaire_brut"]
        r["csst"] += ln["csst"]
        r["budget"] += ln["total_budgeted"]
    out = [{**v, "salaire_brut": round(v["salaire_brut"], 2), "csst": round(v["csst"], 2), "budget": round(v["budget"], 2)} for v in rows.values()]
    out.sort(key=lambda x: -x["budget"])
    return {"rows": out, "csst_max_assurable": hypo.get("csst_max_assurable", 103000)}

@api.get("/reports/pnl")
async def report_pnl(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    depts = await db.departments.find().to_list(1000)
    return _pnl_data(data, depts)

@api.get("/reports/by-class")
async def report_by_class(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    return _by_class_data(data, hypo)

async def _scenario_compare_data(year, department):
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(_active_q(query)).sort("employee_number", 1).to_list(2000)
    scen = {sc: compute_budget(employees, hypo, depts, year=year, scenario=sc) for sc in BUDGET_SCENARIOS}
    dep_rows = {}
    for sc in BUDGET_SCENARIOS:
        for bd in scen[sc]["by_department"]:
            r = dep_rows.setdefault(bd["department"], {"department": bd["department"], "label": bd["label"], "ca": 0.0, "revue1": 0.0, "revue2": 0.0})
            r[sc] = bd["budget"]
            r["label"] = r["label"] or bd["label"]
    def _ecart(r):
        r["ecart_r1"] = round(r["revue1"] - r["ca"], 2)
        r["ecart_r1_pct"] = round((r["revue1"] - r["ca"]) / r["ca"] * 100, 1) if r["ca"] else 0.0
        r["ecart_r2"] = round(r["revue2"] - r["ca"], 2)
        r["ecart_r2_pct"] = round((r["revue2"] - r["ca"]) / r["ca"] * 100, 1) if r["ca"] else 0.0
        for k in ("ca", "revue1", "revue2"):
            r[k] = round(r[k], 2)
        return r
    rows = [_ecart(r) for r in sorted(dep_rows.values(), key=lambda x: (int(x["department"]) if str(x["department"]).isdigit() else 0))]
    tot = {"department": "", "label": "TOTAL", "ca": scen["ca"]["totals"]["budget_total"],
           "revue1": scen["revue1"]["totals"]["budget_total"], "revue2": scen["revue2"]["totals"]["budget_total"]}
    tot = _ecart(tot)
    return {"year": int(year), "rows": rows, "totals": tot}

@api.get("/reports/scenario-compare")
async def report_scenario_compare(department: Optional[str] = None, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    return await _scenario_compare_data(year, department)

def _scenario_compare_excel(cmp, year):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Comparatif scénarios"
    bold = openpyxl.styles.Font(bold=True)
    _xlsx_logo(ws); ws.append([f"Comparatif des scénarios — {year}"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=14)
    ws.append([])
    ws.append(["Département", "Budget CA", "Revue 1", "Écart R1 ($)", "Écart R1 (%)", "Revue 2", "Écart R2 ($)", "Écart R2 (%)"])
    [setattr(c, "font", bold) for c in ws[ws.max_row]]
    for r in cmp["rows"]:
        lbl = f"{r['department']} — {r['label']}" if r["department"] else r["label"]
        ws.append([lbl, r["ca"], r["revue1"], r["ecart_r1"], r["ecart_r1_pct"] / 100, r["revue2"], r["ecart_r2"], r["ecart_r2_pct"] / 100])
    t = cmp["totals"]
    ws.append(["TOTAL", t["ca"], t["revue1"], t["ecart_r1"], t["ecart_r1_pct"] / 100, t["revue2"], t["ecart_r2"], t["ecart_r2_pct"] / 100])
    [setattr(c, "font", bold) for c in ws[ws.max_row]]
    for col in ("B", "C", "D", "F", "G"):
        for cell in ws[col]:
            cell.number_format = '#,##0.00'
    for col in ("E", "H"):
        for cell in ws[col]:
            cell.number_format = '0.0%'
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf

@api.get("/reports/scenario-compare-excel")
async def report_scenario_compare_excel(department: Optional[str] = None, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    y = year or await _active_year()
    cmp = await _scenario_compare_data(y, department)
    buf = _scenario_compare_excel(cmp, y)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=comparatif_scenarios_{y}.xlsx"})

CUSTOM_COLS = {
    "employee_number": "#", "name": "Nom", "title": "Titre", "department": "Département",
    "employment_type": "Type", "security_class": "Classe séc.", "base_salary": "Salaire base",
    "augmentation": "Augment.", "new_salary": "Nouveau salaire", "vacation": "Vacances",
    "primes_total": "Primes", "salaire_brut": "Salaire brut", "avantages": "Avantages",
    "csst": "CSST", "reer": "REER", "assurance": "Assurance", "total_budgeted": "Coût total",
}

def _custom_rows(data, columns, group_by, sort_key, sort_dir):
    lines = data["lines"]
    cols = [c for c in columns if c in CUSTOM_COLS] or ["employee_number", "name", "department", "salaire_brut", "total_budgeted"]
    if sort_key in CUSTOM_COLS:
        lines = sorted(lines, key=lambda l: l.get(sort_key, 0) if not isinstance(l.get(sort_key), str) else l.get(sort_key, ""), reverse=(sort_dir == "desc"))
    numeric = {"base_salary", "new_salary", "vacation", "primes_total", "salaire_brut", "avantages", "csst", "reer", "assurance", "total_budgeted"}
    def fmt(l, c):
        v = l.get(c, "")
        if c == "augmentation":
            return f"{(l.get('augmentation') or 0) * 100:.1f}%"
        return v
    result = {"columns": [{"key": c, "label": CUSTOM_COLS[c]} for c in cols], "numeric": list(numeric)}
    if group_by in CUSTOM_COLS:
        groups = {}
        for l in lines:
            g = l.get(group_by, "—")
            groups.setdefault(g, []).append(l)
        result["grouped"] = True
        result["groups"] = [{"key": str(g), "rows": [{c: fmt(l, c) for c in cols} for l in gl],
                             "subtotals": {c: round(sum(l.get(c, 0) for l in gl), 2) for c in cols if c in numeric}}
                            for g, gl in sorted(groups.items(), key=lambda kv: str(kv[0]))]
    else:
        result["grouped"] = False
        result["rows"] = [{c: fmt(l, c) for c in cols} for l in lines]
    result["totals"] = {c: round(sum(l.get(c, 0) for l in lines), 2) for c in cols if c in numeric}
    return result

@api.get("/reports/custom")
async def report_custom(columns: str = "", group_by: str = "", sort_key: str = "", sort_dir: str = "asc",
                        department: Optional[str] = None, employment_type: Optional[str] = None,
                        year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    if employment_type and employment_type != "all":
        data["lines"] = [l for l in data["lines"] if (("CCQ" if l["is_ccq"] else l["employment_type"]) == employment_type)]
    cols = [c.strip() for c in columns.split(",") if c.strip()]
    return _custom_rows(data, cols, group_by, sort_key, sort_dir)

@api.get("/reports/custom-columns")
async def report_custom_columns(user: dict = Depends(get_current_user)):
    return {"columns": [{"key": k, "label": v} for k, v in CUSTOM_COLS.items()]}

class ReportTemplate(BaseModel):
    name: str
    columns: List[str] = []
    employment_type: str = "all"
    group_by: str = ""
    department: str = "all"

@api.get("/report-templates")
async def list_report_templates(user: dict = Depends(get_current_user)):
    docs = await db.report_templates.find().to_list(1000)
    docs.sort(key=lambda d: d.get("name", "").lower())
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

@api.post("/report-templates")
async def create_report_template(payload: ReportTemplate, user: dict = Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nom requis")
    doc = payload.model_dump()
    doc["name"] = payload.name.strip()
    res = await db.report_templates.insert_one(doc)
    await log_action(user, "Créer", "Modèle de rapport", doc["name"])
    d = await db.report_templates.find_one({"_id": res.inserted_id})
    d["id"] = str(d.pop("_id"))
    return d

@api.delete("/report-templates/{tid}")
async def delete_report_template(tid: str, user: dict = Depends(get_current_user)):
    d = await db.report_templates.find_one({"_id": _oid(tid)})
    res = await db.report_templates.delete_one({"_id": _oid(tid)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    await log_action(user, "Supprimer", "Modèle de rapport", d.get("name", tid) if d else tid)
    return {"success": True}


def _pnl_excel(pnl, year, scenario_label):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "État des résultats"
    bold = openpyxl.styles.Font(bold=True)
    _xlsx_logo(ws); ws.append([f"État des résultats (P&L) — {scenario_label} {year}"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=14)
    ws.append([])
    ws.append(["Compte GL"] + pnl["months"] + ["Total"]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    for r in pnl["rows"]:
        ws.append([r["gl"]] + r["monthly"] + [r["total"]])
    ws.append(["TOTAL"] + pnl["totals"]["monthly"] + [pnl["totals"]["total"]]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf

@api.get("/reports/pnl-excel")
async def report_pnl_excel(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    depts = await db.departments.find().to_list(1000)
    y = year or await _active_year()
    buf = _pnl_excel(_pnl_data(data, depts), y, SCEN_LABEL.get(scenario, scenario))
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=pnl_{scenario}_{y}.xlsx"})


def build_budget_excel(data, year, dept_label):
    wb = openpyxl.Workbook()
    bold = openpyxl.styles.Font(bold=True)
    # Résumé
    ws = wb.active; ws.title = "Résumé"
    _xlsx_logo(ws); ws.append([f"Rapport budgétaire {year} — {dept_label}"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=14)
    ws.append([])
    k = data["kpis"]
    for lbl, val in [("Effectif", k["headcount"]), ("Masse salariale", data["totals"]["salaire_base"]),
                     ("Budget global (avec charges)", data["totals"]["budget_total"]),
                     ("Salaire moyen", k["salaire_moyen"]), ("Employés CCQ", k["ccq_count"])]:
        ws.append([lbl, val])
    ws.append([])
    ws.append(["Ventilation", "Montant", "%"]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    t = data["totals"]; bt = t["budget_total"] or 1
    for lbl, key in [("Salaire de base", "salaire_base"), ("Vacances", "vacances"), ("Primes & Boni", "primes"),
                     ("Avantages sociaux", "avantages"), ("CSST", "csst"), ("RPDB/REER", "reer"), ("Assu. collectives", "assurance")]:
        ws.append([lbl, t[key], f"{t[key]/bt*100:.1f}%"])
    ws.append(["BUDGET TOTAL", t["budget_total"], "100%"]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    # Détail employés
    ws2 = wb.create_sheet("Détail employés")
    cols = ["#", "Nom", "Titre", "Département", "Type", "Salaire base", "Nouveau salaire", "Vacances",
            "Primes", "Salaire brut total", "Avantages", "CSST", "REER", "Assurance", "Coût total"]
    ws2.append(cols); [setattr(c, "font", bold) for c in ws2[1]]
    for l in data["lines"]:
        ws2.append([l["employee_number"], l["name"], l["title"], l["department"], l["employment_type"],
                    l["base_salary"], l["new_salary"], l["vacation"], l["primes_total"],
                    l["salaire_brut"], l["avantages"],
                    l["csst"], l["reer"], l["assurance"], l["total_cost"]])
    # Par département
    ws3 = wb.create_sheet("Par département")
    ws3.append(["Département", "Salaire", "Budget total"]); [setattr(c, "font", bold) for c in ws3[1]]
    for d in data["by_department"]:
        ws3.append([f"{d['department']} — {d['label']}", d["salaire"], d["budget"]])
    # Ventilation mensuelle
    ws4 = wb.create_sheet("Ventilation mensuelle")
    ws4.append(["Mois", "Sem. paie", "Jours std", "Jours CCQ", "Salaires", "Charges", "Total"]); [setattr(c, "font", bold) for c in ws4[1]]
    for m in data["monthly"]:
        ws4.append([m["month"], m["sem_paie"], m["jours_std"], m["jours_ccq"], m["salaires"], m["charges"], m["total"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf

def build_budget_pdf(data, year, dept_label):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0F172A"); TEAL = colors.HexColor("#22C55E")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=18)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=10)
    el = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph(f"Rapport budgétaire {year}", h),
          Paragraph(f"{dept_label} · généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub), Spacer(1, 8)]
    k = data["kpis"]; t = data["totals"]
    kpi_tbl = Table([["Effectif", "Masse salariale", "Budget global", "Salaire moyen"],
                     [str(k["headcount"]), _money(t["salaire_base"]), _money(t["budget_total"]), _money(k["salaire_moyen"])]],
                    colWidths=[42 * mm] * 4)
    kpi_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                 ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0"))]))
    el += [kpi_tbl, Spacer(1, 6), Paragraph("Ventilation des coûts", sec)]
    bt = t["budget_total"] or 1
    vrows = [["Poste", "Montant", "%"]]
    for lbl, key in [("Salaire de base", "salaire_base"), ("Vacances", "vacances"), ("Primes & Boni", "primes"),
                     ("Avantages sociaux", "avantages"), ("CSST", "csst"), ("RPDB/REER", "reer"), ("Assu. collectives", "assurance")]:
        vrows.append([lbl, _money(t[key]), f"{t[key]/bt*100:.1f}%"])
    vrows.append(["BUDGET TOTAL", _money(t["budget_total"]), "100%"])
    vt = Table(vrows, colWidths=[90 * mm, 50 * mm, 25 * mm])
    vt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    el += [vt, Spacer(1, 6), Paragraph("Budget par département", sec)]
    drows = [["Département", "Salaire", "Budget total"]] + [[f"{d['department']} — {d['label']}", _money(d["salaire"]), _money(d["budget"])] for d in data["by_department"]]
    dt = Table(drows, colWidths=[95 * mm, 35 * mm, 35 * mm])
    dt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")])]))
    el += [dt]
    doc.build(el)
    buf.seek(0)
    return buf

def build_employee_fiche_pdf(ln, year, scenario_label):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=15 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0F172A"); TEAL = colors.HexColor("#22C55E")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=17)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=11, spaceBefore=10)
    ccq = ln["is_ccq"]
    el = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph(f"{ln['name']} — #{str(ln['employee_number']).zfill(3)}", h),
          Paragraph(f"{scenario_label} {year} · {ln['employment_type']} · {ln['department_label']} · généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub), Spacer(1, 8)]

    def block(title, rows, color):
        t = Table([[title, ""]] + rows, colWidths=[100 * mm, 60 * mm])
        t.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), color), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("ALIGN", (1, 1), (1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    salaire = [["Salaire de base (actuel)", _money(ln["base_salary"])],
               ["Augmentation", f"{ln['augmentation']*100:.2f} %"],
               ["Nouveau salaire", _money(ln["new_salary"])],
               ["Taux horaire (réf. 2080 h)", f"{ln['taux_horaire']} $/h"],
               ["Vacances", _money(ln["vacation"])]]
    if ccq:
        primes = [[f"Prime ({ln['prime_type']})", _money(ln["prime_amount"])], ["Prime de garde", _money(ln["garde"])],
                  ["Prime HALO", _money(ln["halo"])], ["Alloc. sécurité", _money(ln["alloc"])],
                  ["Total primes", _money(ln["primes_total"])]]
    else:
        primes = [["Boni", _money(ln["boni"])], ["Alloc. sécurité", _money(ln["alloc"])], ["Total primes & boni", _money(ln["primes_total"])]]
    primes.append(["Salaire brut total", _money(ln["new_salary"] + ln["vacation"] + ln["primes_total"])])
    charges = [["RRQ", _money(ln["rrq"])], ["AE", _money(ln["ae"])], ["RQAP", _money(ln["rqap"])], ["FSS", _money(ln["fss"])]]
    if ccq:
        charges.append(["Avantages CCQ (32.33%)", _money(ln["ccq_avantages"])])
    charges.append(["CSST", _money(ln["csst"])])
    if not ccq:
        charges += [["RPDB / REER", _money(ln["reer"])], ["Assu. collectives", _money(ln["assurance"])]]
    charges.append(["Total avantages sociaux", _money(ln["avantages"])])

    el += [block("Salaire", salaire, NAVY), Spacer(1, 6),
           block("Primes & rémunération additionnelle", primes, colors.HexColor("#FBBF24")), Spacer(1, 6),
           block("Cotisations & avantages (max. assurables)", charges, colors.HexColor("#8B5CF6")), Spacer(1, 10)]
    tot = Table([["MASSE SALARIALE TOTALE", _money(ln["total_cost"])]], colWidths=[100 * mm, 60 * mm])
    tot.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                             ("TEXTCOLOR", (1, 0), (1, -1), TEAL), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                             ("FONTSIZE", (0, 0), (-1, -1), 12), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el += [tot]
    doc.build(el)
    buf.seek(0)
    return buf

def _group_by_dept(lines):
    groups = {}
    for l in lines:
        g = groups.setdefault(l["department"], {"label": l["department_label"], "lines": []})
        g["lines"].append(l)
    return sorted(groups.items(), key=lambda kv: kv[0])

FICHE_COLS = ["#", "Nom", "Type", "Sal. base", "Aug.", "Nouv. salaire", "Vacances", "Primes", "Sal. brut total", "Avantages", "CSST", "REER", "Assur.", "Coût total"]
def _fiche_row(l):
    return [str(l["employee_number"]).zfill(3), l["name"], "CCQ" if l["is_ccq"] else l["employment_type"],
            l["base_salary"], f"{l['augmentation']*100:.1f}%", l["new_salary"], l["vacation"], l["primes_total"],
            l["salaire_brut"], l["avantages"], l["csst"], l["reer"], l["assurance"], l["total_cost"]]

def build_fiches_excel(data, year, scenario_label, scope):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Fiches détaillées"
    bold = openpyxl.styles.Font(bold=True)
    _xlsx_logo(ws); ws.append([f"Fiches détaillées {scenario_label} {year} — {scope}"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=14)
    ws.append([])
    num_cols = ["Sal. base", "Nouv. salaire", "Vacances", "Primes", "Sal. brut total", "Avantages", "CSST", "REER", "Assur.", "Coût total"]
    for dept, g in _group_by_dept(data["lines"]):
        ws.append([f"Département {dept} — {g['label']}"]); ws[ws.max_row][0].font = bold
        ws.append(FICHE_COLS); [setattr(c, "font", bold) for c in ws[ws.max_row]]
        sub = {k: 0 for k in num_cols}
        for l in g["lines"]:
            ws.append(_fiche_row(l))
            for k, key in zip(num_cols, ["base_salary", "new_salary", "vacation", "primes_total", "salaire_brut", "avantages", "csst", "reer", "assurance", "total_cost"]):
                sub[k] += l[key]
        ws.append(["", "Sous-total", "", round(sub["Sal. base"], 2), "", round(sub["Nouv. salaire"], 2), round(sub["Vacances"], 2),
                   round(sub["Primes"], 2), round(sub["Sal. brut total"], 2), round(sub["Avantages"], 2), round(sub["CSST"], 2), round(sub["REER"], 2),
                   round(sub["Assur."], 2), round(sub["Coût total"], 2)])
        [setattr(c, "font", bold) for c in ws[ws.max_row]]
        ws.append([])
    t = data["totals"]
    brut_total = round(t["salaire_base"] + t["vacances"] + t["primes"], 2)
    ws.append(["", "BUDGET TOTAL", "", t["salaire_base"], "", t["salaire_base"], t["vacances"], t["primes"], brut_total, t["avantages"], t["csst"], t["reer"], t["assurance"], t["budget_total"]])
    [setattr(c, "font", openpyxl.styles.Font(bold=True, size=12)) for c in ws[ws.max_row]]
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf

def build_fiches_pdf(data, year, scenario_label, scope):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=14 * mm, bottomMargin=12 * mm, leftMargin=12 * mm, rightMargin=12 * mm)
    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#0F172A"); TEAL = colors.HexColor("#22C55E")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=16)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=11, spaceBefore=8)
    el = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph(f"Fiches détaillées — {scenario_label} {year}", h),
          Paragraph(f"{scope} · généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}", sub), Spacer(1, 6)]
    widths = [12 * mm, 46 * mm, 24 * mm, 24 * mm, 14 * mm, 26 * mm, 22 * mm, 22 * mm, 24 * mm, 20 * mm, 20 * mm, 20 * mm, 26 * mm]
    num_keys = ["base_salary", "new_salary", "vacation", "primes_total", "avantages", "csst", "reer", "assurance", "total_cost"]
    for dept, g in _group_by_dept(data["lines"]):
        rows = [FICHE_COLS]
        sub_tot = {k: 0 for k in num_keys}
        for l in g["lines"]:
            r = _fiche_row(l)
            rows.append([r[0], r[1], r[2], _money(l["base_salary"]), r[4], _money(l["new_salary"]), _money(l["vacation"]),
                         _money(l["primes_total"]), _money(l["avantages"]), _money(l["csst"]), _money(l["reer"]), _money(l["assurance"]), _money(l["total_cost"])])
            for k in num_keys:
                sub_tot[k] += l[k]
        rows.append(["", "Sous-total", "", _money(sub_tot["base_salary"]), "", _money(sub_tot["new_salary"]), _money(sub_tot["vacation"]),
                     _money(sub_tot["primes_total"]), _money(sub_tot["avantages"]), _money(sub_tot["csst"]), _money(sub_tot["reer"]), _money(sub_tot["assurance"]), _money(sub_tot["total_cost"])])
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("FONTSIZE", (0, 0), (-1, -1), 7), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                                 ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                                 ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                                 ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
        el += [Paragraph(f"Département {dept} — {g['label']}", sec), tbl, Spacer(1, 6)]
    t = data["totals"]
    gt = Table([["BUDGET TOTAL", _money(t["budget_total"])]], colWidths=[200 * mm, 60 * mm])
    gt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                            ("TEXTCOLOR", (1, 0), (1, -1), TEAL), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 12), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    el += [Spacer(1, 4), gt]
    doc.build(el)
    buf.seek(0)
    return buf

@api.get("/budget/evolution")
async def budget_evolution(department: Optional[str] = None, user: dict = Depends(get_current_user)):
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(_active_q(query)).sort("employee_number", 1).to_list(1000)
    docs = await db.hypotheses.find().to_list(1000)
    years = sorted({int(d["year"]) for d in docs if d.get("year")}) or [DEFAULT_YEAR]
    out = []
    for y in years:
        hypo = await _get_hypo(y)
        ca = compute_budget(employees, hypo, depts, year=y, scenario="ca")
        revue1 = compute_budget(employees, hypo, depts, year=y, scenario="revue1")
        revue2 = compute_budget(employees, hypo, depts, year=y, scenario="revue2")
        actuel = round(sum(_emp_scn(e, y, "actuel")[2] * _proration(e, y)[1] for e in employees), 2)
        out.append({"year": y, "actuel": actuel,
                    "ca": ca["totals"]["salaire_base"], "revue1": revue1["totals"]["salaire_base"], "revue2": revue2["totals"]["salaire_base"],
                    "ca_budget": ca["totals"]["budget_total"], "revue1_budget": revue1["totals"]["budget_total"], "revue2_budget": revue2["totals"]["budget_total"]})
    return {"years": out}

@api.get("/employees/{eid}/fiche-pdf")
async def employee_fiche_pdf(eid: str, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"_id": _oid(eid)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    ln = compute_budget([emp], hypo, depts, year=year, scenario=scenario)["lines"][0]
    buf = build_employee_fiche_pdf(ln, year, SCEN_LABEL.get(scenario, scenario))
    await log_action(user, "Modifier", "Rapport", f"Fiche PDF {SCEN_LABEL.get(scenario, scenario)} {year} — {emp['name']}")
    fname = f"fiche_{ln['name'].replace(' ', '_')}_{scenario}_{year}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})

@api.get("/reports/excel")
async def report_excel(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    scope = "Tous les départements" if not department or department == "all" else department
    dept_label = f"{scope} · {SCEN_LABEL.get(scenario, scenario)}"
    buf = build_budget_excel(data, hypo["year"], dept_label)
    await log_action(user, "Modifier", "Rapport", f"Export Excel {SCEN_LABEL.get(scenario, scenario)} — {scope}")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=rapport_{scenario}_{hypo['year']}.xlsx"})

@api.get("/reports/pdf")
async def report_pdf(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    scope = "Tous les départements" if not department or department == "all" else department
    dept_label = f"{scope} · {SCEN_LABEL.get(scenario, scenario)}"
    buf = build_budget_pdf(data, hypo["year"], dept_label)
    await log_action(user, "Modifier", "Rapport", f"Export PDF {SCEN_LABEL.get(scenario, scenario)} — {scope}")
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=rapport_{scenario}_{hypo['year']}.pdf"})

@api.get("/reports/fiches-pdf")
async def report_fiches_pdf(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    scope = "Tous les départements" if not department or department == "all" else department
    buf = build_fiches_pdf(data, hypo["year"], SCEN_LABEL.get(scenario, scenario), scope)
    await log_action(user, "Modifier", "Rapport", f"Fiches PDF {SCEN_LABEL.get(scenario, scenario)} — {scope}")
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=fiches_{scenario}_{hypo['year']}.pdf"})

@api.get("/reports/fiches-excel")
async def report_fiches_excel(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    scope = "Tous les départements" if not department or department == "all" else department
    buf = build_fiches_excel(data, hypo["year"], SCEN_LABEL.get(scenario, scenario), scope)
    await log_action(user, "Modifier", "Rapport", f"Fiches Excel {SCEN_LABEL.get(scenario, scenario)} — {scope}")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=fiches_{scenario}_{hypo['year']}.xlsx"})

@api.get("/reports/by-class-excel")
async def report_by_class_excel(department: Optional[str] = None, year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    y = year or await _active_year()
    bc = _by_class_data(data, hypo)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Masse par classe"
    bold = openpyxl.styles.Font(bold=True)
    _xlsx_logo(ws); ws.append([f"Masse salariale par classe de sécurité — {SCEN_LABEL.get(scenario, scenario)} {y}  (max assurable {bc['csst_max_assurable']} $)"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=13)
    ws.append([])
    ws.append(["Classe", "Description", "Taux %", "Employés", "Salaire brut", "CSST", "Coût total"]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    for r in bc["rows"]:
        ws.append([r["code"], r["description"], round(r["rate"] * 100, 2), r["count"], r["salaire_brut"], r["csst"], r["budget"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=masse_classe_{scenario}_{y}.xlsx"})

@api.get("/reports/custom-excel")
async def report_custom_excel(columns: str = "", group_by: str = "", sort_key: str = "", sort_dir: str = "asc",
                              department: Optional[str] = None, employment_type: Optional[str] = None,
                              year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department, year, scenario)
    y = year or await _active_year()
    if employment_type and employment_type != "all":
        data["lines"] = [l for l in data["lines"] if (("CCQ" if l["is_ccq"] else l["employment_type"]) == employment_type)]
    rep = _custom_rows(data, [c.strip() for c in columns.split(",") if c.strip()], group_by, sort_key, sort_dir)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Rapport personnalisé"
    bold = openpyxl.styles.Font(bold=True)
    hdr = [c["label"] for c in rep["columns"]]
    _xlsx_logo(ws); ws.append([f"Rapport personnalisé — {SCEN_LABEL.get(scenario, scenario)} {y}"]); ws["A2"].font = openpyxl.styles.Font(bold=True, size=13)
    ws.append([]); ws.append(hdr); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    keys = [c["key"] for c in rep["columns"]]
    if rep["grouped"]:
        for g in rep["groups"]:
            ws.append([f"▸ {g['key']}"]); ws[ws.max_row][0].font = bold
            for row in g["rows"]:
                ws.append([row.get(k, "") for k in keys])
            ws.append([("Sous-total" if k == keys[0] else g["subtotals"].get(k, "")) for k in keys]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    else:
        for row in rep["rows"]:
            ws.append([row.get(k, "") for k in keys])
    ws.append([("TOTAL" if k == keys[0] else rep["totals"].get(k, "")) for k in keys]); [setattr(c, "font", bold) for c in ws[ws.max_row]]
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=rapport_perso_{scenario}_{y}.xlsx"})

# ---------------------------------------------------------------------------
# Excel import / templates
# ---------------------------------------------------------------------------
EMP_HEADERS = ["Matricule (# — laisser vide pour auto)", "Nom", "Département (code)", "Titre", "Type emploi (CCQ / Régulier temps plein / Régulier temps partiel / Stagiaire)",
               "Catégorie CCQ (Électricien / Frigoriste / N/A)", "Salaire annuel", "Taux vacances %",
               "Jours maladie", "Jours fériés", "Type prime (Aucune Prime / Prime 8% / Prime 11% / Prime 12%)",
               "Prime garde (Oui/Non)", "Prime HALO (Oui/Non)", "Alloc sécurité (Oui/Non)",
               "Date embauche (AAAA-MM-JJ)", "Date naissance (AAAA-MM-JJ)",
               "Sexe à la naissance (Masculin / Féminin / Autre / Préfère ne pas répondre)", "Statut (Actif / Inactif)",
               "Superviseur", "Classe de sécurité CSST (code)"]
DEP_HEADERS = ["Code", "Description", "Superviseur", "Compte GL", "Groupe P&L", "CSST %"]

def _b(v):
    return str(v).strip().lower() in ("oui", "yes", "true", "1", "vrai", "x", "o")

def _cell(row, i):
    return row[i] if i < len(row) and row[i] is not None else None

def _date(v):
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()[:10]

def _xlsx_response(headers, example, sheet, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    ws.append(example)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

@api.get("/employees/template")
async def emp_template(user: dict = Depends(get_current_user)):
    ex = [101, "Jean Exemple", "400", "Comptable", "Régulier temps plein", "N/A", 80000, 8, 8, 14,
          "Prime 8%", "Non", "Non", "Non", "2020-01-15", "1985-05-20", "Masculin", "Actif", "Marie Superviseur", "90010"]
    return _xlsx_response(EMP_HEADERS, ex, "Employés", "modele_employes.xlsx")

@api.get("/departments/template")
async def dep_template(user: dict = Depends(get_current_user)):
    ex = ["999", "Nouveau département", "Superviseur", "5006000", "Services", 0.61]
    return _xlsx_response(DEP_HEADERS, ex, "Départements", "modele_departements.xlsx")

@api.post("/employees/import")
async def import_employees(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin" and await _any_locked():
        raise HTTPException(status_code=403, detail="Un budget est verrouillé. Seul un administrateur peut importer des employés.")
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsx) invalide")
    ws = wb.active
    valid_types = {"CCQ", "Régulier temps plein", "Régulier temps partiel", "Stagiaire"}
    valid_primes = {"Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"}
    dept_codes = {d["code"] for d in await db.departments.find().to_list(1000)}
    existing_nums = {e["employee_number"] for e in await db.employees.find({}, {"employee_number": 1}).to_list(100000)}
    used = set()
    errors = []
    to_insert, to_update = [], []
    n = await _next_number()
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(c is None for c in row):
            continue
        name = _cell(row, 1)
        if not name:
            continue
        try:
            mat_raw = _cell(row, 0)
            is_update = False
            if mat_raw is not None and str(mat_raw).strip() != "":
                try:
                    num = int(float(mat_raw))
                except Exception:
                    raise ValueError(f"Matricule invalide '{mat_raw}'")
                if num in used:
                    raise ValueError(f"Matricule {num} en double dans le fichier")
                if num in existing_nums:
                    is_update = True
            else:
                while n in existing_nums or n in used:
                    n += 1
                num = n
            etype = str(_cell(row, 4) or "Régulier temps plein").strip()
            if etype not in valid_types:
                raise ValueError(f"Type emploi invalide '{etype}'")
            cat = str(_cell(row, 5) or "N/A").strip() or "N/A"
            is_ccq = etype == "CCQ"
            if is_ccq and cat not in ("Électricien", "Frigoriste"):
                raise ValueError("Catégorie CCQ requise (Électricien/Frigoriste)")
            if not is_ccq:
                cat = "N/A"
            prime = str(_cell(row, 10) or "Aucune Prime").strip()
            if prime not in valid_primes:
                prime = "Aucune Prime"
            vac = float(_cell(row, 7) or 0)
            sex_raw = str(_cell(row, 16) or "").strip()
            valid_sexes = {"Masculin", "Féminin", "Autre", "Préfère ne pas répondre"}
            if sex_raw and sex_raw not in valid_sexes:
                raise ValueError(f"Sexe à la naissance invalide '{sex_raw}'")
            status_raw = str(_cell(row, 17) or "").strip().lower()
            active = False if status_raw in ("inactif", "inactive", "non", "false", "0", "no") else True
            doc = {
                "name": str(name).strip(), "department": str(_cell(row, 2) or "").strip(),
                "title": str(_cell(row, 3) or "").strip(), "employment_type": etype, "ccq_category": cat,
                "current_annual_salary": float(_cell(row, 6) or 0),
                "vacation_rate": vac / 100 if vac > 1 else vac,
                "sick_personal_days": int(_cell(row, 8) or 0), "holiday_days": int(_cell(row, 9) or 0),
                "is_ccq": is_ccq, "prime_type": prime,
                "prime_garde": _b(_cell(row, 11)), "prime_halo": _b(_cell(row, 12)), "alloc_securite": _b(_cell(row, 13)),
                "hire_date": _date(_cell(row, 14)), "birth_date": _date(_cell(row, 15)),
                "sex_at_birth": sex_raw or None, "active": active,
                "supervisor": str(_cell(row, 18) or "").strip() or None,
                "security_class": str(_cell(row, 19) or "").strip() or None,
                "employee_number": num,
            }
            if not doc["department"]:
                raise ValueError("Département requis")
            if doc["department"] not in dept_codes:
                raise ValueError(f"Département '{doc['department']}' inexistant")
            if is_update:
                to_update.append((num, doc))
            else:
                to_insert.append(doc)
            used.add(num)
        except Exception as ex:
            errors.append({"line": idx, "name": str(name).strip() if name else "", "message": str(ex)})
    if errors:
        return {"inserted": 0, "updated": 0, "errors": errors, "aborted": True}
    inserted, updated = 0, 0
    for num, doc in to_update:
        # Met à jour les champs de base sans toucher aux overrides annuels (years).
        await db.employees.update_one({"employee_number": num}, {"$set": doc})
        updated += 1
    for doc in to_insert:
        await db.employees.insert_one(doc)
        inserted += 1
    await log_action(user, "Créer", "Employé", f"Import Excel — {inserted} ajout(s), {updated} mise(s) à jour")
    return {"inserted": inserted, "updated": updated, "errors": [], "aborted": False}

@api.post("/departments/import")
async def import_departments(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsx) invalide")
    ws = wb.active
    errors = []
    to_insert = []
    seen = set()
    existing_codes = {d["code"] for d in await db.departments.find({}, {"code": 1}).to_list(100000)}
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(c is None for c in row):
            continue
        code = _cell(row, 0)
        if not code:
            continue
        try:
            code = str(code).strip()
            if code in seen:
                raise ValueError(f"Code '{code}' en double dans le fichier")
            if code in existing_codes:
                raise ValueError(f"Code '{code}' existe déjà")
            csst = float(_cell(row, 5) or 0)
            doc = {"code": code, "description": str(_cell(row, 1) or "").strip(),
                   "superviseur": str(_cell(row, 2) or "").strip(), "compte_gl": str(_cell(row, 3) or "").strip(),
                   "groupe_pl": str(_cell(row, 4) or "Services").strip(), "csst": csst / 100 if csst > 1 else csst}
            to_insert.append(doc)
            seen.add(code)
        except Exception as ex:
            errors.append({"line": idx, "name": str(code).strip() if code else "", "message": str(ex)})
    if errors:
        return {"inserted": 0, "errors": errors, "aborted": True}
    inserted = 0
    for doc in to_insert:
        await db.departments.insert_one(doc)
        inserted += 1
    await log_action(user, "Créer", "Département", f"Import Excel — {inserted} département(s)")
    return {"inserted": inserted, "errors": [], "aborted": False}

@api.get("/logs")
async def get_logs(
    limit: int = Query(300, ge=1, le=1000),
    company_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    user: dict = Depends(require_admin),
):
    """Read-only, workspace-scoped logs. Admin only."""
    return await list_logs_for_admin(
        db, user, limit=limit, company_id=company_id,
        event_type=event_type, severity=severity,
    )


@api.get("/journal", deprecated=True)
async def get_journal(user: dict = Depends(require_admin)):
    """P1.6 compatibility alias. Remove after frontend migration is complete."""
    logs = await list_logs_for_admin(db, user, limit=300)
    if logs:
        return logs
    # Transitional fallback before migrate_phase1_logs.py --commit. Scope even
    # legacy reads so one admin can never inspect another workspace's journal.
    workspace_id = user.get("workspace_id")
    query = {"workspace_id": workspace_id} if workspace_id else {}
    docs = await db.journal.find(query).sort("timestamp", -1).limit(300).to_list(300)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

def _acct_norm(s):
    import unicodedata
    s = str(s or "").replace("\xa0", " ")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.upper().split())

@api.get("/acct/summary")
async def acct_summary(year: int, month: int, user: dict = Depends(get_current_user)):
    rep = await _acct_report(year, month, "pnl")
    rev = ben = None
    for ln in rep["lines"]:
        n = _acct_norm(ln["label"])
        if rev is None and n == "TOTAL DES REVENUS":
            rev = ln["values"]
        if n.startswith("BENEFICE NET") and "PERTE" in n and "SELON" not in n:
            ben = ln["values"]
    keys = ["reel", "bud_ca", "bud_rev1"]
    if not rev or not ben:
        return {"period": rep["period"], "month_label": rep["month_label"], "year": rep["year"], "categories": []}
    cats = [
        {"label": "Revenus", "values": {k: rev.get(k, 0) for k in keys}},
        {"label": "Dépenses", "values": {k: round(rev.get(k, 0) - ben.get(k, 0), 2) for k in keys}},
        {"label": "Bénéfice net", "values": {k: ben.get(k, 0) for k in keys}},
    ]
    return {"period": rep["period"], "month_label": rep["month_label"], "year": rep["year"],
            "locked": rep["locked"], "categories": cats}

@api.get("/acct/trend")
async def acct_trend(user: dict = Depends(get_current_user)):
    periods = await db.acct_periods.find({"company_id": await _company_id("acct")}).sort("_id", 1).to_list(500)
    out = []
    for p in periods:
        bv = await db.acct_bv.find_one({"_id": p["_id"]})
        if not bv:
            continue
        try:
            rep = await _acct_report(p["year"], p["month"], "pnl")
        except Exception:
            continue
        net_m = net_c = rev_m = rev_c = cogs_c = baiia_c = None
        for ln in rep["lines"]:
            n = _acct_norm(ln["label"])
            if rev_c is None and n == "TOTAL DES REVENUS":
                rev_m = ln["values"].get("reel"); rev_c = ln["values"].get("cumulatif")
            if cogs_c is None and n.startswith("TOTAL") and "COUT DES MARCHANDISES VENDUES" in n:
                cogs_c = ln["values"].get("cumulatif")
            if baiia_c is None and "BAIIA" in n:
                baiia_c = ln["values"].get("cumulatif")
            if n.startswith("BENEFICE NET") and "PERTE" in n and "SELON" not in n:
                net_m = ln["values"].get("reel"); net_c = ln["values"].get("cumulatif")
        dep_m = round((rev_m or 0) - (net_m or 0), 2) if rev_m is not None and net_m is not None else None
        dep_c = round((rev_c or 0) - (net_c or 0), 2) if rev_c is not None and net_c is not None else None
        out.append({"period": p["_id"], "year": p["year"], "month": p["month"],
                    "month_label": MONTHS_FR[p["month"]-1],
                    "benefice_mois": net_m, "benefice_cumulatif": net_c,
                    "revenus_mois": rev_m, "revenus_cumulatif": rev_c,
                    "depenses_mois": dep_m, "depenses_cumulatif": dep_c,
                    "cogs_cumulatif": cogs_c, "baiia_cumulatif": baiia_c})
    return out

@api.get("/")
async def root():
    return {"message": "API Budget Salaires Pro"}

# ---------------------------------------------------------------------------
# Module Comptabilité (BV -> Bilan / États des résultats)
# ---------------------------------------------------------------------------
MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
BILAN_CFG = {"sheet": "Bilan Détaillé", "value_cols": {"cumulatif": "I"}, "account_col": "B", "label_col": "C",
             "stop_after": ["diff", "différence", "difference", "contrôle", "controle"]}
PNL_CFG = {"sheet": "Resultats internes", "account_col": "C", "label_col": "D", "stop_after": None,
           "stop_at": ["pour tableau"],
           "exclude": ["bénéfice net (perte nette) - selon", "contrôle"],
           "exclude_range": [("gestion demande", "marge brute - gd %")],
           "value_cols": {
               "reel": "E", "bud_rev2": "F", "ecart_rev2": "G", "bud_rev1": "I", "ecart_rev1": "J",
               "bud_ca": "L", "ecart_ca": "M", "reel_prec": "O",
               "cumulatif": "Q", "bud_rev2_cum": "R", "ecart_rev2_cum": "S", "bud_rev1_cum": "U",
               "ecart_rev1_cum": "V", "bud_ca_cum": "X", "ecart_ca_cum": "Y", "prec_cum": "AA"},
           "col_groups": [
               {"label": "Mois", "keys": ["reel", "bud_rev2", "ecart_rev2", "bud_rev1", "ecart_rev1", "bud_ca", "ecart_ca", "reel_prec"]},
               {"label": "Cumulatif (exercice à date)", "keys": ["cumulatif", "bud_rev2_cum", "ecart_rev2_cum", "bud_rev1_cum", "ecart_rev1_cum", "bud_ca_cum", "ecart_ca_cum", "prec_cum"]},
           ],
           "col_toggle_groups": [
               {"id": "ca", "label": "Budget CA", "keys": ["bud_ca", "ecart_ca", "bud_ca_cum", "ecart_ca_cum"]},
               {"id": "rev1", "label": "Budget Rév-1", "keys": ["bud_rev1", "ecart_rev1", "bud_rev1_cum", "ecart_rev1_cum"]},
               {"id": "rev2", "label": "Budget Rév-2", "keys": ["bud_rev2", "ecart_rev2", "bud_rev2_cum", "ecart_rev2_cum"]},
               {"id": "prec", "label": "Année précédente", "keys": ["reel_prec", "prec_cum"]},
           ]}
BV_FIELD_COLS = {"c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "i": 9, "j": 10, "k": 11, "l": 12, "m": 13}

PNL_SOMMAIRE_CFG = {
    "sheet": "Resultats sommaires", "account_col": "A", "label_col": "B", "stop_after": None,
    "stop_at": None, "exclude": None, "exclude_range": None,
    "value_cols": {
        "reel": "F", "bud_rev2": "G", "ecart_rev2": "H", "bud_rev1": "J", "ecart_rev1": "K",
        "bud_ca": "M", "ecart_ca": "N",
        "cumulatif": "P", "bud_rev2_cum": "Q", "ecart_rev2_cum": "R", "bud_rev1_cum": "T",
        "ecart_rev1_cum": "U", "bud_ca_cum": "W", "ecart_ca_cum": "X"},
    "col_groups": [
        {"label": "Mois", "keys": ["reel", "bud_rev2", "ecart_rev2", "bud_rev1", "ecart_rev1", "bud_ca", "ecart_ca"]},
        {"label": "Cumulatif (exercice à date)", "keys": ["cumulatif", "bud_rev2_cum", "ecart_rev2_cum", "bud_rev1_cum", "ecart_rev1_cum", "bud_ca_cum", "ecart_ca_cum"]},
    ],
    "col_toggle_groups": [
        {"id": "ca", "label": "Budget CA", "keys": ["bud_ca", "ecart_ca", "bud_ca_cum", "ecart_ca_cum"]},
        {"id": "rev1", "label": "Budget Rév-1", "keys": ["bud_rev1", "ecart_rev1", "bud_rev1_cum", "ecart_rev1_cum"]},
        {"id": "rev2", "label": "Budget Rév-2", "keys": ["bud_rev2", "ecart_rev2", "bud_rev2_cum", "ecart_rev2_cum"]},
    ]}


def _pkey(year, month):
    return f"{int(year):04d}-{int(month):02d}"

async def _load_engine():
    doc = await db.acct_template.find_one({"_id": "current"})
    if not doc:
        return None
    return ReportEngine.from_dict(doc["engine"])

def _parse_bv_xlsx(content):
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb["BV Détaillée"] if "BV Détaillée" in wb.sheetnames else wb.active
    accounts = []
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if not isinstance(a, (int, float)) or not float(a).is_integer():
            continue
        rec = {"account": int(a), "name": str(ws.cell(r, 2).value or "").strip()}
        for field, col in BV_FIELD_COLS.items():
            v = ws.cell(r, col).value
            rec[field] = float(v) if isinstance(v, (int, float)) else 0.0
        accounts.append(rec)
    return accounts

def _bv_dict(accounts, amap=None):
    bv = {a["account"]: {f: a.get(f, 0.0) for f in BV_FIELD_COLS} for a in accounts}
    # Affectation des nouveaux comptes : fusionne leurs montants dans le compte-cible mémorisé.
    if amap:
        for src, tgt in amap.items():
            src = int(src); tgt = int(tgt)
            if src in bv:
                dest = bv.setdefault(tgt, {f: 0.0 for f in BV_FIELD_COLS})
                for f in BV_FIELD_COLS:
                    dest[f] = dest.get(f, 0.0) + bv[src].get(f, 0.0)
    return bv

async def _account_map():
    doc = await db.acct_account_map.find_one({"_id": "current"})
    return {k: v for k, v in (doc.get("map", {}) if doc else {}).items()}

def _unassigned(accounts, tmpl_accts, amap):
    return [{"account": a["account"], "name": a["name"]} for a in accounts
            if a["account"] not in tmpl_accts and str(a["account"]) not in amap
            and any(abs(a.get(f, 0.0)) > 0.005 for f in BV_FIELD_COLS)]

# Grand livre détaillé. Détection des colonnes par en-tête (compatible modèle standard
# et export complet : Type|Période|Date|Numéro|Description|Compte|Description|Débit|Crédit).
# Écritures en double partie : montant = débit - crédit. Filtrage par mois/année si fournis.
def _parse_ledger_xlsx(content, year=None, month=None):
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    header_row = None; headers = []
    for r in range(1, min(15, ws.max_row) + 1):
        rh = [(str(ws.cell(r, c).value).strip().lower(), c) for c in range(1, ws.max_column + 1)
              if isinstance(ws.cell(r, c).value, str) and str(ws.cell(r, c).value).strip()]
        names = [h[0] for h in rh]
        if any("compte" in n for n in names) and any(("bit" in n or "dit" in n) for n in names):
            header_row = r; headers = rh; break
    if header_row is None:
        return []
    def find(pred):
        for name, c in headers:
            if pred(name):
                return c
        return None
    c_compte = find(lambda n: "compte" in n)
    c_date = find(lambda n: "date" in n)
    c_debit = find(lambda n: "débit" in n or "debit" in n)
    c_credit = find(lambda n: "crédit" in n or "credit" in n)
    c_numero = find(lambda n: "numéro" in n or "numero" in n or "n°" in n)
    c_type = find(lambda n: n == "type" or n.startswith("type"))
    desc_cols = sorted([c for name, c in headers if ("description" in name or "libell" in name)])
    c_payee = next((c for c in desc_cols if c < (c_compte or 9999)), None)
    c_acctname = next((c for c in desc_cols if c > (c_compte or 0)), None)
    txns = []
    for r in range(header_row + 1, ws.max_row + 1):
        av = ws.cell(r, c_compte).value if c_compte else None
        if not isinstance(av, (int, float)) or not float(av).is_integer():
            continue
        acct = int(av)
        dv = ws.cell(r, c_date).value if c_date else None
        if isinstance(dv, datetime):
            dt = dv; date_s = dv.date().isoformat()
        else:
            dt = None; date_s = str(dv).strip() if dv is not None else ""
        if year and month and dt is not None and not (dt.year == int(year) and dt.month == int(month)):
            continue
        payee = str(ws.cell(r, c_payee).value or "").strip() if c_payee else ""
        acctname = str(ws.cell(r, c_acctname).value or "").strip() if c_acctname else ""
        desc = payee or acctname
        dbt = ws.cell(r, c_debit).value if c_debit else None; dbt = float(dbt) if isinstance(dbt, (int, float)) else 0.0
        crd = ws.cell(r, c_credit).value if c_credit else None; crd = float(crd) if isinstance(crd, (int, float)) else 0.0
        if dbt == 0 and crd == 0:
            continue
        numero = None
        if c_numero:
            nv = ws.cell(r, c_numero).value
            if nv is not None and str(nv).strip():
                numero = str(int(nv)) if isinstance(nv, float) and float(nv).is_integer() else str(nv).strip()
        etype = str(ws.cell(r, c_type).value or "").strip() if c_type else ""
        rec = {"account": acct, "date": date_s, "description": desc,
               "debit": round(dbt, 2), "credit": round(crd, 2), "amount": round(dbt - crd, 2)}
        if numero:
            rec["numero"] = numero
        if etype:
            rec["type"] = etype
        txns.append(rec)
    return txns

@api.post("/acct/template")
async def acct_upload_template(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    content = await file.read()
    try:
        eng = ReportEngine.from_template(io.BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Modèle Excel invalide (.xlsx attendu)")
    if "Bilan Détaillé" not in eng.sheets or "Resultats internes" not in eng.sheets:
        raise HTTPException(status_code=400, detail="Le modèle doit contenir les feuilles « Bilan Détaillé » et « Resultats internes »")
    accts = sorted(a for a in eng.template_accounts() if a is not None)
    names = eng.account_names()
    await db.acct_template.replace_one({"_id": "current"}, {
        "_id": "current", "engine": eng.to_dict(), "accounts": accts,
        "account_names": {str(k): v for k, v in names.items()},
        "imported_at": datetime.now(timezone.utc).isoformat(), "imported_by": user["email"],
    }, upsert=True)
    await log_action(user, "Créer", "Comptabilité", f"Import modèle — {len(accts)} comptes mappés")
    return {"success": True, "account_count": len(accts)}

@api.get("/acct/template")
async def acct_get_template(user: dict = Depends(get_current_user)):
    doc = await db.acct_template.find_one({"_id": "current"})
    if not doc:
        return {"imported": False}
    return {"imported": True, "account_count": len(doc.get("accounts", [])),
            "imported_at": doc.get("imported_at"), "imported_by": doc.get("imported_by")}

@api.post("/acct/bv")
async def acct_upload_bv(year: int, month: int, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})
    if period and period.get("locked"):
        raise HTTPException(status_code=403, detail=f"Le mois {MONTHS_FR[month-1]} {year} est verrouillé — aucun nouvel upload permis.")
    content = await file.read()
    try:
        accounts = _parse_bv_xlsx(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier BV invalide (.xlsx attendu)")
    if not accounts:
        raise HTTPException(status_code=400, detail="Aucun compte détecté dans la BV (colonne A = n° de compte, B = nom, C = mouvement, I = cumulatif)")
    eng = await _load_engine()
    balanced = None; diff = None; net_control = None; unassigned = []
    if eng:
        amap = await _account_map()
        bv = _bv_dict(accounts, amap)
        comp = eng.compute_all(bv)
        diff = round(comp("Bilan Détaillé", "I", 174), 2)   # TOTAL PASSIF+CAPITAUX − TOTAL ACTIF
        net_control = round(comp("Resultats internes", "E", 559), 2)  # doit être ~0
        balanced = abs(diff) < 1.0
        tmpl_accts = set(eng.template_accounts())
        unassigned = _unassigned(accounts, tmpl_accts, amap)
    await db.acct_bv.replace_one({"_id": pk}, {
        "_id": pk, "year": int(year), "month": int(month), "accounts": accounts,
        "uploaded_at": datetime.now(timezone.utc).isoformat(), "uploaded_by": user["email"],
    }, upsert=True)
    await db.acct_periods.update_one({"_id": pk}, {"$set": {
        "_id": pk, "year": int(year), "month": int(month),
        "last_upload_at": datetime.now(timezone.utc).isoformat(), "last_upload_by": user["email"],
        "balanced": balanced, "diff": diff, "net_control": net_control,
        "new_accounts": unassigned, "account_count": len(accounts),
    }, "$setOnInsert": {"locked": False, "lock_history": []}}, upsert=True)
    await log_action(user, "Créer", "Comptabilité", f"Upload BV {pk} — {len(accounts)} comptes")
    return {"success": True, "period": pk, "account_count": len(accounts),
            "balanced": balanced, "diff": diff, "net_control": net_control, "new_accounts": unassigned,
            "requires_assignment": len(unassigned) > 0, "template_imported": eng is not None}

@api.get("/acct/periods")
async def acct_periods(user: dict = Depends(get_current_user)):
    docs = await db.acct_periods.find({"company_id": await _company_id("acct")}).sort("_id", -1).to_list(500)
    for d in docs:
        d["id"] = d.pop("_id")
    return docs

@api.post("/acct/period/lock")
async def acct_lock(year: int, month: int, locked: bool = True, user: dict = Depends(require_admin)):
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})
    if not period:
        raise HTTPException(status_code=404, detail="Aucune donnée pour ce mois")
    entry = {"locked": locked, "by": user["email"], "at": datetime.now(timezone.utc).isoformat()}
    await db.acct_periods.update_one({"_id": pk}, {"$set": {"locked": locked}, "$push": {"lock_history": entry}})
    await log_action(user, "Modifier", "Comptabilité", f"{'Verrouillage' if locked else 'Déverrouillage'} mois {pk}")
    return {"success": True, "locked": locked}

@api.delete("/acct/period")
async def acct_delete_period(year: int, month: int, user: dict = Depends(require_admin)):
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})
    if not period:
        raise HTTPException(status_code=404, detail="Aucune donnée pour ce mois")
    if period.get("locked"):
        raise HTTPException(status_code=403, detail=f"Le mois {MONTHS_FR[month-1]} {year} est verrouillé — suppression impossible.")
    await db.acct_bv.delete_one({"_id": pk})
    await db.acct_periods.delete_one({"_id": pk})
    await db.acct_ledger.delete_one({"_id": pk})
    await log_action(user, "Supprimer", "Comptabilité", f"Suppression BV {pk}")
    return {"success": True, "period": pk}

LEDGER_HEADERS = ["Type", "Période", "Date", "Numéro", "Description", "Compte", "Description", "Débit", "Crédit"]

@api.get("/acct/ledger/template")
async def acct_ledger_template(user: dict = Depends(get_current_user)):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Transactions"
    ws.append(LEDGER_HEADERS)
    for c in ws[1]:
        c.font = openpyxl.styles.Font(bold=True)
    ws.append(["C", 1, "2026-01-02", 20126, "Shred-it", 1001060, "VISA - cartes de crédit", 0, 218.91])
    ws.append(["C", 1, "2026-01-02", 20126, "Shred-it", 2002100, "Comptes à payer", 218.91, 0])
    ws.append(["E", 1, "2026-01-15", 15012, "Facturation contrat #1042", 4504500, "Revenus - Service énergie", 0, 18500.00])
    for col, w in {"A": 8, "B": 9, "C": 13, "D": 12, "E": 32, "F": 12, "G": 30, "H": 13, "I": 13}.items():
        ws.column_dimensions[col].width = w
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=modele_grand_livre_detaille.xlsx"})

@api.post("/acct/ledger")
async def acct_upload_ledger(year: int, month: int, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})
    if period and period.get("locked"):
        raise HTTPException(status_code=403, detail=f"Le mois {MONTHS_FR[month-1]} {year} est verrouillé — aucun nouvel upload permis.")
    content = await file.read()
    try:
        txns = _parse_ledger_xlsx(content, year, month)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier de grand livre invalide (.xlsx attendu). En-têtes attendus : Compte, Date, Description, Débit, Crédit.")
    if not txns:
        raise HTTPException(status_code=400, detail=f"Aucune transaction pour {MONTHS_FR[month-1]} {year} dans ce fichier. Vérifiez le mois sélectionné et les colonnes (Compte, Date, Débit, Crédit).")
    # Étape 1 (déterministe, sans IA) : agrégation par compte pour la période.
    totals = {}
    for t in txns:
        g = totals.setdefault(t["account"], {"debit": 0.0, "credit": 0.0, "amount": 0.0, "count": 0})
        g["debit"] = round(g["debit"] + t["debit"], 2)
        g["credit"] = round(g["credit"] + t["credit"], 2)
        g["amount"] = round(g["amount"] + t["amount"], 2)
        g["count"] += 1
    account_totals = {str(k): v for k, v in totals.items()}
    now = datetime.now(timezone.utc).isoformat()
    await db.acct_ledger.replace_one({"_id": pk}, {
        "_id": pk, "year": int(year), "month": int(month), "transactions": txns,
        "account_totals": account_totals,
        "uploaded_at": now, "uploaded_by": user["email"],
    }, upsert=True)
    await db.acct_periods.update_one({"_id": pk}, {"$set": {
        "_id": pk, "year": int(year), "month": int(month),
        "ledger_count": len(txns), "ledger_accounts": len(totals),
        "ledger_uploaded_at": now, "ledger_uploaded_by": user["email"],
    }, "$setOnInsert": {"locked": False, "lock_history": []}}, upsert=True)
    await log_action(user, "Créer", "Comptabilité", f"Upload grand livre détaillé {pk} — {len(txns)} transactions")
    return {"success": True, "period": pk, "transaction_count": len(txns), "account_count": len(totals)}

def _ledger_account_totals(txns):
    totals = {}
    for t in txns:
        g = totals.setdefault(t["account"], {"debit": 0.0, "credit": 0.0, "amount": 0.0, "count": 0})
        g["debit"] = round(g["debit"] + t["debit"], 2)
        g["credit"] = round(g["credit"] + t["credit"], 2)
        g["amount"] = round(g["amount"] + t["amount"], 2)
        g["count"] += 1
    return {str(k): v for k, v in totals.items()}

@api.post("/acct/ledger/import-all")
async def acct_upload_ledger_all(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    try:
        txns = _parse_ledger_xlsx(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier de grand livre invalide (.xlsx attendu). En-têtes attendus : Compte, Date, Description, Débit, Crédit.")
    if not txns:
        raise HTTPException(status_code=400, detail="Aucune transaction détectée. Vérifiez les colonnes (Compte, Date, Débit, Crédit).")
    groups = {}
    for t in txns:
        d = t.get("date") or ""
        if len(d) >= 7 and d[4] == "-":
            try:
                y = int(d[:4]); m = int(d[5:7])
            except ValueError:
                continue
            groups.setdefault((y, m), []).append(t)
    now = datetime.now(timezone.utc).isoformat()
    imported, skipped_locked, skipped_small = [], [], []
    THRESH = 10
    for (y, m), tl in sorted(groups.items()):
        pk = _pkey(y, m)
        if len(tl) < THRESH:
            skipped_small.append({"period": pk, "count": len(tl)}); continue
        period = await db.acct_periods.find_one({"_id": pk})
        if period and period.get("locked"):
            skipped_locked.append({"period": pk, "count": len(tl)}); continue
        at = _ledger_account_totals(tl)
        await db.acct_ledger.replace_one({"_id": pk}, {
            "_id": pk, "year": y, "month": m, "transactions": tl,
            "account_totals": at, "uploaded_at": now, "uploaded_by": user["email"],
        }, upsert=True)
        await db.acct_periods.update_one({"_id": pk}, {"$set": {
            "_id": pk, "year": y, "month": m, "ledger_count": len(tl), "ledger_accounts": len(at),
            "ledger_uploaded_at": now, "ledger_uploaded_by": user["email"],
        }, "$setOnInsert": {"locked": False, "lock_history": []}}, upsert=True)
        imported.append({"period": pk, "count": len(tl)})
    await log_action(user, "Créer", "Comptabilité", f"Import grand livre (toutes périodes) — {len(imported)} mois, {len(txns)} transactions")
    return {"success": True, "imported": imported, "skipped_locked": skipped_locked,
            "skipped_small": skipped_small, "total_transactions": len(txns)}

def _ledger_unusual_idx(txns):
    """Indices des transactions atypiques (aberrations IQR par compte, déterministe)."""
    by_acct = {}
    for i, t in enumerate(txns):
        by_acct.setdefault(t.get("account"), []).append((i, t.get("amount") or 0))
    unusual = set()
    for acct, items in by_acct.items():
        amts = sorted(a for _i, a in items)
        n = len(amts)
        if n < 4:
            continue
        def pct(p):
            k = p * (n - 1); lo = int(k); frac = k - lo
            return amts[lo] + (amts[min(lo + 1, n - 1)] - amts[lo]) * frac
        q1, q3 = pct(0.25), pct(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo_b, hi_b = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for gi, a in items:
            if a < lo_b or a > hi_b:
                unusual.add(gi)
    return unusual


@api.get("/acct/ledger/transactions")
async def acct_ledger_transactions(year: int, month: int, q: str = "", unusual_only: bool = False, skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    doc = await db.acct_ledger.find_one({"_id": pk})
    if not doc:
        raise HTTPException(status_code=404, detail="Aucun grand livre détaillé pour ce mois")
    all_txns = doc.get("transactions", [])
    unusual = _ledger_unusual_idx(all_txns)
    indexed = [{**t, "idx": i, "unusual": (i in unusual)} for i, t in enumerate(all_txns)]
    ql = (q or "").strip().lower()
    if ql:
        indexed = [t for t in indexed if ql in str(t.get("account", "")).lower() or ql in (t.get("description") or "").lower()]
    if unusual_only:
        indexed = [t for t in indexed if t["unusual"]]
    total = len(indexed)
    page = indexed[skip:skip + min(limit, 500)]
    return {"period": pk, "total": total, "skip": skip, "limit": limit, "transactions": page,
            "account_count": len(doc.get("account_totals", {})), "grand_total": len(all_txns), "unusual_total": len(unusual)}


@api.get("/acct/ledger/entry")
async def acct_ledger_entry(year: int, month: int, index: int, user: dict = Depends(get_current_user)):
    """Reconstitue l'écriture complète (toutes les lignes débit/crédit) d'une transaction.
    Regroupe par « numéro » si disponible, sinon par plage contiguë partageant date + description."""
    pk = _pkey(year, month)
    doc = await db.acct_ledger.find_one({"_id": pk})
    if not doc:
        raise HTTPException(status_code=404, detail="Aucun grand livre détaillé pour ce mois")
    txns = doc.get("transactions", [])
    if index < 0 or index >= len(txns):
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    base = txns[index]
    group_by = "numero" if base.get("numero") else "date_description"
    if group_by == "numero":
        lines = [{**t, "idx": i} for i, t in enumerate(txns) if t.get("numero") == base["numero"]]
    else:
        key = (base.get("date"), base.get("description"))
        lo = index
        while lo - 1 >= 0 and (txns[lo - 1].get("date"), txns[lo - 1].get("description")) == key:
            lo -= 1
        hi = index
        while hi + 1 < len(txns) and (txns[hi + 1].get("date"), txns[hi + 1].get("description")) == key:
            hi += 1
        lines = [{**txns[i], "idx": i} for i in range(lo, hi + 1)]
    total_debit = round(sum(l.get("debit") or 0 for l in lines), 2)
    total_credit = round(sum(l.get("credit") or 0 for l in lines), 2)
    return {"period": pk, "group_by": group_by,
            "numero": base.get("numero"), "type": base.get("type"),
            "date": base.get("date"), "description": base.get("description"),
            "lines": lines, "total_debit": total_debit, "total_credit": total_credit,
            "balanced": abs(total_debit - total_credit) < 0.01}


# ---- Commentaires sur les lignes du P&L / Bilan ----
def _comment_out(d):
    return {"id": str(d["_id"]), "report": d["report"], "account": d["account"], "text": d["text"],
            "author": d["author"], "author_name": d.get("author_name") or d["author"],
            "year": d["year"], "month": d["month"], "month_label": MONTHS_FR[d["month"] - 1],
            "created_at": d["created_at"], "updated_at": d.get("updated_at")}


@api.get("/acct/line-comments")
async def acct_line_comments(report: str, account: int, user: dict = Depends(get_current_user)):
    docs = await db.acct_line_comments.find({"report": report, "account": account}).sort("created_at", 1).to_list(1000)
    return [_comment_out(d) for d in docs]


@api.get("/acct/line-comments/counts")
async def acct_line_comment_counts(report: str, user: dict = Depends(get_current_user)):
    rows = await db.acct_line_comments.aggregate(
        [{"$match": {"report": report}}, {"$group": {"_id": "$account", "count": {"$sum": 1}}}]
    ).to_list(10000)
    return {"counts": {str(r["_id"]): r["count"] for r in rows}}


class LineCommentBody(BaseModel):
    report: str
    account: int
    text: str
    year: int
    month: int


class LineCommentEdit(BaseModel):
    text: str


@api.post("/acct/line-comments")
async def acct_add_line_comment(body: LineCommentBody, user: dict = Depends(get_current_user)):
    if body.report not in ("pnl", "bilan"):
        raise HTTPException(status_code=400, detail="Rapport invalide")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Commentaire vide")
    now = datetime.now(timezone.utc).isoformat()
    doc = {"_id": ObjectId(), "report": body.report, "account": body.account, "text": text[:2000],
           "author": user["email"], "author_name": user.get("name") or user["email"],
           "year": body.year, "month": body.month, "created_at": now,
           "company_id": await _company_id("acct")}
    await db.acct_line_comments.insert_one(doc)
    await log_action(user, "Ajouter", "Commentaire", f"{body.report} · compte {body.account}")
    return _comment_out(doc)


@api.put("/acct/line-comments/{cid}")
async def acct_edit_line_comment(cid: str, body: LineCommentEdit, user: dict = Depends(get_current_user)):
    doc = await db.acct_line_comments.find_one({"_id": _oid(cid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    if doc["author"] != user["email"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Seul l'auteur ou un administrateur peut modifier ce commentaire")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Commentaire vide")
    await db.acct_line_comments.update_one({"_id": doc["_id"]}, {"$set": {"text": text[:2000], "updated_at": datetime.now(timezone.utc).isoformat()}})
    return _comment_out({**doc, "text": text[:2000], "updated_at": datetime.now(timezone.utc).isoformat()})


@api.delete("/acct/line-comments/{cid}")
async def acct_del_line_comment(cid: str, user: dict = Depends(get_current_user)):
    doc = await db.acct_line_comments.find_one({"_id": _oid(cid)})
    if not doc:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    if doc["author"] != user["email"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Seul l'auteur ou un administrateur peut supprimer ce commentaire")
    await db.acct_line_comments.delete_one({"_id": doc["_id"]})
    return {"ok": True}



@api.get("/acct/ledger/status")
async def acct_ledger_status(year: int, month: int, user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    pk = _pkey(year, month)
    doc = await db.acct_ledger.find_one({"_id": pk})
    if not doc:
        return {"imported": False, "period": pk}
    return {"imported": True, "period": pk, "transaction_count": len(doc.get("transactions", [])),
            "uploaded_at": doc.get("uploaded_at"), "uploaded_by": doc.get("uploaded_by")}

@api.delete("/acct/ledger")
async def acct_delete_ledger(year: int, month: int, user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})
    if period and period.get("locked"):
        raise HTTPException(status_code=403, detail=f"Le mois {MONTHS_FR[month-1]} {year} est verrouillé — suppression impossible.")
    doc = await db.acct_ledger.find_one({"_id": pk})
    if not doc:
        raise HTTPException(status_code=404, detail="Aucun grand livre détaillé pour ce mois")
    await db.acct_ledger.delete_one({"_id": pk})
    await db.acct_periods.update_one({"_id": pk}, {"$unset": {"ledger_count": "", "ledger_uploaded_at": "", "ledger_uploaded_by": ""}})
    await log_action(user, "Supprimer", "Comptabilité", f"Suppression grand livre détaillé {pk}")
    return {"success": True, "period": pk}


@api.get("/acct/accounts")
async def acct_accounts(user: dict = Depends(get_current_user)):
    doc = await db.acct_template.find_one({"_id": "current"})
    if not doc:
        return []
    names = doc.get("account_names", {})
    return [{"account": a, "name": names.get(str(a), "")} for a in doc.get("accounts", [])]

class AccountAssign(BaseModel):
    assignments: dict  # {new_account: target_account}

@api.post("/acct/account-map")
async def acct_account_map(payload: AccountAssign, year: Optional[int] = None, month: Optional[int] = None, user: dict = Depends(get_current_user)):
    doc = await db.acct_account_map.find_one({"_id": "current"})
    amap = dict(doc.get("map", {})) if doc else {}
    for k, v in payload.assignments.items():
        if v is None or v == "":
            amap.pop(str(k), None)
        else:
            amap[str(int(k))] = int(v)
    await db.acct_account_map.replace_one({"_id": "current"}, {"_id": "current", "map": amap}, upsert=True)
    await log_action(user, "Modifier", "Comptabilité", f"Affectation de {len(payload.assignments)} compte(s)")
    # Recalcule le statut de la période courante si fournie (pour lever le blocage)
    if year and month:
        pk = _pkey(year, month)
        bvdoc = await db.acct_bv.find_one({"_id": pk})
        eng = await _load_engine()
        if bvdoc and eng:
            bv = _bv_dict(bvdoc["accounts"], amap)
            comp = eng.compute_all(bv)
            diff = round(comp("Bilan Détaillé", "I", 174), 2)
            tmpl = set(eng.template_accounts())
            unassigned = _unassigned(bvdoc["accounts"], tmpl, amap)
            await db.acct_periods.update_one({"_id": pk}, {"$set": {"balanced": abs(diff) < 1.0, "diff": diff, "new_accounts": unassigned}})
    return {"success": True, "count": len(amap)}

async def _acct_report(year, month, kind):
    eng = await _load_engine()
    if not eng:
        raise HTTPException(status_code=400, detail="Aucun modèle importé. Un administrateur doit d'abord importer le modèle Excel.")
    pk = _pkey(year, month)
    bvdoc = await db.acct_bv.find_one({"_id": pk})
    if not bvdoc:
        raise HTTPException(status_code=404, detail=f"Aucune BV uploadée pour {MONTHS_FR[month-1]} {year}")
    period = await db.acct_periods.find_one({"_id": pk})
    amap = await _account_map()
    bv = _bv_dict(bvdoc["accounts"], amap)
    cfg = {"bilan": BILAN_CFG, "pnl": PNL_CFG, "pnl_sommaire": PNL_SOMMAIRE_CFG}[kind]
    lines = eng.build_report(bv, cfg["sheet"], cfg["value_cols"], cfg["account_col"], cfg["label_col"], cfg.get("stop_after"), cfg.get("stop_at"), cfg.get("exclude"), cfg.get("exclude_range"))
    if kind == "pnl_sommaire":
        lines = [l for l in lines if (l.get("label") or "").strip()]
    return {"period": pk, "year": int(year), "month": int(month), "month_label": MONTHS_FR[month-1],
            "kind": kind, "value_cols": list(cfg["value_cols"].keys()), "col_groups": cfg.get("col_groups"),
            "col_toggle_groups": cfg.get("col_toggle_groups"),
            "locked": bool(period and period.get("locked")),
            "balanced": period.get("balanced") if period else None,
            "lines": lines}

async def _bilan_sommaire_data(year, month):
    eng = await _load_engine()
    if not eng:
        raise HTTPException(status_code=400, detail="Aucun modèle importé.")
    pk = _pkey(year, month)
    bvdoc = await db.acct_bv.find_one({"_id": pk})
    if not bvdoc:
        raise HTTPException(status_code=404, detail=f"Aucune BV uploadée pour {MONTHS_FR[month-1]} {year}")
    if "Bilan Sommaire" not in eng.sheets:
        raise HTTPException(status_code=400, detail="Le modèle importé ne contient pas la feuille « Bilan Sommaire ».")
    period = await db.acct_periods.find_one({"_id": pk})
    amap = await _account_map()
    bv = _bv_dict(bvdoc["accounts"], amap)
    comp = eng.compute_all(bv)
    sd = eng.sheets["Bilan Sommaire"]

    def build_side(lbl_col, val_col, r_lo, r_hi):
        out = []
        for r in range(r_lo, r_hi + 1):
            cells = sd["rows"].get(r) or {}
            lbl = cells.get(lbl_col)
            if lbl is None:
                continue
            label = str(lbl).strip()
            raw = cells.get(val_col)
            has_val = raw is not None
            val = round(comp("Bilan Sommaire", val_col, r), 2) if has_val else None
            low = label.lower()
            if low.startswith("total"):
                kind = "total"
            elif not has_val:
                kind = "header"
            else:
                kind = "data"
            out.append({"label": label, "value": val, "kind": kind, "style": sd.get("style", {}).get(r)})
        return out

    actif = build_side("B", "C", 6, 32)
    passif = build_side("E", "F", 6, 32)
    return {"period": pk, "year": int(year), "month": int(month), "month_label": MONTHS_FR[month-1],
            "kind": "bilan_sommaire",
            "locked": bool(period and period.get("locked")),
            "actif": actif, "passif": passif,
            "total_actif": round(comp("Bilan Sommaire", "C", 32), 2),
            "total_passif": round(comp("Bilan Sommaire", "F", 32), 2),
            "validation": round(comp("Bilan Sommaire", "C", 35), 2)}

@api.get("/acct/report")
async def acct_report(type: str, year: int, month: int, user: dict = Depends(get_current_user)):
    if type == "bilan_sommaire":
        return await _bilan_sommaire_data(year, month)
    if type not in ("bilan", "pnl", "pnl_sommaire"):
        raise HTTPException(status_code=400, detail="Type invalide")
    return await _acct_report(year, month, type)

PNL_PCT_LABELS = {
    "Matériels Projets/Revenus Projets", "Sous-traitance projets/Revenus Projets",
    "Coût main d'œuvre direct projets/Revenus Projets", "FGF projets/Revenus Projets",
    "Marge Brute - Projet - %", "Marge très brute - Projets",
    "Matériel Services vs Revenus Services", "Sous-traitance Services vs Revenus Services",
    "Salaires Services vs Revenus Services", "Marge Brute - Service %", "Marge Brute Globale - %",
}

@api.get("/acct/report/pnl-monthly")
async def acct_pnl_monthly(year: int, variant: str = "detail", user: dict = Depends(get_current_user)):
    """État des résultats avec chaque mois de l'année en colonne. Réutilise le moteur P&L par mois.
    variant: 'detail' (Resultats internes) ou 'sommaire' (Resultats sommaires)."""
    kind = "pnl_sommaire" if variant == "sommaire" else "pnl"
    months = list(range(1, 13))
    per = {p["month"]: p for p in await db.acct_periods.find({"year": int(year), "company_id": await _company_id("acct")}).to_list(200)}
    reports = {}
    for m in months:
        try:
            reports[m] = await _acct_report(year, m, kind)
        except HTTPException:
            reports[m] = None
    base = next((r for r in reports.values() if r), None)
    if not base:
        return {"year": int(year), "months": [], "lines": [], "empty": True}
    base_lines = base["lines"]
    # Alignement par clé stable `row` (le nombre/ordre de lignes peut varier selon le mois).
    row_maps = {m: ({l.get("row"): l for l in reports[m]["lines"]} if reports[m] else {}) for m in months}
    last_r = next((reports[m] for m in reversed(months) if reports[m]), None)
    last_row_map = ({l.get("row"): l for l in last_r["lines"]} if last_r else {})
    labels = [(ln.get("label") or "").strip() for ln in base_lines]
    baiia_idx = next((i for i, l in enumerate(labels) if "BAIIA" in l), -1)
    is_detail = (variant != "sommaire")
    out_lines = []
    for i, ln in enumerate(base_lines):
        rk = ln.get("row")
        is_pct = is_detail and ((labels[i] in PNL_PCT_LABELS) or (baiia_idx >= 0 and i == baiia_idx + 1))
        vals = {}
        for m in months:
            lm = row_maps[m].get(rk)
            vals[str(m)] = (lm["values"].get("reel") if lm else 0.0) or 0.0
        if ln["kind"] != "header":
            if is_pct:
                lr = last_row_map.get(rk)
                vals["total"] = round(((lr["values"].get("cumulatif") if lr else 0.0) or 0.0), 6)
            else:
                vals["total"] = round(sum(vals[str(m)] for m in months), 2)
        out_lines.append({"account": ln["account"], "label": ln["label"], "kind": ln["kind"],
                          "style": ln.get("style"), "row": rk, "is_pct": is_pct, "values": vals})
    month_meta = [{"month": m, "label": MONTHS_FR[m - 1], "short": MONTHS[m - 1],
                   "locked": bool(per.get(m, {}).get("locked")), "has_data": reports[m] is not None} for m in months]
    return {"year": int(year), "months": month_meta, "lines": out_lines, "empty": False}

# ---------------------------------------------------------------------------
# Responsables budgétaires (mapping responsable -> comptes) + rapport par responsable
# ---------------------------------------------------------------------------
class BudgetManager(BaseModel):
    name: str
    email: str = ""
    accounts: List[str] = []
    active: bool = True

@api.get("/acct/budget-managers")
async def list_budget_managers(user: dict = Depends(get_current_user)):
    docs = await db.acct_budget_managers.find().sort("name", 1).to_list(500)
    return [{"id": str(d["_id"]), "name": d.get("name", ""), "email": d.get("email", ""),
             "accounts": d.get("accounts", []), "active": d.get("active", True)} for d in docs]

@api.post("/acct/budget-managers")
async def create_budget_manager(payload: BudgetManager, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    doc = payload.model_dump()
    doc["company_id"] = await _company_id("acct")
    res = await db.acct_budget_managers.insert_one(dict(doc))
    await log_action(user, "Créer", "Responsable budgétaire", payload.name)
    return {"id": str(res.inserted_id), **payload.model_dump()}

@api.put("/acct/budget-managers/{mid}")
async def update_budget_manager(mid: str, payload: BudgetManager, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    r = await db.acct_budget_managers.update_one({"_id": _oid(mid)}, {"$set": payload.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Responsable introuvable")
    await log_action(user, "Modifier", "Responsable budgétaire", payload.name)
    return {"id": mid, **payload.model_dump()}

@api.delete("/acct/budget-managers/{mid}")
async def delete_budget_manager(mid: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    d = await db.acct_budget_managers.find_one({"_id": _oid(mid)})
    await db.acct_budget_managers.delete_one({"_id": _oid(mid)})
    await log_action(user, "Supprimer", "Responsable budgétaire", (d or {}).get("name", mid))
    return {"success": True}

REV_MONTH_KEY = {"ca": "bud_ca", "rev1": "bud_rev1", "rev2": "bud_rev2"}
REV_CUM_KEY = {"ca": "bud_ca_cum", "rev1": "bud_rev1_cum", "rev2": "bud_rev2_cum"}
REV_LABEL = {"ca": "CA", "rev1": "REV-1", "rev2": "REV-2"}

BUDGET_MANAGERS_SEED = [
    {"name": "RH", "email": "bbindanda@accslegroupe.ca", "accounts": ["8006600", "8006610", "8006630", "8006640", "8006645", "8006650", "8006655", "8006660", "8006665", "8006670", "8006675"], "active": True},
    {"name": "TI", "email": "bbindanda@accslegroupe.ca", "accounts": ["7006500", "7006410", "7006510", "7006520", "7006530", "7006540", "7006550", "7006560", "7006565", "7005500", "7006400", "7505500", "5005500", "5505500", "5995500", "6005500", "8505500", "8005500", "9005500"], "active": True},
    {"name": "MARKETING", "email": "bbindanda@accslegroupe.ca", "accounts": ["8506720", "8506721", "8506722", "8506723", "8506730", "8506731", "8506732", "8506733", "8506734", "8506740", "8506741", "8506742", "8506743", "8506750", "8506751", "8506752", "8506753", "8506754", "8506755", "8506756", "8506760", "8506761", "8506762", "8506763", "8507000", "8507001", "8507002", "8507003"], "active": True},
    {"name": "FGF", "email": "bbindanda@accslegroupe.ca", "accounts": ["5005210", "5505210", "5995210", "9005210", "5995050", "5995060", "5995070", "5995080", "5995100", "5995110", "5995140", "5995150", "5995160", "5995220", "5995230", "5995240", "5995500", "5996400", "5996410", "5996420", "5996430", "5996440", "5996450", "5997000", "5997115", "5997120", "5997125"], "active": True},
]

async def _by_manager_data(manager_id, year, month, rev="rev1"):
    """Reproduit le modèle « Suivi Budget frais d'exploitation - <responsable> » :
    No GL | Désignation | Réel (Cumulatif) | Budget (à date) | Budget (Annuel) | Écart | Notes.
    Réel cum = P&L cumulatif ; Budget à date = P&L budget cumulatif ; Annuel = budget mensuel × 12 ;
    Écart = Annuel − Réel cumulatif (budget annuel restant)."""
    if rev not in REV_CUM_KEY:
        rev = "rev1"
    mgr = await db.acct_budget_managers.find_one({"_id": _oid(manager_id)})
    if not mgr:
        raise HTTPException(status_code=404, detail="Responsable introuvable")
    rep = await _acct_report(year, month, "pnl")
    cum_key = REV_CUM_KEY[rev]
    mon_key = REV_MONTH_KEY[rev]
    accts = [str(a).strip() for a in (mgr.get("accounts") or []) if str(a).strip()]
    acct_set = set(accts)
    by_acct = {str(ln.get("account") or ""): ln for ln in rep["lines"]}
    # Notes par compte pour cette période (partagées entre rapports, éditables par tous).
    notes = {}
    async for nd in db.acct_manager_notes.find({"year": int(year), "month": int(month), "account": {"$in": accts}}):
        notes[str(nd["account"])] = nd.get("text", "")
    lines = []
    tot = {"reel": 0.0, "budget": 0.0, "annuel": 0.0, "ecart": 0.0}
    for a in accts:
        ln = by_acct.get(a)
        if not ln:
            lines.append({"account": a, "label": "(compte absent du P&L)", "reel": 0.0,
                          "budget": 0.0, "annuel": 0.0, "ecart": 0.0, "note": notes.get(a, "")})
            continue
        v = ln.get("values") or {}
        reel = round(v.get("cumulatif") or 0.0, 2)
        budget = round(v.get(cum_key) or 0.0, 2)
        annuel = round((v.get(mon_key) or 0.0) * 12, 2)
        ecart = round(annuel - reel, 2)
        lines.append({"account": a, "label": ln.get("label") or "", "reel": reel,
                      "budget": budget, "annuel": annuel, "ecart": ecart, "note": notes.get(a, "")})
        tot["reel"] += reel; tot["budget"] += budget; tot["annuel"] += annuel; tot["ecart"] += ecart
    for k in tot:
        tot[k] = round(tot[k], 2)
    last = await db.acct_email_last.find_one({"_id": f"{mgr['_id']}:{_pkey(year, month)}"})
    last_sent = None
    if last:
        last_sent = {"sent_at": last.get("sent_at"), "email": last.get("email"),
                     "sent_by": last.get("sent_by"), "rev_label": last.get("rev_label")}
    return {"manager": {"id": manager_id, "name": mgr.get("name", ""), "email": mgr.get("email", "")},
            "year": int(year), "month": int(month), "month_label": rep["month_label"],
            "rev": rev, "rev_label": REV_LABEL[rev], "locked": rep["locked"],
            "lines": lines, "total": tot, "accounts": accts, "last_sent": last_sent}

@api.get("/acct/report/by-manager")
async def acct_report_by_manager(manager_id: str, year: int, month: int, rev: str = "rev1", user: dict = Depends(get_current_user)):
    return await _by_manager_data(manager_id, year, month, rev)

class ManagerNote(BaseModel):
    year: int
    month: int
    account: str
    text: str = ""

@api.put("/acct/report/by-manager/note")
async def save_manager_note(payload: ManagerNote, user: dict = Depends(get_current_user)):
    """Note par compte + période (éditable par tout utilisateur connecté). Réapparaît au rechargement du mois."""
    key = f"{int(payload.year):04d}-{int(payload.month):02d}-{str(payload.account).strip()}"
    text = (payload.text or "").strip()
    if not text:
        await db.acct_manager_notes.delete_one({"_id": key})
    else:
        await db.acct_manager_notes.update_one(
            {"_id": key},
            {"$set": {"year": int(payload.year), "month": int(payload.month),
                      "account": str(payload.account).strip(), "text": text,
                      "updated_by": user.get("email"), "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True)
    return {"success": True, "account": str(payload.account).strip(), "text": text}

def _mgr_col_headers(data):
    y = data["year"]; ml = data["month_label"]; rl = data["rev_label"]
    return [f"Réel {ml} {y} (Cumulatif)", f"Budget {rl} {y} ({ml} {y})",
            f"Budget {rl} {y} (Annuel)", "Écart Budget Mois vs Annuel", "Notes et commentaires"]

@api.get("/acct/report/by-manager/excel")
async def acct_report_by_manager_excel(manager_id: str, year: int, month: int, rev: str = "rev1", user: dict = Depends(get_current_user)):
    data = await _by_manager_data(manager_id, year, month, rev)
    S = openpyxl.styles
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Suivi Budget vs Réel"
    navy = "FF063044"; teal = "FF0E9488"; grey = "FFEEF1F5"
    title = f"Suivi Budget frais d'exploitation - {data['manager']['name']}"
    ws["B3"] = title; ws["B3"].font = S.Font(bold=True, size=13, color=navy)
    hdrs = _mgr_col_headers(data)
    for i, h in enumerate(hdrs[:4]):
        c = ws.cell(row=4, column=5 + i, value=h)
        c.font = S.Font(bold=True, color=navy, size=9); c.alignment = S.Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.cell(row=4, column=10, value=hdrs[4]).font = S.Font(bold=True, color=navy, size=9)
    ws["A5"] = "No GL"; ws["B5"] = "Désignation"
    for cell in ("A5", "B5"):
        ws[cell].font = S.Font(bold=True, size=9)
    r = 7
    money_fmt = '#,##0.00;(#,##0.00)'
    for ln in data["lines"]:
        ws.cell(row=r, column=1, value=ln["account"])
        ws.cell(row=r, column=2, value=ln["label"])
        for j, key in enumerate(("reel", "budget", "annuel", "ecart")):
            c = ws.cell(row=r, column=5 + j, value=ln[key]); c.number_format = money_fmt
            if ln[key] < 0: c.font = S.Font(color="FFDC2626")
        nc = ws.cell(row=r, column=10, value=ln.get("note", "")); nc.alignment = S.Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    ws.cell(row=r, column=1, value=f"TOTAL - {data['manager']['name'].upper()}")
    for j, key in enumerate(("reel", "budget", "annuel", "ecart")):
        c = ws.cell(row=r, column=5 + j, value=data["total"][key]); c.number_format = money_fmt
    for c in ws[r]:
        c.font = S.Font(bold=True, color=navy)
        c.fill = S.PatternFill("solid", fgColor=grey)
    ws.column_dimensions["A"].width = 12; ws.column_dimensions["B"].width = 44
    for col in ("E", "F", "G", "H"): ws.column_dimensions[col].width = 18
    ws.column_dimensions["J"].width = 30
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    fn = f"suivi_budget_{data['manager']['name']}_{_pkey(year, month)}.xlsx".replace(" ", "_")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={fn}"})

def _build_manager_pdf(data):
    """Construit le PDF « Suivi Budget » et renvoie (bytes, filename)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); GREY = colors.HexColor("#EEF1F5"); RED = colors.HexColor("#DC2626")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Title"], fontSize=15, textColor=NAVY, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748B"))
    cellS = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)
    elems = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph(f"Suivi Budget frais d'exploitation - {data['manager']['name']}", h)]
    prov = "" if data["locked"] else " · données provisoires"
    elems.append(Paragraph(f"Réel {data['month_label']} {data['year']} (Cumulatif) · Budget {data['rev_label']}{prov}", sub))
    elems.append(Spacer(1, 6 * mm))
    hdrs = _mgr_col_headers(data)
    head = ["No GL", "Désignation"] + [Paragraph(x, ParagraphStyle("hh", parent=cellS, fontSize=7.5, textColor=colors.white, alignment=1)) for x in hdrs]
    rows = [head]
    def fmt(v):
        s = f"{abs(v):,.2f}".replace(",", " ")
        return f"({s})" if v < 0 else s
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (-1, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    ri = 1
    for ln in data["lines"]:
        vals = [ln["reel"], ln["budget"], ln["annuel"], ln["ecart"]]
        note_p = Paragraph(ln.get("note", "") or "", cellS)
        rows.append([str(ln["account"]), Paragraph(ln["label"], cellS)] + [fmt(v) for v in vals] + [note_p])
        for ci, v in enumerate(vals):
            if v < 0: style_cmds.append(("TEXTCOLOR", (2 + ci, ri), (2 + ci, ri), RED))
        ri += 1
    t = data["total"]
    rows.append([f"TOTAL - {data['manager']['name'].upper()}", "", fmt(t["reel"]), fmt(t["budget"]), fmt(t["annuel"]), fmt(t["ecart"]), ""])
    style_cmds += [("BACKGROUND", (0, ri), (-1, ri), GREY), ("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"), ("TEXTCOLOR", (0, ri), (-1, ri), NAVY)]
    col_w = [24 * mm, 78 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm]
    tbl = Table(rows, colWidths=col_w, repeatRows=1); tbl.setStyle(TableStyle(style_cmds))
    elems.append(tbl)
    doc.build(elems); buf.seek(0)
    fn = f"suivi_budget_{data['manager']['name']}_{_pkey(data['year'], data['month'])}.pdf".replace(" ", "_")
    return buf.getvalue(), fn

@api.get("/acct/report/by-manager/pdf")
async def acct_report_by_manager_pdf(manager_id: str, year: int, month: int, rev: str = "rev1", user: dict = Depends(get_current_user)):
    data = await _by_manager_data(manager_id, year, month, rev)
    pdf_bytes, fn = _build_manager_pdf(data)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={fn}"})

# ---------------------------------------------------------------------------
# Envoi par courriel des rapports « par responsable » (Resend)
# ---------------------------------------------------------------------------
def _email_configured():
    return bool(os.environ.get("RESEND_API_KEY"))

async def _send_manager_report_email(mgr_doc, year, month, rev="rev1", actor=None):
    """Génère le PDF et l'envoie au responsable. Renvoie (ok: bool, message: str)."""
    email = (mgr_doc.get("email") or "").strip()
    name = mgr_doc.get("name", "")
    if not email:
        return False, f"{name} : aucun courriel renseigné"
    if not _email_configured():
        return False, "Service d'email non configuré (clé Resend manquante)"
    data = await _by_manager_data(str(mgr_doc["_id"]), year, month, rev)
    pdf_bytes, fn = _build_manager_pdf(data)
    ml = data["month_label"]
    subject = f"Suivi budgétaire {name} — {ml} {year}"
    html = (
        f"<div style=\"font-family:Arial,sans-serif;color:#1e293b;font-size:14px;line-height:1.5\">"
        f"<p>Bonjour,</p>"
        f"<p>Veuillez trouver ci-joint votre <strong>suivi des frais d'exploitation — {name}</strong> "
        f"pour la période de <strong>{ml} {year}</strong> (réel cumulatif vs budget {data['rev_label']}).</p>"
        f"<p>Ce rapport est généré automatiquement à la clôture du mois. "
        f"N'hésitez pas à nous transmettre vos commentaires.</p>"
        f"<p style=\"color:#64748b;font-size:12px;margin-top:24px\">ACCSL Groupe — Plateforme financière</p>"
        f"</div>"
    )
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    params = {
        "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
        "to": [email],
        "subject": subject,
        "html": html,
        "attachments": [{"filename": fn, "content": list(pdf_bytes)}],
    }
    try:
        res = await asyncio.to_thread(resend.Emails.send, params)
        sent_by = (actor or {}).get("email") or "système"
        rec = {"manager_id": str(mgr_doc["_id"]), "manager_name": name, "email": email,
               "year": int(year), "month": int(month), "rev": rev, "rev_label": data["rev_label"],
               "sent_at": datetime.now(timezone.utc).isoformat(), "sent_by": sent_by,
               "email_id": (res or {}).get("id") if isinstance(res, dict) else None,
               "company_id": await _company_id("acct")}
        await db.acct_email_log.insert_one(dict(rec))
        # Dernier envoi mémorisé par (responsable, période).
        await db.acct_email_last.update_one(
            {"_id": f"{mgr_doc['_id']}:{_pkey(year, month)}"}, {"$set": rec}, upsert=True)
        await log_action(actor or {"email": "système"}, "Envoyer", "Rapport responsable", f"{name} → {email} ({_pkey(year, month)})")
        return True, f"{name} → {email}"
    except Exception as e:
        logger.error(f"Resend échec ({name}): {e}")
        return False, f"{name} : échec d'envoi ({str(e)[:120]})"

@api.get("/acct/email/status")
async def acct_email_status(user: dict = Depends(get_current_user)):
    return {"configured": _email_configured(), "sender": os.environ.get("SENDER_EMAIL", "")}

@api.get("/acct/email/log")
async def acct_email_log(manager_id: Optional[str] = None, limit: int = 100, user: dict = Depends(get_current_user)):
    q = {}
    if manager_id:
        q["manager_id"] = manager_id
    docs = await db.acct_email_log.find(q).sort("sent_at", -1).to_list(int(limit))
    return [{"manager_id": d.get("manager_id"), "manager_name": d.get("manager_name"), "email": d.get("email"),
             "year": d.get("year"), "month": d.get("month"), "rev_label": d.get("rev_label"),
             "sent_at": d.get("sent_at"), "sent_by": d.get("sent_by")} for d in docs]

@api.post("/acct/report/by-manager/email")
async def email_manager_report(manager_id: str, year: int, month: int, rev: str = "rev1", user: dict = Depends(get_current_user)):
    mgr = await db.acct_budget_managers.find_one({"_id": _oid(manager_id)})
    if not mgr:
        raise HTTPException(status_code=404, detail="Responsable introuvable")
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré. Un administrateur doit renseigner la clé Resend.")
    ok, msg = await _send_manager_report_email(mgr, year, month, rev, actor=user)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@api.post("/acct/report/by-manager/email-all")
async def email_all_manager_reports(year: int, month: int, rev: str = "rev1", user: dict = Depends(get_current_user)):
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré. Un administrateur doit renseigner la clé Resend.")
    mgrs = await db.acct_budget_managers.find({"active": {"$ne": False}}).sort("name", 1).to_list(500)
    sent, failed, skipped = [], [], []
    for m in mgrs:
        if not (m.get("email") or "").strip():
            skipped.append(m.get("name", "")); continue
        ok, msg = await _send_manager_report_email(m, year, month, rev, actor=user)
        (sent if ok else failed).append(msg)
    return {"success": True, "sent": sent, "failed": failed, "skipped": skipped,
            "summary": f"{len(sent)} envoyé(s), {len(failed)} échec(s), {len(skipped)} sans courriel"}

# ---------------------------------------------------------------------------
# Envoi Externe : contacts externes + rapports « présentation » + Margination
# ---------------------------------------------------------------------------
EXTERNAL_REPORT_CATALOG = [
    {"key": "pnl_presentation", "label": "États de Résultats (présentation)", "fmt": "pdf"},
    {"key": "bilan_presentation", "label": "Bilan (présentation)", "fmt": "pdf"},
    {"key": "margination", "label": "Rapport de Margination (Excel téléversé)", "fmt": "xlsx"},
    {"key": "pnl", "label": "États de résultats — détaillé", "fmt": "pdf"},
    {"key": "pnl_sommaire", "label": "États de résultats — sommaire", "fmt": "pdf"},
    {"key": "bilan", "label": "Bilan — détaillé", "fmt": "pdf"},
    {"key": "cashflow", "label": "Flux de trésorerie", "fmt": "pdf"},
]
_CATALOG_LABELS = {c["key"]: c["label"] for c in EXTERNAL_REPORT_CATALOG}

EXTERNAL_CONTACTS_SEED = [
    {"name": "Banque Desjardins", "email": "", "report_types": ["pnl_presentation", "bilan_presentation", "margination"], "active": True},
]

class ExternalContact(BaseModel):
    name: str
    email: str = ""
    report_types: List[str] = []
    active: bool = True

async def _generate_external_report(key, year, month):
    """Renvoie (bytes, filename, mimetype) ou (None, None, None) si indisponible."""
    ml = MONTHS_FR[month - 1]
    if key == "pnl_presentation":
        data = await _acct_report(year, month, "pnl_sommaire")
        data["month"] = month; data.setdefault("month_label", ml)
        b = presentation_reports.build_presentation_pnl_pdf(data, year, ml)
        return b, f"etats_resultats_presentation_{_pkey(year, month)}.pdf", "application/pdf"
    if key == "bilan_presentation":
        data = await _acct_report(year, month, "bilan")
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        b = presentation_reports.build_presentation_bilan_pdf(data, year, ml, f"{last} {ml} {year}")
        return b, f"bilan_presentation_{_pkey(year, month)}.pdf", "application/pdf"
    if key == "margination":
        doc = await db.acct_margination.find_one({"_id": _pkey(year, month)})
        if not doc:
            return None, None, None
        return base64.b64decode(doc["data"]), doc.get("filename", f"margination_{_pkey(year, month)}.xlsx"), \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if key in ("pnl", "pnl_sommaire", "bilan"):
        rep = await _acct_report(year, month, key)
        if key == "pnl":
            rep = _pnl_detail_adjust(rep)
        rep = _filter_rep_view(rep, "", False)
        return _acct_pdf(rep).getvalue(), f"{key}_{_pkey(year, month)}.pdf", "application/pdf"
    if key == "cashflow":
        oy, om = (year, month - 1) if month > 1 else (year - 1, 12)
        try:
            rep = await _cashflow_data(oy, om, year, month)
        except HTTPException:
            return None, None, None
        buf = _cashflow_pdf(rep)
        data_bytes = buf.getvalue() if hasattr(buf, "getvalue") else buf
        return data_bytes, f"flux_tresorerie_{_pkey(year, month)}.pdf", "application/pdf"
    return None, None, None

@api.get("/acct/external/catalog")
async def external_catalog(user: dict = Depends(get_current_user)):
    return EXTERNAL_REPORT_CATALOG

@api.get("/acct/external-contacts")
async def list_external_contacts(user: dict = Depends(get_current_user)):
    docs = await db.acct_external_contacts.find().sort("name", 1).to_list(500)
    return [{"id": str(d["_id"]), "name": d.get("name", ""), "email": d.get("email", ""),
             "report_types": d.get("report_types", []), "active": d.get("active", True),
             "last_sent": d.get("last_sent")} for d in docs]

@api.post("/acct/external-contacts")
async def create_external_contact(payload: ExternalContact, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    ec_doc = payload.model_dump()
    ec_doc["company_id"] = await _company_id("acct")
    res = await db.acct_external_contacts.insert_one(ec_doc)
    await log_action(user, "Créer", "Contact externe", payload.name)
    return {"id": str(res.inserted_id), **payload.model_dump()}

@api.put("/acct/external-contacts/{cid}")
async def update_external_contact(cid: str, payload: ExternalContact, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    r = await db.acct_external_contacts.update_one({"_id": _oid(cid)}, {"$set": payload.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    await log_action(user, "Modifier", "Contact externe", payload.name)
    return {"id": cid, **payload.model_dump()}

@api.delete("/acct/external-contacts/{cid}")
async def delete_external_contact(cid: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    d = await db.acct_external_contacts.find_one({"_id": _oid(cid)})
    await db.acct_external_contacts.delete_one({"_id": _oid(cid)})
    await log_action(user, "Supprimer", "Contact externe", (d or {}).get("name", cid))
    return {"success": True}

@api.post("/acct/margination/upload")
async def upload_margination(year: int, month: int, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    content = await file.read()
    await db.acct_margination.update_one(
        {"_id": _pkey(year, month)},
        {"$set": {"year": int(year), "month": int(month), "filename": file.filename,
                  "data": base64.b64encode(content).decode(), "size": len(content),
                  "uploaded_by": user.get("email"), "uploaded_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    await log_action(user, "Téléverser", "Rapport Margination", f"{file.filename} ({_pkey(year, month)})")
    return {"success": True, "filename": file.filename, "size": len(content)}

@api.get("/acct/margination/status")
async def margination_status(year: int, month: int, user: dict = Depends(get_current_user)):
    doc = await db.acct_margination.find_one({"_id": _pkey(year, month)})
    if not doc:
        return {"present": False}
    return {"present": True, "filename": doc.get("filename"), "size": doc.get("size"),
            "uploaded_by": doc.get("uploaded_by"), "uploaded_at": doc.get("uploaded_at")}

@api.get("/acct/margination/preview")
async def margination_preview(year: int, month: int, user: dict = Depends(get_current_user)):
    doc = await db.acct_margination.find_one({"_id": _pkey(year, month)})
    if not doc:
        raise HTTPException(status_code=404, detail="Aucun fichier Margination pour cette période")
    raw = base64.b64decode(doc["data"])
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    sheets = []
    for ws in wb.worksheets:
        maxr = min(ws.max_row or 0, 300)
        maxc = min(ws.max_column or 0, 20)
        rows = []
        for r in ws.iter_rows(min_row=1, max_row=maxr, max_col=maxc, values_only=True):
            cells = []
            for v in r:
                if v is None:
                    cells.append("")
                elif isinstance(v, (int, float)):
                    cells.append(v)
                elif isinstance(v, datetime):
                    cells.append(v.strftime("%Y-%m-%d"))
                else:
                    cells.append(str(v))
            rows.append(cells)
        while rows and all((c == "" for c in rows[-1])):
            rows.pop()
        sheets.append({"name": ws.title, "rows": rows})
    wb.close()
    return {"filename": doc.get("filename"), "sheets": sheets}

@api.get("/acct/external/report")
async def external_report_download(key: str, year: int, month: int, user: dict = Depends(get_current_user)):
    b, fn, mime = await _generate_external_report(key, year, month)
    if b is None:
        raise HTTPException(status_code=404, detail="Rapport indisponible pour cette période (fichier Margination non téléversé ?)")
    return StreamingResponse(io.BytesIO(b), media_type=mime, headers={"Content-Disposition": f"attachment; filename={fn}"})

@api.post("/acct/external/email")
async def external_email(contact_id: str, year: int, month: int, user: dict = Depends(get_current_user)):
    c = await db.acct_external_contacts.find_one({"_id": _oid(contact_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré. Un administrateur doit renseigner la clé Resend.")
    email = (c.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail=f"{c.get('name')} : aucun courriel renseigné")
    attachments, missing, doc_labels = [], [], []
    for key in c.get("report_types", []):
        b, fn, mime = await _generate_external_report(key, year, month)
        if b is None:
            missing.append(_CATALOG_LABELS.get(key, key)); continue
        attachments.append({"filename": fn, "content": list(b)})
        doc_labels.append(_CATALOG_LABELS.get(key, key))
    if not attachments:
        raise HTTPException(status_code=400, detail="Aucun rapport disponible à envoyer. " + (f"Manquant : {', '.join(missing)}" if missing else ""))
    ml = MONTHS_FR[month - 1]
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#1e293b;font-size:14px\">"
            f"<p>Bonjour,</p><p>Veuillez trouver ci-joint le package financier de <strong>{ml} {year}</strong> "
            f"pour <strong>{c.get('name')}</strong> ({len(attachments)} document(s)).</p>"
            f"<p style=\"color:#64748b;font-size:12px;margin-top:24px\">ACCSL Groupe — Plateforme financière</p></div>")
    try:
        res = await asyncio.to_thread(resend.Emails.send, {
            "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
            "to": [email], "subject": f"Package financier {c.get('name')} — {ml} {year}",
            "html": html, "attachments": attachments})
        sent_by = (user or {}).get("email") or "système"
        rec = {"contact_id": contact_id, "contact_name": c.get("name", ""), "email": email,
               "year": int(year), "month": int(month), "period": _pkey(year, month),
               "documents": doc_labels, "doc_count": len(attachments), "missing": missing,
               "sent_at": datetime.now(timezone.utc).isoformat(), "sent_by": sent_by,
               "email_id": (res or {}).get("id") if isinstance(res, dict) else None}
        await db.acct_external_email_log.insert_one(dict(rec))
        await db.acct_external_contacts.update_one(
            {"_id": _oid(contact_id)}, {"$set": {"last_sent": {k: rec[k] for k in
             ("email", "year", "month", "period", "documents", "doc_count", "sent_at", "sent_by")}}})
        await log_action(user, "Envoyer", "Package externe", f"{c.get('name')} → {email} ({_pkey(year, month)})")
        msg = f"{len(attachments)} document(s) envoyé(s) à {email}"
        if missing:
            msg += f" · manquant : {', '.join(missing)}"
        return {"success": True, "message": msg}
    except Exception as e:
        logger.error(f"Envoi externe échec : {e}")
        raise HTTPException(status_code=400, detail=f"Échec d'envoi : {str(e)[:150]}")

@api.get("/acct/external/email/log")
async def external_email_log(contact_id: Optional[str] = None, limit: int = 100, user: dict = Depends(get_current_user)):
    q = {}
    if contact_id:
        q["contact_id"] = contact_id
    docs = await db.acct_external_email_log.find(q).sort("sent_at", -1).to_list(int(limit))
    return [{"contact_id": d.get("contact_id"), "contact_name": d.get("contact_name"), "email": d.get("email"),
             "year": d.get("year"), "month": d.get("month"), "period": d.get("period"),
             "documents": d.get("documents", []), "doc_count": d.get("doc_count"),
             "missing": d.get("missing", []), "sent_at": d.get("sent_at"), "sent_by": d.get("sent_by")} for d in docs]



@api.get("/acct/dashboard")
async def acct_dashboard(user: dict = Depends(get_current_user)):
    tmpl = await db.acct_template.find_one({"_id": "current"})
    periods = await db.acct_periods.find({"company_id": await _company_id("acct")}).sort("_id", -1).to_list(500)
    latest = periods[0] if periods else None
    return {
        "template_imported": tmpl is not None,
        "template_accounts": len(tmpl.get("accounts", [])) if tmpl else 0,
        "period_count": len(periods),
        "latest": {
            "period": latest["_id"], "year": latest["year"], "month": latest["month"],
            "month_label": MONTHS_FR[latest["month"]-1], "locked": latest.get("locked", False),
            "balanced": latest.get("balanced"), "diff": latest.get("diff"),
            "last_upload_at": latest.get("last_upload_at"), "last_upload_by": latest.get("last_upload_by"),
            "new_accounts": len(latest.get("new_accounts", [])),
        } if latest else None,
    }

# ---------------------------------------------------------------------------
# Indicateurs (KPI) : DSO, DPO, Fonds de roulement + projections 12 mois
# ---------------------------------------------------------------------------
def _find_line(lines, exact_norm):
    for l in lines:
        if _acct_norm(l.get("label")) == exact_norm:
            return l
    return None

def _bilan_ct_lines(bdata):
    """Lignes de détail (data) de l'actif court terme et du passif court terme."""
    actif_ct, passif_ct = [], []
    inb = False
    for l in bdata["actif"]:
        n = _acct_norm(l["label"])
        if n == "ACTIF COURT TERME":
            inb = True; continue
        if inb:
            if n.startswith("TOTAL"):
                break
            if l.get("kind") == "data":
                actif_ct.append({"label": l["label"], "value": l["value"]})
    inb = False
    for l in bdata["passif"]:
        n = _acct_norm(l["label"])
        if n == "PASSIF A COURT TERME":
            inb = True; continue
        if inb:
            if n.startswith("TOTAL"):
                break
            if l.get("kind") == "data":
                passif_ct.append({"label": l["label"], "value": l["value"]})
    return actif_ct, passif_ct

def _pnl_figures(pnl):
    """Extrait (mois, cumulatif) pour ventes, COGS, charges depuis un rapport P&L."""
    out = {"sales": {}, "cogs": {}, "charges": {}}
    for ln in pnl["lines"]:
        n = _acct_norm(ln["label"])
        if not out["sales"] and n == "TOTAL DES REVENUS":
            out["sales"] = {"reel": ln["values"].get("reel"), "cumulatif": ln["values"].get("cumulatif")}
        if not out["cogs"] and (n == "COUT DES MARCHANDISES VENDUES" or (n.startswith("TOTAL") and "COUT DES MARCHANDISES VENDUES" in n)):
            out["cogs"] = {"reel": ln["values"].get("reel"), "cumulatif": ln["values"].get("cumulatif")}
        if not out["charges"] and n == "TOTAL DES CHARGES":
            out["charges"] = {"reel": ln["values"].get("reel"), "cumulatif": ln["values"].get("cumulatif")}
    return out

async def _acct_tax_factor():
    doc = await db.acct_settings.find_one({"_id": "kpi"})
    try:
        v = float(doc.get("tax_factor")) if doc and doc.get("tax_factor") else 1.14975
        return v if v > 0 else 1.14975
    except Exception:
        return 1.14975

def _pnl_cogs_labor(pnl_det):
    """(ventes_reel, cogs_reel, main_oeuvre_cogs_reel) depuis le P&L détaillé."""
    sales = cogs = None
    labor = 0.0
    in_cogs = False
    for ln in pnl_det["lines"]:
        n = _acct_norm(ln["label"])
        if sales is None and n == "TOTAL DES REVENUS":
            sales = ln["values"].get("reel")
        if n == "COUT DES MARCHANDISES VENDUES" and ln.get("kind") == "header":
            in_cogs = True
        if in_cogs and n.startswith("TOTAL MAIN D") and "UVRE" in n:  # ligature Œ non décomposée
            labor += (ln["values"].get("reel") or 0.0)
        if n.startswith("TOTAL") and "COUT DES MARCHANDISES VENDUES" in n:
            cogs = ln["values"].get("reel")
            in_cogs = False
            break
    return sales, cogs, round(labor, 2)

async def _kpi_dispute(pk, field):
    """Report automatique : dernier ajustement explicite (≤ période) pour ce champ."""
    docs = await db.acct_kpi_adjust.find({"_id": {"$lte": pk}, field: {"$exists": True}}).sort("_id", -1).to_list(1)
    doc = docs[0] if docs else {}
    try:
        amount = float(doc.get(field) or 0.0)
    except Exception:
        amount = 0.0
    note = doc.get(field + "_note") or ""
    src = doc.get("_id") if doc else None
    return {"amount": round(amount, 2), "note": note, "source": src, "carried": bool(src and src != pk)}

async def _kpi_data(year, month, with_trend=True):
    bdata = await _bilan_sommaire_data(year, month)
    pnl = await _acct_report(year, month, "pnl_sommaire")
    months = int(month)  # exercice = année civile -> mois écoulés = n° du mois
    pk = _pkey(year, month)
    period = await db.acct_periods.find_one({"_id": pk})

    ar = _find_line(bdata["actif"], "COMPTES A RECEVOIR")
    inv = _find_line(bdata["actif"], "INVENTAIRE")
    ca_total = _find_line(bdata["actif"], "TOTAL DE L'ACTIF A COURT TERME")
    ap = _find_line(bdata["passif"], "COMPTES FOURNISSEURS")
    cl_total = _find_line(bdata["passif"], "TOTAL DU PASSIF A COURT TERME")
    actif_ct, passif_ct = _bilan_ct_lines(bdata)
    fig = _pnl_figures(pnl)

    # --- Retenues contractuelles sur factures émises (garantie de construction) ---
    retenues = 0.0; retenues_label = None; retenues_found = False
    try:
        bilan_det = await _acct_report(year, month, "bilan")
        for ln in bilan_det["lines"]:
            n = _acct_norm(ln["label"])
            if "RETENUE" in n and "CONSTRUCTION" in n:
                retenues = ln["values"].get("cumulatif") or 0.0
                retenues_label = ln["label"]; retenues_found = True
                break
    except Exception:
        pass

    # --- Fenêtre glissante 12 mois : ventes, COGS & main-d'œuvre du COGS mensuels réels (P&L détaillé) ---
    inv_current = inv["value"] if inv else None
    cogs_12m = 0.0; sales_12m = 0.0; labor_12m = 0.0
    missing = []
    for k in range(12):
        wy, wm = _add_months(year, month, -k)
        wpk = _pkey(wy, wm)
        wp = await db.acct_periods.find_one({"_id": wpk})
        wbv = await db.acct_bv.find_one({"_id": wpk})
        if not wp or not wbv:
            missing.append(wpk); continue
        try:
            s, c, lab = _pnl_cogs_labor(await _acct_report(wy, wm, "pnl"))
            sales_12m += (s or 0.0); cogs_12m += (c or 0.0); labor_12m += lab
        except Exception:
            missing.append(wpk)
    months_available = 12 - len(missing)

    # Inventaire il y a 12 mois (ouverture de la fenêtre glissante)
    oy, om = _add_months(year, month, -12)
    inv12_pk = _pkey(oy, om)
    inv_12m = None
    if await db.acct_bv.find_one({"_id": inv12_pk}):
        try:
            b12 = await _bilan_sommaire_data(oy, om)
            l12 = _find_line(b12["actif"], "INVENTAIRE")
            if l12 is not None:
                inv_12m = l12["value"]
        except Exception:
            pass

    # --- DSO --- base glissante 12 mois ; CC courants nets de taxes (÷ taux QC), hors retenues, moins litige manuel
    QC_TAX = await _acct_tax_factor()  # TPS 5% + TVQ 9,975% par défaut (configurable)
    dso_adj = await _kpi_dispute(pk, "dso_dispute")
    dispute = dso_adj["amount"]
    ar_courant = round(ar["value"] - retenues, 2) if ar else None
    ar_courant_net = round(ar_courant / QC_TAX, 2) if ar_courant is not None else None
    ar_dso_base = round(ar_courant_net - dispute, 2) if ar_courant_net is not None else None
    dso = {"available": False, "value": None, "reason": None, "method": "rolling_12m",
           "ar_label": ar["label"] if ar else None, "ar": ar["value"] if ar else None,
           "retenues": round(retenues, 2), "ar_courant": ar_courant,
           "tax_factor": QC_TAX, "ar_courant_net": ar_courant_net,
           "dispute": dispute, "dispute_note": dso_adj["note"], "ar_dso_base": ar_dso_base,
           "dispute_source": dso_adj["source"], "dispute_carried": dso_adj["carried"],
           "sales_12m": round(sales_12m, 2), "months_available": months_available}
    if ar is None:
        dso["reason"] = "Compte « Comptes à recevoir » introuvable dans le mapping du bilan."
    elif missing:
        dso["reason"] = f"DSO non calculable de façon fiable — {months_available}/12 mois réels disponibles (base glissante 12 mois requise)."
    elif sales_12m <= 0:
        dso["reason"] = "Ventes des 12 derniers mois nulles ou négatives."
    else:
        dso["value"] = round(ar_dso_base / sales_12m * 365, 1)
        dso["available"] = True

    # --- DPO --- base glissante 12 mois ; CF nets de taxes (÷ taux QC) moins litige ; Achats = (COGS 12m − main-d'œuvre COGS 12m) + variation d'inventaire 12m
    inv_var = round(inv_current - inv_12m, 2) if (inv_current is not None and inv_12m is not None) else None
    dpo_adj = await _kpi_dispute(pk, "dpo_dispute")
    dpo_dispute = dpo_adj["amount"]
    ap_net = round(ap["value"] / QC_TAX, 2) if ap else None
    ap_dpo_base = round(ap_net - dpo_dispute, 2) if ap_net is not None else None
    cogs_ex_labor_12m = round(cogs_12m - labor_12m, 2)
    dpo = {"available": False, "value": None, "reason": None, "method": "rolling_12m",
           "ap_label": ap["label"] if ap else None, "ap": ap["value"] if ap else None,
           "tax_factor": QC_TAX, "ap_net": ap_net,
           "dispute": dpo_dispute, "dispute_note": dpo_adj["note"], "ap_dpo_base": ap_dpo_base,
           "dispute_source": dpo_adj["source"], "dispute_carried": dpo_adj["carried"],
           "cogs_12m": round(cogs_12m, 2), "labor_12m": round(labor_12m, 2), "cogs_ex_labor_12m": cogs_ex_labor_12m,
           "inv_current": inv_current, "inv_12m": inv_12m,
           "inv_12m_period": inv12_pk, "inv_variation": inv_var,
           "months_available": months_available, "purchases_12m": None}
    if ap is None:
        dpo["reason"] = "Compte « Comptes fournisseurs » introuvable dans le mapping du bilan."
    elif missing or inv_12m is None:
        dpo["reason"] = f"DPO non calculable de façon fiable — {months_available}/12 mois réels disponibles (base glissante 12 mois requise)."
    else:
        purchases = cogs_ex_labor_12m + (inv_var or 0.0)
        dpo["purchases_12m"] = round(purchases, 2)
        if purchases <= 0:
            dpo["reason"] = "Achats des 12 derniers mois nuls ou négatifs."
        else:
            dpo["value"] = round(ap_dpo_base / purchases * 365, 1)
            dpo["available"] = True

    # --- Fonds de roulement (FDR) & Besoin en fonds de roulement (BFR) ---
    # Exclusion des retenues contractuelles de l'actif court terme et des comptes clients.
    fdr = {"available": False, "value": None, "ratio": None, "reason": None,
           "current_assets": ca_total["value"] if ca_total else None,
           "current_liabilities": cl_total["value"] if cl_total else None,
           "current_assets_excl": None,
           "retenues": round(retenues, 2), "retenues_label": retenues_label, "retenues_found": retenues_found,
           "actif_ct": actif_ct, "passif_ct": passif_ct,
           "bfr": {"available": False, "value": None, "reason": None,
                   "ar": ar["value"] if ar else None, "ar_label": ar["label"] if ar else None,
                   "ar_courant": None, "inventory": inv_current, "ap": ap["value"] if ap else None}}
    if ca_total is None or cl_total is None:
        fdr["reason"] = "Totaux actif/passif à court terme introuvables dans le mapping du bilan."
    else:
        ca_excl = ca_total["value"] - retenues
        fdr["current_assets_excl"] = round(ca_excl, 2)
        fdr["value"] = round(ca_excl - cl_total["value"], 2)
        fdr["ratio"] = round(ca_excl / cl_total["value"], 2) if cl_total["value"] else None
        fdr["available"] = True
    if ar is None or inv_current is None or ap is None:
        fdr["bfr"]["reason"] = "Comptes clients, inventaire ou fournisseurs introuvables dans le mapping du bilan."
    else:
        ar_courant = ar["value"] - retenues
        fdr["bfr"]["ar_courant"] = round(ar_courant, 2)
        fdr["bfr"]["value"] = round(ar_courant + inv_current - ap["value"], 2)
        fdr["bfr"]["available"] = True

    result = {"period": pk, "year": int(year), "month": int(month), "month_label": MONTHS_FR[month - 1],
              "locked": bool(period and period.get("locked")),
              "dso": dso, "dpo": dpo, "fdr": fdr}

    # --- Tendance vs mois précédent ---
    if with_trend:
        py, pm = _add_months(year, month, -1)
        prev = None
        if await db.acct_bv.find_one({"_id": _pkey(py, pm)}):
            try:
                prev = await _kpi_data(py, pm, with_trend=False)
            except Exception:
                prev = None
        def _trend(cur, prv):
            if cur is None or prv is None:
                return None
            delta = round(cur - prv, 2)
            pct = round((delta / abs(prv)) * 100, 1) if prv else None
            return {"prev": prv, "delta": delta, "delta_pct": pct}
        result["trend"] = {
            "period": _pkey(py, pm), "month_label": MONTHS_FR[pm - 1], "year": int(py),
            "dso": _trend(dso.get("value"), (prev or {}).get("dso", {}).get("value")),
            "dpo": _trend(dpo.get("value"), (prev or {}).get("dpo", {}).get("value")),
            "fdr": _trend(fdr.get("value"), (prev or {}).get("fdr", {}).get("value")),
            "bfr": _trend(fdr.get("bfr", {}).get("value"), (prev or {}).get("fdr", {}).get("bfr", {}).get("value")),
        }
    return result

@api.get("/acct/kpis")
async def acct_kpis(year: int, month: int, user: dict = Depends(get_current_user)):
    return await _kpi_data(year, month)

@api.get("/acct/settings")
async def acct_get_settings(user: dict = Depends(get_current_user)):
    return {"tax_factor": await _acct_tax_factor()}

class AcctSettingsBody(BaseModel):
    tax_factor: float

@api.put("/acct/settings")
async def acct_put_settings(body: AcctSettingsBody, user: dict = Depends(get_current_user)):
    tf = float(body.tax_factor)
    if tf <= 0:
        raise HTTPException(status_code=400, detail="Le taux de taxe doit être supérieur à 0.")
    await db.acct_settings.update_one({"_id": "kpi"}, {"$set": {"tax_factor": tf, "updated_by": user["email"], "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    await log_action(user, "Modifier", "Comptabilité", f"Taux de taxe KPI = {tf}")
    return {"tax_factor": tf}

class KpiAdjustBody(BaseModel):
    dso_dispute: Optional[float] = None
    dso_dispute_note: Optional[str] = None
    dpo_dispute: Optional[float] = None
    dpo_dispute_note: Optional[str] = None

@api.put("/acct/kpi-adjust")
async def acct_put_kpi_adjust(year: int, month: int, body: KpiAdjustBody, user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    provided = body.dict(exclude_unset=True)
    sets = {}
    for f in ("dso_dispute", "dpo_dispute"):
        if f in provided:
            sets[f] = max(0.0, float(provided[f] or 0.0))
    for f in ("dso_dispute_note", "dpo_dispute_note"):
        if f in provided:
            sets[f] = (provided[f] or "").strip()
    if sets:
        sets["updated_by"] = user["email"]; sets["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.acct_kpi_adjust.update_one({"_id": pk}, {"$set": sets}, upsert=True)
        await log_action(user, "Modifier", "Comptabilité", f"Ajustement KPI {pk}: {', '.join(k for k in sets if k.endswith('dispute'))}")
    return {"period": pk, **{k: v for k, v in sets.items() if k not in ("updated_by", "updated_at")}}

def _linreg_project(ys, n_future):
    pts = [(i, v) for i, v in enumerate(ys) if v is not None]
    if len(pts) < 2:
        last = next((v for v in reversed(ys) if v is not None), 0.0) or 0.0
        return [round(float(last), 2)] * n_future
    n = len(pts); sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        slope = 0.0; intercept = sy / n
    else:
        slope = (n * sxy - sx * sy) / denom; intercept = (sy - slope * sx) / n
    start = len(ys)
    return [round(intercept + slope * (start + k), 2) for k in range(n_future)]

def _add_months(y, m, k):
    idx = (y * 12 + (m - 1)) + k
    return idx // 12, idx % 12 + 1

@api.get("/acct/projections")
async def acct_projections(user: dict = Depends(get_current_user)):
    periods = await db.acct_periods.find({"locked": True, "company_id": await _company_id("acct")}).sort("_id", 1).to_list(500)
    series = []
    for p in periods:
        y, m = p["year"], p["month"]
        try:
            bdata = await _bilan_sommaire_data(y, m)
            pnl = await _acct_report(y, m, "pnl_sommaire")
        except Exception:
            continue
        cash = None
        enc = _find_line(bdata["actif"], "ENCAISSE")
        if enc is not None:
            cash = enc["value"]
        fig = _pnl_figures(pnl)
        series.append({"period": p["_id"], "year": y, "month": m, "month_label": MONTHS_FR[m - 1],
                       "cash": cash, "sales": fig["sales"].get("reel"),
                       "charges": fig["charges"].get("reel"), "cogs": fig["cogs"].get("reel")})
    if len(series) < 2:
        return {"insufficient": True, "n_base": len(series), "base": series, "projection": []}
    base = series[-12:]
    n_fut = 12
    sales_p = _linreg_project([b["sales"] for b in base], n_fut)
    charges_p = _linreg_project([b["charges"] for b in base], n_fut)
    cogs_p = _linreg_project([b["cogs"] for b in base], n_fut)

    # KPI (DSO/DPO) du dernier mois verrouillé pour caler le décalage de trésorerie
    last = base[-1]
    try:
        kpi = await _kpi_data(last["year"], last["month"])
        dso = kpi["dso"]["value"]; dpo = kpi["dpo"]["value"]
    except Exception:
        dso = dpo = None
    lag_in = max(0, min(11, round((dso or 0) / 30.44)))
    lag_out = max(0, min(11, round((dpo or 0) / 30.44)))

    # Séries combinées (base + projection) pour appliquer le décalage
    comb_sales = [b["sales"] or 0 for b in base] + sales_p
    comb_out = [((b["charges"] or 0) + (b["cogs"] or 0)) for b in base] + [charges_p[k] + cogs_p[k] for k in range(n_fut)]
    bl = len(base)
    cash_start = last["cash"] or 0.0
    proj = []
    run_cash = cash_start
    for f in range(n_fut):
        gi = bl + f
        collections = comb_sales[max(0, gi - lag_in)]
        payments = comb_out[max(0, gi - lag_out)]
        run_cash = run_cash + collections - payments
        y2, m2 = _add_months(last["year"], last["month"], f + 1)
        proj.append({"year": y2, "month": m2, "month_label": MONTHS_FR[m2 - 1],
                     "cash": round(run_cash, 2), "sales": sales_p[f],
                     "charges": charges_p[f], "cogs": cogs_p[f]})
    return {"insufficient": False, "n_base": len(base), "base": base, "projection": proj,
            "dso": dso, "dpo": dpo, "lag_in_months": lag_in, "lag_out_months": lag_out}


_PNL_PCT_LABELS = {
    "Matériels Projets/Revenus Projets", "Sous-traitance projets/Revenus Projets",
    "Coût main d'œuvre direct projets/Revenus Projets", "FGF projets/Revenus Projets",
    "Marge Brute - Projet - %", "Marge très brute - Projets",
    "Matériel Services vs Revenus Services", "Sous-traitance Services vs Revenus Services",
    "Salaires Services vs Revenus Services", "Marge Brute - Service %", "Marge Brute Globale - %",
}

def _pnl_detail_adjust(rep):
    """P&L détaillé : retire les lignes « Réel vs Budget » et marque les lignes de ratio (+ ligne sous BAIIA) en pourcentage."""
    rep = dict(rep)
    lines = [dict(ln) for ln in rep["lines"] if (ln.get("label") or "").strip() != "Réel vs Budget"]
    baiia_idx = next((i for i, l in enumerate(lines) if "BAIIA" in (l.get("label") or "")), -1)
    for i, ln in enumerate(lines):
        if (ln.get("label") or "").strip() in _PNL_PCT_LABELS or (baiia_idx >= 0 and i == baiia_idx + 1):
            ln["_pct"] = True
    rep["lines"] = lines
    return rep

def _pdf_pct(v):
    if v is None or v == "":
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{v * 100:,.1f}".replace(",", " ").replace(".", ",") + " %"


def _filter_rep_view(rep, cols, hide_zero):
    """Filtre un rapport (bilan/pnl) pour refléter l'affichage écran : colonnes visibles + masquage des soldes zéro."""
    rep = dict(rep)
    if cols:
        wanted = [c for c in cols.split(",") if c in rep["value_cols"]]
        if wanted:
            rep["value_cols"] = wanted
            if rep.get("col_groups"):
                gs = [dict(g, keys=[k for k in g["keys"] if k in wanted]) for g in rep["col_groups"]]
                rep["col_groups"] = [g for g in gs if g["keys"]]
            if rep.get("col_toggle_groups"):
                tg = [dict(g, keys=[k for k in g["keys"] if k in wanted]) for g in rep["col_toggle_groups"]]
                rep["col_toggle_groups"] = [g for g in tg if g["keys"]]
    if hide_zero:
        vc = rep["value_cols"]
        rep["lines"] = [ln for ln in rep["lines"]
                        if not (ln["kind"] == "data" and all(abs(ln["values"].get(k) or 0) < 0.005 for k in vc))]
    return rep

def _row_view_style(ln, bold_totals=True):
    """Réplique la logique frontale excelRowStyle : gras, fond, couleur police, bordures haut/bas."""
    st = ln.get("style") or {}
    is_dark = st.get("f") == "dark"
    is_grey = st.get("f") == "grey"
    bold = is_dark or is_grey or bool(st.get("b")) or (bold_totals and ln["kind"] == "total") or ln["kind"] == "header"
    bg = "063044" if is_dark else ("EEF1F5" if is_grey else None)
    if is_dark:
        color = st.get("c") or "#FFFFFF"
    elif st.get("c"):
        color = st["c"]
    elif ln["kind"] == "header":
        color = "#0F172A"
    else:
        color = None
    color = color[-6:].upper() if color else None
    return {"bold": bold, "bg": bg, "color": color, "is_dark": is_dark,
            "top": bool(st.get("t")), "bottom": bool(st.get("u"))}

def _acct_excel(rep):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.title = "Bilan" if rep["kind"] == "bilan" else "Résultats"
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    bold = Font(bold=True); title_f = Font(bold=True, size=14)
    fill = PatternFill("solid", fgColor="E2E8F0")
    nf = '#,##0.00;[Red](#,##0.00)'
    bold_totals = "sommaire" not in rep["kind"]
    border_col = "94A3B8"
    cols = rep["value_cols"]
    col_labels = {
        "mois": f"{rep['month_label']} {rep['year']}", "cumulatif": "Réel à date (cum.)",
        "reel": f"Réel {rep['month_label']}", "bud_rev2": "Bud. Rév-2 (mois)", "ecart_rev2": "Écart Rév-2 (mois)",
        "bud_rev1": "Bud. Rév-1 (mois)", "ecart_rev1": "Écart Rév-1 (mois)", "bud_ca": "Bud. CA (mois)",
        "ecart_ca": "Écart CA (mois)", "reel_prec": "Réel an. préc. (mois)",
        "bud_rev2_cum": "Bud. Rév-2 (cum.)", "ecart_rev2_cum": "Écart Rév-2 (cum.)",
        "bud_rev1_cum": "Bud. Rév-1 (cum.)", "ecart_rev1_cum": "Écart Rév-1 (cum.)",
        "bud_ca_cum": "Bud. CA (cum.)", "ecart_ca_cum": "Écart CA (cum.)", "prec_cum": "Cumul. an. préc.",
    }
    if rep["kind"] == "bilan":
        col_labels["cumulatif"] = "Cumulatif"
    ws.append([("BILAN" if rep["kind"] == "bilan" else ("RÉSULTAT SOMMAIRE" if rep["kind"] == "pnl_sommaire" else "ÉTAT DES RÉSULTATS")) + f" — {rep['month_label']} {rep['year']}"])
    ws["A1"].font = title_f
    if not rep["locked"]:
        ws.append(["** DONNÉES PROVISOIRES (mois non verrouillé) **"])
        ws[f"A{ws.max_row}"].font = Font(bold=True, color="B45309")
    ws.append([])
    groups = rep.get("col_groups")
    if groups:
        ws.append(["", ""] + ["" for _ in cols])
        grow = ws.max_row
        for g in groups:
            gk = [k for k in g["keys"] if k in cols]
            if not gk:
                continue
            idxs = [cols.index(k) for k in gk]
            c0, c1 = 3 + min(idxs), 3 + max(idxs)
            if c1 > c0:
                ws.merge_cells(start_row=grow, start_column=c0, end_row=grow, end_column=c1)
            cell = ws.cell(grow, c0); cell.value = g["label"]
            cell.font = bold; cell.alignment = Alignment(horizontal="center"); cell.fill = fill
    header = ["Compte", "Description"] + [col_labels.get(k, k) for k in cols]
    ws.append(header)
    hcells = ws[ws.max_row]
    for c in hcells:
        c.font = bold; c.fill = fill; c.alignment = Alignment(horizontal="center", wrap_text=True)
    hcells[0].alignment = Alignment(horizontal="left")
    hcells[1].alignment = Alignment(horizontal="left")
    for ln in rep["lines"]:
        vs = _row_view_style(ln, bold_totals)
        is_pct = bool(ln.get("_pct"))
        row = [ln["account"] or "", ln["label"] or ""] + [ln["values"].get(k) for k in cols]
        ws.append(row)
        cells = ws[ws.max_row]
        row_fill = None if is_pct else (PatternFill("solid", fgColor=vs["bg"]) if vs["bg"] else None)
        row_font = Font(bold=False, italic=True, color="0E9488") if is_pct else (Font(bold=vs["bold"], color=vs["color"]) if (vs["bold"] or vs["color"]) else None)
        row_border = None
        if not is_pct and (vs["top"] or vs["bottom"]):
            row_border = Border(top=Side(style="thin", color=border_col) if vs["top"] else None,
                                bottom=Side(style="medium", color=border_col) if vs["bottom"] else None)
        for c in cells:
            if row_font:
                c.font = row_font
            if row_fill:
                c.fill = row_fill
            if row_border:
                c.border = row_border
        for i, k in enumerate(cols):
            cell = cells[2 + i]
            cell.alignment = Alignment(horizontal="right")
            if is_pct:
                cell.number_format = '0.0%'
                cell.font = Font(bold=False, italic=True, color="0E9488")
            else:
                cell.number_format = nf
                if k.startswith("ecart"):
                    cell.font = Font(bold=vs["bold"], italic=True, color=("FFFFFF" if vs["is_dark"] else "64748B"))
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 52
    for i in range(len(cols)):
        ws.column_dimensions[openpyxl.utils.get_column_letter(3 + i)].width = 16
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf

@api.get("/acct/report/excel")
async def acct_report_excel(type: str, year: int, month: int, cols: str = "", hide_zero: bool = False, user: dict = Depends(get_current_user)):
    if type == "bilan_sommaire":
        rep = await _bilan_sommaire_data(year, month)
        buf = _bilan_sommaire_excel(rep)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename=bilan_sommaire_{_pkey(year, month)}.xlsx"})
    if type not in ("bilan", "pnl", "pnl_sommaire"):
        raise HTTPException(status_code=400, detail="Type invalide")
    rep = await _acct_report(year, month, type)
    if type == "pnl":
        rep = _pnl_detail_adjust(rep)
    rep = _filter_rep_view(rep, cols, hide_zero)
    buf = _acct_excel(rep)
    fname = f"{'bilan' if type=='bilan' else ('resultats_sommaire' if type=='pnl_sommaire' else 'resultats')}_{_pkey(year, month)}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})

def _bilan_sommaire_excel(rep):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Bilan sommaire"
    from openpyxl.styles import Font, Alignment
    nf = '#,##0.00;[Red](#,##0.00)'
    ws.append([f"BILAN SOMMAIRE — {rep['month_label']} {rep['year']}"]); ws["A1"].font = Font(bold=True, size=13)
    ws.append([]); ws.append(["ACTIF", "", "PASSIF ET CAPITAUX", ""])
    for c in (1, 3): ws.cell(ws.max_row, c).font = Font(bold=True, size=11)
    a, p = rep["actif"], rep["passif"]
    for i in range(max(len(a), len(p))):
        la = a[i] if i < len(a) else None
        lp = p[i] if i < len(p) else None
        row = [la["label"] if la else "", la["value"] if la and la["value"] is not None else None,
               lp["label"] if lp else "", lp["value"] if lp and lp["value"] is not None else None]
        ws.append(row)
        rr = ws.max_row
        for (li, ci) in ((la, 1), (lp, 3)):
            if li and li["kind"] in ("total", "header"):
                ws.cell(rr, ci).font = Font(bold=True)
        for ci in (2, 4):
            if ws.cell(rr, ci).value is not None:
                ws.cell(rr, ci).number_format = nf; ws.cell(rr, ci).alignment = Alignment(horizontal="right")
    ws.column_dimensions["A"].width = 42; ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 42; ws.column_dimensions["D"].width = 18
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf


# ---------------------------------------------------------------------------
# Flux de trésorerie (méthode indirecte) — variation entre deux périodes
# ---------------------------------------------------------------------------
def _cf_category(group_label):
    """Retourne (section, sous-groupe) pour une section du Bilan."""
    g = (group_label or "").lower()
    if g.startswith("encaisse"):
        return ("cash", None)
    if "amortissement" in g and "cumul" in g:
        return ("exploitation", "amortissement")
    if "actifs incorporel" in g or g.startswith("immobilisation"):
        return ("investissement", None)
    if ("marge de cr" in g or "long terme" in g or "capital action" in g
            or "non répartis" in g or "non-répartis" in g or "non repartis" in g
            or "distribution" in g or g.startswith("avoir")):
        return ("financement", None)
    return ("exploitation", "fdr")  # fonds de roulement (par défaut)

def _bilan_groups(eng):
    """Ordonne les comptes du Bilan par section (libellé du total de fin de groupe)."""
    sd = eng.sheets["Bilan Détaillé"]
    groups, pending = [], []
    for r in sorted(sd["rows"].keys()):
        if r > 173:
            break
        acct = sd["acct"].get(r)
        cells = sd["rows"][r]
        label = cells.get("C")
        lbl = str(label).strip() if isinstance(label, str) else ""
        if acct is not None:
            pending.append(acct)
        else:
            raw = cells.get("I")
            if isinstance(raw, str) and raw.startswith("=") and lbl and pending:
                groups.append({"label": lbl, "accounts": pending})
                pending = []
    return groups

async def _cashflow_data(open_year, open_month, close_year, close_month):
    eng = await _load_engine()
    if not eng:
        raise HTTPException(status_code=400, detail="Aucun modèle importé. Un administrateur doit d'abord importer le modèle Excel.")
    open_pk, close_pk = _pkey(open_year, open_month), _pkey(close_year, close_month)
    if open_pk == close_pk:
        raise HTTPException(status_code=400, detail="Les périodes d'ouverture et de clôture doivent être différentes.")
    bv_open_doc = await db.acct_bv.find_one({"_id": open_pk})
    bv_close_doc = await db.acct_bv.find_one({"_id": close_pk})
    if not bv_close_doc:
        raise HTTPException(status_code=404, detail=f"Aucune BV pour {MONTHS_FR[close_month-1]} {close_year}")
    if not bv_open_doc:
        raise HTTPException(status_code=404, detail=f"Aucune BV d'ouverture pour {MONTHS_FR[open_month-1]} {open_year}")
    amap = await _account_map()
    bv_open = _bv_dict(bv_open_doc["accounts"], amap)
    bv_close = _bv_dict(bv_close_doc["accounts"], amap)
    groups = _bilan_groups(eng)

    def bal(bvd, acct):
        return float((bvd.get(acct) or {}).get("i", 0.0))

    def ale(bvd):  # Actif − Passif − Avoir sur les comptes du Bilan (= bénéfice net cumulatif)
        return sum((1 if a // 1000000 == 1 else -1) * bal(bvd, a) for g in groups for a in g["accounts"])

    benefice_net = round(ale(bv_close) - ale(bv_open), 2)

    fdr_lines, inv_lines, fin_lines = [], [], []
    amort_total = cash_open = cash_close = 0.0
    for grp in groups:
        cat, sub = _cf_category(grp["label"])
        eff = oi = ci = 0.0
        for a in grp["accounts"]:
            o, c = bal(bv_open, a), bal(bv_close, a)
            oi += o; ci += c
            d = c - o
            eff += (-d if a // 1000000 == 1 else d)
        eff = round(eff, 2)
        if cat == "cash":
            cash_open += oi; cash_close += ci
            continue
        if abs(eff) < 0.005:
            continue
        disp = grp["label"]
        if cat == "financement" and ("année courante" in disp.lower() or "annee courante" in disp.lower()):
            disp = "Bénéfices non répartis et distributions"
        line = {"label": disp, "value": eff}
        if cat == "exploitation" and sub == "amortissement":
            amort_total += eff
        elif cat == "exploitation":
            fdr_lines.append(line)
        elif cat == "investissement":
            inv_lines.append(line)
        else:
            fin_lines.append(line)

    amort_total = round(amort_total, 2)
    exploitation_total = round(benefice_net + amort_total + sum(l["value"] for l in fdr_lines), 2)
    investissement_total = round(sum(l["value"] for l in inv_lines), 2)
    financement_total = round(sum(l["value"] for l in fin_lines), 2)
    variation_nette = round(exploitation_total + investissement_total + financement_total, 2)
    cash_open, cash_close = round(cash_open, 2), round(cash_close, 2)
    ecart = round(cash_close - (cash_open + variation_nette), 2)
    period = await db.acct_periods.find_one({"_id": close_pk})
    return {
        "open_period": open_pk, "close_period": close_pk,
        "open_label": f"{MONTHS_FR[open_month-1]} {open_year}", "close_label": f"{MONTHS_FR[close_month-1]} {close_year}",
        "locked": bool(period and period.get("locked")),
        "benefice_net": benefice_net, "amortissement": amort_total, "fdr": fdr_lines,
        "exploitation_total": exploitation_total,
        "investissement": inv_lines, "investissement_total": investissement_total,
        "financement": fin_lines, "financement_total": financement_total,
        "variation_nette": variation_nette,
        "encaisse_ouverture": cash_open, "encaisse_cloture": cash_close,
        "encaisse_calculee": round(cash_open + variation_nette, 2),
        "ecart": ecart, "balanced": abs(ecart) < 1.0,
    }

@api.get("/acct/cashflow")
async def acct_cashflow(open_year: int, open_month: int, close_year: int, close_month: int, user: dict = Depends(get_current_user)):
    return await _cashflow_data(open_year, open_month, close_year, close_month)

def _cashflow_excel(rep):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Flux de trésorerie"
    from openpyxl.styles import Font, PatternFill, Alignment
    bold = Font(bold=True); title_f = Font(bold=True, size=14); sect_f = Font(bold=True, size=11, color="0F172A")
    fill = PatternFill("solid", fgColor="E2E8F0"); sfill = PatternFill("solid", fgColor="F1F5F9")
    nf = '#,##0.00;[Red](#,##0.00)'

    def add(label, value=None, style=None):
        ws.append([label, value if value is not None else None])
        row = ws[ws.max_row]
        if style == "title":
            row[0].font = title_f
        elif style == "section":
            row[0].font = sect_f
            for c in row: c.fill = sfill
        elif style == "subtotal":
            for c in row: c.font = bold; c.fill = fill
        elif style == "net":
            for c in row: c.font = Font(bold=True, size=12)
        if value is not None:
            row[1].number_format = nf; row[1].alignment = Alignment(horizontal="right")

    add(f"ÉTAT DES FLUX DE TRÉSORERIE", None, "title")
    add(f"Du {rep['open_label']} au {rep['close_label']} (méthode indirecte)")
    if not rep["locked"]:
        add("** DONNÉES PROVISOIRES (mois de clôture non verrouillé) **")
    ws.append([])
    add("ACTIVITÉS D'EXPLOITATION", None, "section")
    add("Bénéfice net (perte nette)", rep["benefice_net"])
    if abs(rep["amortissement"]) >= 0.005:
        add("Amortissement", rep["amortissement"])
    if rep["fdr"]:
        add("Variation des éléments hors caisse du fonds de roulement :")
        for l in rep["fdr"]:
            add(f"   {l['label']}", l["value"])
    add("Flux liés aux activités d'exploitation", rep["exploitation_total"], "subtotal")
    ws.append([])
    add("ACTIVITÉS D'INVESTISSEMENT", None, "section")
    for l in rep["investissement"]:
        add(l["label"], l["value"])
    add("Flux liés aux activités d'investissement", rep["investissement_total"], "subtotal")
    ws.append([])
    add("ACTIVITÉS DE FINANCEMENT", None, "section")
    for l in rep["financement"]:
        add(l["label"], l["value"])
    add("Flux liés aux activités de financement", rep["financement_total"], "subtotal")
    ws.append([])
    add("VARIATION NETTE DE LA TRÉSORERIE", rep["variation_nette"], "net")
    add("Encaisse à l'ouverture", rep["encaisse_ouverture"])
    add("Encaisse à la clôture", rep["encaisse_cloture"], "subtotal")
    ws.column_dimensions["A"].width = 58; ws.column_dimensions["B"].width = 20
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf

@api.get("/acct/cashflow/excel")
async def acct_cashflow_excel(open_year: int, open_month: int, close_year: int, close_month: int, user: dict = Depends(get_current_user)):
    rep = await _cashflow_data(open_year, open_month, close_year, close_month)
    buf = _cashflow_excel(rep)
    fname = f"flux_tresorerie_{rep['open_period']}_{rep['close_period']}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})

# ---------------------------------------------------------------------------
# Export PDF des rapports comptables (Bilan / Résultats / Bilan sommaire / Flux)
# ---------------------------------------------------------------------------
def _pdf_money(v):
    if v is None or v == "":
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    neg = v < -0.004
    s = f"{abs(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"({s})" if neg else s

def _acct_pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    cols = rep["value_cols"]
    col_labels = {
        "mois": f"{rep['month_label']} {rep['year']}", "cumulatif": "Réel à date",
        "reel": f"Réel {rep['month_label']}", "bud_rev2": "Bud. Rév-2", "ecart_rev2": "Écart Rév-2",
        "bud_rev1": "Bud. Rév-1", "ecart_rev1": "Écart Rév-1", "bud_ca": "Bud. CA",
        "ecart_ca": "Écart CA", "reel_prec": "Réel an. préc.",
        "bud_rev2_cum": "Bud. Rév-2", "ecart_rev2_cum": "Écart Rév-2",
        "bud_rev1_cum": "Bud. Rév-1", "ecart_rev1_cum": "Écart Rév-1",
        "bud_ca_cum": "Bud. CA", "ecart_ca_cum": "Écart CA", "prec_cum": "Cumul. an. préc.",
    }
    if rep["kind"] == "bilan":
        col_labels["cumulatif"] = "Cumulatif"
    NAVY = colors.HexColor("#0F172A"); RED = colors.HexColor("#DC2626")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor=NAVY, fontSize=13)
    sub = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=8)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=6, leading=7)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
    heading = "BILAN" if rep["kind"] == "bilan" else ("RÉSULTAT SOMMAIRE" if rep["kind"] == "pnl_sommaire" else "ÉTAT DES RÉSULTATS")
    el = [Paragraph(f"{heading} — {rep['month_label']} {rep['year']}", title),
          Paragraph(f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}" + ("" if rep["locked"] else " · DONNÉES PROVISOIRES (mois non verrouillé)"), sub),
          Spacer(1, 5)]
    grid = colors.HexColor("#E2E8F0")
    groups = rep.get("col_groups")
    data = []
    span_ops = []
    hri = 0
    if groups:
        grp = ["", ""] + ["" for _ in cols]
        for g in groups:
            gk = [k for k in g["keys"] if k in cols]
            if not gk:
                continue
            idxs = [cols.index(k) for k in gk]
            c0, c1 = 2 + min(idxs), 2 + max(idxs)
            grp[c0] = g["label"]
            if c1 > c0:
                span_ops.append(("SPAN", (c0, 0), (c1, 0)))
        data.append(grp)
        hri = 1
    header = ["Compte", "Description"] + [col_labels.get(k, k) for k in cols]
    data.append(header)
    ops = [
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, hri), (-1, -1), 0.25, grid),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("BACKGROUND", (0, hri), (-1, hri), NAVY), ("TEXTCOLOR", (0, hri), (-1, hri), colors.white),
        ("FONTNAME", (0, hri), (-1, hri), "Helvetica-Bold"),
        ("ALIGN", (0, hri), (1, hri), "LEFT"),
    ]
    if groups:
        ops += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (2, 0), (-1, 0), "CENTER"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.4, grid),
        ] + span_ops
    bold_totals = "sommaire" not in rep["kind"]
    GREEN = colors.HexColor("#22C55E")
    for ln in rep["lines"]:
        ri = len(data)
        vs = _row_view_style(ln, bold_totals)
        is_dark = vs["is_dark"]
        is_pct = bool(ln.get("_pct"))
        bold = False if is_pct else vs["bold"]
        if is_pct:
            desc_color = GREEN
        elif is_dark:
            desc_color = colors.white
        else:
            desc_color = colors.HexColor("#" + vs["color"]) if vs["color"] else colors.black
        desc_style = ParagraphStyle(f"d{ri}", parent=(cellb if bold else cell), textColor=desc_color)
        if is_pct:
            desc_style = ParagraphStyle(f"dp{ri}", parent=cell, fontName="Helvetica-Oblique", textColor=GREEN)
        row = [str(ln["account"] or ""), Paragraph(str(ln["label"] or ""), desc_style)]
        for k in cols:
            row.append(_pdf_pct(ln["values"].get(k)) if is_pct else _pdf_money(ln["values"].get(k)))
        data.append(row)
        if is_pct:
            ops.append(("TEXTCOLOR", (0, ri), (-1, ri), GREEN))
            ops.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Oblique"))
            continue
        if is_dark:
            ops.append(("BACKGROUND", (0, ri), (-1, ri), NAVY))
            ops.append(("TEXTCOLOR", (0, ri), (-1, ri), colors.white))
        elif vs["bg"]:
            ops.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#" + vs["bg"])))
        if bold:
            ops.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"))
        if not is_dark and vs["color"]:
            ops.append(("TEXTCOLOR", (0, ri), (-1, ri), colors.HexColor("#" + vs["color"])))
        if vs["top"]:
            ops.append(("LINEABOVE", (0, ri), (-1, ri), 0.5, colors.HexColor("#94A3B8")))
        if vs["bottom"]:
            ops.append(("LINEBELOW", (0, ri), (-1, ri), 0.9, colors.HexColor("#94A3B8")))
        for ci, k in enumerate(cols):
            col_idx = 2 + ci
            v = ln["values"].get(k)
            neg = False
            try:
                neg = v is not None and float(v) < -0.004
            except (TypeError, ValueError):
                neg = False
            if k.startswith("ecart"):
                ops.append(("FONTNAME", (col_idx, ri), (col_idx, ri), "Helvetica-BoldOblique" if bold else "Helvetica-Oblique"))
                if not neg and not is_dark:
                    ops.append(("TEXTCOLOR", (col_idx, ri), (col_idx, ri), colors.HexColor("#64748B")))
            if neg:
                ops.append(("TEXTCOLOR", (col_idx, ri), (col_idx, ri), colors.HexColor("#FCA5A5") if is_dark else RED))
    ncols = len(cols)
    avail = 281.0
    acct_w, desc_w = 13.0, 46.0
    val_w = max(11.0, (avail - acct_w - desc_w) / max(1, ncols))
    col_widths = [acct_w * mm, desc_w * mm] + [val_w * mm] * ncols
    tbl = Table(data, colWidths=col_widths, repeatRows=hri + 1)
    tbl.setStyle(TableStyle(ops))
    el.append(tbl)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=10 * mm, bottomMargin=8 * mm, leftMargin=8 * mm, rightMargin=8 * mm)
    el.insert(0, _pdf_logo(38)); el.insert(1, Spacer(1, 3 * mm))
    doc.build(el)
    buf.seek(0)
    return buf

def _bilan_sommaire_pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); RED = colors.HexColor("#DC2626")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor=NAVY, fontSize=13)
    sub = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=8)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=8, leading=10)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Helvetica-Bold")
    a, p = rep["actif"], rep["passif"]
    el = [Paragraph(f"BILAN SOMMAIRE — {rep['month_label']} {rep['year']}", title),
          Paragraph(f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}" + ("" if rep["locked"] else " · DONNÉES PROVISOIRES"), sub),
          Spacer(1, 6)]
    data = [["ACTIF", "", "PASSIF ET CAPITAUX", ""]]
    ops = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]

    def bold_of(li):
        return bool(li and (li.get("kind") in ("total", "header") or (li.get("style") or {}).get("b")))

    for i in range(max(len(a), len(p))):
        ri = len(data)
        la = a[i] if i < len(a) else None
        lp = p[i] if i < len(p) else None
        la_b, lp_b = bold_of(la), bold_of(lp)
        row = [
            Paragraph((la["label"] if la else "") or "", cellb if la_b else cell),
            _pdf_money(la["value"]) if la and la.get("value") is not None else "",
            Paragraph((lp["label"] if lp else "") or "", cellb if lp_b else cell),
            _pdf_money(lp["value"]) if lp and lp.get("value") is not None else "",
        ]
        data.append(row)
        for li, vci in ((la, 1), (lp, 3)):
            if li and li.get("value") is not None:
                try:
                    if float(li["value"]) < -0.004:
                        ops.append(("TEXTCOLOR", (vci, ri), (vci, ri), RED))
                except (TypeError, ValueError):
                    pass
    tbl = Table(data, colWidths=[95 * mm, 40 * mm, 95 * mm, 40 * mm])
    tbl.setStyle(TableStyle(ops))
    el.append(tbl)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=12 * mm, bottomMargin=10 * mm, leftMargin=8 * mm, rightMargin=8 * mm)
    el.insert(0, _pdf_logo(38)); el.insert(1, Spacer(1, 3 * mm))
    doc.build(el)
    buf.seek(0)
    return buf

def _cashflow_pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); RED = colors.HexColor("#DC2626")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor=NAVY, fontSize=13)
    sub = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=8)
    el = [Paragraph("ÉTAT DES FLUX DE TRÉSORERIE", title),
          Paragraph(f"Du {rep['open_label']} au {rep['close_label']} (méthode indirecte)" + ("" if rep["locked"] else " · DONNÉES PROVISOIRES"), sub),
          Spacer(1, 6)]
    data = []
    ops = [
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
    ]

    def add(label, value=None, kind=None, indent=False):
        ri = len(data)
        lbl = ("     " if indent else "") + label
        data.append([lbl, _pdf_money(value) if value is not None else ""])
        if kind == "section":
            ops.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#F1F5F9")))
            ops.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"))
        elif kind == "subtotal":
            ops.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#E2E8F0")))
            ops.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"))
        elif kind == "net":
            ops.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"))
            ops.append(("LINEABOVE", (0, ri), (-1, ri), 0.8, NAVY))
        if value is not None:
            try:
                if float(value) < -0.004:
                    ops.append(("TEXTCOLOR", (1, ri), (1, ri), RED))
            except (TypeError, ValueError):
                pass

    add("ACTIVITÉS D'EXPLOITATION", None, "section")
    add("Bénéfice net (perte nette)", rep["benefice_net"], indent=True)
    if abs(rep["amortissement"]) >= 0.005:
        add("Amortissement", rep["amortissement"], indent=True)
    if rep["fdr"]:
        add("Variation des éléments hors caisse du fonds de roulement :")
        for l in rep["fdr"]:
            add(l["label"], l["value"], indent=True)
    add("Flux liés aux activités d'exploitation", rep["exploitation_total"], "subtotal")
    add("ACTIVITÉS D'INVESTISSEMENT", None, "section")
    for l in rep["investissement"]:
        add(l["label"], l["value"], indent=True)
    add("Flux liés aux activités d'investissement", rep["investissement_total"], "subtotal")
    add("ACTIVITÉS DE FINANCEMENT", None, "section")
    for l in rep["financement"]:
        add(l["label"], l["value"], indent=True)
    add("Flux liés aux activités de financement", rep["financement_total"], "subtotal")
    add("VARIATION NETTE DE LA TRÉSORERIE", rep["variation_nette"], "net")
    add("Encaisse à l'ouverture", rep["encaisse_ouverture"], indent=True)
    add("Encaisse à la clôture", rep["encaisse_cloture"], "subtotal")
    tbl = Table(data, colWidths=[135 * mm, 45 * mm])
    tbl.setStyle(TableStyle(ops))
    el.append(tbl)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=12 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    el.insert(0, _pdf_logo(38)); el.insert(1, Spacer(1, 3 * mm))
    doc.build(el)
    buf.seek(0)
    return buf

@api.get("/acct/report/pdf")
async def acct_report_pdf(type: str, year: int, month: int, cols: str = "", hide_zero: bool = False, user: dict = Depends(get_current_user)):
    if type == "bilan_sommaire":
        rep = await _bilan_sommaire_data(year, month)
        buf = _bilan_sommaire_pdf(rep)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f"attachment; filename=bilan_sommaire_{_pkey(year, month)}.pdf"})
    if type not in ("bilan", "pnl", "pnl_sommaire"):
        raise HTTPException(status_code=400, detail="Type invalide")
    rep = await _acct_report(year, month, type)
    if type == "pnl":
        rep = _pnl_detail_adjust(rep)
    rep = _filter_rep_view(rep, cols, hide_zero)
    buf = _acct_pdf(rep)
    fname = f"{'bilan' if type=='bilan' else ('resultats_sommaire' if type=='pnl_sommaire' else 'resultats')}_{_pkey(year, month)}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})

@api.get("/acct/cashflow/pdf")
async def acct_cashflow_pdf(open_year: int, open_month: int, close_year: int, close_month: int, user: dict = Depends(get_current_user)):
    rep = await _cashflow_data(open_year, open_month, close_year, close_month)
    buf = _cashflow_pdf(rep)
    fname = f"flux_tresorerie_{rep['open_period']}_{rep['close_period']}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


# ===========================================================================
# Entité comptable indépendante : « 9434-3977 QC inc. »
# Saisie directe (journal général), balance de vérification, verrouillage annuel.
# Données 100% isolées du reste du module Comptabilité (collections qc9434_*).
# ===========================================================================
class QcLine(BaseModel):
    account: str
    account_name: str = ""
    tiers: str = ""
    debit: float = 0.0
    credit: float = 0.0

class QcEntry(BaseModel):
    date: str
    description: str = ""
    reference: str = ""
    lines: List[QcLine]

class QcExternalContact(BaseModel):
    name: str
    email: str = ""
    report_types: List[str] = []
    active: bool = True

QC_EXTERNAL_CATALOG = [
    {"key": "etats_financiers_pdf", "label": "États Financiers complets (PDF)", "fmt": "pdf"},
    {"key": "etats_financiers", "label": "États Financiers complets (Excel)", "fmt": "xlsx"},
    {"key": "bilan_pdf", "label": "Bilan détaillé (PDF)", "fmt": "pdf"},
    {"key": "pnl_pdf", "label": "État des résultats (PDF)", "fmt": "pdf"},
    {"key": "trial_balance", "label": "Balance de vérification (Excel)", "fmt": "xlsx"},
    {"key": "bilan", "label": "Bilan détaillé (Excel)", "fmt": "xlsx"},
    {"key": "pnl", "label": "État des résultats (Excel)", "fmt": "xlsx"},
]
_QC_CAT_LABELS = {c["key"]: c["label"] for c in QC_EXTERNAL_CATALOG}

def _qc_entry_out(d):
    return {"id": str(d["_id"]), "year": d.get("year"), "date": d.get("date"),
            "num": d.get("num", ""), "seq": d.get("seq"),
            "description": d.get("description", ""), "reference": d.get("reference", ""),
            "lines": d.get("lines", []), "total": d.get("total", 0.0),
            "source": d.get("source"), "source_id": d.get("source_id"),
            "created_at": d.get("created_at"), "created_by": d.get("created_by"),
            "updated_at": d.get("updated_at")}

async def _qc_year_doc(year: int):
    return await db.qc9434_years.find_one({"_id": int(year)})

async def _qc_next_seq(year):
    top = await db.qc9434_entries.find({"year": int(year)}).sort("seq", -1).limit(1).to_list(1)
    n = (top[0].get("seq") or 0) + 1 if top else 1
    return n, f"{year}-{n:04d}"

def _qc_validate_line_dicts(lines):
    if not lines or len(lines) < 2:
        raise HTTPException(status_code=400, detail="L'écriture doit comporter au moins deux lignes.")
    td = round(sum(float(l.get("debit") or 0) for l in lines), 2)
    tc = round(sum(float(l.get("credit") or 0) for l in lines), 2)
    for l in lines:
        if not (str(l.get("account") or "").strip()):
            raise HTTPException(status_code=400, detail="Chaque ligne doit avoir un numéro de compte.")
    if td <= 0 and tc <= 0:
        raise HTTPException(status_code=400, detail="Le montant de l'écriture ne peut être nul.")
    if abs(td - tc) > 0.005:
        raise HTTPException(status_code=400, detail=f"Écriture déséquilibrée : débits {td:,.2f} $ ≠ crédits {tc:,.2f} $.")
    return td

async def _qc_post_entry(year, date, description, line_dicts, reference="", source=None, source_id=None, actor=None):
    """Insère une écriture (validée + numérotée). Retourne le doc."""
    total = _qc_validate_line_dicts(line_dicts)
    seq, num = await _qc_next_seq(year)
    doc = {"year": int(year), "date": date, "num": num, "seq": seq,
           "description": (description or "").strip(), "reference": (reference or "").strip(),
           "lines": line_dicts, "total": total, "source": source, "source_id": source_id,
           "created_at": datetime.now(timezone.utc).isoformat(),
           "created_by": (actor or {}).get("email") if actor else "système",
           "company_id": await _company_id("qc9434")}
    res = await db.qc9434_entries.insert_one(doc)
    await db.qc9434_years.update_one({"_id": int(year)}, {"$inc": {"entry_count": 1}})
    doc["_id"] = res.inserted_id
    return doc

def _qc_validate_lines(lines):
    if not lines:
        raise HTTPException(status_code=400, detail="L'écriture doit comporter au moins deux lignes.")
    td = round(sum(l.debit or 0 for l in lines), 2)
    tc = round(sum(l.credit or 0 for l in lines), 2)
    for l in lines:
        if not (l.account or "").strip():
            raise HTTPException(status_code=400, detail="Chaque ligne doit avoir un numéro de compte.")
        if (l.debit or 0) < 0 or (l.credit or 0) < 0:
            raise HTTPException(status_code=400, detail="Les montants ne peuvent pas être négatifs.")
        if (l.debit or 0) > 0 and (l.credit or 0) > 0:
            raise HTTPException(status_code=400, detail="Une ligne ne peut être à la fois au débit et au crédit.")
    if td <= 0 and tc <= 0:
        raise HTTPException(status_code=400, detail="Le montant de l'écriture ne peut être nul.")
    if abs(td - tc) > 0.005:
        raise HTTPException(status_code=400, detail=f"Écriture déséquilibrée : débits {td:,.2f} $ ≠ crédits {tc:,.2f} $.")
    return td

# Comptes & taux par défaut (modèle Commandité)
QC_DEF = {"sales": "400310", "ar": "130118", "ap": "211010", "tps_pay": "215310",
          "tvq_pay": "215301", "tps_rec": "145110", "tvq_rec": "145101", "cash": "100110", "bnr": "330010"}
QC_TPS, QC_TVQ = 0.05, 0.09975

# Chiffres comparatifs 2025 figés (modèle Excel « Commandité ACCS EF 2026 »)
QC_EF_PREV_YEAR = 2025
QC_EF_PREV = {
    "result": {"rev": 10000.0, "juridique": 7720.0, "expertise": 32.0, "financiers": 68.0,
               "charges": 7820.0, "avant_qp": 2180.0, "qp": -95.0, "avant_impot": 2275.0,
               "impots": 1864.0, "net": 411.0},
    "bnr": {"debut": 5278.0, "fin": 5689.0},
    "bilan": {"treso": 6735.0, "clients": 11498.0, "taxes_rec": 1447.0, "total_ct": 19680.0,
              "placement": 271.0, "total_actif": 19951.0, "crediteurs": 11879.0,
              "taxes_rem": 0.0, "impot_pay": 637.0, "total_passif": 12516.0,
              "capital": 100.0, "bnr": 7335.0, "total_pc": 19951.0},
}
QC_EF_ADMINS_DEFAULT = {"a1_name": "Marco Vézina", "a1_title": "Administrateur",
                        "a2_name": "Simon Chevalier-Fournier", "a2_title": "Administrateur"}

# Flux de trésorerie 2025 figé (modèle « Commandité ACCS EF 2026 »)
QC_CF_PREV = {
    "net": 411.0, "qp_noncash": -95.0, "wc": 0.0, "op_sub": 316.0,
    "capital": 0.0, "placement": 350.0, "net_var": 666.0,
    "cash_open": 8545.0, "cash_close": 9211.0,
    "wc_detail": {"clients": 1.0, "taxes_rec": 0.0, "crediteurs": 0.0, "taxes_rem": 0.0, "impot": 0.0, "total": 1.0},
}

# Bilan de clôture 2025 = solde d'ouverture 2026, en base débit (actif +, passif/capitaux −).
# Aligné sur les données réelles (créance client 11 497,50 $ = 10 000 $ × 1,14975) pour un solde net nul.
QC_OPENING_2026 = {
    "100110": 6735.00, "130118": 11497.50, "145110": 1447.00, "160010": 271.00,
    "211010": -11879.00, "215400": -637.00, "310000": -100.00, "330010": -7334.50,
}

async def _qc_ef_admins():
    cfg = await db.qc9434_settings.find_one({"_id": "config"}) or {}
    a = cfg.get("ef_admins") or {}
    return {**QC_EF_ADMINS_DEFAULT, **a}


async def _qc_acc_name(gl):
    a = await db.qc9434_accounts.find_one({"gl": gl})
    return a.get("description", "") if a else ""


# ---- Années -------------------------------------------------------------
@api.get("/qc9434/years")
async def qc_years(user: dict = Depends(get_current_user)):
    docs = await db.qc9434_years.find({"company_id": await _company_id("qc9434")}).sort("_id", -1).to_list(1000)
    cfg = await db.qc9434_settings.find_one({"_id": "config"}) or {}
    active = cfg.get("active_year")
    if active is None and docs:
        active = docs[0]["_id"]
    return {"years": [{"year": d["_id"], "locked": d.get("locked", False),
                       "locked_by": d.get("locked_by"), "locked_at": d.get("locked_at"),
                       "entry_count": d.get("entry_count", 0)} for d in docs],
            "active_year": active}

@api.post("/qc9434/years")
async def qc_create_year(year: Optional[int] = None, user: dict = Depends(require_admin)):
    docs = await db.qc9434_years.find({"company_id": await _company_id("qc9434")}).sort("_id", -1).to_list(1000)
    if docs:
        latest = docs[0]
        if not latest.get("locked"):
            raise HTTPException(status_code=400, detail=f"Vous devez d'abord verrouiller l'année {latest['_id']} avant de créer une nouvelle année.")
        new_year = int(year) if year else latest["_id"] + 1
    else:
        new_year = int(year) if year else datetime.now(timezone.utc).year
    if await _qc_year_doc(new_year):
        raise HTTPException(status_code=400, detail=f"L'année {new_year} existe déjà.")
    await db.qc9434_years.insert_one({"_id": new_year, "locked": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"),
        "company_id": await _company_id("qc9434")})
    await db.qc9434_settings.update_one({"_id": "config"}, {"$set": {"active_year": new_year}}, upsert=True)
    await log_action(user, "Créer", "9434 — Année", str(new_year))
    return {"success": True, "year": new_year}

@api.put("/qc9434/years/active")
async def qc_set_active_year(year: int, user: dict = Depends(get_current_user)):
    if not await _qc_year_doc(year):
        raise HTTPException(status_code=404, detail="Année introuvable")
    await db.qc9434_settings.update_one({"_id": "config"}, {"$set": {"active_year": int(year)}}, upsert=True)
    return {"success": True, "active_year": int(year)}

@api.post("/qc9434/years/lock")
async def qc_lock_year(year: int, locked: bool = True, user: dict = Depends(require_admin)):
    y = await _qc_year_doc(year)
    if not y:
        raise HTTPException(status_code=404, detail="Année introuvable")
    if locked:
        await _qc_post_closing(year, user)
    else:
        await db.qc9434_entries.delete_many({"year": int(year), "source": "closing"})
    await db.qc9434_years.update_one({"_id": int(year)}, {"$set": {
        "locked": bool(locked), "locked_by": user.get("email") if locked else None,
        "locked_at": datetime.now(timezone.utc).isoformat() if locked else None}})
    await log_action(user, "Verrouiller" if locked else "Déverrouiller", "9434 — Année", str(year))
    return {"success": True, "year": int(year), "locked": bool(locked)}

async def _qc_post_closing(year, user):
    """Écriture de fermeture : solde les comptes de résultat de l'exercice vers les BNR."""
    _cid = await _company_id("qc9434")
    await db.qc9434_entries.delete_many({"year": int(year), "source": "closing", "company_id": _cid})
    accts = {d["gl"]: d for d in await db.qc9434_accounts.find({"company_id": _cid}).to_list(2000)}
    docs = await db.qc9434_entries.find({"year": int(year), "source": {"$ne": "closing"}, "company_id": _cid}).to_list(50000)
    bal = {}
    for e in docs:
        for l in e.get("lines", []):
            gl = (l.get("account") or "").strip()
            if (accts.get(gl) or {}).get("type") in ("produit", "charge"):
                bal[gl] = bal.get(gl, 0.0) + float(l.get("debit") or 0) - float(l.get("credit") or 0)
    lines, td, tc = [], 0.0, 0.0
    for gl, b in bal.items():
        b = round(b, 2)
        if abs(b) < 0.005:
            continue
        name = (accts.get(gl) or {}).get("description", "")
        if b > 0:  # solde débiteur (charge) → créditer pour fermer
            lines.append({"account": gl, "account_name": name, "tiers": "", "debit": 0.0, "credit": b}); tc += b
        else:
            lines.append({"account": gl, "account_name": name, "tiers": "", "debit": -b, "credit": 0.0}); td += -b
    if not lines:
        return None
    diff = round(td - tc, 2)  # bénéfice net (>0 = profit)
    bnr_name = (accts.get(QC_DEF["bnr"]) or {}).get("description", "Bénéfices non répartis")
    if diff > 0:
        lines.append({"account": QC_DEF["bnr"], "account_name": bnr_name, "tiers": "", "debit": 0.0, "credit": diff})
    elif diff < 0:
        lines.append({"account": QC_DEF["bnr"], "account_name": bnr_name, "tiers": "", "debit": -diff, "credit": 0.0})
    date = f"{year}-12-31"
    dts = [e.get("date") for e in docs if e.get("date")]
    if dts:
        date = max(dts)
    return await _qc_post_entry(year, date, "Écriture de fermeture — transfert du résultat aux BNR",
        lines, reference="FERMETURE", source="closing", actor=user)

# ---- Écritures (journal général) ---------------------------------------
@api.get("/qc9434/entries")
async def qc_entries(year: int, user: dict = Depends(get_current_user)):
    docs = await db.qc9434_entries.find({"year": int(year), "company_id": await _company_id("qc9434")}).sort([("date", 1), ("created_at", 1)]).to_list(5000)
    return [_qc_entry_out(d) for d in docs]

@api.post("/qc9434/entries")
async def qc_create_entry(payload: QcEntry, year: int, user: dict = Depends(get_current_user)):
    y = await _qc_year_doc(year)
    if not y:
        raise HTTPException(status_code=404, detail="Année introuvable — créez d'abord l'exercice.")
    if y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'année {year} est verrouillée. Impossible de saisir de nouvelles écritures.")
    doc = await _qc_post_entry(year, payload.date, payload.description,
        [l.model_dump() for l in payload.lines], reference=payload.reference, source="manual", actor=user)
    await log_action(user, "Créer", "9434 — Écriture", f"{doc['num']} · {payload.description[:40]} ({doc['total']:,.2f} $)")
    return _qc_entry_out(doc)

@api.put("/qc9434/entries/{eid}")
async def qc_update_entry(eid: str, payload: QcEntry, user: dict = Depends(get_current_user)):
    ex = await db.qc9434_entries.find_one({"_id": _oid(eid)})
    if not ex:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    y = await _qc_year_doc(ex["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'année {ex['year']} est verrouillée.")
    total = _qc_validate_lines(payload.lines)
    await db.qc9434_entries.update_one({"_id": _oid(eid)}, {"$set": {
        "date": payload.date, "description": payload.description.strip(),
        "reference": payload.reference.strip(), "lines": [l.model_dump() for l in payload.lines],
        "total": total, "updated_at": datetime.now(timezone.utc).isoformat()}})
    await log_action(user, "Modifier", "9434 — Écriture", f"{payload.date} · {payload.description[:40]}")
    return _qc_entry_out(await db.qc9434_entries.find_one({"_id": _oid(eid)}))

@api.delete("/qc9434/entries/{eid}")
async def qc_delete_entry(eid: str, user: dict = Depends(get_current_user)):
    ex = await db.qc9434_entries.find_one({"_id": _oid(eid)})
    if not ex:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    y = await _qc_year_doc(ex["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'année {ex['year']} est verrouillée.")
    await db.qc9434_entries.delete_one({"_id": _oid(eid)})
    await db.qc9434_years.update_one({"_id": ex["year"]}, {"$inc": {"entry_count": -1}})
    await log_action(user, "Supprimer", "9434 — Écriture", f"{ex.get('date')} · {ex.get('description','')[:40]}")
    return {"success": True}

# ---- Balance de vérification (générée à partir des écritures) -----------
async def _qc_trial_balance(year: int):
    docs = await db.qc9434_entries.find({"year": int(year), "source": {"$ne": "closing"}, "company_id": await _company_id("qc9434")}).to_list(20000)
    agg = {}
    for e in docs:
        for l in e.get("lines", []):
            acc = (l.get("account") or "").strip()
            if not acc:
                continue
            a = agg.setdefault(acc, {"account": acc, "account_name": l.get("account_name", ""), "debit": 0.0, "credit": 0.0})
            a["debit"] += float(l.get("debit") or 0)
            a["credit"] += float(l.get("credit") or 0)
            if not a["account_name"] and l.get("account_name"):
                a["account_name"] = l.get("account_name")
    rows = []
    for acc in sorted(agg.keys(), key=lambda k: (len(k), k)):
        a = agg[acc]
        bal = round(a["debit"] - a["credit"], 2)
        rows.append({"account": a["account"], "account_name": a["account_name"],
                     "debit": round(a["debit"], 2), "credit": round(a["credit"], 2), "balance": bal})
    td = round(sum(r["debit"] for r in rows), 2)
    tc = round(sum(r["credit"] for r in rows), 2)
    return {"year": int(year), "rows": rows, "total_debit": td, "total_credit": tc,
            "balanced": abs(td - tc) < 0.005, "entry_count": len(docs)}

@api.get("/qc9434/trial-balance")
async def qc_trial_balance(year: int, user: dict = Depends(get_current_user)):
    return await _qc_trial_balance(year)

def _qc_tb_xlsx(tb):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Balance de vérification"
    from openpyxl.styles import Font, PatternFill, Alignment
    navy = PatternFill("solid", fgColor="063044"); white = Font(color="FFFFFF", bold=True)
    ws.append(["9434-3977 QC inc."]); ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Balance de vérification — Exercice {tb['year']}"]); ws["A2"].font = Font(size=10, italic=True)
    ws.append([])
    hdr = ["Compte", "Nom du compte", "Débit", "Crédit", "Solde"]
    ws.append(hdr)
    hr = ws.max_row
    for c in range(1, 6):
        cell = ws.cell(row=hr, column=c); cell.fill = navy; cell.font = white
    for r in tb["rows"]:
        ws.append([r["account"], r["account_name"], r["debit"], r["credit"], r["balance"]])
    ws.append(["", "TOTAL", tb["total_debit"], tb["total_credit"], round(tb["total_debit"] - tb["total_credit"], 2)])
    tr = ws.max_row
    for c in range(1, 6):
        ws.cell(row=tr, column=c).font = Font(bold=True)
    for col, w in zip("ABCDE", [14, 40, 16, 16, 16]):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=5, min_col=3, max_col=5):
        for cell in row:
            cell.number_format = '#,##0.00;(#,##0.00)'; cell.alignment = Alignment(horizontal="right")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.getvalue()

@api.get("/qc9434/trial-balance/excel")
async def qc_tb_excel(year: int, user: dict = Depends(get_current_user)):
    tb = await _qc_trial_balance(year)
    b = _qc_tb_xlsx(tb)
    return StreamingResponse(io.BytesIO(b),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=balance_verification_9434_{year}.xlsx"})

# ---- Envoi externe (contacts propres à cette entité) --------------------
async def _qc_generate_external(key, year):
    if key == "trial_balance":
        tb = await _qc_trial_balance(year)
        return _qc_tb_xlsx(tb), f"balance_verification_9434_{year}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if key == "bilan":
        rep = await _qc_bilan(year)
        return _qc_report_xlsx(rep, "Bilan détaillé"), f"bilan_9434_{year}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if key == "pnl":
        rep = await _qc_pnl(year)
        return _qc_report_xlsx(rep, "État des résultats"), f"resultats_9434_{year}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if key == "bilan_pdf":
        rep = await _qc_bilan(year)
        return _qc_report_pdf(rep, "BILAN DÉTAILLÉ", year), f"bilan_9434_{year}.pdf", "application/pdf"
    if key == "pnl_pdf":
        rep = await _qc_pnl(year)
        return _qc_report_pdf(rep, "ÉTAT DES RÉSULTATS", year), f"resultats_9434_{year}.pdf", "application/pdf"
    if key == "etats_financiers_pdf":
        return _qc_ef_pdf(await _qc_etats_financiers(year)), f"etats_financiers_9434_{year}.pdf", "application/pdf"
    if key == "etats_financiers":
        return _qc_ef_xlsx(await _qc_etats_financiers(year)), f"etats_financiers_9434_{year}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return None, None, None

@api.get("/qc9434/external/catalog")
async def qc_external_catalog(user: dict = Depends(get_current_user)):
    return QC_EXTERNAL_CATALOG

@api.get("/qc9434/external-contacts")
async def qc_list_external(user: dict = Depends(get_current_user)):
    docs = await db.qc9434_external_contacts.find().sort("name", 1).to_list(500)
    return [{"id": str(d["_id"]), "name": d.get("name", ""), "email": d.get("email", ""),
             "report_types": d.get("report_types", []), "active": d.get("active", True),
             "last_sent": d.get("last_sent")} for d in docs]

@api.post("/qc9434/external-contacts")
async def qc_create_external(payload: QcExternalContact, user: dict = Depends(require_admin)):
    qc_ec_doc = payload.model_dump()
    qc_ec_doc["company_id"] = await _company_id("qc9434")
    res = await db.qc9434_external_contacts.insert_one(qc_ec_doc)
    await log_action(user, "Créer", "9434 — Contact externe", payload.name)
    return {"success": True, "id": str(res.inserted_id)}

@api.put("/qc9434/external-contacts/{cid}")
async def qc_update_external(cid: str, payload: QcExternalContact, user: dict = Depends(require_admin)):
    ex = await db.qc9434_external_contacts.find_one({"_id": _oid(cid)})
    if not ex:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    await db.qc9434_external_contacts.update_one({"_id": _oid(cid)}, {"$set": payload.model_dump()})
    await log_action(user, "Modifier", "9434 — Contact externe", payload.name)
    return {"success": True}

@api.delete("/qc9434/external-contacts/{cid}")
async def qc_delete_external(cid: str, user: dict = Depends(require_admin)):
    ex = await db.qc9434_external_contacts.find_one({"_id": _oid(cid)})
    if not ex:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    await db.qc9434_external_contacts.delete_one({"_id": _oid(cid)})
    await log_action(user, "Supprimer", "9434 — Contact externe", ex.get("name", ""))
    return {"success": True}

@api.get("/qc9434/external/report")
async def qc_external_report(key: str, year: int, user: dict = Depends(get_current_user)):
    b, fn, mime = await _qc_generate_external(key, year)
    if b is None:
        raise HTTPException(status_code=404, detail="Rapport indisponible pour cette entité.")
    return StreamingResponse(io.BytesIO(b), media_type=mime, headers={"Content-Disposition": f"attachment; filename={fn}"})

@api.get("/qc9434/external/email/log")
async def qc_external_email_log(contact_id: Optional[str] = None, limit: int = 100, user: dict = Depends(get_current_user)):
    q = {}
    if contact_id:
        q["contact_id"] = contact_id
    docs = await db.qc9434_external_email_log.find(q).sort("sent_at", -1).to_list(int(limit))
    return [{"contact_id": d.get("contact_id"), "contact_name": d.get("contact_name"), "email": d.get("email"),
             "year": d.get("year"), "documents": d.get("documents", []), "doc_count": d.get("doc_count"),
             "missing": d.get("missing", []), "sent_at": d.get("sent_at"), "sent_by": d.get("sent_by")} for d in docs]

@api.post("/qc9434/external/email")
async def qc_external_email(contact_id: str, year: int, user: dict = Depends(get_current_user)):
    c = await db.qc9434_external_contacts.find_one({"_id": _oid(contact_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré. Un administrateur doit renseigner la clé Resend.")
    email = (c.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail=f"{c.get('name')} : aucun courriel renseigné")
    attachments, missing, doc_labels = [], [], []
    for key in c.get("report_types", []):
        b, fn, mime = await _qc_generate_external(key, year)
        if b is None:
            missing.append(_QC_CAT_LABELS.get(key, key)); continue
        attachments.append({"filename": fn, "content": list(b)})
        doc_labels.append(_QC_CAT_LABELS.get(key, key))
    if not attachments:
        raise HTTPException(status_code=400, detail="Aucun rapport disponible à envoyer. " + (f"Manquant : {', '.join(missing)}" if missing else ""))
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#1e293b;font-size:14px\">"
            f"<p>Bonjour,</p><p>Veuillez trouver ci-joint les documents financiers de <strong>9434-3977 QC inc.</strong> "
            f"pour l'exercice <strong>{year}</strong> ({len(attachments)} document(s)).</p>"
            f"<p style=\"color:#64748b;font-size:12px;margin-top:24px\">ACCSL Groupe — Plateforme financière</p></div>")
    try:
        res = await asyncio.to_thread(resend.Emails.send, {
            "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
            "to": [email], "subject": f"Documents financiers 9434-3977 QC inc. — {year}",
            "html": html, "attachments": attachments})
        rec = {"contact_id": contact_id, "contact_name": c.get("name", ""), "email": email,
               "year": int(year), "documents": doc_labels, "doc_count": len(attachments), "missing": missing,
               "sent_at": datetime.now(timezone.utc).isoformat(), "sent_by": (user or {}).get("email") or "système",
               "email_id": (res or {}).get("id") if isinstance(res, dict) else None,
               "company_id": await _company_id("qc9434")}
        await db.qc9434_external_email_log.insert_one(dict(rec))
        await db.qc9434_external_contacts.update_one({"_id": _oid(contact_id)}, {"$set": {"last_sent": {k: rec[k] for k in
            ("email", "year", "documents", "doc_count", "sent_at", "sent_by")}}})
        await log_action(user, "Envoyer", "9434 — Package externe", f"{c.get('name')} → {email} ({year})")
        msg = f"{len(attachments)} document(s) envoyé(s) à {email}"
        if missing:
            msg += f" · manquant : {', '.join(missing)}"
        return {"success": True, "message": msg}
    except Exception as e:
        logger.error(f"Envoi externe 9434 échec : {e}")
        raise HTTPException(status_code=400, detail=f"Échec d'envoi : {str(e)[:150]}")


# ---- Plan comptable (chart of accounts) --------------------------------
def _qc_type_from_gl(gl):
    p = str(gl).strip()[:1]
    return {"1": "actif", "2": "passif", "3": "capitaux", "4": "produit", "5": "charge"}.get(p, "actif")

QC_SECTIONS = {
    "actif_court": "Actif à court terme", "actif_placement": "Placement et autre participation",
    "actif_long": "Immobilisations", "passif_court": "Passif à court terme",
    "passif_long": "Passif à long terme", "capitaux": "Capitaux",
    "revenus": "Revenus", "charges": "Charges", "quote_part": "Quote-part des bénéfices", "impots": "Impôts",
}

# Plan comptable seed d'après le modèle « Commandité ACCS EF 2026 » (23 comptes + sections).
QC_ACCOUNTS_SEED = [
    ("100105", "Caisse populaire (CAD) - # 084129 - Part sociale", "actif", "actif_court"),
    ("100110", "Caisse populaire (CAD) - # 084129", "actif", "actif_court"),
    ("130118", "Comptes à recevoir - Apparentés", "actif", "actif_court"),
    ("145110", "TPS à recevoir", "actif", "actif_court"),
    ("145101", "TVQ à recevoir", "actif", "actif_court"),
    ("160010", "Participation - Société en commandite ACCS", "actif", "actif_placement"),
    ("211010", "Comptes à payer - Auxiliaire", "passif", "passif_court"),
    ("211120", "Provision - comptes à payer", "passif", "passif_court"),
    ("215301", "TVQ à payer", "passif", "passif_court"),
    ("215310", "TPS à payer", "passif", "passif_court"),
    ("215311", "TPS-TVQ à Recevoir/Payer", "passif", "passif_court"),
    ("215400", "Impôt à payer", "passif", "passif_court"),
    ("310000", "Actions ordinaires", "capitaux", "capitaux"),
    ("330010", "Bénéfices non-répartis - début", "capitaux", "capitaux"),
    ("400310", "Ventes - Services autres", "produit", "revenus"),
    ("400311", "Ventes - Revenus à facturer", "produit", "revenus"),
    ("450010", "Quote-part des bénéfices - Société en commandite ACCS", "produit", "quote_part"),
    ("540210", "Service d'expertise comptable et financière", "charge", "charges"),
    ("550108", "Services juridiques", "charge", "charges"),
    ("578220", "Intérêts sur le compte de banque", "charge", "charges"),
    ("579000", "Intérêts et pénalités", "charge", "charges"),
    ("580210", "Frais de banque", "charge", "charges"),
    ("595110", "Impôt exigible", "charge", "impots"),
]

async def _qc_seed_accounts():
    if await db.qc9434_accounts.count_documents({}) == 0:
        _cid = await _company_id("qc9434")
        docs = [{"gl": gl, "description": desc, "type": typ, "section": sec, "sort": i, "company_id": _cid}
                for i, (gl, desc, typ, sec) in enumerate(QC_ACCOUNTS_SEED)]
        await db.qc9434_accounts.insert_many(docs)

class QcAccount(BaseModel):
    gl: str
    description: str = ""
    type: str = "actif"
    section: str = "actif_court"

@api.get("/qc9434/accounts")
async def qc_accounts(user: dict = Depends(get_current_user)):
    await _qc_seed_accounts()
    docs = await db.qc9434_accounts.find({"company_id": await _company_id("qc9434")}).to_list(2000)
    docs.sort(key=lambda d: (str(d.get("gl"))))
    return {"sections": QC_SECTIONS,
            "accounts": [{"gl": d["gl"], "description": d.get("description", ""),
                          "type": d.get("type"), "section": d.get("section")} for d in docs]}

@api.post("/qc9434/accounts")
async def qc_create_account(payload: QcAccount, user: dict = Depends(get_current_user)):
    gl = payload.gl.strip()
    if not gl:
        raise HTTPException(status_code=400, detail="Numéro de compte requis.")
    if await db.qc9434_accounts.find_one({"gl": gl}):
        raise HTTPException(status_code=400, detail=f"Le compte {gl} existe déjà.")
    await db.qc9434_accounts.insert_one({"gl": gl, "description": payload.description.strip(),
        "type": payload.type, "section": payload.section, "company_id": await _company_id("qc9434")})
    await log_action(user, "Créer", "9434 — Compte", f"{gl} · {payload.description}")
    return {"success": True}

@api.put("/qc9434/accounts/{gl}")
async def qc_update_account(gl: str, payload: QcAccount, user: dict = Depends(get_current_user)):
    ex = await db.qc9434_accounts.find_one({"gl": gl})
    if not ex:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    await db.qc9434_accounts.update_one({"gl": gl}, {"$set": {"description": payload.description.strip(),
        "type": payload.type, "section": payload.section}})
    await log_action(user, "Modifier", "9434 — Compte", gl)
    return {"success": True}

@api.delete("/qc9434/accounts/{gl}")
async def qc_delete_account(gl: str, user: dict = Depends(get_current_user)):
    used = await db.qc9434_entries.find_one({"lines.account": gl})
    if used:
        raise HTTPException(status_code=400, detail="Compte utilisé dans des écritures — suppression impossible.")
    await db.qc9434_accounts.delete_one({"gl": gl})
    await log_action(user, "Supprimer", "9434 — Compte", gl)
    return {"success": True}

# ---- Balances par exercice (mouvement / antérieur / cumulatif) ---------
async def _qc_report_balances(year):
    """Retourne {gl: {movement, opening, cumulative}} + méta comptes."""
    await _qc_seed_accounts()
    _cid = await _company_id("qc9434")
    accts = {d["gl"]: d for d in await db.qc9434_accounts.find({"company_id": _cid}).to_list(2000)}
    docs = await db.qc9434_entries.find({"year": {"$lte": int(year)}, "source": {"$ne": "closing"}, "company_id": _cid}).to_list(50000)
    bal = {}
    for e in docs:
        cur = e.get("year") == int(year)
        for l in e.get("lines", []):
            gl = (l.get("account") or "").strip()
            if not gl:
                continue
            b = bal.setdefault(gl, {"movement": 0.0, "opening": 0.0})
            net = float(l.get("debit") or 0) - float(l.get("credit") or 0)
            if cur:
                b["movement"] += net
            else:
                b["opening"] += net
    for gl, b in bal.items():
        b["cumulative"] = round(b["opening"] + b["movement"], 2)
        b["movement"] = round(b["movement"], 2); b["opening"] = round(b["opening"], 2)
    return bal, accts

async def _qc_post_opening(year, targets, actor=None):
    """Pose l'à-nouveaux pour que le solde d'ouverture de `year` égale `targets` (base débit, actif +)."""
    y = int(year)
    await db.qc9434_entries.delete_many({"source": "opening", "$or": [{"opening_year": y}, {"num": f"OUV-{y}"}]})
    bal, accts = await _qc_report_balances(y)  # ouverture = report des écritures année < y (hors 'opening' supprimé)
    gls = set(targets) | set(bal)
    lines = []
    for gl in sorted(gls):
        target = round(float(targets.get(gl, 0.0)), 2)
        cur_open = round((bal.get(gl) or {}).get("opening", 0.0), 2)
        delta = round(target - cur_open, 2)
        if abs(delta) < 0.005:
            continue
        name = (accts.get(gl) or {}).get("description", gl)
        lines.append({"account": gl, "account_name": name, "tiers": "",
                      "debit": delta if delta > 0 else 0.0, "credit": round(-delta, 2) if delta < 0 else 0.0})
    if not lines:
        return None
    doc = {"year": y - 1, "date": f"{y - 1}-12-31", "num": f"OUV-{y}", "period": "ouverture", "opening_year": y,
           "description": f"Solde d'ouverture au 1er janvier {y} (report de la clôture {y - 1})",
           "source": "opening", "lines": lines,
           "created_at": datetime.now(timezone.utc).isoformat(),
           "created_by": (actor or {}).get("email", "système"),
           "company_id": await _company_id("qc9434")}
    await db.qc9434_entries.insert_one(doc)
    return doc

async def _qc_seed_opening_balances(actor=None):
    """Établit le solde d'ouverture 2026 = bilan de clôture 2025 du modèle (à-nouveaux)."""
    return await _qc_post_opening(2026, QC_OPENING_2026, actor)

def _acc_val(accts, gl, default_type):
    a = accts.get(gl) or {}
    return a.get("description", ""), a.get("type", default_type)

async def _qc_bilan(year):
    bal, accts = await _qc_report_balances(year)
    # net income (produit/charge/quote_part/impots) — équité
    def sum_pl(key):
        s = 0.0
        for gl, b in bal.items():
            t = (accts.get(gl) or {}).get("type")
            if t in ("produit", "charge"):
                s += b[key]
        return round(-s, 2)  # bénéfice = -(débit-crédit) des comptes de résultat
    ni = {"movement": sum_pl("movement"), "opening": sum_pl("opening"), "cumulative": sum_pl("cumulative")}

    order = ["actif_court", "actif_placement", "actif_long", "passif_court", "passif_long", "capitaux"]
    by_sec = {k: [] for k in order}
    for gl, a in accts.items():
        sec = a.get("section")
        if sec in by_sec:
            b = bal.get(gl, {"movement": 0, "opening": 0, "cumulative": 0})
            sign = 1 if a.get("type") == "actif" else -1  # passif/capitaux présentés positifs
            by_sec[sec].append({"gl": gl, "label": a.get("description", ""),
                "movement": round(sign * b["movement"], 2), "opening": round(sign * b["opening"], 2),
                "cumulative": round(sign * b["cumulative"], 2)})
    for k in by_sec:
        by_sec[k].sort(key=lambda r: r["gl"])

    lines = []
    def total_of(*secs):
        return {c: round(sum(r[c] for s in secs for r in by_sec[s]), 2) for c in ("movement", "opening", "cumulative")}

    lines.append({"kind": "title", "label": "ACTIF"})
    lines.append({"kind": "header", "label": QC_SECTIONS["actif_court"]})
    lines += [{"kind": "data", **r} for r in by_sec["actif_court"]]
    if by_sec["actif_placement"]:
        lines.append({"kind": "header", "label": QC_SECTIONS["actif_placement"]})
        lines += [{"kind": "data", **r} for r in by_sec["actif_placement"]]
    if by_sec["actif_long"]:
        lines.append({"kind": "header", "label": QC_SECTIONS["actif_long"]})
        lines += [{"kind": "data", **r} for r in by_sec["actif_long"]]
    t_actif = total_of("actif_court", "actif_placement", "actif_long")
    lines.append({"kind": "total", "label": "TOTAL DE L'ACTIF", **t_actif})

    lines.append({"kind": "title", "label": "PASSIF"})
    lines.append({"kind": "header", "label": QC_SECTIONS["passif_court"]})
    lines += [{"kind": "data", **r} for r in by_sec["passif_court"]]
    if by_sec["passif_long"]:
        lines.append({"kind": "header", "label": QC_SECTIONS["passif_long"]})
        lines += [{"kind": "data", **r} for r in by_sec["passif_long"]]
    lines.append({"kind": "subtotal", "label": "TOTAL DU PASSIF", **total_of("passif_court", "passif_long")})
    lines.append({"kind": "header", "label": QC_SECTIONS["capitaux"]})
    lines += [{"kind": "data", **r} for r in by_sec["capitaux"]]
    lines.append({"kind": "data", "gl": "", "label": "Bénéfices non répartis", **ni})
    t_capitaux = total_of("capitaux")
    t_pc = {c: round(total_of("passif_court", "passif_long")[c] + t_capitaux[c] + ni[c], 2) for c in ("movement", "opening", "cumulative")}
    lines.append({"kind": "total", "label": "TOTAL PASSIF ET CAPITAUX", **t_pc})
    diff = {c: round(t_actif[c] - t_pc[c], 2) for c in ("movement", "opening", "cumulative")}
    lines.append({"kind": "diff", "label": "Diff", **diff})
    return {"year": int(year), "lines": lines, "balanced": abs(diff["cumulative"]) < 0.01,
            "cols": ["movement", "opening", "cumulative"]}

async def _qc_pnl(year):
    bal, accts = await _qc_report_balances(year)
    by_sec = {"revenus": [], "charges": [], "quote_part": [], "impots": []}
    for gl, a in accts.items():
        sec = a.get("section")
        if sec in by_sec:
            b = bal.get(gl, {"movement": 0, "opening": 0})
            # produits présentés positifs (crédit), charges positives (débit)
            sign = -1 if a.get("type") == "produit" else 1
            by_sec[sec].append({"gl": gl, "label": a.get("description", ""),
                "cur": round(sign * b["movement"], 2), "prev": round(sign * b["opening"], 2)})
    for k in by_sec:
        by_sec[k].sort(key=lambda r: r["gl"])
    def tot(sec):
        return {"cur": round(sum(r["cur"] for r in by_sec[sec]), 2), "prev": round(sum(r["prev"] for r in by_sec[sec]), 2)}
    lines = []
    lines.append({"kind": "header", "label": "REVENUS"})
    lines += [{"kind": "data", **r} for r in by_sec["revenus"]]
    t_rev = tot("revenus"); lines.append({"kind": "subtotal", "label": "TOTAL - REVENUS", **t_rev})
    lines.append({"kind": "header", "label": "CHARGES"})
    lines += [{"kind": "data", **r} for r in by_sec["charges"]]
    t_chg = tot("charges"); lines.append({"kind": "subtotal", "label": "TOTAL - CHARGES", **t_chg})
    baiia = {"cur": round(t_rev["cur"] - t_chg["cur"], 2), "prev": round(t_rev["prev"] - t_chg["prev"], 2)}
    lines.append({"kind": "total", "label": "BÉNÉFICE AVANT INTÉRÊTS, IMPÔT ET AMORTISSEMENT (BAIIA)", **baiia})
    t_qp = tot("quote_part")
    if by_sec["quote_part"]:
        lines += [{"kind": "data", **r} for r in by_sec["quote_part"]]
    avant_impot = {"cur": round(baiia["cur"] + t_qp["cur"], 2), "prev": round(baiia["prev"] + t_qp["prev"], 2)}
    lines.append({"kind": "subtotal", "label": "BÉNÉFICE AVANT IMPÔT", **avant_impot})
    lines.append({"kind": "header", "label": "IMPÔTS"})
    lines += [{"kind": "data", **r} for r in by_sec["impots"]]
    t_imp = tot("impots"); lines.append({"kind": "subtotal", "label": "TOTAL - IMPÔTS", **t_imp})
    net = {"cur": round(avant_impot["cur"] - t_imp["cur"], 2), "prev": round(avant_impot["prev"] - t_imp["prev"], 2)}
    lines.append({"kind": "total", "label": "BÉNÉFICE NET (PERTE NETTE)", **net})
    lines.append({"kind": "qp", "label": "Q-P DES RÉSULTATS - SERVICES HILO (65%)",
                  "cur": round(net["cur"] * 0.65, 2), "prev": round(net["prev"] * 0.65, 2)})
    lines.append({"kind": "qp", "label": "Q-P DES RÉSULTATS - 9379-5599 QUEBEC INC (35%)",
                  "cur": round(net["cur"] * 0.35, 2), "prev": round(net["prev"] * 0.35, 2)})
    return {"year": int(year), "lines": lines, "net": net, "cols": ["cur", "prev"]}

@api.get("/qc9434/bilan")
async def qc_bilan(year: int, user: dict = Depends(get_current_user)):
    return await _qc_bilan(year)

@api.get("/qc9434/pnl")
async def qc_pnl(year: int, user: dict = Depends(get_current_user)):
    return await _qc_pnl(year)

def _qc_report_xlsx(rep, title):
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = title[:30]
    navy = PatternFill("solid", fgColor="063044"); white = Font(color="FFFFFF", bold=True)
    ws.append(["9434-3977 QUÉBEC INC - COMMANDITÉ"]); ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"{title} — Exercice {rep['year']}"]); ws["A2"].font = Font(size=10, italic=True)
    ws.append([])
    is_bilan = "cumulative" in rep.get("cols", [])
    hdr = ["Compte", "Libellé"] + (["Exercice", "Antérieur", "Cumulatif"] if is_bilan else [f"{rep['year']}", f"{rep['year']-1}"])
    ws.append(hdr); hr = ws.max_row
    for c in range(1, len(hdr) + 1):
        cell = ws.cell(hr, c); cell.fill = navy; cell.font = white
    for ln in rep["lines"]:
        if is_bilan:
            vals = [ln.get("gl", ""), ln["label"], ln.get("movement"), ln.get("opening"), ln.get("cumulative")]
        else:
            vals = [ln.get("gl", ""), ln["label"], ln.get("cur"), ln.get("prev")]
        if ln["kind"] in ("title", "header"):
            vals = [ln["label"]] + [None] * (len(hdr) - 1)
        ws.append(vals)
        r = ws.max_row
        if ln["kind"] in ("total", "subtotal", "title"):
            for c in range(1, len(hdr) + 1):
                ws.cell(r, c).font = Font(bold=True)
        if ln["kind"] == "header":
            ws.cell(r, 1).font = Font(bold=True)
    for col, w in zip("ABCDE", [14, 44, 16, 16, 16]):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=5, min_col=3, max_col=len(hdr)):
        for cell in row:
            cell.number_format = '#,##0.00;(#,##0.00)'; cell.alignment = Alignment(horizontal="right")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.getvalue()

@api.get("/qc9434/bilan/excel")
async def qc_bilan_excel(year: int, user: dict = Depends(get_current_user)):
    rep = await _qc_bilan(year)
    return StreamingResponse(io.BytesIO(_qc_report_xlsx(rep, "Bilan détaillé")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=bilan_9434_{year}.xlsx"})

@api.get("/qc9434/pnl/excel")
async def qc_pnl_excel(year: int, user: dict = Depends(get_current_user)):
    rep = await _qc_pnl(year)
    return StreamingResponse(io.BytesIO(_qc_report_xlsx(rep, "État des résultats")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=resultats_9434_{year}.xlsx"})

# ---- Journal général PDF -----------------------------------------------
@api.get("/qc9434/journal/pdf")
async def qc_journal_pdf(year: int, user: dict = Depends(get_current_user)):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    docs = await db.qc9434_entries.find({"year": int(year), "company_id": await _company_id("qc9434")}).sort([("date", 1), ("created_at", 1)]).to_list(50000)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=7.5, leading=9)
    NAVY = colors.HexColor("#0F172A"); GREY = colors.HexColor("#E9EDEF")
    rows = [["Date", "Réf.", "Compte", "Libellé / Description", "Tiers", "Débit", "Crédit"]]
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
             ("ALIGN", (5, 0), (6, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
             ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY)]
    td = tc = 0.0
    r = 1
    for e in docs:
        first = True
        for l in e.get("lines", []):
            dr = float(l.get("debit") or 0); cr = float(l.get("credit") or 0)
            td += dr; tc += cr
            rows.append([e.get("date", "") if first else "", (e.get("reference", "") if first else ""),
                         l.get("account", ""), Paragraph(((e.get("description", "") + " · ") if first and e.get("description") else "") + (l.get("account_name") or ""), small),
                         l.get("tiers", ""), f"{dr:,.2f}" if dr else "", f"{cr:,.2f}" if cr else ""])
            r += 1
            first = False
        style.append(("LINEBELOW", (0, r - 1), (-1, r - 1), 0.3, colors.HexColor("#CBD5E1")))
    rows.append(["", "", "", "TOTAUX", "", f"{td:,.2f}", f"{tc:,.2f}"])
    style += [("FONTNAME", (0, len(rows) - 1), (-1, len(rows) - 1), "Helvetica-Bold"),
              ("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), GREY)]
    tbl = Table(rows, colWidths=[20 * mm, 18 * mm, 22 * mm, 120 * mm, 45 * mm, 25 * mm, 25 * mm], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=8 * mm)
    hS = ParagraphStyle("h", parent=styles["Normal"], fontSize=12, fontName="Helvetica-Bold", textColor=NAVY)
    doc.build([Paragraph("9434-3977 QUÉBEC INC - COMMANDITÉ", hS),
               Paragraph(f"Journal général — Exercice {year}", ParagraphStyle("s2", parent=styles["Normal"], fontSize=9)),
               Spacer(1, 4 * mm), tbl])
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=journal_9434_{year}.pdf"})

# ---- Écritures modèles (récurrentes) -----------------------------------
class QcTemplate(BaseModel):
    name: str
    description: str = ""
    lines: List[QcLine]

@api.get("/qc9434/templates")
async def qc_templates(user: dict = Depends(get_current_user)):
    docs = await db.qc9434_templates.find().sort("name", 1).to_list(500)
    return [{"id": str(d["_id"]), "name": d.get("name", ""), "description": d.get("description", ""),
             "lines": d.get("lines", [])} for d in docs]

@api.post("/qc9434/templates")
async def qc_create_template(payload: QcTemplate, user: dict = Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nom du modèle requis.")
    res = await db.qc9434_templates.insert_one({"name": payload.name.strip(), "description": payload.description.strip(),
        "lines": [l.model_dump() for l in payload.lines], "company_id": await _company_id("qc9434")})
    await log_action(user, "Créer", "9434 — Modèle d'écriture", payload.name)
    return {"success": True, "id": str(res.inserted_id)}

@api.delete("/qc9434/templates/{tid}")
async def qc_delete_template(tid: str, user: dict = Depends(get_current_user)):
    await db.qc9434_templates.delete_one({"_id": _oid(tid)})
    await log_action(user, "Supprimer", "9434 — Modèle d'écriture", tid)
    return {"success": True}

# ---- PDF présentation Bilan / Résultats --------------------------------
def _qc_report_pdf(rep, title, year):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); TEAL = colors.HexColor("#22C55E")
    styles = getSampleStyleSheet()
    is_bilan = "cumulative" in rep.get("cols", [])
    cols = ([("movement", "Exercice"), ("opening", "Antérieur"), ("cumulative", "Cumulatif")]
            if is_bilan else [("cur", str(year)), ("prev", str(year - 1))])
    header = ["", ""] + [c[1] for c in cols]
    rows = [header]
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONTSIZE", (0, 0), (-1, -1), 8), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
          ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 5)]
    r = 1
    for ln in rep["lines"]:
        is_text = ln["kind"] in ("title", "header")
        vals = [ln.get("gl", ""), ln["label"]]
        for k, _ in cols:
            v = ln.get(k)
            vals.append("" if (is_text or v is None) else f"{v:,.2f}")
        rows.append(vals)
        if ln["kind"] == "title":
            st += [("BACKGROUND", (0, r), (-1, r), NAVY), ("TEXTCOLOR", (0, r), (-1, r), colors.white), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold")]
        elif ln["kind"] == "header":
            st += [("TEXTCOLOR", (0, r), (-1, r), TEAL), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold")]
        elif ln["kind"] in ("total",):
            st += [("LINEABOVE", (0, r), (-1, r), 1, NAVY), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#E9EDEF"))]
        elif ln["kind"] in ("subtotal",):
            st += [("LINEABOVE", (0, r), (-1, r), 0.5, colors.grey), ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold")]
        elif ln["kind"] == "qp":
            st += [("TEXTCOLOR", (0, r), (-1, r), colors.grey), ("FONTNAME", (0, r), (-1, r), "Helvetica-Oblique")]
        r += 1
    cw = ([18 * mm, 82 * mm, 30 * mm, 30 * mm, 30 * mm] if is_bilan else [18 * mm, 96 * mm, 38 * mm, 38 * mm])
    tbl = Table(rows, colWidths=cw, repeatRows=1); tbl.setStyle(TableStyle(st))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=10 * mm)
    hS = ParagraphStyle("h", parent=styles["Normal"], fontSize=13, fontName="Helvetica-Bold", textColor=NAVY)
    doc.build([_pdf_logo(38), Spacer(1, 3 * mm), Paragraph("9434-3977 QUÉBEC INC - COMMANDITÉ", hS),
               Paragraph(f"{title} — Exercice {year}", ParagraphStyle("s", parent=styles["Normal"], fontSize=9)),
               Spacer(1, 4 * mm), tbl])
    buf.seek(0)
    return buf.getvalue()

@api.get("/qc9434/bilan/pdf")
async def qc_bilan_pdf(year: int, user: dict = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(_qc_report_pdf(await _qc_bilan(year), "BILAN DÉTAILLÉ", year)),
        media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=bilan_9434_{year}.pdf"})

@api.get("/qc9434/pnl/pdf")
async def qc_pnl_pdf(year: int, user: dict = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(_qc_report_pdf(await _qc_pnl(year), "ÉTAT DES RÉSULTATS", year)),
        media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=resultats_9434_{year}.pdf"})

# ---- Stockage objet (factures fournisseurs) ----------------------------
_QC_STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
_qc_storage_key = None

def _qc_init_storage():
    global _qc_storage_key
    if _qc_storage_key:
        return _qc_storage_key
    resp = requests.post(f"{_QC_STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    _qc_storage_key = resp.json()["storage_key"]
    return _qc_storage_key

def _qc_put_object(path, data, content_type):
    key = _qc_init_storage()
    resp = requests.put(f"{_QC_STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def _qc_get_object(path):
    key = _qc_init_storage()
    resp = requests.get(f"{_QC_STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---- Factures clients (auxiliaire recevable) ---------------------------
def _round2(x):
    return round(float(x or 0), 2)

async def _qc_next_invoice_number(year):
    top = await db.qc9434_invoices.find({"year": int(year)}).sort("num_seq", -1).limit(1).to_list(1)
    n = (top[0].get("num_seq") or 0) + 1 if top else 1
    return n, f"{year}-{n:03d}"

def _qc_invoice_out(d):
    total = d.get("total", 0); paid = d.get("paid_amount", 0); credited = d.get("credited_amount", 0)
    items = d.get("items") or [{"description": d.get("description", ""), "account": d.get("sales_account", QC_DEF["sales"]), "amount": d.get("amount", 0)}]
    typ = d.get("type", "invoice")
    if typ == "credit_note":
        applied = d.get("applied_amount", 0)
        balance = round(-(total - applied), 2)
        status = d.get("status", "credit")
    else:
        balance = round(total - paid - credited, 2)
        status = d.get("status", "open")
    return {"id": str(d["_id"]), "year": d.get("year"), "number": d.get("number"), "date": d.get("date"),
            "type": typ, "ar_account": d.get("ar_account", QC_DEF["ar"]), "client_id": d.get("client_id"),
            "linked_invoice": d.get("linked_invoice"), "linked_number": d.get("linked_number"),
            "due_date": d.get("due_date"), "client_name": d.get("client_name", ""), "client_att": d.get("client_att", ""),
            "client_address": d.get("client_address", ""), "client_email": d.get("client_email", ""), "description": d.get("description", ""),
            "amount": d.get("amount", 0), "tps": d.get("tps", 0), "tvq": d.get("tvq", 0), "total": total, "items": items,
            "paid_amount": round(paid, 2), "credited_amount": round(credited, 2), "balance": balance,
            "status": status, "paid_at": d.get("paid_at"), "entry_id": str(d.get("entry_id")) if d.get("entry_id") else None}

class QcInvoiceLine(BaseModel):
    description: str = ""
    account: str = QC_DEF["sales"]
    amount: float = 0

class QcInvoiceIn(BaseModel):
    date: str
    due_date: str = ""
    client_name: str
    client_att: str = ""
    client_address: str = ""
    client_email: str = ""
    client_id: Optional[str] = None
    ar_account: Optional[str] = None
    description: str = ""
    amount: float = 0
    sales_account: str = QC_DEF["sales"]
    items: Optional[List[QcInvoiceLine]] = None

async def _qc_resolve_client(payload):
    """Retourne (client_name, att, address, email, ar_account, client_id) selon la fiche client ou la saisie libre."""
    if getattr(payload, "client_id", None):
        c = await db.qc9434_clients.find_one({"_id": _oid(payload.client_id)})
        if c:
            return (c.get("name", ""), c.get("att", ""), c.get("address", ""), c.get("email", ""),
                    c.get("ar_account") or QC_DEF["ar"], str(c["_id"]))
    ar = getattr(payload, "ar_account", None) or QC_DEF["ar"]
    return (payload.client_name, payload.client_att, payload.client_address, payload.client_email, ar, None)

async def _qc_build_invoice_doc(payload, year, num_seq, number, entry_id, cname, catt, caddr, cemail, ar):
    amount = _round2(sum(i["amount"] for i in payload["items"]))
    return {"year": int(year), "num_seq": num_seq, "number": number, "type": "invoice", "date": payload["date"],
            "due_date": payload.get("due_date", ""), "client_name": cname, "client_att": catt, "client_address": caddr,
            "client_email": cemail, "client_id": payload.get("client_id"), "ar_account": ar, "description": payload.get("description", ""),
            "amount": amount, "tps": payload["tps"], "tvq": payload["tvq"], "total": payload["total"],
            "sales_account": payload["items"][0]["account"], "items": payload["items"], "status": "open",
            "paid_amount": 0.0, "credited_amount": 0.0, "entry_id": entry_id,
            "created_at": datetime.now(timezone.utc).isoformat()}

@api.get("/qc9434/invoices")
async def qc_invoices(year: int, user: dict = Depends(get_current_user)):
    docs = await db.qc9434_invoices.find({"year": int(year), "company_id": await _company_id("qc9434")}).sort("num_seq", 1).to_list(2000)
    return [_qc_invoice_out(d) for d in docs]

@api.post("/qc9434/invoices")
async def qc_create_invoice(payload: QcInvoiceIn, year: int, user: dict = Depends(get_current_user)):
    y = await _qc_year_doc(year)
    if not y:
        raise HTTPException(status_code=404, detail="Année introuvable — créez d'abord l'exercice.")
    if y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {year} est verrouillé.")
    raw_items = payload.items if payload.items else [QcInvoiceLine(description=payload.description, account=payload.sales_account or QC_DEF["sales"], amount=payload.amount)]
    items = []
    for it in raw_items:
        a = _round2(it.amount)
        if a <= 0:
            continue
        items.append({"description": (it.description or "").strip(), "account": it.account or QC_DEF["sales"], "amount": a})
    if not items:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne avec un montant supérieur à zéro.")
    amount = _round2(sum(i["amount"] for i in items))
    tps = _round2(amount * QC_TPS); tvq = _round2(amount * QC_TVQ); total = _round2(amount + tps + tvq)
    cname, catt, caddr, cemail, ar, cid = await _qc_resolve_client(payload)
    num_seq, number = await _qc_next_invoice_number(year)
    lines = [{"account": ar, "account_name": await _qc_acc_name(ar), "tiers": cname, "debit": total, "credit": 0.0}]
    for it in items:
        lines.append({"account": it["account"], "account_name": await _qc_acc_name(it["account"]), "tiers": cname,
                      "debit": 0.0, "credit": it["amount"], "memo": it["description"]})
    lines += [
        {"account": QC_DEF["tps_pay"], "account_name": await _qc_acc_name(QC_DEF["tps_pay"]), "tiers": "", "debit": 0.0, "credit": tps},
        {"account": QC_DEF["tvq_pay"], "account_name": await _qc_acc_name(QC_DEF["tvq_pay"]), "tiers": "", "debit": 0.0, "credit": tvq},
    ]
    entry = await _qc_post_entry(year, payload.date, f"Facturation client #{number} — {cname}", lines,
        reference=number, source="invoice", actor=user)
    doc = {"year": int(year), "num_seq": num_seq, "number": number, "type": "invoice", "date": payload.date, "due_date": payload.due_date,
           "client_name": cname, "client_att": catt, "client_address": caddr, "client_email": cemail, "client_id": cid, "ar_account": ar,
           "description": payload.description, "amount": amount, "tps": tps, "tvq": tvq, "total": total,
           "sales_account": items[0]["account"], "items": items, "status": "open", "paid_amount": 0.0, "credited_amount": 0.0, "entry_id": entry["_id"],
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"),
           "company_id": await _company_id("qc9434")}
    res = await db.qc9434_invoices.insert_one(doc)
    await db.qc9434_entries.update_one({"_id": entry["_id"]}, {"$set": {"source_id": str(res.inserted_id)}})
    await log_action(user, "Créer", "9434 — Facture client", f"{number} · {cname} ({total:,.2f} $)")
    doc["_id"] = res.inserted_id
    return _qc_invoice_out(doc)

@api.post("/qc9434/invoices/{iid}/receive")
async def qc_receive_invoice(iid: str, date: str = "", amount: float = 0, user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if inv.get("type") == "credit_note":
        raise HTTPException(status_code=400, detail="Un encaissement ne s'applique pas à une note de crédit.")
    if inv.get("status") in ("paid", "reversed"):
        raise HTTPException(status_code=400, detail="Facture déjà encaissée ou extournée.")
    y = await _qc_year_doc(inv["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {inv['year']} est verrouillé.")
    ar = inv.get("ar_account") or QC_DEF["ar"]
    balance = round(inv["total"] - inv.get("paid_amount", 0) - inv.get("credited_amount", 0), 2)
    amt = round(float(amount), 2) if amount and float(amount) > 0 else balance
    if amt <= 0 or amt > balance + 0.005:
        raise HTTPException(status_code=400, detail=f"Montant invalide (solde restant : {balance:,.2f} $).")
    lines = [
        {"account": QC_DEF["cash"], "account_name": await _qc_acc_name(QC_DEF["cash"]), "tiers": inv.get("client_name", ""), "debit": amt, "credit": 0.0},
        {"account": ar, "account_name": await _qc_acc_name(ar), "tiers": inv.get("client_name", ""), "debit": 0.0, "credit": amt},
    ]
    await _qc_post_entry(inv["year"], date or datetime.now(timezone.utc).date().isoformat(),
        f"Encaissement facture #{inv['number']} — {inv.get('client_name','')}", lines, reference=inv["number"], source="receipt", source_id=iid, actor=user)
    new_paid = round(inv.get("paid_amount", 0) + amt, 2)
    paid_full = new_paid + inv.get("credited_amount", 0) >= round(inv["total"], 2) - 0.005
    await db.qc9434_invoices.update_one({"_id": _oid(iid)}, {"$set": {"paid_amount": new_paid,
        "status": "paid" if paid_full else "partial", "paid_at": datetime.now(timezone.utc).isoformat() if paid_full else inv.get("paid_at")}})
    await log_action(user, "Encaisser", "9434 — Facture client", f"{inv['number']} ({amt:,.2f} $)")
    return {"success": True, "paid_amount": new_paid, "balance": round(inv["total"] - new_paid - inv.get("credited_amount", 0), 2)}

# ---- Carnet de clients (compte AR dédié) ------------------------------
def _qc_client_out(c):
    return {"id": str(c["_id"]), "name": c.get("name", ""), "att": c.get("att", ""), "address": c.get("address", ""),
            "email": c.get("email", ""), "ar_account": c.get("ar_account") or QC_DEF["ar"], "active": c.get("active", True)}

@api.get("/qc9434/clients")
async def qc_clients(user: dict = Depends(get_current_user)):
    docs = await db.qc9434_clients.find({"company_id": await _company_id("qc9434")}).sort("name", 1).to_list(1000)
    return [_qc_client_out(c) for c in docs]

@api.post("/qc9434/clients")
async def qc_create_client(payload: dict, user: dict = Depends(require_admin)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom du client est requis.")
    doc = {"name": name, "att": (payload.get("att") or "").strip(), "address": (payload.get("address") or "").strip(),
           "email": (payload.get("email") or "").strip(), "ar_account": payload.get("ar_account") or QC_DEF["ar"],
           "active": True, "created_at": datetime.now(timezone.utc).isoformat(),
           "company_id": await _company_id("qc9434")}
    res = await db.qc9434_clients.insert_one(doc); doc["_id"] = res.inserted_id
    await log_action(user, "Créer", "9434 — Client", f"{name} → compte {doc['ar_account']}")
    return _qc_client_out(doc)

@api.put("/qc9434/clients/{cid}")
async def qc_update_client(cid: str, payload: dict, user: dict = Depends(require_admin)):
    upd = {k: (payload.get(k) or "").strip() for k in ("name", "att", "address", "email") if k in payload}
    if "ar_account" in payload:
        upd["ar_account"] = payload.get("ar_account") or QC_DEF["ar"]
    if "active" in payload:
        upd["active"] = bool(payload.get("active"))
    await db.qc9434_clients.update_one({"_id": _oid(cid)}, {"$set": upd})
    c = await db.qc9434_clients.find_one({"_id": _oid(cid)})
    return _qc_client_out(c)

@api.delete("/qc9434/clients/{cid}")
async def qc_delete_client(cid: str, user: dict = Depends(require_admin)):
    await db.qc9434_clients.delete_one({"_id": _oid(cid)})
    return {"success": True}

# ---- Relevé de compte client ------------------------------------------
async def _qc_client_statement(cid: str, year: Optional[int]):
    c = await db.qc9434_clients.find_one({"_id": _oid(cid)})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    q = {"$or": [{"client_id": cid}, {"client_name": c.get("name", "")}], "company_id": await _company_id("qc9434")}
    if year:
        q = {"$and": [q, {"year": int(year)}]}
    docs = await db.qc9434_invoices.find(q).sort([("date", 1), ("num_seq", 1)]).to_list(5000)
    rows, total_billed, total_paid, total_credited, total_balance = [], 0.0, 0.0, 0.0, 0.0
    for d in docs:
        o = _qc_invoice_out(d)
        is_cn = o["type"] == "credit_note"
        rows.append({"number": o["number"], "date": o["date"], "due_date": o.get("due_date", ""),
                     "type": "Note de crédit" if is_cn else "Facture", "is_credit_note": is_cn,
                     "status": o["status"], "total": o["total"], "paid_amount": o["paid_amount"],
                     "credited_amount": o["credited_amount"], "balance": o["balance"],
                     "linked_number": o.get("linked_number")})
        if is_cn:
            total_credited += o["total"]
        else:
            total_billed += o["total"]; total_paid += o["paid_amount"]
        if o["status"] != "reversed":
            total_balance += o["balance"]
    return {"client": _qc_client_out(c), "year": int(year) if year else None, "rows": rows,
            "totals": {"billed": round(total_billed, 2), "paid": round(total_paid, 2),
                       "credited": round(total_credited, 2), "balance": round(total_balance, 2)}}

@api.get("/qc9434/clients/{cid}/statement")
async def qc_client_statement(cid: str, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    return await _qc_client_statement(cid, year)

@api.get("/qc9434/clients/{cid}/statement/pdf")
async def qc_client_statement_pdf(cid: str, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    data = await _qc_client_statement(cid, year)
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); VIOLET = colors.HexColor("#7C3AED"); styles = getSampleStyleSheet()
    H = ParagraphStyle("h", parent=styles["Normal"], fontSize=15, fontName="Helvetica-Bold", textColor=NAVY)
    N = ParagraphStyle("n", parent=styles["Normal"], fontSize=9, leading=12)
    B = ParagraphStyle("b", parent=styles["Normal"], fontSize=9, leading=12, fontName="Helvetica-Bold")
    cl = data["client"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    el = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph("9434-3977 QUÉBEC INC.", H), Spacer(1, 1 * mm),
          Paragraph("RELEVÉ DE COMPTE" + (f" — Exercice {data['year']}" if data["year"] else ""), B), Spacer(1, 4 * mm)]
    who = cl["name"]
    if cl.get("att"): who += f"<br/>Att : {cl['att']}"
    if cl.get("address"): who += "<br/>" + cl["address"].replace("\n", "<br/>")
    if cl.get("email"): who += f"<br/>{cl['email']}"
    el += [Paragraph("Client", B), Paragraph(who, N),
           Paragraph(f"Compte de comptes-clients : {cl.get('ar_account','')}", N), Spacer(1, 5 * mm)]
    header = ["N°", "Date", "Type", "Total", "Réglé", "Crédité", "Solde"]
    body = [header]
    for r in data["rows"]:
        num = r["number"] + (f" ↩ {r['linked_number']}" if r.get("linked_number") else "")
        stat = " (Extournée)" if r["status"] == "reversed" else ""
        body.append([num, r["date"], r["type"] + stat, f"{r['total']:,.2f} $",
                     f"{r['paid_amount']:,.2f} $", f"{r['credited_amount']:,.2f} $", f"{r['balance']:,.2f} $"])
    t = data["totals"]
    body.append(["", "", "TOTAUX", f"{t['billed']:,.2f} $", f"{t['paid']:,.2f} $", f"{t['credited']:,.2f} $", f"{t['balance']:,.2f} $"])
    tbl = Table(body, colWidths=[26 * mm, 20 * mm, 34 * mm, 24 * mm, 22 * mm, 22 * mm, 24 * mm])
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E9EDEF")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F6F8F9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    el += [tbl, Spacer(1, 6 * mm)]
    el += [Paragraph(f"<b>Solde dû : {t['balance']:,.2f} $</b>", ParagraphStyle("bal", parent=B, fontSize=11, textColor=NAVY))]
    doc.build(el); buf.seek(0)
    fname = f"releve_{cl['name'].replace(' ', '_')}{('_' + str(data['year'])) if data['year'] else ''}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={fname}"})

# ---- Purge des données de démonstration (TEST_) -----------------------
@api.post("/qc9434/purge-test-data")
async def qc_purge_test_data(user: dict = Depends(require_admin)):
    rx = {"$regex": "^TEST_", "$options": "i"}
    invs = await db.qc9434_invoices.find({"client_name": rx, "company_id": await _company_id("qc9434")}).to_list(5000)
    bills = await db.qc9434_bills.find({"supplier": rx, "company_id": await _company_id("qc9434")}).to_list(5000)
    src_ids = [str(d["_id"]) for d in invs] + [str(d["_id"]) for d in bills]
    entry_oids = [d["entry_id"] for d in (invs + bills) if d.get("entry_id")]
    ent1 = 0; ent2 = 0
    if src_ids:
        r = await db.qc9434_entries.delete_many({"source_id": {"$in": src_ids}}); ent1 = r.deleted_count
    if entry_oids:
        r = await db.qc9434_entries.delete_many({"_id": {"$in": entry_oids}}); ent2 = r.deleted_count
    ri = await db.qc9434_invoices.delete_many({"client_name": rx})
    rb = await db.qc9434_bills.delete_many({"supplier": rx})
    rc = await db.qc9434_clients.delete_many({"name": rx})
    counts = {"clients": rc.deleted_count, "invoices": ri.deleted_count, "bills": rb.deleted_count, "entries": ent1 + ent2}
    await log_action(user, "Purger", "9434 — Données de test",
                     f"{counts['clients']} client(s), {counts['invoices']} facture(s), {counts['bills']} fournisseur(s), {counts['entries']} écriture(s)")
    return {"success": True, "deleted": counts,
            "message": f"Purgé : {counts['clients']} client(s), {counts['invoices']} facture(s) client, {counts['bills']} facture(s) fournisseur, {counts['entries']} écriture(s)."}


# ---- Notes de crédit --------------------------------------------------
class QcCreditNoteIn(QcInvoiceIn):
    invoice_id: Optional[str] = None

@api.post("/qc9434/credit-notes")
async def qc_create_credit_note(payload: QcCreditNoteIn, year: int, user: dict = Depends(get_current_user)):
    y = await _qc_year_doc(year)
    if not y:
        raise HTTPException(status_code=404, detail="Année introuvable.")
    if y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {year} est verrouillé.")
    linked = None
    if payload.invoice_id:
        linked = await db.qc9434_invoices.find_one({"_id": _oid(payload.invoice_id)})
        if not linked or linked.get("type") == "credit_note":
            raise HTTPException(status_code=404, detail="Facture liée introuvable.")
    raw_items = payload.items if payload.items else [QcInvoiceLine(description=payload.description, account=payload.sales_account or QC_DEF["sales"], amount=payload.amount)]
    items = [{"description": (it.description or "").strip(), "account": it.account or QC_DEF["sales"], "amount": _round2(it.amount)} for it in raw_items if _round2(it.amount) > 0]
    if not items:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne avec un montant supérieur à zéro.")
    amount = _round2(sum(i["amount"] for i in items))
    tps = _round2(amount * QC_TPS); tvq = _round2(amount * QC_TVQ); total = _round2(amount + tps + tvq)
    if linked:
        cname, catt, caddr, cemail = linked.get("client_name", ""), linked.get("client_att", ""), linked.get("client_address", ""), linked.get("client_email", "")
        ar, cid = linked.get("ar_account") or QC_DEF["ar"], linked.get("client_id")
        rem = round(linked["total"] - linked.get("paid_amount", 0) - linked.get("credited_amount", 0), 2)
        if total > rem + 0.005:
            raise HTTPException(status_code=400, detail=f"La note de crédit ({total:,.2f} $) dépasse le solde de la facture ({rem:,.2f} $).")
    else:
        cname, catt, caddr, cemail, ar, cid = await _qc_resolve_client(payload)
    top = await db.qc9434_invoices.find({"year": int(year), "type": "credit_note"}).sort("num_seq", -1).limit(1).to_list(1)
    nseq = (top[0].get("num_seq") or 0) + 1 if top else 1
    number = f"NC-{year}-{nseq:03d}"
    # écriture inverse : Dr Ventes/taxes, Cr Clients
    lines = []
    for it in items:
        lines.append({"account": it["account"], "account_name": await _qc_acc_name(it["account"]), "tiers": cname, "debit": it["amount"], "credit": 0.0, "memo": it["description"]})
    lines += [
        {"account": QC_DEF["tps_pay"], "account_name": await _qc_acc_name(QC_DEF["tps_pay"]), "tiers": "", "debit": tps, "credit": 0.0},
        {"account": QC_DEF["tvq_pay"], "account_name": await _qc_acc_name(QC_DEF["tvq_pay"]), "tiers": "", "debit": tvq, "credit": 0.0},
        {"account": ar, "account_name": await _qc_acc_name(ar), "tiers": cname, "debit": 0.0, "credit": total},
    ]
    entry = await _qc_post_entry(year, payload.date, f"Note de crédit {number} — {cname}", lines, reference=number, source="credit_note", actor=user)
    doc = {"year": int(year), "num_seq": nseq, "number": number, "type": "credit_note", "date": payload.date, "due_date": "",
           "client_name": cname, "client_att": catt, "client_address": caddr, "client_email": cemail, "client_id": cid, "ar_account": ar,
           "description": payload.description, "amount": amount, "tps": tps, "tvq": tvq, "total": total,
           "sales_account": items[0]["account"], "items": items, "status": "applied" if linked else "credit",
           "applied_amount": total if linked else 0.0, "linked_invoice": str(linked["_id"]) if linked else None,
           "linked_number": linked.get("number") if linked else None, "entry_id": entry["_id"],
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"),
           "company_id": await _company_id("qc9434")}
    res = await db.qc9434_invoices.insert_one(doc)
    await db.qc9434_entries.update_one({"_id": entry["_id"]}, {"$set": {"source_id": str(res.inserted_id)}})
    if linked:
        newc = round(linked.get("credited_amount", 0) + total, 2)
        full = round(linked.get("paid_amount", 0) + newc, 2) >= round(linked["total"], 2) - 0.005
        await db.qc9434_invoices.update_one({"_id": linked["_id"]}, {"$set": {"credited_amount": newc, "status": "paid" if full else "partial"}})
    await log_action(user, "Créer", "9434 — Note de crédit", f"{number} · {cname} ({total:,.2f} $)")
    doc["_id"] = res.inserted_id
    return _qc_invoice_out(doc)

@api.post("/qc9434/invoices/{iid}/reverse")
async def qc_reverse_invoice(iid: str, date: str = "", user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if inv.get("type") == "credit_note":
        raise HTTPException(status_code=400, detail="Une note de crédit ne peut être extournée.")
    if inv.get("status") == "reversed":
        raise HTTPException(status_code=400, detail="Facture déjà extournée.")
    if inv.get("paid_amount", 0) > 0:
        raise HTTPException(status_code=400, detail="Impossible d'extourner : la facture a des encaissements. Créez une note de crédit.")
    y = await _qc_year_doc(inv["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {inv['year']} est verrouillé — extourne impossible.")
    ar = inv.get("ar_account") or QC_DEF["ar"]
    items = inv.get("items") or [{"account": inv.get("sales_account", QC_DEF["sales"]), "amount": inv.get("amount", 0), "description": inv.get("description", "")}]
    lines = []
    for it in items:
        lines.append({"account": it["account"], "account_name": await _qc_acc_name(it["account"]), "tiers": inv.get("client_name", ""), "debit": it["amount"], "credit": 0.0, "memo": "Extourne " + (it.get("description") or "")})
    lines += [
        {"account": QC_DEF["tps_pay"], "account_name": await _qc_acc_name(QC_DEF["tps_pay"]), "tiers": "", "debit": inv.get("tps", 0), "credit": 0.0},
        {"account": QC_DEF["tvq_pay"], "account_name": await _qc_acc_name(QC_DEF["tvq_pay"]), "tiers": "", "debit": inv.get("tvq", 0), "credit": 0.0},
        {"account": ar, "account_name": await _qc_acc_name(ar), "tiers": inv.get("client_name", ""), "debit": 0.0, "credit": inv.get("total", 0)},
    ]
    await _qc_post_entry(inv["year"], date or datetime.now(timezone.utc).date().isoformat(),
        f"Extourne facture #{inv['number']} — {inv.get('client_name','')}", lines, reference=inv["number"], source="reversal", source_id=iid, actor=user)
    await db.qc9434_invoices.update_one({"_id": _oid(iid)}, {"$set": {"status": "reversed", "credited_amount": round(inv.get("total", 0), 2), "reversed_at": datetime.now(timezone.utc).isoformat()}})
    await log_action(user, "Extourner", "9434 — Facture client", f"{inv['number']} ({inv.get('total',0):,.2f} $)")
    return {"success": True, "message": f"Facture {inv['number']} extournée."}

@api.put("/qc9434/invoices/{iid}")
async def qc_edit_invoice(iid: str, payload: QcInvoiceIn, user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if inv.get("type") == "credit_note":
        raise HTTPException(status_code=400, detail="Une note de crédit ne se modifie pas.")
    if inv.get("status") == "reversed":
        raise HTTPException(status_code=400, detail="Facture extournée — modification impossible.")
    if inv.get("paid_amount", 0) > 0 or inv.get("credited_amount", 0) > 0:
        raise HTTPException(status_code=400, detail="Modification impossible : la facture a un encaissement ou une note de crédit.")
    y = await _qc_year_doc(inv["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {inv['year']} est verrouillé — modification impossible.")
    raw_items = payload.items if payload.items else [QcInvoiceLine(description=payload.description, account=payload.sales_account or QC_DEF["sales"], amount=payload.amount)]
    items = [{"description": (it.description or "").strip(), "account": it.account or QC_DEF["sales"], "amount": _round2(it.amount)} for it in raw_items if _round2(it.amount) > 0]
    if not items:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne avec un montant supérieur à zéro.")
    amount = _round2(sum(i["amount"] for i in items))
    tps = _round2(amount * QC_TPS); tvq = _round2(amount * QC_TVQ); total = _round2(amount + tps + tvq)
    cname, catt, caddr, cemail, ar, cid = await _qc_resolve_client(payload)
    if inv.get("entry_id"):
        await db.qc9434_entries.delete_one({"_id": inv["entry_id"]})
    lines = [{"account": ar, "account_name": await _qc_acc_name(ar), "tiers": cname, "debit": total, "credit": 0.0}]
    for it in items:
        lines.append({"account": it["account"], "account_name": await _qc_acc_name(it["account"]), "tiers": cname, "debit": 0.0, "credit": it["amount"], "memo": it["description"]})
    lines += [
        {"account": QC_DEF["tps_pay"], "account_name": await _qc_acc_name(QC_DEF["tps_pay"]), "tiers": "", "debit": 0.0, "credit": tps},
        {"account": QC_DEF["tvq_pay"], "account_name": await _qc_acc_name(QC_DEF["tvq_pay"]), "tiers": "", "debit": 0.0, "credit": tvq},
    ]
    entry = await _qc_post_entry(inv["year"], payload.date, f"Facturation client #{inv['number']} — {cname}", lines, reference=inv["number"], source="invoice", source_id=iid, actor=user)
    await db.qc9434_invoices.update_one({"_id": _oid(iid)}, {"$set": {
        "date": payload.date, "due_date": payload.due_date, "client_name": cname, "client_att": catt, "client_address": caddr,
        "client_email": cemail, "client_id": cid, "ar_account": ar, "description": payload.description, "amount": amount,
        "tps": tps, "tvq": tvq, "total": total, "sales_account": items[0]["account"], "items": items, "entry_id": entry["_id"]}})
    await log_action(user, "Modifier", "9434 — Facture client", f"{inv['number']} ({total:,.2f} $)")
    doc = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    return _qc_invoice_out(doc)

@api.post("/qc9434/invoices/{iid}/email")
async def qc_email_invoice(iid: str, user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    email = (inv.get("client_email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Aucun courriel client sur cette facture.")
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré.")
    pdf = await qc_invoice_pdf(iid, user)
    pdf_bytes = b"".join([chunk async for chunk in pdf.body_iterator]) if hasattr(pdf, "body_iterator") else pdf.body
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#1e293b;font-size:14px\"><p>Bonjour,</p>"
            f"<p>Veuillez trouver ci-joint la facture <strong>#{inv['number']}</strong> de 9434-3977 Québec Inc. "
            f"au montant de <strong>{inv['total']:,.2f} $</strong>.</p>"
            f"<p style=\"color:#64748b;font-size:12px;margin-top:24px\">9434-3977 Québec Inc.</p></div>")
    try:
        await asyncio.to_thread(resend.Emails.send, {"from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
            "to": [email], "subject": f"Facture #{inv['number']} — 9434-3977 Québec Inc.",
            "html": html, "attachments": [{"filename": f"facture_{inv['number']}.pdf", "content": list(pdf_bytes)}]})
        await db.qc9434_invoices.update_one({"_id": _oid(iid)}, {"$set": {"emailed_at": datetime.now(timezone.utc).isoformat()}})
        await log_action(user, "Envoyer", "9434 — Facture client", f"{inv['number']} → {email}")
        return {"success": True, "message": f"Facture envoyée à {email}"}
    except Exception as e:
        logger.error(f"Envoi facture échec : {e}")
        raise HTTPException(status_code=400, detail=f"Échec d'envoi : {str(e)[:150]}")

@api.get("/qc9434/invoices/{iid}/pdf")
async def qc_invoice_pdf(iid: str, user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); styles = getSampleStyleSheet()
    H = ParagraphStyle("h", parent=styles["Normal"], fontSize=16, fontName="Helvetica-Bold", textColor=NAVY)
    N = ParagraphStyle("n", parent=styles["Normal"], fontSize=9, leading=12)
    B = ParagraphStyle("b", parent=styles["Normal"], fontSize=9, leading=12, fontName="Helvetica-Bold")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    el = [_pdf_logo(38), Spacer(1, 3 * mm), Paragraph("9434-3977 QUÉBEC INC.", H), Spacer(1, 2 * mm)]
    meta = Table([[Paragraph("<b>FACTURE</b>", B), Paragraph(f"Facture No : <b>{inv['number']}</b>", N)],
                  ["", Paragraph(f"Date : {inv.get('date','')}", N)],
                  ["", Paragraph(f"Échéance : {inv.get('due_date','') or '—'}", N)]], colWidths=[95 * mm, 75 * mm])
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    el += [meta, Spacer(1, 4 * mm)]
    el += [Paragraph("Émetteur", B), Paragraph("9434-3977 Québec Inc<br/>75, boulevard René-Lévesque Ouest, 20e étage<br/>Montréal (Québec) H2Z 1A4", N), Spacer(1, 3 * mm)]
    cli = inv.get("client_name", "")
    if inv.get("client_att"): cli += f"<br/>Att : {inv['client_att']}"
    if inv.get("client_address"): cli += "<br/>" + inv["client_address"].replace("\n", "<br/>")
    el += [Paragraph("Facturé à", B), Paragraph(cli, N), Spacer(1, 5 * mm)]
    items = [["Description", "Montant"],
             [inv.get("description", "Frais de gestion"), f"{inv['amount']:,.2f} $"],
             ["Total des ventes", f"{inv['amount']:,.2f} $"],
             ["T.P.S. (5,0 %)", f"{inv['tps']:,.2f} $"],
             ["T.V.Q. (9,975 %)", f"{inv['tvq']:,.2f} $"],
             ["TOTAL DE LA PRÉSENTE FACTURE", f"{inv['total']:,.2f} $"]]
    t = Table(items, colWidths=[125 * mm, 45 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY), ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E9EDEF")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [t, Spacer(1, 8 * mm)]
    el += [Paragraph("Numéro d'inscription T.P.S. : 765426465 RT0001<br/>Numéro d'inscription T.V.Q. : 1228200201 TQ0001<br/>NEQ : 1176211903",
                     ParagraphStyle("f", parent=styles["Normal"], fontSize=8, textColor=colors.grey))]
    doc.build(el); buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=facture_{inv['number']}.pdf"})

async def _qc_payment_history(source_id: str, source: str, tier_account: str):
    entries = await db.qc9434_entries.find({"source_id": source_id, "source": source}).sort([("date", 1), ("created_at", 1)]).to_list(1000)
    out = []
    for e in entries:
        amt = round(sum(l.get("debit", 0) if source == "receipt" else l.get("credit", 0)
                        for l in e.get("lines", []) if l.get("account") == QC_DEF["cash"]), 2)
        out.append({"num": e.get("num", ""), "date": e.get("date", ""), "amount": amt,
                    "description": e.get("description", ""), "entry_id": str(e.get("_id"))})
    return out

@api.get("/qc9434/invoices/{iid}/payments")
async def qc_invoice_payments(iid: str, user: dict = Depends(get_current_user)):
    inv = await db.qc9434_invoices.find_one({"_id": _oid(iid)})
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    payments = await _qc_payment_history(iid, "receipt", QC_DEF["ar"])
    return {"invoice": _qc_invoice_out(inv), "payments": payments}

@api.post("/qc9434/invoices/send-reminders")
async def qc_invoice_send_reminders(year: int, user: dict = Depends(get_current_user)):
    if not _email_configured():
        raise HTTPException(status_code=400, detail="Service d'email non configuré. Un administrateur doit renseigner la clé Resend.")
    today = datetime.now(timezone.utc).date().isoformat()
    docs = await db.qc9434_invoices.find({"year": int(year), "company_id": await _company_id("qc9434")}).to_list(2000)
    overdue = [d for d in docs if d.get("status") != "paid" and d.get("due_date") and d["due_date"] < today]
    import resend
    resend.api_key = os.environ["RESEND_API_KEY"]
    sent, skipped = [], []
    for inv in overdue:
        email = (inv.get("client_email") or "").strip()
        if not email:
            skipped.append({"number": inv.get("number"), "reason": "aucun courriel"}); continue
        bal = round(inv.get("total", 0) - inv.get("paid_amount", 0), 2)
        html = (f"<div style=\"font-family:Arial,sans-serif;color:#1e293b;font-size:14px\"><p>Bonjour,</p>"
                f"<p>Notre système indique que la facture <strong>#{inv['number']}</strong> "
                f"(échéance du <strong>{inv.get('due_date')}</strong>) demeure impayée.</p>"
                f"<p>Solde dû : <strong>{bal:,.2f} $</strong> sur un total de {inv.get('total',0):,.2f} $.</p>"
                f"<p>Nous vous saurions gré de bien vouloir procéder au règlement dans les meilleurs délais. "
                f"Si le paiement a déjà été effectué, veuillez ignorer ce rappel.</p>"
                f"<p style=\"color:#64748b;font-size:12px;margin-top:24px\">9434-3977 Québec Inc.</p></div>")
        try:
            await asyncio.to_thread(resend.Emails.send, {"from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
                "to": [email], "subject": f"Rappel — Facture #{inv['number']} échue — 9434-3977 Québec Inc.", "html": html})
            await db.qc9434_invoices.update_one({"_id": inv["_id"]}, {"$set": {"reminded_at": datetime.now(timezone.utc).isoformat()}})
            sent.append({"number": inv.get("number"), "email": email})
        except Exception as e:
            logger.error(f"Relance facture {inv.get('number')} échec : {e}")
            skipped.append({"number": inv.get("number"), "reason": str(e)[:80]})
    await log_action(user, "Relancer", "9434 — Factures clients", f"{len(sent)} relance(s) · {len(skipped)} ignorée(s)")
    msg = f"{len(sent)} rappel(s) envoyé(s)" + (f", {len(skipped)} ignoré(s)" if skipped else "")
    return {"success": True, "sent": sent, "skipped": skipped, "message": msg}

# ---- Factures fournisseurs (auxiliaire payable) ------------------------
def _qc_bill_out(d):
    total = d.get("total", 0); paid = d.get("paid_amount", 0)
    items = d.get("items") or [{"description": d.get("description", ""), "account": d.get("expense_account", ""), "amount": d.get("amount", 0)}]
    return {"id": str(d["_id"]), "year": d.get("year"), "number": d.get("number"), "supplier": d.get("supplier", ""),
            "date": d.get("date"), "due_date": d.get("due_date"), "description": d.get("description", ""),
            "amount": d.get("amount", 0), "tps": d.get("tps", 0), "tvq": d.get("tvq", 0), "total": total, "items": items,
            "paid_amount": round(paid, 2), "balance": round(total - paid, 2),
            "expense_account": d.get("expense_account", ""), "status": d.get("status", "open"), "paid_at": d.get("paid_at"),
            "file_id": d.get("file_id"), "file_name": d.get("file_name"),
            "entry_id": str(d.get("entry_id")) if d.get("entry_id") else None}

@api.get("/qc9434/bills")
async def qc_bills(year: int, user: dict = Depends(get_current_user)):
    docs = await db.qc9434_bills.find({"year": int(year)}).sort("created_at", 1).to_list(2000)
    return [_qc_bill_out(d) for d in docs]

@api.post("/qc9434/bills")
async def qc_create_bill(year: int = Form(...), supplier: str = Form(...), date: str = Form(...),
        due_date: str = Form(""), description: str = Form(""), amount: float = Form(0),
        expense_account: str = Form(""), reference: str = Form(""), items_json: str = Form(""),
        file: Optional[UploadFile] = File(None), user: dict = Depends(get_current_user)):
    y = await _qc_year_doc(year)
    if not y:
        raise HTTPException(status_code=404, detail="Année introuvable — créez d'abord l'exercice.")
    if y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {year} est verrouillé.")
    raw_items = []
    if items_json.strip():
        try:
            raw_items = json.loads(items_json)
        except Exception:
            raise HTTPException(status_code=400, detail="Format des lignes invalide.")
    if not raw_items:
        raw_items = [{"description": description, "account": expense_account, "amount": amount}]
    items = []
    for it in raw_items:
        a = _round2(it.get("amount", 0))
        acc = (it.get("account") or "").strip()
        if a <= 0 or not acc:
            continue
        items.append({"description": (it.get("description") or "").strip(), "account": acc, "amount": a})
    if not items:
        raise HTTPException(status_code=400, detail="Ajoutez au moins une ligne avec un compte et un montant.")
    amt = _round2(sum(i["amount"] for i in items))
    tps = _round2(amt * QC_TPS); tvq = _round2(amt * QC_TVQ); total = _round2(amt + tps + tvq)
    file_id = file_name = None
    if file is not None:
        data = await file.read()
        if data:
            ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
            path = f"qc9434/bills/{year}/{uuid.uuid4()}.{ext}"
            try:
                result = _qc_put_object(path, data, file.content_type or "application/octet-stream")
                file_id = result["path"]; file_name = file.filename
                await db.qc9434_files.insert_one({"storage_path": file_id, "original_filename": file.filename,
                    "content_type": file.content_type, "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                logger.error(f"Upload facture fournisseur échec : {e}")
                raise HTTPException(status_code=400, detail="Échec du téléversement du fichier.")
    lines = []
    for it in items:
        lines.append({"account": it["account"], "account_name": await _qc_acc_name(it["account"]), "tiers": supplier,
                      "debit": it["amount"], "credit": 0.0, "memo": it["description"]})
    lines += [
        {"account": QC_DEF["tps_rec"], "account_name": await _qc_acc_name(QC_DEF["tps_rec"]), "tiers": "", "debit": tps, "credit": 0.0},
        {"account": QC_DEF["tvq_rec"], "account_name": await _qc_acc_name(QC_DEF["tvq_rec"]), "tiers": "", "debit": tvq, "credit": 0.0},
        {"account": QC_DEF["ap"], "account_name": await _qc_acc_name(QC_DEF["ap"]), "tiers": supplier, "debit": 0.0, "credit": total},
    ]
    entry = await _qc_post_entry(year, date, f"Facture fournisseur — {supplier}" + (f" ({reference})" if reference else ""),
        lines, reference=reference, source="bill", actor=user)
    doc = {"year": int(year), "number": reference or entry["num"], "supplier": supplier, "date": date, "due_date": due_date,
           "description": description, "amount": amt, "tps": tps, "tvq": tvq, "total": total, "expense_account": items[0]["account"],
           "items": items, "status": "open", "file_id": file_id, "file_name": file_name, "entry_id": entry["_id"],
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"),
           "company_id": await _company_id("qc9434")}
    res = await db.qc9434_bills.insert_one(doc)
    await db.qc9434_entries.update_one({"_id": entry["_id"]}, {"$set": {"source_id": str(res.inserted_id)}})
    await log_action(user, "Créer", "9434 — Facture fournisseur", f"{supplier} ({total:,.2f} $)")
    doc["_id"] = res.inserted_id
    return _qc_bill_out(doc)

async def _qc_parse_ai_json(text):
    import re
    t = (text or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
        if m:
            t = m.group(1).strip()
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        t = t[s:e + 1]
    return json.loads(t)

@api.post("/qc9434/bills/extract")
async def qc_bill_extract(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    import base64, io as _io
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    ct = (file.content_type or "").lower(); fname = (file.filename or "").lower()
    images_b64 = []
    try:
        if "pdf" in ct or fname.endswith(".pdf"):
            import fitz
            pdf = fitz.open(stream=data, filetype="pdf")
            for page in list(pdf)[:2]:
                pix = page.get_pixmap(dpi=150)
                images_b64.append(base64.b64encode(pix.tobytes("png")).decode())
            pdf.close()
        else:
            from PIL import Image
            img = Image.open(_io.BytesIO(data)).convert("RGB")
            img.thumbnail((1600, 1600))
            buf = _io.BytesIO(); img.save(buf, format="PNG")
            images_b64.append(base64.b64encode(buf.getvalue()).decode())
    except Exception as e:
        logger.error(f"Extraction facture — préparation image échec : {e}")
        raise HTTPException(status_code=400, detail="Impossible de lire le document (PDF ou image).")
    if not images_b64:
        raise HTTPException(status_code=400, detail="Aucune page exploitable dans le document.")
    charges = await db.qc9434_accounts.find({"type": "charge", "company_id": await _company_id("qc9434")}).sort("gl", 1).to_list(500)
    charge_list = "\n".join(f"{c['gl']} — {c.get('description', '')}" for c in charges) or "(aucun)"
    system = ("Tu es un comptable québécois expert. Tu analyses une facture FOURNISSEUR et tu retournes des données structurées "
              "en français. Les montants sont en dollars canadiens. TPS = 5 %, TVQ = 9,975 %.")
    prompt = (
        "Analyse cette facture fournisseur et retourne UNIQUEMENT un objet JSON valide (aucun texte autour), au format :\n"
        '{"supplier": string, "date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD ou vide", "reference": string, '
        '"items": [{"description": string, "account": "<code_GL>", "amount": number}], '
        '"subtotal": number, "tps": number, "tvq": number, "total": number, "confidence": number}\n'
        "Règles : chaque \"amount\" de ligne est le montant HORS TAXES. Choisis pour chaque ligne le compte de charge le plus "
        "approprié en utilisant EXACTEMENT un code GL de cette liste :\n" + charge_list + "\n"
        "Si une information est absente, mets une chaîne vide ou 0."
    )
    try:
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"qc-extract-{uuid.uuid4()}",
                       system_message=system).with_model("openai", "gpt-5.4")
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=b) for b in images_b64])
        raw = await chat.send_message(msg)
        parsed = await _qc_parse_ai_json(raw)
    except Exception as e:
        logger.error(f"Extraction facture — appel IA échec : {e}")
        raise HTTPException(status_code=502, detail="L'analyse IA a échoué. Veuillez saisir les champs manuellement.")
    valid_gl = {c["gl"] for c in charges}
    default_gl = QC_DEF.get("default_expense") or (charges[0]["gl"] if charges else "")
    items = []
    for it in (parsed.get("items") or []):
        a = _round2(it.get("amount", 0))
        if a <= 0:
            continue
        acc = str(it.get("account", "")).strip()
        items.append({"description": str(it.get("description", "")).strip(),
                      "account": acc if acc in valid_gl else default_gl, "amount": a})
    if not items:
        st = _round2(parsed.get("subtotal", 0)) or _round2((parsed.get("total", 0)) / 1.14975)
        if st > 0:
            items = [{"description": "Facture", "account": default_gl, "amount": st}]
    return {"supplier": str(parsed.get("supplier", "")).strip(), "date": str(parsed.get("date", "")).strip(),
            "due_date": str(parsed.get("due_date", "")).strip(), "reference": str(parsed.get("reference", "")).strip(),
            "items": items, "confidence": parsed.get("confidence", 0)}

@api.post("/qc9434/bills/{bid}/pay")
async def qc_pay_bill(bid: str, date: str = "", amount: float = 0, user: dict = Depends(get_current_user)):
    b = await db.qc9434_bills.find_one({"_id": _oid(bid)})
    if not b:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if b.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Facture déjà payée.")
    y = await _qc_year_doc(b["year"])
    if y and y.get("locked"):
        raise HTTPException(status_code=403, detail=f"L'exercice {b['year']} est verrouillé.")
    balance = round(b["total"] - b.get("paid_amount", 0), 2)
    amt = round(float(amount), 2) if amount and float(amount) > 0 else balance
    if amt <= 0 or amt > balance + 0.005:
        raise HTTPException(status_code=400, detail=f"Montant invalide (solde restant : {balance:,.2f} $).")
    lines = [
        {"account": QC_DEF["ap"], "account_name": await _qc_acc_name(QC_DEF["ap"]), "tiers": b.get("supplier", ""), "debit": amt, "credit": 0.0},
        {"account": QC_DEF["cash"], "account_name": await _qc_acc_name(QC_DEF["cash"]), "tiers": b.get("supplier", ""), "debit": 0.0, "credit": amt},
    ]
    await _qc_post_entry(b["year"], date or datetime.now(timezone.utc).date().isoformat(),
        f"Paiement fournisseur — {b.get('supplier','')}", lines, reference=b.get("number", ""), source="payment", source_id=bid, actor=user)
    new_paid = round(b.get("paid_amount", 0) + amt, 2)
    paid_full = new_paid >= round(b["total"], 2) - 0.005
    await db.qc9434_bills.update_one({"_id": _oid(bid)}, {"$set": {"paid_amount": new_paid,
        "status": "paid" if paid_full else "partial", "paid_at": datetime.now(timezone.utc).isoformat() if paid_full else b.get("paid_at")}})
    await log_action(user, "Payer", "9434 — Facture fournisseur", f"{b.get('supplier','')} ({amt:,.2f} $)")
    return {"success": True, "paid_amount": new_paid, "balance": round(b["total"] - new_paid, 2)}

@api.get("/qc9434/bills/{bid}/payments")
async def qc_bill_payments(bid: str, user: dict = Depends(get_current_user)):
    b = await db.qc9434_bills.find_one({"_id": _oid(bid)})
    if not b:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    payments = await _qc_payment_history(bid, "payment", QC_DEF["ap"])
    return {"bill": _qc_bill_out(b), "payments": payments}

@api.get("/qc9434/bills/{bid}/file")
async def qc_bill_file(bid: str, auth: str = Query(None), authorization: str = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Non autorisé")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        raise HTTPException(status_code=401, detail="Session invalide")
    b = await db.qc9434_bills.find_one({"_id": _oid(bid)})
    if not b or not b.get("file_id"):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    data, ct = _qc_get_object(b["file_id"])
    return Response(content=data, media_type=ct, headers={"Content-Disposition": f"inline; filename={b.get('file_name','facture')}"})

# ---- Import des écritures du modèle Excel ------------------------------
@api.post("/qc9434/import-model")
async def qc_import_model(user: dict = Depends(require_admin)):
    if await db.qc9434_entries.count_documents({}) > 0 or await db.qc9434_years.count_documents({}) > 0:
        raise HTTPException(status_code=400, detail="Des données existent déjà. Videz d'abord les exercices pour réimporter le modèle.")
    await _qc_seed_accounts()
    await db.qc9434_years.insert_one({"_id": 2025, "locked": False, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"), "company_id": await _company_id("qc9434")})
    await db.qc9434_settings.update_one({"_id": "config"}, {"$set": {"active_year": 2025}}, upsert=True)
    inv = await qc_create_invoice(QcInvoiceIn(date="2025-10-31", due_date="2025-11-30", client_name="Société en commandite ACCS",
        client_att="Simon Fournier", client_address="3152 Boulevard des Entreprises\nTerrebonne, Québec J6X 4J8",
        description="Frais de gestion annuel pour 2025", amount=10000.0), 2025, user)
    await _qc_post_closing(2025, user)
    await db.qc9434_years.update_one({"_id": 2025}, {"$set": {"locked": True, "locked_by": user.get("email"), "locked_at": datetime.now(timezone.utc).isoformat()}})
    await db.qc9434_years.insert_one({"_id": 2026, "locked": False, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user.get("email"), "company_id": await _company_id("qc9434")})
    await db.qc9434_settings.update_one({"_id": "config"}, {"$set": {"active_year": 2026}})
    def L(gl, name, dr, cr, tiers=""):
        return {"account": gl, "account_name": name, "tiers": tiers, "debit": float(dr), "credit": float(cr)}
    C = "Caisse populaire (CAD) - # 084129"
    entries = [
        ("2026-01-30", "Frais bancaires", [L("100110", C, 0, 5.95), L("580210", "Frais de banque", 5.95, 0)]),
        ("2026-02-27", "Frais bancaires", [L("100110", C, 0, 5.95), L("580210", "Frais de banque", 5.95, 0)]),
        ("2026-02-13", "Paiement reçu de SEC ACCS pour facture #2025-001", [L("100110", C, 11497.50, 0, "SEC ACCS"), L("130118", "Comptes à recevoir - Apparentés", 0, 11497.50, "SEC ACCS")]),
        ("2026-03-31", "Frais bancaires", [L("100110", C, 0, 5.95), L("580210", "Frais de banque", 5.95, 0)]),
        ("2026-04-30", "Frais bancaires", [L("100110", C, 0, 5.95), L("580210", "Frais de banque", 5.95, 0)]),
        ("2026-05-31", "Frais bancaires", [L("100110", C, 0, 5.95), L("580210", "Frais de banque", 5.95, 0)]),
        ("2026-06-10", "Revenus d'intérêts", [L("100110", C, 11.64, 0), L("578220", "Intérêts sur le compte de banque", 0, 11.64)]),
        ("2026-06-15", "Paiement dividendes SEC ACCS", [L("100110", C, 50, 0), L("160010", "Participation - Société en commandite ACCS", 0, 50)]),
        ("2026-06-17", "Paiement impôts", [L("100110", C, 0, 284.81), L("215400", "Impôt à payer", 284.81, 0)]),
    ]
    for date, desc, lines in entries:
        await _qc_post_entry(2026, date, desc, lines, source="import", actor=user)
    await db.qc9434_invoices.update_one({"_id": _oid(inv["id"])}, {"$set": {"status": "paid", "paid_at": "2026-02-13"}})
    await _qc_seed_opening_balances(user)
    await log_action(user, "Importer", "9434 — Modèle Excel", "Exercices 2025 (verrouillé) + 2026")
    return {"success": True, "message": "Modèle importé : exercice 2025 (verrouillé) + exercice 2026 (9 écritures) + soldes d'ouverture 2026."}

@api.post("/qc9434/seed-opening")
async def qc_seed_opening(user: dict = Depends(require_admin)):
    doc = await _qc_seed_opening_balances(user)
    await log_action(user, "Recalculer", "9434 — Soldes d'ouverture 2026", "à-nouveaux régénérés")
    return {"success": True, "lines": len((doc or {}).get("lines", [])), "message": "Soldes d'ouverture 2026 régénérés."}

@api.get("/qc9434/opening/{year}")
async def qc_get_opening(year: int, user: dict = Depends(get_current_user)):
    y = int(year)
    bal, accts = await _qc_report_balances(y)
    rows = []
    for gl, a in accts.items():
        if a.get("type") not in ("actif", "passif", "capitaux"):
            continue
        op = round((bal.get(gl) or {}).get("opening", 0.0), 2)
        rows.append({"gl": gl, "description": a.get("description", gl), "section": a.get("section", ""),
                     "type": a.get("type"), "sort": a.get("sort", 0),
                     "debit": op if op > 0 else 0.0, "credit": round(-op, 2) if op < 0 else 0.0})
    rows.sort(key=lambda r: (r["gl"]))
    td = round(sum(r["debit"] for r in rows), 2); tc = round(sum(r["credit"] for r in rows), 2)
    return {"year": y, "rows": rows, "total_debit": td, "total_credit": tc, "balanced": abs(td - tc) < 0.01}

@api.put("/qc9434/opening/{year}")
async def qc_put_opening(year: int, payload: dict, user: dict = Depends(require_admin)):
    y = int(year)
    rows = payload.get("rows", [])
    targets = {}
    td = tc = 0.0
    for r in rows:
        gl = str(r.get("gl", "")).strip()
        if not gl:
            continue
        d = round(float(r.get("debit") or 0), 2); c = round(float(r.get("credit") or 0), 2)
        td += d; tc += c
        targets[gl] = round(targets.get(gl, 0.0) + d - c, 2)
    if abs(round(td - tc, 2)) >= 0.01:
        raise HTTPException(status_code=400, detail=f"Débits ({td:,.2f}) et crédits ({tc:,.2f}) doivent être égaux (écart {td - tc:,.2f}).")
    await _qc_post_opening(y, targets, user)
    await log_action(user, "Modifier", f"9434 — Soldes d'ouverture {y}", f"{len(targets)} compte(s)")
    return await qc_get_opening(y, user)


# ---- Détail d'un compte (drill-down) -----------------------------------
@api.get("/qc9434/account-detail")
async def qc_account_detail(year: int, account: str, scope: str = "movement", user: dict = Depends(get_current_user)):
    q = {"source": {"$ne": "closing"}, "company_id": await _company_id("qc9434")}
    q["year"] = {"$lte": int(year)} if scope == "cumulative" else int(year)
    docs = await db.qc9434_entries.find(q).sort([("date", 1), ("seq", 1)]).to_list(50000)
    name = await _qc_acc_name(account)
    rows = []; running = 0.0
    for e in docs:
        for l in e.get("lines", []):
            if (l.get("account") or "").strip() != account:
                continue
            dr = float(l.get("debit") or 0); cr = float(l.get("credit") or 0)
            running += dr - cr
            rows.append({"date": e.get("date"), "num": e.get("num"), "year": e.get("year"),
                         "description": e.get("description", ""), "tiers": l.get("tiers", ""),
                         "debit": round(dr, 2), "credit": round(cr, 2), "balance": round(running, 2)})
    return {"account": account, "name": name, "scope": scope, "year": int(year), "rows": rows,
            "total_debit": round(sum(r["debit"] for r in rows), 2), "total_credit": round(sum(r["credit"] for r in rows), 2),
            "balance": round(running, 2)}

# ---- États Financiers (structure du modèle Excel) ---------------------
async def _qc_etats_financiers(year):
    bal, accts = await _qc_report_balances(year)
    def bcum(gl): return (bal.get(gl) or {}).get("cumulative", 0.0)
    def sec_pl(section, key):
        s = 0.0
        for gl, a in accts.items():
            if a.get("section") == section:
                s += (bal.get(gl) or {}).get(key, 0.0)
        return s
    def stmt(key):
        rev = round(-sec_pl("revenus", key), 2)
        juridique = round((bal.get("550108") or {}).get(key, 0.0), 2)
        expertise = round((bal.get("540210") or {}).get(key, 0.0), 2)
        financiers = round(sum((bal.get(g) or {}).get(key, 0.0) for g in ("578220", "579000", "580210")), 2)
        charges = round(juridique + expertise + financiers, 2)
        avant_qp = round(rev - charges, 2)
        qp = round(-sec_pl("quote_part", key), 2)
        avant_impot = round(avant_qp + qp, 2)
        impots = round(sec_pl("impots", key), 2)
        net = round(avant_impot - impots, 2)
        return {"rev": rev, "juridique": juridique, "expertise": expertise, "financiers": financiers,
                "charges": charges, "avant_qp": avant_qp, "qp": qp, "avant_impot": avant_impot, "impots": impots, "net": net}
    cur = stmt("movement")
    prev = dict(QC_EF_PREV["result"])
    bnr_debut_cur = round(QC_EF_PREV["bnr"]["fin"], 2)
    bnr_fin_cur = round(bnr_debut_cur + cur["net"], 2)
    bnr_debut_prev = round(QC_EF_PREV["bnr"]["debut"], 2)
    bnr_fin_prev = round(QC_EF_PREV["bnr"]["fin"], 2)
    def cum_pos(gl): return round(-bcum(gl), 2)
    treso = round(bcum("100105") + bcum("100110"), 2)
    clients = round(bcum("130118"), 2)
    taxes_rec = round(bcum("145110") + bcum("145101"), 2)
    total_ct = round(treso + clients + taxes_rec, 2)
    placement = round(bcum("160010"), 2)
    total_actif = round(total_ct + placement, 2)
    crediteurs = round(cum_pos("211010") + cum_pos("211120"), 2)
    taxes_rem = round(cum_pos("215301") + cum_pos("215310") + cum_pos("215311"), 2)
    impot_pay = round(cum_pos("215400"), 2)
    total_passif = round(crediteurs + taxes_rem + impot_pay, 2)
    capital = round(cum_pos("310000"), 2)
    # BNR au bilan = solde équilibrant (actif − passif − capital) → le bilan balance toujours
    bnr_bilan = round(total_actif - total_passif - capital, 2)
    total_pc = round(total_passif + capital + bnr_bilan, 2)
    # ---- États des flux de trésorerie (méthode indirecte) ----
    def bopen(gl): return (bal.get(gl) or {}).get("opening", 0.0)
    def bclose(gl): return (bal.get(gl) or {}).get("cumulative", 0.0)
    def contrib(gls): return round(sum(bopen(g) - bclose(g) for g in gls), 2)  # apport de trésorerie (débit: ouverture - clôture)
    CASH = ["100105", "100110"]; ARG = ["130118"]; TXREC = ["145110", "145101"]; PLAC = ["160010"]
    PAY = ["211010", "211120"]; TXREM = ["215301", "215310", "215311"]; IMP = ["215400"]; CAP = ["310000"]
    cash_open = round(sum(bopen(g) for g in CASH), 2)
    cash_close = round(sum(bclose(g) for g in CASH), 2)
    net_mv = cur["net"]; qp_mv = cur["qp"]
    d_clients = contrib(ARG); d_txrec = contrib(TXREC); d_pay = contrib(PAY); d_txrem = contrib(TXREM); d_imp = contrib(IMP)
    wc = round(d_clients + d_txrec + d_pay + d_txrem + d_imp, 2)
    op_sub = round(net_mv - qp_mv + wc, 2)
    fin = contrib(CAP)
    inv = round(contrib(PLAC) + qp_mv, 2)
    net_var = round(op_sub + fin + inv, 2)
    cf = {"net": net_mv, "qp_noncash": round(-qp_mv, 2), "wc": wc, "op_sub": op_sub,
          "capital": fin, "fin_sub": fin, "placement": inv, "inv_sub": inv,
          "net_var": net_var, "cash_open": cash_open, "cash_close": round(cash_open + net_var, 2),
          "bilan_cash": cash_close, "reconciled": abs(cash_open + net_var - cash_close) < 1.0,
          "prev": dict(QC_CF_PREV),
          "wc_detail": {"clients": d_clients, "taxes_rec": d_txrec, "crediteurs": d_pay, "taxes_rem": d_txrem, "impot": d_imp, "total": wc}}
    admins = await _qc_ef_admins()
    return {"year": int(year), "cur": cur, "prev": prev, "prev_year": QC_EF_PREV_YEAR, "admins": admins,
            "bnr": {"debut_cur": bnr_debut_cur, "fin_cur": bnr_fin_cur, "debut_prev": bnr_debut_prev, "fin_prev": bnr_fin_prev},
            "cashflow": cf,
            "bilan": {"treso": treso, "clients": clients, "taxes_rec": taxes_rec, "total_ct": total_ct,
                      "placement": placement, "total_actif": total_actif, "crediteurs": crediteurs, "taxes_rem": taxes_rem,
                      "impot_pay": impot_pay, "total_passif": total_passif, "capital": capital, "bnr": bnr_bilan, "total_pc": total_pc},
            "prev_bilan": dict(QC_EF_PREV["bilan"]),
            "qp": {"hilo_cur": round(cur["net"] * 0.65, 2), "hilo_prev": round(prev["net"] * 0.65, 2),
                   "autre_cur": round(cur["net"] * 0.35, 2), "autre_prev": round(prev["net"] * 0.35, 2)}}

def _qc_ef_pdf(ef):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    NAVY = colors.HexColor("#0F172A"); y = ef["year"]; c = ef["cur"]; p = ef["prev"]; b = ef["bilan"]; bn = ef["bnr"]
    styles = getSampleStyleSheet()
    TITLE = ParagraphStyle("t", parent=styles["Normal"], fontSize=14, fontName="Helvetica-Bold", textColor=NAVY, alignment=1)
    SUB = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, alignment=1, textColor=colors.grey)
    H = ParagraphStyle("h", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, alignment=1)
    B = ParagraphStyle("efb", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold", textColor=NAVY)
    N = ParagraphStyle("efn", parent=styles["Normal"], fontSize=9, leading=13)
    def fmt(v): return f"{v:,.2f}" if v else "—"
    def money_table(data):
        t = Table([[r[0], fmt(r[1]) if isinstance(r[1], (int, float)) else r[1], fmt(r[2]) if isinstance(r[2], (int, float)) else r[2]] for r in data],
                  colWidths=[110 * mm, 30 * mm, 30 * mm])
        st = [("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
              ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        return t, st
    el = [_pdf_logo(52), Spacer(1, 22 * mm), Paragraph("9434-3977 QUÉBEC INC. - COMMANDITÉ", TITLE), Spacer(1, 6 * mm),
          Paragraph("ÉTATS FINANCIERS (non-audités)", H), Paragraph(f"31 décembre {y}", SUB), PageBreak()]
    el += [Paragraph("9434-3977 QUÉBEC INC. - COMMANDITÉ", H), Spacer(1, 2 * mm),
           Paragraph("ÉTAT DES RÉSULTATS ET DES BÉNÉFICES NON-RÉPARTIS", H),
           Paragraph("Exercice terminé le 31 décembre — Non-audités — En dollars canadiens", SUB), Spacer(1, 4 * mm)]
    rows = [["", str(y), str(y - 1)], ["Produits", "", ""], ["  Honoraires de gestion", c["rev"], p["rev"]],
            ["Charges", "", ""], ["  Services juridiques", c["juridique"], p["juridique"]],
            ["  Services d'expertise comptable et financière", c["expertise"], p["expertise"]],
            ["  Frais financiers", c["financiers"], p["financiers"]], ["  ", c["charges"], p["charges"]],
            ["Bénéfice (perte) avant quote-part et impôts", c["avant_qp"], p["avant_qp"]],
            ["Quote-part des résultats de la société en commandite", c["qp"], p["qp"]],
            ["Bénéfice (perte) avant impôts sur les bénéfices", c["avant_impot"], p["avant_impot"]],
            ["Impôts sur les bénéfices exigibles", c["impots"], p["impots"]],
            ["Bénéfice (perte) net(te) de l'exercice", c["net"], p["net"]],
            ["Bénéfices non répartis au début de l'exercice", bn["debut_cur"], bn["debut_prev"]],
            ["Bénéfices non répartis à la fin de l'exercice", bn["fin_cur"], bn["fin_prev"]]]
    t, st = money_table(rows)
    st += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
           ("FONTNAME", (0, 12), (-1, 12), "Helvetica-Bold"), ("LINEABOVE", (0, 12), (-1, 12), 0.5, colors.grey),
           ("FONTNAME", (0, 14), (-1, 14), "Helvetica-Bold"), ("LINEABOVE", (0, 7), (-1, 7), 0.3, colors.grey)]
    t.setStyle(TableStyle(st)); el += [t, PageBreak()]
    el += [Paragraph("9434-3977 QUÉBEC INC. - COMMANDITÉ", H), Spacer(1, 2 * mm), Paragraph("BILAN", H),
           Paragraph("Non-audités — En dollars canadiens", SUB), Spacer(1, 4 * mm)]
    pb = ef.get("prev_bilan", {})
    brows = [["", str(y), str(y - 1)], ["ACTIF", "", ""], ["Actif à court terme", "", ""],
             ["  Trésorerie", b["treso"], pb.get("treso")], ["  Clients - Société en commandite ACCS", b["clients"], pb.get("clients")],
             ["  Sommes à recevoir de l'état - Taxes de ventes", b["taxes_rec"], pb.get("taxes_rec")], ["  ", b["total_ct"], pb.get("total_ct")],
             ["Placement – Société en commandite ACCS", b["placement"], pb.get("placement")], ["TOTAL DE L'ACTIF", b["total_actif"], pb.get("total_actif")],
             ["PASSIF", "", ""], ["Passif à court terme", "", ""],
             ["  Créditeurs et charges à payer aux apparentés", b["crediteurs"], pb.get("crediteurs")],
             ["  Taxes de ventes à remettre", b["taxes_rem"], pb.get("taxes_rem")], ["  Impôt à payer", b["impot_pay"], pb.get("impot_pay")],
             ["  ", b["total_passif"], pb.get("total_passif")], ["Capital-actions", b["capital"], pb.get("capital")],
             ["Bénéfices non-répartis", b["bnr"], pb.get("bnr")], ["TOTAL DU PASSIF ET CAPITAUX PROPRES", b["total_pc"], pb.get("total_pc")]]
    t2, st2 = money_table(brows)
    st2 += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTNAME", (0, 9), (-1, 9), "Helvetica-Bold"), ("FONTNAME", (0, 8), (-1, 8), "Helvetica-Bold"),
            ("FONTNAME", (0, 17), (-1, 17), "Helvetica-Bold"), ("LINEABOVE", (0, 8), (-1, 8), 0.5, NAVY),
            ("LINEABOVE", (0, 17), (-1, 17), 0.5, NAVY)]
    t2.setStyle(TableStyle(st2)); el += [t2, Spacer(1, 10 * mm)]
    ad = ef.get("admins") or {}
    el += [Paragraph("Au nom du Conseil d'administration", B), Spacer(1, 10 * mm)]
    sig = Table([[Paragraph(f"_____________________________<br/><b>{ad.get('a1_name','')}</b><br/>{ad.get('a1_title','Administrateur')}", N),
                  Paragraph(f"_____________________________<br/><b>{ad.get('a2_name','')}</b><br/>{ad.get('a2_title','Administrateur')}", N)]],
                 colWidths=[85 * mm, 85 * mm])
    sig.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [sig]
    cf = ef.get("cashflow")
    if cf:
        cp = cf.get("prev", {})
        el += [PageBreak(), Paragraph("9434-3977 QUÉBEC INC. - COMMANDITÉ", H), Spacer(1, 2 * mm),
               Paragraph("ÉTATS DES FLUX DE TRÉSORERIE", H),
               Paragraph(f"Exercice terminé le 31 décembre {y} — Non-audités — En dollars canadiens", SUB), Spacer(1, 4 * mm)]
        crows = [["", str(y), str(y - 1)],
                 ["Activités d'exploitation", "", ""],
                 ["  Bénéfice (perte) net(te) de l'exercice", cf["net"], cp.get("net")],
                 ["  Élément sans effet sur la trésorerie :", "", ""],
                 ["    Quote-part des résultats de la Société en commandite", cf["qp_noncash"], cp.get("qp_noncash")],
                 ["  Variation des éléments hors caisse du fonds de roulement", cf["wc"], cp.get("wc")],
                 ["  ", cf["op_sub"], cp.get("op_sub")],
                 ["Activités de financement", "", ""],
                 ["  Émission d'actions ordinaires", cf["capital"], cp.get("capital")],
                 ["Activités d'investissement", "", ""],
                 ["  Variation du placement – Société en commandite ACCS", cf["placement"], cp.get("placement")],
                 ["Variation nette de la trésorerie au cours de l'exercice", cf["net_var"], cp.get("net_var")],
                 ["Trésorerie au début de l'exercice", cf["cash_open"], cp.get("cash_open")],
                 ["Trésorerie à la fin de l'exercice", cf["cash_close"], cp.get("cash_close")]]
        t3, st3 = money_table(crows)
        st3 += [("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
                ("FONTNAME", (0, 9), (-1, 9), "Helvetica-Bold"), ("FONTNAME", (0, 11), (-1, 13), "Helvetica-Bold"),
                ("LINEABOVE", (0, 6), (-1, 6), 0.3, colors.grey), ("LINEABOVE", (0, 11), (-1, 11), 0.5, NAVY)]
        t3.setStyle(TableStyle(st3)); el += [t3, Spacer(1, 4 * mm)]
        cpd = cp.get("wc_detail", {}); wd = cf["wc_detail"]
        drows = [["Informations supplémentaires — Variation des éléments hors caisse du fonds de roulement", str(y), str(y - 1)],
                 ["  Clients – Société en commandite ACCS", wd["clients"], cpd.get("clients")],
                 ["  Sommes à recevoir de l'état - Taxes de ventes", wd["taxes_rec"], cpd.get("taxes_rec")],
                 ["  Créditeurs et charges à payer aux apparentés", wd["crediteurs"], cpd.get("crediteurs")],
                 ["  Taxes de ventes à remettre", wd["taxes_rem"], cpd.get("taxes_rem")],
                 ["  Impôt à payer", wd["impot"], cpd.get("impot")],
                 ["  ", wd["total"], cpd.get("total")]]
        t4, st4 = money_table(drows)
        st4 += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("LINEABOVE", (0, 6), (-1, 6), 0.3, colors.grey)]
        t4.setStyle(TableStyle(st4)); el += [t4]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(el); buf.seek(0)
    return buf.getvalue()

def _qc_ef_xlsx(ef):
    from openpyxl.styles import Font, Alignment
    y = ef["year"]; c = ef["cur"]; p = ef["prev"]; b = ef["bilan"]; bn = ef["bnr"]
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Résultats et BNR"
    ws.append(["9434-3977 QUÉBEC INC. - COMMANDITÉ"]); ws.append(["ÉTAT DES RÉSULTATS ET DES BÉNÉFICES NON-RÉPARTIS"])
    ws.append(["", y, y - 1])
    for lbl, cv, pv in [("Produits — Honoraires de gestion", c["rev"], p["rev"]),
                        ("Charges — Services juridiques", c["juridique"], p["juridique"]),
                        ("Charges — Services d'expertise comptable et financière", c["expertise"], p["expertise"]),
                        ("Charges — Frais financiers", c["financiers"], p["financiers"]),
                        ("Total des charges", c["charges"], p["charges"]),
                        ("Bénéfice avant quote-part et impôts", c["avant_qp"], p["avant_qp"]),
                        ("Quote-part des résultats de la société en commandite", c["qp"], p["qp"]),
                        ("Bénéfice avant impôts", c["avant_impot"], p["avant_impot"]),
                        ("Impôts sur les bénéfices exigibles", c["impots"], p["impots"]),
                        ("Bénéfice (perte) net(te) de l'exercice", c["net"], p["net"]),
                        ("BNR au début de l'exercice", bn["debut_cur"], bn["debut_prev"]),
                        ("BNR à la fin de l'exercice", bn["fin_cur"], bn["fin_prev"])]:
        ws.append([lbl, cv, pv])
    ws.append([]); ws.append(["BILAN", y, y - 1])
    pb = ef.get("prev_bilan", {})
    for lbl, v, pk in [("Trésorerie", b["treso"], "treso"), ("Clients - Société en commandite ACCS", b["clients"], "clients"),
                   ("Sommes à recevoir de l'état - Taxes de ventes", b["taxes_rec"], "taxes_rec"),
                   ("Total de l'actif à court terme", b["total_ct"], "total_ct"), ("Placement – SEC ACCS", b["placement"], "placement"),
                   ("TOTAL DE L'ACTIF", b["total_actif"], "total_actif"), ("Créditeurs et charges à payer", b["crediteurs"], "crediteurs"),
                   ("Taxes de ventes à remettre", b["taxes_rem"], "taxes_rem"), ("Impôt à payer", b["impot_pay"], "impot_pay"),
                   ("Total du passif à court terme", b["total_passif"], "total_passif"), ("Capital-actions", b["capital"], "capital"),
                   ("Bénéfices non-répartis", b["bnr"], "bnr"), ("TOTAL DU PASSIF ET CAPITAUX PROPRES", b["total_pc"], "total_pc")]:
        ws.append([lbl, v, pb.get(pk)])
    cf = ef.get("cashflow")
    if cf:
        cp = cf.get("prev", {}); cpd = cp.get("wc_detail", {}); wd = cf["wc_detail"]
        ws.append([]); ws.append(["ÉTATS DES FLUX DE TRÉSORERIE", y, y - 1])
        for lbl, v, pv in [("Activités d'exploitation", None, None),
                       ("  Bénéfice (perte) net(te) de l'exercice", cf["net"], cp.get("net")),
                       ("  Quote-part des résultats de la Société en commandite (sans effet trésorerie)", cf["qp_noncash"], cp.get("qp_noncash")),
                       ("  Variation des éléments hors caisse du fonds de roulement", cf["wc"], cp.get("wc")),
                       ("  Flux liés à l'exploitation", cf["op_sub"], cp.get("op_sub")),
                       ("Activités de financement — Émission d'actions ordinaires", cf["capital"], cp.get("capital")),
                       ("Activités d'investissement — Variation du placement – SEC ACCS", cf["placement"], cp.get("placement")),
                       ("Variation nette de la trésorerie", cf["net_var"], cp.get("net_var")),
                       ("Trésorerie au début de l'exercice", cf["cash_open"], cp.get("cash_open")),
                       ("Trésorerie à la fin de l'exercice", cf["cash_close"], cp.get("cash_close"))]:
            ws.append([lbl, v, pv])
        ws.append([]); ws.append(["Variation des éléments hors caisse du fonds de roulement", y, y - 1])
        for lbl, v, pv in [("Clients – Société en commandite ACCS", wd["clients"], cpd.get("clients")),
                       ("Sommes à recevoir de l'état - Taxes de ventes", wd["taxes_rec"], cpd.get("taxes_rec")),
                       ("Créditeurs et charges à payer aux apparentés", wd["crediteurs"], cpd.get("crediteurs")),
                       ("Taxes de ventes à remettre", wd["taxes_rem"], cpd.get("taxes_rem")),
                       ("Impôt à payer", wd["impot"], cpd.get("impot")),
                       ("Total", wd["total"], cpd.get("total"))]:
            ws.append([lbl, v, pv])
    ad = ef.get("admins") or {}
    ws.append([]); ws.append(["Au nom du Conseil d'administration"])
    ws.append([ad.get("a1_name", ""), ad.get("a2_name", "")])
    ws.append([ad.get("a1_title", "Administrateur"), ad.get("a2_title", "Administrateur")])
    ws["A1"].font = Font(bold=True, size=13); ws.column_dimensions["A"].width = 52
    for col in ("B", "C"):
        ws.column_dimensions[col].width = 16
    for row in ws.iter_rows(min_col=2, max_col=3):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00;(#,##0.00)'; cell.alignment = Alignment(horizontal="right")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.getvalue()

@api.get("/qc9434/etats-financiers")
async def qc_ef(year: int, user: dict = Depends(get_current_user)):
    return await _qc_etats_financiers(year)

@api.get("/qc9434/ef-settings")
async def qc_ef_settings(user: dict = Depends(get_current_user)):
    return await _qc_ef_admins()

@api.put("/qc9434/ef-settings")
async def qc_ef_settings_update(payload: dict, user: dict = Depends(require_admin)):
    admins = {k: str(payload.get(k, "")).strip() for k in ("a1_name", "a1_title", "a2_name", "a2_title") if k in payload}
    await db.qc9434_settings.update_one({"_id": "config"}, {"$set": {"ef_admins": {**QC_EF_ADMINS_DEFAULT, **admins}}}, upsert=True)
    await log_action(user, "Modifier", "9434 — Signataires États Financiers", ", ".join(v for v in admins.values() if v))
    return await _qc_ef_admins()

@api.get("/qc9434/etats-financiers/pdf")
async def qc_ef_pdf(year: int, user: dict = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(_qc_ef_pdf(await _qc_etats_financiers(year))),
        media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=etats_financiers_9434_{year}.pdf"})

@api.get("/qc9434/etats-financiers/excel")
async def qc_ef_excel(year: int, user: dict = Depends(get_current_user)):
    return StreamingResponse(io.BytesIO(_qc_ef_xlsx(await _qc_etats_financiers(year))),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=etats_financiers_9434_{year}.xlsx"})







import acct_ai
acct_ai.init(
    db=db, log_action=log_action, _acct_report=_acct_report, _kpi_data=_kpi_data,
    _bilan_sommaire_data=_bilan_sommaire_data, _pnl_figures=_pnl_figures, _cashflow_data=_cashflow_data,
    _pkey=_pkey, _add_months=_add_months, MONTHS_FR=MONTHS_FR, get_current_user=get_current_user,
)
api.include_router(acct_ai.router)

app.include_router(api)

WRITE_ALLOW_ALL = {"/api/auth/login", "/api/auth/logout", "/api/me/preferences", "/api/me/avatar", "/api/acct/bv", "/api/acct/account-map",
                   "/api/acct/ai/variance", "/api/acct/ai/anomalies", "/api/acct/ai/chat", "/api/acct/ai/suggest-mapping",
                   "/api/acct/report/by-manager/note"}

def _is_admin_only_path(path: str) -> bool:
    return (path.startswith("/api/users")
            or path == "/api/hypotheses"
            or path == "/api/budget/lock"
            or path.startswith("/api/years"))

def _legacy_prefix_for_path(path: str):
    """Résout le préfixe legacy de la société ciblée par une route financière."""
    if path == "/api/acct" or path.startswith("/api/acct/"):
        return "acct"
    if path == "/api/qc9434" or path.startswith("/api/qc9434/"):
        return "qc9434"
    return None

@app.middleware("http")
async def write_guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)

    legacy = _legacy_prefix_for_path(path)
    is_write = request.method in ("POST", "PUT", "DELETE", "PATCH")
    # Le lookup utilisateur n'est nécessaire que pour une route financière legacy
    # (contrôle d'accès société, toutes méthodes) ou une écriture (garde de rôle).
    if not legacy and not is_write:
        return await call_next(request)

    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]

    user_doc = None
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            user_doc = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        except Exception:
            user_doc = None

    # 1. P1.11 — Enforcement d'accès société sur les routes financières legacy (toutes méthodes).
    #    Le legacy_prefix / _company_id sert UNIQUEMENT de pont pour résoudre la société ;
    #    l'autorisation passe systématiquement par le helper centralisé require_company_access
    #    (admin = toutes les sociétés du workspace ; cross-workspace/inexistant = 404 sans fuite).
    #    On n'agit que si un utilisateur valide est identifié — sinon la route renverra 401.
    if legacy and user_doc is not None:
        try:
            company_id = await _company_id(legacy)
        except Exception:
            company_id = None
        if company_id is not None:
            workspace_doc = await load_workspace_for_user(db, user_doc)
            auth_user = build_auth_user(user_doc, workspace_doc)
            try:
                await require_company_access(db, company_id, auth_user)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # 2. Garde d'écriture par rôle (comportement existant).
    if is_write and path not in WRITE_ALLOW_ALL:
        if user_doc is not None:
            role = user_doc.get("role")
            if _is_admin_only_path(path):
                if role != "admin":
                    return JSONResponse(status_code=403, content={"detail": "Action réservée aux administrateurs"})
            elif _normalized_role(role) not in ("admin", "user"):
                return JSONResponse(status_code=403, content={"detail": "Modification non autorisée"})
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    try:
        await _ensure_financial_year_indexes(db)
        await _ensure_financial_period_indexes(db)
        await _ensure_account_indexes(db)
        await _ensure_membership_indexes(db)
        await _ensure_data_import_indexes(db)
        await _ensure_trial_balance_indexes(db)
        await _ensure_journal_indexes(db)
        await _ensure_financial_config_indexes(db)
        await _ensure_phase2_signoff_indexes(db)
        await _ensure_concept_indexes(db)
        await _ensure_i18n_indexes(db)
        await _ensure_mapping_indexes(db)
        await _ensure_reporting_template_indexes(db)
        await _ensure_custom_template_indexes(db)
        await _ensure_report_runs_indexes(db)
    except Exception as e:
        logger.error(f"Index financial_years échec : {e}")
    try:
        _qc_init_storage()
    except Exception as e:
        logger.error(f"Init stockage objet échec : {e}")
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({"email": admin_email, "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]),
                                   "name": "Administrateur", "role": "admin", "created_at": datetime.now(timezone.utc).isoformat()})
    elif not verify_password(os.environ["ADMIN_PASSWORD"], existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(os.environ["ADMIN_PASSWORD"])}})
    # Migration multi-années : renommer l'ancien doc "current" en clé annuelle.
    cur = await db.hypotheses.find_one({"key": "current"})
    if cur:
        y = int(cur.get("year", DEFAULT_YEAR))
        await db.hypotheses.update_one({"key": "current"}, {"$set": {"key": _hkey(y), "year": y}})
    if await db.hypotheses.count_documents({"key": _hkey(DEFAULT_YEAR)}) == 0:
        base = dict(DEFAULT_HYPOTHESES); base["key"] = _hkey(DEFAULT_YEAR); base["year"] = DEFAULT_YEAR
        await db.hypotheses.insert_one(base)
    await db.hypotheses.update_many({"prime_garde_nb_annuel": 365}, {"$set": {"prime_garde_nb_annuel": 2.08}})
    await db.hypotheses.update_many({"prime_garde_nb_annuel": 52}, {"$set": {"prime_garde_nb_annuel": 2.08}})
    await db.hypotheses.update_many({}, {"$unset": {"ccq_electricien_compagnon_rate": ""}})
    # Migration : renommer l'ancien scénario "revue" en "revue1".
    async for e in db.employees.find({}):
        yrs = e.get("years") or {}
        changed = False
        for ystr, yd in yrs.items():
            if isinstance(yd, dict) and "revue" in yd:
                yd["revue1"] = yd.pop("revue"); changed = True
        if changed:
            await db.employees.update_one({"_id": e["_id"]}, {"$set": {"years": yrs}})
    years = sorted({int(d["year"]) for d in await db.hypotheses.find().to_list(1000) if d.get("year")}) or [DEFAULT_YEAR]
    if await db.settings.count_documents({"key": "app"}) == 0:
        await db.settings.insert_one({"key": "app", "active_year": DEFAULT_YEAR, "years": years})
    if await db.departments.count_documents({}) == 0:
        await db.departments.insert_many([dict(d) for d in DEPARTMENTS_SEED])
    # Seed initial des employés : une seule fois. Après cela, si l'utilisateur vide
    # volontairement la liste, les fiches de démonstration ne réapparaissent PAS.
    app_settings = await db.settings.find_one({"key": "app"})
    already_seeded = bool(app_settings and app_settings.get("employees_seeded"))
    if not already_seeded:
        if await db.employees.count_documents({}) == 0:
            n = 1
            for e in EMPLOYEES_SEED:
                e = dict(e); e["employee_number"] = n; n += 1
                await db.employees.insert_one(e)
        await db.settings.update_one({"key": "app"}, {"$set": {"employees_seeded": True}}, upsert=True)
    # Seed des responsables budgétaires (RH, TI, MARKETING, FGF) — une seule fois.
    if not (app_settings and app_settings.get("budget_managers_seeded")):
        if await db.acct_budget_managers.count_documents({}) == 0:
            _cid = await _company_id("acct")
            await db.acct_budget_managers.insert_many([{**dict(m), "company_id": _cid} for m in BUDGET_MANAGERS_SEED])
        await db.settings.update_one({"key": "app"}, {"$set": {"budget_managers_seeded": True}}, upsert=True)
    # Seed des contacts externes (Banque Desjardins) — une seule fois.
    if not (app_settings and app_settings.get("external_contacts_seeded")):
        if await db.acct_external_contacts.count_documents({}) == 0:
            _cid = await _company_id("acct")
            await db.acct_external_contacts.insert_many([{**dict(c), "company_id": _cid} for c in EXTERNAL_CONTACTS_SEED])
        await db.settings.update_one({"key": "app"}, {"$set": {"external_contacts_seeded": True}}, upsert=True)

@app.on_event("shutdown")
async def shutdown():
    client.close()
