from types import SimpleNamespace as NS

import numpy as np

from kairo.providers.openai_ import OpenAIEmbedder, OpenAILLM
from kairo.types import Chunk


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    async def create(self, model, input):
        self.calls.append((model, input))
        # return out of order to prove we sort by index
        data = [NS(index=i, embedding=[3.0, 4.0] + [0.0] * 1534) for i in range(len(input))]
        return NS(data=list(reversed(data)))


async def test_embedder_normalises_and_batches():
    emb = FakeEmbeddings()
    e = OpenAIEmbedder(client=NS(embeddings=emb))
    out = await e.embed(["a", "b"])
    assert e.dim == 1536 and out.shape == (2, 1536)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
    assert len(emb.calls) == 1 and emb.calls[0][0] == "text-embedding-3-small"
    assert (await e.embed([])).shape == (0, 1536)
    assert len(emb.calls) == 1  # empty input makes no API call


class FakeChat:
    def __init__(self, text):
        self.calls, self._text = [], text
        self.completions = self

    async def create(self, **kw):
        self.calls.append(kw)
        if kw.get("stream"):
            async def gen():
                for t in ["Hel", "lo", None]:
                    yield NS(choices=[NS(delta=NS(content=t))])
                yield NS(choices=[])
            return gen()
        return NS(choices=[NS(message=NS(content=self._text))])


async def test_llm_predict_and_stream():
    chat = FakeChat('["pricing tiers", "sso"]')
    llm = OpenAILLM(client=NS(chat=chat))
    assert await llm.predict_topics([("user", "hi")], 5) == ["pricing tiers", "sso"]
    assert chat.calls[0]["temperature"] == 0.3
    toks = [t async for t in llm.stream_answer("q?", [Chunk("1", "ctx text")], [("user", "hi")])]
    assert "".join(toks) == "Hello"
    msgs = chat.calls[1]["messages"]
    assert msgs[0]["role"] == "system" and "ctx text" in msgs[-1]["content"]
