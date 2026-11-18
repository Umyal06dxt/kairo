import asyncio
from argparse import Namespace

import pytest

from kairo import cli
from kairo.providers.faiss_store import FaissStore


class Emb:
    def __init__(self, dim):
        self.dim = dim


def test_missing_index_exits_with_hint(tmp_path):
    with pytest.raises(SystemExit) as e:
        cli._store(Namespace(store="faiss", index=str(tmp_path / "none")), Emb(8), "local:x")
    assert "kairo ingest" in str(e.value)


def test_dimension_mismatch_exits_clearly(tmp_path):
    FaissStore(4).save(tmp_path / "idx")
    args = Namespace(store="faiss", index=str(tmp_path / "idx"))
    with pytest.raises(SystemExit) as e:
        cli._store(args, Emb(8), "local:x")
    assert "4-d" in str(e.value) and "8-d" in str(e.value)
    assert cli._store(args, Emb(4), "local:x").dim == 4


def test_embedder_mismatch_between_ingest_and_query_is_caught(tmp_path):
    FaissStore(4).save(tmp_path / "idx", {"embedder": "openai:text-embedding-3-small"})
    args = Namespace(store="faiss", index=str(tmp_path / "idx"))
    with pytest.raises(SystemExit) as e:
        cli._store(args, Emb(4), "local:BAAI/bge-small-en-v1.5")
    assert "openai:text-embedding-3-small" in str(e.value)
    assert cli._store(args, Emb(4), "openai:text-embedding-3-small").meta["embedder"]


def test_unknown_embed_model_rejected():
    from kairo.providers.openai_ import OpenAIEmbedder
    with pytest.raises(ValueError, match="unknown embedding model"):
        OpenAIEmbedder("nope", client=object())


def test_bench_rejects_unknown_profile(monkeypatch):
    monkeypatch.delenv("QDRANT_URL", raising=False)
    args = Namespace(llm="extractive", embedder="hash", qdrant=False, profiles="paper,bogus")
    with pytest.raises(SystemExit) as e:
        asyncio.run(cli.cmd_bench(args))
    assert "bogus" in str(e.value)


async def test_chat_survives_turn_error(monkeypatch, capsys):
    class R:
        def __init__(self):
            self.calls, self.cache = 0, []

        async def warmup(self): ...
        async def start(self): ...
        async def stop(self): ...

        async def handle_utterance(self, text, on_token=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("rate limited")
            on_token("ok")
            from kairo.fast_talker import TurnResult
            return TurnResult("ok", hit=True, source="cache")

    r = R()
    monkeypatch.setattr(cli, "_router", lambda args: r)
    inputs = iter(["q1", "q2", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    await cli.cmd_chat(Namespace(profile="optimized"))
    out = capsys.readouterr().out
    assert "rate limited" in out and "cache HIT" in out and r.calls == 2


def test_bench_qdrant_requires_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("QDRANT_URL", raising=False)
    args = Namespace(llm="openai", embedder="local", qdrant=True)
    with pytest.raises(SystemExit) as e:
        asyncio.run(cli.cmd_bench(args))
    assert "QDRANT_URL" in str(e.value)
