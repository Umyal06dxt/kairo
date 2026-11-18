"""Web lab: shared resources and one Session per websocket (= one phone call)."""

import asyncio
import base64
import os
import random
import time
from collections import Counter
from dataclasses import dataclass

from ..bench.distractors import cached_distractors
from ..bench.domains import DOMAIN_KEYS, get_domain, score_answer
from ..bench.run import PROFILES
from ..config import for_embedder
from ..fast_talker import TurnResult
from ..ingest import chunk_documents
from ..providers.faiss_store import FaissStore
from ..providers.fake import DelayedStore, ExtractiveLLM, HashEmbedder
from ..router import MemoryRouter
from ..stream import ConversationStream
from ..telemetry import Telemetry
from ..voice.endpoint import split_sentences
from ..voice.io import EdgeTTS, decode_to_pcm16k, pcm_to_wav

EMBEDDERS = ("local", "openai", "hash")


@dataclass
class Settings:
    domain: str = "bank"
    profile: str = "optimized"
    embedder: str = "local"
    llm: str = "auto"  # auto = GPT if OPENAI_API_KEY is set, else the offline extractive stand-in
    distractors: bool = True
    tau: float | None = None  # None = the embedder's default threshold
    store_latency_ms: float = 110.0
    speak: bool = False

    @classmethod
    def from_msg(cls, m: dict) -> "Settings":
        s = cls()
        if m.get("domain") in DOMAIN_KEYS:
            s.domain = m["domain"]
        if m.get("profile") in PROFILES:
            s.profile = m["profile"]
        if m.get("embedder") in EMBEDDERS:
            s.embedder = m["embedder"]
        if m.get("llm") in ("auto", "openai", "extractive"):
            s.llm = m["llm"]
        s.distractors = bool(m.get("distractors", s.distractors))
        s.speak = bool(m.get("speak", s.speak))
        try:
            if m.get("tau") is not None:
                s.tau = min(0.95, max(0.05, float(m["tau"])))
            s.store_latency_ms = min(2000.0, max(0.0, float(m.get("store_latency_ms", 110.0))))
        except (TypeError, ValueError):
            pass
        return s


def _title(text: str) -> str:
    """Short row label: the first heading without the institution prefix."""
    first = text.strip().splitlines()[0].lstrip("# ").strip()
    for prefix in ("Harbor Federal Credit Union - ", "Harbor Federal Credit Union", "NovaCRM "):
        if first.startswith(prefix) and len(first) > len(prefix) + 2:
            first = first[len(prefix):].strip(" -")
    return (first[:1].upper() + first[1:])[:48]


class Shared:
    """Expensive, reusable resources: embedding models, indexes, Whisper, Edge TTS."""

    def __init__(self) -> None:
        self._embedders: dict[str, object] = {}
        self._indexes: dict[tuple, tuple] = {}
        self._lock = asyncio.Lock()
        self.stt = None
        self.stt_state = "off"  # off | loading | ready | error
        self.tts = EdgeTTS()

    async def load_stt(self, size: str) -> None:
        self.stt_state = "loading"
        try:
            from ..voice.io import WhisperSTT
            self.stt = await asyncio.to_thread(WhisperSTT, size)
            self.stt_state = "ready"
        except Exception:
            self.stt_state = "error"

    async def embedder(self, name: str) -> tuple[object, str, str | None]:
        """-> (embedder, name actually used, fallback notice)."""
        notice = None
        if name == "openai" and not os.environ.get("OPENAI_API_KEY"):
            name, notice = "local", "No OPENAI_API_KEY: using the on-device embedder instead."
        if name == "local":
            try:
                async with self._lock:
                    if "local" not in self._embedders:
                        from ..providers.local import LocalEmbedder
                        self._embedders["local"] = await asyncio.to_thread(LocalEmbedder)
            except Exception:
                name, notice = "hash", "On-device embedder unavailable (pip install fastembed): using toy hash embeddings."
        async with self._lock:
            if name not in self._embedders:
                if name == "openai":
                    from ..providers.openai_ import OpenAIEmbedder
                    self._embedders[name] = OpenAIEmbedder()
                else:
                    self._embedders[name] = HashEmbedder(dim=512)
        return self._embedders[name], name, notice

    async def index(self, domain_key: str, emb_name: str, emb, distractors: bool):
        key = (domain_key, emb_name, distractors)
        async with self._lock:
            if key in self._indexes:
                return self._indexes[key]
        domain = get_domain(domain_key)
        docs = dict(domain.docs)
        extra = cached_distractors(64) if (distractors and domain_key == "bank") else {}
        docs.update(extra)
        chunks = chunk_documents(list(docs.items()))
        vecs = await emb.embed([c.text for c in chunks])
        store = FaissStore(emb.dim)
        await store.add(chunks, vecs)
        board = {"docs": [
            {"name": n, "title": _title(t),
             "extra": n in extra,
             "chunks": [c.id for c in chunks if c.id.rsplit(":", 1)[0] == n]}
            for n, t in docs.items()], "n_chunks": len(chunks), "n_extra": len(extra)}
        async with self._lock:
            self._indexes[key] = (store, board)
        return store, board

    def llm(self, choice: str):
        """-> (llm, name used, notice)."""
        if choice != "extractive" and os.environ.get("OPENAI_API_KEY"):
            from ..providers.openai_ import OpenAILLM
            return OpenAILLM(), "openai", None
        notice = None if choice == "extractive" else (
            "No OPENAI_API_KEY: answers are copied from the knowledge base and follow-ups can't "
            "be predicted. Add a key to .env for GPT answers and predictions.")
        return ExtractiveLLM(ttft_s=0.25), "extractive", notice


class BaselineRouter:
    """Traditional RAG with the same interface as MemoryRouter: embed -> store -> LLM, every turn."""

    cache = None
    answers = None

    def __init__(self, embedder, llm, store, config):
        self.embedder, self.llm, self.store, self.config = embedder, llm, store, config
        self.telemetry, self.stream, self.sources = Telemetry(), ConversationStream(), Counter()

    async def start(self): ...
    async def stop(self): ...
    async def speculate(self, text): ...

    async def warmup(self):
        warm = getattr(self.llm, "warmup", None)
        await asyncio.gather(self.embedder.embed(["warm up"]), warm() if warm else asyncio.sleep(0),
                             return_exceptions=True)

    async def handle_utterance(self, text, on_token=None) -> TurnResult:
        text = text.strip()
        if not text:
            return TurnResult(answer="")
        t0 = time.perf_counter()
        embed = getattr(self.embedder, "embed_queries", self.embedder.embed)
        vec = (await embed([text]))[0]
        embed_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        found = await self.store.search(vec, self.config.prefetch_top_k)
        res = TurnResult(answer="", source="store", embed_ms=embed_ms,
                         retrieval_ms=(time.perf_counter() - t0) * 1000)
        used = found[: self.config.llm_context_chunks]
        res.chunk_ids = [r.chunk.id for r in used]
        t1, parts = time.perf_counter(), []
        async for tok in self.llm.stream_answer(text, [r.chunk for r in used], self.stream.history()):
            if not parts:
                res.llm_first_token_ms = (time.perf_counter() - t1) * 1000
            parts.append(tok)
            if on_token:
                on_token(tok)
        res.answer = "".join(parts)
        self.stream.add_turn("user", text)
        self.stream.add_turn("assistant", res.answer)
        self.sources["store"] += 1
        return res


def user_ms(r: TurnResult) -> float:
    return r.embed_ms + r.retrieval_ms + (r.llm_first_token_ms or 0.0)


class Session:
    def __init__(self, ws, shared: Shared):
        self.ws, self.shared = ws, shared
        self.out: asyncio.Queue = asyncio.Queue()
        self.settings = Settings()
        self.router = None
        self.domain = None
        self.gold: dict = {}
        self.llm_name = "extractive"
        self.lock = asyncio.Lock()
        self.stats = Counter()
        self.user_ms_sum = 0.0
        self._tasks: set[asyncio.Task] = set()
        self._autoplay: asyncio.Task | None = None
        self._cache_event = asyncio.Event()
        self._sender = self._spawn(self._send_loop())
        self._pusher = self._spawn(self._cache_loop())

    # ---- plumbing
    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def emit(self, msg: dict) -> None:
        self.out.put_nowait(msg)

    async def _send_loop(self) -> None:
        while True:
            msg = await self.out.get()
            try:
                await self.ws.send_json(msg)
            except Exception:
                return  # socket closed

    async def _cache_loop(self) -> None:
        """Throttled cache snapshots so lamps update while the Slow Thinker works."""
        while True:
            await self._cache_event.wait()
            await asyncio.sleep(0.08)
            self._cache_event.clear()
            self.push_cache()

    def push_cache(self) -> None:
        r = self.router
        if r is None or r.cache is None:
            self.emit({"t": "cache", "entries": [], "drafts": []})
            return
        self.emit({"t": "cache",
                   "entries": [{"id": e["id"], "tag": e["tag"], "hits": e["hits"], "ttl": e["ttl_left_s"]}
                               for e in r.cache.snapshot()],
                   "drafts": r.answers.snapshot() if r.answers is not None else []})

    def _on_telemetry(self, kind: str, data: dict) -> None:
        if kind.startswith("slow.") or kind == "fast.corrected":
            msg = {"t": "slow", "kind": kind.split(".", 1)[1]}
            msg.update({k: v for k, v in data.items() if k != "embedding"})
            if kind == "slow.drafted":
                msg["answer"] = data.get("answer", "")[:200]
            self.emit(msg)
            self._cache_event.set()

    # ---- configuration
    async def configure(self, msg: dict) -> None:
        if self._autoplay:
            self._autoplay.cancel()
        s = Settings.from_msg(msg)
        self.settings = s
        notes: list[str] = []
        self.emit({"t": "status", "state": "loading", "message": "Loading knowledge base…"})
        emb, emb_name, n1 = await self.shared.embedder(s.embedder)
        if n1:
            notes.append(n1)
        s.embedder = emb_name
        store, board = await self.shared.index(s.domain, emb_name, emb, s.distractors)
        llm, llm_name, n2 = self.shared.llm(s.llm)
        if n2:
            notes.append(n2)
        self.llm_name = llm_name
        if s.distractors and s.domain == "bank" and not board["n_extra"]:
            notes.append("No distractor pages found (run `kairo make-distractors`): the knowledge "
                         "base is small, so caching looks easier than it would in production.")
        if self.router is not None:
            await self.router.stop()
        prof = PROFILES[s.profile]
        cfg = for_embedder(prof.config, emb_name)
        if s.tau is not None:
            from dataclasses import replace
            cfg = replace(cfg, similarity_threshold=s.tau)
        sim_store = DelayedStore(store, s.store_latency_ms / 1000) if s.store_latency_ms > 0 else store
        if prof.cache:
            self.router = MemoryRouter.create(emb, llm, sim_store, cfg)
        else:
            self.router = BaselineRouter(emb, llm, sim_store, cfg)
        self.router.telemetry.add_sink(self._on_telemetry)
        await self.router.start()
        self.domain = get_domain(s.domain)
        self.gold = {t.q: t for turns in self.domain.scenarios.values() for t in turns}
        self.stats, self.user_ms_sum = Counter(), 0.0
        self.emit({"t": "ready", "board": board, "settings": s.__dict__,
                   "profile": {"key": prof.key, "label": prof.label, "cache": prof.cache},
                   "config": {"strategy": cfg.strategy, "verify": cfg.verify_hits,
                              "drafts": cfg.speculative_answers, "tau": round(cfg.similarity_threshold, 2),
                              "context": cfg.llm_context_chunks, "rerank": cfg.lexical_rerank},
                   "llm": llm_name, "embedder": emb_name, "notes": notes,
                   "domain": {"key": self.domain.key, "title": self.domain.title,
                              "blurb": self.domain.blurb,
                              "scenarios": [{"key": k, "turns": len(v),
                                             "questions": [t.q for t in v[:4]]}
                                            for k, v in self.domain.scenarios.items()]},
                   "voice": {"stt": self.shared.stt_state, "tts": True}})
        self.push_cache()
        self._spawn(self._warm())

    async def _warm(self) -> None:
        try:
            await self.router.warmup()
        finally:
            self.emit({"t": "status", "state": "ready", "message": ""})

    # ---- a turn
    async def say(self, text: str, via: str = "text") -> None:
        text = text.strip()
        if not text or self.router is None:
            return
        async with self.lock:
            speak = (self.settings.speak or via == "voice")
            tok_q: asyncio.Queue | None = asyncio.Queue() if speak else None
            self.emit({"t": "turn_start", "q": text, "via": via})

            def on_token(tok: str) -> None:
                self.emit({"t": "token", "s": tok})
                if tok_q is not None:
                    tok_q.put_nowait(tok)

            speaker = self._spawn(self._speak(tok_q)) if tok_q is not None else None
            try:
                res = await self.router.handle_utterance(text, on_token)
            except Exception as e:
                self.emit({"t": "error", "message": f"That turn failed ({type(e).__name__}: {e}). "
                                                    "Check your connection or API key and try again."})
                return
            finally:
                if tok_q is not None:
                    tok_q.put_nowait(None)
            self.stats["turns"] += 1
            self.stats[res.source] += 1
            self.stats["hits"] += bool(res.hit)
            self.stats["corrected"] += bool(res.corrected)
            self.user_ms_sum += user_ms(res)
            gold = self._gold(text, res)
            self.emit({"t": "turn", "q": text, "answer": res.answer, "source": res.source,
                       "hit": res.hit, "verified": res.verified, "corrected": res.corrected,
                       "embed_ms": round(res.embed_ms, 1), "retrieval_ms": round(res.retrieval_ms, 2),
                       "llm_ms": None if res.llm_first_token_ms is None else round(res.llm_first_token_ms, 1),
                       "user_ms": round(user_ms(res), 1), "chunk_ids": res.chunk_ids, "tags": res.tags,
                       "draft_sim": res.draft_sim, "store_failed": res.store_failed, "gold": gold,
                       "stats": {"turns": self.stats["turns"], "hits": self.stats["hits"],
                                 "drafts": self.stats["draft"], "corrected": self.stats["corrected"],
                                 "avg_user_ms": round(self.user_ms_sum / self.stats["turns"], 1)}})
            self.push_cache()
            if speaker is not None:
                await speaker

    def _gold(self, text: str, res: TurnResult) -> dict | None:
        g = self.gold.get(text)
        if g is None or not g.expect:
            return None
        docs = {c.rsplit(":", 1)[0] for c in res.chunk_ids}
        return {"doc_ok": (g.doc in docs) if g.doc else None,
                "answer_ok": score_answer(res.answer, g.expect) if self.llm_name == "openai" else None,
                "doc": g.doc}

    async def _speak(self, q: asyncio.Queue) -> None:
        async def tokens():
            while (tok := await q.get()) is not None:
                yield tok

        async def deliver(task, sentence, seq):
            try:
                pcm = await task
            except Exception:
                return
            self.emit({"t": "audio_out", "seq": seq, "sentence": sentence,
                       "data": base64.b64encode(pcm_to_wav(pcm, EdgeTTS.OUT_SR)).decode()})

        prev, seq = None, 0
        async for sentence in split_sentences(tokens()):
            task = asyncio.create_task(self.shared.tts.synth(sentence))
            if prev:
                await deliver(*prev)
            prev, seq = (task, sentence, seq), seq + 1
        if prev:
            await deliver(*prev)

    async def partial(self, text: str) -> None:
        if self.router is not None and not self.lock.locked():
            await self.router.speculate(text)
            self._cache_event.set()

    async def audio(self, b64: str, mime: str = "") -> None:
        stt = self.shared.stt
        if stt is None:
            self.emit({"t": "error", "message": "Speech recognition isn't loaded yet. "
                       "Start the server without --no-voice, or type your question."})
            return
        try:
            pcm = await asyncio.to_thread(decode_to_pcm16k, base64.b64decode(b64))
            text = await stt.atranscribe(pcm) if len(pcm) > 4800 else ""
        except Exception as e:
            self.emit({"t": "error", "message": f"Couldn't read that recording ({type(e).__name__}). Try again."})
            return
        self.emit({"t": "transcript", "text": text})
        if text.strip():
            await self.say(text, via="voice")

    # ---- scripted calls
    async def autoplay(self, scenario: str) -> None:
        if self._autoplay:
            self._autoplay.cancel()
        if self.domain is None or scenario not in self.domain.scenarios:
            return
        self._autoplay = self._spawn(self._run_autoplay(scenario))

    async def stop_autoplay(self) -> None:
        if self._autoplay:
            self._autoplay.cancel()

    async def _run_autoplay(self, key: str) -> None:
        think = (3.0, 6.0) if self.llm_name == "openai" else (1.5, 2.5)
        self.emit({"t": "autoplay", "state": "start", "scenario": key})
        try:
            for turn in self.domain.scenarios[key]:
                await self.say(turn.q, via="script")
                await asyncio.sleep(random.uniform(*think))
            self.emit({"t": "autoplay", "state": "done", "scenario": key})
        except asyncio.CancelledError:
            self.emit({"t": "autoplay", "state": "stopped", "scenario": key})
            raise

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        if self.router is not None:
            await self.router.stop()
