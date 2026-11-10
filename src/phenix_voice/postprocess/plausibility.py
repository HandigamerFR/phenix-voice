"""Arbitre de Plausibilité Contextuelle & Acoustique — Phénix Voice.

Au lieu d'appliquer aveuglément un dictionnaire « A -> B » à 100 % (qui risquerait de
remplacer un mot voulu comme « loi adoptée » par « loi adaptée »), cet arbitre combine :
1. La certitude acoustique de Whisper (`confidence`) et ses hypothèses alternatives (`alternatives`).
2. La plausibilité linguistique et contextuelle en français (détection des bégaiements de
   décodage, mots tronqués, cohérence sémantique avec les mots voisins).
3. Les confusions phonétiques connues de l'utilisateur (issues de l'étalonnage et des
   corrections), qui ne sont activées QUE lorsque l'énoncé brut est peu plausible dans son
   contexte ou correspond à une commande isolée.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


def _normalize(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[.!?,;:«»\"'…]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Contextes sémantiques permettant de départager des paires phonétiques proches (ex: adoptée vs adaptée)
CONTEXTUAL_PAIR_PREFERENCES: list[tuple[str, str, set[str], set[str]]] = [
    (
        "adoptée",
        "adaptée",
        # Contextes où « adoptée » est pleinement plausible et doit être préservé :
        {"loi", "mesure", "motion", "résolution", "décision", "enfant", "stratégie", "assemblée", "parlement"},
        # Contextes où « adaptée » est beaucoup plus plausible :
        {"vocale", "reconnaissance", "interface", "ergonomie", "solution", "version", "personne", "situation", "commande", "dictée"},
    ),
    (
        "adopté",
        "adapté",
        {"projet", "texte", "budget", "amendement", "enfant", "décret"},
        {"vocal", "logiciel", "modèle", "outil", "système", "clavier", "contrôle", "handicap"},
    ),
]

# Expressions qui, en français courant, ont une très faible plausibilité sémantique en fin de phrase
# et résultent d'une confusion phonétique avec une commande de ponctuation dictée :
IMPLAUSIBLE_TAIL_PHONETIC_PUNCTUATION: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r",?\s*\b(?:pour\s+la\s+ligne|pour\s+un\s+aligné|pour\s+en\s+aligné|o[uù]\s+est\s+la\s+ligne)\b[.!?]*$",
            re.IGNORECASE,
        ),
        " point à la ligne",
    ),
    (
        re.compile(
            r"[,.?]?\s*\b(?:pour\s+l['’]interrogation|pas\s+d['’]interrogation|point\s+à['’]?interrogation)\b[.!?]*$",
            re.IGNORECASE,
        ),
        " point d'interrogation",
    ),
]


@dataclass
class ArbitratedResult:
    """Résultat après arbitrage de plausibilité entre les hypothèses acoustiques et le contexte."""

    best_text: str
    ranked_alternatives: list[str]
    plausibility_score: float
    was_adapted: bool = False
    adaptation_reason: str = ""


class PlausibilityArbitrator:
    """Évalue la plausibilité linguistique et contextuelle de ce que Whisper entend."""

    def __init__(
        self,
        rules_path: str | Path = "user_data/learned_rules.json",
        enable_strict_dictionary: bool = False,
    ) -> None:
        self.rules_path = Path(rules_path)
        # Par défaut False : pas de remplacement aveugle à 100 % sur le texte libre
        self.enable_strict_dictionary = enable_strict_dictionary
        self.command_confusions: dict[str, str] = {}
        self.word_confusions: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        if not self.rules_path.exists():
            return
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            for k, v in data.get("utterance_rules", {}).items():
                self.command_confusions[_normalize(k)] = v
            for k, v in data.get("word_rules", {}).items():
                self.word_confusions[k.lower().strip()] = v
        except Exception:
            pass

    def score_french_plausibility(self, text: str) -> float:
        """Attribue un score de plausibilité linguistique dans [0.0, 1.0] à une hypothèse."""
        if not text or not text.strip():
            return 0.0

        score = 0.85
        cleaned = text.strip()
        words = re.findall(r"[a-zA-ZÀ-ÿœŒæÆ']+", cleaned.lower())
        if not words:
            return 0.1

        # 1. Pénaliser les bégaiements de décodage Whisper (ex: "est est-ce", "point à la ligne, point à la ligne")
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and words[i] not in {"nous", "vous"}:
                score -= 0.25

        # Répétition de demi-phrase (ex: "Point à la ligne, point à la ligne.")
        half = len(words) // 2
        if half >= 2 and words[:half] == words[half : 2 * half]:
            score -= 0.30

        # 2. Pénaliser les tokens manifestement tronqués ou pseudo-mots (ex: "cper", "etacier", "oopsups", "phoenix,po")
        implausible_tokens = {
            "cper",
            "etacier",
            "oopsups",
            "hoppo",
            "hopo",
            "scama",
            "veering",
            "virering",
            "sooisir",
            "vgine",
        }
        for w in words:
            if w in implausible_tokens:
                score -= 0.35
            # Mot d'une seule consonne isolée non française (hors y, a, à, ô, c', l', d', j', m', n', s', t', qu')
            if len(w) == 1 and w not in {"a", "à", "y", "ô", "u"}:
                score -= 0.20

        # 3. Pénaliser les tournures agrammaticales connues issues de confusions phonétiques
        lower_clean = cleaned.lower()
        if "pour un aligné" in lower_clean or "pour en aligné" in lower_clean:
            score -= 0.35
        if "une commande dragonne" in lower_clean or "comme un dragonne" in lower_clean:
            score -= 0.30

        return float(max(0.05, min(1.0, score)))

    def arbitrate(
        self,
        raw_text: str,
        alternatives: list[str],
        acoustic_confidence: float,
        audio_duration_s: float,
        recent_context_text: str = "",
        acoustic_fp_match: tuple[str, float] | None = None,
    ) -> ArbitratedResult:
        """Choisit la meilleure interprétation en combinant score acoustique, plausibilité
        linguistique et contexte, sans jamais appliquer aveuglément un remplacement hors contexte.
        """
        if not raw_text or not raw_text.strip():
            return ArbitratedResult(
                best_text="", ranked_alternatives=[], plausibility_score=0.0
            )

        candidates = [raw_text.strip()] + [
            a.strip() for a in alternatives if a.strip() and a.strip() != raw_text.strip()
        ]

        # 1. Cas d'un énoncé court isolé (potentielle commande vocale ou ponctuation isolée <= 2,6s)
        norm_raw = _normalize(raw_text)
        word_count = len(norm_raw.split())
        is_short_isolated = audio_duration_s <= 2.7 and word_count <= 6

        if is_short_isolated:
            # Si l'énoncé court correspond à une confusion phonétique de commande calibrée
            # ET que soit la confiance acoustique n'est pas maximale (< 0.88), soit sa plausibilité
            # comme phrase autonome est faible (ex: "Phoenix Hoppo", "Précis en train", "Choisir de")
            if norm_raw in self.command_confusions:
                target_cmd = self.command_confusions[norm_raw]
                raw_plaus = self.score_french_plausibility(raw_text)
                if acoustic_confidence < 0.88 or raw_plaus < 0.75:
                    return ArbitratedResult(
                        best_text=target_cmd,
                        ranked_alternatives=candidates[:3],
                        plausibility_score=0.95,
                        was_adapted=True,
                        adaptation_reason=f"Commande isolée plausible ({raw_text!r} -> {target_cmd!r})",
                    )

            # Vérifier aussi si la 1re alternative de Whisper correspond exactement à une commande calibrée
            for alt in candidates[1:]:
                norm_alt = _normalize(alt)
                if norm_alt in self.command_confusions and acoustic_confidence < 0.75:
                    target_cmd = self.command_confusions[norm_alt]
                    return ArbitratedResult(
                        best_text=target_cmd,
                        ranked_alternatives=candidates[:3],
                        plausibility_score=0.92,
                        was_adapted=True,
                        adaptation_reason=f"Alternative commande plausible ({alt!r} -> {target_cmd!r})",
                    )

            # Court-circuit d'empreinte acoustique directe uniquement si Whisper est très incertain (< 0.45)
            if acoustic_fp_match is not None and acoustic_confidence < 0.45:
                return ArbitratedResult(
                    best_text=acoustic_fp_match[0],
                    ranked_alternatives=candidates[:3],
                    plausibility_score=0.90,
                    was_adapted=True,
                    adaptation_reason=f"Empreinte acoustique DTW ({acoustic_fp_match[0]!r})",
                )

        # 2. Re-classement des hypothèses de Whisper par score combiné (Acoustique + Plausibilité française)
        scored_candidates: list[tuple[float, str, float]] = []
        for idx, cand in enumerate(candidates):
            plaus = self.score_french_plausibility(cand)
            # Pénalité de rang légère pour les alternatives secondaires de Whisper
            acoustic_prior = acoustic_confidence if idx == 0 else max(0.3, acoustic_confidence - 0.08 * idx)
            combined = 0.55 * acoustic_prior + 0.45 * plaus
            scored_candidates.append((combined, cand, plaus))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_combined, chosen_text, chosen_plaus = scored_candidates[0]
        was_adapted = chosen_text != raw_text.strip()
        reason = "Alternative Whisper plus plausible" if was_adapted else ""

        # 3. Résolution contextuelle des paires phonétiques ambiguës (ex: adoptée vs adaptée)
        context_words = set(
            re.findall(
                r"[a-zA-ZÀ-ÿœŒæÆ']+",
                (recent_context_text + " " + chosen_text).lower(),
            )
        )
        for heard_w, target_w, keep_ctx, replace_ctx in CONTEXTUAL_PAIR_PREFERENCES:
            if re.search(r"\b" + re.escape(heard_w) + r"\b", chosen_text, re.IGNORECASE):
                has_keep_ctx = bool(context_words & keep_ctx)
                has_replace_ctx = bool(context_words & replace_ctx)
                if has_replace_ctx and not has_keep_ctx:
                    chosen_text = re.sub(
                        r"\b" + re.escape(heard_w) + r"\b",
                        target_w,
                        chosen_text,
                        flags=re.IGNORECASE,
                    )
                    was_adapted = True
                    reason = f"Plausibilité contextuelle ({heard_w} -> {target_w})"
                elif not has_keep_ctx and self.enable_strict_dictionary:
                    chosen_text = re.sub(
                        r"\b" + re.escape(heard_w) + r"\b",
                        target_w,
                        chosen_text,
                        flags=re.IGNORECASE,
                    )
                    was_adapted = True

        # 4. Correction des queues de phrases phonétiquement invraisemblables (ex: "... pour un aligné.")
        for pattern, replacement in IMPLAUSIBLE_TAIL_PHONETIC_PUNCTUATION:
            if pattern.search(chosen_text):
                chosen_text = pattern.sub(replacement, chosen_text)
                was_adapted = True
                reason = "Correction de queue phonétique invraisemblable"

        # 5. Générer la liste des alternatives pertinentes à proposer dans la barre « Corriger ça »
        final_alts: list[str] = []
        for _, cand, _ in scored_candidates:
            if cand.lower() != chosen_text.lower() and cand not in final_alts:
                final_alts.append(cand)

        # Ajouter aussi la variante inverse si une paire contextuelle est présente (pour que l'utilisateur
        # puisse toujours choisir l'autre mot en 1 clic dans « Corriger ça » !)
        for heard_w, target_w, _, _ in CONTEXTUAL_PAIR_PREFERENCES:
            if re.search(r"\b" + re.escape(target_w) + r"\b", chosen_text, re.IGNORECASE):
                alt_var = re.sub(
                    r"\b" + re.escape(target_w) + r"\b",
                    heard_w,
                    chosen_text,
                    flags=re.IGNORECASE,
                )
                if alt_var not in final_alts:
                    final_alts.insert(0, alt_var)
            elif re.search(r"\b" + re.escape(heard_w) + r"\b", chosen_text, re.IGNORECASE):
                alt_var = re.sub(
                    r"\b" + re.escape(heard_w) + r"\b",
                    target_w,
                    chosen_text,
                    flags=re.IGNORECASE,
                )
                if alt_var not in final_alts:
                    final_alts.insert(0, alt_var)

        return ArbitratedResult(
            best_text=chosen_text,
            ranked_alternatives=final_alts[:4],
            plausibility_score=chosen_plaus,
            was_adapted=was_adapted,
            adaptation_reason=reason,
        )
