"""Couche de cohérence inter-souffles (étape 1 du plan de cohérence validé le 13/11).

Sous-ensemble minimal implémenté maintenant :
- `strip_auto_punctuation` : retire TOUTE la ponctuation/symbole auto-ajouté par le
  modèle de transcription. Le pipeline ne produit plus aucune ponctuation
  automatique : seules les formes dictées explicitement (« virgule », « point »,
  « arobase »…) sont écrites. La couche de cohérence remettra une ponctuation
  ultérieure selon des options choisies par l'utilisateur.
- `adapt_chunk_to_context` : casse et espacement cohérents avec le souffle
  précédent (majuscule uniquement au début du texte et après une fin de phrase
  dictée ; minuscule sinon ; espace de liaison seulement quand il manque).
- `is_textual_only_correction` : classe une correction en « règle de texte »
  (ponctuation/casse/espace uniquement) vs « erreur acoustique ». Les
  corrections de texte n'alimentent PAS l'apprentissage audio (pas de WAV/LoRA).
"""

from __future__ import annotations

import re

# Caractères de ponctuation/symboles susceptibles d'être auto-ajoutés par le modèle.
# ON NE TOUCHE PAS aux apostrophes (« c'est »), aux traits d'union (« vas-tu »),
# ni aux lettres/chiffres : le texte dicté reste naturel en français.
# La ponctuation dictée (« virgule »…) est produite APRÈS ce nettoyage, elle survit.
_AUTO_PUNCT_CHARS = '.,;:!?«»"“”…()[]{}<>/\\|@#$%^&*=~`_—–'
_AUTO_PUNCT_TABLE = {ord(ch): None for ch in _AUTO_PUNCT_CHARS}

# Séparateurs entre deux chiffres : décimales (« 3,5 » / « 3.5 »), heures
# (« 14:30 ») et dates (« 13/11/2026 ») — contenu dicté, pas de la ponctuation.
_NUMERIC_SEP_RE = re.compile(r"(?<=\d)[.,:/](?=\d)")

# Fins de phrase dictées après lesquelles une majuscule est justifiée.
_SENTENCE_END_CHARS = frozenset(".!?…")

# Caractères devant lesquels AUCUN espace de liaison n'est ajouté.
NO_SPACE_BEFORE = frozenset(".,;:!?)]}»…«'\"")

# Comparaison « règles de texte » : ponctuation et espaces ignorés, casse
# ignorée, mais ACCENTS SIGNIFICATIFS (« été » ≠ « et »).
_NON_WORD_RE = re.compile(r"[\W_]+")


def strip_auto_punctuation(text: str) -> str:
    """Retire toute la ponctuation/symbole auto-ajouté par le modèle de transcription.

    Les séparateurs entre chiffres (« 3,5 », « 14:30 », « 13/11/2026 ») sont
    protégés, les apostrophes et traits d'union conservés.
    """
    if not text:
        return text

    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x01{len(protected) - 1}\x02"

    out = _NUMERIC_SEP_RE.sub(_protect, text)
    out = out.translate(_AUTO_PUNCT_TABLE)
    if protected:
        out = re.sub(
            r"\x01(\d+)\x02",
            lambda m: protected[int(m.group(1))],
            out,
        )
    # Nettoyage des espaces résiduels (« mot.  Nouveau » → « mot Nouveau »)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.lstrip(" \t").rstrip(" \t")


def _prev_tail(previous_text: str | None) -> str:
    """Fin du texte précédent, hors espaces horizontaux de fin de ligne."""
    return (previous_text or "").rstrip(" \t")


def _starts_new_sentence(previous_text: str | None) -> bool:
    """Vrai au début du texte, après un saut de ligne ou après une fin de phrase dictée."""
    tail = _prev_tail(previous_text)
    if not tail:
        return True
    if tail.endswith("\n"):
        return True
    return tail[-1] in _SENTENCE_END_CHARS


def adapt_chunk_to_context(text: str, previous_text: str | None) -> str:
    """Harmonise un souffle dicté avec le texte déjà injecté.

    - Casse : majuscule seulement au début du texte et après « . ! ? … » ou un
      saut de ligne ; minuscule sinon (fin du « chaque souffle commence par une
      majuscule automatique »).
    - Espace de liaison : un seul espace manquant est ajouté (corrige le
      « mot.Nouveau » d'après un « point » dicté), inutile sinon.
    """
    if not text:
        return text
    prev = previous_text or ""
    tail = _prev_tail(prev)

    # 1. Casse du premier caractère alphabétique
    first = text[0]
    if first.isalpha():
        if _starts_new_sentence(prev):
            text = first.upper() + text[1:]
        else:
            text = first.lower() + text[1:]

    # 2. Espace de liaison avec le souffle précédent
    needs_space = (
        bool(tail)
        and not tail.endswith("\n")
        and not prev.endswith((" ", "\t"))
        and text[0] not in "\n "
        and text[0] not in NO_SPACE_BEFORE
    )
    if needs_space:
        text = " " + text
    return text


def _comparison_key(text: str) -> str:
    """Clé de comparaison d'une correction : ni ponctuation, ni espaces, ni casse ; accents conservés."""
    return _NON_WORD_RE.sub("", text or "").casefold()


def is_textual_only_correction(old_text: str, new_text: str) -> bool:
    """Vrai si la correction ne change que la forme du texte (ponctuation, casse,
    espaces, accents déjà présents) : règle de texte, pas une erreur de
    reconnaissance audio → aucun échantillon WAV/LoRA à enregistrer.

    Un changement de lettres (« bonjour » → « bonsoir ») reste une correction
    acoustique. Un texte vide n'est jamais classé « règle de texte ».
    """
    old_key = _comparison_key(old_text)
    new_key = _comparison_key(new_text)
    if not old_key or not new_key:
        return False
    return old_key == new_key
