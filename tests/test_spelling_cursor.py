"""Insertion au curseur en mode épellation/correction + espaces conservés (14/11).

- `SpellingWindow.append_text` insère à la position ACTUELLE du curseur du
  champ (miroir en lecture seule compris) — fini le « tout part en fin » ;
- reconstruction pure `insert_chunk_at_cursor` : `_pending_correction_text`
  reste la source de vérité, la position de curseur UI est lue via
  `PhenixHUD.active_insert_position()` puis RESTAURÉE après réécriture ;
- les espaces ajoutés à la main survivent aux synchronisations (fini le
  `.strip()` destructeur du flux texte programme/humain).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from phenix_voice.main import PhenixVoiceController, insert_chunk_at_cursor
from phenix_voice.ui.hud import PhenixHUD, SpellingWindow


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# --- A1. SpellingWindow.append_text : insertion au curseur -------------------


def test_append_text_inserts_at_the_cursor(qapp) -> None:
    win = SpellingWindow()
    win.set_text("bonjour", cursor=3)  # curseur entre « bon » et « jour »
    win.append_text("X")
    assert win.spell_edit.text() == "bonXjour"
    # Le curseur suit juste après l'insertion (prochain chunk au bon endroit)
    assert win.spell_edit.cursorPosition() == 4


def test_append_text_honours_a_manually_clicked_cursor(qapp) -> None:
    win = SpellingWindow()
    win.set_text("mot")
    win.spell_edit.setCursorPosition(0)  # clic utilisateur en tête de champ
    win.append_text("!")
    assert win.spell_edit.text() == "!mot"
    assert win.spell_edit.cursorPosition() == 1


def test_append_text_works_in_the_read_only_mirror(qapp) -> None:
    # Mode épellation direct : le champ est en lecture seule (miroir), mais le
    # curseur y est déplaçable et l'insertion doit le respecter.
    win = SpellingWindow()
    win.open_window("mot", from_correction=False)
    assert win.spell_edit.isReadOnly()
    win.spell_edit.setCursorPosition(3)
    win.append_text(" ")
    assert win.spell_edit.text() == "mot "


def test_append_text_never_reenters_the_text_changed_callback(qapp) -> None:
    # Anti-récursion : les réécritures programme ne rappellent PAS
    # `on_text_changed` (→ `set_spelling_text_from_ui`) ; la saisie humaine, si.
    seen: list[str] = []
    win = SpellingWindow(on_text_changed=seen.append)
    win.set_text("abc", cursor=1)
    win.append_text("X")
    assert seen == []            # programme : aucun rappel
    assert win.spell_edit.text() == "aXbc"
    win.spell_edit.insert("Y")   # « humain » (hors drapeau programmatic)
    assert seen == ["aXYbc"]


def test_correction_mode_keeps_both_fields_in_sync_without_clobbering(qapp) -> None:
    # Depuis la correction : édition humaine dans le champ d'épellation →
    # miroir champ correction mis à jour, champ épellation NON réécrit.
    seen: list[str] = []
    win = SpellingWindow(on_text_changed=seen.append)
    win.open_window("mot", from_correction=True)
    win.spell_edit.insert(" x")   # saisie humaine
    assert seen == ["mot x"]      # le drapeau n'a pas bouclé, le texte humain est là
    assert win.spell_edit.text() == "mot x"


# --- A2. Reconstruction pure (source de vérité _pending_correction_text) -----


def test_insert_chunk_at_cursor_mid_text() -> None:
    assert insert_chunk_at_cursor("bonjour", "X", 3) == ("bonXjour", 4)


def test_insert_chunk_at_cursor_keeps_a_manual_trailing_space() -> None:
    # Espace ajouté à la main, puis souffle suivant : l'espace survit.
    assert insert_chunk_at_cursor("mot ", "s", 4) == ("mot s", 5)


def test_insert_chunk_at_cursor_clamps_out_of_range_positions() -> None:
    assert insert_chunk_at_cursor("mot", "X", 99) == ("motX", 4)   # fin
    assert insert_chunk_at_cursor("mot", "X", -5) == ("Xmot", 1)   # tête
    assert insert_chunk_at_cursor("", "mot", 0) == ("mot", 3)


# --- A3. Curseur actif lu par le thread STT (PhenixHUD) ----------------------


def _make_hud() -> PhenixHUD:
    def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    return PhenixHUD(
        on_toggle_mute=_noop,
        on_toggle_sleep=_noop,
        on_open_correction=_noop,
        on_oups_scratch=_noop,
        on_select_alternative=_noop,
        on_toggle_learn_mode=_noop,
        on_apply_manual_correction=_noop,
        on_toggle_help=_noop,
        on_quit=_noop,
    )


def test_active_insert_position_follows_the_spelling_cursor(qapp) -> None:
    hud = _make_hud()
    hud.show_spelling_window("bonjour", from_correction=True)
    assert hud.active_insert_position() == 7        # fin du pré-rempli (7 lettres)
    hud.spelling_window.spell_edit.setCursorPosition(3)
    assert hud.active_insert_position() == 3        # curseur cliqué
    # Réécriture du flux correction avec restauration explicite du curseur
    hud.set_spelling_text("bonjour!", cursor=4)
    assert hud.spelling_window.spell_edit.text() == "bonjour!"
    assert hud.spelling_window.spell_edit.cursorPosition() == 4
    assert hud.active_insert_position() == 4
    hud.hide_spelling_window()
    assert hud.active_insert_position() == 0        # épellation fermée → champ correction


def test_active_insert_position_falls_back_to_the_correction_field(qapp) -> None:
    hud = _make_hud()
    hud.show_correction_panel("mot", ["mot 2"], learn_enabled=True)
    hud.set_correction_edit_text("mot 2", cursor=3)
    assert hud.active_insert_position() == 3


def test_hud_append_spelling_text_inserts_at_the_cursor(qapp) -> None:
    hud = _make_hud()
    hud.show_spelling_window("", from_correction=False)
    hud.spelling_window.spell_edit.setCursorPosition(0)
    hud.append_spelling_text("ab")
    hud.spelling_window.spell_edit.setCursorPosition(1)
    hud.append_spelling_text("X")
    assert hud.spelling_window.spell_edit.text() == "aXb"


# --- B. Espaces ajoutés à la main : jamais détruits par un .strip() ----------


class _FakeHUD:
    """Double minimal du HUD : enregistre les réécritures de champs."""

    def __init__(self) -> None:
        self.spelling: list[tuple[str, int | None]] = []
        self.correction: list[tuple[str, int | None]] = []
        self.showed: list[tuple[str, bool]] = []

    def set_spelling_text(self, text: str, cursor: int | None = None) -> None:
        self.spelling.append((text, cursor))

    def set_correction_edit_text(self, text: str, cursor: int | None = None) -> None:
        self.correction.append((text, cursor))

    def show_spelling_window(self, prefill: str, from_correction: bool) -> None:
        self.showed.append((prefill, from_correction))


def test_manual_trailing_space_survives_the_next_breath() -> None:
    fake = SimpleNamespace(
        _correction_open=True,
        _pending_correction_text="",
        hud=_FakeHUD(),
    )
    # L'utilisateur ajoute un espace à la main entre deux mots épelés :
    PhenixVoiceController.set_spelling_text_from_ui(fake, "mot ")
    # …plus aucun .strip() destructeur : l'espace est la source de vérité…
    assert fake._pending_correction_text == "mot "
    assert fake.hud.correction == [("mot ", None)]   # miroir champ correction aussi
    # …et le souffle suivant s'insère APRÈS cet espace.
    assert insert_chunk_at_cursor(fake._pending_correction_text, "x", 4) == (
        "mot x",
        5,
    )


def test_manual_space_in_the_correction_field_is_not_stripped() -> None:
    fake = SimpleNamespace(
        _correction_open=True,
        _spelling_mode=True,
        _pending_correction_text="",
        hud=_FakeHUD(),
    )
    PhenixVoiceController.set_pending_correction_text(fake, "mot ")
    assert fake._pending_correction_text == "mot "
    assert fake.hud.spelling == [("mot ", None)]     # miroir épellation synchronisé


def test_enter_spelling_mode_prefill_keeps_manual_spaces() -> None:
    hud = _FakeHUD()
    fake = SimpleNamespace(
        _spelling_mode=False,
        _correction_open=True,
        _pending_correction_text="mot ",
        hud=hud,
        _spelling_casing=SimpleNamespace(reset=lambda: None),
        _spelling_from_correction=False,
        injection_logger=SimpleNamespace(log_action=lambda *_a, **_k: None),
    )
    PhenixVoiceController.enter_spelling_mode(fake)
    assert hud.showed == [("mot ", True)]            # pas de .strip() sur le pré-rempli
    assert fake._pending_correction_text == "mot "
    assert fake._spelling_from_correction is True


# --- C. Clics partagés + log de diagnostic (décision utilisateur 15/11) -----


def test_click_on_the_correction_field_while_spelling_is_open_is_not_ignored(
    qapp,
) -> None:
    # Les deux champs sont des MIROIRS du même `_pending_correction_text` :
    # un clic dans le champ Correction pendant l'épellation doit compter.
    hud = _make_hud()
    hud.show_correction_panel("mot", ["mot 2"], learn_enabled=True)
    hud.show_spelling_window("mot", from_correction=True)
    assert hud.active_insert_position() == 3        # curseur en fin, avant clic
    # Clic en tête du champ correction (x=1 px → 1re frontière de caractère)
    QTest.mouseClick(
        hud.correction_window.correction_edit,
        Qt.MouseButton.LeftButton,
        pos=QPoint(1, 5),
    )
    clicked = hud.correction_window.correction_edit.cursorPosition()
    assert clicked == 0                             # le clic est bien tombé dedans
    assert hud.active_insert_position() == clicked  # …et n'est plus ignoré


def test_click_on_spell_edit_drives_the_next_insertion(qapp) -> None:
    hud = _make_hud()
    hud.show_correction_panel("mot", ["mot 2"], learn_enabled=True)
    hud.show_spelling_window("mot", from_correction=True)
    assert hud.active_insert_position() == 3        # fin du pré-rempli
    QTest.mouseClick(
        hud.spelling_window.spell_edit,
        Qt.MouseButton.LeftButton,
        pos=QPoint(1, 10),
    )
    assert hud.spelling_window.spell_edit.cursorPosition() == 0
    assert hud.active_insert_position() == 0        # position partagée cohérente
    # Le prochain chunk s'insère BIEN à la position cliquée (pas en fin)
    text, cursor = insert_chunk_at_cursor(
        "mot", "X", hud.active_insert_position()
    )
    assert text == "Xmot"
    assert cursor == 1


def test_click_on_spell_edit_emits_edit_field_clicked(qapp) -> None:
    hud = _make_hud()
    spy = QSignalSpy(hud.signals.edit_field_clicked)
    hud.show_spelling_window("mot", from_correction=True)
    QTest.mouseClick(
        hud.spelling_window.spell_edit,
        Qt.MouseButton.LeftButton,
        pos=QPoint(1, 10),
    )
    assert spy.count() == 1                         # un seul log par clic
    assert list(spy.at(0)) == [
        "epellation",
        hud.spelling_window.spell_edit.cursorPosition(),
    ]


def test_click_on_the_spelling_window_title_logs_the_window(qapp) -> None:
    # Le titre est un QLabel : il n'accepte pas le clic et Qt le propage au
    # parent (la fenêtre) — le log doit le capter, une seule fois.
    hud = _make_hud()
    spy = QSignalSpy(hud.signals.edit_field_clicked)
    hud.show_spelling_window("mot", from_correction=True)
    QTest.mouseClick(
        hud.spelling_window.title_label,
        Qt.MouseButton.LeftButton,
        pos=QPoint(2, 5),
    )
    assert spy.count() == 1
    assert list(spy.at(0)) == ["fenetre_epellation", -1]


def test_spell_edit_is_the_first_widget_and_tall_enough(qapp) -> None:
    # Champ remonté EN HAUT du layout et agrandi 30 → 60 px (15/11) : cible
    # facile à viser avec un pointage imprécis.
    win = SpellingWindow()
    layout = win.layout()
    assert layout is not None
    first_item = layout.itemAt(0)
    assert first_item is not None
    assert first_item.widget() is win.spell_edit     # indice 0 = le champ
    assert win.spell_edit.minimumHeight() >= 60
