"""Moteur de règles déterministes prioritaires (« Si tu entends A, écris/exécute B »).

Alimenté automatiquement par :
1. Le Studio d'Étalonnage (lorsque l'utilisateur valide une prononciation habituelle et que
   Whisper a transcrit une variante phonétique A pour la cible B).
2. L'action « Corriger & Apprendre » de la barre de correction (Phase 2).
3. L'ajout manuel de règles par l'utilisateur.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata


def normalize_key(text: str) -> str:
    """Normalise une chaîne pour la recherche d'équivalence phonétique."""
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[.!?,;:«»\"'…]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def collapse_repeated_utterance(text: str) -> str:
    """Replie un énoncé doublé/triplé en sa forme simple (en mémoire uniquement).

    La voix dysarthrique répète parfois la commande entière : « Mode épellation,
    mode épellation. », « Corriger ça, Corriger ça. » — l'appariement exact des
    commandes cassait, l'énoncé partait en dictée. On détecte une séquence de
    mots strictement répétée (comparaison aussi sans accents) et on ne garde
    qu'une unité, **uniquement pour le matching des commandes** : le texte dicté
    (`mapped`) n'est jamais modifié par ce repli.
    """
    tokens = text.split()
    n = len(tokens)
    if n < 2:
        return text

    def _fold(token: str) -> str:
        decomposed = unicodedata.normalize("NFD", token)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    tokens_folded = [_fold(t) for t in tokens]
    for p in range(1, n // 2 + 1):
        if n % p:
            continue
        unit = tokens_folded[:p]
        if all(tokens_folded[i] == unit[i % p] for i in range(n)):
            return " ".join(tokens[:p])
    return text


def command_keys(text: str) -> list[str]:
    """Formes de comparaison d'une commande — **uniquement en mémoire**.

    La forme naturelle (accents et apostrophes **conservés**) fait foi : une table
    écrite « c'était une commande » reconnaît « C'était une commande » tel quel.
    Les variantes repliées (sans accents, apostrophes supprimées ou détachées) ne
    servent que de filet pour les sorties de Whisper dégradées (« c'etait »,
    « c etait »). Elles ne sont jamais affichées ni enregistrées sur disque.

    Principe de design : le code reste en français naturel ; seule cette clé de
    comparaison tolère les écarts de transcription.
    """
    keys: list[str] = []

    def _add(candidate: str) -> None:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)

    # 1) Forme naturelle : casse réduite, apostrophes typographiques redressées,
    #    ponctuation et tirets réduits à des espaces (accents et apostrophes gardés).
    lowered = text.strip().lower().replace("’", "'")
    natural = re.sub(r"[.!?,;:«»\"…–—-]+", " ", lowered)
    _add(natural)
    if not natural:
        return keys

    # 2) Variantes repliées (filet anti-écarts STT) : accents retirés, puis
    #    apostrophes conservées / supprimées / détachées.
    decomposed = unicodedata.normalize("NFD", natural)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    _add(no_accents)
    _add(no_accents.replace("'", ""))
    _add(no_accents.replace("'", " "))
    return keys


# Équivalences initiales déjà observées dans les journaux réels de l'utilisateur
DEFAULT_LEARNED_COMMAND_ALIASES: dict[str, str] = {
    # Effacer ça
    "il faisait ça": "Effacer ça",
    "f faisait ça": "Effacer ça",
    "il fait ça": "Effacer ça",
    "il fait aussi ça": "Effacer ça",
    "il faut aussi ça": "Effacer ça",
    "il fait ses armes": "Effacer ça",
    "effacier ça": "Effacer ça",
    "etacier ça": "Effacer ça",
    "effacé ça": "Effacer ça",
    "effacez ça": "Effacer ça",
    "effaz ça": "Effacer ça",
    # Presser Entrée
    "pressé entrer": "Presser Entrée",
    "pressée entrer": "Presser Entrée",
    "pressé entrée": "Presser Entrée",
    "presser entrer": "Presser Entrée",
    "précis en train": "Presser Entrée",
    "précise en train": "Presser Entrée",
    # Ponctuations isolées fréquentes
    "virgine": "virgule",
    "vgine": "virgule",
    "où est la ligne": "point à la ligne",
    "ou est la ligne": "point à la ligne",
    "pour la ligne": "point à la ligne",
    "pour un aligné": "point à la ligne",
    "pour en aligné": "point à la ligne",
}


class PhoneticRuleEngine:
    """Gère et applique les règles déterministes A -> B propres à la diction de l'utilisateur."""

    def __init__(
        self, rules_path: str | Path = "user_data/learned_rules.json"
    ) -> None:
        self.rules_path = Path(rules_path)
        self.utterance_rules: dict[str, str] = dict(DEFAULT_LEARNED_COMMAND_ALIASES)
        self.word_rules: dict[str, str] = {
            "adoptée": "adaptée",
        }
        self.reload()

    def reload(self) -> None:
        if not self.rules_path.exists():
            self.save()
            return
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            for k, v in data.get("utterance_rules", {}).items():
                self.utterance_rules[normalize_key(k)] = v
            for k, v in data.get("word_rules", {}).items():
                self.word_rules[k.lower().strip()] = v
        except Exception:
            pass

    def save(self) -> None:
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "utterance_rules": self.utterance_rules,
            "word_rules": self.word_rules,
        }
        self.rules_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def learn_utterance_mapping(self, heard_text: str, target_text: str) -> bool:
        """Enregistre la règle : « Si Whisper entend `heard_text`, remplacer par `target_text` »."""
        norm_heard = normalize_key(heard_text)
        norm_target = normalize_key(target_text)
        if not norm_heard or not norm_target or norm_heard == norm_target:
            return False
        # Ne pas écraser un mot très court générique d'une seule lettre
        if len(norm_heard) < 2:
            return False
        self.utterance_rules[norm_heard] = target_text.strip()
        self.save()
        return True

    def learn_word_mapping(self, heard_word: str, target_word: str) -> bool:
        """Enregistre une règle de remplacement de mot ou d'expression à l'intérieur d'une phrase."""
        hw = heard_word.strip().lower()
        tw = target_word.strip()
        if not hw or not tw or hw == tw.lower():
            return False
        self.word_rules[hw] = tw
        self.save()
        return True

    def apply(self, raw_text: str) -> str:
        """Applique en priorité les règles d'énoncé complet puis les règles de mots/expressions."""
        if not raw_text or not raw_text.strip():
            return raw_text

        norm = normalize_key(raw_text)
        if norm in self.utterance_rules:
            return self.utterance_rules[norm]

        # Application des règles de mots/expressions dans le texte
        result = raw_text
        for bad_expr, good_expr in self.word_rules.items():
            pattern = re.compile(r"\b" + re.escape(bad_expr) + r"\b", re.IGNORECASE)
            result = pattern.sub(good_expr, result)
        return result
