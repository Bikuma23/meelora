"""P1.13A — Commercial module registry (system-defined, stable internal codes).

Modules are system-defined and never hard-coded into navigation logic. The
registry is the single source of truth for the canonical module codes and for
the technical access-level ladder (none < read < contribute < manage).
"""
from typing import Optional

REPORTING = "REPORTING"
ACCOUNTING = "ACCOUNTING"
FIXED_ASSETS = "FIXED_ASSETS"
CONSOLIDATION = "CONSOLIDATION"

# Canonical initial module registry. UI naming is decided later; codes are stable.
MODULES = [
    {"code": REPORTING, "sort_order": 1,
     "name": {"en": "Reporting", "fr": "Reporting"}},
    {"code": ACCOUNTING, "sort_order": 2,
     "name": {"en": "Accounting", "fr": "Comptabilité"}},
    {"code": FIXED_ASSETS, "sort_order": 3,
     "name": {"en": "Fixed Assets", "fr": "Immobilisations"}},
    {"code": CONSOLIDATION, "sort_order": 4,
     "name": {"en": "Consolidation", "fr": "Consolidation"}},
]

MODULE_CODES = {m["code"] for m in MODULES}

# Technical access levels. UI naming can differ (e.g. "contribute" shown as
# "Saisie"). ``manage`` is NOT unlimited authority — sensitive actions remain
# separate explicit permissions (see permissions_catalog).
ACCESS_LEVELS = ["none", "read", "contribute", "manage"]
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(ACCESS_LEVELS)}


def is_valid_module(code: Optional[str]) -> bool:
    return code in MODULE_CODES


def is_valid_level(level: Optional[str]) -> bool:
    return level in _LEVEL_RANK


def level_rank(level: Optional[str]) -> int:
    return _LEVEL_RANK.get(level, -1)


def level_satisfies(actual: Optional[str], required: Optional[str]) -> bool:
    """True when ``actual`` module access covers ``required`` (fail-closed)."""
    a, r = level_rank(actual), level_rank(required)
    if a < 0 or r < 0:
        return False
    return a >= r


def list_modules() -> list[dict]:
    return [dict(m) for m in sorted(MODULES, key=lambda m: m["sort_order"])]
