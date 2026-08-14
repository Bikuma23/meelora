"""P2.7 — Ingestion abstraction shared by accounts / trial_balance / journal.

Layers: Source Reader → DataType Adapter → Orchestrator → Normalized Writer.
Domain rules stay inside the domain adapters/services; this package only unifies
orchestration (data_import lifecycle, status transitions, counters) and file
reading. Public import APIs and financial behavior are unchanged.
"""
