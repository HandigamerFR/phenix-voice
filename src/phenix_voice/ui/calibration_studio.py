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

from collections.abc import Callable
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

from phenix_voice.audio.vad import CHUNK_SAMPLES, BreathSegmenter, SileroVAD
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

# --- Studio mixte (décision 13/11) -------------------------------------------
# 1. Les 26 mots OTAN, dits avec la voix de l'utilisateur : ils alimentent le
#    FILET acoustique DTW du mode épellation
#    (`AcousticCommandProtector.match_nato_letter`) quand le STT n'a rien compris
#    (le fameux « Mike » transcrit « Make. » / « Veilk »).
# 2. Des textes naturels à couverture phonémique FR : corpus de l'étape 5
#    (alignement forcé MFA puis LoRA Whisper large-v3 FR).
NATO_VOCABULARY: tuple[tuple[str, str, str], ...] = (
    ("alpha", "Alpha", "a"),
    ("bravo", "Bravo", "b"),
    ("charlie", "Charlie", "c"),
    ("delta", "Delta", "d"),
    ("echo", "Echo", "e"),
    ("foxtrot", "Foxtrot", "f"),
    ("golf", "Golf", "g"),
    ("hotel", "Hotel", "h"),
    ("india", "India", "i"),
    ("juliett", "Juliett", "j"),
    ("kilo", "Kilo", "k"),
    ("lima", "Lima", "l"),
    ("mike", "Mike", "m"),
    ("november", "November", "n"),
    ("oscar", "Oscar", "o"),
    ("papa", "Papa", "p"),
    ("quebec", "Quebec", "q"),
    ("romeo", "Romeo", "r"),
    ("sierra", "Sierra", "s"),
    ("tango", "Tango", "t"),
    ("uniform", "Uniform", "u"),
    ("victor", "Victor", "v"),
    ("whiskey", "Whiskey", "w"),
    ("xray", "X-Ray", "x"),
    ("yankee", "Yankee", "y"),
    ("zulu", "Zulu", "z"),
)

NATO_PROMPTS: list[CalibrationPrompt] = [
    CalibrationPrompt(
        id=f"nato_{key}",
        category="13. Alphabet OTAN — Filet acoustique (mode épellation)",
        expected_text=word,
        instruction=(
            f"Dites le mot OTAN « {word} » (= lettre « {letter.upper()} ») "
            "avec votre prononciation habituelle."
        ),
    )
    for key, word, letter in NATO_VOCABULARY
]

# Phrases naturelles : nasales (an/en/on/un), « e » muet, ch/gn/ou/oi, accents.
CORPUS_TEXTS: tuple[str, ...] = (
    "Le renard brun saute près du vieux pont.",
    "J'ai écrit une lettre à ma sœur ce matin.",
    "Les jeunes gens chantent une chanson joyeuse.",
    "Mon frère achète des cerises très sucrées.",
    "Pourquoi les ouvriers réparent-ils la toiture ?",
    "Une île calme au milieu de la rivière.",
    "Le bûcheron débite le bois sous la pluie.",
    "Ta sœur a mangé des champignons au jardin.",
    "Zoé a pris le bus jaune pour aller au cirque.",
    "Vingt-cinq soldats chargent leurs sacs près du port.",
    "Le docteur examine gentiment le petit oiseau.",
    "Écoutez la musique douce du violon ce soir.",
)

CORPUS_PROMPTS: list[CalibrationPrompt] = [
    CalibrationPrompt(
        id=f"corpus_{i:02d}",
        category="14. Corpus naturel FR (étape 5 — alignement + LoRA)",
        expected_text=text,
        instruction="Dictez cette phrase naturellement, comme en dictée normale.",
    )
    for i, text in enumerate(CORPUS_TEXTS, start=1)
]

# Corpus d'étalonnage COMPLET (384 phrases, étape 5) : une phrase par ligne de
# `corpus/etalonnage.txt`, ids `utt0001`..`utt0384` alignés sur
# `corpus/etalonnage_mfa.txt` (jumelage direct avec les WAV pour MFA).
# Chargé depuis le dépôt ; si le fichier est absent (installation publique),
# seuls les 50 prompts intégrés restent disponibles.
def _load_full_corpus_prompts() -> list[CalibrationPrompt]:
    corpus_file = Path(__file__).resolve().parents[3] / "corpus" / "etalonnage.txt"
    if not corpus_file.is_file():
        return []
    texts = [
        line.strip()
        for line in corpus_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        CalibrationPrompt(
            id=f"utt{i:04d}",
            category="15. Corpus étalonnage complet 384 phrases (étape 5)",
            expected_text=text,
            instruction="Dictez cette phrase naturellement, comme en dictée normale.",
        )
        for i, text in enumerate(texts, start=1)
    ]


FULL_CORPUS_PROMPTS: list[CalibrationPrompt] = _load_full_corpus_prompts()

ENRICHED_PROMPTS.extend(NATO_PROMPTS)
ENRICHED_PROMPTS.extend(CORPUS_PROMPTS)
ENRICHED_PROMPTS.extend(FULL_CORPUS_PROMPTS)

# --- Mode « Lecture guidée » (zéro clic, exigence 17/11) ----------------------
# Principe inspiré du wizard d'entraînement Windows/SAPI (lecture continue,
# avancement automatique) MAIS sans sa dérive : jamais de moyenne d'essais
# ratés. Un segment n'entre au manifeste que s'il passe la vérification texte ;
# sinon il est rejeté (nouvelle tentative) ou conservé marqué « à réviser ».
GUIDED_OK_SIM = 0.70  # similarité texte minimum pour valider automatiquement
GUIDED_REVIEW_SIM = 0.45  # en dessous : échec -> nouvelle tentative du même prompt
GUIDED_MAX_ATTEMPTS = 3  # après 3 échecs : meilleur (dernier) essai + révision finale


def _normalize_for_match(text: str) -> str:
    """Minuscules, sans accents ni ponctuation — comparable STT <-> texte cible."""
    import unicodedata

    lowered = unicodedata.normalize("NFKD", text.lower())
    deaccented = "".join(c for c in lowered if not unicodedata.combining(c))
    # Apostrophes supprimées (« j'ai » == « jai ») ; le reste de la ponctuation
    # devient un espace puis les espaces doubles sont fusionnés.
    deaccented = deaccented.replace("'", "").replace("\u2019", "")
    return " ".join("".join(c if c.isalnum() else " " for c in deaccented).split())


def text_similarity(a: str, b: str) -> float:
    """Similarité 0..1 (1 = identique) = 1 - distance de Levenshtein normalisée."""
    na, nb = _normalize_for_match(a), _normalize_for_match(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Tableau de Levenshtein (phrases courtes : coût négligeable)
    prev = list(range(len(nb) + 1))
    for i, ca in enumerate(na, start=1):
        curr = [i]
        for j, cb in enumerate(nb, start=1):
            curr.append(
                min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb))
            )
        prev = curr
    return 1.0 - prev[-1] / max(len(na), len(nb))


def is_stutter_command(text: str) -> bool:
    """Détecte la commande vocale « J'ai fourché » (variante « Oups ») dite par l'utilisateur."""
    n = _normalize_for_match(text)
    return "fourche" in n or n in {"oups", "jai rate", "jai foche", "jai fourche"}


class CalibrationStudioWindow(QWidget):
    """Fenêtre d'étalonnage avec transcription GPU immédiate et apprentissage automatique A -> B."""

    def __init__(
        self,
        output_dir: str | Path = "user_data/calibration",
        sample_rate: int = 16000,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.output_dir = Path(output_dir)
        self.samples_dir = self.output_dir / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.output_dir / "manifest.json"
        self.sample_rate = sample_rate
        self.on_close = on_close

        self.prompts = ENRICHED_PROMPTS
        self.current_index = 0
        self.recorded_entries: list[dict] = self._load_existing_manifest()
        self.rule_engine = PhoneticRuleEngine()
        self.vad = SileroVAD()
        # Auto-fin de segment (accessibilité 16/11) : on arrête tout seul dès que
        # la parole est terminée. En studio, aucune hésitation n'est attendue
        # (choix utilisateur 17/11) -> pause courte de 800 ms ; garde-fou 60 s.
        self._auto_segmenter = BreathSegmenter(
            silence_pause_ms=800, min_speech_ms=224, max_segment_s=60.0
        )
        self._auto_stop_requested = False
        self.stt_engine: WhisperDirectMLEngine | None = None

        # --- Mode « Lecture guidée » (zéro clic, 17/11) ---
        self._guided = True  # auto-validation + avancement (désactivable)
        self._attempts = 0  # essais sur le prompt courant (3 max avant révision)
        self._pending_review = False  # le segment en cours sera marqué « à réviser »
        self._last_validated_index = -1  # dernier prompt validé automatiquement
        self._review_ids: list[str] = [
            str(e.get("id")) for e in self.recorded_entries if e.get("review")
        ]
        self._visited_reviews: set[str] = set()  # ids déjà revus (anti-boucle)

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
        # Studio mixte (40+ prompts) : démarrer directement au premier NON enregistré
        # pour ne pas re-sauffer les 12 prompts déjà étalonnés.
        self._load_prompt(self._first_missing_index())

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

    def _first_missing_index(self) -> int:
        """Indice du premier prompt absent du manifeste (0 si tout est enregistré)."""
        recorded_ids = {e.get("id") for e in self.recorded_entries}
        for i, p in enumerate(self.prompts):
            if p.id not in recorded_ids:
                return i
        return 0

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
            QPushButton#playBtn {
                background-color: #475569;
                border-color: #64748b;
                font-size: 15px;
            }
            QPushButton#playBtn:hover {
                background-color: #64748b;
            }
            QPushButton#playBtn:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #334155;
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

        # Mode Lecture guidée (zéro clic) — exigence 17/11
        self.guided_btn = QPushButton("🚀 Lecture guidée : ON")
        self.guided_btn.setCheckable(True)
        self.guided_btn.setChecked(True)
        self.guided_btn.setToolTip(
            "Avancement automatique après vérification texte ; dites « J'ai fourché » "
            "pour rejeter. OFF = validation manuelle (✅/🔄)."
        )
        self.guided_btn.clicked.connect(self._toggle_guided)
        header_row.addWidget(self.guided_btn)

        # File de révision des segments douteux (une seule passe)
        self.review_btn = QPushButton("⚠️ Réviser : 0")
        self.review_btn.clicked.connect(self._goto_next_review)
        self.review_btn.setVisible(False)
        header_row.addWidget(self.review_btn)

        self.progress_label = QLabel("Étape 1 / 12")
        self.progress_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.progress_label.setStyleSheet("color: #38bdf8;")
        header_row.addWidget(self.progress_label)

        self.prev_btn = QPushButton("⬅️ Précédent")
        self.prev_btn.clicked.connect(self._prev_current)
        header_row.addWidget(self.prev_btn)

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

        self.play_btn = QPushButton("🔊 Réécouter mon enregistrement")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setMinimumHeight(46)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_current_audio)
        btn_row.addWidget(self.play_btn)

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

    def _load_prompt(self, index: int, *, auto: bool = False) -> None:
        # Changement de phrase : on repart à zéro côté tentatives ; rechargement
        # du MÊME prompt (« j'ai fourché ») conserve le compteur d'essais.
        if index != self.current_index:
            self._attempts = 0
            # Navigation MANUELLE (⬅️/⏭) : plus de « dernier validé » à rejeter.
            # La navigation automatique (auto=True) garde la référence, même si
            # elle saute des prompts déjà enregistrés.
            if not auto and index != self._last_validated_index + 1:
                self._last_validated_index = -1
        self._pending_review = False
        self.current_index = index
        p = self.prompts[index]
        self.progress_label.setText(f"Étape {index + 1} / {len(self.prompts)}")
        self.prev_btn.setEnabled(index > 0)
        self.skip_btn.setEnabled(True)
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
        self._stop_playback()
        self.play_btn.setEnabled(False)
        self._update_review_button()

    # --- Mode « Lecture guidée » (zéro clic) -------------------------------
    def _toggle_guided(self) -> None:
        self._guided = self.guided_btn.isChecked()
        self.guided_btn.setText(
            "🚀 Lecture guidée : ON" if self._guided else "🚀 Lecture guidée : OFF"
        )
        if not self._guided:
            self.validation_frame.setVisible(self._current_audio is not None)

    def _update_review_button(self) -> None:
        n = len(self._review_ids)
        self.review_btn.setText(f"⚠️ Réviser : {n}")
        self.review_btn.setVisible(n > 0)

    def _guided_decide(self) -> None:
        """Décision automatique après transcription (mode guidé) — zéro clic.

        1. « J'ai fourché » -> rejet (segment courant, ou le dernier validé si
           on vient déjà d'avancer d'une phrase) ;
        2. similarité texte OK -> validation + passage à la suite ;
        3. doute -> validation MARQUÉE « à réviser » (fin de session) ;
        4. échec -> nouvelle tentative du même prompt (jamais de moyenne),
           3 échecs -> dernier essai conservé + marqué à réviser.
        """
        p = self.prompts[self.current_index]
        target = self.target_edit.text().strip() or p.expected_text
        heard = self._current_heard_text
        self._attempts += 1

        # 1) Commande vocale « J'ai fourché »
        if is_stutter_command(heard):
            just_advanced = self._last_validated_index == self.current_index - 1
            if just_advanced and text_similarity(heard, target) < GUIDED_REVIEW_SIM:
                # On est déjà sur la phrase suivante : il parle de la PREMIÈRE
                # (validée automatiquement) -> on la rejette et on la relit.
                self._reject_last_validated()
            else:
                # Phrase en cours lue puis signalée (ou aucun validé) -> reprise.
                self.heard_label.setText("🗑️ Segment rejeté à votre demande — relisez la phrase")
                self._discard_and_retry()
            return

        # 2-4) Vérification texte
        sim = text_similarity(heard, target) if heard else 0.0
        if sim >= GUIDED_OK_SIM:
            self._pending_review = False
            self.heard_label.setText(
                f"✅ Accepté automatiquement ({sim:.0%}) — passage à la phrase suivante"
            )
            self._validate_and_next()
        elif sim >= GUIDED_REVIEW_SIM:
            self._pending_review = True
            self.heard_label.setText(
                f"⚠️ Doute ({sim:.0%}) — conservé, à RÉVISER en fin de session (bouton ⚠️)"
            )
            self._validate_and_next()
        elif self._attempts >= GUIDED_MAX_ATTEMPTS:
            self._pending_review = True
            self.heard_label.setText(
                f"⚠️ {GUIDED_MAX_ATTEMPTS} essais — dernier essai conservé, marqué à RÉVISER"
            )
            self._validate_and_next()
        else:
            self._guided_retry()

    def _guided_retry(self) -> None:
        """Échec : abandonne l'audio (aucune moyenne) et reprend le MÊME prompt."""
        attempts = self._attempts
        self._discard_and_retry()
        self.heard_label.setText(
            f"❌ Pas reconnu ({attempts}/{GUIDED_MAX_ATTEMPTS} essai) — recommencez la même phrase"
        )

    def _reject_last_validated(self) -> None:
        """Rejette le dernier segment validé automatiquement et revient dessus."""
        idx = self._last_validated_index
        if idx < 0 or idx >= len(self.prompts):
            return
        pid = self.prompts[idx].id
        self._stop_playback()
        self._recorded_entries_discard(pid)
        if pid in self._review_ids:
            self._review_ids.remove(pid)
        self._last_validated_index = -1
        self.heard_label.setText("🗑️ Dernière phrase rejetée — relisez-la")
        self._load_prompt(idx)
        QTimer.singleShot(700, self._auto_start_recording)

    def _next_guided_index(self) -> int | None:
        """Prochain prompt à faire : non enregistré, ou restant en file de révision."""
        recorded = {e.get("id") for e in self.recorded_entries}
        for i in range(self.current_index + 1, len(self.prompts)):
            p = self.prompts[i]
            if p.id not in recorded or p.id in self._review_ids:
                return i
        # Fin de la file : un ou plusieurs segments restent à réviser ?
        for i, p in enumerate(self.prompts):
            if p.id in self._review_ids:
                return i
        return None

    def _goto_next_review(self) -> None:
        """Va écouter (et éventuellement refaire) le premier segment douteux."""
        if not self._review_ids:
            return
        pid = self._review_ids.pop(0)
        self._visited_reviews.add(pid)
        self._update_review_button()
        idx = next(
            (i for i, p in enumerate(self.prompts) if p.id == pid), None
        )
        if idx is None:
            return
        self._load_prompt(idx)
        entry = next((e for e in self.recorded_entries if e.get("id") == pid), None)
        audio = None
        if entry is not None:
            audio = self._load_wav(Path(str(entry.get("raw_wav", ""))))
        if audio is not None:
            self._current_audio = audio
            self.play_btn.setEnabled(True)
            self.validation_frame.setVisible(True)
            self.heard_label.setText(
                "⚠️ Segment douteux : 🔊 Écoutez, puis ✅ garder ou 🔄 refaire"
            )
        else:
            self.heard_label.setText("⚠️ Segment douteux : ré-enregistrez-le")
            QTimer.singleShot(500, self._auto_start_recording)

    def _recorded_entries_discard(self, pid: str) -> None:
        """Retire une entrée du manifeste (rejet) et réécrit le fichier."""
        self.recorded_entries = [
            e for e in self.recorded_entries if e.get("id") != pid
        ]
        self._save_manifest()

    def _save_manifest(self) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(
                {"samples": self.recorded_entries}, f, ensure_ascii=False, indent=2
            )

    def _load_wav(self, path: Path) -> np.ndarray | None:
        try:
            with wave.open(str(path), "rb") as wf:
                data = wf.readframes(wf.getnframes())
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            return audio if audio.size else None
        except Exception:
            return None

    def _skip_current(self) -> None:
        if self.current_index + 1 < len(self.prompts):
            self._load_prompt(self.current_index + 1)
        else:
            self.close()

    def _prev_current(self) -> None:
        if self.current_index > 0:
            self._load_prompt(self.current_index - 1)

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

        # Auto-fin de segment : la fin de la parole est détectée par le VAD ici
        # (thread audio) ; l'arrêt réel est fait dans `_update_meter` (thread GUI).
        for start in range(0, len(mono) - CHUNK_SAMPLES + 1, CHUNK_SAMPLES):
            if self._auto_segmenter.feed_chunk(mono[start : start + CHUNK_SAMPLES]) is not None:
                self._auto_stop_requested = True
                break

    def _update_meter(self) -> None:
        if self._auto_stop_requested and self._is_recording:
            # Fin de parole détectée automatiquement -> arrêt sans clic.
            self._auto_stop_requested = False
            self.peak_info_label.setText("⏹ Fin détectée — analyse en cours…")
            self._stop_recording()
            return
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
            self._auto_stop_requested = False
            self._auto_segmenter.reset()
            self._stop_playback()
            self.play_btn.setEnabled(False)
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
                "🎙️ Parlez… l'arrêt est AUTOMATIQUE après la fin de votre phrase"
            )
            self.record_btn.setStyleSheet(
                "background-color: #2563eb; border-color: #3b82f6; font-size: 16px;"
            )
        else:
            self._stop_recording()

    def _stop_recording(self) -> None:
        """Arrête la capture (clic ou fin de parole automatique) et analyse l'audio."""
        self._is_recording = False
        self._auto_stop_requested = False
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

            if self._guided:
                # Lecture guidée : la décision (accepter / doute / rejeter) est
                # prise ici, sans aucun clic — voir `_guided_decide`.
                self.record_btn.setEnabled(False)
                self.record_btn.setText("🚀 Lecture guidée — décision automatique…")
                self.record_btn.setStyleSheet("background-color: #334155;")
                self._guided_decide()
                return

            self.heard_label.setText(
                f"Entendu par Whisper ({res.total_ms:.0f} ms) : « {res.text} »  ➔  Sera associé à : « {target_txt} »"
            )
        elif self._guided:
            self.heard_label.setText(
                "⏳ Moteur pas encore chargé — validation manuelle en attendant"
            )

        self.record_btn.setEnabled(False)
        self.record_btn.setText("Enregistrement analysé — Validez ci-dessous :")
        self.record_btn.setStyleSheet("background-color: #334155;")
        self.play_btn.setEnabled(True)
        self.validation_frame.setVisible(True)

    def _play_current_audio(self) -> None:
        """Réécoute l'enregistrement en cours pour trancher : valider ou rejeter."""
        if self._current_audio is None or self._current_audio.size == 0:
            return
        sd.stop()
        sd.play(self._current_audio, self.sample_rate)

    def _stop_playback(self) -> None:
        try:
            sd.stop()
        except Exception:
            pass

    def _discard_and_retry(self) -> None:
        self._stop_playback()
        self.play_btn.setEnabled(False)
        self._current_audio = None
        self.vu_bar.setValue(0)
        self.peak_info_label.setText("Prêt à ré-enregistrer")
        self._load_prompt(self.current_index)
        # Reprise automatique : on ré-enregistre le MÊME prompt sans clic.
        QTimer.singleShot(500, self._auto_start_recording)

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
        self._stop_playback()
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
            "review": bool(self._pending_review),
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
        # File de révision : une seule passe (jamais de boucle) — un segment
        # déjà revisité n'y revient pas, même s'il reste douteux.
        if self._pending_review:
            if p.id not in self._review_ids and p.id not in self._visited_reviews:
                self._review_ids.append(p.id)
        elif p.id in self._review_ids:
            self._review_ids.remove(p.id)
        self._update_review_button()
        self._save_manifest()
        self._last_validated_index = self.current_index

        if self._guided:
            # Lecture guidée : saute les prompts déjà enregistrés, puis les
            # segments restant à réviser ; fin de file -> fermeture.
            nxt = self._next_guided_index()
            if nxt is None:
                self.close()
            else:
                self._load_prompt(nxt, auto=True)
                QTimer.singleShot(500, self._auto_start_recording)
        elif self.current_index + 1 < len(self.prompts):
            self._load_prompt(self.current_index + 1)
            # Enchaînement AUTOMATIQUE sur l'enregistrement suivant : pas de
            # clic « Démarrer » supplémentaire (contrainte d'accessibilité 16/11).
            QTimer.singleShot(500, self._auto_start_recording)
        else:
            self.close()

    def _auto_start_recording(self) -> None:
        """Démarre l'enregistrement sans clic (après validation ou reprise)."""
        if not self._is_recording and self._current_audio is None:
            self._toggle_recording()

    def closeEvent(self, event) -> None:  # noqa: N802 (API Qt)
        """Fermeture (✕, « Terminer » ou fin de liste) -> callback (réveil dictée)."""
        self._stop_playback()
        if self.on_close is not None:
            try:
                self.on_close()
            except Exception:
                pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    win = CalibrationStudioWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
