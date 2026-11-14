"""Mode épellation : filtrage sur l'utile + rejet explicite (étape 2, 13/11).

Vérifie :
- la tolérance phonétique des lettres NATO (prononciation dysarthrique :
  « Make. » ≈ « mike » → « m », table restant en français naturel) ;
- la conversion via les ALTERNATIVES du STT quand le texte principal échoue
  (« M. » parmi les hypothèses de « Make. ») ;
- le rejet EXPLICITE d'un souffle non reconnu (fini le silence `dictation_empty`).
"""

from __future__ import annotations

import numpy as np

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


# --- Accents dictés (formes validées 13/11 : lettres OTAN seulement) ----------


def test_accent_composes_on_previous_nato_letter() -> None:
    # « écho accent aigu » → « é » (une seule lettre, pas « e » + « é »)
    assert text_to_nato_spelling("écho accent aigu") == "é"
    # Formes validées par l'utilisateur : « Charlie cédille » ET « accent cédille »
    assert text_to_nato_spelling("charlie cédille") == "ç"
    assert text_to_nato_spelling("charlie accent cédille") == "ç"
    assert text_to_nato_spelling("alpha accent grave") == "à"
    assert text_to_nato_spelling("india tréma") == "ï"
    assert text_to_nato_spelling("uniforme accent circonflexe") == "û"


def test_accent_standalone_when_no_letter_before() -> None:
    assert text_to_nato_spelling("accent aigu") == "é"
    assert text_to_nato_spelling("accent grave") == "è"
    assert text_to_nato_spelling("cédille") == "ç"


def test_accent_falls_back_when_letter_cannot_take_it() -> None:
    # « kilo accent aigu » : k ne prend pas l'aigu → caractère autonome après (« ké »)
    assert text_to_nato_spelling("kilo accent aigu") == "ké"
    # Après un espace : caractère autonome
    assert text_to_nato_spelling("espace accent aigu") == " é"


def test_accent_forms_tolerance() -> None:
    # Plurales (« accents aigus »), casse et accents STT tolérés
    assert text_to_nato_spelling("Accent Aigus") == "é"
    assert text_to_nato_spelling("écho accents graves") == "è"
    # « cedille » sans accent accepté (sortie STT dégradée)
    assert text_to_nato_spelling("charlie cedille") == "ç"


# --- spelling_with_acoustic_net : STT d'abord, filet OTAN ensuite ------------


class _FakeProtector:
    """Double d'AcousticCommandProtector : hit OTAN programmable."""

    def __init__(self, hit: tuple[str, float] | None = None) -> None:
        self.hit = hit
        self.calls = 0

    def match_nato_letter(self, audio_pcm: object, sr: int = 16000) -> tuple[str, float] | None:
        self.calls += 1
        return self.hit


def _silence(seconds: float = 1.0) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.float32)


def test_acoustic_net_prefers_stt_and_skips_protector() -> None:
    from phenix_voice.main import spelling_with_acoustic_net

    protector = _FakeProtector(hit=("Mike", 0.05))
    text, rejected, nato = spelling_with_acoustic_net(
        protector, _silence(), "Make.", ["Make,", "M."]
    )
    assert text == "m"            # conversion STT directe (fuzzy ≈ mike)
    assert rejected is None
    assert nato is None           # le filet acoustique n'a pas été sollicité
    assert protector.calls == 0


def test_acoustic_net_falls_back_to_nato_templates() -> None:
    from phenix_voice.main import spelling_with_acoustic_net

    protector = _FakeProtector(hit=("Mike", 0.11))
    text, rejected, nato = spelling_with_acoustic_net(
        protector, _silence(), "inutile", ["rien de tel"]
    )
    assert text == "m"            # lettre sauvée par le filet du studio mixte
    assert rejected is None       # plus de rejet affiché quand le filet a tranché
    assert nato == ("Mike", 0.11)
    assert protector.calls == 1


def test_acoustic_net_keeps_explicit_rejection_when_nothing_works() -> None:
    from phenix_voice.main import spelling_with_acoustic_net

    protector = _FakeProtector(hit=None)
    text, rejected, nato = spelling_with_acoustic_net(
        protector, _silence(), "Bank.", ["Bank!", "inutile"]
    )
    assert text == ""
    assert rejected == "Bank."    # l'appelant DOIT afficher ce rejet
    assert nato is None


def test_acoustic_net_keeps_silence_as_silence() -> None:
    from phenix_voice.main import spelling_with_acoustic_net

    protector = _FakeProtector(hit=None)
    text, rejected, nato = spelling_with_acoustic_net(protector, _silence(), "   ", [])
    assert text == ""
    assert rejected is None       # souffle vide : pas de message d'erreur
    assert nato is None


def test_acoustic_net_saves_stt_silence_with_template_hit() -> None:
    """Le STT rend parfois vide (anomalie dictation_empty) : le filet doit rattraper."""
    from phenix_voice.main import spelling_with_acoustic_net

    protector = _FakeProtector(hit=("Mike", 0.09))
    text, rejected, nato = spelling_with_acoustic_net(protector, _silence(), "  ", [])
    assert text == "m"
    assert rejected is None
    assert nato == ("Mike", 0.09)
