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
    text_to_nato_spelling,
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
        self._learn_on_correction = True  # True = Corriger & Apprendre (LoRA), False = Annuler sans apprendre
        self._help_visible = False
        self._pending_correction_text = ""
        self._spelling_mode = False  # Mode épellation (alphabet radio international)

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
            on_apply_manual_correction=self.apply_manual_correction,
            on_toggle_help=self.toggle_help,
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
        self._pending_correction_text = last.injected_text.strip()
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

    def apply_manual_correction(self, new_text: str) -> None:
        """Applique la correction saisie manuellement dans le champ du volet de correction."""
        cleaned = new_text.strip()
        if cleaned:
            self._pending_correction_text = cleaned
            self._perform_replacement(cleaned, learn=self._learn_on_correction)

    def apply_pending_correction(self) -> None:
        """Valide explicitement la correction en attente (proposition dictée ou texte courant du volet)."""
        if not self._correction_open:
            self.hud.set_transcript("[Aucune correction en cours à valider]", 0.0)
            return
        text = self._pending_correction_text.strip()
        if not text:
            last = self.shadow_buffer.last_segment
            text = last.injected_text.strip() if last else ""
        if text:
            self._perform_replacement(text, learn=self._learn_on_correction)

    def toggle_help(self) -> None:
        self._help_visible = not self._help_visible
        self.hud.show_help(self._build_help_text(), self._help_visible)

    def _close_help(self) -> None:
        if self._help_visible:
            self._help_visible = False
            self.hud.show_help("", False)

    def _build_help_text(self) -> str:
        common = (
            "• <b>F8</b> ou <b>« Couper Phénix »</b> : allumer/couper totalement le micro<br>"
            "• <b>F9</b> : basculer Écoute active / Veille vocale<br>"
            "• <b>« Que puis-je dire ? »</b> : afficher/masquer cette aide"
        )
        spelling_note = (
            "• <b>« Mode épellation »</b> : épeler avec l’alphabet radio (Alpha, Bravo, Charlie…)<br>"
            "• <b>« Fin épellation »</b> / <b>« Mode dictée »</b> : revenir à la dictée normale<br>"
        )
        if self.is_muted:
            state = "<b>État : MICRO COUPÉ (OFF)</b><br>Le micro n'écoute rien. Réactivez-le avec <b>F8</b> ou le bouton <b>[🔌 Micro ON/OFF (F8)]</b>."
            cmds = common
        elif self.is_sleeping:
            state = "<b>État : VEILLE VOCALE (« Phénix repos »)</b>"
            cmds = (
                "• <b>« Phénix écoute »</b> : reprendre la dictée<br>"
                "• <b>« Couper Phénix »</b> / <b>« Éteindre Phénix »</b> : couper totalement le micro<br>"
                + common
            )
        elif self._spelling_mode:
            state = "<b>État : MODE ÉPELLATION (alphabet radio international)</b>"
            cmds = (
                "• Dites <b>Alpha, Bravo, Charlie…</b> pour épeler des lettres (utile en correction, en double avec le clavier)<br>"
                "• <b>« Chiffre un / Chiffre 5 »</b> : insérer le caractère numérique (1, 5…)<br>"
                "• <b>« En lettres un »</b> ou <b>« Mot un »</b> : insérer le mot littéral « un » (pas le chiffre)<br>"
                "• <b>« Espace »</b> : insérer un espace<br>"
                "• <b>« Fin épellation »</b> ou <b>« Mode dictée »</b> : revenir à la dictée normale<br>"
                "• <b>« Valider la correction »</b> : appliquer la correction si le volet est ouvert<br>"
                "• <b>« Corriger ça »</b>, <b>« Effacer ça »</b>, <b>« Annuler sans apprendre »</b> restent disponibles<br>"
                + common
            )
        elif self._correction_open:
            state = "<b>État : CORRECTION DU DERNIER SEGMENT</b>"
            cmds = (
                "• <b>« Choisir un / deux / trois »</b> ou clic souris : remplacer par l'alternative proposée<br>"
                "• <b>Re-dicter la phrase</b> : propose une nouvelle correction dans le champ (PAS appliquée automatiquement)<br>"
                "• <b>« Valider la correction »</b> (ou bouton <b>[Appliquer la correction]</b>) : appliquer explicitement la correction<br>"
                "• <b>Modifier le texte dans le champ</b> puis <b>[Appliquer la correction]</b> : correction manuelle précise<br>"
                "• <b>« Mode épellation »</b> : épeler en alphabet radio (Alpha, Bravo…) pour corriger lettre par lettre<br>"
                "• <b>« Annuler sans apprendre »</b> ou bascule du bouton : passer en mode <b>SANS apprendre</b> (ne pollue pas le profil)<br>"
                "• <b>« Effacer ça »</b> : annuler le segment<br>"
                "• <b>« Phénix repos »</b> : mettre en veille, <b>« Couper Phénix »</b> : couper le micro<br>"
                + common
            )
        else:
            state = "<b>État : ÉCOUTE ACTIVE (dictée libre)</b>"
            cmds = (
                "• <b>Dictée libre</b> : parlez normalement, le texte s'écrit dans la fenêtre active<br>"
                "• La ponctuation finale n'est plus forcée automatiquement ; dictez <b>« point »</b>, <b>« virgule »</b>, <b>« point d'interrogation »</b> etc. quand vous le souhaitez<br>"
                + spelling_note
                + "• <b>« Phénix repos »</b> : mettre en veille vocale (sans conflit avec Dragon)<br>"
                "• <b>« Couper Phénix »</b> / <b>« Éteindre Phénix »</b> : couper totalement le micro<br>"
                "• <b>« Corriger ça »</b> : ouvrir les alternatives (1/2/3) et la correction manuelle du dernier souffle<br>"
                "• <b>« Effacer ça »</b> : supprimer le dernier souffle<br>"
                "• <b>« Annuler sans apprendre »</b> : effacer le dernier souffle SANS apprendre (bafouillage / fausse manip)<br>"
                "• <b>« Presser Entrée »</b> : appuyer sur Entrée<br>"
                "• <b>« Point à la ligne »</b>, <b>« Nouveau paragraphe »</b>, <b>« Virgule »</b>, <b>« Point d'interrogation »</b> etc.<br>"
                + common
            )
        return f"{state}<br><br>{cmds}"

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
                "[Souffle effacé — Audio détruit (« Annuler sans apprendre »)]", 0.0
            )

    def _close_correction_bar(self) -> None:
        if self._correction_open:
            self._correction_open = False
            self._pending_correction_text = ""
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
            self.hud.set_transcript(
                "Micro coupé — Appuyez sur F8 ou dites « Que puis-je dire ? » (après réactivation) pour l'aide",
                0.0,
            )
        elif self.is_sleeping:
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.hud.set_state(MicState.LISTENING)
            self.hud.set_transcript(
                "Prêt — Dites « Que puis-je dire ? » pour l'aide, « Mode épellation » pour épeler, ou « Couper Phénix »",
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

            if processed.intent == VoiceIntentType.SHOW_HELP:
                self.toggle_help()
                if self.is_muted:
                    self.hud.set_state(MicState.MUTED)
                elif self.is_sleeping:
                    self.hud.set_state(MicState.SLEEPING)
                else:
                    self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.ENTER_SPELLING:
                self._spelling_mode = True
                self.hud.set_transcript(
                    "Mode épellation activé — dites Alpha, Bravo, Charlie… (« Fin épellation » pour quitter)",
                    result.total_ms,
                )
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.EXIT_SPELLING:
                self._spelling_mode = False
                self.hud.set_transcript(
                    "Mode épellation désactivé — retour à la dictée normale",
                    result.total_ms,
                )
                self.hud.set_state(MicState.LISTENING)
                continue

            if processed.intent == VoiceIntentType.SLEEP:
                self.is_sleeping = True
                self._spelling_mode = False
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
                    # Si le volet de correction est ouvert, « Annuler sans apprendre » le passe en mode SANS apprendre
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

            if processed.intent == VoiceIntentType.APPLY_CORRECTION:
                if self._correction_open:
                    self.apply_pending_correction()
                elif processed.text_to_inject:
                    self.shadow_buffer.inject_and_record(
                        text_to_inject=processed.text_to_inject,
                        raw_text=result.text,
                        alternatives=arbitrated.ranked_alternatives[:3],
                        audio_pcm=segment,
                    )
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

            # Dictée de texte : si le volet « Corriger ça » est ouvert, la nouvelle dictée est
            # proposée dans le champ de correction SANS application automatique (anti-bafouillage / anti-coupure).
            # L'utilisateur doit valider explicitement (bouton, « Valider la correction », ou choix 1/2/3).
            if processed.intent == VoiceIntentType.DICTATION:
                inject_text = processed.text_to_inject
                # Mode épellation (alphabet radio) : convertir les mots NATO en lettres, sans ponctuation auto.
                if self._spelling_mode:
                    spelled = text_to_nato_spelling(result.text)
                    inject_text = spelled
                if inject_text:
                    if self._correction_open:
                        proposed = inject_text.lstrip(" ").strip()
                        self._pending_correction_text = proposed
                        self.hud.set_correction_edit_text(proposed)
                        mode_tag = " [Épellation]" if self._spelling_mode else ""
                        self.hud.set_transcript(
                            proposed,
                            result.total_ms,
                            f"[Proposition de correction{mode_tag} — cliquez « Appliquer » ou dites « Valider la correction »]",
                        )
                    else:
                        self.shadow_buffer.inject_and_record(
                            text_to_inject=inject_text,
                            raw_text=result.text,
                            alternatives=arbitrated.ranked_alternatives[:3],
                            audio_pcm=segment,
                        )
                        alt_preview = (
                            f"(Alt: {arbitrated.ranked_alternatives[0]})"
                            if arbitrated.ranked_alternatives and not self._spelling_mode
                            else ""
                        )
                        display_text = inject_text
                        if self._spelling_mode:
                            alt_preview = "[Épellation]"
                        self.hud.set_transcript(
                            display_text, result.total_ms, alt_preview
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
