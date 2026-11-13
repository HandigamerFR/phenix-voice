"""Générateur d'alternatives de correction jusqu'à 9 choix (étape « 9 choix »).

Vérifie `stt/engine.py::build_alternatives` :
- substitutions unitaires d'abord (positions les plus ambiguës) ;
- puis combinaisons de DEUX substitutions pour remplir la grille 3×3 ;
- dédoublonnage insensible à la casse + exclusion du texte principal ;
- quota respecté.
"""

from __future__ import annotations

from phenix_voice.stt.engine import build_alternatives


def _fake_decode(vocab: dict[int, str]):
    def decode(seq: list[int]) -> str:
        return " ".join(vocab[t] for t in seq)

    return decode


def test_single_substitutions_first_then_pairs() -> None:
    # Tokens du texte principal : 10=mot 11=un 12=deux
    tokens = [10, 11, 12]
    # Seconds choix : (position, token_second, ratio)
    runner = [
        (0, 20, 0.50),  # -> "bonjour un deux"
        (1, 21, 0.40),  # -> "mot le deux"
        (2, 22, 0.30),  # -> "mot un monde"
    ]
    vocab = {10: "mot", 11: "un", 12: "deux", 20: "bonjour", 21: "le", 22: "monde"}
    alts = build_alternatives(tokens, runner, _fake_decode(vocab), "mot un deux", 9)

    # 3 substitutions unitaires + combinaisons de paires (3 paires distinctes)
    assert len(alts) == 6, f"attendu 6 (3 unitaires + 3 paires), obtenu {len(alts)}"
    # Les unitaires viennent d'abord, triées par ratio décroissant
    assert alts[0] == "bonjour un deux"
    assert alts[1] == "mot le deux"
    assert alts[2] == "mot un monde"
    # Paires présentes
    assert "bonjour le deux" in alts
    assert "bonjour un monde" in alts
    assert "mot le monde" in alts
    # Jamais le texte principal
    assert all(a.casefold() != "mot un deux" for a in alts)


def test_quota_nine_respected() -> None:
    tokens = [10, 11, 12, 13]
    runner = [
        (0, 20, 0.5),
        (1, 21, 0.4),
        (2, 22, 0.3),
        (3, 23, 0.2),
    ]
    vocab = {
        10: "a", 11: "b", 12: "c", 13: "d",
        20: "w", 21: "x", 22: "y", 23: "z",
    }
    alts = build_alternatives(tokens, runner, _fake_decode(vocab), "a b c d", 9)
    assert len(alts) <= 9, f"quota dépassé : {len(alts)}"
    assert len(alts) == len({a.casefold() for a in alts}), "doublons détectés"


def test_dedup_case_insensitive_and_main_excluded() -> None:
    tokens = [10, 11]
    # Deux substitutions qui donnent le même texte (casse différente)
    runner = [
        (0, 20, 0.5),
        (1, 20, 0.4),  # "mot bonjour" vs "bonjour un" — textes distincts
        (0, 21, 0.3),  # 21 décode identique à 20 -> doublon
    ]
    vocab = {10: "mot", 11: "un", 20: "BONJOUR", 21: "bonjour"}
    alts = build_alternatives(tokens, runner, _fake_decode(vocab), "mot un", 9)
    keys = [a.casefold() for a in alts]
    assert len(keys) == len(set(keys)), f"doublons : {alts}"
    assert "mot un" not in keys


def test_no_runner_ups_returns_empty() -> None:
    alts = build_alternatives([10, 11], [], _fake_decode({10: "a", 11: "b"}), "a b", 9)
    assert alts == []


def test_pairs_only_fill_when_singles_insufficient() -> None:
    # Un seul second choix : 1 unitaire + pas de paire possible (il faut 2 positions)
    tokens = [10, 11]
    runner = [(0, 20, 0.5)]
    vocab = {10: "mot", 11: "un", 20: "bonjour"}
    alts = build_alternatives(tokens, runner, _fake_decode(vocab), "mot un", 9)
    assert alts == ["bonjour un"]
