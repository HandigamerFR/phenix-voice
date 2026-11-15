"""Interface Phénix Voice PySide6 (Phase 2+) :
- Barre HUD flottante No-Focus : 3 états de micro (Actif / Veille vocale « Phénix repos » /
  Micro Coupé F8), transcription, popup de choix de symbole et aide « Que puis-je dire ? ».
- **Fenêtre de correction SÉPARÉE** (décision 12/11) : jusqu'à 9 alternatives
  (voix « Choisir un…neuf » ou clic), champ éditable, validation explicite
  (rien n'est inséré avant), séparation stricte « 🧠 Corriger & Apprendre » vs
  « 🛡️ Corriger SANS apprendre (Oups) » et ajout de forme orale personnelle.
- **Fenêtre d'ÉPELLATION SÉPARÉE** (décision 12/11) : n'écoute que lettres /
  chiffres / symboles / espace (restriction appliquée dans le routage de main.py) ;
  depuis la correction : champ pré-rempli et modifiable (rien inséré avant validation) ;
  hors correction : texte épelé inséré directement dans l'éditeur cible.
"""

from __future__ import annotations

import ctypes
from enum import Enum
from typing import Callable
from PySide6.QtCore import QEvent, QPoint, Qt, Signal, QObject
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

user32 = ctypes.WinDLL("user32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080


class MicState(str, Enum):
    """États visuels du microphone et du moteur."""

    LOADING = "loading"
    LISTENING = "listening"
    SPEAKING = "speaking"
    TRANSCRIBING = "transcribing"
    SLEEPING = "sleeping"
    MUTED = "muted"


STATE_STYLE_MAP: dict[MicState, tuple[str, str, str]] = {
    MicState.LOADING: (
        "#475569",
        "⏳ Chargement GPU AMD...",
        "Initialisation de Whisper Large-v3-Turbo (DirectML FP16)...",
    ),
    MicState.LISTENING: (
        "#16a34a",
        "🟢 ÉCOUTE ACTIVE",
        "Dictez librement — « Corriger ça », « Effacer ça », « Presser Entrée », « Couper Phénix »",
    ),
    MicState.SPEAKING: (
        "#2563eb",
        "🔵 PAROLE DÉTECTÉE...",
        "Acquisition du souffle en cours...",
    ),
    MicState.TRANSCRIBING: (
        "#9333ea",
        "🟣 TRANSCRIPTION GPU...",
        "Inférence DirectML sur AMD Radeon RX 5700 XT...",
    ),
    MicState.SLEEPING: (
        "#d97706",
        "🟠 VEILLE (« Phénix repos »)",
        "Dites « Phénix écoute » ou appuyez sur F8/F9 pour reprendre la dictée",
    ),
    MicState.MUTED: (
        "#dc2626",
        "🔴 MICRO COUPÉ (OFF)",
        "Micro totalement coupé — Appuyez sur [F8] ou cliquez sur [🔌 Micro F8] pour rallumer",
    ),
}


class HUDSignals(QObject):
    """Signaux thread-safe pour piloter le HUD depuis les threads d'arrière-plan."""

    state_changed = Signal(str)
    transcript_ready = Signal(str, float, str)
    correction_opened = Signal(str, list, bool)  # (target_text, alternatives, learn_mode)
    correction_closed = Signal()
    # texte dicté proposé pendant correction (sans application auto) ;
    # int = position du curseur après réécriture, -1 = conserver la position actuelle
    correction_edit_text_set = Signal(str, int)
    spelling_opened = Signal(str, bool)  # (texte pré-rempli, ouvert_depuis_la_correction)
    spelling_closed = Signal()
    # miroir complet du texte en attente (mode correction) ; int = curseur, -1 = conserver
    spelling_text_set = Signal(str, int)
    spelling_text_append = Signal(str)  # chunk épelé ajouté (insertion directe hors correction)
    help_toggled = Signal(str, bool)  # (help_text, visible)
    symbol_choice_requested = Signal(str, list)  # (forme dictée, libellés des choix 1/2)
    symbol_choice_hidden = Signal()
    # Clic diagnostique sur un champ/fenêtre (correction ou épellation) :
    # (« epellation » | « correction » | « fenetre_epellation » |
    # « fenetre_correction », position curseur ou -1 si non concerné)
    edit_field_clicked = Signal(str, int)


class CorrectionWindow(QWidget):
    """Fenêtre de correction SÉPARÉE de la barre HUD (décision utilisateur 12/11).

    - Jusqu'à **9 alternatives** (voix « Choisir un…neuf » ou clic, grille 3×3).
    - Tout choix n'est qu'une **PROPOSITION dans le champ** : rien n'est inséré
      dans le texte avant validation explicite (« Valider la correction » ou
      [Appliquer la correction]) — l'utilisateur a toujours le droit de
      changer d'avis ou de s'être trompé.
    - Mode 🧠 Corriger & Apprendre / 🛡️ SANS apprendre, édition manuelle,
      ajout de forme orale personnelle (« 🔑 + Forme orale »).
    """

    def __init__(
        self,
        on_select_alternative: Callable[[int], None],
        on_toggle_learn_mode: Callable[[], None],
        on_apply_manual_correction: Callable[[str], None],
        on_correction_text_changed: Callable[[str], None] | None,
        on_add_spoken_form: Callable[[str], None] | None,
        on_close: Callable[[], None] | None,
        on_enter_spelling: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.on_select_alternative = on_select_alternative
        self.on_toggle_learn_mode = on_toggle_learn_mode
        self.on_apply_manual_correction = on_apply_manual_correction
        self.on_correction_text_changed = on_correction_text_changed
        self.on_add_spoken_form = on_add_spoken_form
        self.on_close = on_close
        self.on_enter_spelling = on_enter_spelling
        self._programmatic_edit = False
        self._positioned_once = False

        self.setWindowTitle("Phénix Voice — Correction")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        # Ouvrir la fenêtre ne vole pas le focus de l'utilisateur ; un clic dans
        # le champ suffit pour saisir du texte (focus restauré avant injection).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(780)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background-color: #0f172a; }
            QLabel { color: #f8fafc; }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #94a3b8;
            }
            QPushButton#altBtn {
                background-color: #0f172a;
                border: 1px solid #38bdf8;
                color: #e0f2fe;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton#altBtn:hover {
                background-color: #0284c7;
                color: white;
            }
            QPushButton#applyBtn {
                background-color: #14532d;
                border-color: #22c55e;
                color: #dcfce7;
            }
            QPushButton#helpBtn {
                background-color: #312e81;
                border-color: #6366f1;
                color: #e0e7ff;
            }
            QPushButton#quitBtn {
                background-color: #2a1818;
                border-color: #7f1d1d;
                color: #fecaca;
                padding: 5px 9px;
            }
            QLineEdit#corrEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # Ligne 1 : titre + mode apprendre + fermer
        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_label = QLabel("✏️ Correction")
        self.title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #38bdf8;")
        self.title_label.setWordWrap(True)
        header.addWidget(self.title_label, stretch=1)

        self.learn_mode_btn = QPushButton("🧠 Mode : Corriger & Apprendre")
        self.learn_mode_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.learn_mode_btn.clicked.connect(self.on_toggle_learn_mode)
        header.addWidget(self.learn_mode_btn)

        self.spelling_btn = QPushButton("🔤 Épellation")
        self.spelling_btn.setObjectName("helpBtn")
        self.spelling_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.spelling_btn.setToolTip(
            "Ouvrir la fenêtre d'épellation dédiée (alphabet radio : Alpha, Bravo…), "
            "pré-remplie avec le texte à corriger."
        )
        if self.on_enter_spelling is not None:
            self.spelling_btn.clicked.connect(self.on_enter_spelling)
        header.addWidget(self.spelling_btn)

        self.close_btn = QPushButton("✕ Fermer")
        self.close_btn.setObjectName("quitBtn")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(self._request_close)
        header.addWidget(self.close_btn)
        outer.addLayout(header)

        # Ligne 2 : grille de jusqu'à 9 alternatives (voix « Choisir un…neuf » ou clic)
        self.alt_grid = QGridLayout()
        self.alt_grid.setSpacing(8)
        self.alt_buttons: list[QPushButton] = []
        for idx in range(9):
            btn = QPushButton("---")
            btn.setObjectName("altBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda _=False, i=idx + 1: self.on_select_alternative(i))
            self.alt_grid.addWidget(btn, idx // 3, idx % 3)
            self.alt_buttons.append(btn)
        outer.addLayout(self.alt_grid)

        # Ligne 2bis : signal explicite du nombre de choix réellement trouvés
        # (exigé : si le système ne trouve pas neuf alternatives, il doit le dire).
        self.alt_count_label = QLabel("")
        self.alt_count_label.setFont(QFont("Segoe UI", 8))
        self.alt_count_label.setWordWrap(True)
        outer.addWidget(self.alt_count_label)

        # Ligne 3 : champ éditable + validation + forme orale
        manual_row = QHBoxLayout()
        manual_row.setSpacing(8)
        self.correction_edit = QLineEdit()
        self.correction_edit.setObjectName("corrEdit")
        self.correction_edit.setPlaceholderText("Modifiez ici le texte à corriger...")
        self.correction_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.correction_edit.textChanged.connect(self._on_correction_text_changed)
        manual_row.addWidget(self.correction_edit, stretch=1)

        self.apply_edit_btn = QPushButton("✅ Appliquer la correction")
        self.apply_edit_btn.setObjectName("applyBtn")
        self.apply_edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_edit_btn.clicked.connect(self._on_apply_manual_clicked)
        manual_row.addWidget(self.apply_edit_btn)

        self.add_form_btn = QPushButton("🔑 + Forme orale")
        self.add_form_btn.setObjectName("helpBtn")
        self.add_form_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_form_btn.setToolTip(
            "Ajouter une forme orale personnelle : le segment dicté sera écrit "
            "comme le texte du champ (dictionnaire personnel)."
        )
        self.add_form_btn.clicked.connect(self._on_add_spoken_form_clicked)
        manual_row.addWidget(self.add_form_btn)
        outer.addLayout(manual_row)

        # Ligne 4 : rappel de la règle « rien sans validation »
        self.hint_label = QLabel(
            "💡 Rien n'est inséré avant validation : un choix (voix « Choisir un…neuf » ou clic) "
            "va dans le champ, puis validez avec [Appliquer la correction] ou « Valider la correction ». "
            "Vous pouvez toujours changer d'avis, modifier le champ à la main, ou re-dicter la phrase."
        )
        self.hint_label.setFont(QFont("Segoe UI", 8))
        self.hint_label.setStyleSheet("color: #94a3b8;")
        self.hint_label.setWordWrap(True)
        outer.addWidget(self.hint_label)

    # --- API appelée par les signaux du HUD (thread GUI uniquement) -----------

    def open_panel(
        self, target_text: str, alternatives: list[str], learn_enabled: bool
    ) -> None:
        clean_target = target_text.strip()
        count = sum(1 for a in alternatives if a and a.strip())
        self.title_label.setText(
            f"✏️ Corriger « {clean_target} » — choisissez 1…{max(count, 1)} "
            "(proposition dans le champ, rien inséré avant validation) :"
        )
        # Signal « moins de neuf choix » : on dit explicitement combien il y en a.
        if count >= 9:
            self.alt_count_label.setText("✅ 9/9 choix disponibles")
            self.alt_count_label.setStyleSheet("color: #4ade80;")
        elif count > 0:
            self.alt_count_label.setText(
                f"⚠️ {count}/9 choix seulement — le système n'a pas trouvé "
                "plus d'alternatives pour ce souffle."
            )
            self.alt_count_label.setStyleSheet("color: #fbbf24;")
        else:
            self.alt_count_label.setText(
                "❌ 0/9 choix — aucune alternative trouvée : modifiez le champ "
                "à la main ou re-dictez la phrase."
            )
            self.alt_count_label.setStyleSheet("color: #f87171;")
        self._programmatic_edit = True
        try:
            self.correction_edit.setText(clean_target)
            # Curseur en FIN de proposition (comportement historique `setText`)
            self.correction_edit.setCursorPosition(len(clean_target))
        finally:
            self._programmatic_edit = False

        if learn_enabled:
            self.learn_mode_btn.setText("🧠 Mode : Corriger & Apprendre")
            self.learn_mode_btn.setStyleSheet(
                "background-color: #14532d; border-color: #22c55e; color: #dcfce7;"
            )
        else:
            self.learn_mode_btn.setText("🛡️ Mode : SANS Apprendre")
            self.learn_mode_btn.setStyleSheet(
                "background-color: #7c2d12; border-color: #f97316; color: #ffedd5;"
            )

        fm = self.correction_edit.fontMetrics()
        for i, btn in enumerate(self.alt_buttons):
            if i < len(alternatives) and alternatives[i].strip():
                full = alternatives[i].strip()
                # Libellé tronqué au milieu + texte complet en infobulle
                btn.setText(f"{i + 1}. " + fm.elidedText(full, Qt.TextElideMode.ElideMiddle, 360))
                btn.setToolTip(full)
                btn.setVisible(True)
            else:
                btn.setVisible(False)

        if not self.isVisible():
            self._ensure_position()
            self.show()
        self.raise_()

    def set_edit_text(self, text: str, cursor: int | None = None) -> None:
        """Propose un texte dans le champ (sans insertion automatique).

        `cursor` : position explicite du curseur après réécriture ; `None` =
        conserver la position actuelle du champ (rognée à la longueur du texte)
        — les espaces saisis à la main ne sont PAS rognés (seuls les retours à
        la ligne résiduels le sont, le champ est monoligne).
        """
        clean = text.strip("\r\n")
        self._programmatic_edit = True
        try:
            if cursor is None:
                cursor = min(self.correction_edit.cursorPosition(), len(clean))
            self.correction_edit.setText(clean)
            self.correction_edit.setCursorPosition(max(0, cursor))
        finally:
            self._programmatic_edit = False

    def close_panel(self) -> None:
        self.hide()
        self._programmatic_edit = True
        try:
            self.correction_edit.clear()
        finally:
            self._programmatic_edit = False

    # --- Événements internes --------------------------------------------------

    def _ensure_position(self) -> None:
        if self._positioned_once:
            return
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.adjustSize()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 150  # sous la barre HUD
            self.move(x, y)
        self._positioned_once = True

    def _request_close(self) -> None:
        if self.on_close:
            self.on_close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Fermer la fenêtre (✕ ou titre) = annuler la correction en cours :
        # rien n'a été inséré, l'utilisateur change simplement d'avis.
        if self.on_close:
            self.on_close()
        super().closeEvent(event)

    def _on_correction_text_changed(self, text: str) -> None:
        if self._programmatic_edit:
            return
        if self.on_correction_text_changed:
            self.on_correction_text_changed(text)

    def _on_apply_manual_clicked(self) -> None:
        text = self.correction_edit.text().strip()
        if text:
            self.on_apply_manual_correction(text)

    def _on_add_spoken_form_clicked(self) -> None:
        if self.on_add_spoken_form:
            self.on_add_spoken_form(self.correction_edit.text())


class SpellingWindow(QWidget):
    """Fenêtre d'ÉPELLATION SÉPARÉE de la barre HUD (décision utilisateur 12/11).

    - N'écoute **que** les lettres / chiffres / symboles / **[espace]** (alphabet
      radio) + la commande de sortie — la restriction d'intentions est appliquée
      dans le routage de `main.py`.
    - **Depuis la correction** : champ **pré-rempli avec le texte du souffle
      corrigé, modifiable** ; les lettres dictées s'ajoutent au texte, mais
      **rien n'est inséré dans l'éditeur avant validation explicite**
      (« Valider la correction » / [Appliquer la correction]).
    - **Hors correction** : le texte épelé est inséré **directement dans
      l'éditeur cible** jusqu'à la sortie (« Fin épellation » /
      « Passer en mode dictée » / ✕) ; le champ sert de miroir en lecture seule.
    - **Décision 15/11** : le champ est **remonté en haut** du layout et
      **agrandi (30 → 60 px)** — l'utilisateur corrige avec un pointage
      souris imprécis et ratait la petite cible ; titre/boutons passent après.
    """

    def __init__(
        self,
        on_text_changed: Callable[[str], None] | None = None,
        on_apply: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.on_text_changed = on_text_changed
        self.on_apply = on_apply
        self.on_close = on_close
        self._from_correction = False
        self._programmatic_edit = False
        self._positioned_once = False

        self.setWindowTitle("Phénix Voice — Épellation")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        # Ouvrir la fenêtre ne vole pas le focus de l'utilisateur (dictée continue).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(720)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background-color: #0f172a; }
            QLabel { color: #f8fafc; }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #94a3b8;
            }
            QPushButton#applyBtn {
                background-color: #14532d;
                border-color: #22c55e;
                color: #dcfce7;
            }
            QPushButton#quitBtn {
                background-color: #2a1818;
                border-color: #7f1d1d;
                color: #fecaca;
                padding: 5px 9px;
            }
            QLineEdit#spellEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #a78bfa;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
            }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # Ligne 1 (décision 15/11) : le CHAMP passe EN HAUT, agrandi de 30 à
        # 60 px — l'utilisateur corrige avec un pointage souris imprécis et
        # ratait régulièrement la petite cible ; titre/vider/fermer passent
        # ensuite, puis validation et rappel des règles.
        self.spell_edit = QLineEdit()
        self.spell_edit.setObjectName("spellEdit")
        self.spell_edit.setPlaceholderText(
            "Mode dictée : le texte épelé s'écrit directement dans l'éditeur (miroir ici)."
        )
        self.spell_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Cible facile à viser : 60 px de haut (était 30 px en fenêtre de 192 px).
        self.spell_edit.setMinimumHeight(60)
        self.spell_edit.textChanged.connect(self._on_text_changed)
        outer.addWidget(self.spell_edit)

        # Ligne 2 : titre + vider + fermer
        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_label = QLabel("🔤 Épellation")
        self.title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #a78bfa;")
        self.title_label.setWordWrap(True)
        header.addWidget(self.title_label, stretch=1)

        self.clear_btn = QPushButton("🗑 Vider")
        self.clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_btn.setToolTip(
            "Vider le champ (le texte déjà inséré dans l'éditeur n'est pas touché)."
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        header.addWidget(self.clear_btn)

        self.close_btn = QPushButton("✕ Fin épellation")
        self.close_btn.setObjectName("quitBtn")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(self._request_close)
        header.addWidget(self.close_btn)
        outer.addLayout(header)

        # Ligne 3 : validation (uniquement depuis la correction)
        self.apply_btn = QPushButton("✅ Appliquer la correction")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        outer.addWidget(self.apply_btn)

        # Ligne 4 : rappel des règles
        self.hint_label = QLabel("")
        self.hint_label.setFont(QFont("Segoe UI", 8))
        self.hint_label.setStyleSheet("color: #94a3b8;")
        self.hint_label.setWordWrap(True)
        outer.addWidget(self.hint_label)

    # --- API appelée par les signaux du HUD (thread GUI uniquement) -----------

    def open_window(self, prefill: str, from_correction: bool) -> None:
        self._from_correction = from_correction
        # Curseur en FIN du pré-rempli : le premier chunk épelé s'ajoute à la suite.
        self._set_text_programmatic(prefill, cursor=len(prefill))
        if from_correction:
            self.title_label.setText(
                "🔤 Épellation — depuis la correction (Alpha, Bravo… ; les lettres "
                "s'ajoutent au texte, rien inséré avant validation) :"
            )
            self.spell_edit.setReadOnly(False)
            self.apply_btn.setVisible(True)
            self.hint_label.setText(
                "💡 Depuis la correction : éppez avec l'alphabet radio (Alpha, Bravo, "
                "« chiffre 5 », « espace », symboles…). Le texte s'ajoute au champ, "
                "rien n'est inséré avant [Appliquer la correction] ou "
                "« Valider la correction ». Vous pouvez aussi modifier le champ à la main."
            )
        else:
            self.title_label.setText(
                "🔤 Épellation — texte inséré directement dans l'éditeur "
                "(Alpha, Bravo… ; sortie : « Fin épellation » / « Passer en mode dictée »)"
            )
            self.spell_edit.setReadOnly(True)
            self.apply_btn.setVisible(False)
            self.hint_label.setText(
                "💡 Hors correction : chaque lettre/chiffre/symbole dicté est inséré "
                "directement dans l'éditeur cible ; ce champ est un simple miroir. "
                "Dites « Fin épellation » ou « Passer en mode dictée » (ou cliquez ✕) "
                "pour revenir à la dictée normale."
            )

        if not self.isVisible():
            self._ensure_position()
            self.show()
        self.raise_()

    def set_text(self, text: str, cursor: int | None = None) -> None:
        """Miroir du texte en attente (mode correction).

        `cursor` = position explicite du curseur après réécriture (le flux
        correction s'en sert pour RESTAURER le curseur juste après une
        insertion) ; `None` = conserver la position actuelle du champ.
        """
        self._set_text_programmatic(text, cursor)

    def append_text(self, chunk: str) -> None:
        """Insère un chunk épelé à la position ACTUELLE du curseur du champ.

        L'utilisateur peut avoir cliqué n'importe où dans le champ : le texte
        ne doit pas partir en fin. `QLineEdit.insert()` fonctionne aussi sur le
        miroir en lecture seule (seule la saisie humaine y est bloquée), et le
        drapeau `_programmatic_edit` évite de re-boucler vers `on_text_changed`.
        """
        if not chunk:
            return
        self._programmatic_edit = True
        try:
            self.spell_edit.insert(chunk)
        finally:
            self._programmatic_edit = False

    def close_window(self) -> None:
        self.hide()
        self._set_text_programmatic("")
        self._from_correction = False

    # --- Événements internes --------------------------------------------------

    def _set_text_programmatic(self, text: str, cursor: int | None = None) -> None:
        """Réécrit le champ SANS déclencher `on_text_changed` (anti-récursion).

        `cursor=None` conserve la position actuelle du curseur (rognée à la
        nouvelle longueur) ; sinon le curseur est placé explicitement.
        """
        self._programmatic_edit = True
        try:
            if cursor is None:
                cursor = min(self.spell_edit.cursorPosition(), len(text))
            self.spell_edit.setText(text)
            self.spell_edit.setCursorPosition(max(0, cursor))
        finally:
            self._programmatic_edit = False

    def _ensure_position(self) -> None:
        if self._positioned_once:
            return
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.adjustSize()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 150
            self.move(x, y)
        self._positioned_once = True

    def _request_close(self) -> None:
        if self.on_close:
            self.on_close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Fermer la fenêtre (✕ ou titre) = sortir du mode épellation.
        if self.on_close:
            self.on_close()
        super().closeEvent(event)

    def _on_text_changed(self, text: str) -> None:
        if self._programmatic_edit:
            return
        if self.on_text_changed:
            self.on_text_changed(text)

    def _on_clear_clicked(self) -> None:
        self._set_text_programmatic("")
        if self._from_correction and self.on_text_changed:
            self.on_text_changed("")

    def _on_apply_clicked(self) -> None:
        text = self.spell_edit.text().strip()
        if text and self.on_apply:
            self.on_apply(text)


class PhenixHUD(QWidget):
    """Barre flottante toujours au premier plan (No-Focus / WS_EX_NOACTIVATE)
    pour ne jamais voler le curseur de la fenêtre cible.
    La correction vit dans une fenêtre SÉPARÉE (`CorrectionWindow`).
    """

    def __init__(
        self,
        on_toggle_mute: Callable[[], None],
        on_toggle_sleep: Callable[[], None],
        on_open_correction: Callable[[], None],
        on_oups_scratch: Callable[[], None],
        on_select_alternative: Callable[[int], None],
        on_toggle_learn_mode: Callable[[], None],
        on_apply_manual_correction: Callable[[str], None],
        on_toggle_help: Callable[[], None],
        on_quit: Callable[[], None],
        on_correction_text_changed: Callable[[str], None] | None = None,
        on_add_spoken_form: Callable[[str], None] | None = None,
        on_close_correction: Callable[[], None] | None = None,
        on_enter_spelling: Callable[[], None] | None = None,
        on_spelling_text_changed: Callable[[str], None] | None = None,
        on_close_spelling: Callable[[], None] | None = None,
        on_edit_field_clicked: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.on_toggle_mute = on_toggle_mute
        self.on_toggle_sleep = on_toggle_sleep
        self.on_open_correction = on_open_correction
        self.on_oups_scratch = on_oups_scratch
        self.on_select_alternative = on_select_alternative
        self.on_toggle_learn_mode = on_toggle_learn_mode
        self.on_apply_manual_correction = on_apply_manual_correction
        self.on_toggle_help = on_toggle_help
        self.on_quit = on_quit
        self.on_correction_text_changed = on_correction_text_changed
        self.on_add_spoken_form = on_add_spoken_form
        self._drag_offset: QPoint | None = None
        self._is_noactivate = True

        self.signals = HUDSignals()
        self.signals.state_changed.connect(self._apply_state_slot)
        self.signals.transcript_ready.connect(self._apply_transcript_slot)
        self.signals.correction_opened.connect(self._apply_open_correction_slot)
        self.signals.correction_closed.connect(self._apply_close_correction_slot)
        self.signals.correction_edit_text_set.connect(self._apply_correction_edit_text_slot)
        self.signals.spelling_opened.connect(self._apply_spelling_opened_slot)
        self.signals.spelling_closed.connect(self._apply_spelling_closed_slot)
        self.signals.spelling_text_set.connect(self._apply_spelling_text_set_slot)
        self.signals.spelling_text_append.connect(self._apply_spelling_append_slot)
        self.signals.help_toggled.connect(self._apply_help_slot)
        self.signals.symbol_choice_requested.connect(self._apply_symbol_choice_slot)
        self.signals.symbol_choice_hidden.connect(self._apply_symbol_choice_hidden_slot)
        # Clic diagnostique sur un champ/fenêtre (log distance, décision 15/11)
        if on_edit_field_clicked is not None:
            self.signals.edit_field_clicked.connect(on_edit_field_clicked)

        # Fenêtre de correction SÉPARÉE (jusqu'à 9 alternatives + validation)
        self.correction_window = CorrectionWindow(
            on_select_alternative=on_select_alternative,
            on_toggle_learn_mode=on_toggle_learn_mode,
            on_apply_manual_correction=on_apply_manual_correction,
            on_correction_text_changed=on_correction_text_changed,
            on_add_spoken_form=on_add_spoken_form,
            on_close=on_close_correction,
            on_enter_spelling=on_enter_spelling,
        )

        # Fenêtre d'ÉPELLATION SÉPARÉE (lettres / chiffres / symboles / espace)
        self.spelling_window = SpellingWindow(
            on_text_changed=on_spelling_text_changed,
            on_apply=on_apply_manual_correction,
            on_close=on_close_spelling,
        )

        # Curseurs des deux champs éditables : écrits EN THREAD GUI par
        # `cursorPositionChanged`, lus par le thread STT via
        # `active_insert_position()` pour l'insertion au curseur en mode
        # épellation (jamais d'accès direct aux widgets depuis le worker).
        # Les deux champs sont des MIROIRS du même texte en attente :
        # `_shared_insert_pos` retient le dernier champ TOUCHÉ (clic ou
        # réécriture programmatique) — le dernier touché fait foi.
        self._spelling_cursor_pos = 0
        self._correction_cursor_pos = 0
        self._shared_insert_pos: int | None = None
        self._spelling_window_active = False
        self.spelling_window.spell_edit.cursorPositionChanged.connect(
            self._on_spelling_cursor_moved
        )
        self.correction_window.correction_edit.cursorPositionChanged.connect(
            self._on_correction_cursor_moved
        )

        # Journalisation de chaque clic (widget visé + position) pour
        # diagnostiquer à distance les clics ratés sur la cible (15/11).
        # `eventFilter` renvoie TOUJOURS False : aucun événement n'est absorbé.
        self.spelling_window.spell_edit.installEventFilter(self)
        self.correction_window.correction_edit.installEventFilter(self)
        self.spelling_window.installEventFilter(self)
        self.correction_window.installEventFilter(self)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._build_ui()
        self._position_top_center()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._enforce_win32_noactivate()

    def _enforce_win32_noactivate(self) -> None:
        hwnd = int(self.winId())
        if hwnd:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self._is_noactivate:
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    ex_style | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
                )
            else:
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    (ex_style & ~WS_EX_NOACTIVATE) | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
                )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.card = QFrame(self)
        self.card.setObjectName("hudCard")
        self.card.setStyleSheet(
            """
            QFrame#hudCard {
                background-color: rgba(15, 23, 42, 242);
                border: 1.5px solid #334155;
                border-radius: 12px;
            }
            QFrame#corrFrame {
                background-color: #1e293b;
                border: 1px solid #38bdf8;
                border-radius: 9px;
            }
            QFrame#helpFrame {
                background-color: #0f172a;
                border: 1px solid #64748b;
                border-radius: 9px;
            }
            QLabel {
                color: #f8fafc;
            }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #94a3b8;
            }
            QPushButton#muteBtn {
                background-color: #1e3a8a;
                border-color: #3b82f6;
            }
            QPushButton#corrBtn {
                background-color: #0f3d3e;
                border-color: #14b8a6;
                color: #99f6e4;
            }
            QPushButton#helpBtn {
                background-color: #312e81;
                border-color: #6366f1;
                color: #e0e7ff;
            }
            QPushButton#scratchBtn {
                background-color: #3b1d2e;
                border-color: #9d174d;
                color: #fbcfe8;
            }
            QPushButton#altBtn {
                background-color: #0f172a;
                border-color: #38bdf8;
                color: #e0f2fe;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton#altBtn:hover {
                background-color: #0284c7;
                color: white;
            }
            QPushButton#applyBtn {
                background-color: #14532d;
                border-color: #22c55e;
                color: #dcfce7;
            }
            QPushButton#quitBtn {
                background-color: #2a1818;
                border-color: #7f1d1d;
                color: #fecaca;
                padding: 5px 9px;
            }
            QLineEdit#corrEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            """
        )

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(6)

        # Ligne 1 : Badge + Latence + Boutons de contrôle sans perte de focus
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.status_badge = QLabel("⏳ Initialisation...")
        self.status_badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_badge.setStyleSheet(
            "background-color: #475569; color: white; padding: 4px 10px; border-radius: 6px;"
        )
        top_row.addWidget(self.status_badge)

        self.latency_label = QLabel("GPU : AMD Radeon RX 5700 XT")
        self.latency_label.setFont(QFont("Segoe UI", 9))
        self.latency_label.setStyleSheet("color: #94a3b8;")
        top_row.addWidget(self.latency_label, stretch=1)

        self.mute_btn = QPushButton("🔌 Micro ON/OFF (F8)")
        self.mute_btn.setObjectName("muteBtn")
        self.mute_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mute_btn.clicked.connect(self.on_toggle_mute)
        top_row.addWidget(self.mute_btn)

        self.sleep_btn = QPushButton("🟠 Veille (F9)")
        self.sleep_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sleep_btn.clicked.connect(self.on_toggle_sleep)
        top_row.addWidget(self.sleep_btn)

        self.help_btn = QPushButton("❓ Que puis-je dire ?")
        self.help_btn.setObjectName("helpBtn")
        self.help_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.help_btn.clicked.connect(self.on_toggle_help)
        top_row.addWidget(self.help_btn)

        self.corr_btn = QPushButton("✏️ Corriger ça")
        self.corr_btn.setObjectName("corrBtn")
        self.corr_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.corr_btn.clicked.connect(self.on_open_correction)
        top_row.addWidget(self.corr_btn)

        self.scratch_btn = QPushButton("🛡️ Sans apprendre / Effacer")
        self.scratch_btn.setObjectName("scratchBtn")
        self.scratch_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scratch_btn.clicked.connect(self.on_oups_scratch)
        top_row.addWidget(self.scratch_btn)

        self.quit_btn = QPushButton("✕")
        self.quit_btn.setObjectName("quitBtn")
        self.quit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.quit_btn.clicked.connect(self.on_quit)
        top_row.addWidget(self.quit_btn)

        card_layout.addLayout(top_row)

        # Ligne 2 : Dernière phrase transcrite
        self.transcript_label = QLabel("Initialisation du modèle vocal local...")
        self.transcript_label.setFont(QFont("Segoe UI", 10))
        self.transcript_label.setStyleSheet("color: #cbd5e1;")
        self.transcript_label.setWordWrap(False)
        card_layout.addWidget(self.transcript_label)

        # Ligne 3 (repliée par défaut) : popup de choix de symbole (formes orales ambiguës)
        self.symbol_frame = QFrame(self.card)
        self.symbol_frame.setObjectName("corrFrame")
        symbol_layout = QVBoxLayout(self.symbol_frame)
        symbol_layout.setContentsMargins(10, 8, 10, 8)
        symbol_layout.setSpacing(6)

        self.symbol_title_label = QLabel("")
        self.symbol_title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.symbol_title_label.setStyleSheet("color: #fbbf24;")
        symbol_layout.addWidget(self.symbol_title_label)

        self.symbol_btn_row = QHBoxLayout()
        self.symbol_btn_row.setSpacing(8)
        self.symbol_buttons: list[QPushButton] = []
        symbol_layout.addLayout(self.symbol_btn_row)

        self.symbol_close_btn = QPushButton("✕ Garder tel quel (symbole)")
        self.symbol_close_btn.setObjectName("quitBtn")
        self.symbol_close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.symbol_close_btn.clicked.connect(self.hide_symbol_choice)
        symbol_layout.addWidget(self.symbol_close_btn)

        self.symbol_frame.setVisible(False)
        card_layout.addWidget(self.symbol_frame)

        # Ligne 4 (repliée par défaut) : Panneau « Que puis-je dire ? »
        self.help_frame = QFrame(self.card)
        self.help_frame.setObjectName("helpFrame")
        help_layout = QVBoxLayout(self.help_frame)
        help_layout.setContentsMargins(10, 8, 10, 8)
        self.help_label = QLabel("")
        self.help_label.setFont(QFont("Segoe UI", 9))
        self.help_label.setStyleSheet("color: #e2e8f0;")
        self.help_label.setWordWrap(True)
        self.help_label.setTextFormat(Qt.TextFormat.RichText)
        help_layout.addWidget(self.help_label)
        self.help_frame.setVisible(False)
        card_layout.addWidget(self.help_frame)

        outer.addWidget(self.card)
        # Barre élargie (remarque 12/11) : le bouton « 🛡️ Sans apprendre / Effacer »
        # doit afficher tout son texte sans troncature.
        self.setFixedWidth(1240)

    def _position_top_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 12
            self.move(x, y)

    def set_state(self, state: MicState) -> None:
        self.signals.state_changed.emit(state.value)

    def set_transcript(
        self, text: str, latency_ms: float, alternatives_info: str = ""
    ) -> None:
        self.signals.transcript_ready.emit(text, latency_ms, alternatives_info)

    def show_correction_panel(
        self, target_text: str, alternatives: list[str], learn_enabled: bool = True
    ) -> None:
        self.signals.correction_opened.emit(target_text, alternatives, learn_enabled)

    def hide_correction_panel(self) -> None:
        self.signals.correction_closed.emit()

    def set_correction_edit_text(
        self, text: str, cursor: int | None = None
    ) -> None:
        """Met à jour le champ de correction avec une proposition dictée (sans l'appliquer).

        `cursor` : position du curseur après réécriture ; `None` (défaut) =
        conserver la position actuelle du champ — une édition humaine en cours
        n'est jamais déplacée par une resynchronisation.
        """
        self.signals.correction_edit_text_set.emit(
            text, -1 if cursor is None else cursor
        )

    def show_spelling_window(self, prefill: str, from_correction: bool) -> None:
        """Ouvre la fenêtre d'épellation (pré-remplie depuis la correction, ou vide)."""
        self.signals.spelling_opened.emit(prefill, from_correction)

    def hide_spelling_window(self) -> None:
        """Ferme la fenêtre d'épellation (idempotent, appelable depuis n'importe quel thread)."""
        self.signals.spelling_closed.emit()

    def set_spelling_text(self, text: str, cursor: int | None = None) -> None:
        """Miroir complet du texte en attente dans la fenêtre d'épellation (mode correction).

        `cursor` : position du curseur après réécriture (restauration après une
        insertion au curseur) ; `None` = conserver la position actuelle.
        """
        self.signals.spelling_text_set.emit(text, -1 if cursor is None else cursor)

    def append_spelling_text(self, chunk: str) -> None:
        """Ajoute un chunk épelé au miroir de la fenêtre (insertion directe hors correction)."""
        if chunk:
            self.signals.spelling_text_append.emit(chunk)

    def show_help(self, help_text: str, visible: bool = True) -> None:
        self.signals.help_toggled.emit(help_text, visible)

    def show_symbol_choice(self, form: str, labels: list[str]) -> None:
        """Popup de choix pour une forme orale ambiguë (« euro » → « € » ou « euro »)."""
        self.signals.symbol_choice_requested.emit(form, list(labels))

    def hide_symbol_choice(self, *_args: object) -> None:
        """Ferme la popup de choix de symbole (idempotent, appelable depuis n'importe quel thread)."""
        self.signals.symbol_choice_hidden.emit()

    def _shrink_to_content(self) -> None:
        self.card.adjustSize()
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def _apply_help_slot(self, help_text: str, visible: bool) -> None:
        self.help_label.setText(help_text)
        self.help_frame.setVisible(visible)
        self._shrink_to_content()

    def _apply_symbol_choice_slot(self, form: str, labels: list[str]) -> None:
        # Boutons reconstruits à chaque ouverture (voix « choix un/deux » ou clic)
        while self.symbol_btn_row.count():
            item = self.symbol_btn_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.symbol_buttons = []
        self.symbol_title_label.setText(
            f"🔤 Forme dictée « {form} » — choisissez 1/2 (voix : « choix un / deux »), "
            "proposé dans le champ à valider, ou gardez tel quel :"
        )
        for i, label in enumerate(labels[:3]):
            btn = QPushButton(f"{i + 1}. {label}")
            btn.setObjectName("altBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, n=i + 1: self.on_select_alternative(n))
            self.symbol_btn_row.addWidget(btn)
            self.symbol_buttons.append(btn)
        self.symbol_frame.setVisible(True)
        self._shrink_to_content()

    def _apply_symbol_choice_hidden_slot(self) -> None:
        if not self.symbol_frame.isVisible():
            return
        self.symbol_frame.setVisible(False)
        self._shrink_to_content()

    def _apply_state_slot(self, state_val: str) -> None:
        state = MicState(state_val)
        color, badge_text, default_hint = STATE_STYLE_MAP[state]
        self.status_badge.setText(badge_text)
        self.status_badge.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px 10px; border-radius: 6px;"
        )
        # Ne pas écraser la transcription visible si la fenêtre de correction est ouverte
        if (
            state in (MicState.LOADING, MicState.SLEEPING, MicState.MUTED)
            and not self.correction_window.isVisible()
        ):
            self.transcript_label.setText(default_hint)

    def _apply_transcript_slot(
        self, text: str, latency_ms: float, alt_info: str
    ) -> None:
        if latency_ms > 0:
            self.latency_label.setText(f"⚡ {latency_ms:.0f} ms · AMD DirectML FP16")
        display = text.replace("\n", " ↵ ")
        if len(display) > 110:
            display = display[:107] + "..."
        if alt_info:
            self.transcript_label.setText(f"« {display} »   {alt_info}")
        else:
            self.transcript_label.setText(f"« {display} »")

    def _apply_open_correction_slot(
        self, target_text: str, alternatives: list[str], learn_enabled: bool
    ) -> None:
        # La popup de choix de symbole ne doit pas chevaucher la fenêtre de correction
        if self.symbol_frame.isVisible():
            self.symbol_frame.setVisible(False)
        self.correction_window.open_panel(target_text, alternatives, learn_enabled)
        # Curseur de référence (fin de proposition) pour le thread STT
        self._correction_cursor_pos = (
            self.correction_window.correction_edit.cursorPosition()
        )

    def _apply_close_correction_slot(self) -> None:
        self.correction_window.close_panel()
        self._correction_cursor_pos = 0

    def _apply_correction_edit_text_slot(self, text: str, cursor: int) -> None:
        self.correction_window.set_edit_text(text, None if cursor < 0 else cursor)

    def _apply_spelling_opened_slot(self, prefill: str, from_correction: bool) -> None:
        # La popup de choix de symbole ne doit pas chevaucher la fenêtre d'épellation
        if self.symbol_frame.isVisible():
            self.symbol_frame.setVisible(False)
        self._spelling_window_active = True
        self.spelling_window.open_window(prefill, from_correction)
        # Curseur de référence (fin du pré-rempli) pour le thread STT
        self._spelling_cursor_pos = self.spelling_window.spell_edit.cursorPosition()
        # Si la fenêtre de correction est ouverte, placer l'épellation dessous
        if self.correction_window.isVisible():
            cg = self.correction_window.frameGeometry()
            self.spelling_window.move(cg.left(), cg.bottom() + 10)

    def _apply_spelling_closed_slot(self) -> None:
        self.spelling_window.close_window()
        self._spelling_window_active = False
        self._spelling_cursor_pos = 0

    def _on_spelling_cursor_moved(self, _old_pos: int, new_pos: int) -> None:
        # `cursorPositionChanged` transmet (ancienne, nouvelle) position.
        self._spelling_cursor_pos = new_pos
        self._shared_insert_pos = new_pos

    def _on_correction_cursor_moved(self, _old_pos: int, new_pos: int) -> None:
        self._correction_cursor_pos = new_pos
        self._shared_insert_pos = new_pos

    def active_insert_position(self) -> int:
        """Position d'insertion du chunk suivant (mode épellation/correction).

        `spell_edit` et `correction_edit` sont deux MIROIRS du même texte en
        attente (`_pending_correction_text`) : le dernier champ TOUCHÉ — clic
        utilisateur OU réécriture programmatique — fait foi
        (`_shared_insert_pos`, mis à jour par `cursorPositionChanged`).
        À défaut de champ jamais touché, repli historique : fenêtre d'épellation
        ouverte → son champ ; sinon → le champ de correction.
        Conçu pour être lu depuis le thread STT : les valeurs sont maintenues
        en thread GUI (`cursorPositionChanged` + réouverture des fenêtres),
        aucun widget n'est touché ici.
        """
        if self._shared_insert_pos is not None:
            return self._shared_insert_pos
        if self._spelling_window_active:
            return self._spelling_cursor_pos
        return self._correction_cursor_pos

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        """Log de chaque clic sur les champs/fenêtres correction + épellation.

        Diagnostique à distance : on sait si le clic a touché le champ, un
        label (titre/instructions) ou le chrome de la fenêtre, et à quelle
        position de curseur. Les clics sur `spell_edit`/`correction_edit` sont
        acceptés par le champ lui-même (aucune propagation vers le parent) :
        on ne traite donc le press sur les fenêtres QUE pour les fenêtres,
        pour ne jamais journaliser deux fois un même clic.
        Renvoie TOUJOURS False : l'événement poursuit son chemin normal.
        """
        etype = event.type()
        if watched is self.spelling_window.spell_edit:
            if etype == QEvent.MouseButtonRelease:
                self.signals.edit_field_clicked.emit(
                    "epellation", self.spelling_window.spell_edit.cursorPosition()
                )
        elif watched is self.correction_window.correction_edit:
            if etype == QEvent.MouseButtonRelease:
                self.signals.edit_field_clicked.emit(
                    "correction", self.correction_window.correction_edit.cursorPosition()
                )
        elif watched is self.spelling_window:
            # Les labels (titre, instructions) n'acceptent pas les clics et
            # Qt les propage ici : le press sur la fenêtre les attrape.
            if etype == QEvent.MouseButtonPress:
                self.signals.edit_field_clicked.emit("fenetre_epellation", -1)
        elif watched is self.correction_window:
            if etype == QEvent.MouseButtonPress:
                self.signals.edit_field_clicked.emit("fenetre_correction", -1)
        return False

    def _apply_spelling_text_set_slot(self, text: str, cursor: int) -> None:
        self.spelling_window.set_text(text, None if cursor < 0 else cursor)

    def _apply_spelling_append_slot(self, chunk: str) -> None:
        self.spelling_window.append_text(chunk)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
