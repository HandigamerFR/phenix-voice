"""Tests unitaires et d'intégration matérielle de la Phase 1 (Socle Audio, GPU AMD & Dictée)."""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path
import numpy as np
import pytest

from phenix_voice.audio.vad import BreathSegmenter, CHUNK_SAMPLES, SileroVAD
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
)
from phenix_voice.stt.engine import WhisperDirectMLEngine
from phenix_voice.stt.mel import compute_log_mel_spectrogram


def test_log_mel_spectrogram_shape() -> None:
    audio = np.zeros(16000 * 2, dtype=np.float32)
    mel = compute_log_mel_spectrogram(audio, n_mels=128, target_frames=600)
    assert mel.shape == (1, 128, 600)
    assert mel.dtype == np.float32


def test_hybrid_punctuation_and_commands() -> None:
    proc = HybridPunctuationProcessor()

    # 1. Dictée avec ponctuation parlée
    r1 = proc.process("bonjour virgule comment allez-vous point d'interrogation")
    assert r1.intent == VoiceIntentType.DICTATION
    assert r1.text_to_inject == "Bonjour, comment allez-vous ?"

    # 2. Enchaînement d'un second souffle sur la même ligne
    r2 = proc.process("je teste Phénix Voice point à la ligne")
    assert r2.intent == VoiceIntentType.DICTATION
    assert r2.text_to_inject == " je teste Phénix Voice.\n"

    # 3. Commandes d'annulation et de mise en veille
    r3 = proc.process("Oups.")
    assert r3.intent == VoiceIntentType.SCRATCH_LAST

    r4 = proc.process("Au repos.")
    assert r4.intent == VoiceIntentType.SLEEP

    # 4. En veille, le texte dicté est ignoré jusqu'à "Écoute"
    r5 = proc.process("Texte ignoré pendant la veille", is_sleeping=True)
    assert r5.text_to_inject == ""

    r6 = proc.process("Écoute !", is_sleeping=True)
    assert r6.intent == VoiceIntentType.WAKE


def test_silero_vad_and_amd_gpu_transcription(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample_fr.wav"
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile('{wav_path}', $f); "
        "$s.Speak('Bonjour, je dicte directement dans la fenêtre active.'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)

    with wave.open(str(wav_path), "rb") as wf:
        pcm = (
            np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(
                np.float32
            )
            / 32768.0
        )

    # Ajouter 0,6s de silence à la fin pour déclencher la détection de fin de souffle du VAD
    padded_pcm = np.concatenate([pcm, np.zeros(int(0.6 * 16000), dtype=np.float32)])

    segmenter = BreathSegmenter(
        vad=SileroVAD(),
        silence_pause_ms=384,
    )
    segments: list[np.ndarray] = []
    for idx in range(0, len(padded_pcm), CHUNK_SAMPLES):
        chunk = padded_pcm[idx : idx + CHUNK_SAMPLES]
        seg = segmenter.feed_chunk(chunk)
        if seg is not None:
            segments.append(seg)

    assert len(segments) >= 1, "Silero VAD doit extraire au moins un segment de parole"

    engine = WhisperDirectMLEngine()
    assert engine.active_provider == "DmlExecutionProvider"

    # Transcription sur la Radeon RX 5700 XT
    result = engine.transcribe(pcm)
    assert "dicte" in result.text.lower()
    assert "active" in result.text.lower()
    assert result.total_ms < 400.0, f"Latence GPU trop élevée : {result.total_ms:.1f} ms"
