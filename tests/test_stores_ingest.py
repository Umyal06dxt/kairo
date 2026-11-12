import numpy as np
from qdrant_client import AsyncQdrantClient

from kairo.ingest import chunk_documents, chunk_text, index_documents, load_documents
from kairo.providers.faiss_store import FaissStore
from kairo.providers.fake import HashEmbedder
from kairo.providers.qdrant_ import QdrantStore
from kairo.types import Chunk


def test_chunk_text_bounds_overlap_empty():
    assert chunk_text("") == [] and chunk_text("  \n ") == []
    assert chunk_text("short text") == ["short text"]
    text = " ".join(f"w{i}" for i in range(400))
    chunks = chunk_text(text, 512, 50)
    assert len(chunks) > 1 and all(len(c) <= 512 for c in chunks)
    assert chunks[1].split()[0] in chunks[0].split()[-15:]  # overlap present
    covered = " ".join(chunks)
    assert "w0" in covered and "w399" in covered


def test_chunk_text_unbroken_string_is_hard_split():
    chunks = chunk_text("x" * 1500, 512, 50)
    assert all(len(c) <= 512 for c in chunks) and sum(len(c) for c in chunks) >= 1500


def test_load_and_chunk_documents(tmp_path):
    (tmp_path / "a.md").write_text("alpha " * 200)
    (tmp_path / "b.txt").write_text("beta")
    (tmp_path / "skip.bin").write_text("zzz")
    docs = load_documents(tmp_path)
    assert [n for n, _ in docs] == ["a.md", "b.txt"]
    chunks = chunk_documents(docs)
    assert chunks[0].id == "a.md:0" and chunks[-1].meta["source"] == "b.txt"


async def test_faiss_store_roundtrip(tmp_path):
    emb = HashEmbedder(dim=64)
    texts = ["pricing plans", "api endpoint"]
    store = FaissStore(emb.dim)
    assert await store.search((await emb.embed(["x"]))[0], 3) == []
    await store.add([Chunk("p", texts[0], {"s": 1}), Chunk("a", texts[1])], await emb.embed(texts))
    store.save(tmp_path / "idx")
    loaded = FaissStore.load(tmp_path / "idx")
    res = await loaded.search((await emb.embed(["pricing"]))[0], 5)
    assert res[0].chunk.id == "p" and res[0].chunk.meta == {"s": 1}
    assert len(res) == 2 and res[0].embedding.shape == (64,)


async def test_index_documents_into_faiss():
    emb = HashEmbedder(dim=64)
    store = FaissStore(emb.dim)
    n = await index_documents([("d.md", "hello world " * 100)], emb, store, size=100, overlap=10)
    assert n == len(store) and n > 1


async def test_qdrant_store_in_memory():
    emb = HashEmbedder(dim=64)
    store = QdrantStore(emb.dim, client=AsyncQdrantClient(":memory:"))
    texts = ["pricing plans", "api endpoint"]
    await store.add([Chunk("p", texts[0], {"source": "x"}), Chunk("a", texts[1])],
                    await emb.embed(texts))
    res = await store.search((await emb.embed(["pricing"]))[0], 2)
    assert res[0].chunk.id == "p" and res[0].chunk.meta == {"source": "x"}
    assert res[0].embedding.shape == (64,) and np.isfinite(res[0].score)
