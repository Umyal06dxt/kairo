"""Voice conversation loop: mic -> endpoint -> STT -> router -> sentence TTS."""

import asyncio
import logging
import time

from ..router import MemoryRouter
from .endpoint import Endpointer, split_sentences

log = logging.getLogger(__name__)


async def _token_iter(q: "asyncio.Queue[str | None]"):
    while (tok := await q.get()) is not None:
        yield tok


async def speak_stream(tts, tokens: "asyncio.Queue[str | None]") -> float | None:
    """Speak sentences as they complete. Synthesis of sentence N+1 overlaps
    playback of N. A sentence that fails to synthesize/play is skipped.
    Returns seconds from call to first audio (None if nothing was spoken)."""
    t0 = time.perf_counter()
    first: float | None = None

    async def play(task: asyncio.Task) -> None:
        nonlocal first
        try:
            pcm = await task
            if first is None:
                first = time.perf_counter() - t0
            await tts.play(pcm)
        except Exception:
            log.warning("TTS failed for a sentence; skipping it", exc_info=True)

    pending: asyncio.Task | None = None
    async for sentence in split_sentences(_token_iter(tokens)):
        nxt = asyncio.create_task(tts.synth(sentence))
        if pending is not None:
            await play(pending)
        pending = nxt
    if pending is not None:
        await play(pending)
    return first


async def _one_turn(router: MemoryRouter, tts, text: str, stt_ms: float, log_fn) -> None:
    q: asyncio.Queue = asyncio.Queue()
    speaker = asyncio.create_task(speak_stream(tts, q))
    r = None
    try:
        r = await router.handle_utterance(text, on_token=q.put_nowait)
    except Exception as e:  # LLM/embedding/network failure must not end the session
        log.warning("turn failed", exc_info=True)
        log_fn(f"  [error: {type(e).__name__}: {e}] — still listening")
    finally:
        q.put_nowait(None)
    first_audio = await speaker
    if r is None:
        return
    log_fn(f"kairo: {r.answer.strip()}")
    fa = f"{first_audio * 1000:.0f}" if first_audio is not None else "-"
    ft = f"{r.llm_first_token_ms:.0f}" if r.llm_first_token_ms is not None else "-"
    log_fn(f"  [{r.source}{' HIT' if r.hit else ''}] stt={stt_ms:.0f}ms "
           f"embed={r.embed_ms:.0f}ms retrieval={r.retrieval_ms:.2f}ms "
           f"llm_first_token={ft}ms first_audio={fa}ms")


async def run_voice(router: MemoryRouter, stt, tts, mic, endpointer: Endpointer | None = None,
                    log_fn=print, mute_after_s: float = 0.4) -> None:
    """Listen until the mic stream ends or the task is cancelled.

    Mic frames are read continuously by a background task but discarded while a
    turn is being processed/spoken (plus `mute_after_s`), so Kairo never
    transcribes its own voice."""
    ep = endpointer or Endpointer()
    state = {"busy": False, "mute_until": 0.0}
    frames: asyncio.Queue = asyncio.Queue()

    async def reader() -> None:
        try:
            async for frame in mic.frames():
                if state["busy"] or time.monotonic() < state["mute_until"]:
                    continue
                frames.put_nowait(frame)
        finally:
            frames.put_nowait(None)  # signals end of stream

    await router.start()
    log_fn("Listening… (Ctrl-C to quit)")
    reader_task: asyncio.Task | None = None
    try:
        async with mic:
            reader_task = asyncio.create_task(reader())
            while (frame := await frames.get()) is not None:
                audio = ep.feed(frame)
                if audio is None:
                    continue
                state["busy"] = True
                try:
                    t0 = time.perf_counter()
                    try:
                        text = await stt.atranscribe(audio)
                    except Exception as e:
                        log.warning("STT failed", exc_info=True)
                        log_fn(f"  [stt error: {type(e).__name__}: {e}]")
                        continue
                    stt_ms = (time.perf_counter() - t0) * 1000
                    if not text.strip():
                        continue
                    log_fn(f"you: {text}")
                    await _one_turn(router, tts, text, stt_ms, log_fn)
                finally:
                    ep.reset()
                    state["busy"] = False
                    state["mute_until"] = time.monotonic() + mute_after_s
            log_fn("Microphone stream ended (is a capture device available? try `arecord -l`).")
    finally:
        if reader_task:
            reader_task.cancel()
        await router.stop()
