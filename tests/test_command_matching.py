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


def test_spelling_exit_forms_include_passer_en_mode_dictee() -> None:
    """Sortie de la fenêtre d'épellation : formes validées 12/11 (« passer en mode dictée »)."""
    proc = HybridPunctuationProcessor()
    for text in (
        "Fin épellation",
        "Mode dictée",
        "Passer en mode dictée",
        "passer en mode dictee",  # variante sans accent (index mémoire uniquement)
        "Retour en mode dictée",
        "fin d'épellation",
    ):
        got = proc.process(text)
        assert got.intent == VoiceIntentType.EXIT_SPELLING, f"{text!r} -> {got.intent.value}"


def test_spelling_enter_forms_still_recognized() -> None:
    proc = HybridPunctuationProcessor()
    for text in ("Mode épellation", "alphabet radio", "mode epeler"):
        got = proc.process(text)
        assert got.intent == VoiceIntentType.ENTER_SPELLING, f"{text!r} -> {got.intent.value}"


def test_spelling_mode_restricts_intents_to_letters_and_safety() -> None:
    """En mode épellation, seules les lettres/chiffres/symboles/espace + sécurité sont écoutées."""
    from phenix_voice.main import SPELLING_ALLOWED_INTENTS

    allowed = SPELLING_ALLOWED_INTENTS
    assert VoiceIntentType.DICTATION in allowed  # converti en alphabet radio
    assert VoiceIntentType.EXIT_SPELLING in allowed
    assert VoiceIntentType.APPLY_CORRECTION in allowed
    for safety in (
        VoiceIntentType.MUTE_MIC,
        VoiceIntentType.SLEEP,
        VoiceIntentType.WAKE,
        VoiceIntentType.SHOW_HELP,
    ):
        assert safety in allowed, safety
    for blocked in (
        VoiceIntentType.ENTER_SPELLING,  # déjà en épellation : sans effet
        VoiceIntentType.OPEN_CORRECTION,
        VoiceIntentType.CHOOSE_ALT,
        VoiceIntentType.SELECT_TARGET,
        VoiceIntentType.SCRATCH_LAST,
        VoiceIntentType.OUPS_NO_LEARN,
        VoiceIntentType.PRESS_ENTER,
        VoiceIntentType.REVISE_COMMAND,
    ):
        assert blocked not in allowed, blocked


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


# --- Énoncés doublés (session 12/11 : la voix répète la commande entière) -----


def test_doubled_spelling_entry_still_enters_mode() -> None:
    """« Mode épellation, mode épellation. » doit entrer en épellation (23:35:09 raté)."""
    proc = HybridPunctuationProcessor()
    r = proc.process("Mode épellation, mode épellation.")
    assert r.intent == VoiceIntentType.ENTER_SPELLING, r.intent


def test_doubled_corriger_ca_still_opens_correction() -> None:
    """« Corriger ça, Corriger ça. » → correction du dernier segment, sans target (23:26:56)."""
    proc = HybridPunctuationProcessor()
    r = proc.process("Corriger ça, Corriger ça.")
    assert r.intent == VoiceIntentType.OPEN_CORRECTION, r.intent
    assert not r.target_arg, f"target_arg parasite : {r.target_arg!r}"


def test_doubled_revise_command_still_recognized() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("C'était une commande, c'était une commande.")
    assert r.intent == VoiceIntentType.REVISE_COMMAND, r.intent


def test_doubled_exit_spelling_still_exits() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("Fin épellation fin épellation")
    assert r.intent == VoiceIntentType.EXIT_SPELLING, r.intent


def test_doubled_non_command_stays_dictation_with_full_text() -> None:
    """Le repli ne touche QUE le matching : le texte dicté reste entier."""
    proc = HybridPunctuationProcessor()
    r = proc.process("bonjour tout le monde bonjour tout le monde")
    assert r.intent == VoiceIntentType.DICTATION
    assert r.text_to_inject == "Bonjour tout le monde bonjour tout le monde"


def test_collapse_repeated_utterance_unit() -> None:
    from phenix_voice.postprocess.rules import collapse_repeated_utterance

    assert collapse_repeated_utterance("mode épellation mode épellation") == "mode épellation"
    assert collapse_repeated_utterance("corriger ça corriger ça") == "corriger ça"
    # Triplé, accents différents entre les répétitions, non-répété : rien à replier
    assert collapse_repeated_utterance("a b a b a b") == "a b"
    assert collapse_repeated_utterance("mode epellation mode épellation") == "mode epellation"
    assert collapse_repeated_utterance("corriger ça hein") == "corriger ça hein"
