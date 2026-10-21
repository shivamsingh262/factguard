"""Checks LLM text for numbers that did not come from a fact."""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from .facts import PLACEHOLDER, Facts

Window = tuple[date, date]

_MALFORMED = re.compile(r"\{\{[^{}]*\}\}|\{fact:[^{}]*\}")
_LIST_MARKER = re.compile(r"(?m)^[ \t]*(?:[-*•][ \t]+)?\d{1,3}[.)](?=\s)")
# Names and words that contain digits but state no quantity.
_TERMS = re.compile(r"(?i)\b(?:GA4|GA360|B2B|B2C|D2C|C2C|P2P|24/7|[123](?:st|nd|rd)[- ]party|H\.26[45])\b")
_ATTRIBUTION = re.compile(r"(?i)\b\d{1,2}[- ]?(?:days?|d)[- ](?:click|view)s?\b")

_MONTH = (
    r"(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(?P<year>(?:19|20)\d{2})\b)?"
_DATES = [
    re.compile(r"\b(?P<year>\d{4})-(?P<m>\d{2})-(?P<day>\d{2})\b"),
    re.compile(r"\b" + _MONTH + r"\s+" + _DAY + r"\b" + _YEAR),
    re.compile(r"\b" + _DAY + r"\s+" + _MONTH + r"(?![A-Za-z])" + _YEAR),
]
_MONTH_YEAR = re.compile(r"\b" + _MONTH + r",?\s+(?P<year>(?:19|20)\d{2})\b")
_YEAR_ONLY = re.compile(r"\b(?:19|20)\d{2}\b")
_DURATION = re.compile(r"(?i)\b(?P<n>\d+)[- ]?(?P<unit>day|week|month)s?\b")

_TOKEN = re.compile(r"\S*\d\S*")
_NUMBER = re.compile(r"(?i)^[^\d\-+]*?(?P<sign>[-+])?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<suffix>%|x|k|m|mn|bn|b)?$")
_MULTIPLIER = {"k": 1e3, "m": 1e6, "mn": 1e6, "b": 1e9, "bn": 1e9}

_NUMBER_WORDS = re.compile(
    r"(?i)\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion"
    r"|dozen|double[sd]?|doubling|triple[sd]?|tripling|twice|half|halved|\w+fold)\b"
)


@dataclass(frozen=True)
class Violation:
    """One broken rule: what kind, the offending text and where it is."""

    kind: str  # unknown_fact | malformed_placeholder | literal_number | date | duration | number_word
    token: str
    start: int
    end: int
    detail: str


@dataclass(frozen=True)
class Report:
    text: str
    violations: tuple[Violation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def __bool__(self) -> bool:
        return self.ok

    @property
    def feedback(self) -> str:
        """A retry message that names every offending key or token."""
        if self.ok:
            return ""
        lines = [
            "Your draft broke the rule that every number must come from a fact placeholder. "
            "Fix only these and keep the rest of the draft as it is:"
        ]
        seen = set()
        for v in self.violations:
            if (v.kind, v.token) not in seen:
                seen.add((v.kind, v.token))
                lines.append(f"- `{v.token}`: {v.detail}")
        return "\n".join(lines)


def _fmt_windows(windows: Sequence[Window]) -> str:
    return ", ".join(f"{a.isoformat()} to {b.isoformat()}" for a, b in windows)


def _month_number(name: str) -> int:
    return [m.lower() for m in calendar.month_abbr].index(name[:3].lower())


def _value(token: str) -> float | None:
    m = _NUMBER.match(token)
    if not m:
        return None
    x = float(m["num"].replace(",", ""))
    x *= _MULTIPLIER.get((m["suffix"] or "").lower(), 1)
    return -x if m["sign"] == "-" else x


def _strip(token: str) -> tuple[str, int]:
    """Trim surrounding punctuation. Returns the token and how much was cut from the left."""
    left = len(token) - len(token.lstrip("(\"'[“‘"))
    return token[left:].rstrip(".,;:!?)\"']”’"), left


class _Text:
    """The text being checked, with spans blanked out once they are accounted for."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.masked = text

    def blank(self, start: int, end: int) -> None:
        self.masked = self.masked[:start] + " " * (end - start) + self.masked[end:]


def validate(
    text: str,
    facts: Facts,
    *,
    windows: Iterable[Window] = (),
    user_text: str = "",
    allow: Iterable[str | re.Pattern[str]] = (),
    list_markers: bool = True,
    attribution_labels: bool = True,
    terms: bool = True,
    number_words: bool = False,
) -> Report:
    """Check LLM text against the rule: no number the code did not compute.

    windows: the date ranges this answer actually used. Dates, years and
        durations ("last 28 days") are allowed only when they match one.
    user_text: what the user wrote. Numbers they typed may be repeated.
    allow: extra regexes for text that may contain digits.
    terms: allow names like GA4, B2B and 3rd-party.
    number_words: also flag quantities in words ("doubled", "twenty").
    """
    windows = tuple(windows)
    t = _Text(text)
    found: list[Violation] = []

    def flag(kind: str, start: int, end: int, detail: str) -> None:
        found.append(Violation(kind, text[start:end], start, end, detail))
        t.blank(start, end)

    for m in PLACEHOLDER.finditer(text):
        if m[1] in facts:
            t.blank(*m.span())
        else:
            flag("unknown_fact", *m.span(), f"`{m[1]}` is not a known fact key. Use only keys from the fact list.")
    for m in _MALFORMED.finditer(t.masked):
        flag("malformed_placeholder", *m.span(), "write placeholders exactly as {{fact:key}}.")

    patterns = [re.compile(p) if isinstance(p, str) else p for p in allow]
    if list_markers:
        patterns.append(_LIST_MARKER)
    if attribution_labels:
        patterns.append(_ATTRIBUTION)
    if terms:
        patterns.append(_TERMS)
    for pattern in patterns:
        for m in pattern.finditer(t.masked):
            t.blank(*m.span())

    _check_dates(t, windows, flag)

    allowed = _numbers(user_text)
    for m in _TOKEN.finditer(t.masked):
        token, cut = _strip(m[0])
        if not token:
            continue
        start = m.start() + cut
        value = _value(token)
        if token in allowed or (value is not None and value in allowed):
            continue
        flag(
            "literal_number",
            start,
            start + len(token),
            "this is a number you typed. Cite it with a {{fact:...}} placeholder, or say it without the figure.",
        )

    if number_words:
        for m in _NUMBER_WORDS.finditer(t.masked):
            flag("number_word", *m.span(), "this states a quantity in words. Cite a fact or drop the comparison.")

    return Report(text, tuple(sorted(found, key=lambda v: v.start)))


def _numbers(user_text: str) -> set[str | float]:
    out: set[str | float] = set()
    for m in _TOKEN.finditer(user_text):
        token, _ = _strip(m[0])
        out.add(token)
        if (value := _value(token)) is not None:
            out.add(value)
    return out


def _check_dates(t: _Text, windows: tuple[Window, ...], flag) -> None:
    where = f"the analysis window ({_fmt_windows(windows)})" if windows else "an analysis window, and none was given"

    def judge(m: re.Match[str], inside: bool, kind: str = "date") -> None:
        if inside:
            t.blank(*m.span())
        else:
            flag(kind, *m.span(), f"dates and periods must come from {where}.")

    def contains(d: date) -> bool:
        return any(a <= d <= b for a, b in windows)

    for i, pattern in enumerate(_DATES):
        for m in pattern.finditer(t.masked):
            month = int(m["m"]) if i == 0 else _month_number(m["mon"])
            day = int(m["day"])
            years = (
                [int(m["year"])]
                if m["year"]
                else range(
                    min((a.year for a, _ in windows), default=0), max((b.year for _, b in windows), default=-1) + 1
                )
            )
            inside = False
            for year in years:
                try:
                    inside = inside or contains(date(year, month, day))
                except ValueError:
                    pass
            judge(m, inside)

    for m in _MONTH_YEAR.finditer(t.masked):
        year, month = int(m["year"]), _month_number(m["mon"])
        first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        judge(m, any(a <= last and b >= first for a, b in windows))

    for m in _YEAR_ONLY.finditer(t.masked):
        judge(m, any(a.year <= int(m[0]) <= b.year for a, b in windows))

    lengths = [(b - a).days + 1 for a, b in windows]
    for m in _DURATION.finditer(t.masked):
        n, unit = int(m["n"]), m["unit"].lower()
        if unit == "day":
            inside = n in lengths
        elif unit == "week":
            inside = n * 7 in lengths
        else:
            inside = any(abs(length - n * 30.44) <= 3 for length in lengths)
        judge(m, inside, "duration")
