from dotenv import load_dotenv
from pathlib import Path
import os

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
    "ccq_rate": 0.3233, "ccq_electricien_compagnon_rate": 0.05,
    "prime_garde_cout_unitaire": 250, "prime_garde_nb_annuel": 365,
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

def compute_budget(employees, hypo, depts):
    dept_csst = {d["code"]: d.get("csst", 0) for d in depts}
    dept_label = {d["code"]: d["description"] for d in depts}
    charges = {c["code"]: c for c in hypo["charges"]}
    aug_ccq = hypo["augmentation_ccq"]
    aug_autres = hypo["augmentation_autres"]

    eligible = [e for e in employees if e.get("prime_garde") and e.get("is_ccq")]
    garde_avg = (hypo["prime_garde_cout_unitaire"] * hypo["prime_garde_nb_annuel"] / len(eligible)) if eligible else 0

    lines = []
    tot = {"salaire_base": 0, "vacances": 0, "primes": 0, "avantages": 0,
           "csst": 0, "reer": 0, "assurance": 0, "budget_total": 0}
    for e in employees:
        ccq = e["is_ccq"]
        ov = (e.get("budget_overrides") or {}).get("budget", {}) or {}
        aug = ov.get("augmentation", aug_ccq if ccq else aug_autres)
        base = ov.get("base_salary", e["current_annual_salary"])
        new_salary = base * (1 + aug)
        taux_horaire = new_salary / ANNUAL_HOURS

        prime_type = ov.get("prime_type", e.get("prime_type", "Aucune Prime"))
        if ccq:
            prime_amt = new_salary * PRIME_PCT.get(prime_type, 0.0)
            garde = garde_avg if ov.get("prime_garde", e.get("prime_garde")) else 0
            halo = new_salary * hypo["prime_halo_rate"] if ov.get("prime_halo", e.get("prime_halo")) else 0
            alloc = hypo["alloc_securite_montant"] if ov.get("alloc_securite", e.get("alloc_securite")) else 0
            compagnon = new_salary * hypo["ccq_electricien_compagnon_rate"] if e.get("ccq_category") == "Électricien" else 0
            boni = 0
        else:
            # Employés non-CCQ : aucune prime. Seul le boni (+ REER/assurance) s'applique.
            prime_type = "Aucune Prime"
            prime_amt = garde = halo = alloc = compagnon = 0
            boni = float(ov.get("boni", 0) or 0)
        primes_total = prime_amt + garde + halo + alloc + compagnon + boni

        vac_rate = ov.get("vacation_rate", e["vacation_rate"])
        vacation = 0 if ccq else vac_rate * (new_salary + primes_total)

        gross = new_salary + vacation + primes_total
        rrq = _capped(gross, charges["RRQ"]["rate"], charges["RRQ"]["ceiling"], charges["RRQ"]["exemption"])
        ae = _capped(gross, charges["AE"]["rate"], charges["AE"]["ceiling"])
        rqap = _capped(gross, charges["RQAP"]["rate"], charges["RQAP"]["ceiling"])
        fss = _capped(gross, charges["FSS"]["rate"], charges["FSS"]["ceiling"])
        csst = _capped(gross, dept_csst.get(e["department"], charges["CSST"]["rate"]), charges["CSST"]["ceiling"])
        gov = rrq + ae + rqap + fss

        if ccq:
            ccq_av = new_salary * hypo["ccq_rate"]
            avantages = gov + ccq_av
            reer = 0
            assurance = 0
        else:
            ccq_av = 0
            avantages = gov
            reer = float(ov.get("reer", new_salary * hypo["reer_rate"]))
            assurance = float(ov.get("assurance", hypo["assurance_annuelle"]))

        total = new_salary + vacation + primes_total + avantages + csst + reer + assurance
        lines.append({
            "employee_id": str(e.get("_id", "")), "employee_number": e["employee_number"],
            "name": e["name"], "title": e.get("title", ""), "department": e["department"],
            "department_label": dept_label.get(e["department"], e["department"]),
            "employment_type": e["employment_type"], "is_ccq": ccq, "overridden": bool(ov),
            "base_salary": round(base, 2), "augmentation": aug, "new_salary": round(new_salary, 2),
            "taux_horaire": round(taux_horaire, 2), "vacation_rate": vac_rate, "vacation": round(vacation, 2),
            "prime_type": prime_type, "prime_amount": round(prime_amt, 2), "garde": round(garde, 2),
            "halo": round(halo, 2), "alloc": round(alloc, 2), "compagnon": round(compagnon, 2),
            "boni": round(boni, 2), "primes_total": round(primes_total, 2),
            "rrq": round(rrq, 2), "ae": round(ae, 2), "rqap": round(rqap, 2), "fss": round(fss, 2),
            "ccq_avantages": round(ccq_av, 2), "avantages": round(avantages, 2), "csst": round(csst, 2),
            "reer": round(reer, 2), "assurance": round(assurance, 2), "total_cost": round(total, 2),
        })
        tot["salaire_base"] += new_salary
        tot["vacances"] += vacation
        tot["primes"] += primes_total
        tot["avantages"] += avantages
        tot["csst"] += csst
        tot["reer"] += reer
        tot["assurance"] += assurance
        tot["budget_total"] += total

    totals = {k: round(v, 2) for k, v in tot.items()}
    # by department
    by_dept = {}
    for ln in lines:
        d = by_dept.setdefault(ln["department"], {"department": ln["department"], "label": ln["department_label"], "salaire": 0, "budget": 0})
        d["salaire"] += ln["new_salary"]
        d["budget"] += ln["total_cost"]
    by_department = sorted([{**v, "salaire": round(v["salaire"], 2), "budget": round(v["budget"], 2)} for v in by_dept.values()], key=lambda x: -x["budget"])
    # by type
    by_type_map = {}
    for ln in lines:
        by_type_map[ln["employment_type"]] = by_type_map.get(ln["employment_type"], 0) + ln["total_cost"]
    by_type = [{"type": k, "total": round(v, 2)} for k, v in by_type_map.items()]
    # monthly ventilation
    total_weeks = sum(hypo["pay_weeks"]) or 1
    sal_ratio = (totals["salaire_base"] + totals["vacances"] + totals["primes"]) / totals["budget_total"] if totals["budget_total"] else 0
    monthly = []
    for i, m in enumerate(MONTHS):
        w = hypo["pay_weeks"][i]
        mt = totals["budget_total"] * w / total_weeks
        sal = mt * sal_ratio
        monthly.append({"month": m, "sem_paie": w, "jours_std": hypo["working_days_std"][i],
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
    top5 = sorted(lines, key=lambda x: -x["total_cost"])[:5]
    top5 = [{"name": l["name"], "title": l["title"], "department": l["department"],
             "total": l["total_cost"], "base": l["base_salary"], "rank": i + 1} for i, l in enumerate(top5)]
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
    e = await db.employees.find_one({"_id": _oid(eid)})
    res = await db.employees.delete_one({"_id": _oid(eid)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    await log_action(user, "Supprimer", "Employé", e["name"] if e else eid)
    return {"success": True}

class OverridePayload(BaseModel):
    override: dict

@api.post("/employees/{eid}/budget-preview")
async def budget_preview(eid: str, payload: OverridePayload, user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"_id": _oid(eid)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    hypo = await db.hypotheses.find_one({"key": "current"})
    depts = await db.departments.find().to_list(1000)
    emp = dict(emp)
    emp["budget_overrides"] = {"budget": payload.override}
    return compute_budget([emp], hypo, depts)["lines"][0]

@api.put("/employees/{eid}/budget-override")
async def save_override(eid: str, payload: OverridePayload, user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"_id": _oid(eid)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    if payload.override:
        upd = {"$set": {"budget_overrides.budget": payload.override}}
    else:
        upd = {"$unset": {"budget_overrides.budget": ""}}
    await db.employees.update_one({"_id": _oid(eid)}, upd)
    await log_action(user, "Modifier", "Budget", f"Fiche — {emp['name']}")
    return {"success": True}

# ---------------------------------------------------------------------------
# Hypotheses & budget
# ---------------------------------------------------------------------------
@api.get("/hypotheses")
async def get_hypotheses(user: dict = Depends(get_current_user)):
    doc = await db.hypotheses.find_one({"key": "current"})
    if not doc:
        await db.hypotheses.insert_one(dict(DEFAULT_HYPOTHESES))
        doc = await db.hypotheses.find_one({"key": "current"})
    doc.pop("_id", None)
    return doc

@api.put("/hypotheses")
async def update_hypotheses(payload: dict, user: dict = Depends(get_current_user)):
    payload["key"] = "current"
    await db.hypotheses.update_one({"key": "current"}, {"$set": payload}, upsert=True)
    await log_action(user, "Modifier", "Hypothèses", f"Taux & paramètres {payload.get('year', '')}")
    doc = await db.hypotheses.find_one({"key": "current"})
    doc.pop("_id", None)
    return doc

@api.get("/budget")
async def get_budget(department: Optional[str] = None, user: dict = Depends(get_current_user)):
    hypo = await db.hypotheses.find_one({"key": "current"})
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    return compute_budget(employees, hypo, depts)

# ---------------------------------------------------------------------------
# Reports (Excel / PDF)
# ---------------------------------------------------------------------------
def _money(v):
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " $"

async def _budget_data(department=None):
    hypo = await db.hypotheses.find_one({"key": "current"})
    depts = await db.departments.find().to_list(1000)
    query = {"department": department} if department and department != "all" else {}
    employees = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    data = compute_budget(employees, hypo, depts)
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
            "Primes", "Avantages", "CSST", "REER", "Assurance", "Coût total"]
    ws2.append(cols); [setattr(c, "font", bold) for c in ws2[1]]
    for l in data["lines"]:
        ws2.append([l["employee_number"], l["name"], l["title"], l["department"], l["employment_type"],
                    l["base_salary"], l["new_salary"], l["vacation"], l["primes_total"], l["avantages"],
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

@api.get("/reports/excel")
async def report_excel(department: Optional[str] = None, user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department)
    dept_label = "Tous les départements" if not department or department == "all" else department
    buf = build_budget_excel(data, hypo["year"], dept_label)
    await log_action(user, "Modifier", "Rapport", f"Export Excel — {dept_label}")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=rapport_budget_{hypo['year']}.xlsx"})

@api.get("/reports/pdf")
async def report_pdf(department: Optional[str] = None, user: dict = Depends(get_current_user)):
    data, hypo = await _budget_data(department)
    dept_label = "Tous les départements" if not department or department == "all" else department
    buf = build_budget_pdf(data, hypo["year"], dept_label)
    await log_action(user, "Modifier", "Rapport", f"Export PDF — {dept_label}")
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=rapport_budget_{hypo['year']}.pdf"})

# ---------------------------------------------------------------------------
# Excel import / templates
# ---------------------------------------------------------------------------
EMP_HEADERS = ["Nom", "Département (code)", "Titre", "Type emploi (CCQ / Régulier temps plein / Stagiaire)",
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
    ex = ["Jean Exemple", "400", "Comptable", "Régulier temps plein", "N/A", 80000, 8, 8, 14,
          "Prime 8%", "Non", "Non", "Non", "2020-01-15", "1985-05-20"]
    return _xlsx_response(EMP_HEADERS, ex, "Employés", "modele_employes.xlsx")

@api.get("/departments/template")
async def dep_template(user: dict = Depends(get_current_user)):
    ex = ["999", "Nouveau département", "Superviseur", "5006000", "Services", 0.61]
    return _xlsx_response(DEP_HEADERS, ex, "Départements", "modele_departements.xlsx")

@api.post("/employees/import")
async def import_employees(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsx) invalide")
    ws = wb.active
    valid_types = {"CCQ", "Régulier temps plein", "Stagiaire"}
    valid_primes = {"Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"}
    dept_codes = {d["code"] for d in await db.departments.find().to_list(1000)}
    inserted, errors = 0, []
    n = await _next_number()
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(c is None for c in row):
            continue
        name = _cell(row, 0)
        if not name:
            continue
        try:
            etype = str(_cell(row, 3) or "Régulier temps plein").strip()
            if etype not in valid_types:
                raise ValueError(f"Type emploi invalide '{etype}'")
            cat = str(_cell(row, 4) or "N/A").strip() or "N/A"
            is_ccq = etype == "CCQ"
            if is_ccq and cat not in ("Électricien", "Frigoriste"):
                raise ValueError("Catégorie CCQ requise (Électricien/Frigoriste)")
            if not is_ccq:
                cat = "N/A"
            prime = str(_cell(row, 9) or "Aucune Prime").strip()
            if prime not in valid_primes:
                prime = "Aucune Prime"
            vac = float(_cell(row, 6) or 0)
            doc = {
                "name": str(name).strip(), "department": str(_cell(row, 1) or "").strip(),
                "title": str(_cell(row, 2) or "").strip(), "employment_type": etype, "ccq_category": cat,
                "current_annual_salary": float(_cell(row, 5) or 0),
                "vacation_rate": vac / 100 if vac > 1 else vac,
                "sick_personal_days": int(_cell(row, 7) or 0), "holiday_days": int(_cell(row, 8) or 0),
                "is_ccq": is_ccq, "prime_type": prime,
                "prime_garde": _b(_cell(row, 10)), "prime_halo": _b(_cell(row, 11)), "alloc_securite": _b(_cell(row, 12)),
                "hire_date": _date(_cell(row, 13)), "birth_date": _date(_cell(row, 14)),
                "employee_number": n,
            }
            if not doc["department"]:
                raise ValueError("Département requis")
            if doc["department"] not in dept_codes:
                raise ValueError(f"Département '{doc['department']}' inexistant")
            await db.employees.insert_one(doc)
            n += 1
            inserted += 1
        except Exception as ex:
            errors.append(f"Ligne {idx}: {ex}")
    await log_action(user, "Créer", "Employé", f"Import Excel — {inserted} employé(s)")
    return {"inserted": inserted, "errors": errors}

@api.post("/departments/import")
async def import_departments(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsx) invalide")
    ws = wb.active
    inserted, errors = 0, []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(c is None for c in row):
            continue
        code = _cell(row, 0)
        if not code:
            continue
        try:
            code = str(code).strip()
            if await db.departments.find_one({"code": code}):
                raise ValueError(f"Code '{code}' existe déjà")
            csst = float(_cell(row, 5) or 0)
            doc = {"code": code, "description": str(_cell(row, 1) or "").strip(),
                   "superviseur": str(_cell(row, 2) or "").strip(), "compte_gl": str(_cell(row, 3) or "").strip(),
                   "groupe_pl": str(_cell(row, 4) or "Services").strip(), "csst": csst / 100 if csst > 1 else csst}
            await db.departments.insert_one(doc)
            inserted += 1
        except Exception as ex:
            errors.append(f"Ligne {idx}: {ex}")
    await log_action(user, "Créer", "Département", f"Import Excel — {inserted} département(s)")
    return {"inserted": inserted, "errors": errors}

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
    if await db.hypotheses.count_documents({"key": "current"}) == 0:
        await db.hypotheses.insert_one(dict(DEFAULT_HYPOTHESES))
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
