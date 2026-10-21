# factguard

[![CI](https://github.com/shivamsingh262/factguard/actions/workflows/ci.yml/badge.svg)](https://github.com/shivamsingh262/factguard/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/factguard)](https://pypi.org/project/factguard/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

Keep LLM-written text free of numbers your code didn't compute.

If an LLM writes a wrong number confidently, users stop trusting every other
number on the screen. factguard enforces one rule: **code computes every
number, the LLM only interprets.**

- Your code registers each number as a **fact**: a key, a value, a format
  (money, percent, count, ratio...) and where it came from.
- The LLM cites facts as placeholders like `{{fact:spend}}` and never types the
  digits itself.
- A **validator** rejects any literal number, unknown fact key, or date or
  duration outside the analysis window.
- On failure the model gets **one retry** with a message naming exactly what
  broke. If the retry fails too, the offending **sentences are dropped**. A
  shorter answer is better than a wrong one.

It works with any LLM and any SDK, and has no dependencies. The design comes
from a production AI analyst for marketing teams; the write-up is
[Stopping an LLM from making up numbers in an AI analyst](https://shivamsingh262.com/notes/code-computes-llm-interprets/).

## Install

```sh
pip install factguard
```

## Quick start

```python
from datetime import date
from factguard import Facts, guard

facts = Facts(currency="INR")
facts.add("spend", 61_240, "money", label="Ad spend this week")
facts.add("roas", 1.8, "ratio", label="ROAS this week")
facts.add("roas_prev", 2.4, "ratio", label="ROAS last week")

system_prompt = facts.prompt()   # the rules, plus "- {{fact:spend}} = INR 61.2K (...)"

def generate(retry):
    # Call your LLM here. On a retry, show it retry.draft and retry.feedback.
    ...

week = (date(2026, 9, 22), date(2026, 9, 28))
result = guard(generate, facts, windows=[week], user_text="Why did ROAS drop?")

result.text      # "ROAS fell from 2.4x to 1.8x while spend held at INR 61.2K."
result.dropped   # sentences removed because they still broke the rules
result.attempts  # 1 or 2
```

[`examples/anthropic_analyst.py`](examples/anthropic_analyst.py) is a complete
example using Claude.

## What counts as a violation

| Kind | Example | Why it fails |
|---|---|---|
| `literal_number` | `CPA is up 40%` | The model typed a number. Cite a fact or say it without the figure. |
| `unknown_fact` | `{{fact:f_9999.roas}}` | No such fact was computed. |
| `malformed_placeholder` | `{{spend}}` | Placeholders must be exactly `{{fact:key}}`. |
| `date` | `since Oct 3` | Dates, months and years must fall inside a window you passed. |
| `duration` | `over the last 45 days` | Durations must match the length of a window you passed. |
| `number_word` | `spend nearly doubled` | Only with `number_words=True`. |

Allowed without a fact:

- numbered list markers (`1.`, `2)`)
- attribution labels (`7-day click`, `1-day view`)
- names like `GA4`, `B2B`, `3rd-party` and `24/7`
- numbers the user typed (`user_text`), so "campaigns with ROAS below 2" can
  repeat the 2
- your own patterns: `allow=[r"SKU-\d+"]`

Without `windows`, every date and duration fails. That is deliberate: the
model shouldn't do date arithmetic. Resolve "last month" in code and pass the
window you actually queried. Pass both windows when you compare two periods.

## The pieces

**`Facts`** holds the facts for one answer.

- `facts.add(key, value, kind, label=..., currency=..., decimals=..., source=..., step=...)`
- `facts.prompt()` returns the citation rules and fact list for your system prompt.
- `facts.render(text)` replaces placeholders with formatted values. It also strips a currency the model typed in
  front of a money placeholder (`INR {{fact:spend}}`), since the fact brings its own.
- `Facts.from_records(json_data)` loads facts from JSON.

Formats: `money` renders as `INR 61.2K` or `$1.2M` (pass `Formatter(compact=False)` for `61,240`). `percent` takes
fractions, so `0.034` renders as `3.4%`. `count` renders as `12,480`, `ratio` as `2.3x`, and `text` as-is. To use
your own formatting, pass any `Callable[[Fact], str]` as `formatter=`.

**`validate(text, facts, **rules)`** returns a `Report` with `.ok`, `.violations` (kind, token, start, end) and
`.feedback`, a retry message that names each offending token.

**`guard(generate, facts, retries=1, **rules)`** runs the whole loop. `generate(None)` should return a first draft,
and `generate(retry)` a corrected one. Use `aguard` for async code.

**`StreamGuard(facts, **rules)`** checks streamed text one sentence at a time. A sentence already on screen can't
be rewritten, so a failing sentence is dropped instead of retried:

```python
sg = StreamGuard(facts, windows=[week])
for chunk in llm_stream:
    for sentence in sg.feed(chunk):
        ui.append(sentence)
for sentence in sg.close():
    ui.append(sentence)
```

**Evals.** Check every recorded answer for zero ungrounded numbers, not just for the right answer:

```python
from factguard.testing import assert_grounded

def test_recorded_answer():
    assert_grounded(answer, facts, windows=[week])
```

Or from the shell or CI:

```sh
factguard check answer.txt --facts facts.json --window 2026-09-22:2026-09-28
factguard render answer.txt --facts facts.json
```

## Trade-offs

The prose gets stiffer. Without "nearly double" or "about a third", the model
writes more literal sentences. Some sentences get dropped, and a retry adds
latency. If users have to trust the numbers before the interpretation is worth
anything, that trade is worth it.

Placeholders don't stop the model from citing the *wrong* fact, so keep fact
labels clear and test with recorded questions. And `number_words` is a
heuristic: it is off by default because words like "half" are often harmless.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports with a sentence that was
wrongly flagged or wrongly let through are especially useful.

## License

[MIT](LICENSE)
