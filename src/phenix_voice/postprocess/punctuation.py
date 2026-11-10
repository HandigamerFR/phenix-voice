"""Post-processeur de ponctuation hybride, règles déterministes A->B et routeur d'intentions (Phase 2+)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from phenix_voice.postprocess.rules import PhoneticRuleEngine, normalize_key


class VoiceIntentType(str, Enum):
    """Type d'intention détecté après transcription et application des règles A->B."""

    DICTATION = "dictation"
    WAKE = "wake"                    # « Phénix écoute »
    SLEEP = "sleep"                  # « Phénix repos »
    MUTE_MIC = "mute_mic"            # « Couper Phénix », « Éteindre Phénix »
    SCRATCH_LAST = "scratch"         # « Effacer ça », « Rayez ça »
    OUPS_NO_LEARN = "oups"           # « Annuler sans apprendre » (jette l'audio, ne pollue pas le profil)
    OPEN_CORRECTION = "correct"      # « Corriger ça », « Corriger [mot] »
    CHOOSE_ALT = "choose_alt"        # « Choisir un / deux / trois »
    SELECT_TARGET = "select_target"  # « Sélectionner [mot] »
    PRESS_ENTER = "press_enter"      # « Presser Entrée »
    SHOW_HELP = "show_help"          # « Que puis-je dire ? » (liste des commandes disponibles)
    APPLY_CORRECTION = "apply_corr"  # « Valider la correction » (applique le texte du champ de correction)
    ENTER_SPELLING = "enter_spell"   # « Mode épellation » (alphabet radio international)
    EXIT_SPELLING = "exit_spell"     # « Fin épellation » / « Mode dictée »


@dataclass
class ProcessedUtterance:
    """Résultat enrichi du post-traitement d'un souffle."""

    intent: VoiceIntentType
    text_to_inject: str = ""
    raw_text: str = ""
    mapped_text: str = ""
    choice_index: int = 0
    target_arg: str = ""


# Commandes dédiées Phénix Voice (sans conflit avec « Écoute / Au repos » de Dragon)
WAKE_COMMANDS: set[str] = {
    "phénix écoute",
    "phenix ecoute",
    "phoenix écoute",
    "fénix écoute",
    "félix écoute",
    "activer phénix",
}

SLEEP_COMMANDS: set[str] = {
    "phénix repos",
    "phenix repos",
    "phoenix repos",
    "phénix au repos",
    "phoenix au repos",
    "pause phénix",
}

MUTE_COMMANDS: set[str] = {
    "couper phénix",
    "couper phoenix",
    "coupez phénix",
    "éteindre phénix",
    "éteindre phoenix",
    "arrêter phénix",
    "couper le micro",
    "éteindre le micro",
}

SHOW_HELP_COMMANDS: set[str] = {
    "que puis-je dire",
    "qu'est-ce que je peux dire",
    "quest-ce que je peux dire",
    "quelles sont les commandes",
    "quelle sont les commandes",
    "liste des commandes",
    "aide commandes",
    "commandes disponibles",
    "aide vocale",
    "afficher l'aide",
    "afficher les commandes",
}

APPLY_CORRECTION_COMMANDS: set[str] = {
    "valider la correction",
    "appliquer la correction",
    "appliquer correction",
    "appliquer",
    "valider correction",
    "valider",
    "c'est corrigé",
    "cest corrigé",
    "c'est bon",
    "cest bon",
    "confirmer la correction",
}

SCRATCH_COMMANDS: set[str] = {
    "effacer ça",
    "efface ça",
    "rayez ça",
    "rayer ça",
    "annuler ça",
    "annule ça",
    "supprimer ça",
}

OUPS_COMMANDS: set[str] = {
    "annuler sans apprendre",
    "ne pas apprendre",
    "ne retiens pas",
    "ne rien apprendre",
    "sans apprendre",
    "corriger sans apprendre",
    "j'ai fourché",
    "j'ai bafouillé",
}

SPELLING_ENTER_COMMANDS: set[str] = {
    "mode épellation",
    "mode epellation",
    "mode épeler",
    "mode epeler",
    "épellation",
    "epellation",
    "alphabet radio",
}

SPELLING_EXIT_COMMANDS: set[str] = {
    "fin épellation",
    "fin epellation",
    "fin d'épellation",
    "fin d'epellation",
    "arrêter épellation",
    "arreter epellation",
    "stop épellation",
    "stop epellation",
    "mode dictée",
    "mode dictee",
    "fin de l'épellation",
    "fin de l epellation",
}

OPEN_CORRECTION_COMMANDS: set[str] = {
    "corriger ça",
    "corrigez ça",
    "corrige ça",
}

PRESS_ENTER_COMMANDS: set[str] = {
    "presser entrée",
    "pressez entrée",
    "pressé entrée",
    "pressé entrer",
    "appuyer sur entrée",
    "appuyez sur entrée",
    "touche entrée",
}

CHOOSE_MAP: dict[str, int] = {
    "choisir un": 1,
    "choisir 1": 1,
    "choix un": 1,
    "choix 1": 1,
    "numéro un": 1,
    "numéro 1": 1,
    "choisir deux": 2,
    "choisir 2": 2,
    "choisir de": 2,
    "choix deux": 2,
    "choix 2": 2,
    "numéro deux": 2,
    "numéro 2": 2,
    "choisir trois": 3,
    "choisir 3": 3,
    "choix trois": 3,
    "choix 3": 3,
    "numéro trois": 3,
    "numéro 3": 3,
}

# Remplacements de ponctuation dictée et équivalences phonétiques dysarthriques
SPOKEN_PUNCTUATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r",?\s*\b(?:point\s+à\s+la\s+ligne|pour\s+la\s+ligne|pour\s+un\s+aligné|pour\s+en\s+aligné|o[uù]\s+est\s+la\s+ligne)\b[.!?]*",
            re.IGNORECASE,
        ),
        ".\n",
    ),
    (re.compile(r",?\s*\bnouveaux?\s+paragraphes?\b[.!?]*", re.IGNORECASE), "\n\n"),
    (re.compile(r",?\s*\b(?:retour\s+)?à\s+la\s+ligne\b[.!?]*", re.IGNORECASE), "\n"),
    (
        re.compile(
            r"[,.?]?\s*\b(?:point|pour|pas)\s+(?:d['’]|l['’]|à['’]?)interrogation\b[.!?]*",
            re.IGNORECASE,
        ),
        " ?",
    ),
    (re.compile(r"[,.!]?\s*\bpoint\s+d['’]exclamation\b[.!?]*", re.IGNORECASE), " !"),
    (re.compile(r",?\s*\bpoints?\s+de\s+suspension\b[.!?]*", re.IGNORECASE), "..."),
    (re.compile(r",?\s*\bpoint[- ]virgule\b[.!?]*", re.IGNORECASE), " ;"),
    (re.compile(r",?\s*\bdeux[- ]points\b[.!?]*", re.IGNORECASE), " :"),
    (re.compile(r"\bouvr(?:ir|ez|ons)\s+les\s+guillemets\b[.!?]*", re.IGNORECASE), "« "),
    (re.compile(r"\bferm(?:er|ez|ons)\s+les\s+guillemets\b[.!?]*", re.IGNORECASE), " »"),
    (re.compile(r"\bouvr(?:ir|ez|ons)\s+la\s+parenthèse\b[.!?]*", re.IGNORECASE), "("),
    (re.compile(r"\bferm(?:er|ez|ons)\s+la\s+parenthèse\b[.!?]*", re.IGNORECASE), ")"),
    (re.compile(r",?\s*\bvirgule\b[,.]*", re.IGNORECASE), ","),
]

# Indicateurs de ponctuation/mise en forme explicitement dictée (en fin d'énoncé) : on ne retire
# pas la ponctuation finale dans ces cas, contrairement à la ponctuation auto-ajoutée par Whisper.
EXPLICIT_SPOKEN_PUNCT_ENDINGS: tuple[str, ...] = (
    "point à la ligne",
    "pour la ligne",
    "pour un aligné",
    "pour en aligné",
    "où est la ligne",
    "ou est la ligne",
    "à la ligne",
    "nouveau paragraphe",
    "nouveaux paragraphes",
    "nouveaux paragraphe",
    "point d'interrogation",
    "point d interrogation",
    "point interrogation",
    "pour l'interrogation",
    "pas d'interrogation",
    "point d'exclamation",
    "point exclamation",
    "points de suspension",
    "point de suspension",
    "point virgule",
    "point-virgule",
    "deux points",
    "deux-points",
    "virgule",
    "point",
)

NATO_ALPHABET: dict[str, str] = {
    "alpha": "a",
    "alfa": "a",
    "bravo": "b",
    "charlie": "c",
    "delta": "d",
    "echo": "e",
    "écho": "e",
    "foxtrot": "f",
    "fox trot": "f",
    "golf": "g",
    "hotel": "h",
    "hôtel": "h",
    "india": "i",
    "juliett": "j",
    "juliet": "j",
    "juliette": "j",
    "kilo": "k",
    "lima": "l",
    "mike": "m",
    "november": "n",
    "novembre": "n",
    "oscar": "o",
    "papa": "p",
    "quebec": "q",
    "québec": "q",
    "romeo": "r",
    "roméo": "r",
    "sierra": "s",
    "tango": "t",
    "uniform": "u",
    "uniforme": "u",
    "victor": "v",
    "whiskey": "w",
    "whisky": "w",
    "xray": "x",
    "x-ray": "x",
    "x ray": "x",
    "yankee": "y",
    "zulu": "z",
    "zoulou": "z",
}
NATO_SPACE_TOKENS: set[str] = {"espace", "space"}
NATO_EMPTY_TOKENS: set[str] = {"trait d'union", "tiret", "moins"}  # symboles simples éventuels (optionnel)


def _ends_with_explicit_spoken_punctuation(norm_text: str) -> bool:
    n = norm_text.strip()
    if not n:
        return False
    for ending in EXPLICIT_SPOKEN_PUNCT_ENDINGS:
        if n == ending or n.endswith(" " + ending) or n.endswith(ending):
            return True
    return False


def _strip_auto_terminal_punctuation(text: str) -> str:
    """Retire la ponctuation finale ajoutée automatiquement par le modèle (point/virgule)
    pour ne pas casser les phrases inachevées. Préserve les fins explicites comme « .\n », « \n\n » ou « ... »."""
    if not text:
        return text
    # Ne pas toucher aux fins de ligne/paragraphes gérées par les commandes de ponctuation dictée
    if text.endswith("\n"):
        return text
    # Préserver les points de suspension explicites
    if text.rstrip().endswith("..."):
        return text
    # Retirer uniquement le point ou la virgule terminaux auto-ajoutés (cas signalé : phrase/groupes de mots coupés)
    stripped = re.sub(r"[ \t]*[.,]+[ \t]*$", "", text)
    return stripped
def text_to_nato_spelling(raw_text: str) -> str:
    """Convertit une énonciation d'alphabet radio (Alpha Bravo Charlie) en lettres épelées."""
    norm = normalize_key(raw_text)
    if not norm:
        return ""
    # Gérer quelques tokens multi-mots avant découpage simple
    norm = norm.replace("trait d union", "trait-d-union").replace("x ray", "x-ray").replace("fox trot", "fox-trot")
    tokens = norm.split()
    out: list[str] = []
    for tok in tokens:
        t = tok.replace("’", "'").strip("-")
        t_compact = t.replace("-", " ")
        if t in NATO_ALPHABET:
            out.append(NATO_ALPHABET[t])
        elif t_compact in NATO_ALPHABET:
            out.append(NATO_ALPHABET[t_compact])
        elif t in NATO_SPACE_TOKENS:
            out.append(" ")
        elif t in NATO_EMPTY_TOKENS or t_compact in NATO_EMPTY_TOKENS:
            # symboles simples : tiret/moins
            if "tiret" in t or "moins" in t:
                out.append("-")
        elif len(t) == 1 and t.isalnum():
            out.append(t)
        # Les mots inconnus sont ignorés pour éviter d'injecter du texte dicté parasite en mode épellation
    return "".join(out)


class HybridPunctuationProcessor:
    """Applique les règles déterministes A->B, route les commandes Phase 2 et met en forme la ponctuation."""

    def __init__(
        self,
        rule_engine: PhoneticRuleEngine | None = None,
        enable_strict_dictionary: bool = False,
    ) -> None:
        self.rule_engine = rule_engine or PhoneticRuleEngine()
        self.enable_strict_dictionary = enable_strict_dictionary
        self._after_sentence_end: bool = True

    def reset_context(self) -> None:
        self._after_sentence_end = True

    def process(self, raw_text: str, is_sleeping: bool = False) -> ProcessedUtterance:
        if not raw_text or not raw_text.strip():
            return ProcessedUtterance(
                intent=VoiceIntentType.DICTATION,
                text_to_inject="",
                raw_text=raw_text,
            )

        # Le dictionnaire 100 % déterministe est désactivé par défaut (l'Arbitre de Plausibilité
        # gère la désambiguïsation contextuelle en amont). Il reste activable en option.
        mapped = (
            self.rule_engine.apply(raw_text)
            if self.enable_strict_dictionary
            else raw_text.strip()
        )
        norm = normalize_key(mapped)

        # 2. En mode veille vocale (« Phénix repos »), seules quelques commandes de contrôle restent actives
        if is_sleeping:
            if norm in WAKE_COMMANDS or any(norm.endswith(cmd) for cmd in WAKE_COMMANDS):
                return ProcessedUtterance(
                    intent=VoiceIntentType.WAKE, raw_text=raw_text, mapped_text=mapped
                )
            if norm in MUTE_COMMANDS:
                return ProcessedUtterance(
                    intent=VoiceIntentType.MUTE_MIC,
                    raw_text=raw_text,
                    mapped_text=mapped,
                )
            if norm in SHOW_HELP_COMMANDS:
                return ProcessedUtterance(
                    intent=VoiceIntentType.SHOW_HELP,
                    raw_text=raw_text,
                    mapped_text=mapped,
                )
            if norm in SPELLING_EXIT_COMMANDS:
                return ProcessedUtterance(
                    intent=VoiceIntentType.EXIT_SPELLING,
                    raw_text=raw_text,
                    mapped_text=mapped,
                )
            return ProcessedUtterance(
                intent=VoiceIntentType.DICTATION,
                text_to_inject="",
                raw_text=raw_text,
                mapped_text=mapped,
            )

        # 3. Commandes de contrôle du micro, aide et modes
        if norm in MUTE_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.MUTE_MIC, raw_text=raw_text, mapped_text=mapped
            )
        if norm in SLEEP_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.SLEEP, raw_text=raw_text, mapped_text=mapped
            )
        if norm in WAKE_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.WAKE, raw_text=raw_text, mapped_text=mapped
            )
        if norm in SHOW_HELP_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.SHOW_HELP, raw_text=raw_text, mapped_text=mapped
            )
        if norm in SPELLING_EXIT_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.EXIT_SPELLING, raw_text=raw_text, mapped_text=mapped
            )
        if norm in SPELLING_ENTER_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.ENTER_SPELLING, raw_text=raw_text, mapped_text=mapped
            )

        # 4. Commandes de correction, d'édition et de touche Entrée
        if norm in APPLY_CORRECTION_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.APPLY_CORRECTION,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if norm in PRESS_ENTER_COMMANDS:
            self._after_sentence_end = True
            return ProcessedUtterance(
                intent=VoiceIntentType.PRESS_ENTER,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if norm in OUPS_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.OUPS_NO_LEARN,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if norm in SCRATCH_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.SCRATCH_LAST,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if norm in OPEN_CORRECTION_COMMANDS:
            return ProcessedUtterance(
                intent=VoiceIntentType.OPEN_CORRECTION,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if norm in CHOOSE_MAP:
            return ProcessedUtterance(
                intent=VoiceIntentType.CHOOSE_ALT,
                raw_text=raw_text,
                mapped_text=mapped,
                choice_index=CHOOSE_MAP[norm],
            )

        # Commandes paramétrées : « Sélectionner [mot] » / « Corriger [mot] »
        m_sel = re.match(
            r"^(?:sélectionner|sélectionne|selectionner)\s+(.+)$", norm, re.IGNORECASE
        )
        if m_sel:
            return ProcessedUtterance(
                intent=VoiceIntentType.SELECT_TARGET,
                raw_text=raw_text,
                mapped_text=mapped,
                target_arg=m_sel.group(1).strip(),
            )

        m_cor = re.match(r"^(?:corriger|corrigez|corrige)\s+(.+)$", norm, re.IGNORECASE)
        if m_cor and m_cor.group(1).strip() != "ça":
            return ProcessedUtterance(
                intent=VoiceIntentType.OPEN_CORRECTION,
                raw_text=raw_text,
                mapped_text=mapped,
                target_arg=m_cor.group(1).strip(),
            )

        # 5. Mise en forme du texte dicté et ponctuation hybride
        explicit_spoken_punct = _ends_with_explicit_spoken_punctuation(norm)
        text = mapped.strip()
        for pattern, replacement in SPOKEN_PUNCTUATION_RULES:
            text = pattern.sub(replacement, text)

        # « point » isolé ou final explicite
        if re.search(r"\bpoint\b", norm, re.IGNORECASE) and explicit_spoken_punct:
            text = re.sub(r"\s+\bpoint\b[.!?]*$", ".", text, flags=re.IGNORECASE)
            if normalize_key(text) == "point":
                text = "."

        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r"\s+\.", ".", text)
        text = re.sub(r"\.\.+", lambda m: "..." if len(m.group(0)) >= 3 else ".", text)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Ponctuation automatique du modèle (Whisper) : ne pas forcer un point/virgule final
        # sur un groupe de mots inachevé. On conserve la ponctuation uniquement si elle a été dictée explicitement.
        if not explicit_spoken_punct:
            text = _strip_auto_terminal_punctuation(text)

        if not self._after_sentence_end and text and not text.startswith(("\n", ".", ",", ")", "!", "?", ";", ":")):
            text = " " + text
        elif self._after_sentence_end and text and text[0].isalpha():
            text = text[0].upper() + text[1:]

        stripped_end = text.rstrip(" ")
        if stripped_end.endswith(("\n", ".", "!", "?", "...")):
            self._after_sentence_end = True
        else:
            # Laisser la suite dans la même phrase si l'utilisateur n'a pas terminé explicitement
            self._after_sentence_end = False

        return ProcessedUtterance(
            intent=VoiceIntentType.DICTATION,
            text_to_inject=text,
            raw_text=raw_text,
            mapped_text=mapped,
        )
