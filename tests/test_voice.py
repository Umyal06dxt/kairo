import asyncio

import numpy as np

from kairo.voice.endpoint import Endpointer, split_sentences
from kairo.voice.loop import speak_stream

SR = 16000
FRAME = 480  # 30 ms


def tone(n_frames, amp=0.2):
    return [np.full(FRAME, amp, dtype=np.float32) for _ in range(n_frames)]


def silence(n_frames):
    return [np.zeros(FRAME, dtype=np.float32) for _ in range(n_frames)]


def run(ep, frames):
    return [a for a in (ep.feed(f) for f in frames) if a is not None]


def test_endpointer_emits_one_utterance_after_silence():
    ep = Endpointer(silence_ms=300)
    out = run(ep, silence(5) + tone(20) + silence(15))
    assert len(out) == 1
    assert len(out[0]) >= 20 * FRAME  # speech retained (plus pre-roll/trailing silence)


def test_endpointer_pure_silence_and_blips_emit_nothing():
    ep = Endpointer(silence_ms=300, min_speech_ms=250)
    assert run(ep, silence(100)) == []
    assert run(ep, tone(2) + silence(20)) == []  # 60 ms click is below min speech


def test_endpointer_two_utterances_and_max_length():
    ep = Endpointer(silence_ms=300)
    assert len(run(ep, tone(15) + silence(15) + tone(15) + silence(15))) == 2
    ep = Endpointer(silence_ms=300, max_s=1.0)
    assert len(run(ep, tone(100))) >= 1  # forced out without trailing silence


async def agen(parts):
    for p in parts:
        yield p


async def test_split_sentences_boundaries_and_tail():
    out = [s async for s in split_sentences(agen(["Hello the", "re. How are", " you? Fine"]))]
    assert out == ["Hello there.", "How are you?", "Fine"]


async def test_split_sentences_short_fragment_merges():
    out = [s async for s in split_sentences(agen(["Dr. Smith is here. Ok."]))]
    assert out == ["Dr. Smith is here.", "Ok."]


async def test_split_sentences_empty():
    assert [s async for s in split_sentences(agen([]))] == []


class FakeTTS:
    def __init__(self):
        self.played, self.synthed = [], []

    async def synth(self, text):
        self.synthed.append(text)
        return np.array([len(text)], dtype=np.int16)

    async def play(self, pcm):
        self.played.append(int(pcm[0]))


async def test_speak_stream_plays_in_order_and_reports_first_audio():
    q = asyncio.Queue()
    tts = FakeTTS()
    task = asyncio.create_task(speak_stream(tts, q))
    for tok in ["First sentence here. ", "Second one is longer."]:
        q.put_nowait(tok)
    q.put_nowait(None)
    first = await task
    assert tts.synthed == ["First sentence here.", "Second one is longer."]
    assert tts.played == [20, 21] and first is not None


async def test_speak_stream_silent_when_no_tokens():
    q = asyncio.Queue()
    q.put_nowait(None)
    assert await speak_stream(FakeTTS(), q) is None
