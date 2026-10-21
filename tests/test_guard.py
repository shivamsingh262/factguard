import asyncio
from datetime import date

import pytest

from factguard import Facts, Retry, StreamGuard, aguard, guard
from factguard.testing import assert_grounded


@pytest.fixture
def facts():
    f = Facts(currency="INR")
    f.add("spend", 60_000, "money")
    f.add("purchases", 412, "count")
    return f


def scripted(*drafts):
    """A fake LLM that returns drafts in order and records what it was asked."""
    calls: list[Retry | None] = []

    def generate(retry):
        calls.append(retry)
        return drafts[len(calls) - 1]

    return generate, calls


def test_clean_first_draft(facts):
    generate, calls = scripted("Spend rose to {{fact:spend}}.")
    result = guard(generate, facts)
    assert result.text == "Spend rose to INR 60K."
    assert result.raw == "Spend rose to {{fact:spend}}."
    assert result.attempts == 1
    assert result.clean
    assert calls == [None]


def test_retry_fixes_it(facts):
    generate, calls = scripted("Spend rose 40% to {{fact:spend}}.", "Spend rose to {{fact:spend}}.")
    result = guard(generate, facts)
    assert result.text == "Spend rose to INR 60K."
    assert result.attempts == 2
    assert calls[1].draft == "Spend rose 40% to {{fact:spend}}."
    assert "`40%`" in calls[1].feedback


def test_drops_sentences_when_retry_fails(facts):
    generate, _ = scripted(
        "Spend rose 40%. Purchases fell.",
        "Spend rose to {{fact:spend}}. Purchases fell to {{fact:purchases}}, a 12% drop. Worth a look.",
    )
    result = guard(generate, facts)
    assert result.text == "Spend rose to INR 60K. Worth a look."
    assert result.dropped == ("Purchases fell to {{fact:purchases}}, a 12% drop.",)
    assert [v.token for v in result.violations] == ["12%"]
    assert not result.clean


def test_unknown_fact_is_dropped_not_rendered(facts):
    generate, _ = scripted("ROAS was {{fact:roas}}. Spend was {{fact:spend}}.", "ROAS was {{fact:roas}}.  Fine.")
    result = guard(generate, facts)
    assert result.text == "Fine."


def test_retries_zero_and_rules_pass_through(facts):
    window = (date(2026, 9, 1), date(2026, 9, 28))
    generate, calls = scripted("Over the last 28 days spend was {{fact:spend}}. Over 45 days it was flat.")
    result = guard(generate, facts, retries=0, windows=[window])
    assert len(calls) == 1
    assert result.text == "Over the last 28 days spend was INR 60K."


def test_everything_dropped(facts):
    generate, _ = scripted("Up 40%.", "Up 41%.")
    result = guard(generate, facts)
    assert result.text == ""
    assert result.dropped == ("Up 41%.",)


def test_aguard(facts):
    async def generate(retry):
        return "Spend was {{fact:spend}}." if retry else "Spend was 60K."

    result = asyncio.run(aguard(generate, facts))
    assert result.text == "Spend was INR 60K."
    assert result.attempts == 2


def test_stream_guard(facts):
    sg = StreamGuard(facts)
    out = []
    for chunk in ["Spend rose to {{fact:sp", "end}}. CPA is", " up 40%. Purchases were {{fact:purch", "ases}}."]:
        out += sg.feed(chunk)
    assert out == ["Spend rose to INR 60K. "]
    out += sg.close()
    assert "".join(out) == "Spend rose to INR 60K. Purchases were 412."
    assert sg.dropped == ["CPA is up 40%."]
    assert sg.close() == []


def test_stream_guard_keeps_line_breaks(facts):
    sg = StreamGuard(facts)
    out = sg.feed("- Spend {{fact:spend}}\n- Up 40%\n- Purchases {{fact:purchases}}\n") + sg.close()
    assert "".join(out) == "- Spend INR 60K\n- Purchases 412\n"


def test_assert_grounded(facts):
    assert assert_grounded("Spend {{fact:spend}}.", facts).ok
    with pytest.raises(AssertionError, match="40%"):
        assert_grounded("Spend up 40%.", facts)
