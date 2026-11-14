"""Variantes d'accord grammatical dans la boîte « Corriger ça » (décision 14/11).

Le texte dicté reste correct par défaut ; la boîte propose en PLUS toutes les
variantes d'accord RÉELLES du texte (même grammaticalement fautives au contexte
près), validées par le lexique Lexique383 compilé (voir
src/phenix_voice/resources/README_Lexique383.txt).
"""

from __future__ import annotations

from phenix_voice.postprocess.agreement import (
    agreement_variants,
    load_agreement_lexicon,
    merge_agreement_alternatives,
)


def test_lexicon_resource_is_present_and_usable() -> None:
    lexicon = load_agreement_lexicon()
    assert len(lexicon) > 10_000, "lexique d'accord compilé absent ou trop maigre"
    # Formes de l'exemple utilisateur
    assert set(lexicon["terminées"]) >= {"terminé", "terminée", "terminés"}


def test_user_example_offers_all_agreement_forms() -> None:
    text = "les conversations sont terminées."
    variants = agreement_variants(text)
    assert "les conversations sont terminé." in variants
    assert "les conversations sont terminée." in variants
    assert "les conversations sont terminés." in variants
    # Même « fautif » au contexte près : le nom au singulier est proposé
    assert "les conversation sont terminées." in variants
    # Le texte DÉFAUT n'est jamais redéclaré comme variante
    assert text not in variants


def test_variants_are_ordered_from_the_end_of_sentence() -> None:
    """Les variantes du dernier mot passent en tête (l'accord se joue en fin)."""
    variants = agreement_variants("les conversations sont terminées.")
    # Les 3 premières propositions remplacent le dernier mot (« terminées »)…
    assert len(variants) >= 4
    for v in variants[:3]:
        assert v.startswith("les conversations sont terminé")
    # …et celle du nom (« conversations ») arrive après.
    assert variants[3] == "les conversation sont terminées."


def test_case_of_dictated_word_is_preserved() -> None:
    variants = agreement_variants("Il a dit Terminées hier.")
    assert "Il a dit Terminé hier." in variants
    assert "Il a dit Terminée hier." in variants
    # Casse TOUT MAJUSCULES conservée aussi
    uppers = agreement_variants("FIN DEPHASE TERMINÉES.")
    assert any(v.endswith("TERMINÉ.") for v in uppers)


def test_no_invented_word_is_ever_proposed() -> None:
    # « cafée » n'existe pas en français : jamais proposé (validation lexique).
    variants = agreement_variants("Je bois un café.")
    assert variants, "le pluriel réel « cafés » doit être proposé"
    assert not any("cafée" in v for v in variants)
    assert "Je bois un cafés." in variants  # réel, même si faux au contexte


def test_apostrophe_prefix_is_preserved() -> None:
    variants = agreement_variants("C'est d'accord.")
    assert "C'est d'accords." in variants


def test_variants_are_capped() -> None:
    text = "les conversations sont terminées."
    assert len(agreement_variants(text, max_variants=2)) == 2
    assert agreement_variants(text, max_variants=0) == []


def test_empty_or_blank_text_has_no_variants() -> None:
    assert agreement_variants("") == []
    assert agreement_variants("   ") == []


def test_merge_puts_agreement_variants_first_and_caps_at_nine() -> None:
    stt_alts = [f"hypothèse acoustique {i}" for i in range(12)]
    merged = merge_agreement_alternatives(
        "les conversations sont terminées.", stt_alts, max_total=9
    )
    assert len(merged) <= 9
    assert merged[0] == "les conversations sont terminé."
    assert "hypothèse acoustique 0" in merged


def test_merge_deduplicates_stt_alternative_equal_to_variant() -> None:
    merged = merge_agreement_alternatives(
        "les conversations sont terminées.",
        ["les conversations sont terminé."],
        max_total=9,
    )
    assert merged.count("les conversations sont terminé.") == 1
