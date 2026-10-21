import pytest

from factguard import drop_sentences, split_sentences


@pytest.mark.parametrize(
    "text",
    [
        "One. Two! Three?",
        "Spend rose to {{fact:f_3a9c.spend}}. ROAS fell.",
        "Intro:\n- first point.\n- second point\n\n## Next\nMore text.",
        "1. Spend rose. It was big.\n2. ROAS fell.",
        "We compared channels, e.g. Meta vs. Google. Then stopped.",
        '"Quoted." Next one.',
    ],
)
def test_split_round_trips(text):
    assert "".join(split_sentences(text)) == text


def test_split_points():
    assert split_sentences("Spend rose to {{fact:a.b}}. ROAS was 2.3x! Done") == [
        "Spend rose to {{fact:a.b}}. ",
        "ROAS was 2.3x! ",
        "Done",
    ]
    assert split_sentences("1. Spend rose. It was big.") == ["1. Spend rose. ", "It was big."]
    assert split_sentences("Like e.g. Meta. Next.") == ["Like e.g. Meta. ", "Next."]


def test_drop_middle_sentence():
    text = "Spend rose. CPA is up 40%. ROAS fell."
    kept, dropped = drop_sentences(text, [(text.index("40%"), text.index("40%") + 3)])
    assert kept == "Spend rose. ROAS fell."
    assert dropped == ["CPA is up 40%."]


def test_drop_bullet_keeps_list_shape():
    text = "Findings:\n- Spend rose.\n- CPA is up 40%.\n- ROAS fell.\n"
    start = text.index("40%")
    kept, dropped = drop_sentences(text, [(start, start + 3)])
    assert kept == "Findings:\n- Spend rose.\n- ROAS fell."
    assert dropped == ["- CPA is up 40%."]


def test_drop_nothing():
    assert drop_sentences("Fine. Text.", []) == ("Fine. Text.", [])
