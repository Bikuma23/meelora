from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing import List, Optional, Annotated, Literal
from bson import ObjectId
from datetime import datetime, date

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Budget Masse Salariale")
api_router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Départements + taux CSST (source: Taux et hypothèses 2026)
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    {"code": "100-Entr. Contrôles", "csst": 0.023032685},
    {"code": "110-Optimisation", "csst": 0.023032685},
    {"code": "120-Frigoristes", "csst": 0.036299185},
    {"code": "150-Télégestion", "csst": 0.006092385},
    {"code": "810-Électriciens", "csst": 0.030788485},
    {"code": "20-Mise en service", "csst": 0.023032685},
    {"code": "30-Ingénierie", "csst": 0.006092385},
    {"code": "40-Charge de projets", "csst": 0.006092385},
    {"code": "50-Programmation", "csst": 0.006092385},
    {"code": "400-Administration", "csst": 0.006092385},
    {"code": "401-Ressources Humaines", "csst": 0.006092385},
    {"code": "402-Opérations FGF", "csst": 0.006092385},
    {"code": "403-Marketing", "csst": 0.006092385},
    {"code": "404-Gestion de Service", "csst": 0.02438995},
    {"code": "405-TI", "csst": 0.006092385},
    {"code": "406-Ventes/Estimation", "csst": 0.006092385},
    {"code": "409-Opérations FGF Entrepot", "csst": 0.006092385},
    {"code": "200-Programmation GD", "csst": 0.006092385},
]

DEFAULT_HYPOTHESES = {
    "key": "current",
    "year": 2026,
    # Charges sociales part employeur
    "rrq_rate": 0.064, "rrq_ceiling": 103000, "rrq_exemption": 3500,
    "ae_rate": 0.0163, "ae_ceiling": 65700,
    "rqap_rate": 0.00636, "rqap_ceiling": 98000,
    "fss_rate": 0.0426,
    # Assurance & REER (non-CCQ uniquement)
    "assurance_annuelle": 3600,
    "reer_rate": 0.05,
    # CCQ
    "ccq_rate": 0.3233,
    "ccq_electricien_compagnon_rate": 0.05,
    # Primes & allocations
    "prime_garde_cout_unitaire": 250,
    "prime_garde_nb_annuel": 365,
    "prime_halo_rate": 0.05,
    "prime_chef_equipe_montant": 5000,
    "alloc_securite_montant": 2000,
    # Départements / CSST
    "departments": DEPARTMENTS,
}

SEED_EMPLOYEES = [
    {"name": "Jean Tremblay", "department": "810-Électriciens", "title": "Électricien compagnon", "employment_type": "CCQ", "ccq_category": "Électricien", "current_annual_salary": 92000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 12%", "prime_garde": True, "prime_chef_equipe": True, "prime_halo": False, "alloc_securite": True, "hire_date": "2016-04-11", "birth_date": "1985-06-23"},
    {"name": "Sophie Roy", "department": "810-Électriciens", "title": "Électricienne", "employment_type": "CCQ", "ccq_category": "Électricien", "current_annual_salary": 88000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 11%", "prime_garde": False, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": True, "hire_date": "2019-09-02", "birth_date": "1990-02-14"},
    {"name": "Éric Fortin", "department": "120-Frigoristes", "title": "Frigoriste", "employment_type": "CCQ", "ccq_category": "Frigoriste", "current_annual_salary": 95000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 12%", "prime_garde": True, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": True, "hire_date": "2014-07-21", "birth_date": "1982-11-30"},
    {"name": "Nadia Côté", "department": "120-Frigoristes", "title": "Frigoriste", "employment_type": "CCQ", "ccq_category": "Frigoriste", "current_annual_salary": 90000, "vacation_rate": 0.13, "sick_personal_days": 8, "holiday_days": 16, "is_ccq": True, "prime_type": "Prime 11%", "prime_garde": True, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": True, "hire_date": "2021-03-15", "birth_date": "1993-08-05"},
    {"name": "Isabelle Caron", "department": "400-Administration", "title": "Adjointe administrative", "employment_type": "Régulier", "ccq_category": "N/A", "current_annual_salary": 62000, "vacation_rate": 0.08, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": False, "hire_date": "2018-01-08", "birth_date": "1988-04-19"},
    {"name": "Martin Bélanger", "department": "30-Ingénierie", "title": "Ingénieur", "employment_type": "Régulier", "ccq_category": "N/A", "current_annual_salary": 105000, "vacation_rate": 0.10, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_chef_equipe": True, "prime_halo": True, "alloc_securite": False, "hire_date": "2012-06-04", "birth_date": "1980-12-11"},
    {"name": "Julie Morin", "department": "401-Ressources Humaines", "title": "Conseillère RH", "employment_type": "Régulier", "ccq_category": "N/A", "current_annual_salary": 72000, "vacation_rate": 0.08, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": False, "hire_date": "2020-11-23", "birth_date": "1991-07-27"},
    {"name": "Alain Girard", "department": "406-Ventes/Estimation", "title": "Estimateur", "employment_type": "Régulier", "ccq_category": "N/A", "current_annual_salary": 84000, "vacation_rate": 0.08, "sick_personal_days": 10, "holiday_days": 14, "is_ccq": False, "prime_type": "Prime 8%", "prime_garde": False, "prime_chef_equipe": False, "prime_halo": False, "alloc_securite": False, "hire_date": "2017-02-13", "birth_date": "1984-03-08"},
]


# ---------------------------------------------------------------------------
# Mongo helpers
# ---------------------------------------------------------------------------
def _oid(v):
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=404, detail="Introuvable")


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v))]


class EmployeeBase(BaseModel):
    name: str
    department: str
    title: str
    employment_type: Literal["CCQ", "Régulier"]
    ccq_category: Literal["Électricien", "Frigoriste", "N/A"]
    current_annual_salary: float
    vacation_rate: float
    sick_personal_days: int
    holiday_days: int
    is_ccq: bool
    prime_type: Literal["Prime 8%", "Prime 11%", "Prime 12%"]
    prime_garde: bool
    prime_chef_equipe: bool
    prime_halo: bool
    alloc_securite: bool
    hire_date: str
    birth_date: str


class Employee(EmployeeBase):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    employee_number: int


# ---------------------------------------------------------------------------
# Budget engine
# ---------------------------------------------------------------------------
PRIME_PCT = {"Prime 8%": 0.08, "Prime 11%": 0.11, "Prime 12%": 0.12}


def _capped(salary, rate, ceiling, exemption=0):
    base = max(0.0, min(salary, ceiling) - exemption)
    return base * rate


def compute_section(employees, hypo, aug_reg, aug_ccq, garde_avg):
    dept_csst = {d["code"]: d["csst"] for d in hypo.get("departments", [])}
    lines = []
    tot = {"salaire_base": 0, "vacances": 0, "primes": 0, "avantages": 0,
           "csst": 0, "reer": 0, "assurance": 0, "budget_total": 0}
    for e in employees:
        ccq = e["is_ccq"]
        aug = aug_ccq if ccq else aug_reg
        base = e["current_annual_salary"]
        new_salary = base * (1 + aug)

        vacation = 0 if ccq else new_salary * e["vacation_rate"]

        prime_amt = new_salary * PRIME_PCT[e["prime_type"]]
        garde = garde_avg if e["prime_garde"] else 0
        halo = new_salary * hypo["prime_halo_rate"] if e["prime_halo"] else 0
        chef = hypo["prime_chef_equipe_montant"] if e["prime_chef_equipe"] else 0
        alloc = hypo["alloc_securite_montant"] if e["alloc_securite"] else 0
        compagnon = new_salary * hypo["ccq_electricien_compagnon_rate"] if (ccq and e["ccq_category"] == "Électricien") else 0
        primes_total = prime_amt + garde + halo + chef + alloc + compagnon

        rrq = _capped(new_salary, hypo["rrq_rate"], hypo["rrq_ceiling"], hypo["rrq_exemption"])
        ae = _capped(new_salary, hypo["ae_rate"], hypo["ae_ceiling"])
        rqap = _capped(new_salary, hypo["rqap_rate"], hypo["rqap_ceiling"])
        fss = new_salary * hypo["fss_rate"]
        gov = rrq + ae + rqap + fss

        if ccq:
            avantages = gov + new_salary * hypo["ccq_rate"]
            reer = 0
            assurance = 0
        else:
            avantages = gov
            reer = new_salary * hypo["reer_rate"]
            assurance = hypo["assurance_annuelle"]

        csst = new_salary * dept_csst.get(e["department"], 0)
        total = new_salary + vacation + primes_total + avantages + csst + reer + assurance

        lines.append({
            "employee_number": e["employee_number"], "name": e["name"],
            "department": e["department"], "employment_type": e["employment_type"],
            "is_ccq": ccq, "base_salary": round(base), "augmentation": aug,
            "new_salary": round(new_salary), "vacation": round(vacation),
            "primes_total": round(primes_total), "avantages": round(avantages),
            "csst": round(csst), "reer": round(reer), "assurance": round(assurance),
            "total_cost": round(total),
        })
        tot["salaire_base"] += new_salary
        tot["vacances"] += vacation
        tot["primes"] += primes_total
        tot["avantages"] += avantages
        tot["csst"] += csst
        tot["reer"] += reer
        tot["assurance"] += assurance
        tot["budget_total"] += total
    return {"lines": lines, "totals": {k: round(v) for k, v in tot.items()}}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "API Budget Masse Salariale"}


async def _next_number():
    last = await db.employees.find_one(sort=[("employee_number", -1)])
    return (last["employee_number"] + 1) if last else 1


@api_router.get("/employees")
async def list_employees(q: Optional[str] = None):
    query = {}
    if q:
        query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"department": {"$regex": q, "$options": "i"}},
            {"title": {"$regex": q, "$options": "i"}},
            {"employment_type": {"$regex": q, "$options": "i"}},
        ]}
    docs = await db.employees.find(query).sort("employee_number", 1).to_list(1000)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@api_router.post("/employees")
async def create_employee(payload: EmployeeBase):
    doc = payload.model_dump()
    doc["employee_number"] = await _next_number()
    res = await db.employees.insert_one(doc)
    created = await db.employees.find_one({"_id": res.inserted_id})
    created["id"] = str(created.pop("_id"))
    return created


@api_router.put("/employees/{employee_id}")
async def update_employee(employee_id: str, payload: EmployeeBase):
    oid = _oid(employee_id)
    res = await db.employees.update_one({"_id": oid}, {"$set": payload.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    updated = await db.employees.find_one({"_id": oid})
    updated["id"] = str(updated.pop("_id"))
    return updated


@api_router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str):
    res = await db.employees.delete_one({"_id": _oid(employee_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    return {"success": True}


@api_router.get("/hypotheses")
async def get_hypotheses():
    doc = await db.hypotheses.find_one({"key": "current"})
    if not doc:
        await db.hypotheses.insert_one(dict(DEFAULT_HYPOTHESES))
        doc = await db.hypotheses.find_one({"key": "current"})
    doc.pop("_id", None)
    return doc


@api_router.put("/hypotheses")
async def update_hypotheses(payload: dict):
    payload["key"] = "current"
    await db.hypotheses.update_one({"key": "current"}, {"$set": payload}, upsert=True)
    doc = await db.hypotheses.find_one({"key": "current"})
    doc.pop("_id", None)
    return doc


@api_router.get("/budget")
async def get_budget(
    aug_reg_ca: float = Query(0.05),
    aug_reg_revue: float = Query(0.035),
    aug_ccq: float = Query(0.033333),
):
    hypo = await db.hypotheses.find_one({"key": "current"})
    if not hypo:
        await db.hypotheses.insert_one(dict(DEFAULT_HYPOTHESES))
        hypo = await db.hypotheses.find_one({"key": "current"})
    employees = await db.employees.find().sort("employee_number", 1).to_list(1000)

    eligible = [e for e in employees if e.get("prime_garde")]
    garde_total = hypo["prime_garde_cout_unitaire"] * hypo["prime_garde_nb_annuel"]
    garde_avg = (garde_total / len(eligible)) if eligible else 0

    sections = [
        {"key": "actuel", "label": "Salaire Actuel", "augmentation": {"regulier": 0, "ccq": 0},
         **compute_section(employees, hypo, 0, 0, garde_avg)},
        {"key": "ca", "label": "Budget (CA)", "augmentation": {"regulier": aug_reg_ca, "ccq": aug_ccq},
         **compute_section(employees, hypo, aug_reg_ca, aug_ccq, garde_avg)},
        {"key": "revue", "label": "Budget (Revue)", "augmentation": {"regulier": aug_reg_revue, "ccq": aug_ccq},
         **compute_section(employees, hypo, aug_reg_revue, aug_ccq, garde_avg)},
    ]

    # Dashboard aggregates (based on Budget CA)
    ca = sections[1]
    by_dept = {}
    by_type = {"CCQ": 0, "Régulier": 0}
    for ln in ca["lines"]:
        by_dept[ln["department"]] = by_dept.get(ln["department"], 0) + ln["total_cost"]
        by_type[ln["employment_type"]] += ln["total_cost"]
    dashboard = {
        "headcount": len(employees),
        "ccq_count": sum(1 for e in employees if e.get("is_ccq")),
        "regulier_count": sum(1 for e in employees if not e.get("is_ccq")),
        "by_department": [{"department": k, "total": round(v)} for k, v in sorted(by_dept.items(), key=lambda x: -x[1])],
        "by_type": [{"type": k, "total": round(v)} for k, v in by_type.items()],
        "section_totals": [{"section": s["label"], "total": s["totals"]["budget_total"]} for s in sections],
        "garde_moyenne": round(garde_avg),
    }
    return {"sections": sections, "dashboard": dashboard}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def seed_data():
    if await db.hypotheses.count_documents({"key": "current"}) == 0:
        await db.hypotheses.insert_one(dict(DEFAULT_HYPOTHESES))
    if await db.employees.count_documents({}) == 0:
        n = 1
        for e in SEED_EMPLOYEES:
            e = dict(e)
            e["employee_number"] = n
            n += 1
            await db.employees.insert_one(e)
        logger.info("Seeded %d employees", len(SEED_EMPLOYEES))


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
