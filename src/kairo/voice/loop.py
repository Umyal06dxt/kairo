"""Voice conversation loop: mic -> endpoint -> STT -> router -> sentence TTS."""

import asyncio
import time

from ..router import MemoryRouter
from .endpoint import Endpointer, split_sentences


async def _token_iter(q: "asyncio.Queue[str | None]"):
    while (tok := await q.get()) is not None:
        yield tok


async def speak_stream(tts, tokens: "asyncio.Queue[str | None]") -> float | None:
    """Speak sentences as they complete. Synthesis of sentence N+1 overlaps
    playback of N. Returns seconds from call to first audio (None if silent)."""
    t0 = time.perf_counter()
    first: float | None = None
    pending: asyncio.Task | None = None
    async for sentence in split_sentences(_token_iter(tokens)):
        nxt = asyncio.create_task(tts.synth(sentence))
        if pending is not None:
            pcm = await pending
            first = first if first is not None else time.perf_counter() - t0
            await tts.play(pcm)
        pending = nxt
    if pending is not None:
        pcm = await pending
        first = first if first is not None else time.perf_counter() - t0
        await tts.play(pcm)
    return first


async def run_voice(router: MemoryRouter, stt, tts, mic, endpointer: Endpointer | None = None,
                    log=print) -> None:
    ep = endpointer or Endpointer()
    await router.start()
    log("Listening… (Ctrl-C to quit)")
    try:
        async with mic:
            async for frame in mic.frames():
                audio = ep.feed(frame)
                if audio is None:
                    continue
                t0 = time.perf_counter()
                text = await stt.atranscribe(audio)
                stt_ms = (time.perf_counter() - t0) * 1000
                if not text.strip():
                    continue
                log(f"you: {text}")
                q: asyncio.Queue = asyncio.Queue()
                speaker = asyncio.create_task(speak_stream(tts, q))
                try:
                    r = await router.handle_utterance(text, on_token=q.put_nowait)
                finally:
                    q.put_nowait(None)
                first_audio = await speaker
                log(f"kairo: {r.answer.strip()}")
                fa = f"{first_audio * 1000:.0f}" if first_audio is not None else "-"
                log(f"  [{r.source}{' HIT' if r.hit else ''}] stt={stt_ms:.0f}ms "
                    f"embed={r.embed_ms:.0f}ms retrieval={r.retrieval_ms:.2f}ms "
                    f"first_audio={fa}ms")
                ep.reset()  # drop anything the mic heard while we were talking
    finally:
        await router.stop()
