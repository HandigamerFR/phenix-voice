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
    assert r3.intent == VoiceIntentType.OUPS_NO_LEARN

    r4 = proc.process("Phénix repos.")
    assert r4.intent == VoiceIntentType.SLEEP

    # 4. En veille, le texte dicté est ignoré jusqu'à "Phénix écoute"
    r5 = proc.process("Texte ignoré pendant la veille", is_sleeping=True)
    assert r5.text_to_inject == ""

    r6 = proc.process("Phénix écoute !", is_sleeping=True)
    assert r6.intent == VoiceIntentType.WAKE


def test_silero_vad_and_amd_gpu_transcription(
    tmp_path: Path, shared_engine: WhisperDirectMLEngine
) -> None:
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

    engine = shared_engine
    assert engine.active_provider == "DmlExecutionProvider"

    # Transcription sur la Radeon RX 5700 XT
    result = engine.transcribe(pcm)
    assert "dicte" in result.text.lower()
    assert "active" in result.text.lower()
    assert result.total_ms < 850.0, f"Latence GPU trop élevée : {result.total_ms:.1f} ms"


def test_user_voice_calibration_samples_if_present(
    shared_engine: WhisperDirectMLEngine,
) -> None:
    manifest_path = Path("user_data/calibration/manifest.json")
    if not manifest_path.exists():
        pytest.skip("Pas d'échantillons d'étalonnage utilisateur présents")

    import json
    from phenix_voice.audio.fingerprints import AcousticCommandProtector

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    engine = shared_engine
    proc = HybridPunctuationProcessor()
    protector = AcousticCommandProtector()

    results_by_id: dict[str, ProcessedUtterance] = {}
    for item in manifest["samples"]:
        with wave.open(item["raw_wav"], "rb") as wf:
            pcm = (
                np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(
                    np.float32
                )
                / 32768.0
            )
        vad = SileroVAD()
        probs = [
            vad.process_chunk(pcm[i : i + CHUNK_SAMPLES])
            for i in range(0, len(pcm), CHUNK_SAMPLES)
        ]
        active = [i for i, p in enumerate(probs) if p >= 0.35]
        s = max(0, (active[0] - 8) * CHUNK_SAMPLES)
        e = min(len(pcm), (active[-1] + 10) * CHUNK_SAMPLES)
        segment = pcm[s:e]

        fp = protector.match_command(segment)
        stt_res = engine.transcribe(segment)
        eff_text = stt_res.text
        if fp is not None and (not eff_text or stt_res.confidence < 0.68):
            eff_text = fp[0]

        is_sleep = item["id"] == "cmd_ecoute"
        proc.reset_context()
        processed = proc.process(eff_text, is_sleeping=is_sleep)
        results_by_id[item["id"]] = processed

    assert results_by_id["cmd_oups"].intent == VoiceIntentType.OUPS_NO_LEARN
    assert "comment ça va aujourd'hui ?" in results_by_id["phrase_1"].text_to_inject.lower()
    assert "reconnaissance vocale adaptée.\n" in results_by_id["phrase_2"].text_to_inject.lower()

