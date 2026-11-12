"""Document loading, recursive character chunking, and indexing."""

from pathlib import Path

from .providers.base import Embedder, VectorStore
from .types import Chunk

_SEPS = ["\n\n", "\n", ". ", " "]


def _split(text: str, size: int, seps: list[str]) -> list[str]:
    """Break text into pieces <= size, preferring the coarsest separator."""
    if len(text) <= size:
        return [text]
    if not seps:
        return [text[i:i + size] for i in range(0, len(text), size)]
    sep, rest = seps[0], seps[1:]
    parts = text.split(sep)
    parts = [p + sep for p in parts[:-1]] + [parts[-1]]
    out: list[str] = []
    for p in parts:
        out.extend(_split(p, size, rest) if len(p) > size else [p])
    return out


def chunk_text(text: str, size: int = 512, overlap: int = 50) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    cur = ""
    for piece in _split(text, size, _SEPS):
        if cur and len(cur) + len(piece) > size:
            chunks.append(cur.strip())
            tail = cur[-overlap:] if overlap else ""
            if " " in tail:  # start the overlap on a word boundary
                tail = tail.split(" ", 1)[1]
            cur = tail + piece if len(tail) + len(piece) <= size else piece
        else:
            cur += piece
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def load_documents(directory: str | Path) -> list[tuple[str, str]]:
    root = Path(directory)
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".md", ".txt"})
    return [(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")) for p in files]


def chunk_documents(docs: list[tuple[str, str]], size: int = 512,
                    overlap: int = 50) -> list[Chunk]:
    return [Chunk(f"{name}:{i}", text, {"source": name})
            for name, body in docs
            for i, text in enumerate(chunk_text(body, size, overlap))]


async def index_documents(docs: list[tuple[str, str]], embedder: Embedder,
                          store: VectorStore, size: int = 512, overlap: int = 50,
                          batch: int = 64) -> int:
    chunks = chunk_documents(docs, size, overlap)
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        await store.add(part, await embedder.embed([c.text for c in part]))
    return len(chunks)
