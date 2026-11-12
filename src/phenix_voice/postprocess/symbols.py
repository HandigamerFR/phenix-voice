"""Formes orales de symboles (« astérisque » → « * », façon Dragon) et dictionnaire
personnel de formes orales (« si tu entends A, écris B »).

Principe de design (imposé par l'utilisateur) :
- Les tables restent écrites en **français naturel** (accents, apostrophes).
- La tolérance (casse, accents, apostrophes, ponctuation) n'existe que dans la
  clé de comparaison dérivée **en mémoire** via `command_keys()` — jamais
  persistée, jamais affichée.
- Substitution **en place** : le symbole remplace le mot dicté en conservant les
  espaces dictés (typographie française contextuelle ensuite) :
  - signes à double partie (`` : ``, `` ; ``, `` ! ``, `` ? ``, `` % ``) :
    espace **avant et après** ;
  - `` € £ § ® ° `` : espace **avant** (typographie française) ;
  - `` @ `` : **collé** aux mots voisins seulement en contexte e-mail détecté
    (mot avant/après alphanumérique, pas de mot-outro), sinon espaces dictés.
- Les formes **ambiguës** (« euro », « dollar », « paragraphe »…) insèrent le
  symbole par défaut et remontent une seconde alternative (le mot dicté) pour
  une popup de choix façon Dragon (voix « choix un / deux » ou clic).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

from phenix_voice.postprocess.rules import command_keys

# --- Tables (français naturel — la tolérance vit uniquement dans les clés) --------

# Formes orales SANS ambiguïté : substitution directe.
# Remarque : « virgule », « point », « deux points », « point-virgule »,
# « points de suspension », « guillemets », « parenthèse », « à la ligne »…
# sont déjà gérés par SPOKEN_PUNCTUATION_RULES (appliquée avant ce module).
CORE_SYMBOL_FORMS: dict[str, str] = {
    "esperluette": "&",
    "astérisque": "*",
    "arobase": "@",
    "arrobase": "@",
    "barre oblique": "/",
    "barre oblique inverse": "\\",
    "chevron d'insertion": "^",
    "ellipse": "...",
    "tilde": "~",
    "soulignement": "_",
    "dièse": "#",
    "barre verticale": "|",
    "livre sterling": "£",
    "marque déposée": "®",
    "ouvrir les crochets": "[",
    "fermer les crochets": "]",
    "ouvrir les accolades": "{",
    "fermer les accolades": "}",
    "ouvrir les chevrons": "<",
    "fermer les chevrons": ">",
    "signe égal": "=",
    "signe plus": "+",
    "signe moins": "-",
    "smiley content": ":-)",
    "smiley triste": ":-(",
    "smiley clin d'œil": ";-)",
}

# Formes orales AMBIGUËS (mots courants) : le symbole est inséré par défaut et
# une popup propose aussi le mot dicté (« choix un » = symbole, « choix deux » = mot).
AMBIGUOUS_SYMBOL_FORMS: dict[str, str] = {
    "euro": "€",
    "euros": "€",
    "dollar": "$",
    "dollars": "$",
    "paragraphe": "§",
    "degré": "°",
    "degrés": "°",
    "copyright": "©",
    "pourcentage": "%",
}

# Formes supplémentaires utiles UNIQUEMENT en mode épellation (où chaque jeton
# est interprété littéralement) : « point » / « virgule » isolés, très courants
# pour dicter une adresse e-mail lettre-à-lettre.
SPELLING_EXTRA_SYMBOL_FORMS: dict[str, str] = {
    "point": ".",
    "virgule": ",",
}

# --- Typographie française contextuelle ------------------------------------------

# Espace avant ET après (signes à deux parties).
SPACED_BOTH: set[str] = {":", ";", "!", "?", "%"}
# Espace avant seulement (unités / mentions typographiques françaises).
SPACED_BEFORE: set[str] = {"€", "£", "§", "®", "©", "°"}
# Collé aux mots voisins si le contexte ressemble à un e-mail.
GLUED: set[str] = {"@"}

# Mots-outro : si le mot qui suit « @ » en est un, ce n'est probablement pas un e-mail.
_EMAIL_STOP_WORDS: frozenset[str] = frozenset(
    {
        "le", "la", "les", "un", "une", "des", "du", "de", "et", "en", "à", "au",
        "aux", "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes",
        "son", "sa", "ses", "dans", "par", "pour", "que", "qui", "est", "sont",
        "sur", "avec", "ou", "où", "plus", "pas", "que", "qu", "l", "d", "n", "j",
    }
)

_TOKEN_RE = re.compile(r"\S+")
_EDGE_PUNCT = ".,;:!?…()[]{}«»\"'’–—/\\@#*+=<>|~^%$€£§©®°"


def _build_index(table: Mapping[str, object]) -> dict[str, object]:
    """Index de comparaison tolérant — dérivé EN MÉMOIRE uniquement."""
    index: dict[str, object] = {}
    for entry, value in table.items():
        for key in command_keys(entry):
            index.setdefault(key, value)
    return index


def _core_and_offset(token: str) -> tuple[str, int]:
    """Mot « nu » d'un jeton (ponctuation de bord retirée) + décalage dans le jeton."""
    start = 0
    end = len(token)
    while start < end and token[start] in _EDGE_PUNCT:
        start += 1
    while end > start and token[end - 1] in _EDGE_PUNCT:
        end -= 1
    return token[start:end], start


def _email_context(prev_core: str | None, next_core: str | None) -> bool:
    """Détecte un contexte e-mail pour coller « @ » (ex. « laure arobase gmail »)."""
    if not prev_core or not next_core:
        return False
    if prev_core.lower() in _EMAIL_STOP_WORDS or next_core.lower() in _EMAIL_STOP_WORDS:
        return False
    for core in (prev_core, next_core):
        if not all(ch.isalnum() or ch in "'’" for ch in core):
            return False
    return True


@dataclass
class _Substitution:
    text: str
    variant_text: str | None = None  # variante gardant le mot dicté (si ambiguïté)
    form: str = ""  # forme dictée (titre de la popup)
    symbol_char: str = ""  # symbole inséré (libellé de la popup)


def _render_piece(replacement: str, before: str, after: str, glue: bool) -> str:
    """Habille le symbole selon la typographie française contextuelle."""
    if glue:
        return replacement
    piece = replacement
    if replacement in SPACED_BOTH:
        if before and before.isalnum():
            piece = " " + piece
        if after and after.isalnum():
            piece = piece + " "
    elif replacement in SPACED_BEFORE:
        if before and before.isalnum():
            piece = " " + piece
    return piece


def _substitute(
    text: str,
    index: Mapping[str, tuple[str, bool]],
    max_words: int,
) -> _Substitution:
    """Remplace les formes orales du texte (fenêtres glissantes multi-mots).

    Les valeurs de l'index sont `(texte de remplacement, ambiguë?)`.
    Si une forme ambiguë est rencontrée, une variante complète du texte (mot
    conservé) est produite pour la popup de choix.
    """
    if not text or not index:
        return _Substitution(text)

    tokens = list(_TOKEN_RE.finditer(text))
    token_cores: list[tuple[str, int]] = [_core_and_offset(t.group()) for t in tokens]

    # 1) Repérage des correspondances (fenêtre la plus longue d'abord)
    matches: list[tuple[int, int, tuple[str, bool]]] = []
    i = 0
    while i < len(tokens):
        found = None
        for size in range(min(max_words, len(tokens) - i), 0, -1):
            cores = token_cores[i : i + size]
            if any(not core for core, _ in cores):
                continue
            if size > 1:
                gaps_ok = all(
                    text[tokens[j].end() : tokens[j + 1].start()] in ("",)
                    or text[tokens[j].end() : tokens[j + 1].start()].isspace()
                    for j in range(i, i + size - 1)
                )
                if not gaps_ok:
                    continue
            phrase = " ".join(core for core, _ in cores)
            hit = None
            for key in command_keys(phrase):
                if key in index:
                    hit = index[key]
                    break
            if hit is not None:
                found = (size, hit)
                break
        if found is not None:
            matches.append((i, found[0], found[1]))
            i += found[0]
        else:
            i += 1

    if not matches:
        return _Substitution(text)

    def _build(skip: int = -1) -> str:
        out: list[str] = []
        pos = 0
        for idx, (mi, size, (replacement, _is_amb)) in enumerate(matches):
            first_core, first_off = token_cores[mi]
            last_core, last_off = token_cores[mi + size - 1]
            span_start = tokens[mi].start() + first_off
            span_end = tokens[mi + size - 1].start() + last_off + len(last_core)
            gap = text[pos:span_start]
            if idx == skip:
                # Variante : on garde le mot dicté tel quel.
                out.append(gap)
                out.append(text[span_start:span_end])
                pos = span_end
                continue
            prev_core = token_cores[mi - 1][0] if mi > 0 else None
            next_core = token_cores[mi + size][0] if mi + size < len(tokens) else None
            glue = False
            if replacement in GLUED:
                glue = _email_context(prev_core, next_core)
                if glue and gap.endswith((" ", "\t")):
                    # Collage à gauche : retirer l'espace dicté juste avant le symbole
                    gap = gap.rstrip(" \t")
            before = text[span_start - 1] if span_start > 0 else ""
            after = text[span_end] if span_end < len(text) else ""
            out.append(gap)
            out.append(_render_piece(replacement, before, after, glue))
            pos = span_end
            if glue:
                while pos < len(text) and text[pos] in " \t":
                    pos += 1
        out.append(text[pos:])
        return "".join(out)

    # 2) Première ambiguïté rencontrée → variante « mot dicté » pour la popup
    ambiguous_at = next(
        (idx for idx, (_, _, (_, is_amb)) in enumerate(matches) if is_amb), None
    )
    result_text = _build()
    if ambiguous_at is None:
        return _Substitution(result_text)

    variant = _build(skip=ambiguous_at)
    mi, size, (symbol_char, _) = matches[ambiguous_at]
    form = token_cores[mi][0]
    return _Substitution(
        text=result_text,
        variant_text=variant,
        form=form,
        symbol_char=symbol_char,
    )


_SYMBOL_INDEX: dict[str, tuple[str, bool]] = {
    **{k: (v, False) for k, v in _build_index(CORE_SYMBOL_FORMS).items()},
    **{k: (v, True) for k, v in _build_index(AMBIGUOUS_SYMBOL_FORMS).items()},
}
_SYMBOL_MAX_WORDS = max(
    len(entry.split())
    for entry in (*CORE_SYMBOL_FORMS, *AMBIGUOUS_SYMBOL_FORMS)
)

# Index simple pour le mode épellation (jeton → symbole), tolérant en mémoire.
SPELLING_SYMBOL_INDEX: dict[str, str] = _build_index(
    {**CORE_SYMBOL_FORMS, **AMBIGUOUS_SYMBOL_FORMS, **SPELLING_EXTRA_SYMBOL_FORMS}
)


def apply_symbol_forms(text: str) -> _Substitution:
    """Substitution des formes orales de symboles dans un texte dicté."""
    return _substitute(text, _SYMBOL_INDEX, _SYMBOL_MAX_WORDS)


def spelling_symbol(token: str) -> str | None:
    """Symbole correspondant à un jeton en mode épellation (sinon `None`)."""
    if not token:
        return None
    for key in command_keys(token):
        if key in SPELLING_SYMBOL_INDEX:
            return SPELLING_SYMBOL_INDEX[key]
    return None


class SpokenFormStore:
    """Dictionnaire personnel de formes orales persisté dans
    `user_data/spoken_forms.json` (« si tu entends A, écris B »).

    Prioritaire sur les règles générales : ajoutable depuis le volet de
    correction (bouton « + Forme orale »). La tolérance de comparaison reste
    en mémoire ; seules les formes naturelles sont écrites sur disque.
    """

    def __init__(self, path: str | Path = "user_data/spoken_forms.json") -> None:
        self.path = Path(path)
        self.forms: dict[str, str] = {}
        self._index: dict[str, tuple[str, bool]] = {}
        self._max_words = 1
        self._load()

    def _rebuild_index(self) -> None:
        natural_index = _build_index(self.forms)
        self._index = {k: (v, False) for k, v in natural_index.items()}
        self._max_words = max((len(e.split()) for e in self.forms), default=1)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw = data.get("forms", {})
            if isinstance(raw, dict):
                self.forms = {
                    str(k): str(v) for k, v in raw.items() if str(v).strip()
                }
        except Exception:
            self.forms = {}
        self._rebuild_index()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"forms": self.forms}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, heard_text: str, written_text: str) -> bool:
        """Enregistre « si tu entends `heard`, écris `written` ». Refuse si vide/identique."""
        heard = (heard_text or "").strip()
        written = (written_text or "").strip()
        if not heard or not written:
            return False
        heard_keys = command_keys(heard)
        written_keys = command_keys(written)
        if not heard_keys or not written_keys:
            return False
        if heard_keys[0] == written_keys[0]:
            return False
        if len(heard_keys[0]) < 2:
            return False
        self.forms[heard] = written
        self._rebuild_index()
        self._save()
        return True

    def apply(self, text: str) -> str:
        """Applique les formes personnelles (priorité sur les règles générales)."""
        if not text or not self._index:
            return text
        return _substitute(text, self._index, self._max_words).text
