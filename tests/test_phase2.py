"""Tests unitaires et d'intégration de la Phase 2 :
- Arbitre de Plausibilité Contextuelle (préservation de « loi adoptée » vs correction de « vocale adoptée »).
- Commandes micro Phénix sans conflit avec Dragon (« Phénix écoute », « Phénix repos », « Couper Phénix »).
- Commandes d'édition et de correction (« Corriger ça », « Choisir un/deux », « Oups », « Presser Entrée »).
"""

from __future__ import annotations

import json
from pathlib import Path
import wave
import numpy as np
import pytest

from phenix_voice.audio.fingerprints import AcousticCommandProtector
from phenix_voice.audio.vad import CHUNK_SAMPLES, SileroVAD
from phenix_voice.postprocess.plausibility import PlausibilityArbitrator
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
)
from phenix_voice.stt.engine import WhisperDirectMLEngine


def test_plausibility_arbitrator_contextual_disambiguation() -> None:
    arb = PlausibilityArbitrator(enable_strict_dictionary=False)

    # 1. Contexte juridique/législatif : « adoptée » est plausible et DOIT être conservé !
    res_law = arb.arbitrate(
        raw_text="La loi a été adoptée par le parlement.",
        alternatives=["La loi a été adaptée par le parlement."],
        acoustic_confidence=0.88,
        audio_duration_s=3.5,
    )
    assert "adoptée" in res_law.best_text

    # 2. Contexte vocal/ergonomique : « adoptée » + « pour un aligné » sont corrigés par plausibilité !
    res_voice = arb.arbitrate(
        raw_text="Je teste la reconnaissance vocale adoptée pour un aligné.",
        alternatives=[],
        acoustic_confidence=0.82,
        audio_duration_s=4.5,
    )
    assert "adaptée" in res_voice.best_text
    assert "point à la ligne" in res_voice.best_text

    # 3. En milieu de phrase longue, « il faisait ça » est du texte normal, PAS la commande « Effacer ça »
    res_prose = arb.arbitrate(
        raw_text="Autrefois, il faisait ça tous les matins.",
        alternatives=[],
        acoustic_confidence=0.90,
        audio_duration_s=3.8,
    )
    assert res_prose.best_text == "Autrefois, il faisait ça tous les matins."


def test_phase2_commands_and_punctuation() -> None:
    proc = HybridPunctuationProcessor(enable_strict_dictionary=False)

    assert proc.process("Phénix écoute", is_sleeping=True).intent == VoiceIntentType.WAKE
    assert proc.process("Phénix repos").intent == VoiceIntentType.SLEEP
    assert proc.process("Couper Phénix").intent == VoiceIntentType.MUTE_MIC
    assert proc.process("Presser Entrée").intent == VoiceIntentType.PRESS_ENTER
    assert proc.process("Corriger ça").intent == VoiceIntentType.OPEN_CORRECTION
    assert proc.process("Oups").intent == VoiceIntentType.OUPS_NO_LEARN

    c1 = proc.process("Choisir un")
    assert c1.intent == VoiceIntentType.CHOOSE_ALT
    assert c1.choice_index == 1

    c2 = proc.process("Choisir deux")
    assert c2.intent == VoiceIntentType.CHOOSE_ALT
    assert c2.choice_index == 2

    sel = proc.process("Sélectionner reconnaissance")
    assert sel.intent == VoiceIntentType.SELECT_TARGET
    assert sel.target_arg == "reconnaissance"


def test_calibrated_12_commands_on_user_voice(
    shared_engine: WhisperDirectMLEngine,
) -> None:
    manifest_path = Path("user_data/calibration/manifest.json")
    if not manifest_path.exists():
        pytest.skip("Manifeste d'étalonnage absent")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in manifest["samples"]}
    if "cmd_phenix_ecoute" not in by_id:
        pytest.skip("Étalonnage des 12 commandes non présent")

    engine = shared_engine
    arb = PlausibilityArbitrator(enable_strict_dictionary=False)
    proc = HybridPunctuationProcessor(enable_strict_dictionary=False)
    protector = AcousticCommandProtector()

    expected_intents = {
        "cmd_phenix_ecoute": VoiceIntentType.WAKE,
        "cmd_phenix_repos": VoiceIntentType.SLEEP,
        "cmd_couper_phenix": VoiceIntentType.MUTE_MIC,
        "cmd_effacer_ca": VoiceIntentType.SCRATCH_LAST,
        "cmd_presser_entree": VoiceIntentType.PRESS_ENTER,
        "cmd_corriger_ca": VoiceIntentType.OPEN_CORRECTION,
        "cmd_oups": VoiceIntentType.OUPS_NO_LEARN,
        "cmd_choisir_un": VoiceIntentType.CHOOSE_ALT,
        "cmd_choisir_deux": VoiceIntentType.CHOOSE_ALT,
    }

    for cmd_id, expected_intent in expected_intents.items():
        item = by_id[cmd_id]
        with wave.open(item["raw_wav"], "rb") as wf:
            pcm = (
                np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(
                    np.float32
                )
                / 32768.0
            )
        stt_res = engine.transcribe(pcm)
        fp = protector.match_command(pcm)
        arb_res = arb.arbitrate(
            raw_text=stt_res.text,
            alternatives=stt_res.alternatives,
            acoustic_confidence=stt_res.confidence,
            audio_duration_s=stt_res.audio_duration_s,
            acoustic_fp_match=fp,
        )
        proc.reset_context()
        out = proc.process(
            arb_res.best_text, is_sleeping=(cmd_id == "cmd_phenix_ecoute")
        )
        assert (
            out.intent == expected_intent
        ), f"Échec sur {cmd_id}: stt={stt_res.text!r} -> arb={arb_res.best_text!r} -> intent={out.intent}"
