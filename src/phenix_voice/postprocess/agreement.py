"""Variantes d'accord grammatical (genre/nombre) pour la boîte « Corriger ça ».

Le texte dicté est écrit CORRECTEMENT par défaut (le système essaie d'écrire
juste) ; la boîte de correction propose en PLUS toutes les variantes d'accord
RÉELLES du texte — même si elles sont grammaticalement fautives au contexte
près (« les conversations sont terminé/terminée/terminés/terminées »).

Validation : lexique **Lexique383** (formes fléchies du français, licence
CC BY-SA 4.0, voir ``resources/README_Lexique383.txt``). Le fichier
``resources/lexique_accords.tsv`` est compilé par ``tools/build_lexicon_accords.py``
: une ligne = une famille de formes réelles partageant lemme + tronc d'accord +
statut accentué du suffixe. Un mot non réel (« cafée ») n'y figure tout
simplement pas → jamais proposé.

Stratégie (décision utilisateur 14/11) : TOUS les mots inflectables de la
phrase, UNE seule substitution par proposition, traités depuis la FIN (l'accord
se joue souvent en fin de phrase), 9 propositions maximum, casse conservée.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_LEXICON_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "lexique_accords.tsv"
)

# Mot français (accents inclus), éventuellement apostrophé (« d'accord »).
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿŒœÆæ]+(?:['’][A-Za-zÀ-ÿŒœÆæ]+)*")


@lru_cache(maxsize=1)
def load_agreement_lexicon() -> dict[str, list[str]]:
    """forme (minuscules) → variantes d'accord réelles, classées par fréquence."""
    variants: dict[str, list[str]] = {}
    if not _LEXICON_PATH.exists():
        return variants
    with open(_LEXICON_PATH, encoding="utf-8") as fh:
        for line in fh:
            forms = line.rstrip("\n").split("\t")
            if len(forms) < 2:
                continue
            for i, form in enumerate(forms):
                others = forms[:i] + forms[i + 1 :]
                bucket = variants.setdefault(form, [])
                bucket.extend(o for o in others if o not in bucket)
    return variants


def _match_case(variant: str, model: str) -> str:
    """Repose la casse du modèle sur la variante (« Terminées » → « Terminé »)."""
    if model.isupper():
        return variant.upper()
    if model[:1].isupper():
        return variant[:1].upper() + variant[1:]
    return variant


def agreement_variants(text: str, max_variants: int = 9) -> list[str]:
    """Variantes d'accord du texte dicté (une substitution par proposition).

    Les mots sont traités depuis la FIN ; chaque proposition remplace UN mot du
    texte par une forme réelle de la même famille (lemme + tronc d'accord).
    Le texte d'origine n'est jamais retourné (il reste le défaut écrit).
    """
    lexicon = load_agreement_lexicon()
    if not lexicon or not text or not text.strip() or max_variants <= 0:
        return []

    out: list[str] = []
    seen: set[str] = {text.casefold()}
    for match in reversed(list(_WORD_RE.finditer(text))):
        token = match.group(0)
        # « d'accord » → recherche sur « accord », préfixe « d' » préservé.
        cut = max(token.rfind("'"), token.rfind("’"))
        prefix, core = (token[: cut + 1], token[cut + 1 :]) if cut >= 0 else ("", token)
        candidates = [
            v
            for v in lexicon.get(core.lower(), ())
            if v != core.lower() and v not in seen
        ]
        for variant in candidates:
            word = prefix + _match_case(variant, core)
            candidate_text = text[: match.start()] + word + text[match.end() :]
            key = candidate_text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate_text)
            if len(out) >= max_variants:
                return out
    return out


def merge_agreement_alternatives(
    text: str, alternatives: list[str], max_total: int = 9
) -> list[str]:
    """Variantes d'accord + alternatives STT, dédoublonnées, plafonnées.

    Les variantes d'accord passent en TÊTE (c'est la demande explicite de la
    boîte « Corriger ça »), puis viennent les hypothèses acoustiques du STT.
    """
    merged: list[str] = []
    seen: set[str] = set()
    chain = agreement_variants(text, max_variants=max_total) + list(alternatives)
    for alt in chain:
        key = (alt or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(alt)
        if len(merged) >= max_total:
            break
    return merged
