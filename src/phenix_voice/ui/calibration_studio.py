"""Studio d'Étalonnage & d'Auto-Adaptation Dysarthrie (PySide6) — Phénix Voice.

Permet d'enregistrer les commandes dédiées à Phénix Voice (sans conflit avec Dragon) et les
commandes quotidiennes de dictée/ponctuation :
1. Transcrit immédiatement chaque enregistrement sur la Radeon RX 5700 XT.
2. Lorsque l'utilisateur clique sur « ✅ Oui, prononciation habituelle », enregistre à la fois :
   - L'empreinte acoustique directe (.wav + DTW) de la commande,
   - Et la règle phonétique automatique « Ce que Whisper a entendu -> Ce que j'ai voulu dire »
     dans `user_data/learned_rules.json` !
"""

from __future__ import annotations

from dataclasses import dataclass
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
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from phenix_voice.audio.vad import CHUNK_SAMPLES, SileroVAD
from phenix_voice.postprocess.rules import PhoneticRuleEngine
from phenix_voice.stt.engine import WhisperDirectMLEngine


@dataclass
class CalibrationPrompt:
    id: str
    category: str
    expected_text: str
    instruction: str


ENRICHED_PROMPTS: list[CalibrationPrompt] = [
    CalibrationPrompt(
        id="cmd_phenix_ecoute",
        category="1. Contrôle Micro Phénix (sans conflit avec Dragon)",
        expected_text="Phénix écoute",
        instruction="Commande dédiée pour réveiller Phénix Voice sans activer Dragon.",
    ),
    CalibrationPrompt(
        id="cmd_phenix_repos",
        category="2. Contrôle Micro Phénix (sans conflit avec Dragon)",
        expected_text="Phénix repos",
        instruction="Met Phénix Voice en veille vocale (sans endormir Dragon).",
    ),
    CalibrationPrompt(
        id="cmd_couper_phenix",
        category="3. Coupure Totale du Micro Phénix",
        expected_text="Couper Phénix",
        instruction="Coupe totalement le micro de Phénix (réactivable uniquement par F8 ou clic souris).",
    ),
    CalibrationPrompt(
        id="cmd_effacer_ca",
        category="4. Commande d'Édition Quotidienne",
        expected_text="Effacer ça",
        instruction="Efface immédiatement le dernier souffle dicté dans la fenêtre active.",
    ),
    CalibrationPrompt(
        id="cmd_presser_entree",
        category="5. Commande Clavier Quotidienne",
        expected_text="Presser Entrée",
        instruction="Appuie sur la touche Entrée (valider un message, aller à la ligne).",
    ),
    CalibrationPrompt(
        id="cmd_corriger_ca",
        category="6. Commande de Correction Anti-Dérive",
        expected_text="Corriger ça",
        instruction="Ouvre la barre d'alternatives (1, 2, 3) sur le dernier segment dicté.",
    ),
    CalibrationPrompt(
        id="cmd_oups",
        category="7. Protection Anti-Pollution du Profil",
        expected_text="Oups",
        instruction="Signale que vous avez fourché/bafouillé : annule ou corrige SANS polluer le profil.",
    ),
    CalibrationPrompt(
        id="cmd_choisir_un",
        category="8. Sélection d'Alternative Vocale",
        expected_text="Choisir un",
        instruction="Remplace par la proposition n°1 de la barre de correction.",
    ),
    CalibrationPrompt(
        id="cmd_choisir_deux",
        category="9. Sélection d'Alternative Vocale",
        expected_text="Choisir deux",
        instruction="Remplace par la proposition n°2 de la barre de correction.",
    ),
    CalibrationPrompt(
        id="punct_point_ligne",
        category="10. Ponctuation Dictée",
        expected_text="Point à la ligne",
        instruction="Ajoute un point et passe à la ligne suivante.",
    ),
    CalibrationPrompt(
        id="punct_nouveau_para",
        category="11. Ponctuation Dictée",
        expected_text="Nouveau paragraphe",
        instruction="Saute deux lignes pour démarrer un nouveau paragraphe.",
    ),
    CalibrationPrompt(
        id="punct_interrogation",
        category="12. Ponctuation Dictée",
        expected_text="Point d'interrogation",
        instruction="Insère un point d'interrogation « ? ».",
    ),
]


class CalibrationStudioWindow(QWidget):
    """Fenêtre d'étalonnage avec transcription GPU immédiate et apprentissage automatique A -> B."""

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

        self.prompts = ENRICHED_PROMPTS
        self.current_index = 0
        self.recorded_entries: list[dict] = self._load_existing_manifest()
        self.rule_engine = PhoneticRuleEngine()
        self.vad = SileroVAD()
        self.stt_engine: WhisperDirectMLEngine | None = None

        self._is_recording = False
        self._recorded_chunks: list[np.ndarray] = []
        self._current_audio: np.ndarray | None = None
        self._current_heard_text: str = ""
        self._current_alts: list[str] = []
        self._live_peak: float = 0.0
        self._stream: sd.InputStream | None = None

        self.setWindowTitle(
            "Phénix Voice — Studio d'Étalonnage & d'Auto-Apprentissage Dysarthrie"
        )
        self.setMinimumSize(840, 580)
        self._build_ui()
        self._populate_microphones()
        self._load_prompt(0)

        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self._update_meter)
        self._meter_timer.start(50)

        # Chargement différé du moteur GPU pour afficher la fenêtre instantanément
        QTimer.singleShot(150, self._init_gpu_engine)

    def _load_existing_manifest(self) -> list[dict]:
        if not self.manifest_path.exists():
            return []
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return list(data.get("samples", []))
        except Exception:
            return []

    def _init_gpu_engine(self) -> None:
        self.heard_label.setText(
            "⏳ Chargement du moteur Whisper GPU AMD (DirectML FP16)..."
        )
        QApplication.processEvents()
        self.stt_engine = WhisperDirectMLEngine()
        self.heard_label.setText(
            f"✅ Moteur GPU prêt ({len(self.rule_engine.utterance_rules)} règles phonétiques actives)"
        )

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
            QLineEdit#targetEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 2px solid #38bdf8;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 10px;
                padding: 11px 18px;
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
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        # En-tête : Micro + Progression + Boutons Passer / Terminer
        header_row = QHBoxLayout()
        mic_label = QLabel("🎙️ Micro :")
        mic_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header_row.addWidget(mic_label)

        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(290)
        header_row.addWidget(self.mic_combo)
        header_row.addStretch(1)

        self.progress_label = QLabel("Étape 1 / 12")
        self.progress_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.progress_label.setStyleSheet("color: #38bdf8;")
        header_row.addWidget(self.progress_label)

        self.skip_btn = QPushButton("⏭️ Passer cet élément")
        self.skip_btn.clicked.connect(self._skip_current)
        header_row.addWidget(self.skip_btn)

        self.finish_btn = QPushButton("🏁 Terminer & Sauvegarder")
        self.finish_btn.clicked.connect(self.close)
        header_row.addWidget(self.finish_btn)
        root.addLayout(header_row)

        # Carte centrale
        self.card = QFrame()
        self.card.setObjectName("promptCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)

        self.category_label = QLabel("Catégorie")
        self.category_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.category_label.setStyleSheet("color: #94a3b8;")
        card_layout.addWidget(self.category_label)

        edit_hint = QLabel(
            "Expression à prononcer (vous pouvez aussi modifier ce texte si vous préférez une autre formulation) :"
        )
        edit_hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        card_layout.addWidget(edit_hint)

        self.target_edit = QLineEdit()
        self.target_edit.setObjectName("targetEdit")
        self.target_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.target_edit)

        self.instruction_label = QLabel("Instruction")
        self.instruction_label.setFont(QFont("Segoe UI", 11))
        self.instruction_label.setStyleSheet("color: #cbd5e1;")
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.instruction_label)

        self.heard_label = QLabel("En attente d'enregistrement...")
        self.heard_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.heard_label.setStyleSheet(
            "color: #38bdf8; background-color: #0f172a; padding: 8px; border-radius: 8px;"
        )
        self.heard_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.heard_label)

        root.addWidget(self.card, stretch=1)

        # VU-mètre
        meter_row = QHBoxLayout()
        meter_lbl = QLabel("Niveau micro :")
        meter_lbl.setFont(QFont("Segoe UI", 10))
        meter_row.addWidget(meter_lbl)

        self.vu_bar = QProgressBar()
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        meter_row.addWidget(self.vu_bar, stretch=1)

        self.peak_info_label = QLabel("Prêt")
        self.peak_info_label.setFont(QFont("Segoe UI", 10))
        self.peak_info_label.setMinimumWidth(190)
        meter_row.addWidget(self.peak_info_label)
        root.addLayout(meter_row)

        # Bouton d'enregistrement
        self.record_btn = QPushButton("🔴 Cliquez ici pour DÉMARRER l'enregistrement")
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.setMinimumHeight(52)
        self.record_btn.clicked.connect(self._toggle_recording)
        root.addWidget(self.record_btn)

        # Zone de validation anti-dérive
        self.validation_frame = QFrame()
        val_layout = QVBoxLayout(self.validation_frame)
        val_layout.setContentsMargins(0, 4, 0, 0)
        val_layout.setSpacing(8)

        self.val_question_label = QLabel(
            "Avez-vous prononcé normalement (sans fourcher) ? Valider créera automatiquement la règle d'adaptation vocale :"
        )
        self.val_question_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.val_question_label.setStyleSheet("color: #fde047;")
        self.val_question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_layout.addWidget(self.val_question_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self.valid_btn = QPushButton(
            "✅ Oui, prononciation habituelle (Valider & Apprendre)"
        )
        self.valid_btn.setObjectName("validBtn")
        self.valid_btn.setMinimumHeight(46)
        self.valid_btn.clicked.connect(self._validate_and_next)
        btn_row.addWidget(self.valid_btn)

        self.retry_btn = QPushButton("🔄 Non, j'ai fourché (Recommencer)")
        self.retry_btn.setObjectName("retryBtn")
        self.retry_btn.setMinimumHeight(46)
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
        self.target_edit.setText(p.expected_text)
        self.instruction_label.setText(p.instruction)
        self.validation_frame.setVisible(False)
        self.record_btn.setEnabled(True)
        self.record_btn.setText("🔴 Cliquez ici pour DÉMARRER l'enregistrement")
        self.record_btn.setStyleSheet(
            "background-color: #dc2626; border-color: #ef4444; font-size: 16px;"
        )
        self._current_audio = None
        self._current_heard_text = ""
        self._current_alts = []

    def _skip_current(self) -> None:
        if self.current_index + 1 < len(self.prompts):
            self._load_prompt(self.current_index + 1)
        else:
            self.close()

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
        peak = self._live_peak
        self._live_peak *= 0.7
        if peak <= 1e-5:
            pct = 0
        else:
            db = 20.0 * np.log10(min(1.0, peak))
            pct = int(np.clip((db + 60.0) / 54.0 * 100.0, 2, 100))
        self.vu_bar.setValue(pct)
        self.peak_info_label.setText(f"Pic : {peak:.4f} ({pct}%)")

    def _trim_silence(self, pcm: np.ndarray) -> np.ndarray:
        self.vad.reset_states()
        probs = [
            self.vad.process_chunk(pcm[i : i + CHUNK_SAMPLES])
            for i in range(0, len(pcm), CHUNK_SAMPLES)
        ]
        active = [i for i, pr in enumerate(probs) if pr >= 0.32]
        if not active:
            return pcm
        s = max(0, (active[0] - 8) * CHUNK_SAMPLES)
        e = min(len(pcm), (active[-1] + 10) * CHUNK_SAMPLES)
        return pcm[s:e]

    def _toggle_recording(self) -> None:
        if not self._is_recording:
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
            self._is_recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if not self._recorded_chunks:
                return
            full_audio = np.concatenate(self._recorded_chunks, axis=0)
            self._current_audio = self._trim_silence(full_audio)
            dur = len(self._current_audio) / self.sample_rate
            max_amp = float(np.max(np.abs(self._current_audio)))
            self.peak_info_label.setText(f"Durée : {dur:.2f}s | Pic : {max_amp:.4f}")

            # Transcription immédiate sur le GPU pour montrer ce que Whisper entend
            if self.stt_engine is not None:
                self.heard_label.setText("🟣 Analyse GPU en cours...")
                QApplication.processEvents()
                res = self.stt_engine.transcribe(self._current_audio)
                self._current_heard_text = res.text
                self._current_alts = res.alternatives
                target_txt = self.target_edit.text().strip()
                self.heard_label.setText(
                    f"Entendu par Whisper ({res.total_ms:.0f} ms) : « {res.text} »  ➔  Sera associé à : « {target_txt} »"
                )

            self.record_btn.setEnabled(False)
            self.record_btn.setText("Enregistrement analysé — Validez ci-dessous :")
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
        expected_text = self.target_edit.text().strip() or p.expected_text
        raw_audio = self._current_audio
        raw_peak = float(np.max(np.abs(raw_audio)))
        raw_rms = float(np.sqrt(np.mean(raw_audio**2)))
        duration_s = len(raw_audio) / self.sample_rate

        raw_path = self.samples_dir / f"{p.id}_raw.wav"
        norm_path = self.samples_dir / f"{p.id}_norm.wav"

        self._save_wav(raw_path, raw_audio)
        norm_audio = raw_audio * (0.85 / raw_peak) if raw_peak > 1e-4 else raw_audio
        self._save_wav(norm_path, norm_audio)

        # Apprentissage automatique de la règle phonétique A -> B
        if self._current_heard_text:
            self.rule_engine.learn_utterance_mapping(
                self._current_heard_text, expected_text
            )
        for alt in self._current_alts[:2]:
            self.rule_engine.learn_utterance_mapping(alt, expected_text)

        entry = {
            "id": p.id,
            "category": p.category,
            "expected_text": expected_text,
            "heard_text": self._current_heard_text,
            "alternatives": self._current_alts[:3],
            "raw_wav": str(raw_path),
            "norm_wav": str(norm_path),
            "duration_s": round(duration_s, 3),
            "raw_peak": round(raw_peak, 6),
            "raw_rms": round(raw_rms, 6),
            "mic_name": self.mic_combo.currentText(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # Mettre à jour ou ajouter dans le manifeste sans perdre les enregistrements précédents
        self.recorded_entries = [
            e for e in self.recorded_entries if e.get("id") != p.id
        ]
        self.recorded_entries.append(entry)

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(
                {"samples": self.recorded_entries}, f, ensure_ascii=False, indent=2
            )

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
