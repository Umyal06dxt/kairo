import numpy as np

from kairo.voice.io import SR, decode_to_pcm16k, pcm_to_wav


def test_wav_roundtrip_through_the_browser_audio_path():
    t = np.arange(24000) / 24000
    pcm = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)  # 1 s @ 24 kHz
    wav = pcm_to_wav(pcm, 24000)
    assert wav[:4] == b"RIFF"
    x = decode_to_pcm16k(wav)  # resamples 24 kHz -> 16 kHz mono float32
    assert x.dtype == np.float32 and abs(len(x) - SR) < 400
    assert 0.3 < np.sqrt(np.mean(x ** 2)) < 0.4  # 0.5 amplitude sine ~0.354 rms preserved


def test_decode_empty_audio_returns_empty_array():
    assert len(decode_to_pcm16k(pcm_to_wav(np.zeros(0, dtype=np.int16), 16000))) == 0
