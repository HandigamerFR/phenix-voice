"""Barre flottante No-Focus PySide6 (HUD Phénix Voice) : indique l'état du micro et permet
d'agir à la souris sans jamais voler le focus clavier de l'application cible.
"""

from __future__ import annotations

import ctypes
from enum import Enum
from typing import Callable
from PySide6.QtCore import QPoint, Qt, Signal, QObject
from PySide6.QtGui import QColor, QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
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
    """États visuels du microphone et du moteur de transcription."""

    LOADING = "loading"
    LISTENING = "listening"
    SPEAKING = "speaking"
    TRANSCRIBING = "transcribing"
    SLEEPING = "sleeping"


STATE_STYLE_MAP: dict[MicState, tuple[str, str, str]] = {
    MicState.LOADING: (
        "#475569",
        "⏳ Chargement GPU AMD Radeon...",
        "Initialisation de Whisper Large-v3-Turbo (DirectML FP16)...",
    ),
    MicState.LISTENING: (
        "#16a34a",
        "🟢 ÉCOUTE ACTIVE",
        "Parlez normalement — écriture directe dans la fenêtre active",
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
        "🟠 AU REPOS (VEILLE)",
        "Dites « Écoute » ou cliquez sur [Activer F8] pour reprendre",
    ),
}


class HUDSignals(QObject):
    """Signaux thread-safe pour mettre à jour le HUD depuis les threads audio et GPU."""

    state_changed = Signal(str)
    transcript_ready = Signal(str, float, str)  # (texte, latence_ms, alternatives_preview)


class PhenixHUD(QWidget):
    """Mini-barre flottante toujours au premier plan qui ne vole jamais le focus clavier."""

    def __init__(
        self,
        on_toggle_sleep: Callable[[], None],
        on_scratch_last: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        super().__init__(None)
        self.on_toggle_sleep = on_toggle_sleep
        self.on_scratch_last = on_scratch_last
        self.on_quit = on_quit
        self._drag_offset: QPoint | None = None

        self.signals = HUDSignals()
        self.signals.state_changed.connect(self._apply_state_slot)
        self.signals.transcript_ready.connect(self._apply_transcript_slot)

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
        """Applique WS_EX_NOACTIVATE au niveau Win32 pour garantir à 100 % qu'un clic souris
        sur la barre ne retire jamais le curseur clavier de la fenêtre où l'on dicte.
        """
        hwnd = int(self.winId())
        if hwnd:
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.card = QFrame(self)
        self.card.setObjectName("hudCard")
        self.card.setStyleSheet(
            """
            QFrame#hudCard {
                background-color: rgba(15, 23, 42, 238);
                border: 1.5px solid #334155;
                border-radius: 12px;
            }
            QLabel {
                color: #f8fafc;
            }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 7px;
                padding: 5px 11px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #94a3b8;
            }
            QPushButton#scratchBtn {
                background-color: #3b1d2e;
                border-color: #9d174d;
                color: #fbcfe8;
            }
            QPushButton#scratchBtn:hover {
                background-color: #501b3a;
            }
            QPushButton#quitBtn {
                background-color: #2a1818;
                border-color: #7f1d1d;
                color: #fecaca;
                padding: 5px 9px;
            }
            """
        )

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(6)

        # Ligne supérieure : Badge d'état + Boutons d'action cliquables sans perte de focus
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

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

        self.toggle_btn = QPushButton("Pause / Actif (F8)")
        self.toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggle_btn.clicked.connect(self.on_toggle_sleep)
        top_row.addWidget(self.toggle_btn)

        self.scratch_btn = QPushButton("⌫ Effacer souffle (« Oups »)")
        self.scratch_btn.setObjectName("scratchBtn")
        self.scratch_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scratch_btn.clicked.connect(self.on_scratch_last)
        top_row.addWidget(self.scratch_btn)

        self.quit_btn = QPushButton("✕")
        self.quit_btn.setObjectName("quitBtn")
        self.quit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.quit_btn.clicked.connect(self.on_quit)
        top_row.addWidget(self.quit_btn)

        card_layout.addLayout(top_row)

        # Ligne inférieure : Dernière phrase transcrite / sous-titre
        self.transcript_label = QLabel(
            "Initialisation du modèle vocal local..."
        )
        self.transcript_label.setFont(QFont("Segoe UI", 10))
        self.transcript_label.setStyleSheet("color: #cbd5e1;")
        self.transcript_label.setWordWrap(False)
        card_layout.addWidget(self.transcript_label)

        outer.addWidget(self.card)
        self.setFixedWidth(740)

    def _position_top_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 14
            self.move(x, y)

    def set_state(self, state: MicState) -> None:
        self.signals.state_changed.emit(state.value)

    def set_transcript(self, text: str, latency_ms: float, alternatives_info: str = "") -> None:
        self.signals.transcript_ready.emit(text, latency_ms, alternatives_info)

    def _apply_state_slot(self, state_val: str) -> None:
        state = MicState(state_val)
        color, badge_text, default_hint = STATE_STYLE_MAP[state]
        self.status_badge.setText(badge_text)
        self.status_badge.setStyleSheet(
            f"background-color: {color}; color: white; padding: 4px 10px; border-radius: 6px;"
        )
        if state in (MicState.LOADING, MicState.SLEEPING):
            self.transcript_label.setText(default_hint)

    def _apply_transcript_slot(self, text: str, latency_ms: float, alt_info: str) -> None:
        self.latency_label.setText(f"⚡ {latency_ms:.0f} ms · AMD DirectML FP16")
        display = text.replace("\n", " ↵ ")
        if len(display) > 78:
            display = display[:75] + "..."
        if alt_info:
            self.transcript_label.setText(f"« {display} »   {alt_info}")
        else:
            self.transcript_label.setText(f"« {display} »")

    # Déplacement de la barre à la souris par glisser-déposer
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
