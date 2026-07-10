from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing import List, Optional, Annotated, Literal
from bson import ObjectId
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Masse Salariale CCQ")
api_router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Business configuration
# ---------------------------------------------------------------------------
EMPLOYER_TAX_RATE = 0.1477   # Charges sociales employeur standard (CNESST, RRQ, RQAP, AE, FSS)
TREASURY_BUDGET = 2_500_000  # Budget de trésorerie annuel fixe (CAD)

CCQ_RATES = [
    {"trade": "Électricien", "hourly_benefits_charge": 11.85},
    {"trade": "Frigoriste", "hourly_benefits_charge": 12.40},
]

SCENARIOS = [
    {
        "name": "Budget Initial",
        "description": "Salaires de référence, semaine standard de 40 heures.",
        "base_weekly_hours": 40,
        "overtime_multiplier": 1.0,
        "extra_ccq_hires": 0,
        "hiring_frozen": False,
    },
    {
        "name": "Scénario Croissance",
        "description": "Heures supplémentaires CCQ x1.5 et +3 embauches CCQ par métier.",
        "base_weekly_hours": 40,
        "overtime_multiplier": 1.5,
        "extra_ccq_hires": 3,
        "hiring_frozen": False,
    },
    {
        "name": "Scénario Restrictif",
        "description": "Gel des embauches, réduction des heures standard à 35 h/semaine.",
        "base_weekly_hours": 35,
        "overtime_multiplier": 1.0,
        "extra_ccq_hires": 0,
        "hiring_frozen": True,
    },
]

SEED_EMPLOYEES = [
    {"name": "Jean Tremblay", "type": "CCQ", "trade": "Électricien", "base_hourly_rate": 49.5, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Luc Gagnon", "type": "CCQ", "trade": "Électricien", "base_hourly_rate": 52.0, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Marc Bergeron", "type": "CCQ", "trade": "Électricien", "base_hourly_rate": 46.75, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Sophie Roy", "type": "CCQ", "trade": "Électricien", "base_hourly_rate": 50.25, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Éric Fortin", "type": "CCQ", "trade": "Frigoriste", "base_hourly_rate": 51.0, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Nadia Côté", "type": "CCQ", "trade": "Frigoriste", "base_hourly_rate": 53.5, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Pierre Lavoie", "type": "CCQ", "trade": "Frigoriste", "base_hourly_rate": 48.9, "base_monthly_salary": 0, "active_hours_per_week": 40},
    {"name": "Isabelle Caron", "type": "Standard", "trade": "Admin", "base_hourly_rate": 32.0, "base_monthly_salary": 5400, "active_hours_per_week": 40},
    {"name": "Martin Bélanger", "type": "Standard", "trade": "Admin", "base_hourly_rate": 40.0, "base_monthly_salary": 6800, "active_hours_per_week": 40},
    {"name": "Julie Morin", "type": "Standard", "trade": "Admin", "base_hourly_rate": 28.5, "base_monthly_salary": 4700, "active_hours_per_week": 40},
    {"name": "Alain Girard", "type": "Standard", "trade": "Admin", "base_hourly_rate": 35.0, "base_monthly_salary": 5900, "active_hours_per_week": 40},
    {"name": "Chantal Dubé", "type": "Standard", "trade": "Admin", "base_hourly_rate": 30.0, "base_monthly_salary": 5100, "active_hours_per_week": 40},
]


# ---------------------------------------------------------------------------
# Mongo helpers
# ---------------------------------------------------------------------------
def _validate_object_id(v):
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)


PyObjectId = Annotated[str, BeforeValidator(_validate_object_id)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc):
        if not doc:
            return None
        return cls(**doc)

    def to_mongo(self):
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data


class EmployeeBase(BaseModel):
    name: str
    type: Literal["CCQ", "Standard"]
    trade: Literal["Électricien", "Frigoriste", "Admin"]
    base_hourly_rate: float = 0
    base_monthly_salary: float = 0
    active_hours_per_week: float = 40


class Employee(BaseDocument, EmployeeBase):
    pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "API Masse Salariale CCQ"}


@api_router.get("/config")
async def get_config():
    return {
        "employer_tax_rate": EMPLOYER_TAX_RATE,
        "treasury_budget": TREASURY_BUDGET,
        "ccq_rates": CCQ_RATES,
        "scenarios": SCENARIOS,
    }


@api_router.get("/employees", response_model=List[Employee], response_model_by_alias=False)
async def list_employees():
    docs = await db.employees.find().to_list(1000)
    return [Employee.from_mongo(d) for d in docs]


@api_router.post("/employees", response_model=Employee, response_model_by_alias=False)
async def create_employee(payload: EmployeeBase):
    doc = payload.model_dump()
    res = await db.employees.insert_one(doc)
    created = await db.employees.find_one({"_id": res.inserted_id})
    return Employee.from_mongo(created)


def _oid(employee_id: str) -> ObjectId:
    try:
        return ObjectId(employee_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Employé introuvable")


@api_router.put("/employees/{employee_id}", response_model=Employee, response_model_by_alias=False)
async def update_employee(employee_id: str, payload: EmployeeBase):
    oid = _oid(employee_id)
    res = await db.employees.update_one(
        {"_id": oid}, {"$set": payload.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    updated = await db.employees.find_one({"_id": oid})
    return Employee.from_mongo(updated)


@api_router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str):
    res = await db.employees.delete_one({"_id": _oid(employee_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employé introuvable")
    return {"success": True}


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
    count = await db.employees.count_documents({})
    if count == 0:
        await db.employees.insert_many([dict(e) for e in SEED_EMPLOYEES])
        logger.info("Seeded %d employees", len(SEED_EMPLOYEES))


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
