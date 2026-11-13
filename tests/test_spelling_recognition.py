"""Mode épellation : filtrage sur l'utile + rejet explicite (étape 2, 13/11).

Vérifie :
- la tolérance phonétique des lettres NATO (prononciation dysarthrique :
  « Make. » ≈ « mike » → « m », table restant en français naturel) ;
- la conversion via les ALTERNATIVES du STT quand le texte principal échoue
  (« M. » parmi les hypothèses de « Make. ») ;
- le rejet EXPLICITE d'un souffle non reconnu (fini le silence `dictation_empty`).
"""

from __future__ import annotations

from phenix_voice.postprocess.punctuation import (
    spelling_from_result,
    text_to_nato_spelling,
)


# --- tolérance phonétique NATO ----------------------------------------------


def test_fuzzy_nato_accepts_near_pronunciations() -> None:
    assert text_to_nato_spelling("Make.") == "m"     # ≈ mike
    assert text_to_nato_spelling("make") == "m"
    assert text_to_nato_spelling("Alpha Mike") == "am"
    assert text_to_nato_spelling("Bravo Echo") == "be"


def test_fuzzy_nato_rejects_far_words() -> None:
    # Écart > 1 : aucune lettre inventée (le rejet explicite prend le relais)
    assert text_to_nato_spelling("Bank.") == ""
    assert text_to_nato_spelling("Veil.") == ""
    assert text_to_nato_spelling("bonjour") == ""
    # Mots < 3 lettres exclus du flou (trop de faux amis)
    assert text_to_nato_spelling("un") == ""


# --- spelling_from_result : alternatives + rejet -----------------------------


def test_spelling_from_result_uses_stt_alternatives() -> None:
    # Texte principal inutile, mais « alpha bravo » figure parmi les hypothèses
    text, rejected = spelling_from_result("inutile", ["inutile,", "alpha bravo"])
    assert text == "ab"
    assert rejected is None


def test_spelling_from_result_succeeds_on_direct_match() -> None:
    text, rejected = spelling_from_result("Make.", ["Make,", "M."])
    assert text == "m"          # fuzzy direct, alternatives inutiles
    assert rejected is None


def test_spelling_from_result_rejects_explicitly() -> None:
    text, rejected = spelling_from_result("Bank.", ["Bank!", "inutile"])
    assert text == ""
    assert rejected == "Bank."  # l'appelant DOIT afficher ce rejet


def test_spelling_from_result_keeps_silence_as_silence() -> None:
    text, rejected = spelling_from_result("   ", [])
    assert text == ""
    assert rejected is None  # souffle vide : pas de message d'erreur
