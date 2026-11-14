"""Filet acoustique du mode épellation : `match_nato_letter` (studio mixte, 13/11).

Les 26 mots OTAN enregistrés avec la voix de l'utilisateur (prompt `nato_*`) ne
doivent PAS être mélangés aux commandes vitales (`cmd_*`) : deux répertoires
d'empreintes distincts dans le même manifeste. Le filet répond uniquement pour
un segment de durée plausible et sous le seuil de distance DTW.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from phenix_voice.audio.fingerprints import AcousticCommandProtector

SAMPLE_RATE = 16000


def _tone(seconds: float = 1.0, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _write_wav(path: Path, pcm: np.ndarray) -> None:
    data = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(data.tobytes())


def _manifest(tmp_path: Path, samples: list[dict]) -> AcousticCommandProtector:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"samples": samples}, ensure_ascii=False), encoding="utf-8"
    )
    return AcousticCommandProtector(manifest_path=str(manifest))


def test_no_templates_means_no_match(tmp_path: Path) -> None:
    protector = _manifest(tmp_path, [])
    assert protector.nato_templates == {}
    assert protector.match_nato_letter(_tone()) is None


def test_nato_sample_is_routed_to_the_acoustic_net(tmp_path: Path) -> None:
    wav = tmp_path / "nato_mike.wav"
    _write_wav(wav, _tone())
    protector = _manifest(
        tmp_path,
        [
            {"id": "nato_mike", "expected_text": "Mike", "norm_wav": str(wav)},
            {"id": "cmd_oups", "expected_text": "Oups", "norm_wav": str(wav)},
        ],
    )
    # Routage : le mot OTAN alimente le filet, la commande vitale l'arbitrage.
    assert "nato_mike" in protector.nato_templates
    assert "cmd_oups" not in protector.nato_templates
    assert "cmd_oups" in protector.templates
    assert "nato_mike" not in protector.templates


def test_same_voice_nato_word_matches_with_letter_conversion(tmp_path: Path) -> None:
    from phenix_voice.postprocess.punctuation import text_to_nato_spelling

    wav = tmp_path / "nato_mike.wav"
    pcm = _tone()
    _write_wav(wav, pcm)
    protector = _manifest(
        tmp_path, [{"id": "nato_mike", "expected_text": "Mike", "norm_wav": str(wav)}]
    )
    hit = protector.match_nato_letter(pcm.copy())
    assert hit is not None
    word, distance = hit
    assert word == "Mike"
    assert distance <= protector.distance_threshold
    # L'appelant convertit ensuite le mot en lettre (« Mike » → « m »)
    assert text_to_nato_spelling(word) == "m"


def test_too_short_or_too_long_segments_are_not_matched(tmp_path: Path) -> None:
    wav = tmp_path / "nato_mike.wav"
    _write_wav(wav, _tone(seconds=1.2))
    protector = _manifest(
        tmp_path, [{"id": "nato_mike", "expected_text": "Mike", "norm_wav": str(wav)}]
    )
    assert protector.match_nato_letter(_tone(seconds=0.1)) is None   # < 0,2 s
    assert protector.match_nato_letter(_tone(seconds=3.0)) is None   # > 2,5 s (dicte trop long)


def test_corpus_samples_are_neither_commands_nor_nato(tmp_path: Path) -> None:
    wav = tmp_path / "corpus_01.wav"
    _write_wav(wav, _tone())
    protector = _manifest(
        tmp_path, [{"id": "corpus_01", "expected_text": "Le renard brun.", "norm_wav": str(wav)}]
    )
    assert protector.templates == {}
    assert protector.nato_templates == {}
