"""Near-domain distractor pages, so a benchmark KB looks like a real (much larger) credit-union
knowledge base instead of 12 documents. GPT writes plausible pages for OTHER products and
services of the same fictional institution; they share vocabulary with the gold documents, so
retrieval must tell, e.g., student loans from auto loans. Generated once, cached under data/,
never committed. Gold facts are protected by instructing the writer to avoid those topics."""

import asyncio
import json
from pathlib import Path

TOPICS = [
    "Business Checking", "Student Checking", "Senior Checking", "Holiday Club Savings",
    "Traditional IRA", "Roth IRA", "IRA rollovers", "Health Savings Account", "Money Market account",
    "Foreign currency exchange", "Coin counting kiosk", "Cashier's checks", "Money orders",
    "Gift cards", "Business bill pay", "Merchant card processing", "Small business loans",
    "SBA loans", "Commercial real estate loans", "Equipment financing", "Student loans",
    "Student loan refinancing", "RV and boat loans", "Motorcycle loans", "Debt consolidation loans",
    "Credit builder loans", "Secured credit cards", "Business credit cards", "Home insurance referral",
    "Auto insurance referral", "Life insurance", "Identity theft protection", "Credit monitoring",
    "Financial wellness workshops", "One-on-one financial counseling", "Tax preparation partners",
    "Estate planning referral", "Trust services", "Investment services", "Annuities",
    "529 college savings", "Direct deposit setup", "Payroll cards", "Dormant accounts",
    "Closing an account", "Name change on accounts", "Power of attorney", "Accounts of deceased members",
    "Custodial accounts for minors", "ATM locations and shared branching", "Digital wallets",
    "Card controls and spending limits", "Rewards redemption", "Spending insights tool",
    "Account alerts", "Electronic statements", "Tax forms 1099 and 1098", "Lien and levy holds",
    "Garnishment of accounts", "Military and veteran benefits", "Community grants and sponsorships",
    "Annual meeting and board elections", "Careers at the credit union", "Accessibility services",
    "Language assistance", "Check ordering", "Positive pay for businesses", "Lockbox services",
]

AVOID = ("overdraft fees, wire transfer fees and cutoffs, ACH timing, debit card activation, "
         "replacement or freezing, lost or stolen cards, fraud reporting, disputes, online banking "
         "login or password reset, mobile deposit limits, auto loan rates, personal loan rates, "
         "mortgage and HELOC rates, credit card cash back, branch hours, membership eligibility, "
         "NCUA insurance, Everyday/Premier Checking and savings APYs")

PROMPT = (
    "Write a short knowledge-base page (90-140 words, plain prose, one heading line) about "
    "\"{topic}\" for Harbor Federal Credit Union, a fictional credit union in Maryland. Include "
    "2-4 specific but invented facts (a fee, limit, rate, deadline or phone extension). Do NOT "
    "mention any of these topics, which are documented elsewhere: " + AVOID + ".")


async def _generate(topics: list[str], model: str = "gpt-4o-mini", concurrency: int = 8) -> dict[str, str]:
    import openai
    client = openai.AsyncOpenAI(max_retries=4, timeout=60.0)
    sem = asyncio.Semaphore(concurrency)

    async def one(topic: str) -> tuple[str, str]:
        async with sem:
            r = await client.chat.completions.create(
                model=model, temperature=0.7, max_completion_tokens=300,
                messages=[{"role": "user", "content": PROMPT.format(topic=topic)}])
            return topic, (r.choices[0].message.content or "").strip()

    return dict(await asyncio.gather(*(one(t) for t in topics)))


def load_distractors(n: int, cache: str | Path = "data/distractors_bank.json") -> dict[str, str]:
    """name -> text for the first `n` topics (generated on first use; needs OPENAI_API_KEY)."""
    path = Path(cache)
    data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}
    missing = [t for t in TOPICS[:n] if t not in data]
    if missing:
        data.update(asyncio.run(_generate(missing)) if not _in_loop() else {})
        if any(t not in data for t in missing):
            raise RuntimeError("distractors must be generated outside a running event loop; "
                               "run `kairo make-distractors` first")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    out = {}
    for topic in TOPICS[:n]:
        name = "extra_" + "".join(c if c.isalnum() else "_" for c in topic) + ".md"
        out[name] = data[topic]
    return out


def _in_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def cached_distractors(n: int, cache: str | Path = "data/distractors_bank.json") -> dict[str, str]:
    """Like load_distractors but never generates: {} when the cache file doesn't exist."""
    return load_distractors(n, cache) if Path(cache).exists() else {}
