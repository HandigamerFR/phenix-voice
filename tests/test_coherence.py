"""Étape 1 du plan de cohérence (validée 13/11) — couche `postprocess/coherence.py`.

Principes vérifiés ici :
- AUCUNE ponctuation automatique : le texte du modèle est nettoyé en entier
  (seule la ponctuation dictée — « virgule », « point »… — est écrite) ;
- cohérence casse/espaces minimale entre souffles : majuscule seulement au
  début du texte et après une fin de phrase dictée, minuscule sinon, espace de
  liaison seulement quand il manque (fin du « chaque souffle majuscule » et du
  « mot.Nouveau ») ;
- correction « règle de texte » (ponctuation/casse/espace uniquement) ≠
  correction acoustique : les premières n'alimentent pas l'apprentissage audio.
"""

from __future__ import annotations

from phenix_voice.postprocess.coherence import (
    adapt_chunk_to_context,
    is_textual_only_correction,
    strip_auto_punctuation,
)
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
)


# --- strip_auto_punctuation -------------------------------------------------


def test_strip_removes_all_model_punctuation() -> None:
    assert strip_auto_punctuation("Bonjour, comment allez-vous ?") == (
        "Bonjour comment allez-vous"
    )
    assert strip_auto_punctuation("Mot.\nNouveau") == "Mot\nNouveau"
    assert strip_auto_punctuation("salut !") == "salut"
    assert strip_auto_punctuation("un; deux: trois") == "un deux trois"


def test_strip_keeps_french_apostrophes_and_hyphens() -> None:
    assert strip_auto_punctuation("c'est un vas-y, d'accord") == (
        "c'est un vas-y d'accord"
    )


def test_strip_protects_numeric_separators() -> None:
    assert strip_auto_punctuation("il mesure 3,5 m") == "il mesure 3,5 m"
    assert strip_auto_punctuation("il mesure 3.5 m") == "il mesure 3.5 m"
    assert strip_auto_punctuation("à 14:30 pile") == "à 14:30 pile"
    assert strip_auto_punctuation("du 13/11/2026") == "du 13/11/2026"


def test_strip_empty_and_no_punct_unchanged() -> None:
    assert strip_auto_punctuation("") == ""
    assert strip_auto_punctuation("texte simple") == "texte simple"


# --- adapt_chunk_to_context -------------------------------------------------


def test_capital_only_at_start_and_after_sentence_end() -> None:
    # Début de texte → majuscule
    assert adapt_chunk_to_context("bonjour", "") == "Bonjour"
    # Milieu de phrase → minuscule (fin de la majuscule forcée par souffle)
    assert adapt_chunk_to_context("comment ça va", "Bonjour") == " comment ça va"
    # Après fin de phrase dictée → majuscule + espace de liaison
    assert adapt_chunk_to_context("nouvelle phrase", "Salut.") == " Nouvelle phrase"
    assert adapt_chunk_to_context("nouvelle phrase", "Salut ?") == " Nouvelle phrase"
    # Après un saut de ligne → majuscule, sans espace
    assert adapt_chunk_to_context("deuxième ligne", "première ligne\n") == (
        "Deuxième ligne"
    )


def test_no_duplicate_space_or_leading_space() -> None:
    # Le souffle se termine déjà par un espace → pas de double espace
    assert adapt_chunk_to_context("suite", "Salut ") == "suite"
    # Début de texte → pas d'espace inaugural (mais majuscule, voir plus haut)
    assert adapt_chunk_to_context("début", "") == "Début"
    # Le texte qui commence déjà par un espace/ponctuation n'en reçoit pas
    assert adapt_chunk_to_context(" déjà", "Suite") == " déjà"
    assert adapt_chunk_to_context("...", "Suite") == "..."


def test_context_none_equals_start_of_text() -> None:
    assert adapt_chunk_to_context("bonjour", None) == "Bonjour"
    assert adapt_chunk_to_context("", None) == ""


# --- is_textual_only_correction --------------------------------------------


def test_textual_only_corrections_detected() -> None:
    # Ponctuation ajoutée/retraitée
    assert is_textual_only_correction("Bonjour comment ça va", "Bonjour, comment ça va")
    # Casse seule
    assert is_textual_only_correction("Bonjour", "bonjour")
    # Espace seul
    assert is_textual_only_correction("salut la famille", "salut  la famille")
    # Ponctuation finale retirée
    assert is_textual_only_correction("fin de phrase.", "fin de phrase")


def test_acoustic_corrections_not_misclassified() -> None:
    # Changement de lettres → correction acoustique (apprentissage audio)
    assert not is_textual_only_correction("bonjour", "bonsoir")
    # Accents significatifs : « était » ≠ « etait » → classé acoustique
    assert not is_textual_only_correction("il était là", "il etait la")
    assert not is_textual_only_correction("été", "ete")
    # Texte vide → jamais « règle de texte »
    assert not is_textual_only_correction("", "texte")
    assert not is_textual_only_correction("texte", "")


# --- intégration HybridPunctuationProcessor --------------------------------


def test_no_auto_punctuation_from_model() -> None:
    proc = HybridPunctuationProcessor()
    # Sortie type Whisper avec ponctuation auto → entièrement retirée
    r = proc.process("Bonjour, comment allez-vous.")
    assert r.intent == VoiceIntentType.DICTATION
    assert r.text_to_inject == "Bonjour comment allez-vous"
    # Deuxième souffle sans ponctuation dictée → ni ponctuation, ni majuscule forcée
    r2 = proc.process("Je vais bien merci")
    assert r2.text_to_inject == " je vais bien merci"


def test_dictated_punctuation_still_written() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("bonjour virgule comment allez-vous point d'interrogation")
    assert r.text_to_inject == "Bonjour, comment allez-vous ?"
    # Après « ? » : majuscule + espace de liaison sur le souffle suivant
    r2 = proc.process("tout va bien")
    assert r2.text_to_inject == " Tout va bien"


def test_press_enter_resets_capital_context() -> None:
    proc = HybridPunctuationProcessor()
    proc.process("première phrase")
    r_enter = proc.process("Presser Entrée")
    assert r_enter.intent == VoiceIntentType.PRESS_ENTER
    r2 = proc.process("nouvelle ligne")
    assert r2.text_to_inject == "Nouvelle ligne"


# --- format_dictation / format_alternatives (choix jusqu'à 9) ---------------


def test_format_dictation_matches_process_output() -> None:
    """`format_dictation` (cœur partagé) produit exactement le texte de `process`."""
    p1 = HybridPunctuationProcessor()
    p2 = HybridPunctuationProcessor()
    r = p1.process("salut virgule tout le monde")
    text, variant, _sub = p2.format_dictation("salut virgule tout le monde")
    assert text == r.text_to_inject == "Salut, tout le monde"
    assert variant is None
    # Mémorisation du contexte pour le souffle suivant
    r2 = p2.process("suite")
    assert r2.text_to_inject == " suite"


def test_format_alternatives_use_same_rules_as_dictation() -> None:
    """Les alternatives reçoivent le MÊME formatage que le texte dicté."""
    proc = HybridPunctuationProcessor()
    # Début de texte → majuscule ; ponctuation auto du modèle (« ? », « . ») retirée.
    alts = proc.format_alternatives(
        ["bonjour, tout le monde ?", "salut les amis."],
        previous_text="",
        chosen_text="texte retenu",
    )
    assert alts == ["Bonjour tout le monde", "Salut les amis"]


def test_format_alternatives_exclude_chosen_and_dedup() -> None:
    proc = HybridPunctuationProcessor()
    alts = proc.format_alternatives(
        [
            "Je teste Phénix.",   # après formatage == choix retenu -> exclu
            "JE TESTE PHÉNIX",    # casse seule -> même clé casefold -> exclu
            "Je teste Phoenix",   # réellement différent (accents) -> conservé
            "",                   # vide -> exclu
        ],
        previous_text="",
        chosen_text="Je teste Phénix",
    )
    assert alts == ["Je teste Phoenix"]


def test_format_alternatives_do_not_mutate_context() -> None:
    """Proposer une alternative ne doit PAS déplacer le contexte inter-souffles."""
    proc = HybridPunctuationProcessor()
    proc.process("première phrase")
    proc.format_alternatives(
        ["nouvelle phrase complètement différente"],
        previous_text="première phrase",
        chosen_text="x",
    )
    r = proc.process("suite")
    # Contexte toujours « première phrase » (milieu) → minuscule + espace
    assert r.text_to_inject == " suite"


def test_format_alternatives_adapt_to_context_mid_sentence() -> None:
    proc = HybridPunctuationProcessor()
    alts = proc.format_alternatives(
        ["Nouvelle idée.", "AUTRE IDÉE"],
        previous_text="Voilà ce que je pense",
        chosen_text="",
    )
    # Milieu de phrase → minuscule en tête, espace de liaison ajouté puis strip
    assert alts[0] == "nouvelle idée"
