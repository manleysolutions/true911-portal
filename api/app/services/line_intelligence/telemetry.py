"""
Line Intelligence Engine — Telemetry collector.

Produces dashboard-ready structured data from pipeline decisions.
Does NOT modify the UI or any existing telemetry tables — this is
a standalone collector that can later feed into the existing
telemetry_event table or an external dashboard.
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .constants import Confidence, LineType
from .models import SessionDecision


@dataclass
class TelemetrySummary:
    """Snapshot of Line Intelligence telemetry metrics."""

    total_decisions: int = 0
    decisions_by_type: dict[str, int] = field(default_factory=dict)
    decisions_by_confidence: dict[str, int] = field(default_factory=dict)
    fallback_count: int = 0
    override_count: int = 0
    actionable_count: int = 0
    avg_confidence: float = 0.0
    last_decision_at: Optional[datetime] = None
    tenant_id: Optional[str] = None


class TelemetryCollector:
    """
    Collects structured metrics from Line Intelligence pipeline decisions.

    Thread-safe. Designed to be read by a future dashboard endpoint or
    periodic export job.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total: int = 0
        self._by_type: Counter[str] = Counter()
        self._by_confidence: Counter[str] = Counter()
        self._fallbacks: int = 0
        self._overrides: int = 0
        self._actionable: int = 0
        self._confidence_sum: float = 0.0
        self._last_at: Optional[datetime] = None
        self._by_tenant: dict[str, _TenantCounters] = defaultdict(_TenantCounters)

    def record_decision(self, decision: SessionDecision) -> None:
        """Record metrics from a single pipeline decision."""
        cls = decision.classification
        with self._lock:
            self._total += 1
            self._by_type[cls.line_type.value] += 1
            self._by_confidence[cls.confidence_tier.value] += 1
            self._confidence_sum += cls.confidence_score
            if cls.fallback_applied:
                self._fallbacks += 1
            if decision.manual_override:
                self._overrides += 1
            if cls.is_actionable:
                self._actionable += 1
            self._last_at = decision.timestamp

            tc = self._by_tenant[decision.tenant_id]
            tc.total += 1
            tc.by_type[cls.line_type.value] += 1

    def summary(self, tenant_id: Optional[str] = None) -> TelemetrySummary:
        """Return a point-in-time telemetry snapshot."""
        with self._lock:
            if tenant_id and tenant_id in self._by_tenant:
                tc = self._by_tenant[tenant_id]
                return TelemetrySummary(
                    total_decisions=tc.total,
                    decisions_by_type=dict(tc.by_type),
                    tenant_id=tenant_id,
                )
            return TelemetrySummary(
                total_decisions=self._total,
                decisions_by_type=dict(self._by_type),
                decisions_by_confidence=dict(self._by_confidence),
                fallback_count=self._fallbacks,
                override_count=self._overrides,
                actionable_count=self._actionable,
                avg_confidence=(
                    round(self._confidence_sum / self._total, 4)
                    if self._total > 0
                    else 0.0
                ),
                last_decision_at=self._last_at,
            )

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        with self._lock:
            self._total = 0
            self._by_type.clear()
            self._by_confidence.clear()
            self._fallbacks = 0
            self._overrides = 0
            self._actionable = 0
            self._confidence_sum = 0.0
            self._last_at = None
            self._by_tenant.clear()


class _TenantCounters:
    """Per-tenant accumulator (internal)."""

    __slots__ = ("total", "by_type")

    def __init__(self) -> None:
        self.total: int = 0
        self.by_type: Counter[str] = Counter()
