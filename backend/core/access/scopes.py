"""P1.13A — Resource scope + workflow-assignment foundation.

Two orthogonal concepts, kept strictly separate from module access and
permissions:

* ``consolidation_group_scopes`` — a user's Consolidation access is limited to
  explicitly assigned groups. Access to Group Alpha never implies Group Beta.
* ``workflow_assignments`` — being responsible for a specific action/object
  (PO approver, consolidation approver, accounting reviewer). An ASSIGNMENT is
  NOT a PERMISSION: it identifies responsibility, not authority.

Policy metadata (segregation of duties) is also recorded here as foundation
only — no workflow engine is implemented in P1.13A.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import HTTPException

_now = lambda: datetime.now(timezone.utc).isoformat()

ASSIGNMENT_TYPES = {
    "po_approver",
    "consolidation_approver",
    "accounting_reviewer",
    "consolidation_reviewer",
}

# Foundational, non-configurable policy: a PO creator can NEVER approve their own
# PO. Enforced later in the Accounting module; recorded here as a hard rule.
PO_SELF_APPROVAL_ALLOWED = False

# Consolidation separation-of-duties is configurable (unlike PO approval), because
# small organizations may have a single operator.
CONSOLIDATION_SOD_POLICIES = {"required", "recommended", "not_required"}
DEFAULT_CONSOLIDATION_SOD = "recommended"


# ---- Consolidation group scope --------------------------------------------
async def has_group_scope(db, workspace_id: str, user_id: str, group_id: str) -> bool:
    row = await db.consolidation_group_scopes.find_one(
        {"workspace_id": workspace_id, "user_id": user_id, "group_id": group_id, "active": True})
    return bool(row)


async def list_group_scopes(db, workspace_id: str, user_id: str) -> list[str]:
    rows = await db.consolidation_group_scopes.find(
        {"workspace_id": workspace_id, "user_id": user_id, "active": True}).to_list(None)
    return sorted(r.get("group_id") for r in rows if r.get("group_id"))


async def set_group_scope(db, workspace_id: str, user_id: str, group_id: str,
                          active: bool, actor_id: str) -> dict:
    now = _now()
    existing = await db.consolidation_group_scopes.find_one(
        {"workspace_id": workspace_id, "user_id": user_id, "group_id": group_id})
    changes = {"active": bool(active), "updated_at": now, "updated_by": actor_id}
    if existing:
        await db.consolidation_group_scopes.update_one({"_id": existing["_id"]}, {"$set": changes})
    else:
        await db.consolidation_group_scopes.insert_one(
            {"_id": f"cgs_{uuid.uuid4().hex}", "workspace_id": workspace_id, "user_id": user_id,
             "group_id": group_id, "created_at": now, "created_by": actor_id, **changes})
    return {"group_id": group_id, "active": bool(active)}


# ---- Workflow assignments --------------------------------------------------
async def create_assignment(db, workspace_id: str, company_id: Optional[str], user_id: str,
                            assignment_type: str, actor_id: str,
                            object_id: Optional[str] = None) -> dict:
    if assignment_type not in ASSIGNMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Type d'assignation inconnu: {assignment_type}")
    now = _now()
    doc = {"_id": f"wfa_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
           "user_id": user_id, "assignment_type": assignment_type, "object_id": object_id,
           "active": True, "created_at": now, "created_by": actor_id}
    await db.workflow_assignments.insert_one(doc)
    return {k: doc[k] for k in ("id", "workspace_id", "company_id", "user_id",
                                "assignment_type", "object_id", "active") if k in doc} | {"id": doc["_id"]}


async def list_assignments(db, workspace_id: str, company_id: Optional[str] = None,
                           assignment_type: Optional[str] = None) -> list[dict]:
    query = {"workspace_id": workspace_id, "active": True}
    if company_id is not None:
        query["company_id"] = company_id
    if assignment_type is not None:
        query["assignment_type"] = assignment_type
    rows = await db.workflow_assignments.find(query).to_list(None)
    return [{"id": r.get("_id"), "workspace_id": r.get("workspace_id"),
             "company_id": r.get("company_id"), "user_id": r.get("user_id"),
             "assignment_type": r.get("assignment_type"), "object_id": r.get("object_id")}
            for r in rows]


async def ensure_indexes(db) -> None:
    await db.consolidation_group_scopes.create_index(
        [("workspace_id", 1), ("user_id", 1), ("group_id", 1)], unique=True,
        name="uniq_consolidation_group_scope")
    await db.workflow_assignments.create_index(
        [("workspace_id", 1), ("company_id", 1), ("assignment_type", 1)],
        name="idx_workflow_assignment")
