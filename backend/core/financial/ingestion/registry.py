"""Adapter registry / factory. Unknown data_type fails explicitly (no generic fallback)."""
from fastapi import HTTPException


def get_adapter(data_type: str):
    if data_type == "accounts":
        from .adapters.accounts import AccountsImportAdapter
        return AccountsImportAdapter()
    if data_type == "trial_balance":
        from .adapters.trial_balance import TrialBalanceImportAdapter
        return TrialBalanceImportAdapter()
    if data_type == "journal":
        from .adapters.journal import JournalImportAdapter
        return JournalImportAdapter()
    raise HTTPException(status_code=422, detail=f"data_type d'ingestion non pris en charge: {data_type}")


def registered_data_types() -> set:
    return {"accounts", "trial_balance", "journal"}
