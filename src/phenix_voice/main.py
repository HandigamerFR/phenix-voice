"""Point d'entrée principal de Phénix Voice (Phase 2 : Arbitre de Plausibilité, Shadow Buffer,
Correction Anti-Dérive & Contrôle Micro 3 États sans conflit avec Dragon).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import time
import wave
import numpy as np
from PySide6.QtWidgets import QApplication

from phenix_voice.audio.capture import MicrophoneCapture
from phenix_voice.audio.fingerprints import AcousticCommandProtector
from phenix_voice.audio.vad import BreathSegmenter
from phenix_voice.os_control.hotkeys import GlobalInputMonitor
from phenix_voice.os_control.shadow_buffer import ShadowBuffer
from phenix_voice.postprocess.plausibility import PlausibilityArbitrator
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
)
from phenix_voice.stt.engine import WhisperDirectMLEngine
from phenix_voice.ui.hud import MicState, PhenixHUD


class PhenixVoiceController:
    """Orchestrateur temps réel :
    Capture Micro -> Silero VAD -> Whisper GPU AMD -> Arbitre de Plausibilité -> Shadow Buffer & HUD.
    """

    def __init__(
        self,
        model_repo: str = "onnx-community/whisper-large-v3-turbo",
        initial_prompt: str | None = None,
        start_sleeping: bool = False,
        start_muted: bool = False,
        strict_dictionary: bool = False,
    ) -> None:
        self.model_repo = model_repo
        self.initial_prompt = initial_prompt
        self.is_sleeping = start_sleeping
        self.is_muted = start_muted
        self._running = True

        # État du volet de correction Phase 2
        self._correction_open = False
        self._learn_on_correction = True  # True = Corriger & Apprendre (LoRA), False = Oups (Sans apprendre)

        self.shadow_buffer = ShadowBuffer()
        self.arbitrator = PlausibilityArbitrator(
            enable_strict_dictionary=strict_dictionary
        )
        self.processor = HybridPunctuationProcessor(
            enable_strict_dictionary=strict_dictionary
        )
        self.protector = AcousticCommandProtector()
        self.engine: WhisperDirectMLEngine | None = None

        self._segment_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=32)

        self.hud = PhenixHUD(
            on_toggle_mute=self.toggle_mute,
            on_toggle_sleep=self.toggle_sleep,
            on_open_correction=self.open_correction_for_last,
            on_oups_scratch=self.oups_scratch_without_learning,
            on_select_alternative=self.apply_correction_choice,
            on_toggle_learn_mode=self.toggle_correction_learn_mode,
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
            on_toggle_mute=self.toggle_mute,
            on_toggle_sleep=self.toggle_sleep,
            on_cursor_moved=self._on_cursor_moved,
        )

        self._stt_thread = threading.Thread(
            target=self._stt_worker_loop, name="PhenixSTTWorker", daemon=True
        )

    def start(self) -> None:
        self.hud.show()
        self.hud.set_state(MicState.LOADING)
        self._stt_thread.start()

    def _on_cursor_moved(self) -> None:
        self.processor.reset_context()
        self.shadow_buffer.clear_context()

    def _on_speech_state_change(self, speaking: bool) -> None:
        if self.engine is None or not self._running or self.is_muted or self.is_sleeping:
            return
        if speaking:
            self.hud.set_state(MicState.SPEAKING)
        else:
            self.hud.set_state(MicState.LISTENING)

    def _on_segment_ready(self, segment: np.ndarray) -> None:
        if not self._running or self.engine is None or self.is_muted:
            return
        try:
            self._segment_queue.put_nowait(segment)
        except queue.Full:
            pass

    def toggle_mute(self) -> None:
        """Allume ou coupe totalement le micro (F8 ou bouton sur la barre)."""
        if self.engine is None:
            return
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.capture.set_paused(True)
            self._close_correction_bar()
            self.hud.set_state(MicState.MUTED)
        else:
            self.is_sleeping = False
            self.capture.set_paused(False)
            self.processor.reset_context()
            self.hud.set_state(MicState.LISTENING)

    def mute_mic_completely(self) -> None:
        """Coupe totalement le micro (appelé par la commande vocale « Couper Phénix »)."""
        if self.engine is None:
            return
        self.is_muted = True
        self.capture.set_paused(True)
        self._close_correction_bar()
        self.hud.set_state(MicState.MUTED)

    def toggle_sleep(self) -> None:
        """Bascule entre Écoute Active et Veille vocale (« Phénix repos » / F9)."""
        if self.engine is None:
            return
        if self.is_muted:
            # Si le micro était coupé, F9 le passe en veille vocale
            self.is_muted = False
            self.is_sleeping = True
            self.capture.set_paused(False)
            self.hud.set_state(MicState.SLEEPING)
            return

        self.is_sleeping = not self.is_sleeping
        if self.is_sleeping:
            self._close_correction_bar()
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.processor.reset_context()
            self.hud.set_state(MicState.LISTENING)

    def open_correction_for_last(self) -> None:
        """Ouvre le volet de correction sur le dernier segment dicté."""
        last = self.shadow_buffer.last_segment
        if last is None:
            self.hud.set_transcript("[Aucun segment récent à corriger]", 0.0)
            return
        self._correction_open = True
        self._learn_on_correction = True
        self.hud.show_correction_panel(
            last.injected_text,
            last.alternatives[:3],
            learn_enabled=self._learn_on_correction,
        )

    def toggle_correction_learn_mode(self) -> None:
        """Bascule entre « Corriger & Apprendre » et « Corriger SANS apprendre (Oups) »."""
        self._learn_on_correction = not self._learn_on_correction
        last = self.shadow_buffer.last_segment
        if last is not None and self._correction_open:
            self.hud.show_correction_panel(
                last.injected_text,
                last.alternatives[:3],
                learn_enabled=self._learn_on_correction,
            )

    def apply_correction_choice(self, choice_1_based: int) -> None:
        """Remplace le dernier segment par l'alternative choisie (1, 2 ou 3)."""
        last = self.shadow_buffer.last_segment
        if last is None:
            return
        idx = choice_1_based - 1
        if idx < 0 or idx >= len(last.alternatives):
            return
        replacement = last.alternatives[idx]
        self._perform_replacement(replacement, learn=self._learn_on_correction)

    def _perform_replacement(self, new_text: str, learn: bool) -> None:
        old_seg, new_seg = self.shadow_buffer.replace_last(
            new_text, discard_audio=not learn
        )
        self._close_correction_bar()
        if old_seg is not None and learn and old_seg.audio_pcm is not None:
            self._save_learned_correction_sample(
                old_seg.audio_pcm, old_seg.raw_text, new_text
            )
            mode_tag = "🧠 Corrigé & Appris pour LoRA"
        else:
            mode_tag = "🛡️ Corrigé SANS apprendre (Audio écarté)"

        self.hud.set_transcript(new_text, 0.0, f"[{mode_tag}]")

    def oups_scratch_without_learning(self) -> None:
        """Efface immédiatement le dernier souffle et détruit son audio (protection anti-dérive)."""
        self._close_correction_bar()
        erased = self.shadow_buffer.scratch_last(discard_audio=True)
        if erased is not None:
            self.hud.set_transcript(
                "[Souffle effacé — Audio détruit (« Oups, j'ai fourché »)]", 0.0
            )

    def _close_correction_bar(self) -> None:
        if self._correction_open:
            self._correction_open = False
            self.hud.hide_correction_panel()

    def _save_learned_correction_sample(
        self, audio_pcm: np.ndarray, heard_text: str, corrected_text: str
    ) -> None:
        """Enregistre le couple (Audio WAV, Texte corrigé) validé pour le futur Fine-Tuning LoRA."""
        try:
            out_dir = Path("user_data/corrections_learned")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            wav_path = out_dir / f"corr_{ts}.wav"
            pcm16 = np.clip(audio_pcm * 32767.0, -32768, 32767).astype(np.int16)
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm16.tobytes())

            with open(out_dir / "corrections_log.jsonl", "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "timestamp": ts,
                            "wav": str(wav_path),
                            "heard_text": heard_text,
                            "corrected_text": corrected_text,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

    def _stt_worker_loop(self) -> None:
        self.engine = WhisperDirectMLEngine(repo_id=self.model_repo)
        self.input_monitor.start()
        self.capture.start()

        if self.is_muted:
            self.capture.set_paused(True)
            self.hud.set_state(MicState.MUTED)
        elif self.is_sleeping:
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.hud.set_state(MicState.LISTENING)
            self.hud.set_transcript(
                "Prêt — Dites « Phénix repos », « Couper Phénix », « Corriger ça », ou appuyez sur F8",
                0.0,
            )

        while self._running:
            segment = self._segment_queue.get()
            if segment is None or not self._running:
                break
            if self.is_muted:
                continue

            if not self.is_sleeping:
                self.hud.set_state(MicState.TRANSCRIBING)

            fp_match = self.protector.match_command(segment)
            result = self.engine.transcribe(
                segment, initial_prompt=self.initial_prompt
            )

            recent_ctx = (
                self.shadow_buffer.last_segment.injected_text
                if self.shadow_buffer.last_segment
                else ""
            )
            arbitrated = self.arbitrator.arbitrate(
                raw_text=result.text,
                alternatives=result.alternatives,
                acoustic_confidence=result.confidence,
                audio_duration_s=result.audio_duration_s,
                recent_context_text=recent_ctx,
                acoustic_fp_match=fp_match,
            )

            if not arbitrated.best_text:
                if not self.is_sleeping and not self.is_muted:
                    self.hud.set_state(MicState.LISTENING)
                continue

            processed = self.processor.process(
                arbitrated.best_text, is_sleeping=self.is_sleeping
            )

            # Journalisation diagnostique
            try:
                log_dir = Path("logs")
                log_dir.mkdir(parents=True, exist_ok=True)
                with open(log_dir / "dictation_debug.jsonl", "a", encoding="utf-8") as lf:
                    lf.write(
                        json.dumps(
                            {
                                "ts": time.strftime("%H:%M:%S"),
                                "dur_s": round(result.audio_duration_s, 2),
                                "ms": round(result.total_ms, 0),
                                "raw_stt": result.text,
                                "arbitrated": arbitrated.best_text,
                                "plaus": round(arbitrated.plausibility_score, 2),
                                "conf": round(result.confidence, 2),
                                "intent": processed.intent.value,
                                "injected": processed.text_to_inject,
                                "alts": arbitrated.ranked_alternatives[:3],
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception:
                pass

            # Routage des intentions
            if processed.intent == VoiceIntentType.MUTE_MIC:
                self.mute_mic_completely()
                continue

            if processed.intent == VoiceIntentType.SLEEP:
                self.is_sleeping = True
                self._close_correction_bar()
                self.hud.set_state(MicState.SLEEPING)
                continue

            if processed.intent == VoiceIntentType.WAKE:
                self.is_sleeping = False
                self.processor.reset_context()
                self.hud.set_state(MicState.LISTENING)
                self.hud.set_transcript(
                    "Écoute reprise — Parlez librement", result.total_ms
                )
                continue

            if processed.intent == VoiceIntentType.PRESS_ENTER:
                self._close_correction_bar()
                self.shadow_buffer.press_enter_key()
                self.hud.set_transcript("[Touche Entrée ↵]", result.total_ms)
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.OUPS_NO_LEARN:
                if self._correction_open:
                    # Si le volet de correction est ouvert, « Oups » le passe en mode SANS apprendre
                    self._learn_on_correction = False
                    last = self.shadow_buffer.last_segment
                    if last:
                        self.hud.show_correction_panel(
                            last.injected_text,
                            last.alternatives[:3],
                            learn_enabled=False,
                        )
                else:
                    self.oups_scratch_without_learning()
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.SCRATCH_LAST:
                self._close_correction_bar()
                self.shadow_buffer.scratch_last(discard_audio=False)
                self.hud.set_transcript("[Dernier souffle effacé]", result.total_ms)
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.OPEN_CORRECTION:
                if processed.target_arg:
                    self.shadow_buffer.select_word_in_last_segments(processed.target_arg)
                self.open_correction_for_last()
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.CHOOSE_ALT:
                self.apply_correction_choice(processed.choice_index)
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.SELECT_TARGET:
                ok = self.shadow_buffer.select_word_in_last_segments(
                    processed.target_arg
                )
                msg = (
                    f"[Sélectionné : « {processed.target_arg} »]"
                    if ok
                    else f"[Mot introuvable : « {processed.target_arg} »]"
                )
                self.hud.set_transcript(msg, result.total_ms)
                self.hud.set_state(MicState.LISTENING)
                continue

            # Dictée de texte : si le volet « Corriger ça » était ouvert, ce nouveau souffle
            # remplace directement l'ancien segment !
            if (
                processed.intent == VoiceIntentType.DICTATION
                and processed.text_to_inject
            ):
                if self._correction_open:
                    self._perform_replacement(
                        processed.text_to_inject.lstrip(" "),
                        learn=self._learn_on_correction,
                    )
                else:
                    self.shadow_buffer.inject_and_record(
                        text_to_inject=processed.text_to_inject,
                        raw_text=result.text,
                        alternatives=arbitrated.ranked_alternatives[:3],
                        audio_pcm=segment,
                    )
                    alt_preview = (
                        f"(Alt: {arbitrated.ranked_alternatives[0]})"
                        if arbitrated.ranked_alternatives
                        else ""
                    )
                    self.hud.set_transcript(
                        processed.text_to_inject, result.total_ms, alt_preview
                    )

            if not self.is_sleeping and not self.is_muted:
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
        default=None,
        help="Prompt lexical initial pour orienter le vocabulaire",
    )
    parser.add_argument(
        "--sleep",
        action="store_true",
        help="Démarrer en mode veille vocale (« Phénix repos »)",
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        help="Démarrer avec le micro totalement coupé (OFF — activer par F8 ou clic)",
    )
    parser.add_argument(
        "--strict-dict",
        action="store_true",
        help="Activer le dictionnaire déterministe A->B à 100 %% (désactivé par défaut au profit de l'Arbitre de Plausibilité)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = PhenixVoiceController(
        model_repo=args.model,
        initial_prompt=args.prompt,
        start_sleeping=args.sleep,
        start_muted=args.mute,
        strict_dictionary=args.strict_dict,
    )
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
