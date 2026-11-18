"""kairo CLI: ingest | chat | voice | bench   (GPT is the only LLM backend)."""

import argparse
import asyncio
import os
import sys

from .config import Config
from .ingest import index_documents, load_documents
from .providers.faiss_store import FaissStore
from .providers.openai_ import OpenAIEmbedder, OpenAILLM
from .router import MemoryRouter


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, '#' comments, optional quotes.
    Never overrides variables already set in the real environment."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.removeprefix("export ").strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


def _need_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set (export it, or put it in your shell profile).")


def _store(args, dim: int):
    if args.store == "qdrant":
        from .providers.qdrant_ import QdrantStore
        url = os.environ.get("QDRANT_URL") or sys.exit("QDRANT_URL is not set.")
        return QdrantStore(dim, args.collection, url, os.environ.get("QDRANT_API_KEY"))
    try:
        store = FaissStore.load(args.index)
    except (OSError, RuntimeError):
        sys.exit(f"No index at {args.index!r}. Run: kairo ingest --kb <docs> --index {args.index}")
    if store.dim != dim:
        sys.exit(f"Index has {store.dim}-d vectors but --embed-model gives {dim}-d. "
                 f"Re-ingest with the same --embed-model.")
    return store


async def cmd_ingest(args) -> None:
    _need_key()
    cfg = Config()
    docs = load_documents(args.kb)
    if not docs:
        sys.exit(f"No .md/.txt files found in {args.kb}")
    emb = OpenAIEmbedder(args.embed_model)
    if args.store == "qdrant":
        from .providers.qdrant_ import QdrantStore
        url = os.environ.get("QDRANT_URL") or sys.exit("QDRANT_URL is not set.")
        store = QdrantStore(emb.dim, args.collection, url, os.environ.get("QDRANT_API_KEY"))
    else:
        store = FaissStore(emb.dim)
    n = await index_documents(docs, emb, store, cfg.chunk_size, cfg.chunk_overlap)
    if args.store == "faiss":
        store.save(args.index)
    print(f"Indexed {n} chunks from {len(docs)} documents "
          f"-> {args.index if args.store == 'faiss' else args.collection}")


def _router(args) -> MemoryRouter:
    _need_key()
    cfg = Config()
    emb = OpenAIEmbedder(args.embed_model)
    return MemoryRouter.create(emb, OpenAILLM(args.model, cfg.temperature),
                               _store(args, emb.dim), cfg)


async def cmd_chat(args) -> None:
    router = _router(args)
    await router.start()
    print("Kairo text chat. Empty line or Ctrl-D to quit.")
    hits = turns = 0
    try:
        while True:
            try:
                text = (await asyncio.to_thread(input, "you> ")).strip()
            except EOFError:
                break
            if not text:
                break
            print("kairo> ", end="", flush=True)
            try:
                r = await router.handle_utterance(
                    text, on_token=lambda t: print(t, end="", flush=True))
            except Exception as e:  # API/network error: report and keep the session alive
                print(f"\n  [error: {type(e).__name__}: {e}]")
                continue
            turns += 1
            hits += r.hit
            print(f"\n  [{'cache HIT' if r.hit else r.source}] embed={r.embed_ms:.0f}ms "
                  f"retrieval={r.retrieval_ms:.2f}ms cache={len(router.cache)} "
                  f"hit-rate={hits}/{turns}")
    finally:
        await router.stop()


async def cmd_voice(args) -> None:
    from .voice.endpoint import Endpointer
    from .voice.io import ArecordMic, EdgeTTS, WhisperSTT
    from .voice.loop import run_voice
    router = _router(args)
    print(f"Loading Whisper '{args.whisper}'…")
    stt = WhisperSTT(args.whisper)
    await run_voice(router, stt, EdgeTTS(args.voice), ArecordMic(),
                    Endpointer(threshold=args.vad_threshold, silence_ms=args.silence_ms))


async def cmd_bench(args) -> None:
    from .bench.run import format_report, run_benchmark
    if args.mode == "live":
        _need_key()
        if args.qdrant and not os.environ.get("QDRANT_URL"):
            sys.exit("--qdrant needs QDRANT_URL (and QDRANT_API_KEY) in the environment/.env.")
    taus = [0.55, 0.50, 0.45, 0.40, 0.35, 0.30] if args.sweep else None
    reports = await run_benchmark(
        args.mode, Config(), taus=taus,
        store_latency_s=None if args.store_latency_ms is None else args.store_latency_ms / 1000,
        generate=args.generate, qdrant=args.qdrant)
    text = format_report(reports)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="kairo")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, voice_or_chat: bool):
        sp.add_argument("--index", default="data/index", help="FAISS index directory")
        sp.add_argument("--store", choices=["faiss", "qdrant"], default="faiss")
        sp.add_argument("--collection", default="kairo", help="Qdrant collection")
        sp.add_argument("--embed-model", default="text-embedding-3-small")
        if voice_or_chat:
            sp.add_argument("--model", default="gpt-4o-mini")

    sp = sub.add_parser("ingest", help="chunk, embed and index a folder of .md/.txt files")
    sp.add_argument("--kb", required=True)
    common(sp, False)
    sp.set_defaults(fn=cmd_ingest)

    sp = sub.add_parser("chat", help="text REPL over your index")
    common(sp, True)
    sp.set_defaults(fn=cmd_chat)

    sp = sub.add_parser("voice", help="voice conversation (mic -> Whisper -> RAG -> Edge TTS)")
    common(sp, True)
    sp.add_argument("--whisper", default="base.en")
    sp.add_argument("--voice", default="en-US-AriaNeural")
    sp.add_argument("--vad-threshold", type=float, default=0.015)
    sp.add_argument("--silence-ms", type=int, default=700)
    sp.set_defaults(fn=cmd_voice)

    sp = sub.add_parser("bench", help="run the 200-query benchmark")
    sp.add_argument("--mode", choices=["offline", "live"], default="offline")
    sp.add_argument("--sweep", action="store_true", help="threshold sweep 0.30-0.55")
    sp.add_argument("--store-latency-ms", type=float, default=None)
    sp.add_argument("--generate", action="store_true", help="live: also generate answers")
    sp.add_argument("--qdrant", action="store_true", help="live: use Qdrant (QDRANT_URL)")
    sp.add_argument("--out", help="write the markdown report here")
    sp.set_defaults(fn=cmd_bench)

    args = p.parse_args(argv)
    load_dotenv()
    try:
        asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
