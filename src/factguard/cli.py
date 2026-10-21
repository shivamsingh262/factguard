"""factguard check / render, for checking recorded answers from the shell or CI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .facts import Facts
from .validate import Window, validate


def _window(value: str) -> Window:
    try:
        start, end = (date.fromisoformat(part) for part in value.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected START:END as ISO dates, got {value!r}") from None
    if start > end:
        raise argparse.ArgumentTypeError(f"window starts after it ends: {value!r}")
    return start, end


def _read(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factguard", description="Keep LLM text free of numbers code didn't compute.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="list ungrounded numbers; exit 1 if there are any")
    check.add_argument("draft", help="text file with {{fact:key}} placeholders, or - for stdin")
    check.add_argument("--facts", required=True, help="JSON file with the facts")
    check.add_argument(
        "--window",
        action="append",
        type=_window,
        default=[],
        metavar="START:END",
        help="a date range the answer used (repeatable)",
    )
    check.add_argument("--user", default="", help="the user's question; numbers in it may be repeated")
    check.add_argument("--number-words", action="store_true", help="also flag words like 'double' or 'twenty'")
    check.add_argument("--json", action="store_true", help="print violations as JSON")

    render = sub.add_parser("render", help="replace placeholders with formatted values")
    render.add_argument("draft", help="text file, or - for stdin")
    render.add_argument("--facts", required=True, help="JSON file with the facts")

    args = parser.parse_args(argv)
    try:
        facts = Facts.from_records(json.loads(_read(args.facts)))
        text = _read(args.draft)
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"factguard: {e}", file=sys.stderr)
        return 2

    if args.command == "render":
        try:
            sys.stdout.write(facts.render(text))
        except KeyError as e:
            print(f"factguard: {e.args[0]}", file=sys.stderr)
            return 1
        return 0

    report = validate(text, facts, windows=args.window, user_text=args.user, number_words=args.number_words)
    if args.json:
        print(json.dumps([v.__dict__ for v in report.violations], indent=2))
    else:
        for v in report.violations:
            line = text.count("\n", 0, v.start) + 1
            print(f"{args.draft}:{line}: {v.kind}: `{v.token}`: {v.detail}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
