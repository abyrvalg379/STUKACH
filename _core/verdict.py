# -*- coding: utf-8 -*-
"""Verdict aggregation: findings -> ready / warning / critical."""
from __future__ import annotations

from typing import Iterable, Optional

from .model import Finding

_ORDER = {"critical": 0, "warning": 1, "ready": 2}


def verdict(findings: Iterable[Finding]) -> str:
    """Aggregate core findings into a three-state verdict.

    'critical'  — at least one BLOCKER severity finding
    'warning'   — no blockers, at least one WARNING
    'ready'     — nothing blocking"""
    worst = "ready"
    for f in findings:
        if f.severity == "BLOCKER":
            return "critical"
        if f.severity == "WARNING":
            worst = "warning"
    return worst


def merge(*verdicts: Optional[str]) -> str:
    """Combine several verdicts into the worst one ('none'/empty ignored)."""
    worst = "ready"
    for v in verdicts:
        if not v or v == "ready":
            continue
        if v == "critical":
            return "critical"
        if _ORDER.get(v, 2) < _ORDER[worst]:
            worst = v
    return worst
