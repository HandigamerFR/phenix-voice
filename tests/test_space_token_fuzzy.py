"""Tolérance du jeton « espace » en mode épellation (bonus 14/11).

Le STT rate parfois « espace » : pluriel (« espaces »), faute de segmentation
(« espas ») ou jeton scindé (« es pace ») doivent produire un espace — mais
**jamais** un mot lointain (la famille « espace » / « space » reste la seule
acceptée, jetons de >= 5 lettres).
"""

from __future__ import annotations

from phenix_voice.postprocess.punctuation import text_to_nato_spelling


def test_espace_exact_rend_un_espace() -> None:
    assert text_to_nato_spelling("espace") == " "
    assert text_to_nato_spelling("space") == " "


def test_espace_pluriel_accepte() -> None:
    assert text_to_nato_spelling("espaces") == " "


def test_espace_faute_stt_espas_acceptee() -> None:
    # « espas » ≈ « espaces » (écart 2 : le « ce » du pluriel entendu en « s »)
    assert text_to_nato_spelling("espas") == " "


def test_espace_scinde_par_le_stt_accepte() -> None:
    # « es pace » est scindé en deux jetons par `split()` : la normalisation
    # multi-mots le reconstitue (même mécanique que « x ray » → « x-ray »).
    assert text_to_nato_spelling("es pace") == " "


def test_mots_lointains_ne_deviennent_jamais_un_espace() -> None:
    assert text_to_nato_spelling("voiture") == ""
    # Écart 2 de « espace » mais pas de « s » de pluriel → famille rejetée
    assert text_to_nato_spelling("espagne") == ""
    # Jeton trop court : aucune tolérance « raccourcie »
    assert text_to_nato_spelling("pace") == ""
    assert text_to_nato_spelling("un") == ""


def test_espace_fuzzy_s_insere_au_milieu_d_une_epellation() -> None:
    assert text_to_nato_spelling("alpha espaces bravo") == "a b"
    assert text_to_nato_spelling("alpha espas bravo") == "a b"
    # Le mot « espace » suivi d'un accent reste géré comme avant (régression)
    assert text_to_nato_spelling("espace accent aigu") == " é"
