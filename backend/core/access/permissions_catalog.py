"""P1.13A — Sensitive permission catalogue (stable codes, foundational).

Permissions are separate from module access levels. A ``manage`` access level
does NOT automatically imply any of these permissions — each sensitive action
must be granted explicitly. P1.13A only implements the permission *architecture*
and catalogue; the business modules themselves are NOT implemented here.
"""
from typing import Optional

from .modules import ACCOUNTING, BUDGETS, CONSOLIDATION, FIXED_ASSETS, REPORTING

# module_code -> ordered list of stable permission codes.
PERMISSIONS: dict[str, list[str]] = {
    REPORTING: [
        "reporting.import",
        "reporting.mapping_confirm",
        "reporting.report_generate",
        "reporting.report_finalize",
        "reporting.external_send",
        "reporting.template_manage",
        "reporting.settings_manage",
    ],
    # BUDGETS sensitive permissions are not yet catalogued (the historical
    # payroll engine keeps its existing controls). Placeholder keeps the module
    # present in the catalogue without granting anything.
    BUDGETS: [],
    ACCOUNTING: [
        "accounting.entry_post",
        "accounting.entry_approve",
        "accounting.customer_invoice_post",
        "accounting.customer_invoice_approve",
        "accounting.customer_payment_post",
        "accounting.customer_credit_note_approve",
        "accounting.customer_credit_note_post",
        "accounting.supplier_invoice_post",
        "accounting.supplier_invoice_approve",
        "accounting.supplier_payment_post",
        "accounting.supplier_credit_note_approve",
        "accounting.supplier_credit_note_post",
        "accounting.po_approve",
        "accounting.po_match_override",
        "accounting.entry_reverse",
        "accounting.chart_manage",
        "accounting.reconciliation_manage",
        "accounting.reconciliation_approve",
        "accounting.period_close",
        "accounting.period_reopen",
    ],
    FIXED_ASSETS: [
        "fixed_assets.place_in_service",
        "fixed_assets.depreciation_parameters_manage",
        "fixed_assets.depreciation_approve",
        "fixed_assets.impairment_authorize",
        "fixed_assets.revaluation_authorize",
        "fixed_assets.transfer_authorize",
        "fixed_assets.disposal_authorize",
        "fixed_assets.capitalization_policy_manage",
        "fixed_assets.accounting_reference_manage",
    ],
    CONSOLIDATION: [
        "consolidation.prepare",
        "consolidation.intercompany_reconcile",
        "consolidation.adjustment_create",
        "consolidation.submit",
        "consolidation.review",
        "consolidation.approve",
        "consolidation.close",
        "consolidation.reopen",
        "consolidation.group_admin",
        "consolidation.ownership_manage",
        "consolidation.materiality_manage",
    ],
}

ALL_PERMISSIONS = {p for lst in PERMISSIONS.values() for p in lst}
PERMISSION_MODULE = {p: m for m, lst in PERMISSIONS.items() for p in lst}

# A2 — permanently deprecated: period reopening (closed -> open) is forbidden for
# EVERYONE. Corrections after close must be booked in a later period, never by
# reopening. Kept in the catalog for historical grants but never enforced/grantable.
DEPRECATED_PERMISSIONS = {"accounting.period_reopen"}


def is_deprecated_permission(code: Optional[str]) -> bool:
    return code in DEPRECATED_PERMISSIONS


def is_valid_permission(code: Optional[str]) -> bool:
    return code in ALL_PERMISSIONS and code not in DEPRECATED_PERMISSIONS


def module_for_permission(code: Optional[str]) -> Optional[str]:
    return PERMISSION_MODULE.get(code)


def list_permissions(module: Optional[str] = None) -> list[dict]:
    modules = [module] if module else list(PERMISSIONS.keys())
    out: list[dict] = []
    for m in modules:
        for code in PERMISSIONS.get(m, []):
            if code in DEPRECATED_PERMISSIONS:
                continue
            out.append({"code": code, "module_code": m})
    return out
