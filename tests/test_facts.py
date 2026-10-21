import pytest

from factguard import Fact, Facts, Formatter


@pytest.mark.parametrize(
    ("fact", "expected"),
    [
        (Fact("a", 60_240, "money", currency="INR"), "INR 60.2K"),
        (Fact("a", 60_000, "money", currency="$"), "$60K"),
        (Fact("a", 999_960, "money", currency="USD"), "USD 1M"),
        (Fact("a", 1_260_000_000, "money"), "1.3B"),
        (Fact("a", 845.5, "money", currency="€"), "€846"),
        (Fact("a", 12.5, "money", currency="USD"), "USD 12.50"),
        (Fact("a", -4_200, "money", currency="INR"), "INR -4.2K"),
        (Fact("a", 0.034, "percent"), "3.4%"),
        (Fact("a", 0.5, "percent"), "50%"),
        (Fact("a", 0.12345, "percent", decimals=2), "12.35%"),
        (Fact("a", 12_480, "count"), "12,480"),
        (Fact("a", 2.3, "ratio"), "2.3x"),
        (Fact("a", 2.0, "ratio"), "2x"),
        (Fact("a", 1234567, "number"), "1,234,567"),
        (Fact("a", 3.14159, "number"), "3.14"),
        (Fact("a", "Summer sale", "text"), "Summer sale"),
        (Fact("a", float("nan"), "number"), "n/a"),
    ],
)
def test_formatter(fact, expected):
    assert Formatter()(fact) == expected


def test_non_compact_money():
    assert Formatter(currency="INR", compact=False)(Fact("a", 60_240, "money")) == "INR 60,240"


def test_default_currency_applies_to_money_without_one():
    facts = Facts(currency="INR")
    facts.add("spend", 60_000, "money")
    facts.add("cpa", 500, "money", currency="USD")
    assert facts.format("spend") == "INR 60K"
    assert facts.format("cpa") == "USD 500"


def test_fact_validation():
    with pytest.raises(ValueError):
        Fact("has space", 1)
    with pytest.raises(ValueError):
        Fact("a", 1, "bogus")
    with pytest.raises(TypeError):
        Fact("a", "12", "money")
    with pytest.raises(TypeError):
        Fact("a", True, "count")
    facts = Facts()
    facts.add("a", 1)
    with pytest.raises(ValueError):
        facts.add("a", 2)


def test_render_replaces_placeholders():
    facts = Facts(currency="INR")
    facts.add("f_3a9c.spend", 60_000, "money")
    facts.add("f_3a9c.purchases", 412, "count")
    text = "Spend rose to {{fact:f_3a9c.spend}} while purchases fell to {{ fact:f_3a9c.purchases }}."
    assert facts.render(text) == "Spend rose to INR 60K while purchases fell to 412."


def test_render_unknown_key_raises():
    with pytest.raises(KeyError):
        Facts().render("{{fact:nope}}")


@pytest.mark.parametrize("typed", ["INR {{fact:spend}}", "INR{{fact:spend}}", "₹{{fact:spend}}", "Rs. {{fact:spend}}"])
def test_render_strips_typed_currency(typed):
    facts = Facts(currency="INR")
    facts.add("spend", 60_000, "money")
    assert facts.render(f"Spend was {typed}.") == "Spend was INR 60K."


def test_render_keeps_words_that_look_like_codes():
    facts = Facts(currency="INR")
    facts.add("cpa", 512, "money")
    facts.add("ctr", 0.021, "percent")
    assert facts.render("CPA {{fact:cpa}}, CTR {{fact:ctr}}") == "CPA INR 512, CTR 2.1%"
    # Currency in front of a non-money fact is left for the reader to see.
    assert facts.render("$ {{fact:ctr}}") == "$ 2.1%"


def test_from_records():
    facts = Facts.from_records(
        {"currency": "USD", "facts": [{"key": "spend", "value": 1500, "kind": "money"}, {"key": "name", "value": "X"}]}
    )
    assert facts.format("spend") == "USD 1.5K"
    assert facts["name"].kind == "text"
    assert Facts.from_records({"roas": 2.5})["roas"].kind == "number"


def test_prompt_lists_facts_with_rules():
    facts = Facts(currency="INR")
    facts.add("spend", 60_000, "money", label="Ad spend", source="meta_ads")
    prompt = facts.prompt()
    assert "Every number in your answer" in prompt
    assert "- {{fact:spend}} = INR 60K (Ad spend, money, meta_ads)" in prompt
    assert facts.prompt(rules=False).startswith("Facts:")
