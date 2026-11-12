"""Matching de commandes tolérant aux accents / apostrophes / casse / ponctuation.

Principe de design vérifié ici : les tables du code restent en français naturel et
la tolérance n'existe que dans la clé de comparaison (dérivée en mémoire).
"""

from __future__ import annotations

from phenix_voice.postprocess.punctuation import (
    COMMAND_RECALIBRATION_COMMANDS,
    HybridPunctuationProcessor,
    VoiceIntentType,
)
from phenix_voice.postprocess.rules import command_keys


def test_command_keys_are_tolerant_but_memory_only() -> None:
    # Même clé pour la forme naturelle et ses variantes dégradées
    natural = command_keys("C'était une commande,")
    assert natural, "la forme naturelle doit être retenue"
    assert natural[0] == "c'était une commande", "les accents/apostrophes sont conservés en tête"
    for degraded in ("c'etait une commande", "c etait une commande", "cetait une commande"):
        assert degraded in natural or any(degraded == k for k in natural)


def test_revise_command_recognized_in_all_written_forms() -> None:
    proc = HybridPunctuationProcessor()
    expected = VoiceIntentType.REVISE_COMMAND
    for text in (
        "C'était une commande,",
        "C'était une commande.",
        "C’était une commande",  # apostrophe typographique
        "C'etait une commande",  # sans accent
        "CETAIT UNE COMMANDE !",  # casse + ponctuation
        "c était une commande",  # apostrophe détachée par le STT
        "c'était un ordre",
        "C'était une commande vocale",
    ):
        got = proc.process(text).intent
        assert got == expected, f"{text!r} -> {got.value}, attendu {expected.value}"


def test_revise_command_target_arg_is_natural_french() -> None:
    # La valeur lue par l'utilisateur (target_arg) reste en français naturel
    assert set(COMMAND_RECALIBRATION_COMMANDS.values()) == {"corriger ça"}


def test_other_commands_still_match() -> None:
    proc = HybridPunctuationProcessor()
    assert proc.process("Phénix écoute").intent == VoiceIntentType.WAKE
    assert proc.process("phoenix ecoute !").intent == VoiceIntentType.WAKE
    assert proc.process("QUE PUIS-JE DIRE ?").intent == VoiceIntentType.SHOW_HELP
    assert proc.process("qu'est-ce que je peux dire").intent == VoiceIntentType.SHOW_HELP
    assert proc.process("Annuler sans apprendre").intent == VoiceIntentType.OUPS_NO_LEARN
    assert proc.process("Corriger ça").intent == VoiceIntentType.OPEN_CORRECTION
    assert proc.process("Choisir deux").intent == VoiceIntentType.CHOOSE_ALT
    assert proc.process("Presser Entrée").intent == VoiceIntentType.PRESS_ENTER
    assert proc.process("Mode épellation").intent == VoiceIntentType.ENTER_SPELLING
    assert proc.process("Fin d'épellation").intent == VoiceIntentType.EXIT_SPELLING
    assert proc.process("Couper Phénix").intent == VoiceIntentType.MUTE_MIC
    assert proc.process("Phénix repos").intent == VoiceIntentType.SLEEP


def test_dictation_is_not_grabbed_by_command_matching() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("bonjour virgule comment allez-vous")
    assert r.intent == VoiceIntentType.DICTATION
    assert r.text_to_inject == "Bonjour, comment allez-vous"


def test_choose_alt_supports_four_to_nine() -> None:
    """9 alternatives de correction : « Choisir quatre…neuf » (et variantes chiffre/numéro)."""
    proc = HybridPunctuationProcessor()
    expected = {
        "Choisir quatre": 4,
        "choix quatre": 4,
        "numéro quatre": 4,
        "Choisir 4": 4,
        "Choisir cinq": 5,
        "choix 5": 5,
        "Choisir six": 6,
        "Choisir sept": 7,
        "choisir 7": 7,
        "Choisir huit": 8,
        "choix huit": 8,
        "Choisir neuf": 9,
        "numéro 9": 9,
    }
    for text, index in expected.items():
        got = proc.process(text)
        assert got.intent == VoiceIntentType.CHOOSE_ALT, f"{text!r} -> {got.intent.value}"
        assert got.choice_index == index, f"{text!r} -> {got.choice_index}, attendu {index}"


def test_choose_alt_keeps_one_to_three() -> None:
    proc = HybridPunctuationProcessor()
    for text, index in (
        ("Choisir un", 1),
        ("choix deux", 2),
        ("Choisir trois", 3),
    ):
        got = proc.process(text)
        assert got.intent == VoiceIntentType.CHOOSE_ALT, f"{text!r} -> {got.intent.value}"
        assert got.choice_index == index, f"{text!r} -> {got.choice_index}, attendu {index}"
