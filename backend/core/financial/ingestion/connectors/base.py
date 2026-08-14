"""Connector contracts (P2.7 preparation only).

A CONNECTOR obtains data from an external system; an ADAPTER interprets it for a
Meelora data_type. P2.7 ships ONLY the interface + a mock connector — no real
provider (Bexio/QuickBooks/Xero/Abacus) and no real credentials. Future API
ingestion MUST still go through the same data_import lifecycle (source_type=api).
"""
from typing import Optional


class ConnectorError(Exception):
    """Raised when an external source cannot be reached / returns bad data."""


class BaseConnector:
    provider: str = "base"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    async def connect(self) -> None:
        raise NotImplementedError

    async def test_connection(self) -> bool:
        raise NotImplementedError

    async def fetch_accounts(self, **kwargs) -> bytes:
        raise NotImplementedError

    async def fetch_trial_balance(self, **kwargs) -> bytes:
        raise NotImplementedError

    async def fetch_transactions(self, **kwargs) -> bytes:
        raise NotImplementedError


class MockConnector(BaseConnector):
    """In-memory connector for tests/dev. Returns canned CSV payloads or raises
    ConnectorError when configured to fail. Never touches real systems."""
    provider = "mock"

    def __init__(self, config: Optional[dict] = None, payloads: Optional[dict] = None, fail: bool = False):
        super().__init__(config)
        self._payloads = payloads or {}
        self._fail = fail
        self._connected = False

    async def connect(self) -> None:
        if self._fail:
            raise ConnectorError("connexion simulée en échec")
        self._connected = True

    async def test_connection(self) -> bool:
        if self._fail:
            raise ConnectorError("connexion simulée en échec")
        return True

    async def _payload(self, key: str) -> bytes:
        if self._fail:
            raise ConnectorError(f"récupération simulée en échec: {key}")
        data = self._payloads.get(key)
        if data is None:
            raise ConnectorError(f"aucune donnée simulée pour: {key}")
        return data if isinstance(data, bytes) else str(data).encode("utf-8")

    async def fetch_accounts(self, **kwargs) -> bytes:
        return await self._payload("accounts")

    async def fetch_trial_balance(self, **kwargs) -> bytes:
        return await self._payload("trial_balance")

    async def fetch_transactions(self, **kwargs) -> bytes:
        return await self._payload("journal")
