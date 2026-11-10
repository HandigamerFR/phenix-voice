"""Post-processeur de ponctuation hybride et routeur des commandes vocales de base."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class VoiceIntentType(str, Enum):
    """Type d'intention détecté après transcription d'un souffle."""

    DICTATION = "dictation"
    SLEEP = "sleep"          # "Au repos", "Mise en veille"
    WAKE = "wake"            # "Écoute", "Réveille-toi"
    SCRATCH_LAST = "scratch" # "Effacer ça", "Rayez ça", "Oups"
    NEW_LINE = "newline"     # "À la ligne" seul


@dataclass
class ProcessedUtterance:
    """Résultat du post-traitement d'un segment transcrit."""

    intent: VoiceIntentType
    text_to_inject: str = ""
    raw_text: str = ""


# Commandes vocales globales de contrôle du micro et d'annulation immédiate
SLEEP_COMMANDS: set[str] = {
    "au repos",
    "repos",
    "mise en veille",
    "mets-toi en veille",
    "arrête d'écouter",
    "arrete d'ecouter",
    "stop écoute",
}

WAKE_COMMANDS: set[str] = {
    "écoute",
    "ecoute",
    "réveille-toi",
    "reveille-toi",
    "reprends l'écoute",
    "reprendre l'écoute",
    "micro actif",
}

SCRATCH_COMMANDS: set[str] = {
    "effacer ça",
    "efface ça",
    "rayez ça",
    "rayer ça",
    "annuler ça",
    "annule ça",
    "oups",
}

# Remplacements de ponctuation dictée (ordonnés du plus spécifique au plus général)
SPOKEN_PUNCTUATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpoint\s+à\s+la\s+ligne\b\.?", re.IGNORECASE), ".\n"),
    (re.compile(r"\bnouveau\s+paragraphe\b\.?", re.IGNORECASE), "\n\n"),
    (re.compile(r"\bà\s+la\s+ligne\b\.?", re.IGNORECASE), "\n"),
    (re.compile(r"\bretour\s+à\s+la\s+ligne\b\.?", re.IGNORECASE), "\n"),
    (re.compile(r"\bpoint\s+d['’]interrogation\b\.?", re.IGNORECASE), " ?"),
    (re.compile(r"\bpoint\s+d['’]exclamation\b\.?", re.IGNORECASE), " !"),
    (re.compile(r"\bpoints?\s+de\s+suspension\b\.?", re.IGNORECASE), "..."),
    (re.compile(r"\bpoint[- ]virgule\b\.?", re.IGNORECASE), " ;"),
    (re.compile(r"\bdeux[- ]points\b\.?", re.IGNORECASE), " :"),
    (re.compile(r"\bouvr(?:ir|ez|ons)\s+les\s+guillemets\b\.?", re.IGNORECASE), "« "),
    (re.compile(r"\bferm(?:er|ez|ons)\s+les\s+guillemets\b\.?", re.IGNORECASE), " »"),
    (re.compile(r"\bouvr(?:ir|ez|ons)\s+la\s+parenthèse\b\.?", re.IGNORECASE), "("),
    (re.compile(r"\bferm(?:er|ez|ons)\s+la\s+parenthèse\b\.?", re.IGNORECASE), ")"),
    (re.compile(r"\bvirgule\b[,.]?", re.IGNORECASE), ","),
]


def _normalize_command(text: str) -> str:
    """Nettoie une chaîne pour la comparer aux commandes système courtes."""
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[.!?,;:«»\"'…]+$", "", cleaned).strip()
    return cleaned


class HybridPunctuationProcessor:
    """Transforme la sortie brute de Whisper en texte prêt à injecter ou en commande système."""

    def __init__(self) -> None:
        self._after_sentence_end: bool = True

    def reset_context(self) -> None:
        """Réinitialise l'état de début de phrase (ex: après un clic souris ou retour à la ligne)."""
        self._after_sentence_end = True

    def process(self, raw_text: str, is_sleeping: bool = False) -> ProcessedUtterance:
        """Analyse le texte transcrit, détecte les commandes ou applique la ponctuation hybride."""
        if not raw_text or not raw_text.strip():
            return ProcessedUtterance(intent=VoiceIntentType.DICTATION, text_to_inject="", raw_text=raw_text)

        norm = _normalize_command(raw_text)

        # 1. En mode veille ("Au repos"), seule la commande d'éveil est acceptée
        if is_sleeping:
            if norm in WAKE_COMMANDS or any(norm.endswith(cmd) for cmd in WAKE_COMMANDS):
                return ProcessedUtterance(intent=VoiceIntentType.WAKE, raw_text=raw_text)
            return ProcessedUtterance(intent=VoiceIntentType.DICTATION, text_to_inject="", raw_text=raw_text)

        # 2. Commandes système prioritaires en mode actif
        if norm in SLEEP_COMMANDS:
            return ProcessedUtterance(intent=VoiceIntentType.SLEEP, raw_text=raw_text)
        if norm in WAKE_COMMANDS:
            return ProcessedUtterance(intent=VoiceIntentType.WAKE, raw_text=raw_text)
        if norm in SCRATCH_COMMANDS:
            return ProcessedUtterance(intent=VoiceIntentType.SCRATCH_LAST, raw_text=raw_text)

        # 3. Application des règles de ponctuation dictée
        text = raw_text.strip()
        for pattern, replacement in SPOKEN_PUNCTUATION_RULES:
            text = pattern.sub(replacement, text)

        # Cas particulier du mot "point" dicté en fin de souffle ("bonjour point" -> "bonjour.")
        text = re.sub(r"\s+\bpoint\b[.!?]*$", ".", text, flags=re.IGNORECASE)
        if _normalize_command(text) == "point":
            text = "."

        # Nettoyage des espaces autour des signes de ponctuation
        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r"\s+\.", ".", text)
        text = re.sub(r"\.\.+", lambda m: "..." if len(m.group(0)) >= 3 else ".", text)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Gestion de l'espacement inter-souffles : ajouter un espace devant si on poursuit une ligne
        if not self._after_sentence_end and text and not text.startswith(("\n", ".", ",", ")")):
            text = " " + text
        elif self._after_sentence_end and text and text[0].isalpha():
            text = text[0].upper() + text[1:]
            if not text.startswith("\n"):
                # Ajouter un espace après le point de la phrase précédente si ce n'était pas un saut de ligne
                pass

        # Mise à jour de l'état de fin de phrase pour le souffle suivant
        stripped_end = text.rstrip(" ")
        if stripped_end.endswith("\n"):
            self._after_sentence_end = True
        elif stripped_end.endswith((".", "!", "?", "…")):
            self._after_sentence_end = False  # Le souffle suivant ajoutera une espace devant lui
        else:
            self._after_sentence_end = False

        return ProcessedUtterance(
            intent=VoiceIntentType.DICTATION,
            text_to_inject=text,
            raw_text=raw_text,
        )
