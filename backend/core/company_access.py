"""Company access domain model for Meelora V2 Foundation (P1.3).

The security authority for company visibility is ``company_access``. A mandate
may later mirror principal/collaborator assignments for fiduciary workflows,
but authorization must always consult this collection (or an admin override).
"""
from datetime import datetime, timezone
from typing import Literal
import uuid

from pydantic import BaseModel, Field

AccessRole = Literal["principal", "collaborator"]


class CompanyAccess(BaseModel):
    id: str = Field(default_factory=lambda: f"cacc_{uuid.uuid4().hex}", alias="_id")
    workspace_id: str
    company_id: str
    user_id: str
    access_role: AccessRole
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str

    model_config = {"populate_by_name": True}

    def mongo_document(self) -> dict:
        return self.model_dump(by_alias=True)
