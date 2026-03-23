"""
Line Intelligence Engine — Persistence abstraction.

v1 provides a local in-memory backend. The interface is designed so
a Postgres-backed implementation can be swapped in later without
changing the session manager or any upstream code.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Optional

from .models import SessionDecision


class PersistenceBackend(ABC):
    """Abstract persistence interface for Line Intelligence decisions."""

    @abstractmethod
    def save_decision(self, decision: SessionDecision) -> None:
        """Persist a session decision."""
        ...

    @abstractmethod
    def get_decision(self, decision_id: str) -> Optional[SessionDecision]:
        """Retrieve a decision by ID."""
        ...

    @abstractmethod
    def get_decisions_for_line(
        self, line_id: str, tenant_id: str, limit: int = 50
    ) -> list[SessionDecision]:
        """Retrieve recent decisions for a given line, newest first."""
        ...

    @abstractmethod
    def get_decisions_for_tenant(
        self, tenant_id: str, limit: int = 100
    ) -> list[SessionDecision]:
        """Retrieve recent decisions for a tenant, newest first."""
        ...


class InMemoryPersistence(PersistenceBackend):
    """
    Thread-safe in-memory persistence for development and testing.

    Stores decisions in plain dicts. Not suitable for production — replace
    with PostgresPersistence when wiring to the real database.
    """

    def __init__(self, max_per_line: int = 200) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, SessionDecision] = {}
        self._by_line: dict[str, list[SessionDecision]] = defaultdict(list)
        self._by_tenant: dict[str, list[SessionDecision]] = defaultdict(list)
        self._max_per_line = max_per_line

    def save_decision(self, decision: SessionDecision) -> None:
        with self._lock:
            self._by_id[decision.decision_id] = decision
            line_key = f"{decision.tenant_id}:{decision.line_id}"
            self._by_line[line_key].append(decision)
            if len(self._by_line[line_key]) > self._max_per_line:
                self._by_line[line_key] = self._by_line[line_key][-self._max_per_line:]
            self._by_tenant[decision.tenant_id].append(decision)

    def get_decision(self, decision_id: str) -> Optional[SessionDecision]:
        with self._lock:
            return self._by_id.get(decision_id)

    def get_decisions_for_line(
        self, line_id: str, tenant_id: str, limit: int = 50
    ) -> list[SessionDecision]:
        with self._lock:
            key = f"{tenant_id}:{line_id}"
            items = self._by_line.get(key, [])
            return list(reversed(items[-limit:]))

    def get_decisions_for_tenant(
        self, tenant_id: str, limit: int = 100
    ) -> list[SessionDecision]:
        with self._lock:
            items = self._by_tenant.get(tenant_id, [])
            return list(reversed(items[-limit:]))

    def clear(self) -> None:
        """Clear all stored decisions (for testing)."""
        with self._lock:
            self._by_id.clear()
            self._by_line.clear()
            self._by_tenant.clear()
