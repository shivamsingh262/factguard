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

# Stand-in for your own queries: one row of metrics per week.
weekly = {
    this_week: {"spend": 61_240, "roas": 1.8, "ctr": 0.0121},
    last_week: {"spend": 59_800, "roas": 2.4, "ctr": 0.0184},
}

# How each metric is described and formatted: key -> (kind, label, source, extra fields).
metrics = {
    "spend": ("money", "Ad spend", "meta_ads", {}),
    "roas": ("ratio", "ROAS", "shopify + meta_ads", {}),
    "ctr": ("percent", "CTR", "meta_ads", {"decimals": 2}),
}

facts = Facts(currency="INR")
this, prev = weekly[this_week], weekly[last_week]
for key, (kind, label, source, extra) in metrics.items():
    facts.add(key, this[key], kind, label=f"{label} this week", source=source, **extra)
    facts.add(f"{key}_prev", prev[key], kind, label=f"{label} last week", source=source, **extra)
facts.add("top_ad", "Summer UGC v3", "text", label="Ad set with the biggest CTR drop", source="meta_ads")

question = "Why did ROAS drop this week?"
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
