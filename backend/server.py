from dotenv import load_dotenv
from pathlib import Path
import os
import calendar

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
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
    """Retourne (fractions mensuelles [12], facteur annuel). Pro-rata au jour pour l'embauche en cours d'année."""
    frac = [1.0] * 12
    hd = e.get("hire_date")
    if hd and year:
        try:
            p = str(hd)[:10].split("-"); hy = int(p[0]); hm = int(p[1]); hday = int(p[2])
        except Exception:
            hy = None
        if hy is not None and 1 <= (hm if hy else 1) <= 12:
            if hy > int(year):
                frac = [0.0] * 12
            elif hy == int(year):
                dim = calendar.monthrange(int(year), hm)[1]
                first = max(0.0, min(1.0, (dim - hday + 1) / dim))
                frac = [0.0] * (hm - 1) + [round(first, 6)] + [1.0] * (12 - hm)
    return frac, sum(frac) / 12

def compute_budget(employees, hypo, depts, year=None, scenario="ca"):
    dept_csst = {d["code"]: d.get("csst", 0) for d in depts}
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
        ccq = e["is_ccq"]
        ydata, ov, base = _emp_scn(e, year, scenario)
        aug = 0 if is_actuel else ov.get("augmentation", aug_ccq if ccq else aug_autres)
        new_salary = base * (1 + aug)
        taux_horaire = new_salary / ANNUAL_HOURS

        prime_type = ov.get("prime_type", e.get("prime_type", "Aucune Prime"))
        boni = 0
        if is_actuel:
            # Salaires actuels : uniquement le salaire de base, sans prime ni charge.
            prime_type = "Aucune Prime"
            prime_amt = garde = halo = alloc = 0
        elif ccq:
            prime_amt = new_salary * PRIME_PCT.get(prime_type, 0.0)
            garde = garde_avg if ov.get("prime_garde", e.get("prime_garde")) else 0
            halo = new_salary * hypo["prime_halo_rate"] if ov.get("prime_halo", e.get("prime_halo")) else 0
            alloc = hypo["alloc_securite_montant"] if ov.get("alloc_securite", e.get("alloc_securite")) else 0
        else:
            # Employés non-CCQ : pas de prime CCQ ni HALO/garde. Boni + Alloc. sécurité + REER/assurance possibles.
            prime_type = "Aucune Prime"
            prime_amt = garde = halo = 0
            alloc = hypo["alloc_securite_montant"] if ov.get("alloc_securite", e.get("alloc_securite")) else 0
            boni_mode = ov.get("boni_mode", "montant")
            if boni_mode == "pct":
                boni = new_salary * float(ov.get("boni_pct", 0) or 0) / 100
            else:
                boni = float(ov.get("boni", 0) or 0)
        primes_total = prime_amt + garde + halo + alloc + boni

        vac_rate = ov.get("vacation_rate", e["vacation_rate"])
        vacation = 0 if is_actuel else vac_rate * (new_salary + primes_total)

        if is_actuel:
            rrq = ae = rqap = fss = csst = gov = ccq_av = avantages = reer = assurance = 0
            total = new_salary
        else:
            gross = new_salary + vacation + primes_total
            rrq = _capped(gross, charges["RRQ"]["rate"], charges["RRQ"]["ceiling"], charges["RRQ"]["exemption"])
            ae = _capped(gross, charges["AE"]["rate"], charges["AE"]["ceiling"])
            rqap = _capped(gross, charges["RQAP"]["rate"], charges["RQAP"]["ceiling"])
            fss = _capped(gross, charges["FSS"]["rate"], charges["FSS"]["ceiling"])
            csst = _capped(gross, dept_csst.get(e["department"], charges["CSST"]["rate"]), charges["CSST"]["ceiling"])
            gov = rrq + ae + rqap + fss
            if ccq:
                ccq_av = (new_salary + primes_total) * hypo["ccq_rate"]
                avantages = gov + ccq_av
                reer = 0
                assurance = 0
            else:
                ccq_av = 0
                avantages = gov
                reer = float(ov.get("reer", new_salary * hypo["reer_rate"]))
                assurance = float(ov.get("assurance", hypo["assurance_annuelle"]))
            total = new_salary + vacation + primes_total + avantages + csst + reer + assurance
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
            "name": e["name"], "title": e.get("title", ""), "department": e["department"],
            "department_label": dept_label.get(e["department"], e["department"]),
            "employment_type": e["employment_type"], "is_ccq": ccq, "overridden": bool(ov),
            "base_salary": round(base, 2), "augmentation": aug, "new_salary": round(new_salary, 2),
            "taux_horaire": round(taux_horaire, 2), "vacation_rate": vac_rate, "vacation": round(vacation, 2),
            "prime_type": prime_type, "prime_amount": round(prime_amt, 2), "garde": round(garde, 2),
            "halo": round(halo, 2), "alloc": round(alloc, 2),
            "boni": round(boni, 2), "primes_total": round(primes_total, 2),
            "salaire_brut": round(new_salary + vacation + primes_total, 2),
            "boni_mode": (ov.get("boni_mode", "montant") if not ccq else "montant"),
            "boni_pct": float(ov.get("boni_pct", 0) or 0),
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
        "garde_moyenne": round(garde_avg, 2),
    }
    return {"lines": lines, "totals": totals, "by_department": by_department, "by_type": by_type,
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

# ---------------------------------------------------------------------------
# Gestion des utilisateurs (admin uniquement)
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Literal["admin", "user"] = "user"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["admin", "user"]] = None
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
    employment_type: Literal["CCQ", "Régulier temps plein", "Stagiaire"]
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

async def _next_number():
    last = await db.employees.find_one(sort=[("employee_number", -1)])
    return (last["employee_number"] + 1) if last else 1

@api.get("/employees")
async def list_employees(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if q:
        query = {"$or": [{"name": {"$regex": q, "$options": "i"}}, {"department": {"$regex": q, "$options": "i"}},
                         {"title": {"$regex": q, "$options": "i"}}, {"employment_type": {"$regex": q, "$options": "i"}}]}
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
    employees = await db.employees.find().to_list(2000)
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

def _hkey(year):
    return f"y{int(year)}"

async def _get_hypo(year):
    doc = await db.hypotheses.find_one({"key": _hkey(year)})
    if not doc:
        base = dict(DEFAULT_HYPOTHESES); base["key"] = _hkey(year); base["year"] = int(year)
        _apply_working_days(base, year)
        await db.hypotheses.insert_one(base)
        doc = await db.hypotheses.find_one({"key": _hkey(year)})
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
    src = await _get_hypo(payload.source_year)
    newh = {k: v for k, v in src.items() if k != "_id"}
    newh["key"] = _hkey(ny); newh["year"] = ny
    _apply_working_days(newh, ny)
    await db.hypotheses.insert_one(newh)
    # Report : le scénario source de l'année précédente devient le salaire actuel de la nouvelle année.
    depts = await db.departments.find().to_list(1000)
    employees = await db.employees.find().to_list(1000)
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
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    return compute_budget(employees, hypo, depts, year=year, scenario=scenario)

@api.get("/budget/compare")
async def budget_compare(year: Optional[int] = None, department: Optional[str] = None, user: dict = Depends(get_current_user)):
    year = year or await _active_year()
    hypo = await _get_hypo(year)
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
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
    return {"success": True, "locked": payload.locked}

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
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    data = compute_budget(employees, hypo, depts, year=year, scenario=scenario)
    return data, hypo

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
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
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

# ---------------------------------------------------------------------------
# Excel import / templates
# ---------------------------------------------------------------------------
EMP_HEADERS = ["Matricule (# — laisser vide pour auto)", "Nom", "Département (code)", "Titre", "Type emploi (CCQ / Régulier temps plein / Stagiaire)",
               "Catégorie CCQ (Électricien / Frigoriste / N/A)", "Salaire annuel", "Taux vacances %",
               "Jours maladie", "Jours fériés", "Type prime (Aucune Prime / Prime 8% / Prime 11% / Prime 12%)",
               "Prime garde (Oui/Non)", "Prime HALO (Oui/Non)", "Alloc sécurité (Oui/Non)",
               "Date embauche (AAAA-MM-JJ)", "Date naissance (AAAA-MM-JJ)"]
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
          "Prime 8%", "Non", "Non", "Non", "2020-01-15", "1985-05-20"]
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
    valid_types = {"CCQ", "Régulier temps plein", "Stagiaire"}
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
            doc = {
                "name": str(name).strip(), "department": str(_cell(row, 2) or "").strip(),
                "title": str(_cell(row, 3) or "").strip(), "employment_type": etype, "ccq_category": cat,
                "current_annual_salary": float(_cell(row, 6) or 0),
                "vacation_rate": vac / 100 if vac > 1 else vac,
                "sick_personal_days": int(_cell(row, 8) or 0), "holiday_days": int(_cell(row, 9) or 0),
                "is_ccq": is_ccq, "prime_type": prime,
                "prime_garde": _b(_cell(row, 11)), "prime_halo": _b(_cell(row, 12)), "alloc_securite": _b(_cell(row, 13)),
                "hire_date": _date(_cell(row, 14)), "birth_date": _date(_cell(row, 15)),
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
async def get_journal(user: dict = Depends(get_current_user)):
    docs = await db.journal.find().sort("timestamp", -1).limit(300).to_list(300)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

@api.get("/")
async def root():
    return {"message": "API Budget Salaires Pro"}

app.include_router(api)
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
    if await db.employees.count_documents({}) == 0:
        n = 1
        for e in EMPLOYEES_SEED:
            e = dict(e); e["employee_number"] = n; n += 1
            await db.employees.insert_one(e)

@app.on_event("shutdown")
async def shutdown():
    client.close()
