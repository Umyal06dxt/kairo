"""Background agent: direct retrieval, speculation (LLM / neighbours / both), pre-drafting."""

import asyncio
import logging

import numpy as np

from .answer_cache import AnswerCache
from .cache import SemanticCache
from .config import Config
from .events import PartialUtterance, PriorityRetrieval, UserUtterance
from .providers.base import LLM, Embedder, Prediction, VectorStore
from .stream import ConversationStream
from .telemetry import Telemetry

log = logging.getLogger(__name__)


class SlowThinker:
    def __init__(self, embedder: Embedder, llm: LLM, store: VectorStore,
                 cache: SemanticCache, stream: ConversationStream, config: Config,
                 answers: AnswerCache | None = None, telemetry: Telemetry | None = None):
        self.embedder, self.llm, self.store = embedder, llm, store
        self.cache, self.stream, self.config = cache, stream, config
        self.answers = answers
        self.telemetry = telemetry or Telemetry()
        # Subscribe at construction so no event published before run() is lost.
        self._events = stream.subscribe()
        self._last_predict = float("-inf")

    # ------------------------------------------------------------------ event loop
    async def run(self) -> None:
        """Consume events until cancelled."""
        utterance_task: asyncio.Task | None = None
        partial_task: asyncio.Task | None = None
        priority_tasks: set[asyncio.Task] = set()

        def cancel(t: asyncio.Task | None) -> None:
            if t and not t.done():
                t.cancel()

        try:
            while True:
                event = await self._events.get()
                if isinstance(event, UserUtterance):
                    cancel(utterance_task)  # stale cycle must not delay this one
                    cancel(partial_task)    # the final transcript supersedes partials
                    self.telemetry.emit("slow.utterance", text=event.text)
                    utterance_task = asyncio.create_task(
                        self.handle_utterance(event.text, event.embedding))
                elif isinstance(event, PartialUtterance):
                    cancel(partial_task)
                    if not (utterance_task and not utterance_task.done()):
                        partial_task = asyncio.create_task(self.handle_partial(event.text))
                elif isinstance(event, PriorityRetrieval):
                    t = asyncio.create_task(self.handle_priority(event))
                    priority_tasks.add(t)
                    t.add_done_callback(priority_tasks.discard)
        finally:
            for t in [utterance_task, partial_task, *priority_tasks]:
                cancel(t)

    # ------------------------------------------------------------------ handlers
    async def handle_utterance(self, text: str, embedding=None) -> None:
        try:
            await self._cycle(text, embedding)
        except asyncio.CancelledError:
            self.telemetry.emit("slow.cancelled", text=text)
            raise
        except Exception:
            log.exception("slow thinker cycle failed")

    async def handle_partial(self, text: str) -> None:
        """Stream-RAG-style speculation: retrieve on an interim transcript."""
        text = text.strip()
        if len(text) < self.config.partial_min_chars:
            return
        try:
            vec = (await self.embedder.embed([text]))[0]
            results = await self.store.search(vec, self.config.prefetch_top_k)
            self._put_all(results, "partial", text)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("partial retrieval failed")

    async def handle_priority(self, event: PriorityRetrieval) -> None:
        try:
            results = await self.store.search(event.embedding, 2 * self.config.prefetch_top_k)
            self._put_all(results, "miss", event.query)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("priority retrieval failed")

    # ------------------------------------------------------------------ speculation cycle
    def _put_all(self, results, tag: str, query: str) -> int:
        added = []
        for r in results:
            if self.cache.put(r.chunk, r.embedding, r.score, tag=tag):
                added.append(r.chunk.id)
        self.telemetry.emit("slow.prefetch", source=tag, query=query, added=added,
                            returned=[r.chunk.id for r in results])
        return len(added)

    async def _cycle(self, text: str, embedding=None) -> None:
        cfg = self.config
        # 1. direct retrieval for the current utterance (reuse the router's embedding if given)
        vec = embedding if embedding is not None else (await self.embedder.embed([text]))[0]
        results = await self.store.search(vec, cfg.prefetch_top_k)
        self._put_all(results, "direct", text)

        # 2. speculate about what comes next
        jobs = []
        if cfg.strategy in ("neighbors", "hybrid"):
            jobs.append(self._neighbors(results))
        if cfg.strategy in ("llm", "hybrid"):
            jobs.append(self._predict(text))
        if jobs:
            await asyncio.gather(*jobs)

    async def _neighbors(self, results) -> None:
        """Zero-LLM, zero-embedding-API prediction: chunks near what was just retrieved."""
        seeds = results[: self.config.neighbor_seeds]
        found = await asyncio.gather(
            *(self.store.search(r.embedding, self.config.neighbor_k) for r in seeds),
            return_exceptions=True)
        for seed, res in zip(seeds, found):
            if isinstance(res, asyncio.CancelledError):
                raise res
            if isinstance(res, BaseException):
                log.warning("neighbour search failed: %r", res)
                continue
            self._put_all(res, "neighbor", seed.chunk.id)

    async def _get_predictions(self, history) -> list[Prediction]:
        cfg = self.config
        try:
            if cfg.speculative_answers and hasattr(self.llm, "predict_followups"):
                preds = await self.llm.predict_followups(history, cfg.max_predictions)
            else:
                topics = await self.llm.predict_topics(history, cfg.max_predictions)
                preds = [Prediction(t) for t in topics]
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("topic prediction failed; skipping prefetch")
            return []
        return [p for p in preds if isinstance(p.topic, str) and p.topic.strip()][
            : cfg.max_predictions]

    async def _predict(self, text: str) -> None:
        cfg = self.config
        loop = asyncio.get_running_loop()
        wait = self._last_predict + cfg.rate_limit_s - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_predict = loop.time()
        history = self.stream.history(cfg.prediction_history_turns)
        if not history or history[-1] != ("user", text):
            history = [*history, ("user", text)][-cfg.prediction_history_turns:]
        preds = await self._get_predictions(history)
        if not preds:
            return

        # one batched embed: topics (for chunk prefetch) + questions (for draft matching)
        draft_idx = ([i for i, p in enumerate(preds) if p.question][: cfg.draft_top]
                     if self.answers is not None and cfg.speculative_answers else [])
        texts = [p.topic for p in preds] + [preds[i].question for i in draft_idx]
        vecs = await self.embedder.embed(texts)
        topic_vecs, q_vecs = vecs[: len(preds)], vecs[len(preds):]
        results = await asyncio.gather(
            *(self.store.search(v, cfg.prefetch_top_k) for v in topic_vecs),
            return_exceptions=True)
        per_pred: list[list] = []
        for p, res in zip(preds, results):
            if isinstance(res, asyncio.CancelledError):
                raise res
            if isinstance(res, BaseException):
                log.warning("prefetch search failed: %r", res)
                per_pred.append([])
                continue
            per_pred.append(res)
            self._put_all(res, "predicted", p.topic)
        self.telemetry.emit("slow.predicted", predictions=[
            {"topic": p.topic, "question": p.question} for p in preds])

        if draft_idx:
            await asyncio.gather(*(
                self._draft(preds[i].question, q_vecs[j], per_pred[i])
                for j, i in enumerate(draft_idx)))

    async def _draft(self, question: str, qvec: np.ndarray, retrieved) -> None:
        """Pre-generate an answer for a predicted question (Speculative-RAG-style drafting)."""
        if not retrieved:
            return
        ctx = [r.chunk for r in retrieved[: self.config.llm_context_chunks]]
        try:
            answer = await self.llm.draft_answer(question, ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("draft failed")
            return
        if answer and answer.strip():
            self.answers.put(question, qvec, answer.strip(), [c.id for c in ctx])
            self.telemetry.emit("slow.drafted", question=question, answer=answer.strip(),
                                chunk_ids=[c.id for c in ctx])
