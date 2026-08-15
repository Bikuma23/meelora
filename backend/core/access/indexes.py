"""P1.13A — Aggregate index creation for all access collections."""
from . import activation, entitlements, log_scope, module_access, scopes


async def ensure_indexes(db) -> None:
    await entitlements.ensure_indexes(db)
    await module_access.ensure_indexes(db)
    await scopes.ensure_indexes(db)
    await activation.ensure_indexes(db)
    await log_scope.ensure_indexes(db)
