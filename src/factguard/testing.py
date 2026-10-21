"""Helpers for eval suites: assert that recorded answers contain zero ungrounded numbers."""

from __future__ import annotations

from typing import Any

from .facts import Facts
from .validate import Report, validate


def assert_grounded(text: str, facts: Facts, **rules: Any) -> Report:
    """Raise AssertionError listing every ungrounded number in text."""
    report = validate(text, facts, **rules)
    if not report.ok:
        raise AssertionError(report.feedback)
    return report
