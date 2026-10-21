"""Facts are numbers computed in code. The LLM cites them by placeholder."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["money", "percent", "count", "number", "ratio", "text"]
KINDS: tuple[str, ...] = ("money", "percent", "count", "number", "ratio", "text")

KEY = r"[A-Za-z0-9_.:\-]+"
PLACEHOLDER = re.compile(r"\{\{\s*fact:(" + KEY + r")\s*\}\}")

# Codes and symbols the model tends to type in front of a money placeholder.
# Kept to real currencies so "CPA {{fact:cpa}}" is never touched.
CURRENCIES = frozenset(
    "USD EUR GBP INR JPY CNY AUD CAD NZD SGD HKD AED SAR CHF SEK NOK DKK ZAR BRL MXN IDR THB MYR PHP KRW".split()
)
_TYPED_CURRENCY = re.compile(
    r"(?:(?<![A-Za-z])(?P<code>[A-Z]{3}|Rs\.?)\s?|(?P<symbol>[$€£₹¥])\s?)"
    r"(?P<placeholder>\{\{\s*fact:(?P<key>" + KEY + r")\s*\}\})"
)

RULES = """\
Every number in your answer must come from the facts listed below.
- Cite a fact only as its placeholder, exactly as written, for example {{fact:spend}}. \
Never type its value: code fills it in, already formatted with any currency or % sign.
- Do not type any other digits: no totals, differences, percentages, dates, \
durations or thresholds you worked out yourself.
- If a number you want is not in the list, describe the change in words without a figure."""


@dataclass(frozen=True)
class Fact:
    """One computed value, plus where it came from."""

    key: str
    value: float | int | str
    kind: Kind = "number"
    label: str = ""
    currency: str | None = None
    decimals: int | None = None
    source: str | None = None
    step: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(KEY, self.key):
            raise ValueError(f"fact key {self.key!r} may only use letters, digits and _ . : -")
        if self.kind not in KINDS:
            raise ValueError(f"fact kind must be one of {', '.join(KINDS)}, not {self.kind!r}")
        if self.value is None or isinstance(self.value, bool):
            raise TypeError(f"fact {self.key!r} needs a number or text value, not {self.value!r}")
        numeric = isinstance(self.value, (int, float))
        if self.kind != "text" and not numeric:
            raise TypeError(f"fact {self.key!r} is {self.kind}, so its value must be a number")

    @property
    def placeholder(self) -> str:
        return "{{fact:" + self.key + "}}"


def _trim(s: str) -> str:
    return s.rstrip("0").rstrip(".") if "." in s else s


def _compact(x: float, decimals: int) -> str | None:
    """60_240 -> "60.2K". Returns None below a thousand."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        # Check the rounded value so 999_960 becomes "1M", not "1000K".
        if abs(x) >= 1000 and round(abs(x) / size, decimals) >= 1:
            return _trim(f"{x / size:.{decimals}f}") + suffix
    return None


@dataclass(frozen=True)
class Formatter:
    """Turns a fact into the text that replaces its placeholder.

    Percent facts are fractions: 0.034 renders as "3.4%".
    """

    currency: str | None = None
    compact: bool = True

    def __call__(self, fact: Fact) -> str:
        if fact.kind == "text":
            return str(fact.value)
        x = float(fact.value)
        if not math.isfinite(x):
            return "n/a"
        if fact.kind == "money":
            return self._prefix(fact.currency or self.currency) + self._money(x, fact.decimals)
        if fact.kind == "percent":
            return _trim(f"{x * 100:.{1 if fact.decimals is None else fact.decimals}f}") + "%"
        if fact.kind == "count":
            return f"{round(x):,}"
        if fact.kind == "ratio":
            return _trim(f"{x:.{2 if fact.decimals is None else fact.decimals}f}") + "x"
        if x.is_integer() and fact.decimals is None:
            return f"{int(x):,}"
        return _trim(f"{x:,.{2 if fact.decimals is None else fact.decimals}f}")

    def _money(self, x: float, decimals: int | None) -> str:
        if self.compact and (short := _compact(x, 1 if decimals is None else decimals)):
            return short
        if decimals is not None:
            return f"{x:,.{decimals}f}"
        # Decide on the rounded value so 99.999 renders as "100", not "100.00".
        if round(x, 2).is_integer() or abs(x) >= 100:
            return f"{x:,.0f}"
        return f"{x:,.2f}"

    @staticmethod
    def _prefix(currency: str | None) -> str:
        if not currency:
            return ""
        return currency + " " if currency.isalpha() else currency


class Facts:
    """The facts for one answer. Renders placeholders and describes facts to the LLM."""

    def __init__(
        self,
        facts: Iterable[Fact] = (),
        *,
        currency: str | None = None,
        formatter: Callable[[Fact], str] | None = None,
    ) -> None:
        self._facts: dict[str, Fact] = {}
        self.formatter = formatter or Formatter(currency=currency)
        for fact in facts:
            self.put(fact)

    @classmethod
    def from_records(cls, data: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> Facts:
        """Load {"currency": ..., "facts": [...]}, a list of fact dicts, or {key: value}."""
        currency = None
        if isinstance(data, Mapping):
            if "facts" in data:
                currency = data.get("currency")
                data = data["facts"]
            else:
                data = [{"key": k, "value": v} for k, v in data.items()]
        facts = cls(currency=currency)
        for record in data:
            record = dict(record)
            if "kind" not in record:
                record["kind"] = "number" if isinstance(record.get("value"), (int, float)) else "text"
            facts.put(Fact(**record))
        return facts

    def add(self, key: str, value: float | int | str, kind: Kind = "number", **fields: Any) -> Fact:
        return self.put(Fact(key, value, kind, **fields))

    def put(self, fact: Fact) -> Fact:
        if fact.key in self._facts:
            raise ValueError(f"fact {fact.key!r} is already defined")
        self._facts[fact.key] = fact
        return fact

    def get(self, key: str) -> Fact | None:
        return self._facts.get(key)

    def __getitem__(self, key: str) -> Fact:
        return self._facts[key]

    def __contains__(self, key: object) -> bool:
        return key in self._facts

    def __iter__(self) -> Iterator[Fact]:
        return iter(self._facts.values())

    def __len__(self) -> int:
        return len(self._facts)

    def format(self, fact: Fact | str) -> str:
        return self.formatter(self[fact] if isinstance(fact, str) else fact)

    def strip_currency(self, text: str) -> str:
        """Drop a currency the model typed before a money placeholder: "INR {{fact:spend}}".

        Only when the fact renders a currency of its own, so "${{fact:spend}}" keeps
        its "$" if no currency was configured."""

        def fix(m: re.Match[str]) -> str:
            fact = self.get(m["key"])
            typed = m["code"] or m["symbol"]
            known = typed in CURRENCIES or typed.startswith("Rs") or m["symbol"] is not None
            if fact is not None and fact.kind == "money" and known and self._currency(fact):
                return m["placeholder"]
            return m[0]

        return _TYPED_CURRENCY.sub(fix, text)

    def _currency(self, fact: Fact) -> str | None:
        return fact.currency or getattr(self.formatter, "currency", None)

    def render(self, text: str) -> str:
        """Replace every placeholder with its formatted value. Unknown keys raise KeyError,
        so validate first."""

        def fill(m: re.Match[str]) -> str:
            if m[1] not in self._facts:
                raise KeyError(f"unknown fact {m[1]!r}")
            return self.format(m[1])

        return PLACEHOLDER.sub(fill, self.strip_currency(text))

    def prompt(self, *, rules: bool = True) -> str:
        """The fact list for the system prompt, optionally preceded by the citation rules."""
        lines = [RULES, ""] if rules else []
        lines.append("Facts:")
        for fact in self:
            about = ", ".join(x for x in (fact.label, fact.kind, fact.source) if x)
            lines.append(f"- {fact.placeholder} = {self.format(fact)} ({about})")
        return "\n".join(lines)
