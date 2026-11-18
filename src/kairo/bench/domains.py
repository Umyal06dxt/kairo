"""A Domain = knowledge base + scripted conversations (optionally with gold answers)."""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Turn:
    q: str
    # gold facts: every entry must appear (case-insensitive) in the answer; "a|b" = either one
    expect: tuple[str, ...] | None = None
    doc: str | None = None  # source document that holds the answer


@dataclass
class Domain:
    key: str
    title: str
    blurb: str
    docs: dict[str, str]
    scenarios: dict[str, list[Turn]] = field(default_factory=dict)

    @property
    def n_turns(self) -> int:
        return sum(len(v) for v in self.scenarios.values())

    def questions(self) -> list[str]:
        return [t.q for turns in self.scenarios.values() for t in turns]


def score_answer(answer: str, expect: tuple[str, ...] | None) -> bool | None:
    """True/False against gold facts; None when the turn has no gold."""
    if not expect:
        return None
    a = answer.lower()

    def has(tok: str) -> bool:  # whole-token match: "5" must not match "5,000" or "25"
        pat = rf"(?<![a-z0-9])(?<!\d[.,]){re.escape(tok.lower())}(?![a-z0-9])(?![.,]\d)"
        return re.search(pat, a) is not None

    return all(any(has(alt) for alt in req.split("|")) for req in expect)


def _novacrm() -> Domain:
    from .kb import NOVACRM_DOCS
    from .scenarios import SCENARIOS
    return Domain(
        key="novacrm",
        title="NovaCRM - paper replication",
        blurb="Synthetic CRM product KB and the 10 scenarios modeled on VoiceAgentRAG's §3. "
              "No gold answers: used for hit-rate comparison with the paper.",
        docs=NOVACRM_DOCS,
        scenarios={k: [Turn(q) for q in v] for k, v in SCENARIOS.items()},
    )


def get_domain(key: str) -> Domain:
    if key == "novacrm":
        return _novacrm()
    if key == "bank":
        from .bank import BANK
        return BANK
    raise KeyError(f"unknown domain {key!r}; choose novacrm or bank")


DOMAIN_KEYS = ["bank", "novacrm"]
