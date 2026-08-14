"""Meelora V2 — Financial Core package.

Modular home for the normalized reporting engine introduced in Phase 2.
P2.1 adds ``financial_years``. Later components (financial_periods, accounts,
data_imports, trial_balance, journal, ingestion) will live alongside it.

Authorization always reuses the Phase 1 centralized helpers in
``core.permissions`` — this package never introduces a second permission system.
"""
