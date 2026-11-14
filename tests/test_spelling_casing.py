"""Commandes de casse en mode épellation, orthographe naturelle (décision 14/11).

Le « s » final est muet en français : les formes SINGULIER et PLURIEL doivent
toutes deux être acceptées à l'écoute (« Majuscule » ≡ « Majuscules »), sans
dépendance à l'orthographe écrite par le STT. Symétrique minuscules.
"""

from __future__ import annotations

from phenix_voice.postprocess.punctuation import (
    CASING_LOWER_ALL,
    CASING_LOWER_NEXT,
    CASING_RESET,
    CASING_UPPER_ALL,
    CASING_UPPER_NEXT,
    SpellingCasingState,
    spelling_casing_command,
)


def test_singular_and_plural_accepted_for_next_letter() -> None:
    """« s » muet : singulier ET pluriel reconnus, toutes casse et ponctuations."""
    for text in (
        "Majuscule",
        "majuscule",
        "MAJUSCULE",
        "majuscules",
        "Majuscules !",
        "majuscules.",
    ):
        assert spelling_casing_command(text) == CASING_UPPER_NEXT, text


def test_lower_next_is_symmetric() -> None:
    for text in ("Minuscule", "minuscule", "minuscules.", "MINUSCULES"):
        assert spelling_casing_command(text) == CASING_LOWER_NEXT, text


def test_sticky_forms_for_all_following_letters() -> None:
    for text in ("Tout en majuscules", "tout en majuscule", "TOUT EN MAJUSCULES !"):
        assert spelling_casing_command(text) == CASING_UPPER_ALL, text
    for text in ("Tout en minuscules", "tout en minuscule."):
        assert spelling_casing_command(text) == CASING_LOWER_ALL, text


def test_exit_forms_reset_casing() -> None:
    for text in (
        "Fin majuscules",
        "fin majuscule",
        "FIN MINUSCULES",
        "fin des majuscules",
        "fin des minuscules !",
    ):
        assert spelling_casing_command(text) == CASING_RESET, text


def test_ordinary_dictation_is_not_a_casing_command() -> None:
    assert spelling_casing_command("bonjour tout le monde") is None
    assert spelling_casing_command("il veut une majuscule au début") is None
    assert spelling_casing_command("") is None


def test_stt_alternatives_are_checked_too() -> None:
    assert spelling_casing_command("inutile", ["Majuscules !"]) == CASING_UPPER_NEXT
    assert spelling_casing_command("", ["tout en majuscules"]) == CASING_UPPER_ALL


def test_one_shot_casing_consumed_by_next_letters_only() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_UPPER_NEXT)
    assert state.apply_to_text("ab") == "AB"   # consommée : la lettre suivante est en majuscule
    assert state.apply_to_text("cd") == "cd"   # puis retour au normal
    # Un espace/chiffre ne consomme pas la commande ponctuelle
    state.apply_command(CASING_UPPER_NEXT)
    assert state.apply_to_text(" ") == " "
    assert state.apply_to_text("ef") == "EF"


def test_sticky_casing_last_until_reset() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_UPPER_ALL)
    assert state.apply_to_text("ab") == "AB"
    assert state.apply_to_text("cd") == "CD"
    state.apply_command(CASING_RESET)
    assert state.apply_to_text("ef") == "ef"


def test_one_shot_overrides_sticky_then_sticky_resumes() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_UPPER_ALL)
    state.apply_command(CASING_LOWER_NEXT)
    assert state.apply_to_text("AB") == "ab"   # ponctuel prime…
    assert state.apply_to_text("CD") == "CD"   # …puis le mode persistant reprend


def test_sticky_command_clears_pending_one_shot() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_LOWER_NEXT)
    state.apply_command(CASING_UPPER_ALL)
    assert state.apply_to_text("ab") == "AB"   # plus de minuscule en attente


def test_accents_follow_casing() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_UPPER_NEXT)
    assert state.apply_to_text("é") == "É"


def test_reset_clears_everything() -> None:
    state = SpellingCasingState()
    state.apply_command(CASING_UPPER_ALL)
    state.apply_command(CASING_LOWER_NEXT)
    state.reset()
    assert state.apply_to_text("ab") == "ab"
