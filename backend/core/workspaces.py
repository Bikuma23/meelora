"""Workspace domain model for Meelora V2 Foundation.

This module is intentionally dependency-light and is not wired into the existing
financial routes yet. Phase 1 introduces the tenant root without changing the
legacy acct/qc9434 engines.
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, Field

OrganizationType = Literal["company", "group", "fiduciary"]
WorkspaceStatus = Literal["active", "inactive"]


class Workspace(BaseModel):
    id: str = Field(default_factory=lambda: f"ws_{uuid.uuid4().hex}", alias="_id")
    name: str
    organization_type: OrganizationType
    jurisdiction: str
    primary_admin_user_id: str
    status: WorkspaceStatus = "active"
    onboarding_completed: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str

    model_config = {"populate_by_name": True}

    def mongo_document(self) -> dict:
        return self.model_dump(by_alias=True)


class WorkspacePublic(BaseModel):
    id: str
    name: str
    organization_type: OrganizationType
    jurisdiction: str
    status: WorkspaceStatus
    onboarding_completed: bool


def public_workspace(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return WorkspacePublic(
        id=str(doc.get("_id", "")),
        name=doc.get("name", ""),
        organization_type=doc.get("organization_type", "company"),
        jurisdiction=doc.get("jurisdiction", ""),
        status=doc.get("status", "active"),
        onboarding_completed=bool(doc.get("onboarding_completed", False)),
    ).model_dump()
