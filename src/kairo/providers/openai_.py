"""OpenAI-backed Embedder (paper default: text-embedding-3-small, 1536-d) and LLM
(paper default: gpt-4o-mini, temperature 0.3)."""

from typing import AsyncIterator

import numpy as np
import openai

from ..types import Chunk
from .base import History
from .prompts import ANSWER_SYSTEM, PREDICT_SYSTEM, answer_prompt, build_messages, parse_topics

EMBED_DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072,
              "text-embedding-ada-002": 1536}


class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-small",
                 client: openai.AsyncOpenAI | None = None):
        if model not in EMBED_DIMS:
            raise ValueError(f"unknown embedding model {model!r}; known: {sorted(EMBED_DIMS)}")
        self.model = model
        self.dim = EMBED_DIMS[model]
        self._client = client or openai.AsyncOpenAI()

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        resp = await self._client.embeddings.create(model=self.model, input=texts)
        vecs = np.array([d.embedding for d in sorted(resp.data, key=lambda d: d.index)],
                        dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1.0, norms)


class OpenAILLM:
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.3,
                 client: openai.AsyncOpenAI | None = None):
        self.model, self.temperature = model, temperature
        self._client = client or openai.AsyncOpenAI()

    async def predict_topics(self, history: History, n: int) -> list[str]:
        convo = "\n".join(f"{r}: {t}" for r, t in history)
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_completion_tokens=1024,
            messages=[
                {"role": "system", "content": PREDICT_SYSTEM},
                {"role": "user",
                 "content": f"Conversation so far:\n{convo}\n\nGive {n} predictions."},
            ],
        )
        return parse_topics(resp.choices[0].message.content or "", n)

    async def stream_answer(self, question: str, context: list[Chunk],
                            history: History) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_completion_tokens=1024,
            stream=True,
            messages=[{"role": "system", "content": ANSWER_SYSTEM},
                      *build_messages(history, answer_prompt(question, context))],
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
