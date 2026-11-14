"""Espace de liaison préservé à la correction du dernier segment (`replace_last`).

Principe de design vérifié ici :
- un texte de remplacement commençant par un signe (« ,il y a encore… ») ne
  doit JAMAIS être préfixé d'une espace forcée (typographie française, même
  règle que `adapt_chunk_to_context` via `NO_SPACE_BEFORE`) ;
- un texte commençant par une lettre/chiffre garde l'espace de l'ancien
  segment (comportement historique) ;
- ancien segment sans espace initial → aucun espace ajouté ;
- l'exclusion du saut de ligne (`\\n`) est conservée.

Aucune injection Win32 réelle : `_send_text` / `_send_backspaces` sont
neutralisés pour ne jamais envoyer de touches au clavier pendant les tests.
"""

from __future__ import annotations

from phenix_voice.os_control.shadow_buffer import ShadowBuffer


def _make_buffer(last_text: str) -> ShadowBuffer:
    """Buffer avec un dernier segment fictif et des envois clavier factices."""
    buffer = ShadowBuffer()
    buffer._send_text = lambda text: (len(text), {"send_path": "test"})
    buffer._send_backspaces = lambda count: {
        "backspace_count": count,
        "send_path": "test",
    }
    buffer.inject_and_record(last_text, raw_text=last_text.strip())
    return buffer


def test_replace_last_no_space_before_leading_symbol() -> None:
    # Ancien segment précédé d'une espace, remplacement commençant par « , »
    buffer = _make_buffer(" il y a encore un souci")
    _, new_seg = buffer.replace_last(",il y a encore un souci")
    assert new_seg is not None
    # PAS d'espace forcé avant la virgule
    assert new_seg.injected_text == ",il y a encore un souci"


def test_replace_last_keeps_space_for_letter() -> None:
    # Comportement historique inchangé : lettre en tête → espace préservé
    buffer = _make_buffer(" il y a un souci")
    _, new_seg = buffer.replace_last("il y a encore un souci")
    assert new_seg is not None
    assert new_seg.injected_text == " il y a encore un souci"


def test_replace_last_old_segment_without_initial_space() -> None:
    # Ancien segment sans espace initial → jamais d'espace ajouté
    buffer = _make_buffer("mot isolé")
    _, new_seg = buffer.replace_last(",suite")
    assert new_seg is not None
    assert new_seg.injected_text == ",suite"

    buffer2 = _make_buffer("mot isolé")
    _, new_seg2 = buffer2.replace_last("suite")
    assert new_seg2 is not None
    assert new_seg2.injected_text == "suite"


def test_replace_last_newline_exclusion_preserved() -> None:
    # Le saut de ligne n'est jamais préfixé d'une espace (exclusion conservée)
    buffer = _make_buffer(" il y a un souci")
    _, new_seg = buffer.replace_last("\nnouvelle ligne")
    assert new_seg is not None
    assert new_seg.injected_text == "\nnouvelle ligne"
