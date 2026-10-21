# Contributing to factguard

Thanks for your interest! factguard aims to stay small, dependency-free and
easy to read, so the best contributions are focused.

## Getting started

1. Fork the repo and create a branch from `main`.
2. Install [uv](https://docs.astral.sh/uv/) and set up the project:
   ```sh
   uv sync
   uv run pytest
   ```
3. Make your change with a test, then check formatting and lint:
   ```sh
   uv run ruff format .
   uv run ruff check .
   ```
4. Open a pull request describing what you changed and why.

CI runs the tests on Python 3.10 to 3.13 on Linux, macOS and Windows, so
please make sure it stays green.

## Good first contributions

- **False positives and misses.** A sentence that was flagged but shouldn't be,
  or let through but shouldn't be. Add it as a test case first.
- **Date formats.** More ways of writing dates and periods that should be
  checked against the analysis window.
- **Formatting.** Locale-aware number formats, such as lakh and crore grouping.
- **Examples.** Short examples for other LLM SDKs.

For larger changes (new rule kinds, API changes, any new dependency), please
open an issue first so we can agree on the approach.

## Code style

- Python 3.10+, standard library only.
- Readable over clever. Prefer small functions and plain loops.
- Strict by default: a new allowance should be narrow and, where in doubt,
  opt-in.
- Write brief comments explaining *why* a rule exists.
