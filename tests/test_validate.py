import re
from datetime import date

import pytest

from factguard import Facts, validate

SEPT = (date(2026, 9, 1), date(2026, 9, 28))
PREV = (date(2026, 8, 4), date(2026, 8, 31))


@pytest.fixture
def facts():
    f = Facts(currency="INR")
    f.add("f_3a9c.spend", 60_000, "money")
    f.add("f_3a9c.purchases", 412, "count")
    f.add("roas", 2.3, "ratio")
    return f


def kinds(report):
    return [(v.kind, v.token) for v in report.violations]


def test_placeholders_only_passes(facts):
    report = validate("Spend rose to {{fact:f_3a9c.spend}} while purchases fell to {{fact:f_3a9c.purchases}}.", facts)
    assert report.ok
    assert bool(report)
    assert report.feedback == ""


def test_unknown_key(facts):
    report = validate("ROAS was {{fact:f_9999.roas}}.", facts)
    assert kinds(report) == [("unknown_fact", "{{fact:f_9999.roas}}")]
    assert "`f_9999.roas` is not a known fact key" in report.feedback


def test_malformed_placeholder(facts):
    assert kinds(validate("Spend was {{spend}} and {fact:roas}.", facts)) == [
        ("malformed_placeholder", "{{spend}}"),
        ("malformed_placeholder", "{fact:roas}"),
    ]


@pytest.mark.parametrize("token", ["40%", "INR60K", "$1.2M", "2.3x", "1,200", "-12%", "Q3", "3.5"])
def test_any_literal_number_fails(facts, token):
    report = validate(f"CPA is up ({token}) this week.", facts)
    assert kinds(report) == [("literal_number", token)]


def test_violation_offsets_point_at_the_token(facts):
    text = "Spend {{fact:f_3a9c.spend}}, up 40%."
    (v,) = validate(text, facts).violations
    assert text[v.start : v.end] == "40%"


def test_list_markers_and_attribution_labels_are_allowed(facts):
    text = "1. Spend was {{fact:f_3a9c.spend}}.\n2) ROAS was {{fact:roas}} on 7-day click.\n- 3. nested\n"
    assert validate(text, facts).ok
    assert not validate(text, facts, list_markers=False).ok
    assert kinds(validate("Using 1-day view.", facts, attribution_labels=False)) == [("duration", "1-day")]


def test_numbers_the_user_wrote_may_be_repeated(facts):
    report = validate(
        "Campaigns with ROAS below 2: none. Also 40% is new.", facts, user_text="Show campaigns with ROAS below 2."
    )
    assert kinds(report) == [("literal_number", "40%")]
    assert validate("Below 2x.", facts, user_text="ROAS below 2").ok
    assert validate("Over $1,500.", facts, user_text="spend over 1.5k").ok


def test_custom_allow_patterns(facts):
    assert validate("See GA4 and SKU-118.", facts, allow=[r"\bGA4\b", re.compile(r"SKU-\d+")]).ok


def test_dates_need_a_window(facts):
    report = validate("Since 2026-09-03, spend fell.", facts)
    assert kinds(report) == [("date", "2026-09-03")]
    assert "none was given" in report.feedback


@pytest.mark.parametrize(
    "phrase", ["2026-09-03", "Sep 3", "September 3, 2026", "3rd September", "September 2026", "2026"]
)
def test_dates_inside_the_window_pass(facts, phrase):
    assert validate(f"Since {phrase}, spend fell.", facts, windows=[SEPT]).ok


@pytest.mark.parametrize("phrase", ["2026-10-03", "Oct 3", "July 2026", "2024", "Sep 30"])
def test_dates_outside_the_window_fail(facts, phrase):
    report = validate(f"Since {phrase}, spend fell.", facts, windows=[SEPT])
    assert kinds(report) == [("date", phrase)]
    assert "2026-09-01 to 2026-09-28" in report.feedback


def test_invalid_date_fails(facts):
    assert not validate("On 2026-02-30 spend fell.", facts, windows=[SEPT]).ok


@pytest.mark.parametrize("phrase", ["the last 28 days", "a 28-day window", "4 weeks", "1 month"])
def test_durations_matching_a_window_pass(facts, phrase):
    assert validate(f"Over {phrase}, spend fell.", facts, windows=[SEPT]).ok


def test_durations_not_matching_any_window_fail(facts):
    report = validate("Over the last 45 days, spend fell.", facts, windows=[SEPT, PREV])
    assert kinds(report) == [("duration", "45 days")]


def test_number_words_are_opt_in(facts):
    text = "Spend nearly doubled, about twenty campaigns, one of them tenfold."
    assert validate(text, facts).ok
    assert kinds(validate(text, facts, number_words=True)) == [
        ("number_word", "doubled"),
        ("number_word", "twenty"),
        ("number_word", "tenfold"),
    ]


def test_feedback_lists_each_token_once(facts):
    report = validate("Up 40%. Again 40%. And {{fact:x}}.", facts)
    assert report.feedback.count("`40%`") == 1
    assert len(report.violations) == 3


def test_common_terms_are_allowed(facts):
    text = "Check GA4 and 3rd-party cookies for B2B, 24/7."
    assert validate(text, facts).ok
    assert kinds(validate(text, facts, terms=False)) == [
        ("literal_number", "GA4"),
        ("literal_number", "3rd-party"),
        ("literal_number", "B2B"),
        ("literal_number", "24/7"),
    ]
