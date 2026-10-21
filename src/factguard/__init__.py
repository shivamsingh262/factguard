"""Code computes every number, the LLM only interprets.

factguard keeps LLM-written text free of numbers your code didn't compute.
"""

from .facts import RULES, Fact, Facts, Formatter
from .guard import Result, Retry, StreamGuard, aguard, guard
from .sentences import drop_sentences, split_sentences
from .validate import Report, Violation, Window, validate

__version__ = "0.1.2"

__all__ = [
    "RULES",
    "Fact",
    "Facts",
    "Formatter",
    "Report",
    "Result",
    "Retry",
    "StreamGuard",
    "Violation",
    "Window",
    "aguard",
    "drop_sentences",
    "guard",
    "split_sentences",
    "validate",
]
