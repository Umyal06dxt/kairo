"""Speech I/O: Whisper STT, Edge TTS, and ALSA capture/playback via arecord/aplay
(no PortAudio or ffmpeg needed). Heavy deps are imported lazily."""

import asyncio
import io

import numpy as np

SR = 16000


class WhisperSTT:
    def __init__(self, model_size: str = "base.en", device: str = "cpu",
                 compute_type: str = "int8"):
        from faster_whisper import WhisperModel  # lazy: optional dependency
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono 16 kHz."""
        segments, _ = self._model.transcribe(audio, language="en", vad_filter=False,
                                             beam_size=1, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    async def atranscribe(self, audio: np.ndarray) -> str:
        return await asyncio.get_running_loop().run_in_executor(None, self.transcribe, audio)


def decode_audio(data: bytes, sr: int = 24000) -> np.ndarray:
    """Decode compressed audio (Edge TTS mp3) to int16 mono PCM at `sr` using PyAV."""
    import av
    out = []
    with av.open(io.BytesIO(data)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in container.decode(audio=0):
            for f in resampler.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out) if out else np.zeros(0, dtype=np.int16)


class EdgeTTS:
    OUT_SR = 24000

    def __init__(self, voice: str = "en-US-AriaNeural"):
        self.voice = voice

    async def synth(self, text: str) -> np.ndarray:
        import edge_tts
        mp3 = b""
        async for chunk in edge_tts.Communicate(text, self.voice).stream():
            if chunk["type"] == "audio":
                mp3 += chunk["data"]
        return decode_audio(mp3, self.OUT_SR)

    async def play(self, pcm: np.ndarray) -> None:
        if len(pcm) == 0:
            return
        proc = await asyncio.create_subprocess_exec(
            "aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(self.OUT_SR), "-c", "1",
            stdin=asyncio.subprocess.PIPE)
        await proc.communicate(pcm.astype(np.int16).tobytes())


class ArecordMic:
    """Async stream of float32 frames from the default ALSA capture device."""

    def __init__(self, frame_ms: int = 30):
        self.frame_samples = SR * frame_ms // 1000
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self):
        self._proc = await asyncio.create_subprocess_exec(
            "arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(SR), "-c", "1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        return self

    async def __aexit__(self, *exc):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            await self._proc.wait()

    async def frames(self):
        n = self.frame_samples * 2
        while True:
            try:
                raw = await self._proc.stdout.readexactly(n)
            except asyncio.IncompleteReadError:
                return  # arecord exited (no device / permission)
            yield np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
