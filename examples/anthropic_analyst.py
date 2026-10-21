"""Ask Claude why ROAS dropped, with every number in the answer guarded.

    pip install factguard anthropic
    export ANTHROPIC_API_KEY=...
    python examples/anthropic_analyst.py

The numbers below are made up. In a real system they come from your own
queries; the point is that code computes them and the model only cites them.
"""

from datetime import date

import anthropic

from factguard import Facts, Retry, guard

this_week = (date(2026, 9, 22), date(2026, 9, 28))
last_week = (date(2026, 9, 15), date(2026, 9, 21))

facts = Facts(currency="INR")
facts.add("spend", 61_240, "money", label="Ad spend this week", source="meta_ads")
facts.add("spend_prev", 59_800, "money", label="Ad spend last week", source="meta_ads")
facts.add("roas", 1.8, "ratio", label="ROAS this week", source="shopify + meta_ads")
facts.add("roas_prev", 2.4, "ratio", label="ROAS last week", source="shopify + meta_ads")
facts.add("ctr", 0.0121, "percent", decimals=2, label="CTR this week", source="meta_ads")
facts.add("ctr_prev", 0.0184, "percent", decimals=2, label="CTR last week", source="meta_ads")
facts.add("top_ad", "Summer UGC v3", "text", label="Ad set with the biggest CTR drop", source="meta_ads")

question = "Why did ROAS drop last week?"
system = (
    "You are a marketing analyst. Answer in a short paragraph or a few bullets.\n"
    f"This week is {this_week[0]:%b %d} to {this_week[1]:%b %d}; "
    f"it is compared with {last_week[0]:%b %d} to {last_week[1]:%b %d}.\n\n" + facts.prompt()
)

client = anthropic.Anthropic()


def generate(retry: Retry | None) -> str:
    messages = [{"role": "user", "content": question}]
    if retry:
        # Show the model its own draft and exactly what broke the rules.
        messages += [
            {"role": "assistant", "content": retry.draft},
            {"role": "user", "content": retry.feedback},
        ]
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        system=system,
        messages=messages,
        # If the model declines, the API reruns the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined to answer")
    return "".join(block.text for block in response.content if block.type == "text")


result = guard(generate, facts, windows=[this_week, last_week], user_text=question)

print(result.text)
print(f"\n[{result.attempts} attempt(s)]")
for sentence in result.dropped:
    print(f"[dropped] {sentence}")
