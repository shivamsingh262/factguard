"""The validate, retry once, then drop loop around any LLM call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .facts import Facts
from .sentences import drop_sentences, split_sentences
from .validate import Report, Violation, validate


@dataclass(frozen=True)
class Retry:
    """Handed to your generate function when the previous draft failed."""

    draft: str
    report: Report

    @property
    def feedback(self) -> str:
        return self.report.feedback


@dataclass(frozen=True)
class Result:
    text: str  # rendered: placeholders replaced with formatted values
    raw: str  # the accepted text, still with placeholders
    attempts: int
    dropped: tuple[str, ...]  # sentences removed because they still broke the rules
    violations: tuple[Violation, ...]  # what the last draft got wrong

    @property
    def clean(self) -> bool:
        """True when nothing had to be dropped."""
        return not self.dropped


def _reusable(rules: dict[str, Any]) -> dict[str, Any]:
    # validate() runs several times with the same rules; a generator passed as
    # windows or allow would be used up by the first call.
    return {k: tuple(v) if k in ("windows", "allow") else v for k, v in rules.items()}


def _finish(draft: str, report: Report, facts: Facts, attempts: int, rules: dict[str, Any]) -> Result:
    if report.ok:
        return Result(facts.render(draft), draft, attempts, (), ())
    kept, dropped = draft, []
    current = report
    # One pass is enough for local violations; loop in case a drop changes what a
    # later sentence means (a list marker that lost its line, say).
    for _ in range(3):
        kept, more = drop_sentences(kept, [(v.start, v.end) for v in current.violations])
        dropped += more
        current = validate(kept, facts, **rules)
        if current.ok:
            break
    else:
        kept, dropped = "", dropped + [kept]
    return Result(facts.render(kept), kept, attempts, tuple(dropped), report.violations)


def guard(
    generate: Callable[[Retry | None], str],
    facts: Facts,
    *,
    retries: int = 1,
    **rules: Any,
) -> Result:
    """Call generate(None) for a draft. If it breaks the rules, call generate(Retry)
    up to `retries` times. If the last draft still fails, drop the offending sentences.

    rules are passed to validate(): windows, user_text, allow, number_words, ...
    """
    rules = _reusable(rules)
    retry = None
    attempts = 0
    while True:
        attempts += 1
        draft = generate(retry)
        report = validate(draft, facts, **rules)
        if report.ok or attempts > retries:
            return _finish(draft, report, facts, attempts, rules)
        retry = Retry(draft, report)


async def aguard(
    generate: Callable[[Retry | None], Awaitable[str]],
    facts: Facts,
    *,
    retries: int = 1,
    **rules: Any,
) -> Result:
    """guard() for an async generate function."""
    rules = _reusable(rules)
    retry = None
    attempts = 0
    while True:
        attempts += 1
        draft = await generate(retry)
        report = validate(draft, facts, **rules)
        if report.ok or attempts > retries:
            return _finish(draft, report, facts, attempts, rules)
        retry = Retry(draft, report)


class StreamGuard:
    """Validates streamed text sentence by sentence.

    A sentence already on screen can't be rewritten, so a failing sentence is
    dropped rather than retried.

        sg = StreamGuard(facts, windows=[window])
        for chunk in stream:
            for sentence in sg.feed(chunk):
                show(sentence)
        for sentence in sg.close():
            show(sentence)
    """

    def __init__(self, facts: Facts, **rules: Any) -> None:
        self.facts = facts
        self.rules = _reusable(rules)
        self.dropped: list[str] = []
        self.violations: list[Violation] = []
        self._buffer = ""
        self._line_closed = True

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        pieces = split_sentences(self._buffer)
        # The last piece may still be growing.
        self._buffer = pieces.pop() if pieces else ""
        return [out for piece in pieces if (out := self._check(piece))]

    def close(self) -> list[str]:
        rest, self._buffer = self._buffer, ""
        out = self._check(rest) if rest else ""
        return [out] if out else []

    def _check(self, piece: str) -> str:
        report = validate(piece, self.facts, **self.rules)
        if report.ok:
            self._line_closed = piece.endswith("\n")
            return self.facts.render(piece)
        self.dropped.append(piece.strip())
        self.violations.extend(report.violations)
        # Same rule as drop_sentences: close the line only if it isn't closed already.
        ends_line = "\n" in piece[len(piece.rstrip()) :]
        return "\n" if ends_line and not self._line_closed else ""
