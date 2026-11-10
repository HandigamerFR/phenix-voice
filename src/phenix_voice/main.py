"""Point d'entrée principal de Phénix Voice (Phase 1 : Socle Audio, GPU AMD & Dictée Universelle)."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import numpy as np
from PySide6.QtWidgets import QApplication

from phenix_voice.audio.capture import MicrophoneCapture
from phenix_voice.audio.vad import BreathSegmenter
from phenix_voice.os_control.hotkeys import GlobalInputMonitor
from phenix_voice.os_control.injector import DirectTextInjector
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
)
from phenix_voice.stt.engine import WhisperDirectMLEngine
from phenix_voice.ui.hud import MicState, PhenixHUD


class PhenixVoiceController:
    """Orchestrateur temps réel : Capture Micro -> Silero VAD -> Whisper GPU AMD -> SendInput."""

    def __init__(
        self,
        model_repo: str = "onnx-community/whisper-large-v3-turbo",
        initial_prompt: str | None = None,
        start_sleeping: bool = False,
    ) -> None:
        self.model_repo = model_repo
        self.initial_prompt = initial_prompt
        self.is_sleeping = start_sleeping
        self._running = True

        self.injector = DirectTextInjector()
        self.processor = HybridPunctuationProcessor()
        self.engine: WhisperDirectMLEngine | None = None

        self._segment_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=32)

        self.hud = PhenixHUD(
            on_toggle_sleep=self.toggle_sleep,
            on_scratch_last=self.scratch_last_utterance,
            on_quit=self.shutdown,
        )

        self.segmenter = BreathSegmenter(
            on_speech_state_change=self._on_speech_state_change
        )
        self.capture = MicrophoneCapture(
            on_segment_ready=self._on_segment_ready,
            segmenter=self.segmenter,
        )
        self.input_monitor = GlobalInputMonitor(
            on_toggle_mic=self.toggle_sleep,
            on_cursor_moved=self.processor.reset_context,
        )

        self._stt_thread = threading.Thread(
            target=self._stt_worker_loop, name="PhenixSTTWorker", daemon=True
        )

    def start(self) -> None:
        """Affiche la barre flottante No-Focus et lance l'initialisation GPU en arrière-plan."""
        self.hud.show()
        self.hud.set_state(MicState.LOADING)
        self._stt_thread.start()

    def _on_speech_state_change(self, speaking: bool) -> None:
        if self.engine is None or not self._running:
            return
        if self.is_sleeping:
            return
        if speaking:
            self.hud.set_state(MicState.SPEAKING)
        else:
            self.hud.set_state(MicState.LISTENING)

    def _on_segment_ready(self, segment: np.ndarray) -> None:
        if not self._running or self.engine is None:
            return
        try:
            self._segment_queue.put_nowait(segment)
        except queue.Full:
            pass

    def toggle_sleep(self) -> None:
        """Bascule entre le mode Écoute Active et le mode Veille (« Au repos »)."""
        if self.engine is None:
            return
        self.is_sleeping = not self.is_sleeping
        if self.is_sleeping:
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.processor.reset_context()
            self.hud.set_state(MicState.LISTENING)

    def scratch_last_utterance(self) -> None:
        """Efface le dernier souffle dicté dans la fenêtre active."""
        erased = self.injector.scratch_last()
        if erased:
            self.hud.set_transcript("[Dernier souffle effacé]", 0.0)

    def _stt_worker_loop(self) -> None:
        # 1. Chargement et pré-chauffage du modèle Whisper sur la Radeon RX 5700 XT
        self.engine = WhisperDirectMLEngine(repo_id=self.model_repo)
        self.input_monitor.start()
        self.capture.start()

        if self.is_sleeping:
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.hud.set_state(MicState.LISTENING)
            self.hud.set_transcript(
                "Prêt — Dictez dans n'importe quelle fenêtre (ou dites « Au repos » / « Oups »)",
                0.0,
            )

        # 2. Boucle de transcription des souffles
        while self._running:
            segment = self._segment_queue.get()
            if segment is None or not self._running:
                break

            if not self.is_sleeping:
                self.hud.set_state(MicState.TRANSCRIBING)

            result = self.engine.transcribe(
                segment, initial_prompt=self.initial_prompt
            )

            if not result.text:
                if not self.is_sleeping:
                    self.hud.set_state(MicState.LISTENING)
                continue

            processed = self.processor.process(
                result.text, is_sleeping=self.is_sleeping
            )

            if processed.intent == VoiceIntentType.SLEEP:
                self.is_sleeping = True
                self.hud.set_state(MicState.SLEEPING)
                continue

            if processed.intent == VoiceIntentType.WAKE:
                self.is_sleeping = False
                self.processor.reset_context()
                self.hud.set_state(MicState.LISTENING)
                self.hud.set_transcript(
                    "Écoute reprise — Parlez normalement", result.total_ms
                )
                continue

            if processed.intent == VoiceIntentType.SCRATCH_LAST:
                self.scratch_last_utterance()
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.DICTATION and processed.text_to_inject:
                self.injector.inject_text(processed.text_to_inject)
                alt_preview = (
                    f"(Alt: {result.alternatives[0]})"
                    if result.alternatives
                    else ""
                )
                self.hud.set_transcript(
                    processed.text_to_inject, result.total_ms, alt_preview
                )

            if not self.is_sleeping:
                self.hud.set_state(MicState.LISTENING)

    def shutdown(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._segment_queue.put_nowait(None)
        except queue.Full:
            pass
        self.input_monitor.stop()
        self.capture.stop()
        self.hud.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phénix Voice — Dictée universelle adaptative accélérée sur GPU AMD"
    )
    parser.add_argument(
        "--model",
        default="onnx-community/whisper-large-v3-turbo",
        help="Identifiant HuggingFace du modèle ONNX Whisper",
    )
    parser.add_argument(
        "--prompt",
        default="Phénix Voice, OpenCode, Windows, dictée vocale.",
        help="Prompt lexical initial pour orienter le vocabulaire",
    )
    parser.add_argument(
        "--sleep",
        action="store_true",
        help="Démarrer en mode veille (« Au repos »)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = PhenixVoiceController(
        model_repo=args.model,
        initial_prompt=args.prompt,
        start_sleeping=args.sleep,
    )
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
