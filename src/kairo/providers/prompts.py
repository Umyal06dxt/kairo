"""Provider-neutral prompts and helpers shared by all LLM backends."""

import json
import re

from ..types import Chunk
from .base import History

ANSWER_SYSTEM = (
    "You are Kairo, a voice assistant. Answer the user's question using only the "
    "provided context. Replies are spoken aloud: answer in at most two short "
    "sentences (under 35 words) and give only what was asked, not every detail. "
    "Plain prose, no markdown, lists or URLs. If the context does not contain "
    "the answer, say you don't have that information."
)

PREDICT_SYSTEM = (
    "You predict what a user will ask about next in a voice conversation with a "
    "knowledge-base assistant. Output ONLY a JSON array of strings. Each string "
    "must be a short document-style description of the content that would answer "
    "the likely follow-up (e.g. \"Enterprise plan pricing and annual billing "
    "discounts\"), not a question."
)


def parse_topics(text: str, n: int) -> list[str]:
    """Tolerantly extract a JSON string list; return [] on anything malformed."""
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [s.strip() for s in data if isinstance(s, str) and s.strip()][:n]


def format_context(context: list[Chunk]) -> str:
    return "\n\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(context)) or "(none)"


def build_messages(history: History, final_user: str) -> list[dict]:
    """Alternating user/assistant messages, starting with user, ending with final_user."""
    msgs: list[dict] = []
    for role, text in history:
        role = "assistant" if role in ("assistant", "agent") else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + text
        else:
            msgs.append({"role": role, "content": text})
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n\n" + final_user
    else:
        msgs.append({"role": "user", "content": final_user})
    if msgs[0]["role"] != "user":
        msgs.insert(0, {"role": "user", "content": "(conversation start)"})
    return msgs


def answer_prompt(question: str, context: list[Chunk]) -> str:
    return f"Context:\n{format_context(context)}\n\nQuestion: {question}"
