"""P1.13A — Access & Identity Foundation V2.

Layered access model for Meelora V2:

    Identity → Membership → Entitlement → Module Access → Permission → Scope
    → Workflow Assignment → Effective Access

This package is additive infrastructure. It NEVER modifies financial data and it
NEVER grants access implicitly. All resolution is fail-closed (deny-by-default).
The legacy P1.12 ``permissions.py`` gate stays intact as a compatibility bridge;
new functional access is resolved exclusively through ``resolve_effective_access``.
"""
