"""P2.7 — Ingestion abstraction tests (registry, readers, orchestrator, connectors)."""
import asyncio

import pytest
from fastapi import HTTPException

from core.financial.ingestion.registry import get_adapter, registered_data_types
from core.financial.ingestion.readers import read_tabular, _cell_str
from core.financial.ingestion.base import ImportAdapter, assert_transition, ERROR_CATEGORIES
from core.financial.ingestion.connectors.base import BaseConnector, MockConnector, ConnectorError


def _run(c): return asyncio.run(c)


# ---- Registry -------------------------------------------------------------
def test_registry_resolves_known_adapters():
    for dt in ("accounts", "trial_balance", "journal"):
        a = get_adapter(dt)
        assert isinstance(a, ImportAdapter) and a.data_type == dt


def test_registry_unknown_rejected():
    with pytest.raises(HTTPException) as e:
        get_adapter("payroll")
    assert e.value.status_code == 422


def test_registered_data_types():
    assert registered_data_types() == {"accounts", "trial_balance", "journal"}


# ---- Readers (transport only, no business rules) --------------------------
def _norm(h):
    m = {"code": "account_code", "name": "account_name", "amount": "amount"}
    return m.get(str(h).strip().lower())


def test_reader_csv_maps_headers_and_preserves_strings():
    content = b"code,name,amount\n0010,Cash,100\n3200,Sales,200\n"
    rows, header_fields = read_tabular(content, "f.csv", _norm)
    assert header_fields == {"account_code", "account_name", "amount"}
    assert rows[0]["account_code"] == "0010"  # leading zero preserved
    assert rows[0]["_row"] == 2


def test_reader_skips_blank_rows():
    content = b"code,name,amount\n0010,Cash,100\n\n3200,Sales,200\n"
    rows, _ = read_tabular(content, "f.csv", _norm)
    assert len(rows) == 2


def test_reader_empty_file_400():
    with pytest.raises(HTTPException) as e:
        read_tabular(b"", "f.csv", _norm)
    assert e.value.status_code == 400


def test_cell_str_number_formatting():
    assert _cell_str(3200.0) == "3200"
    assert _cell_str("0010") == "0010"
    assert _cell_str(None) == ""


# ---- Lifecycle transitions ------------------------------------------------
def test_valid_transitions():
    assert_transition("valid", "importing")
    assert_transition("importing", "completed")
    assert_transition("importing", "completed_with_warnings")


def test_invalid_transition_rejected():
    with pytest.raises(HTTPException) as e:
        assert_transition("completed", "importing")
    assert e.value.status_code == 409


def test_error_categories_present():
    assert {"validation_error", "financial_consistency_error", "connector_error"} <= ERROR_CATEGORIES


# ---- Base adapter defaults ------------------------------------------------
def test_source_type_restriction():
    a = get_adapter("accounts")
    a.validate_source_type("excel")  # ok
    with pytest.raises(HTTPException) as e:
        a.validate_source_type("bogus")
    assert e.value.status_code == 422


def test_source_type_unrestricted_for_tb_journal():
    # TB/journal never restricted source_type (preserve prior behaviour).
    get_adapter("trial_balance").validate_source_type("anything")
    get_adapter("journal").validate_source_type("anything")


def test_idempotency_keys_are_scoped():
    acc = get_adapter("accounts").idempotency_key("ws", "co", {}, "CHK")
    tb = get_adapter("trial_balance").idempotency_key("ws", "co", {"financial_period_id": "fp"}, "CHK")
    je = get_adapter("journal").idempotency_key("ws", "co", {"financial_period_id": "fp"}, "CHK")
    assert acc == "ws:co:accounts:CHK"
    assert tb == "ws:co:trial_balance:fp:CHK"
    assert je == "ws:co:journal:fp:CHK"


# ---- Connectors (interface + mock, no real providers) ---------------------
def test_mock_connector_success_path():
    mc = MockConnector(payloads={"accounts": b"code,name\n0010,Cash\n"})
    assert _run(mc.test_connection()) is True
    _run(mc.connect())
    data = _run(mc.fetch_accounts())
    assert data.startswith(b"code,name")


def test_mock_connector_failure_propagates():
    mc = MockConnector(fail=True)
    with pytest.raises(ConnectorError):
        _run(mc.connect())
    with pytest.raises(ConnectorError):
        _run(mc.fetch_trial_balance())


def test_mock_connector_missing_payload():
    mc = MockConnector(payloads={})
    with pytest.raises(ConnectorError):
        _run(mc.fetch_transactions())


def test_base_connector_is_abstract_like():
    bc = BaseConnector()
    with pytest.raises(NotImplementedError):
        _run(bc.connect())


# ---- source_type=api goes through the SAME lifecycle (adapter contract) ---
def test_api_source_type_supported_by_accounts_adapter():
    # Accounts adapter accepts source_type=api (same data_import lifecycle).
    get_adapter("accounts").validate_source_type("api")
