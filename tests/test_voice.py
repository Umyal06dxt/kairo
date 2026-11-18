import asyncio

import numpy as np

from kairo.voice.endpoint import Endpointer, split_sentences
from kairo.voice.loop import speak_stream

SR = 16000
FRAME = 480  # 30 ms


def tone(n_frames, amp=0.2, hz=1000.0):
    t = np.arange(FRAME) / SR
    return [(amp * np.sin(2 * np.pi * hz * t + i)).astype(np.float32) for i in range(n_frames)]


def noise(n_frames, amp, seed=0):
    rng = np.random.default_rng(seed)
    return [(amp * rng.standard_normal(FRAME)).astype(np.float32) for _ in range(n_frames)]


def silence(n_frames):
    return [np.zeros(FRAME, dtype=np.float32) for _ in range(n_frames)]


def run(ep, frames):
    return [a for a in (ep.feed(f) for f in frames) if a is not None]


def test_endpointer_emits_one_utterance_after_silence():
    ep = Endpointer(silence_ms=300, calib_frames=0)
    out = run(ep, silence(5) + tone(20) + silence(15))
    assert len(out) == 1
    assert len(out[0]) >= 20 * FRAME  # speech retained (plus pre-roll/trailing silence)


def test_endpointer_pure_silence_and_blips_emit_nothing():
    ep = Endpointer(silence_ms=300, min_speech_ms=250, calib_frames=0)
    assert run(ep, silence(100)) == []
    assert run(ep, tone(2) + silence(20)) == []  # 60 ms click is below min speech


def test_endpointer_two_utterances_and_max_length():
    ep = Endpointer(silence_ms=300, calib_frames=0)
    assert len(run(ep, tone(15) + silence(15) + tone(15) + silence(15))) == 2
    ep = Endpointer(silence_ms=300, max_s=1.0, calib_frames=0)
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


class FlakyTTS(FakeTTS):
    async def synth(self, text):
        if "boom" in text:
            raise RuntimeError("no audio")
        return await super().synth(text)


async def test_speak_stream_skips_failed_sentence():
    q = asyncio.Queue()
    tts = FlakyTTS()
    task = asyncio.create_task(speak_stream(tts, q))
    for tok in ["This one will boom. ", "But this one is fine."]:
        q.put_nowait(tok)
    q.put_nowait(None)
    assert await task is not None
    assert tts.played == [len("But this one is fine.")]


class FakeMic:
    def __init__(self, frame_batches):
        self._frames = [f for b in frame_batches for f in b]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def frames(self):
        for f in self._frames:
            await asyncio.sleep(0.0005)
            yield f


class FakeSTT:
    def __init__(self, texts):
        self.texts = list(texts)

    async def atranscribe(self, audio):
        return self.texts.pop(0)


class FakeResult:
    def __init__(self, answer):
        self.answer, self.source, self.hit = answer, "cache", True
        self.embed_ms = self.retrieval_ms = 1.0
        self.llm_first_token_ms = 2.0


class FakeRouter:
    def __init__(self):
        self.calls, self.started, self.stopped = [], False, False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def handle_utterance(self, text, on_token=None):
        self.calls.append(text)
        if len(self.calls) == 1:
            raise RuntimeError("openai down")
        for t in ["Here is your answer. "]:
            on_token(t)
        return FakeResult("Here is your answer.")


async def test_run_voice_survives_turn_failure_and_keeps_listening():
    from kairo.voice.loop import run_voice
    utt = tone(15) + silence(25)
    mic = FakeMic([utt, utt])
    router, tts, lines = FakeRouter(), FakeTTS(), []
    await run_voice(router, FakeSTT(["first", "second"]), tts, mic,
                    Endpointer(silence_ms=300, calib_frames=0), log_fn=lines.append, mute_after_s=0.0)
    assert router.calls == ["first", "second"]  # error on turn 1 did not end the loop
    assert any("openai down" in line for line in lines)
    assert any("Here is your answer." in line for line in lines)
    assert tts.played, "second answer was spoken"
    assert router.started and router.stopped
    assert any("Microphone stream ended" in line for line in lines)


async def test_run_voice_ignores_blank_transcripts():
    from kairo.voice.loop import run_voice
    router = FakeRouter()
    await run_voice(router, FakeSTT(["   "]), FakeTTS(), FakeMic([tone(15) + silence(25)]),
                    Endpointer(silence_ms=300, calib_frames=0), log_fn=lambda s: None, mute_after_s=0.0)
    assert router.calls == []


def test_band_rms_ignores_low_frequency_rumble():
    ep = Endpointer()
    speech = tone(1, amp=0.3, hz=1000.0)[0]
    rumble = tone(1, amp=0.5, hz=50.0)[0]
    assert abs(ep.band_rms(speech) - 0.3 / np.sqrt(2)) < 0.01
    assert ep.band_rms(rumble) < 0.002


def test_loud_rumble_never_triggers():
    ep = Endpointer(silence_ms=300)
    assert run(ep, tone(300, amp=0.5, hz=50.0)) == []  # the real-mic failure mode


def test_adapts_to_steady_noise_and_still_detects_speech():
    ep = Endpointer(silence_ms=300)
    # 2 s of loud steady hiss never triggers once the floor is learned
    assert run(ep, noise(70, 0.05)) == []
    # speech well above the hiss is detected
    speech = [a + b for a, b in zip(tone(20, amp=0.5), noise(20, 0.05, seed=1))]
    out = run(ep, speech + noise(25, 0.05, seed=2))
    assert len(out) == 1


def test_calibration_prevents_noise_from_looking_like_speech():
    # noise (~0.033 in-band) is above the 0.01 minimum threshold: without calibration the
    # very first frame would start an utterance that never ends.
    ep = Endpointer(silence_ms=300)
    assert run(ep, noise(150, 0.05)) == []
    assert not ep._speaking and ep._floor > 0.02
