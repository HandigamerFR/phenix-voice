"""Barre flottante No-Focus PySide6 (HUD Phénix Voice — Phase 2+) :
- 3 états de micro (Actif / Veille vocale « Phénix repos » / Micro Coupé F8).
- Volet de correction Anti-Dérive : alternatives 1/2/3, édition manuelle à la souris, re-dictée vocale,
  et séparation stricte « 🧠 Corriger & Apprendre » vs « 🛡️ Corriger SANS apprendre (Oups) ».
- Panneau d'aide contextuel « Que puis-je dire ? » listant les commandes vocales disponibles.
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
    correction_edit_text_set = Signal(str)  # texte dicté proposé pendant correction (sans application auto)
    help_toggled = Signal(str, bool)  # (help_text, visible)


class PhenixHUD(QWidget):
    """Barre flottante toujours au premier plan.
    No-Focus (WS_EX_NOACTIVATE) par défaut pour ne jamais voler le curseur de la fenêtre cible,
    mais devient temporairement activable quand l'utilisateur clique pour éditer manuellement une correction.
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
        self._drag_offset: QPoint | None = None
        self._is_noactivate = True

        self.signals = HUDSignals()
        self.signals.state_changed.connect(self._apply_state_slot)
        self.signals.transcript_ready.connect(self._apply_transcript_slot)
        self.signals.correction_opened.connect(self._apply_open_correction_slot)
        self.signals.correction_closed.connect(self._apply_close_correction_slot)
        self.signals.correction_edit_text_set.connect(self._apply_correction_edit_text_slot)
        self.signals.help_toggled.connect(self._apply_help_slot)

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

    def _set_interactive_edit_mode(self, enabled: bool) -> None:
        """Autorise temporairement le focus clavier pour saisir une correction manuelle à la souris."""
        self._is_noactivate = not enabled
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not enabled)
        # Retirer WindowDoesNotAcceptFocus pour que le QLineEdit reçoive le focus clavier
        flags = self.windowFlags()
        if enabled:
            flags = flags & ~Qt.WindowType.WindowDoesNotAcceptFocus
        else:
            flags = flags | Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(
            flags
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._enforce_win32_noactivate()
        self.show()
        if enabled:
            self.activateWindow()
            self.correction_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.correction_edit.setFocus()
            self.correction_edit.selectAll()

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

        # Ligne 3 (repliée par défaut) : Volet de Correction Anti-Dérive
        self.corr_frame = QFrame(self.card)
        self.corr_frame.setObjectName("corrFrame")
        corr_layout = QVBoxLayout(self.corr_frame)
        corr_layout.setContentsMargins(10, 8, 10, 8)
        corr_layout.setSpacing(6)

        corr_header = QHBoxLayout()
        self.corr_title_label = QLabel(
            "✏️ Correction : choisissez 1/2/3, modifiez le texte à la main, ou re-dictez directement :"
        )
        self.corr_title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.corr_title_label.setStyleSheet("color: #38bdf8;")
        corr_header.addWidget(self.corr_title_label, stretch=1)

        self.learn_mode_btn = QPushButton("🧠 Mode : Corriger & Apprendre (Actif)")
        self.learn_mode_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.learn_mode_btn.clicked.connect(self.on_toggle_learn_mode)
        corr_header.addWidget(self.learn_mode_btn)
        corr_layout.addLayout(corr_header)

        self.alt_row = QHBoxLayout()
        self.alt_row.setSpacing(8)
        self.alt_buttons: list[QPushButton] = []
        for idx in range(3):
            btn = QPushButton(f"{idx + 1}. ---")
            btn.setObjectName("altBtn")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, i=idx + 1: self.on_select_alternative(i))
            self.alt_row.addWidget(btn)
            self.alt_buttons.append(btn)

        corr_layout.addLayout(self.alt_row)

        # Édition manuelle (clavier/souris) du segment corrigé
        manual_row = QHBoxLayout()
        manual_row.setSpacing(8)
        self.correction_edit = QLineEdit()
        self.correction_edit.setObjectName("corrEdit")
        self.correction_edit.setPlaceholderText("Modifiez ici le texte à corriger...")
        self.correction_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.correction_edit.installEventFilter(self)
        manual_row.addWidget(self.correction_edit, stretch=1)

        self.apply_edit_btn = QPushButton("✅ Appliquer la correction")
        self.apply_edit_btn.setObjectName("applyBtn")
        self.apply_edit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_edit_btn.clicked.connect(self._on_apply_manual_clicked)
        manual_row.addWidget(self.apply_edit_btn)
        corr_layout.addLayout(manual_row)

        self.corr_hint_label = QLabel(
            "💡 Astuce : cliquez dans le champ pour corriger à la main, ou re-dictez la phrase complète (elle sera proposée sans être appliquée). "
            "Validez ensuite avec [Appliquer la correction] ou dites « Valider la correction »."
        )
        self.corr_hint_label.setFont(QFont("Segoe UI", 8))
        self.corr_hint_label.setStyleSheet("color: #94a3b8;")
        corr_layout.addWidget(self.corr_hint_label)

        self.corr_frame.setVisible(False)
        card_layout.addWidget(self.corr_frame)

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
        self.setFixedWidth(920)

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self.correction_edit:
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
                if self._is_noactivate:
                    self._set_interactive_edit_mode(True)
        return super().eventFilter(obj, event)

    def _on_apply_manual_clicked(self) -> None:
        text = self.correction_edit.text().strip()
        if text:
            self.on_apply_manual_correction(text)
        self._set_interactive_edit_mode(False)

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

    def set_correction_edit_text(self, text: str) -> None:
        """Met à jour le champ de correction avec une proposition dictée (sans l'appliquer)."""
        self.signals.correction_edit_text_set.emit(text)

    def show_help(self, help_text: str, visible: bool = True) -> None:
        self.signals.help_toggled.emit(help_text, visible)

    def _shrink_to_content(self) -> None:
        self.card.adjustSize()
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def _apply_help_slot(self, help_text: str, visible: bool) -> None:
        self.help_label.setText(help_text)
        self.help_frame.setVisible(visible)
        self._shrink_to_content()

    def _apply_state_slot(self, state_val: str) -> None:
        state = MicState(state_val)
        color, badge_text, default_hint = STATE_STYLE_MAP[state]
        self.status_badge.setText(badge_text)
        self.status_badge.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px 10px; border-radius: 6px;"
        )
        # Ne pas écraser la transcription/correction visible si un panneau de correction est ouvert
        if (
            state in (MicState.LOADING, MicState.SLEEPING, MicState.MUTED)
            and not self.corr_frame.isVisible()
        ):
            self.transcript_label.setText(default_hint)

    def _apply_transcript_slot(
        self, text: str, latency_ms: float, alt_info: str
    ) -> None:
        if latency_ms > 0:
            self.latency_label.setText(f"⚡ {latency_ms:.0f} ms · AMD DirectML FP16")
        display = text.replace("\n", " ↵ ")
        if len(display) > 85:
            display = display[:82] + "..."
        if alt_info:
            self.transcript_label.setText(f"« {display} »   {alt_info}")
        else:
            self.transcript_label.setText(f"« {display} »")

    def _apply_open_correction_slot(
        self, target_text: str, alternatives: list[str], learn_enabled: bool
    ) -> None:
        clean_target = target_text.strip()
        self.corr_title_label.setText(
            f"✏️ Corriger « {clean_target} » — choisissez 1/2/3, modifiez à la main, ou re-dictez :"
        )
        self.correction_edit.setText(clean_target)
        if learn_enabled:
            self.learn_mode_btn.setText("🧠 Mode : Corriger & Apprendre")
            self.learn_mode_btn.setStyleSheet(
                "background-color: #14532d; border-color: #22c55e; color: #dcfce7;"
            )
        else:
            self.learn_mode_btn.setText("🛡️ Mode : SANS Apprendre (Annuler sans apprendre)")
            self.learn_mode_btn.setStyleSheet(
                "background-color: #7c2d12; border-color: #f97316; color: #ffedd5;"
            )

        for i, btn in enumerate(self.alt_buttons):
            if i < len(alternatives) and alternatives[i].strip():
                btn.setText(f"{i + 1}. {alternatives[i].strip()}")
                btn.setVisible(True)
            else:
                btn.setVisible(False)

        self.corr_frame.setVisible(True)
        self._shrink_to_content()

    def _apply_close_correction_slot(self) -> None:
        self.corr_frame.setVisible(False)
        self.correction_edit.clear()
        self._set_interactive_edit_mode(False)
        self._shrink_to_content()

    def _apply_correction_edit_text_slot(self, text: str) -> None:
        self.correction_edit.setText(text.strip())
        self._shrink_to_content()

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
