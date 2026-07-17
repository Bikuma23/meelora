from dotenv import load_dotenv
from pathlib import Path
import os
import calendar

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, UploadFile, File
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
import openpyxl
from accounting import ReportEngine

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        user["id"] = str(user.pop("_id"))
        user.pop("password_hash", None)
        return user
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

async def log_action(user, action, entity, label, details=""):
    await db.journal.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_email": user.get("email", "système"),
        "user_name": user.get("name", ""),
        "action": action, "entity": entity, "label": label, "details": details,
    })

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
        {"label": "Vacances", "value": totals["vacances"], "pct": round(totals["vacances"] / bt * 100, 1), "color": "#14B8A6"},
        {"label": "Primes & Boni", "value": totals["primes"], "pct": round(totals["primes"] / bt * 100, 1), "color": "#F59E0B"},
        {"label": "Avantages soc.", "value": totals["avantages"], "pct": round(totals["avantages"] / bt * 100, 1), "color": "#8B5CF6"},
        {"label": "CSST", "value": totals["csst"], "pct": round(totals["csst"] / bt * 100, 1), "color": "#EF4444"},
        {"label": "RPDB (REER)", "value": totals["reer"], "pct": round(totals["reer"] / bt * 100, 1), "color": "#14B8A6"},
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

@api.post("/auth/login")
async def login(payload: LoginPayload, response: Response):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Courriel ou mot de passe invalide")
    uid = str(user["_id"])
    token = create_token(uid, email)
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"token": token, "user": {"id": uid, "email": email, "name": user.get("name", ""), "role": user.get("role", "user")}}

@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"success": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", ""), "role": user.get("role", "user")}

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


# ---------------------------------------------------------------------------
# Gestion des utilisateurs (admin uniquement)
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Literal["admin", "editor", "user"] = "user"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["admin", "editor", "user"]] = None
    password: Optional[str] = None

def _user_public(u):
    return {"id": str(u["_id"]), "email": u["email"], "name": u.get("name", ""), "role": u.get("role", "user"),
            "created_at": u.get("created_at", "")}

@api.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    docs = await db.users.find().sort("email", 1).to_list(1000)
    return [_user_public(u) for u in docs]

@api.post("/users")
async def create_user(payload: UserCreate, user: dict = Depends(require_admin)):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ce courriel existe déjà")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
    doc = {"email": email, "name": payload.name.strip(), "password_hash": hash_password(payload.password),
           "role": payload.role, "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    await log_action(user, "Créer", "Utilisateur", f"{payload.name} ({email}) — {payload.role}")
    u = await db.users.find_one({"_id": res.inserted_id})
    return _user_public(u)

@api.put("/users/{uid}")
async def update_user(uid: str, payload: UserUpdate, user: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": _oid(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    upd = {}
    if payload.name is not None:
        upd["name"] = payload.name.strip()
    if payload.password:
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
        upd["password_hash"] = hash_password(payload.password)
    if payload.role is not None and payload.role != target.get("role"):
        if target.get("role") == "admin" and payload.role != "admin":
            admins = await db.users.count_documents({"role": "admin"})
            if admins <= 1:
                raise HTTPException(status_code=400, detail="Impossible de rétrograder le dernier administrateur")
        upd["role"] = payload.role
    if upd:
        await db.users.update_one({"_id": _oid(uid)}, {"$set": upd})
    await log_action(user, "Modifier", "Utilisateur", f"{target.get('name')} ({target['email']})")
    u = await db.users.find_one({"_id": _oid(uid)})
    return _user_public(u)

@api.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(require_admin)):
    target = await db.users.find_one({"_id": _oid(uid)})
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if str(target["_id"]) == user["id"]:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    if target.get("role") == "admin" and await db.users.count_documents({"role": "admin"}) <= 1:
        raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur")
    await db.users.delete_one({"_id": _oid(uid)})
    await log_action(user, "Supprimer", "Utilisateur", f"{target.get('name')} ({target['email']})")
    return {"success": True}

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
    res = await db.employees.update_one({"_id": _oid(eid)}, {"$set": payload.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    await log_action(user, "Modifier", "Employé", payload.name)
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
    payload["key"] = _hkey(year); payload["year"] = int(year)
    await db.hypotheses.update_one({"key": _hkey(year)}, {"$set": payload}, upsert=True)
    await log_action(user, "Modifier", "Hypothèses", f"Taux & paramètres {year}")
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
    emps = await db.employees.find(_active_q()).sort("employee_number", 1).to_list(2000)
    out = [{"id": str(e["_id"]), "employee_number": e["employee_number"], "name": e["name"],
            "department": e.get("department", "")} for e in emps if not _has_scenario_entry(e, year, scenario)]
    return {"year": year, "scenario": scenario, "employees": out, "count": len(out)}

@api.post("/budget/inactivate-no-entry")
async def inactivate_no_entry(year: Optional[int] = None, scenario: str = "ca", user: dict = Depends(get_current_user)):
    """Inactive tous les employés actifs sans budget saisi pour l'année + scénario donnés."""
    year = year or await _active_year()
    emps = await db.employees.find(_active_q()).to_list(2000)
    ids = [e["_id"] for e in emps if not _has_scenario_entry(e, year, scenario)]
    for _id in ids:
        await db.employees.update_one({"_id": _id}, {"$set": {"active": False}})
    await log_action(user, "Modifier", "Employé", f"Inactivation auto — {len(ids)} employé(s) sans budget {SCEN_LABEL.get(scenario, scenario)} {year}")
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
    ws.append([f"Comparatif des scénarios — {year}"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
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
    ws.append([f"État des résultats (P&L) — {scenario_label} {year}"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
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
    ws.append([f"Rapport budgétaire {year} — {dept_label}"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
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
    NAVY = colors.HexColor("#0E1526"); TEAL = colors.HexColor("#14B8A6")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=18)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=10)
    el = [Paragraph(f"Rapport budgétaire {year}", h),
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
    NAVY = colors.HexColor("#0E1526"); TEAL = colors.HexColor("#14B8A6")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=17)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=11, spaceBefore=10)
    ccq = ln["is_ccq"]
    el = [Paragraph(f"{ln['name']} — #{str(ln['employee_number']).zfill(3)}", h),
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
           block("Primes & rémunération additionnelle", primes, colors.HexColor("#F59E0B")), Spacer(1, 6),
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
    ws.append([f"Fiches détaillées {scenario_label} {year} — {scope}"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
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
    NAVY = colors.HexColor("#0E1526"); TEAL = colors.HexColor("#14B8A6")
    h = ParagraphStyle("h", parent=styles["Title"], textColor=NAVY, fontSize=16)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#64748B"), fontSize=9)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], textColor=NAVY, fontSize=11, spaceBefore=8)
    el = [Paragraph(f"Fiches détaillées — {scenario_label} {year}", h),
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
    ws.append([f"Masse salariale par classe de sécurité — {SCEN_LABEL.get(scenario, scenario)} {y}  (max assurable {bc['csst_max_assurable']} $)"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=13)
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
    ws.append([f"Rapport personnalisé — {SCEN_LABEL.get(scenario, scenario)} {y}"]); ws["A1"].font = openpyxl.styles.Font(bold=True, size=13)
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

@api.get("/journal")
async def get_journal(user: dict = Depends(require_admin)):
    docs = await db.journal.find().sort("timestamp", -1).limit(300).to_list(300)
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
    periods = await db.acct_periods.find().sort("_id", 1).to_list(500)
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
        txns.append({"account": acct, "date": date_s, "description": desc,
                     "debit": round(dbt, 2), "credit": round(crd, 2), "amount": round(dbt - crd, 2)})
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
    docs = await db.acct_periods.find().sort("_id", -1).to_list(500)
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

@api.get("/acct/ledger/transactions")
async def acct_ledger_transactions(year: int, month: int, q: str = "", skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    pk = _pkey(year, month)
    doc = await db.acct_ledger.find_one({"_id": pk})
    if not doc:
        raise HTTPException(status_code=404, detail="Aucun grand livre détaillé pour ce mois")
    txns = doc.get("transactions", [])
    ql = (q or "").strip().lower()
    if ql:
        txns = [t for t in txns if ql in str(t.get("account", "")).lower() or ql in (t.get("description") or "").lower()]
    total = len(txns)
    page = txns[skip:skip + min(limit, 500)]
    return {"period": pk, "total": total, "skip": skip, "limit": limit, "transactions": page,
            "account_count": len(doc.get("account_totals", {})), "grand_total": len(doc.get("transactions", []))}

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

@api.get("/acct/dashboard")
async def acct_dashboard(user: dict = Depends(get_current_user)):
    tmpl = await db.acct_template.find_one({"_id": "current"})
    periods = await db.acct_periods.find().sort("_id", -1).to_list(500)
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
    periods = await db.acct_periods.find({"locked": True}).sort("_id", 1).to_list(500)
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


def _acct_excel(rep):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.title = "Bilan" if rep["kind"] == "bilan" else "Résultats"
    from openpyxl.styles import Font, PatternFill, Alignment
    bold = Font(bold=True); title_f = Font(bold=True, size=14)
    fill = PatternFill("solid", fgColor="E2E8F0")
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
    ws.append([("BILAN" if rep["kind"] == "bilan" else "ÉTAT DES RÉSULTATS") + f" — {rep['month_label']} {rep['year']}"])
    ws["A1"].font = title_f
    if not rep["locked"]:
        ws.append(["** DONNÉES PROVISOIRES (mois non verrouillé) **"])
        ws[f"A{ws.max_row}"].font = Font(bold=True, color="B45309")
    ws.append([])
    header = ["Compte", "Description"] + [col_labels.get(k, k) for k in cols]
    ws.append(header)
    for c in ws[ws.max_row]:
        c.font = bold; c.fill = fill
    for ln in rep["lines"]:
        row = [ln["account"] or "", ln["label"] or ""] + [ln["values"][k] for k in cols]
        ws.append(row)
        cells = ws[ws.max_row]
        if ln["kind"] in ("total", "header"):
            for c in cells:
                c.font = bold
            if ln["kind"] == "total":
                for c in cells:
                    c.fill = fill
        for i in range(len(cols)):
            cell = cells[2 + i]
            cell.number_format = '#,##0.00;[Red](#,##0.00)'
            cell.alignment = Alignment(horizontal="right")
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 52
    for i in range(len(cols)):
        ws.column_dimensions[openpyxl.utils.get_column_letter(3 + i)].width = 18
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf

@api.get("/acct/report/excel")
async def acct_report_excel(type: str, year: int, month: int, user: dict = Depends(get_current_user)):
    if type == "bilan_sommaire":
        rep = await _bilan_sommaire_data(year, month)
        buf = _bilan_sommaire_excel(rep)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename=bilan_sommaire_{_pkey(year, month)}.xlsx"})
    if type not in ("bilan", "pnl", "pnl_sommaire"):
        raise HTTPException(status_code=400, detail="Type invalide")
    rep = await _acct_report(year, month, type)
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

import acct_ai
acct_ai.init(
    db=db, log_action=log_action, _acct_report=_acct_report, _kpi_data=_kpi_data,
    _bilan_sommaire_data=_bilan_sommaire_data, _pnl_figures=_pnl_figures,
    _pkey=_pkey, _add_months=_add_months, MONTHS_FR=MONTHS_FR, get_current_user=get_current_user,
)
api.include_router(acct_ai.router)

app.include_router(api)

WRITE_ALLOW_ALL = {"/api/auth/login", "/api/auth/logout", "/api/me/preferences", "/api/acct/bv", "/api/acct/account-map"}

def _is_admin_only_path(path: str) -> bool:
    return (path.startswith("/api/users")
            or path == "/api/hypotheses"
            or path == "/api/budget/lock"
            or path.startswith("/api/years"))

@app.middleware("http")
async def write_guard(request: Request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and path.startswith("/api") and path not in WRITE_ALLOW_ALL:
        token = request.cookies.get("access_token")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
                u = await db.users.find_one({"_id": ObjectId(payload["sub"])})
                role = (u or {}).get("role")
                if u:
                    if _is_admin_only_path(path):
                        if role != "admin":
                            return JSONResponse(status_code=403, content={"detail": "Action réservée aux administrateurs"})
                    elif role not in ("admin", "editor"):
                        return JSONResponse(status_code=403, content={"detail": "Modification réservée aux administrateurs et éditeurs"})
            except Exception:
                pass
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

@app.on_event("shutdown")
async def shutdown():
    client.close()
