"""Compile le lexique d'accord (Lexique383) → resources/lexique_accords.tsv.

Usage :
    python tools/build_lexicon_accords.py <Lexique383.tsv> [sortie.tsv]

Entrée : Lexique383.tsv (http://www.lexique.org/databases/Lexique383/Lexique383.zip,
licence CC BY-SA 4.0, voir src/phenix_voice/resources/README_Lexique383.txt).

Sortie : une ligne par FAMILLE d'accord = formes réelles partageant
(lemme, tronc d'accord, statut accentué du suffixe), classées par fréquence
décroissante (freqlivres + freqfilms2). Les familles à une seule forme sont
écartées (rien à proposer). Le fichier est ensuite lu par
``phenix_voice.postprocess.agreement``.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

# Suffixes d'accord, du plus long au plus court. « aux » (chevaux → cheval) est
# spécial : le tronc devient stem + "ail" ; « eaux » (bateaux → bateau) passe
# par le retrait simple du « x ».
_SUFFIXES: tuple[str, ...] = (
    "ées",  # terminées → termin
    "eaux",  # bateaux → bateau
    "és",  # terminés → termin
    "ée",  # terminée → termin
    "es",  # faites → fait
    "aux",  # chevaux → cheval
    "é",  # terminé → termin
    "x",  # cheveux → cheveu
    "s",  # conversations → conversation
    "e",  # année → anné (clé interne seulement)
)


def _strip_agreement_suffix(word: str) -> tuple[str, str]:
    """Retourne (tronc, suffixe retiré) pour le groupement des formes."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            if suffix == "aux":
                return word[:-3] + "ail", suffix
            return word[: -len(suffix)], suffix
    return word, ""


def _is_accented(suffix: str) -> bool:
    return any(ch in suffix for ch in "éèêëàâîïôûùüç")


def build_lexicon(tsv_path: Path) -> list[str]:
    with open(tsv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        groups: dict[tuple[str, str, bool], dict[str, float]] = defaultdict(dict)
        for row in reader:
            form = (row.get("ortho") or "").strip().lower()
            lemma = (row.get("lemme") or "").strip().lower()
            if not form.isalpha() or not lemma.isalpha():
                continue  # formes apostrophées/tractées : hors accords simples
            freq = float(row.get("freqlivres") or 0) + float(row.get("freqfilms2") or 0)
            stem, suffix = _strip_agreement_suffix(form)
            key = (lemma, stem, _is_accented(suffix))
            if freq > groups[key].get(form, 0.0):
                groups[key][form] = freq

    lines: list[str] = []
    for forms in groups.values():
        if len(forms) < 2:
            continue  # famille monofome : rien à proposer (ex. « café »)
        ordered = sorted(forms, key=lambda f: (-forms[f], f))
        lines.append("\t".join(ordered))
    lines.sort()
    return lines


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    tsv_path = Path(argv[1])
    out_path = (
        Path(argv[2])
        if len(argv) > 2
        else Path("src/phenix_voice/resources/lexique_accords.tsv")
    )
    lines = build_lexicon(tsv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = out_path.stat().st_size
    print(f"{len(lines)} familles d'accord -> {out_path} ({size} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
