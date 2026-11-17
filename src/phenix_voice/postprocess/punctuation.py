"""Post-processeur de ponctuation hybride, règles déterministes A->B et routeur d'intentions (Phase 2+)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Iterable, Mapping, TypeVar

from phenix_voice.postprocess.coherence import (
    adapt_chunk_to_context,
    strip_auto_punctuation,
)
from phenix_voice.postprocess.rules import (
    PhoneticRuleEngine,
    collapse_repeated_utterance,
    command_keys,
    normalize_key,
)
from phenix_voice.postprocess.symbols import (
    SpokenFormStore,
    _Substitution,
    apply_symbol_forms,
    spelling_symbol,
)

_T = TypeVar("_T")


class VoiceIntentType(str, Enum):
    """Type d'intention détecté après transcription et application des règles A->B."""

    DICTATION = "dictation"
    WAKE = "wake"                    # « Phénix écoute »
    SLEEP = "sleep"                  # « Phénix repos »
    MUTE_MIC = "mute_mic"            # « Couper Phénix », « Éteindre Phénix »
    SCRATCH_LAST = "scratch"         # « Effacer ça », « Rayez ça »
    OUPS_NO_LEARN = "oups"           # « Annuler sans apprendre » (jette l'audio, ne pollue pas le profil)
    OPEN_CORRECTION = "correct"      # « Corriger ça », « Corriger [mot] »
    OPEN_STUDIO = "open_studio"      # « Ouvrir le studio » (étalonnage / corpus)
    CHOOSE_ALT = "choose_alt"        # « Choisir un / deux / trois »
    SELECT_TARGET = "select_target"  # « Sélectionner [mot] »
    PRESS_ENTER = "press_enter"      # « Presser Entrée »
    SHOW_HELP = "show_help"          # « Que puis-je dire ? » (liste des commandes disponibles)
    APPLY_CORRECTION = "apply_corr"  # « Valider la correction » (applique le texte du champ de correction)
    ENTER_SPELLING = "enter_spell"   # « Mode épellation » (alphabet radio international)
    EXIT_SPELLING = "exit_spell"     # « Fin épellation » / « Mode dictée »
    REVISE_COMMAND = "revise_cmd"    # « C'était une commande » (annule le texte écrit à tort)


@dataclass
class ProcessedUtterance:
    """Résultat enrichi du post-traitement d'un souffle."""

    intent: VoiceIntentType
    text_to_inject: str = ""
    raw_text: str = ""
    mapped_text: str = ""
    choice_index: int = 0
    target_arg: str = ""
    # Formes orales de symboles ambiguës (« euro » → « € ») : popup de choix façon Dragon
    symbol_form: str = ""  # forme dictée (titre de la popup)
    symbol_char: str = ""  # symbole inséré (libellé « choix un »)
    symbol_choices: list[str] | None = None  # alternatives complètes [symbole, mot dicté]


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
    "phénix, repos",
    "phénix, au repos",
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
    "passer en mode dictée",
    "passer en mode dictee",
    "retour en mode dictée",
    "retour en mode dictee",
    "fin de l'épellation",
    "fin de l epellation",
}

OPEN_CORRECTION_COMMANDS: set[str] = {
    "corriger ça",
    "corrigez ça",
    "corrige ça",
}

OPEN_STUDIO_COMMANDS: set[str] = {
    "ouvrir le studio",
    "ouvre le studio",
    "ouvrir studio",
    "studio étalonnage",
    "studio d'étalonnage",
    "ouvrir le studio d'étalonnage",
    "ouvrir l'étalonnage",
}

COMMAND_RECALIBRATION_COMMANDS: dict[str, str] = {
    "c'était une commande": "corriger ça",
    "cetait une commande": "corriger ça",
    "c'était la commande": "corriger ça",
    "cetait la commande": "corriger ça",
    "c'était un ordre": "corriger ça",
    "cetait un ordre": "corriger ça",
    "c'était une commande vocale": "corriger ça",
    "cetait une commande vocale": "corriger ça",
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

# Choix 4 à 9 (jusqu'à 9 alternatives de correction, fenêtre séparée)
for _word, _value in (
    ("quatre", 4),
    ("cinq", 5),
    ("six", 6),
    ("sept", 7),
    ("huit", 8),
    ("neuf", 9),
):
    CHOOSE_MAP[f"choisir {_word}"] = _value
    CHOOSE_MAP[f"choix {_word}"] = _value
    CHOOSE_MAP[f"numéro {_word}"] = _value
    CHOOSE_MAP[f"choisir {_value}"] = _value
    CHOOSE_MAP[f"choix {_value}"] = _value
    CHOOSE_MAP[f"numéro {_value}"] = _value


# --- Index de comparaison des commandes (dérivés EN MÉMOIRE, jamais persistés) -----
# Les tables ci-dessus restent écrites en français naturel (accents, apostrophes).
# On en dérive ici, via `command_keys()`, toutes les formes tolérées à la
# comparaison : casse, accents, apostrophes (droites/typographiques), ponctuation.
# Ces index ne servent qu'au matching dans `process()` ; ils ne sont ni affichés ni
# enregistrés sur disque.

def _index_set(entries: Iterable[str]) -> set[str]:
    return {variant for entry in entries for variant in command_keys(entry)}


def _index_map(table: Mapping[str, _T]) -> dict[str, _T]:
    index: dict[str, _T] = {}
    for entry, value in table.items():
        for variant in command_keys(entry):
            index.setdefault(variant, value)
    return index


WAKE_KEYS = _index_set(WAKE_COMMANDS)
SLEEP_KEYS = _index_set(SLEEP_COMMANDS)
MUTE_KEYS = _index_set(MUTE_COMMANDS)
SHOW_HELP_KEYS = _index_set(SHOW_HELP_COMMANDS)
APPLY_CORRECTION_KEYS = _index_set(APPLY_CORRECTION_COMMANDS)
SCRATCH_KEYS = _index_set(SCRATCH_COMMANDS)
OUPS_KEYS = _index_set(OUPS_COMMANDS)
SPELLING_ENTER_KEYS = _index_set(SPELLING_ENTER_COMMANDS)
SPELLING_EXIT_KEYS = _index_set(SPELLING_EXIT_COMMANDS)
OPEN_CORRECTION_KEYS = _index_set(OPEN_CORRECTION_COMMANDS)
OPEN_STUDIO_KEYS = _index_set(OPEN_STUDIO_COMMANDS)
COMMAND_RECALIBRATION_KEYS = _index_map(COMMAND_RECALIBRATION_COMMANDS)
PRESS_ENTER_KEYS = _index_set(PRESS_ENTER_COMMANDS)
CHOOSE_KEYS = _index_map(CHOOSE_MAP)

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
            r"[,.?]?\s*\b(?:point|pour|pas)\s+(?:d['’]?|l['’]?|à['’]?)\s*interrogation\b[.!?]*",
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


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    """Vrai si `a` et `b` diffèrent d'au plus une insertion/suppression/substitution."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    # `a` le plus court : un seul glissement autorisé
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


def _nato_fuzzy(token: str) -> str | None:
    """Lettre NATO à écart <= 1 — prononciation dysarthrique (« make » ≈ « mike »).

    Tolérance **en mémoire, mode épellation uniquement** (le tableau reste en
    français naturel). Les mots de < 3 lettres sont exclus (trop de faux amis).
    """
    if len(token) < 3:
        return None
    for key, letter in NATO_ALPHABET.items():
        if _edit_distance_at_most_one(token, key):
            return letter
    return None


def _edit_distance_at_most_two(a: str, b: str) -> bool:
    """Vrai si `a` et `b` diffèrent d'au plus deux insertions/suppressions/substitutions."""
    if abs(len(a) - len(b)) > 2:
        return False
    # Distance de Levenshtein (coûts unitaires) — mots-clés très courts.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1] <= 2


def _nato_space_fuzzy(token: str) -> bool:
    """Tolérance sur le jeton « espace » **uniquement** (mode épellation).

    Deux familles de formes acceptées, jetons de >= 5 lettres :
    - écart <= 1 sur « espace » / « space » (petites fautes de STT) ;
    - « s » final de pluriel dont la racine est un PRÉFIXE exact de la famille
      (« espaces » → « espace », « spaces » → « space », « espas » → « espa… ») :
      le « s » du pluriel s'entend souvent à la place de « ce » (« espas » ≈
      « espaces » — écart 2, d'où ce second critère).

    Aucune autre famille n'est acceptée : un mot lointain (« voiture »,
    « espagne »…) ne doit JAMAIS devenir un espace.
    """
    if len(token) < 5:
        return False
    if any(_edit_distance_at_most_one(token, key) for key in NATO_SPACE_TOKENS):
        return True
    if token.endswith("s"):
        stem = token[:-1]
        if len(stem) >= 4 and any(key.startswith(stem) for key in NATO_SPACE_TOKENS):
            return True
    return False


DIGIT_WORDS: dict[str, str] = {
    "zéro": "0",
    "zero": "0",
    "un": "1",
    "une": "1",
    "deux": "2",
    "trois": "3",
    "quatre": "4",
    "cinq": "5",
    "six": "6",
    "sept": "7",
    "huit": "8",
    "neuf": "9",
}

# --- Accents dictés (mode épellation) ------------------------------------------
# « écho accent aigu » → « é » (composition sur la dernière lettre épelée) ;
# « accent grave » isolé → « è ». Tables en français naturel, tolérance en mémoire.
ACCENT_SPECS: dict[str, tuple[dict[str, str], str]] = {
    # forme dictée -> (table de composition lettre -> lettre, caractère autonome)
    "aigu": ({"e": "é"}, "é"),
    "grave": ({"a": "à", "e": "è", "u": "ù"}, "è"),
    "circonflexe": ({"a": "â", "e": "ê", "i": "î", "o": "ô", "u": "û"}, "ê"),
    "cédille": ({"c": "ç"}, "ç"),
    "cedille": ({"c": "ç"}, "ç"),
    "tréma": ({"e": "ë", "i": "ï", "u": "ü"}, "ï"),
    "trema": ({"e": "ë", "i": "ï", "u": "ü"}, "ï"),
}
# Formes utilisables SANS le mot « accent » (non ambiguës avec des mots courants) :
# « circonflexe » / « cédille » / « tréma » seuls restent acceptés.
ACCENT_BARE_FORMS: frozenset[str] = frozenset(
    {"circonflexe", "cédille", "cedille", "tréma", "trema"}
)


def _apply_accent(out: list[str], spec: tuple[dict[str, str], str]) -> None:
    """Compose l'accent sur la dernière lettre épelée, sinon insère le caractère."""
    table, standalone = spec
    if out and out[-1] in table:
        out[-1] = table[out[-1]]
    else:
        out.append(standalone)


def _ends_with_explicit_spoken_punctuation(norm_text: str) -> bool:
    n = norm_text.strip()
    if not n:
        return False
    # Normaliser apostrophes et espaces pour la détection (ex. « l'interrogation » / « linterrogation »)
    n = n.replace("’", "'").replace("'", " ").replace("  ", " ").strip()
    for ending in EXPLICIT_SPOKEN_PUNCT_ENDINGS:
        e = ending.replace("’", "'").replace("'", " ").replace("  ", " ").strip()
        if n == e or n.endswith(" " + e) or n.endswith(e):
            return True
    return False


def text_to_nato_spelling(raw_text: str) -> str:
    """Convertit une énonciation d'alphabet radio (Alpha Bravo Charlie) en texte épelé.
    - Lettres NATO : Alpha/Bravo/... -> a/b/...
    - « chiffre <x> » : insère le chiffre (ex. « chiffre un », « chiffre 5 » -> « 1 », « 5 »)
    - « en lettres <mot> » / « mot <mot> » : insère le mot littéral (ex. « en lettres un » -> « un »)
    - « espace » : insère un espace
    """
    norm = normalize_key(raw_text)
    if not norm:
        return ""
    # Normalisations de tokens multi-mots
    norm = (
        norm.replace("trait d union", "trait-d-union")
        .replace("x ray", "x-ray")
        .replace("fox trot", "fox-trot")
        # « espace » scindé par le STT (« es pace ») : reconstitué comme « x ray »
        .replace("es pace", "espace")
    )
    tokens = norm.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].replace("’", "'").strip("-")
        t_compact = tok.replace("-", " ")

        # « chiffre un » / « chiffre 5 » -> caractère(s) numérique(s)
        if tok == "chiffre" and i + 1 < len(tokens):
            nxt = tokens[i + 1].replace("’", "'").strip("-")
            if nxt in DIGIT_WORDS:
                out.append(DIGIT_WORDS[nxt])
                i += 2
                continue
            if nxt.isdigit():
                out.append(nxt)
                i += 2
                continue

        # « en lettres un » / « mot un » -> insérer le mot littéral (utile en correction)
        if tok == "mot" and i + 1 < len(tokens):
            out.append(tokens[i + 1])
            i += 2
            continue
        if tok == "en" and i + 2 < len(tokens) and tokens[i + 1] == "lettres":
            out.append(tokens[i + 2])
            i += 3
            continue

        # Accents dictés : composition sur la dernière lettre épelée
        # (« écho accent aigu » → « é », « charlie cédille » → « ç ») ; sinon
        # caractère autonome (« accent grave » isolé → « è »). Pluriels tolérés
        # (« accents aigus »). Lettres = alphabet OTAN uniquement (décision 13/11).
        if tok in ("accent", "accents") and i + 1 < len(tokens):
            nxt = tokens[i + 1].replace("’", "'").strip("-")
            spec = ACCENT_SPECS.get(nxt)
            if spec is None and nxt.endswith("s"):
                spec = ACCENT_SPECS.get(nxt[:-1])
            if spec is not None:
                _apply_accent(out, spec)
                i += 2
                continue
        bare = tok if tok in ACCENT_BARE_FORMS else None
        if bare is None and tok.endswith("s") and tok[:-1] in ACCENT_BARE_FORMS:
            bare = tok[:-1]
        if bare is not None:
            _apply_accent(out, ACCENT_SPECS[bare])
            i += 1
            continue

        # Symboles dictés (« point », « virgule », « arobase », « astérisque »…) —
        # insertion littérale pour faciliter les adresses e-mail en mode épellation.
        # Les formes ambiguës (« euro »…) y prennent le symbole d'office ;
        # « mot euro » reste disponible pour écrire le mot littéral.
        sym = spelling_symbol(tok)
        if sym is not None:
            out.append(sym)
            i += 1
            continue

        if tok in NATO_ALPHABET:
            out.append(NATO_ALPHABET[tok])
        elif t_compact in NATO_ALPHABET:
            out.append(NATO_ALPHABET[t_compact])
        elif tok in NATO_SPACE_TOKENS or _nato_space_fuzzy(tok):
            out.append(" ")
        elif tok in NATO_EMPTY_TOKENS or t_compact in NATO_EMPTY_TOKENS:
            if "tiret" in tok or "moins" in tok:
                out.append("-")
        elif len(tok) == 1 and tok.isalnum():
            out.append(tok)
        else:
            # Tolérance phonétique (en mémoire, mode épellation uniquement) :
            # « make » ≈ « mike » (écart <= 1) → lettre acceptée quand même.
            fuzzy = _nato_fuzzy(tok)
            if fuzzy is not None:
                out.append(fuzzy)
        # Les autres mots inconnus sont ignorés pour éviter d'injecter du texte dicté parasite en mode épellation
        i += 1
    return "".join(out)


def spelling_from_result(
    raw_text: str, alternatives: Iterable[str] | None = None
) -> tuple[str, str | None]:
    """Conversion d'un souffle en texte épellé (mode épellation) — rejet explicite.

    Retourne `(texte, rejet)` :
    - `texte` non vide → conversion réussie (directement, ou retrouvée dans les
      alternatives du STT — ex. « M. » parmi les secondes hypothèses de « Make. ») ;
    - `texte` vide + `rejet=None` → souffle vide (silence : rien à signaler) ;
    - `texte` vide + `rejet=raw_text` → **non reconnu** : l'appelant doit
      AFFICHER le rejet — plus jamais de silence `dictation_empty` en épellation.
    """
    spelled = text_to_nato_spelling(raw_text)
    if spelled:
        return spelled, None
    if not raw_text.strip():
        return "", None
    for alt in alternatives or ():
        cand = text_to_nato_spelling(alt)
        if cand:
            return cand, None
    return "", raw_text.strip()


# --- Commandes de casse en mode épellation (orthographe naturelle, 14/11) ------
# Le « s » final est muet en français : les formes SINGULIER et PLURIEL sont
# explicitement listées et acceptées à l'écoute — aucune dépendance à
# l'orthographe que le STT aura écrite (« Majuscule » ≡ « Majuscules »).

CASING_UPPER_NEXT = "upper_next"   # « Majuscule »       → prochaine lettre
CASING_LOWER_NEXT = "lower_next"   # « Minuscule »       → prochaine lettre
CASING_UPPER_ALL = "upper_all"     # « Tout en majuscules » → toutes les suivantes
CASING_LOWER_ALL = "lower_all"     # « Tout en minuscules » → toutes les suivantes
CASING_RESET = "reset"             # « Fin majuscules »  → retour au normal

_CASING_COMMANDS: dict[str, str] = {
    "majuscule": CASING_UPPER_NEXT,
    "majuscules": CASING_UPPER_NEXT,
    "minuscule": CASING_LOWER_NEXT,
    "minuscules": CASING_LOWER_NEXT,
    "tout en majuscule": CASING_UPPER_ALL,
    "tout en majuscules": CASING_UPPER_ALL,
    "tout en minuscule": CASING_LOWER_ALL,
    "tout en minuscules": CASING_LOWER_ALL,
    "fin majuscule": CASING_RESET,
    "fin majuscules": CASING_RESET,
    "fin minuscule": CASING_RESET,
    "fin minuscules": CASING_RESET,
    "fin des majuscules": CASING_RESET,
    "fin des minuscules": CASING_RESET,
}


def _normalize_casing_utterance(raw: str) -> str:
    """Minuscules + ponctuation de fin de phrase retirée (« Majuscules ! »)."""
    text = (raw or "").strip().lower().replace("’", "'")
    text = re.sub(r"[.!?…,:;]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def spelling_casing_command(
    raw_text: str, alternatives: Iterable[str] | None = None
) -> str | None:
    """Détecte une commande de casse DITE en mode épellation.

    Retourne `CASING_UPPER_NEXT` / `CASING_LOWER_NEXT` (prochaine lettre),
    `CASING_UPPER_ALL` / `CASING_LOWER_ALL` (toutes les suivantes) ou
    `CASING_RESET` (« Fin majuscules/minuscules »), sinon `None`.
    Les alternatives du STT sont vérifiées après le texte principal.
    """
    for candidate in (raw_text, *(alternatives or ())):
        action = _CASING_COMMANDS.get(_normalize_casing_utterance(candidate))
        if action is not None:
            return action
    return None


class SpellingCasingState:
    """État de casse du mode épellation : lettre suivante (ponctuel) / suivantes.

    - une commande « Majuscule/Minuscule » s'applique à la PROCHAINE production
      contenant une lettre (espace/chiffre ne la consomme pas) ;
    - une commande « Tout en … » reste active jusqu'à « Fin … » ou la sortie
      du mode épellation ;
    - la commande ponctuelle prime sur le mode persistant.
    """

    def __init__(self) -> None:
        self._next: str | None = None
        self._all: str | None = None

    def apply_command(self, action: str) -> None:
        if action == CASING_UPPER_NEXT:
            self._next = "upper"
        elif action == CASING_LOWER_NEXT:
            self._next = "lower"
        elif action == CASING_UPPER_ALL:
            self._all, self._next = "upper", None
        elif action == CASING_LOWER_ALL:
            self._all, self._next = "lower", None
        elif action == CASING_RESET:
            self._next = None
            self._all = None

    def apply_to_text(self, text: str) -> str:
        """Applique la casse active ; consomme la commande ponctuelle si lettres."""
        mode = self._next or self._all
        if not mode or not text:
            return text
        out = text.upper() if mode == "upper" else text.lower()
        if self._next is not None and any(ch.isalpha() for ch in text):
            self._next = None
        return out

    def reset(self) -> None:
        self._next = None
        self._all = None


class HybridPunctuationProcessor:
    """Applique les règles déterministes A->B, route les commandes Phase 2 et met en forme la ponctuation."""

    def __init__(
        self,
        rule_engine: PhoneticRuleEngine | None = None,
        enable_strict_dictionary: bool = False,
        spoken_forms_path: str | Path | None = None,
    ) -> None:
        self.rule_engine = rule_engine or PhoneticRuleEngine()
        self.enable_strict_dictionary = enable_strict_dictionary
        # Dictionnaire personnel de formes orales (« si tu entends A, écris B »)
        self.spoken_forms = (
            SpokenFormStore(spoken_forms_path)
            if spoken_forms_path is not None
            else SpokenFormStore()
        )
        # Dernier texte produit (repli quand l'appelant ne fournit pas le contexte) :
        # sert à la cohérence casse/espaces entre souffles.
        self._last_produced: str = ""

    def reset_context(self) -> None:
        self._last_produced = ""

    # ------------------------------------------------------------------
    # Formatage du texte dicté (cœur partagé dictée / alternatives)
    # ------------------------------------------------------------------

    def _format_core(self, mapped: str) -> tuple[str, _Substitution]:
        """Cœur de formatage d'un chunk dicté — AUCUNE mutation d'état.

        Retire la ponctuation automatique du modèle, applique le dictionnaire
        de formes orales, les règles de ponctuation dictée (« virgule »,
        « point »…) et les formes de symboles. La cohérence inter-souffles
        (casse / espace de liaison) est appliquée ensuite par
        `format_dictation` ou `format_alternatives`.
        """
        norm = normalize_key(mapped)
        explicit_spoken_punct = _ends_with_explicit_spoken_punctuation(norm)
        text = mapped.strip()
        # AUCUNE ponctuation automatique : on retire tout ce que le modèle de
        # transcription a pu ajouter (« Comment vas-tu ? » injectait « ? » tout
        # seul et « Comment vas-tu pour l'interrogation ? » injectait « ? ? »).
        # La ponctuation dictée (« virgule », « point »…) est écrite APRÈS, par
        # les règles et formes de symboles — elle n'est donc pas touchée ici.
        # La couche de cohérence remettra ponctuation/casse selon les options
        # choisies par l'utilisateur (voir postprocess/coherence.py).
        text = strip_auto_punctuation(text)
        # Dictionnaire personnel de formes orales (« si tu entends A, écris B ») :
        # prioritaire, appliqué sur la forme dictée brute avant les règles générales.
        text = self.spoken_forms.apply(text)
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

        # Formes orales de symboles (« astérisque » → « * », façon Dragon) :
        # substitution en place APRÈS les règles de ponctuation dictée (« virgule »,
        # « deux points »… sont déjà traitées là) + typographie française contextuelle.
        substitution = apply_symbol_forms(text)
        return substitution.text, substitution

    def format_dictation(
        self, mapped: str, previous_text: str | None = None
    ) -> tuple[str, str | None, _Substitution]:
        """Formate un chunk dicté avec cohérence inter-souffles.

        Casse (majuscule seulement au début du texte et après une fin de phrase
        dictée) + espace de liaison, puis mémorisation de la fin du texte produit
        pour le souffle suivant. Retourne `(texte, variante_symbole, substitution)`.
        """
        text, substitution = self._format_core(mapped)
        ctx = previous_text if previous_text is not None else self._last_produced
        text = adapt_chunk_to_context(text, ctx)
        variant_text = (
            adapt_chunk_to_context(substitution.variant_text, ctx)
            if substitution.variant_text is not None
            else None
        )
        if text:
            # Mémorise la fin du texte produit pour le souffle suivant
            # (repli si l'appelant ne fournit pas `previous_text`).
            self._last_produced = text
        return text, variant_text, substitution

    def format_alternatives(
        self,
        alternatives: list[str],
        previous_text: str | None = None,
        chosen_text: str = "",
    ) -> list[str]:
        """Formate les alternatives de correction avec les MÊMES règles que le
        texte dicté (ponctuation dictée, symboles, casse/espaces), exclut le
        choix retenu et dédoublonne (insensible à la casse).

        Aucune mutation d'état : une alternative proposée n'est pas un texte
        produit. Retourne les alternatives nettoyées, prêtes pour la fenêtre
        « Corriger ça » (jusqu'à 9).
        """
        ctx = previous_text if previous_text is not None else self._last_produced
        chosen_key = chosen_text.strip().casefold()
        out: list[str] = []
        seen: set[str] = set()
        for alt in alternatives:
            raw = (alt or "").strip()
            if not raw:
                continue
            text, _sub = self._format_core(raw)
            text = adapt_chunk_to_context(text, ctx).strip()
            key = text.casefold()
            if not key or key == chosen_key or key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def process(
        self,
        raw_text: str,
        is_sleeping: bool = False,
        previous_text: str | None = None,
    ) -> ProcessedUtterance:
        """Route l'énoncé ; `previous_text` (texte déjà injecté) guide casse/espaces du dicté."""
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
        # Formes tolérées de l'énoncé pour le matching des commandes (en mémoire) :
        # « C'était une commande, » ≡ « c'etait une commande » ≡ « CETAIT UNE COMMANDE ! »
        ckey = command_keys(mapped)
        # Énoncés doublés (« Mode épellation, mode épellation. », « Corriger ça,
        # Corriger ça. ») : repli de la répétition pour le matching SEULEMENT —
        # le texte dicté (`mapped`) reste intact.
        collapsed = collapse_repeated_utterance(norm)
        if collapsed != norm:
            for k in command_keys(collapsed):
                if k not in ckey:
                    ckey.insert(0, k)
            norm = collapsed

        def _hit(index: set[str]) -> bool:
            return any(v in index for v in ckey)

        def _lookup(index: Mapping[str, _T]) -> _T | None:
            for v in ckey:
                if v in index:
                    return index[v]
            return None

        # 2. En mode veille vocale (« Phénix repos »), seules quelques commandes de contrôle restent actives
        if is_sleeping:
            if _hit(WAKE_KEYS) or any(
                v.endswith(w) for v in ckey for w in WAKE_KEYS
            ):
                return ProcessedUtterance(
                    intent=VoiceIntentType.WAKE, raw_text=raw_text, mapped_text=mapped
                )
            if _hit(MUTE_KEYS):
                return ProcessedUtterance(
                    intent=VoiceIntentType.MUTE_MIC,
                    raw_text=raw_text,
                    mapped_text=mapped,
                )
            if _hit(SHOW_HELP_KEYS):
                return ProcessedUtterance(
                    intent=VoiceIntentType.SHOW_HELP,
                    raw_text=raw_text,
                    mapped_text=mapped,
                )
            if _hit(SPELLING_EXIT_KEYS):
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
        if _hit(MUTE_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.MUTE_MIC, raw_text=raw_text, mapped_text=mapped
            )
        if _hit(SLEEP_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.SLEEP, raw_text=raw_text, mapped_text=mapped
            )
        if _hit(WAKE_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.WAKE, raw_text=raw_text, mapped_text=mapped
            )
        if _hit(SHOW_HELP_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.SHOW_HELP, raw_text=raw_text, mapped_text=mapped
            )
        if _hit(SPELLING_EXIT_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.EXIT_SPELLING, raw_text=raw_text, mapped_text=mapped
            )
        if _hit(SPELLING_ENTER_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.ENTER_SPELLING, raw_text=raw_text, mapped_text=mapped
            )
        recal_target = _lookup(COMMAND_RECALIBRATION_KEYS)
        if recal_target is not None:
            return ProcessedUtterance(
                intent=VoiceIntentType.REVISE_COMMAND,
                raw_text=raw_text,
                mapped_text=mapped,
                target_arg=recal_target,
            )

        # 4. Commandes de correction, d'édition et de touche Entrée
        if _hit(APPLY_CORRECTION_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.APPLY_CORRECTION,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if _hit(PRESS_ENTER_KEYS):
            # Entrée = nouvelle ligne : le souffle suivant reprend une majuscule.
            self._last_produced = "\n"
            return ProcessedUtterance(
                intent=VoiceIntentType.PRESS_ENTER,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if _hit(OUPS_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.OUPS_NO_LEARN,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if _hit(SCRATCH_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.SCRATCH_LAST,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if _hit(OPEN_CORRECTION_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.OPEN_CORRECTION,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        if _hit(OPEN_STUDIO_KEYS):
            return ProcessedUtterance(
                intent=VoiceIntentType.OPEN_STUDIO,
                raw_text=raw_text,
                mapped_text=mapped,
            )
        choice = _lookup(CHOOSE_KEYS)
        if choice is not None:
            return ProcessedUtterance(
                intent=VoiceIntentType.CHOOSE_ALT,
                raw_text=raw_text,
                mapped_text=mapped,
                choice_index=choice,
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
        # (cœur partagé avec `format_alternatives` : mêmes règles pour les
        # choix de la fenêtre « Corriger ça » — voir `_format_core`).
        text, variant_text, substitution = self.format_dictation(
            mapped, previous_text
        )

        return ProcessedUtterance(
            intent=VoiceIntentType.DICTATION,
            text_to_inject=text,
            raw_text=raw_text,
            mapped_text=mapped,
            symbol_form=substitution.form,
            symbol_char=substitution.symbol_char,
            symbol_choices=[text, variant_text] if variant_text is not None else None,
        )
