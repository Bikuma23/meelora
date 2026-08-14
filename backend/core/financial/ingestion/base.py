"""Common ingestion contracts: adapter interface, lifecycle states, error model."""
from fastapi import HTTPException

from ...permissions import require_company_admin, require_tenant_context

# P2.4 data_import lifecycle (unchanged historical meaning).
LIFECYCLE_STATES = {
    "pending", "validating", "valid", "importing",
    "completed", "completed_with_warnings", "failed",
}
# Allowed transitions the orchestrator centralizes (fail explicitly otherwise).
ALLOWED_TRANSITIONS = {
    "valid": {"importing", "completed", "completed_with_warnings", "failed"},
    "importing": {"completed", "completed_with_warnings", "failed"},
}

# Normalized ingestion error categories (for future connector/UX use).
ERROR_CATEGORIES = {
    "source_format_error", "validation_error", "account_resolution_error",
    "financial_consistency_error", "duplicate_error", "period_error", "connector_error",
}


def assert_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Transition de statut invalide: {current} → {target}")


class ImportAdapter:
    """Contract every data-type adapter implements. Domain rules live in the
    adapter (delegating to the domain service); orchestration is shared."""
    data_type: str = None
    source_types = None  # None → no restriction

    def validate_source_type(self, source_type: str) -> None:
        if self.source_types is not None and source_type not in self.source_types:
            raise HTTPException(status_code=422, detail=f"source_type invalide: {source_type}")

    async def authorize(self, db, company_id, user):
        """Structural import = workspace admin (P1.12). Returns (company, workspace_id)."""
        company = await require_company_admin(db, company_id, user)
        workspace_id = require_tenant_context(user)
        return company, workspace_id

    async def context_fields(self, db, company_id, user, workspace_id, actx):
        """Return (doc_fields, runtime). doc_fields persist on the data_import;
        runtime is passed to validate (e.g. resolved period)."""
        return {}, {}

    def parse(self, content, file_name):
        raise NotImplementedError

    async def validate(self, db, company, workspace_id, rows, actx, runtime):
        raise NotImplementedError

    def idempotency_key(self, workspace_id, company_id, doc_fields, checksum):
        raise NotImplementedError

    async def pre_commit(self, db, doc, workspace_id):
        return

    async def idempotency_noop(self, db, doc, workspace_id):
        """Return None, or {"mode": "already_committed"} / {"mode": "terminal", ...}."""
        return None

    async def write(self, db, doc, user, workspace_id):
        raise NotImplementedError
