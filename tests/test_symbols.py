"""Formes orales de symboles (« astérisque » → « * », façon Dragon) et
dictionnaire personnel de formes orales.

Principe de design vérifié ici :
- tables en français naturel, tolérance uniquement dans la clé de comparaison ;
- substitution en place avec typographie française contextuelle
  (signes doubles espacés, `@` collé en contexte e-mail) ;
- formes ambiguës (« euro »…) → symbole par défaut + variante « mot dicté »
  pour la popup de choix (voix « choix un / deux ») ;
- portée dictée + mode épellation (adresses e-mail) ;
- dictionnaire personnel persisté, ajoutable depuis le volet de correction.
"""

from __future__ import annotations

from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
    text_to_nato_spelling,
)
from phenix_voice.postprocess.symbols import (
    SpokenFormStore,
    apply_symbol_forms,
)


def test_core_symbol_replaces_word_in_place() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("cinq astérisque trois")
    assert r.intent == VoiceIntentType.DICTATION
    assert r.text_to_inject == "Cinq * trois"
    # Pas d'ambiguïté → pas de popup
    assert r.symbol_choices is None


def test_spaced_symbol_gets_french_spacing() -> None:
    proc = HybridPunctuationProcessor()
    # « % » : espace avant et après (typographie française)
    r = proc.process("5 pourcentage de réussite")
    assert r.text_to_inject == "5 % de réussite"
    # Forme ambiguë : symbole par défaut + variante « mot dicté » complète
    assert r.symbol_form == "pourcentage"
    assert r.symbol_char == "%"
    assert r.symbol_choices is not None
    assert r.symbol_choices[0] == r.text_to_inject
    assert r.symbol_choices[1] == "5 pourcentage de réussite"


def test_arobase_glued_in_email_context() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("écris laure arobase gmail")
    assert r.text_to_inject == "Écris laure@gmail"


def test_arobase_keeps_dictated_spaces_outside_email_context() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("contactez arobase le support")
    assert r.text_to_inject == "Contactez @ le support"


def test_ambiguous_euro_offers_symbol_or_word_choices() -> None:
    proc = HybridPunctuationProcessor()
    r = proc.process("j'ai cinq euros sur la table")
    assert r.text_to_inject == "J'ai cinq € sur la table"
    assert r.symbol_form == "euros"
    assert r.symbol_char == "€"
    assert r.symbol_choices is not None
    assert r.symbol_choices == [
        "J'ai cinq € sur la table",
        "J'ai cinq euros sur la table",
    ]


def test_multiword_symbol_form() -> None:
    sub = apply_symbol_forms("insère barre oblique inverse ici")
    assert sub.text == "insère \\ ici"
    assert sub.variant_text is None


def test_spelling_mode_emits_symbols_for_email() -> None:
    assert (
        text_to_nato_spelling("mot laure arobase mot gmail point mot com")
        == "laure@gmail.com"
    )
    assert text_to_nato_spelling("alpha virgule bravo") == "a,b"


def test_personal_spoken_forms_roundtrip(tmp_path) -> None:
    path = tmp_path / "spoken_forms.json"
    proc = HybridPunctuationProcessor(spoken_forms_path=path)
    assert proc.spoken_forms.add("truc machin", "chose élégante")
    r = proc.process("bonjour truc machin")
    assert r.text_to_inject == "Bonjour chose élégante"

    # Persistance : un nouveau moteur recharge le dictionnaire personnel
    proc2 = HybridPunctuationProcessor(spoken_forms_path=path)
    assert proc2.process("salut truc machin").text_to_inject == "Salut chose élégante"

    # Refus si texte identique ou trop court
    assert not proc.spoken_forms.add("truc machin", "truc machin")
    assert not proc.spoken_forms.add("a", "b")


def test_personal_form_can_seed_symbol(tmp_path) -> None:
    store = SpokenFormStore(tmp_path / "forms.json")
    assert store.add("arobase professionnelle", "@")
    # Contexte e-mail détecté (« contact … ici ») → « @ » collé
    assert store.apply("contact arobase professionnelle ici") == "contact@ici"


def test_personal_spoken_form_accepts_symbolic_written_text(tmp_path) -> None:
    """Écrit PUREMENT symbolique (« Birgule, » → « , ») : accepté ET retrouvé.

    `command_keys(",")` ne renvoie plus une clé vide : le signe lui-même sert
    de clé de repli, de sorte que le cycle ajout → recherche fasse round-trip.
    """
    store = SpokenFormStore(tmp_path / "forms.json")
    assert store.add("Birgule, ", ",")
    # Lookup : la forme entendue est retrouvée (round-trip add → recherche)
    assert store.apply("birgule") == ","
    assert store.apply("Birgule") == ","

    # Persistance : un nouveau store recharge la forme symbolique
    store2 = SpokenFormStore(tmp_path / "forms.json")
    assert store2.apply("birgule") == ","

    # Une forme alphabétique existante continue de fonctionner à côté
    assert store.add("truc machin", "chose élégante")
    assert store.apply("truc machin") == "chose élégante"


def test_personal_spoken_form_refusals_still_hold(tmp_path) -> None:
    store = SpokenFormStore(tmp_path / "forms.json")
    # Écrit/entendu identique → refus
    assert not store.add("Birgule,", "Birgule,")
    assert not store.add(",", ",")
    # Entendu vide ou réduit à des espaces → refus
    assert not store.add("", ",")
    assert not store.add("   ", ",")
    # Écrit vide ou réduit à des espaces → refus
    assert not store.add("Birgule,", "")
    assert not store.add("Birgule,", "   ")
    # Trop court côté entendu → refus (comportement historique)
    assert not store.add("a", "b")


def test_existing_punctuation_rules_still_win() -> None:
    # « virgule » / « deux points » restent gérés par SPOKEN_PUNCTUATION_RULES
    proc = HybridPunctuationProcessor()
    r = proc.process("bonjour virgule comment allez-vous")
    assert r.text_to_inject == "Bonjour, comment allez-vous"
    # Nouvelle phrase : le contexte de phrase est réinitialisé (comportement existant)
    proc.reset_context()
    r2 = proc.process("je viens deux points la suite")
    assert r2.text_to_inject == "Je viens : la suite"
