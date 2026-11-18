"""kairo CLI: ingest | chat | voice | bench   (GPT is the only LLM backend)."""

import argparse
import asyncio
import os
import sys
import time

from .config import OPTIMIZED, PAPER, Config, for_embedder
from .ingest import index_documents, load_documents
from .providers.faiss_store import FaissStore
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
        sys.exit("OPENAI_API_KEY is not set (put it in .env or export it).")


def _embedder(name: str, model: str | None):
    """local = on-device ONNX (~5 ms/query); openai = API (~700 ms/query, paper default)."""
    if name == "local":
        from .providers.local import DEFAULT_MODEL, LocalEmbedder
        model = model or DEFAULT_MODEL
        return LocalEmbedder(model), f"local:{model}"
    from .providers.openai_ import OpenAIEmbedder
    _need_key()
    model = model or "text-embedding-3-small"
    return OpenAIEmbedder(model), f"openai:{model}"


def _store(args, emb, tag: str):
    if args.store == "qdrant":
        from .providers.qdrant_ import QdrantStore
        url = os.environ.get("QDRANT_URL") or sys.exit("QDRANT_URL is not set.")
        return QdrantStore(emb.dim, args.collection, url, os.environ.get("QDRANT_API_KEY"))
    try:
        store = FaissStore.load(args.index)
    except (OSError, RuntimeError):
        sys.exit(f"No index at {args.index!r}. Run: kairo ingest --kb <docs> --index {args.index}")
    built_with = store.meta.get("embedder")
    if built_with and built_with != tag:
        sys.exit(f"Index was built with {built_with} but you are using {tag}. "
                 f"Re-ingest, or pass the matching --embedder/--embed-model.")
    if store.dim != emb.dim:
        sys.exit(f"Index has {store.dim}-d vectors but the embedder gives {emb.dim}-d. "
                 f"Re-ingest with the same --embedder/--embed-model.")
    return store


async def cmd_ingest(args) -> None:
    cfg = Config()
    docs = load_documents(args.kb)
    if not docs:
        sys.exit(f"No .md/.txt files found in {args.kb}")
    emb, tag = _embedder(args.embedder, args.embed_model)
    if args.store == "qdrant":
        from .providers.qdrant_ import QdrantStore
        url = os.environ.get("QDRANT_URL") or sys.exit("QDRANT_URL is not set.")
        store = QdrantStore(emb.dim, args.collection, url, os.environ.get("QDRANT_API_KEY"))
    else:
        store = FaissStore(emb.dim)
    n = await index_documents(docs, emb, store, cfg.chunk_size, cfg.chunk_overlap)
    if args.store == "faiss":
        store.save(args.index, {"embedder": tag})
    print(f"Indexed {n} chunks from {len(docs)} documents with {tag} "
          f"-> {args.index if args.store == 'faiss' else args.collection}")


def _router(args) -> MemoryRouter:
    from .providers.openai_ import OpenAILLM
    _need_key()  # GPT answers and predictions
    cfg = for_embedder(OPTIMIZED if args.profile == "optimized" else PAPER, args.embedder)
    emb, tag = _embedder(args.embedder, args.embed_model)
    return MemoryRouter.create(emb, OpenAILLM(args.model, cfg.temperature),
                               _store(args, emb, tag), cfg)


async def cmd_chat(args) -> None:
    router = _router(args)
    await router.warmup()
    await router.start()
    print(f"Kairo text chat ({args.profile} profile). Empty line or Ctrl-D to quit.")
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
            label = {"draft": "DRAFT HIT", "cache": "cache HIT"}.get(r.source, r.source)
            print(f"\n  [{label}] embed={r.embed_ms:.0f}ms retrieval={r.retrieval_ms:.2f}ms "
                  f"cache={len(router.cache)} hit-rate={hits}/{turns}")
    finally:
        await router.stop()


async def cmd_voice(args) -> None:
    from .voice.endpoint import Endpointer
    from .voice.io import ArecordMic, EdgeTTS, WhisperSTT
    from .voice.loop import run_voice
    router = _router(args)
    print(f"Loading Whisper '{args.whisper}'…")
    stt = WhisperSTT(args.whisper)
    await router.warmup()
    kw = {} if args.vad_threshold is None else {"threshold": args.vad_threshold}
    await run_voice(router, stt, EdgeTTS(args.voice), ArecordMic(),
                    Endpointer(silence_ms=args.silence_ms, **kw))


async def cmd_bench(args) -> None:
    from .bench.run import PROFILES, format_experiment, parse_overrides, run_experiment
    if args.llm == "openai" or args.embedder == "openai":
        _need_key()
    if args.qdrant and not os.environ.get("QDRANT_URL"):
        sys.exit("--qdrant needs QDRANT_URL (and QDRANT_API_KEY) in the environment/.env.")
    keys = [k.strip() for k in args.profiles.split(",") if k.strip()]
    bad = [k for k in keys if k not in PROFILES]
    if bad:
        sys.exit(f"unknown profile(s) {bad}; choose from {sorted(PROFILES)}")
    think = tuple(float(x) for x in args.think.split(",")) if args.think else None
    taus = [float(x) for x in args.taus.split(",")] if args.taus else None
    try:
        overrides = parse_overrides(args.set) if args.set else None
    except ValueError as e:
        sys.exit(str(e))
    res = await run_experiment(
        args.domain, keys, embedder=args.embedder, llm=args.llm, generate=not args.no_generate,
        think_s=think, store_latency_s=args.store_latency_ms / 1000, concurrency=args.concurrency,
        sweep_profile=args.sweep, taus=taus, qdrant=args.qdrant, overrides=overrides,
        distractors=args.distractors, progress=lambda m: print(f"  … {m}", flush=True))
    text = format_experiment(res)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    if args.json:
        import json
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as f:
            json.dump({**res.to_json(), "generated": time.strftime("%Y-%m-%d %H:%M")}, f, indent=1)


async def cmd_make_distractors(args) -> None:
    """Generate (and cache) the distractor pages. Costs ~2 cents of gpt-4o-mini."""
    from .bench import distractors as d
    _need_key()
    data = await d._generate(d.TOPICS[: args.n])
    path = d.Path("data/distractors_bank.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = __import__("json").loads(path.read_text()) if path.exists() else {}
    old.update(data)
    path.write_text(__import__("json").dumps(old))
    print(f"wrote {len(old)} distractor pages to {path}")


async def cmd_serve(args) -> None:
    from .server.app import serve
    await serve(args)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="kairo")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, llm: bool):
        sp.add_argument("--index", default="data/index", help="FAISS index directory")
        sp.add_argument("--store", choices=["faiss", "qdrant"], default="faiss")
        sp.add_argument("--collection", default="kairo", help="Qdrant collection")
        sp.add_argument("--embedder", choices=["local", "openai"], default="local")
        sp.add_argument("--embed-model", default=None, help="override the embedder's model")
        if llm:
            sp.add_argument("--model", default="gpt-4o-mini")
            sp.add_argument("--profile", choices=["optimized", "paper"], default="optimized")

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
    sp.add_argument("--vad-threshold", type=float, default=None,
                    help="minimum speech-band level (default 0.01; adapts to noise)")
    sp.add_argument("--silence-ms", type=int, default=700)
    sp.set_defaults(fn=cmd_voice)

    sp = sub.add_parser("bench", help="compare strategies on a domain (hit rate, accuracy, latency)")
    sp.add_argument("--domain", choices=["bank", "novacrm"], default="bank")
    sp.add_argument("--profiles", default="baseline,paper,optimized",
                    help="comma list of: baseline,reactive,paper,neighbors,verified,optimized,fast")
    sp.add_argument("--embedder", choices=["hash", "local", "openai"], default="local")
    sp.add_argument("--llm", choices=["extractive", "openai"], default="extractive",
                    help="extractive = offline stand-in (no key, no cost)")
    sp.add_argument("--no-generate", action="store_true", help="skip answer generation (cheaper)")
    sp.add_argument("--think", default=None, help="think-time range in s, e.g. 3,6")
    sp.add_argument("--store-latency-ms", type=float, default=110.0)
    sp.add_argument("--concurrency", type=int, default=8)
    sp.add_argument("--sweep", default=None, metavar="PROFILE", help="tau sweep for this profile")
    sp.add_argument("--set", default=None, metavar="K=V,...",
                    help="override Config fields for cache profiles, e.g. llm_context_chunks=6,answer_threshold=0.78")
    sp.add_argument("--taus", default=None, help="thresholds for --sweep, e.g. 0.5,0.6,0.7")
    sp.add_argument("--distractors", type=int, default=0,
                    help="add N GPT-written near-domain pages as background (bank domain; max %d)"
                    % __import__("kairo.bench.distractors", fromlist=["TOPICS"]).__dict__["TOPICS"].__len__())
    sp.add_argument("--qdrant", action="store_true", help="use Qdrant (QDRANT_URL)")
    sp.add_argument("--out", help="write the markdown report here")
    sp.add_argument("--json", help="also save machine-readable results (shown in the web lab)")
    sp.set_defaults(fn=cmd_bench)

    sp = sub.add_parser("make-distractors", help="generate near-domain distractor pages (needs a key)")
    sp.add_argument("-n", type=int, default=64)
    sp.set_defaults(fn=cmd_make_distractors)

    sp = sub.add_parser("serve", help="web lab: chat, voice, live cache map, experiments")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--whisper", default="base.en")
    sp.add_argument("--no-voice", action="store_true", help="don't load Whisper")
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    load_dotenv()
    try:
        asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
