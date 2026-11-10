"""Mini-Studio d'Étalonnage & Diagnostic Vocal (PySide6) — Phénix Voice.

Permet d'enregistrer en quelques clics de souris un jeu de commandes vitales et de phrases
de référence avec validation anti-pollution (« Ai-je prononcé normalement sans fourcher ? »),
afin de :
1. Mesurer le niveau réel du microphone (K66) et calibrer la normalisation de gain (AGC) et le VAD.
2. Enregistrer les empreintes acoustiques des commandes vitales (« Écoute », « Au repos », « Corriger ça », « Oups »).
3. Tester et régler le moteur Whisper GPU AMD directement sur la vraie voix de l'utilisateur.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import time
import wave
import numpy as np
import sounddevice as sd
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class CalibrationPrompt:
    id: str
    category: str
    expected_text: str
    instruction: str


DEFAULT_PROMPTS: list[CalibrationPrompt] = [
    CalibrationPrompt(
        id="cmd_ecoute",
        category="Commande vitale (Réveil)",
        expected_text="Écoute",
        instruction="Prononcez ce mot naturellement, comme pour réveiller le micro.",
    ),
    CalibrationPrompt(
        id="cmd_au_repos",
        category="Commande vitale (Mise en veille)",
        expected_text="Au repos",
        instruction="Prononcez cette commande avec votre diction habituelle.",
    ),
    CalibrationPrompt(
        id="cmd_corriger_ca",
        category="Commande vitale (Correction)",
        expected_text="Corriger ça",
        instruction="Servira aussi d'empreinte acoustique protégée contre la dérive.",
    ),
    CalibrationPrompt(
        id="cmd_oups",
        category="Commande vitale (Annulation sans apprendre)",
        expected_text="Oups",
        instruction="Commande rapide pour effacer un bafouillage sans polluer le profil.",
    ),
    CalibrationPrompt(
        id="phrase_1",
        category="Phrase d'étalonnage 1 (Conversation)",
        expected_text="Bonjour, comment ça va aujourd'hui ?",
        instruction="Parlez à votre rythme naturel, même si vous faites de légères pauses.",
    ),
    CalibrationPrompt(
        id="phrase_2",
        category="Phrase d'étalonnage 2 (Dictée & Ponctuation)",
        expected_text="Je teste la reconnaissance vocale adaptée point à la ligne",
        instruction="Prononcez toute la phrase jusqu'au bout à votre rythme habituel.",
    ),
]


class CalibrationStudioWindow(QWidget):
    """Fenêtre guidée d'étalonnage vocal pilotable intégralement à la souris."""

    def __init__(
        self,
        output_dir: str | Path = "user_data/calibration",
        sample_rate: int = 16000,
    ) -> None:
        super().__init__()
        self.output_dir = Path(output_dir)
        self.samples_dir = self.output_dir / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.output_dir / "manifest.json"
        self.sample_rate = sample_rate

        self.prompts = DEFAULT_PROMPTS
        self.current_index = 0
        self.recorded_entries: list[dict] = []

        self._is_recording = False
        self._recorded_chunks: list[np.ndarray] = []
        self._current_audio: np.ndarray | None = None
        self._live_peak: float = 0.0
        self._stream: sd.InputStream | None = None

        self.setWindowTitle("Phénix Voice — Mini-Studio d'Étalonnage & Diagnostic Vocal")
        self.setMinimumSize(780, 520)
        self._build_ui()
        self._populate_microphones()
        self._load_prompt(0)

        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self._update_meter)
        self._meter_timer.start(50)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI';
            }
            QFrame#promptCard {
                background-color: #1e293b;
                border: 2px solid #334155;
                border-radius: 14px;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #334155;
            }
            QPushButton#recordBtn {
                background-color: #dc2626;
                border-color: #ef4444;
                font-size: 16px;
            }
            QPushButton#recordBtn:hover {
                background-color: #b91c1c;
            }
            QPushButton#validBtn {
                background-color: #16a34a;
                border-color: #22c55e;
                font-size: 15px;
            }
            QPushButton#validBtn:hover {
                background-color: #15803d;
            }
            QPushButton#retryBtn {
                background-color: #d97706;
                border-color: #f59e0b;
                font-size: 15px;
            }
            QPushButton#retryBtn:hover {
                background-color: #b45309;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 5px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # En-tête : Choix du micro + Progression
        header_row = QHBoxLayout()
        mic_label = QLabel("🎙️ Microphone :")
        mic_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header_row.addWidget(mic_label)

        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(340)
        header_row.addWidget(self.mic_combo)
        header_row.addStretch(1)

        self.progress_label = QLabel("Étape 1 / 6")
        self.progress_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.progress_label.setStyleSheet("color: #38bdf8;")
        header_row.addWidget(self.progress_label)
        root.addLayout(header_row)

        # Carte centrale du texte à prononcer
        self.card = QFrame()
        self.card.setObjectName("promptCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(12)

        self.category_label = QLabel("Catégorie")
        self.category_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.category_label.setStyleSheet("color: #94a3b8;")
        card_layout.addWidget(self.category_label)

        self.target_text_label = QLabel("Texte à prononcer")
        self.target_text_label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.target_text_label.setStyleSheet("color: #f8fafc; padding: 8px 0px;")
        self.target_text_label.setWordWrap(True)
        self.target_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.target_text_label)

        self.instruction_label = QLabel("Instruction")
        self.instruction_label.setFont(QFont("Segoe UI", 11))
        self.instruction_label.setStyleSheet("color: #cbd5e1;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.instruction_label)

        root.addWidget(self.card, stretch=1)

        # VU-mètre de niveau micro
        meter_row = QHBoxLayout()
        meter_lbl = QLabel("Niveau capté :")
        meter_lbl.setFont(QFont("Segoe UI", 10))
        meter_row.addWidget(meter_lbl)

        self.vu_bar = QProgressBar()
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        meter_row.addWidget(self.vu_bar, stretch=1)

        self.peak_info_label = QLabel("En attente...")
        self.peak_info_label.setFont(QFont("Segoe UI", 10))
        self.peak_info_label.setMinimumWidth(190)
        meter_row.addWidget(self.peak_info_label)
        root.addLayout(meter_row)

        # Bouton principal Démarrer / Arrêter l'enregistrement
        self.record_btn = QPushButton("🔴 Cliquez ici pour DÉMARRER l'enregistrement")
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.setMinimumHeight(54)
        self.record_btn.clicked.connect(self._toggle_recording)
        root.addWidget(self.record_btn)

        # Zone de validation anti-dérive (affichée après chaque enregistrement)
        self.validation_frame = QFrame()
        val_layout = QVBoxLayout(self.validation_frame)
        val_layout.setContentsMargins(0, 4, 0, 0)
        val_layout.setSpacing(10)

        self.val_question_label = QLabel(
            "Avez-vous prononcé cet élément avec votre diction habituelle (sans fourcher ni tousser) ?"
        )
        self.val_question_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.val_question_label.setStyleSheet("color: #fde047;")
        self.val_question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_layout.addWidget(self.val_question_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self.valid_btn = QPushButton(
            "✅ Oui, prononciation habituelle (Valider & Suivant)"
        )
        self.valid_btn.setObjectName("validBtn")
        self.valid_btn.setMinimumHeight(48)
        self.valid_btn.clicked.connect(self._validate_and_next)
        btn_row.addWidget(self.valid_btn)

        self.retry_btn = QPushButton("🔄 Non, j'ai fourché (Recommencer)")
        self.retry_btn.setObjectName("retryBtn")
        self.retry_btn.setMinimumHeight(48)
        self.retry_btn.clicked.connect(self._discard_and_retry)
        btn_row.addWidget(self.retry_btn)

        val_layout.addLayout(btn_row)
        self.validation_frame.setVisible(False)
        root.addWidget(self.validation_frame)

    def _populate_microphones(self) -> None:
        self.mic_combo.clear()
        devices = sd.query_devices()
        k66_index_in_combo = 0
        seen_names: set[str] = set()
        for dev_id, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                name = str(d["name"])
                if name in seen_names:
                    continue
                seen_names.add(name)
                self.mic_combo.addItem(f"{name} (id={dev_id})", userData=dev_id)
                if "K66" in name and k66_index_in_combo == 0:
                    k66_index_in_combo = self.mic_combo.count() - 1
        self.mic_combo.setCurrentIndex(k66_index_in_combo)

    def _load_prompt(self, index: int) -> None:
        self.current_index = index
        p = self.prompts[index]
        self.progress_label.setText(f"Étape {index + 1} / {len(self.prompts)}")
        self.category_label.setText(p.category.upper())
        self.target_text_label.setText(f"« {p.expected_text} »")
        self.instruction_label.setText(p.instruction)
        self.validation_frame.setVisible(False)
        self.record_btn.setEnabled(True)
        self.record_btn.setText("🔴 Cliquez ici pour DÉMARRER l'enregistrement")
        self.record_btn.setStyleSheet(
            "background-color: #dc2626; border-color: #ef4444; font-size: 16px;"
        )
        self._current_audio = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if not self._is_recording:
            return
        mono = indata[:, 0].copy()
        self._recorded_chunks.append(mono)
        chunk_peak = float(np.max(np.abs(mono)))
        if chunk_peak > self._live_peak:
            self._live_peak = chunk_peak

    def _update_meter(self) -> None:
        if not self._is_recording:
            return
        # Échelle logarithmique sensible même aux faibles gains (0.001 à 0.5)
        peak = self._live_peak
        self._live_peak *= 0.7
        if peak <= 1e-5:
            pct = 0
        else:
            db = 20.0 * np.log10(min(1.0, peak))
            # -60 dB -> 0%, -6 dB -> 100%
            pct = int(np.clip((db + 60.0) / 54.0 * 100.0, 2, 100))
        self.vu_bar.setValue(pct)
        self.peak_info_label.setText(f"Pic : {peak:.4f} ({pct}%)")

    def _toggle_recording(self) -> None:
        if not self._is_recording:
            # Démarrage
            dev_id = self.mic_combo.currentData()
            self._recorded_chunks.clear()
            self._live_peak = 0.0
            self._is_recording = True
            self.validation_frame.setVisible(False)
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=512,
                device=dev_id,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self.record_btn.setText(
                "⏹️ Parlez maintenant... Puis cliquez ici pour ARRÊTER"
            )
            self.record_btn.setStyleSheet(
                "background-color: #2563eb; border-color: #3b82f6; font-size: 16px;"
            )
        else:
            # Arrêt
            self._is_recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if not self._recorded_chunks:
                return
            self._current_audio = np.concatenate(self._recorded_chunks, axis=0)
            dur = len(self._current_audio) / self.sample_rate
            max_amp = float(np.max(np.abs(self._current_audio)))
            self.peak_info_label.setText(f"Durée : {dur:.2f}s | Pic max : {max_amp:.4f}")
            self.record_btn.setEnabled(False)
            self.record_btn.setText("Enregistrement terminé — Validez ci-dessous :")
            self.record_btn.setStyleSheet("background-color: #334155;")
            self.validation_frame.setVisible(True)

    def _discard_and_retry(self) -> None:
        self._current_audio = None
        self.vu_bar.setValue(0)
        self.peak_info_label.setText("Prêt à ré-enregistrer")
        self._load_prompt(self.current_index)

    def _save_wav(self, path: Path, audio_f32: np.ndarray) -> None:
        pcm16 = np.clip(audio_f32 * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm16.tobytes())

    def _validate_and_next(self) -> None:
        if self._current_audio is None:
            return
        p = self.prompts[self.current_index]
        raw_audio = self._current_audio
        raw_peak = float(np.max(np.abs(raw_audio)))
        raw_rms = float(np.sqrt(np.mean(raw_audio**2)))
        duration_s = len(raw_audio) / self.sample_rate

        raw_path = self.samples_dir / f"{p.id}_raw.wav"
        norm_path = self.samples_dir / f"{p.id}_norm.wav"

        self._save_wav(raw_path, raw_audio)
        # Sauvegarder aussi la version normalisée à 0.85 pleine échelle
        if raw_peak > 1e-4:
            norm_audio = raw_audio * (0.85 / raw_peak)
        else:
            norm_audio = raw_audio
        self._save_wav(norm_path, norm_audio)

        self.recorded_entries.append(
            {
                "id": p.id,
                "category": p.category,
                "expected_text": p.expected_text,
                "raw_wav": str(raw_path),
                "norm_wav": str(norm_path),
                "duration_s": round(duration_s, 3),
                "raw_peak": round(raw_peak, 6),
                "raw_rms": round(raw_rms, 6),
                "mic_name": self.mic_combo.currentText(),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )

        # Sauvegarder le manifeste au fil de l'eau
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump({"samples": self.recorded_entries}, f, ensure_ascii=False, indent=2)

        if self.current_index + 1 < len(self.prompts):
            self._load_prompt(self.current_index + 1)
        else:
            self.close()


def main() -> None:
    app = QApplication(sys.argv)
    win = CalibrationStudioWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
