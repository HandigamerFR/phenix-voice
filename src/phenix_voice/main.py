"""Point d'entrée principal de Phénix Voice (Phase 2 : Arbitre de Plausibilité, Shadow Buffer,
Correction Anti-Dérive & Contrôle Micro 3 États sans conflit avec Dragon).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
import queue
import sys
import threading
import time
import traceback
import wave
import ctypes
from typing import Any
import numpy as np
from PySide6.QtWidgets import QApplication

user32 = ctypes.WinDLL("user32", use_last_error=True)

from phenix_voice.profile.snapshot import (
    InjectionTraceLogger,
    ProfileSnapshotManager,
    SessionTraceLogger,
)

from phenix_voice.audio.capture import MicrophoneCapture
from phenix_voice.audio.fingerprints import AcousticCommandProtector
from phenix_voice.audio.vad import BreathSegmenter
from phenix_voice.os_control.hotkeys import GlobalInputMonitor
from phenix_voice.os_control.shadow_buffer import ShadowBuffer
from phenix_voice.postprocess.coherence import is_textual_only_correction
from phenix_voice.postprocess.plausibility import PlausibilityArbitrator
from phenix_voice.postprocess.punctuation import (
    HybridPunctuationProcessor,
    VoiceIntentType,
    spelling_from_result,
)
from phenix_voice.stt.engine import WhisperDirectMLEngine
from phenix_voice.ui.hud import MicState, PhenixHUD

# En mode épellation, la fenêtre n'écoute QUE les lettres / chiffres / symboles /
# espace (DICTATION convertie en alphabet radio) + la commande de sortie, la
# validation d'une correction ouverte, et les commandes de sécurité (micro, veille,
# aide). Toute autre commande est ignorée et journalisée (« spelling_command_ignored »).
SPELLING_ALLOWED_INTENTS: set[VoiceIntentType] = {
    VoiceIntentType.DICTATION,
    VoiceIntentType.EXIT_SPELLING,
    VoiceIntentType.APPLY_CORRECTION,
    VoiceIntentType.MUTE_MIC,
    VoiceIntentType.SLEEP,
    VoiceIntentType.WAKE,
    VoiceIntentType.SHOW_HELP,
}


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
        self._spelling_from_correction = False  # fenêtre d'épellation ouverte depuis la correction
        self._correction_target_hwnd: int = 0  # fenêtre cible à restaurer avant injection de correction manuelle

        self._session_id = time.strftime("session_%Y%m%d_%H%M%S")
        self.trace_logger = SessionTraceLogger()
        self.injection_logger = InjectionTraceLogger(session_id=self._session_id)
        self.snapshot_manager = ProfileSnapshotManager()

        self.shadow_buffer = ShadowBuffer(action_logger=self.injection_logger.log_action)
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
            on_correction_text_changed=self.set_pending_correction_text,
            on_add_spoken_form=self.add_spoken_form_from_correction,
            # Fermeture de la fenêtre de correction (✕ ou titre) = annuler sans rien insérer
            on_close_correction=self._close_correction_bar,
            # Fenêtre d'épellation séparée (depuis la correction ou à tout moment)
            on_enter_spelling=self.enter_spelling_mode,
            on_spelling_text_changed=self.set_spelling_text_from_ui,
            on_close_spelling=self._exit_spelling_mode,
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
        self.injection_logger.log_action(
            "session_start",
            session_id=self._session_id,
            model_repo=self.model_repo,
            start_muted=self.is_muted,
            start_sleeping=self.is_sleeping,
            strict_dictionary=getattr(self.arbitrator, "enable_strict_dictionary", None),
        )
        # Point de restauration initial du profil (avant toute nouvelle session)
        try:
            self.snapshot_manager.create_snapshot("demarrage")
            self.injection_logger.log_action("snapshot_created", label="demarrage")
        except Exception as e:
            self.injection_logger.log_action("snapshot_failed", label="demarrage", error=repr(e))
        self._stt_thread.start()

    def _on_cursor_moved(self, source: str = "unknown", **details) -> None:
        self.processor.reset_context()
        self.shadow_buffer.clear_context()
        self.injection_logger.log_action("cursor_context_cleared", source=source, **details)

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

    def _normalize_source_arg(self, source_or_checked: Any = "ui") -> str:
        # QPushButton.clicked(bool) passe False/True ; hotkeys peut passer "hotkey"
        if isinstance(source_or_checked, bool):
            return "ui"
        if isinstance(source_or_checked, str):
            return source_or_checked
        return "ui"

    def toggle_mute(self, source_or_checked: Any = "ui", **details) -> None:
        """Allume ou coupe totalement le micro (F8, bouton HUD, ou autre)."""
        source = self._normalize_source_arg(source_or_checked)
        if self.engine is None:
            self.injection_logger.log_action("mic_toggle_ignored", source=source, reason="engine_not_ready", **details)
            return
        prev_muted = self.is_muted
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.capture.set_paused(True)
            self.hud.set_state(MicState.MUTED)
        else:
            self.is_sleeping = False
            self.capture.set_paused(False)
            self.processor.reset_context()
            self.hud.set_state(MicState.LISTENING)
        self.injection_logger.log_action(
            "mic_state_changed",
            source=source,
            previous_muted=prev_muted,
            muted=self.is_muted,
            sleeping=self.is_sleeping,
            **details,
        )

    def mute_mic_completely(self, source: str = "voice") -> None:
        """Coupe totalement le micro (ex. commande vocale « Couper Phénix »)."""
        if self.engine is None:
            self.injection_logger.log_action("mic_mute_ignored", source=source, reason="engine_not_ready")
            return
        prev_muted = self.is_muted
        self.is_muted = True
        self.capture.set_paused(True)
        self.hud.set_state(MicState.MUTED)
        self.injection_logger.log_action(
            "mic_state_changed",
            source=source,
            previous_muted=prev_muted,
            muted=True,
            sleeping=self.is_sleeping,
            action="mute_completely",
        )

    def toggle_sleep(self, source_or_checked: Any = "ui", **details) -> None:
        """Bascule entre Écoute Active et Veille vocale (« Phénix repos » / F9)."""
        source = self._normalize_source_arg(source_or_checked)
        if self.engine is None:
            self.injection_logger.log_action("sleep_toggle_ignored", source=source, reason="engine_not_ready", **details)
            return
        prev_sleeping = self.is_sleeping
        prev_muted = self.is_muted
        if self.is_muted:
            # Si le micro était coupé, F9 le passe en veille vocale
            self.is_muted = False
            self.is_sleeping = True
            self.capture.set_paused(False)
            self.hud.set_state(MicState.SLEEPING)
        else:
            self.is_sleeping = not self.is_sleeping
            if self.is_sleeping:
                self.hud.set_state(MicState.SLEEPING)
            else:
                self.processor.reset_context()
                self.hud.set_state(MicState.LISTENING)
        self.injection_logger.log_action(
            "sleep_state_changed",
            source=source,
            previous_sleeping=prev_sleeping,
            sleeping=self.is_sleeping,
            previous_muted=prev_muted,
            muted=self.is_muted,
            **details,
        )
        # La veille vocale ferme la fenêtre d'épellation (la reprise n'est pas mémorisée).
        if self.is_sleeping:
            self._exit_spelling_mode()

    def open_correction_for_last(self) -> None:
        """Ouvre le volet de correction sur le dernier segment dicté."""
        last = self.shadow_buffer.last_segment
        if last is None:
            self.hud.set_transcript("[Aucun segment récent à corriger]", 0.0)
            return
        # Mémoriser la fenêtre cible (éditeur) pour pouvoir y réinjecter la correction même si le HUD prend le focus
        try:
            fg = int(user32.GetForegroundWindow() or 0)
            hud_hwnd = int(self.hud.winId()) if self.hud is not None else 0
            if fg and fg != hud_hwnd:
                self._correction_target_hwnd = fg
        except Exception:
            pass
        self._correction_open = True
        self._learn_on_correction = True
        self._pending_correction_text = last.injected_text.strip()
        self.hud.hide_symbol_choice()
        self.hud.show_correction_panel(
            last.injected_text,
            last.alternatives[:9],
            learn_enabled=self._learn_on_correction,
        )

    def add_spoken_form_from_correction(self, written_text: str) -> None:
        """Ajoute une forme orale personnelle depuis le volet de correction :
        « si tu entends [segment dicté], écris [texte saisi] » (dictionnaire
        personnel `user_data/spoken_forms.json`, prioritaire sur les règles)."""
        last = self.shadow_buffer.last_segment
        written = (written_text or "").strip()
        if last is None or not written:
            self.hud.set_transcript("[Aucune forme orale à ajouter]", 0.0)
            return
        heard = (last.raw_text or "").strip()
        ok = self.processor.spoken_forms.add(heard, written)
        if ok:
            msg = f"[Forme orale ajoutée : « {heard} » → « {written} »]"
        else:
            msg = "[Forme orale non ajoutée (texte identique ou trop court)]"
        self.hud.set_transcript(msg, 0.0)
        self.injection_logger.log_action(
            "spoken_form_added", heard=heard, written=written, ok=ok
        )

    def toggle_correction_learn_mode(self) -> None:
        """Bascule entre « Corriger & Apprendre » et « Corriger SANS apprendre (Oups) »."""
        self._learn_on_correction = not self._learn_on_correction
        last = self.shadow_buffer.last_segment
        if last is not None and self._correction_open:
            self.hud.show_correction_panel(
                last.injected_text,
                last.alternatives[:9],
                learn_enabled=self._learn_on_correction,
            )

    def apply_correction_choice(self, choice_1_based: int) -> None:
        """Propose l'alternative choisie (1, 2 ou 3) dans le champ de correction.

        AUCUNE insertion immédiate : la proposition reste dans le champ et
        l'utilisateur valide ensuite explicitement (« Valider la correction »
        ou bouton [Appliquer la correction]). Il a toujours le droit de
        changer d'avis ou de s'être trompé.
        """
        last = self.shadow_buffer.last_segment
        if last is None:
            self.hud.set_transcript("[Aucun segment récent à corriger]", 0.0)
            return
        idx = choice_1_based - 1
        if idx < 0 or idx >= len(last.alternatives):
            self.hud.set_transcript(
                f"[Alternative {choice_1_based} indisponible]", 0.0
            )
            return
        replacement = last.alternatives[idx]
        # Mémoriser la fenêtre cible (éditeur) pour pouvoir y réinjecter après validation
        try:
            fg = int(user32.GetForegroundWindow() or 0)
            hud_hwnd = int(self.hud.winId()) if self.hud is not None else 0
            if fg and fg != hud_hwnd:
                self._correction_target_hwnd = fg
        except Exception:
            pass
        self._correction_open = True
        self._pending_correction_text = replacement
        self.hud.show_correction_panel(
            last.injected_text,
            last.alternatives[:9],
            learn_enabled=self._learn_on_correction,
        )
        self.hud.set_correction_edit_text(replacement)
        self.hud.set_transcript(
            replacement,
            0.0,
            f"[Alternative {choice_1_based} proposée dans le champ — validez pour insérer]",
        )
        self.injection_logger.log_action(
            "correction_choice_proposed",
            choice_index=choice_1_based,
            text=replacement,
            applied=False,
        )

    def set_pending_correction_text(self, new_text: str) -> None:
        if self._correction_open:
            self._pending_correction_text = new_text.strip()
            # Synchroniser le miroir de la fenêtre d'épellation ouverte depuis la correction
            if self._spelling_mode:
                self.hud.set_spelling_text(self._pending_correction_text)

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

    def enter_spelling_mode(self) -> None:
        """Ouvre la fenêtre d'épellation séparée (depuis la correction ou à tout moment).

        - Depuis la correction : champ pré-rempli avec le texte en attente, modifiable ;
          les lettres dictées s'ajoutent, rien n'est inséré avant validation explicite.
        - Hors correction : le texte épelé est inséré directement dans l'éditeur cible.
        """
        if self._spelling_mode:
            return
        self._spelling_mode = True
        self._spelling_from_correction = self._correction_open
        prefill = self._pending_correction_text.strip() if self._correction_open else ""
        self.hud.show_spelling_window(prefill, from_correction=self._correction_open)
        self.injection_logger.log_action(
            "spelling_mode_entered", from_correction=self._correction_open
        )

    def _exit_spelling_mode(self) -> None:
        """Sortie du mode épellation (voix « Fin épellation » / « Passer en mode dictée » ou ✕)."""
        was_active = self._spelling_mode
        self._spelling_mode = False
        self._spelling_from_correction = False
        self.hud.hide_spelling_window()
        if was_active:
            self.injection_logger.log_action("spelling_mode_exited")

    def set_spelling_text_from_ui(self, new_text: str) -> None:
        """Édition manuelle dans la fenêtre d'épellation (depuis la correction) → texte en attente."""
        if self._correction_open:
            cleaned = new_text.strip()
            self._pending_correction_text = cleaned
            self.hud.set_correction_edit_text(cleaned)

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
            "• <b>« Mode épellation »</b> : ouvre la fenêtre d'épellation dédiée (alphabet radio : Alpha, Bravo, Charlie…, chiffres, symboles, espace)<br>"
            "• <b>« Fin épellation »</b> / <b>« Passer en mode dictée »</b> : fermer la fenêtre et revenir à la dictée normale<br>"
        )
        if self._correction_open:
            mic_info = ""
            if self.is_muted:
                mic_info = "<br><i>Micro coupé pendant la correction — utilisez les boutons/souris pour corriger, puis réactivez avec <b>F8</b>.</i>"
            elif self.is_sleeping:
                mic_info = "<br><i>Veille vocale pendant la correction — dites <b>« Phénix écoute »</b> pour reprendre la voix, ou utilisez les boutons/souris.</i>"
            state = "<b>État : CORRECTION DU DERNIER SEGMENT</b>" + mic_info
            cmds = (
                "• <b>« Choisir un … neuf »</b> ou clic : propose l'alternative dans le champ de la fenêtre de correction — validez avec <b>« Valider la correction »</b> ou <b>[Appliquer la correction]</b> (rien n'est inséré avant)<br>"
                "• <b>Re-dicter la phrase</b> : propose une nouvelle correction dans le champ (PAS appliquée automatiquement)<br>"
                "• <b>« Valider la correction »</b> (ou bouton <b>[Appliquer la correction]</b>) : appliquer explicitement la correction<br>"
                "• <b>Modifier le texte dans le champ</b> puis <b>[Appliquer la correction]</b> : correction manuelle précise<br>"
                "• <b>« Mode épellation »</b> ou bouton <b>[🔤 Épellation]</b> : fenêtre d'épellation dédiée, pré-remplie avec le texte à corriger — épeler lettre par lettre (Alpha, Bravo…), le texte s'ajoute au champ puis vous validez<br>"
                "• <b>« Annuler sans apprendre »</b> ou bascule du bouton : passer en mode <b>SANS apprendre</b> (ne pollue pas le profil)<br>"
                "• <b>« Effacer ça »</b> : annuler le segment<br>"
                "• <b>« Phénix repos »</b> / <b>F9</b> ou <b>« Couper Phénix »</b> / <b>F8</b> : mettre en pause le micro sans fermer la correction<br>"
                + common
            )
        elif self.is_muted:
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
            state = "<b>État : MODE ÉPELLATION (fenêtre dédiée — lettres, chiffres, symboles, espace)</b>"
            cmds = (
                "• <b>Seules les commandes d'épellation et de sécurité sont écoutées</b> : les autres commandes sont ignorées tant que la fenêtre est ouverte (fermez-la pour tout faire)<br>"
                "• Dites <b>Alpha, Bravo, Charlie…</b> pour épeler des lettres (miroir dans la fenêtre, ou insertion directe dans l'éditeur hors correction)<br>"
                "• <b>« Chiffre un / Chiffre 5 »</b> : insérer le caractère numérique (1, 5…)<br>"
                "• <b>« En lettres un »</b> ou <b>« Mot un »</b> : insérer le mot littéral « un » (pas le chiffre)<br>"
                "• <b>« Virgule », « Point », « Arobase », « Astérisque »…</b> : insèrent le symbole (ex. adresse e-mail : « Mot laure point arobase mot gmail »)<br>"
                "• <b>« Espace »</b> : insérer un espace<br>"
                "• <b>« Fin épellation »</b> ou <b>« Passer en mode dictée »</b> : fermer la fenêtre et revenir à la dictée normale<br>"
                "• <b>« Valider la correction »</b> : appliquer le texte de la fenêtre (si ouverte depuis la correction)<br>"
                "• <b>« Phénix écoute »</b>, <b>« Phénix repos »</b>, <b>« Couper Phénix »</b>, <b>« Que puis-je dire ? »</b> restent actifs<br>"
                + common
            )
        else:
            state = "<b>État : ÉCOUTE ACTIVE (dictée libre)</b>"
            cmds = (
                "• <b>Dictée libre</b> : parlez normalement, le texte s'écrit dans la fenêtre active<br>"
                "• <b>Aucune ponctuation automatique</b> : le texte s'écrit nu ; dictez <b>« point »</b>, <b>« virgule »</b>, <b>« point d'interrogation »</b> etc. quand vous le souhaitez<br>"
                "• La casse suit la phrase : majuscule seulement au début du texte et après une phrase terminée, minuscule sinon (plus de majuscule forcée à chaque souffle)<br>"
                + spelling_note
                + "• <b>« Phénix repos »</b> : mettre en veille vocale (sans conflit avec Dragon)<br>"
                "• <b>« Couper Phénix »</b> / <b>« Éteindre Phénix »</b> : couper totalement le micro<br>"
                "• <b>« Corriger ça »</b> : ouvrir la fenêtre de correction (jusqu'à 9 alternatives + édition manuelle) du dernier souffle<br>"
                "• <b>« C'était une commande »</b> : si une commande a été écrite à tort comme du texte (ex. « Phénix repos »), efface le segment et ouvre la correction<br>"
                "• <b>« Effacer ça »</b> : supprimer le dernier souffle<br>"
                "• <b>« Annuler sans apprendre »</b> : effacer le dernier souffle SANS apprendre (bafouillage / fausse manip)<br>"
                "• <b>« Presser Entrée »</b> : appuyer sur Entrée<br>"
                "• <b>« Point à la ligne »</b>, <b>« Nouveau paragraphe »</b>, <b>« Virgule »</b>, <b>« Point d'interrogation »</b> etc.<br>"
                "• <b>« Astérisque », « Arobase », « Esperluette », « Dièse »…</b> : insèrent le symbole correspondant<br>"
                "• Formes ambiguës <b>« Euro », « Dollar », « Paragraphe », « Pourcentage »…</b> : le symbole s'écrit d'office ; <b>« Choisir un »</b> (symbole) / <b>« Choisir deux »</b> (le mot) propose le choix dans le champ, à valider<br>"
                + common
            )
        return f"{state}<br><br>{cmds}"

    def _restore_correction_target_focus(self) -> None:
        hwnd = int(getattr(self, "_correction_target_hwnd", 0) or 0)
        if hwnd:
            try:
                for _ in range(3):
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.04)
                    if int(user32.GetForegroundWindow() or 0) == hwnd:
                        break
            except Exception:
                pass

    def _perform_replacement(self, new_text: str, learn: bool) -> None:
        # Si l'utilisateur a édité manuellement dans le HUD, redonner le focus à la fenêtre cible avant d'envoyer Backspace/texte
        self._restore_correction_target_focus()
        self.hud.hide_symbol_choice()
        old_seg, new_seg = self.shadow_buffer.replace_last(
            new_text, discard_audio=not learn
        )
        self._close_correction_bar()

        # Classification de la correction : règle de texte (ponctuation/casse/
        # espaces uniquement) vs erreur de reconnaissance audio. Une correction
        # de texte ne doit JAMAIS polluer l'apprentissage audio (LoRA).
        textual = old_seg is not None and is_textual_only_correction(
            old_seg.injected_text, new_text
        )

        if textual and learn:
            # Règle de texte validée : tracée dans le journal SANS échantillon WAV.
            self._save_learned_correction_sample(
                None, old_seg.injected_text, new_text, kind="textual"
            )
            mode_tag = "✏️ Corrigé — règle texte (pas d'apprentissage audio)"
        elif textual:
            mode_tag = "🛡️ Corrigé SANS apprendre (règle texte)"
        elif old_seg is not None and learn and old_seg.audio_pcm is not None:
            # Snapshot de sécurité avant d'apprendre une correction (anti-dérive / rollback)
            self.snapshot_manager.create_snapshot("avant_correction")
            self._save_learned_correction_sample(
                old_seg.audio_pcm, old_seg.raw_text, new_text, kind="acoustic"
            )
            mode_tag = "🧠 Corrigé & Appris pour LoRA"
        else:
            mode_tag = "🛡️ Corrigé SANS apprendre (Audio écarté)"

        self.hud.set_transcript(new_text, 0.0, f"[{mode_tag}]")

    def oups_scratch_without_learning(self) -> None:
        """Efface immédiatement le dernier souffle et détruit son audio (protection anti-dérive)."""
        self._close_correction_bar()
        self.hud.hide_symbol_choice()
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
            # La fenêtre d'épellation ouverte DEPUIS la correction perd son contexte : on la ferme aussi.
            if self._spelling_from_correction:
                self._exit_spelling_mode()

    def _save_learned_correction_sample(
        self,
        audio_pcm: np.ndarray | None,
        heard_text: str,
        corrected_text: str,
        kind: str = "acoustic",
    ) -> None:
        """Enregistre le couple (Audio WAV, Texte corrigé) validé pour le futur Fine-Tuning LoRA.

        `kind="textual"` : correction de règle de texte (ponctuation/casse/espace)
        — journalisée pour diagnostic SANS échantillon audio (`audio_pcm=None`),
        afin de ne jamais polluer l'apprentissage acoustique.
        """
        try:
            out_dir = Path("user_data/corrections_learned")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            wav_path: Path | None = None
            if audio_pcm is not None:
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
                            "wav": str(wav_path) if wav_path is not None else None,
                            "heard_text": heard_text,
                            "corrected_text": corrected_text,
                            "kind": kind,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

    def _stt_worker_loop(self) -> None:
        try:
            self.engine = WhisperDirectMLEngine(repo_id=self.model_repo)
            self.injection_logger.log_action("engine_ready", model_repo=self.model_repo)
            self.input_monitor.start()
            self.capture.start()
            self.injection_logger.log_action("audio_pipeline_started")

            if self.is_muted:
                self.capture.set_paused(True)
                self.hud.set_state(MicState.MUTED)
                self.hud.set_transcript(
                    "Micro coupé — Appuyez sur F8 ou dites « Que puis-je dire ? » (après réactivation) pour l'aide",
                    0.0,
                )
                self.injection_logger.log_action("initial_state", muted=True, sleeping=False, spelling_mode=self._spelling_mode)
            elif self.is_sleeping:
                self.hud.set_state(MicState.SLEEPING)
                self.injection_logger.log_action("initial_state", muted=False, sleeping=True, spelling_mode=self._spelling_mode)
            else:
                self.hud.set_state(MicState.LISTENING)
                self.hud.set_transcript(
                    "Prêt — Dites « Que puis-je dire ? » pour l'aide, « Mode épellation » pour épeler, ou « Couper Phénix »",
                    0.0,
                )
                self.injection_logger.log_action("initial_state", muted=False, sleeping=False, spelling_mode=self._spelling_mode)
        except Exception as e:
            self.injection_logger.log_action(
                "exception",
                where="stt_worker_init",
                error=repr(e),
                traceback=traceback.format_exc(),
            )
            return

        while self._running:
            try:
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
                    arbitrated.best_text,
                    is_sleeping=self.is_sleeping,
                    # Contexte du texte déjà injecté : cohérence casse/espaces
                    # entre souffles (pas de majuscule automatique en tête de souffle).
                    previous_text=recent_ctx,
                )

                # Alternatives de correction nettoyées avec les MÊMES règles que le
                # texte dicté (ponctuation dictée, symboles, casse/espaces), choix
                # retenu exclu et dédoublonnage : la fenêtre « Corriger ça » propose
                # ainsi des choix directement comparables à ce qui a été écrit.
                if arbitrated.ranked_alternatives:
                    arbitrated = replace(
                        arbitrated,
                        ranked_alternatives=self.processor.format_alternatives(
                            arbitrated.ranked_alternatives,
                            previous_text=recent_ctx,
                            chosen_text=(
                                processed.text_to_inject or arbitrated.best_text
                            ),
                        ),
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
                                    "alts": arbitrated.ranked_alternatives[:9],
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                except Exception:
                    pass

                # Trace de session avec audio (rotation bornée) pour savoir ce qui a été réellement dit
                seg_ts = self.trace_logger.log(
                    audio_pcm=segment,
                    raw_stt=result.text,
                    arbitrated=arbitrated.best_text,
                    intent=processed.intent.value,
                    injected=processed.text_to_inject,
                    alternatives=arbitrated.ranked_alternatives,
                    extra={
                        "dur_s": round(result.audio_duration_s, 2),
                        "ms": round(result.total_ms, 0),
                        "plaus": round(arbitrated.plausibility_score, 2),
                        "conf": round(result.confidence, 2),
                        "session_id": self._session_id,
                    },
                )
                seg_audio = f"user_data/session_audio/seg_{seg_ts}.wav" if seg_ts else None
                self.injection_logger.set_segment_context(
                    segment_ts=seg_ts,
                    audio=seg_audio,
                    intent=processed.intent.value,
                    raw_stt=result.text,
                    arbitrated=arbitrated.best_text,
                )
                # Journal de session : trace des commandes reconnues (et intentions) pour diagnostic
                if processed.intent != VoiceIntentType.DICTATION:
                    self.injection_logger.log_action(
                        "command_recognized",
                        intent=processed.intent.value,
                        raw_stt=result.text,
                        arbitrated=arbitrated.best_text,
                        text_to_inject=processed.text_to_inject,
                        target_arg=getattr(processed, "target_arg", None),
                        choice_index=getattr(processed, "choice_index", None),
                    )

                # Routage des intentions
                # Mode épellation : la fenêtre n'écoute QUE lettres / chiffres /
                # symboles / espace (+ sécurité micro/veille/aide). Toute autre
                # commande est ignorée et journalisée (droit de changer d'avis,
                # pas d'effet de bord caché).
                if self._spelling_mode and (
                    processed.intent not in SPELLING_ALLOWED_INTENTS
                    or (
                        processed.intent == VoiceIntentType.APPLY_CORRECTION
                        and not self._correction_open
                    )
                ):
                    self.injection_logger.log_action(
                        "spelling_command_ignored",
                        intent=processed.intent.value,
                        raw_stt=result.text,
                    )
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.MUTE_MIC:
                    self.mute_mic_completely()
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, result="muted")
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.SHOW_HELP:
                    self.toggle_help()
                    if self.is_muted:
                        self.hud.set_state(MicState.MUTED)
                    elif self.is_sleeping:
                        self.hud.set_state(MicState.SLEEPING)
                    else:
                        self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, help_visible=self._help_visible)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.ENTER_SPELLING:
                    self.enter_spelling_mode()
                    self.hud.set_transcript(
                        "Mode épellation activé — dites Alpha, Bravo, Charlie… "
                        "« chiffre 5 », « espace » (« Fin épellation » / "
                        "« Passer en mode dictée » pour quitter)",
                        result.total_ms,
                    )
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, spelling_mode=True)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.EXIT_SPELLING:
                    self._exit_spelling_mode()
                    self.hud.set_transcript(
                        "Mode épellation désactivé — retour à la dictée normale",
                        result.total_ms,
                    )
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, spelling_mode=False)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.SLEEP:
                    prev_sleeping, prev_muted = self.is_sleeping, self.is_muted
                    self.is_sleeping = True
                    self._exit_spelling_mode()
                    self.hud.set_state(MicState.SLEEPING)
                    self.injection_logger.log_action(
                        "sleep_state_changed",
                        source="voice",
                        previous_sleeping=prev_sleeping,
                        sleeping=True,
                        previous_muted=prev_muted,
                        muted=self.is_muted,
                    )
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, sleeping=True)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.WAKE:
                    prev_sleeping, prev_muted = self.is_sleeping, self.is_muted
                    self.is_sleeping = False
                    self.processor.reset_context()
                    self.hud.set_state(MicState.LISTENING)
                    self.hud.set_transcript(
                        "Écoute reprise — Parlez librement", result.total_ms
                    )
                    self.injection_logger.log_action(
                        "sleep_state_changed",
                        source="voice",
                        previous_sleeping=prev_sleeping,
                        sleeping=False,
                        previous_muted=prev_muted,
                        muted=self.is_muted,
                    )
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, sleeping=False)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.PRESS_ENTER:
                    self._close_correction_bar()
                    self.shadow_buffer.press_enter_key()
                    self.hud.set_transcript("[Touche Entrée ↵]", result.total_ms)
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.OUPS_NO_LEARN:
                    if self._correction_open:
                        # Si le volet de correction est ouvert, « Annuler sans apprendre » le passe en mode SANS apprendre
                        self._learn_on_correction = False
                        last = self.shadow_buffer.last_segment
                        if last:
                            self.hud.show_correction_panel(
                                last.injected_text,
                                last.alternatives[:9],
                                learn_enabled=False,
                            )
                        self.injection_logger.log_action("command_executed", intent=processed.intent.value, mode="disable_learn_in_correction")
                    else:
                        self.oups_scratch_without_learning()
                        self.injection_logger.log_action("command_executed", intent=processed.intent.value, mode="scratch_no_learn")
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.SCRATCH_LAST:
                    self._close_correction_bar()
                    self.shadow_buffer.scratch_last(discard_audio=False)
                    self.hud.set_transcript("[Dernier souffle effacé]", result.total_ms)
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.REVISE_COMMAND:
                    # « C'était une commande » : efface le texte dicté à tort et ouvre la correction sur le segment concerné
                    self._close_correction_bar()
                    erased = self.shadow_buffer.scratch_last(discard_audio=False)
                    self.hud.set_transcript(
                        "[Commande reconnue à posteriori — segment effacé, corrigez ou validez la commande]",
                        result.total_ms,
                    )
                    if erased is not None:
                        self.hud.show_correction_panel(
                            erased.raw_text,
                            [],
                            learn_enabled=self._learn_on_correction,
                        )
                    self.injection_logger.log_action(
                        "command_executed",
                        intent=processed.intent.value,
                        erased_text=(erased.injected_text if erased else None),
                        erased_raw=(erased.raw_text if erased else None),
                        result=("opened_correction" if erased else "no_segment"),
                    )
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.OPEN_CORRECTION:
                    if processed.target_arg:
                        self.shadow_buffer.select_word_in_last_segments(processed.target_arg)
                    self.open_correction_for_last()
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, target_arg=processed.target_arg)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.CHOOSE_ALT:
                    self.apply_correction_choice(processed.choice_index)
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, choice_index=processed.choice_index)
                    self.injection_logger.clear_segment_context()
                    continue

                if processed.intent == VoiceIntentType.APPLY_CORRECTION:
                    if self._correction_open:
                        self.apply_pending_correction()
                    elif processed.text_to_inject:
                        self.shadow_buffer.inject_and_record(
                            text_to_inject=processed.text_to_inject,
                            raw_text=result.text,
                            alternatives=arbitrated.ranked_alternatives[:9],
                            audio_pcm=segment,
                        )
                    self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, correction_open=self._correction_open)
                    self.injection_logger.clear_segment_context()
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
                    self.injection_logger.log_action("command_executed", intent=processed.intent.value, target_arg=processed.target_arg, found=ok)
                    self.injection_logger.clear_segment_context()
                    continue

                # Dictée de texte : si le volet « Corriger ça » est ouvert, la nouvelle dictée est
                # proposée dans le champ de correction SANS application automatique (anti-bafouillage / anti-coupure).
                # L'utilisateur doit valider explicitement (bouton, « Valider la correction », ou choix 1…9).
                if processed.intent == VoiceIntentType.DICTATION:
                    inject_text = processed.text_to_inject
                    # Mode épellation (alphabet radio) : convertir les mots NATO en
                    # lettres, sans ponctuation auto. Filtrage sur l'utile : si le
                    # STT n'a rien d'utile, on cherche dans ses alternatives (« M. »
                    # parmi les hypothèses de « Make. ») puis on REJETTE explicitement
                    # — plus jamais de silence en mode épellation.
                    spelling_rejected: str | None = None
                    if self._spelling_mode:
                        inject_text, spelling_rejected = spelling_from_result(
                            result.text, result.alternatives
                        )
                    # Forme orale ambiguë (« euro », « paragraphe »…) : le symbole est inséré
                    # par défaut et une popup propose aussi le mot dicté (voix « choix un /
                    # deux » ou clic), façon Dragon. Alternative complète = [symbole, mot].
                    show_symbol_popup = (
                        not self._spelling_mode
                        and not self._correction_open
                        and bool(processed.symbol_choices)
                    )
                    if inject_text:
                        if self._correction_open:
                            if self._spelling_mode:
                                # Épellation depuis la correction : chaque chunk s'AJOUTE
                                # au texte pré-rempli (pas de remplacement) ; rien n'est
                                # inséré dans l'éditeur avant validation explicite.
                                proposed = self._pending_correction_text + inject_text
                            else:
                                proposed = inject_text.lstrip(" ").strip()
                            self._pending_correction_text = proposed
                            self.hud.set_correction_edit_text(proposed)
                            if self._spelling_mode:
                                self.hud.set_spelling_text(proposed)
                            self.injection_logger.log_action(
                                "dictation_proposed_to_correction",
                                text=proposed,
                                spelling_mode=self._spelling_mode,
                                raw_stt=result.text,
                            )
                            mode_tag = " [Épellation]" if self._spelling_mode else ""
                            self.hud.set_transcript(
                                proposed,
                                result.total_ms,
                                f"[Proposition de correction{mode_tag} — cliquez « Appliquer » ou dites « Valider la correction »]",
                            )
                        else:
                            seg_alternatives = (
                                processed.symbol_choices
                                if show_symbol_popup
                                else arbitrated.ranked_alternatives[:9]
                            )
                            if not show_symbol_popup:
                                # Une popup de symbole éventuellement ouverte sur un segment précédent est obsolète.
                                self.hud.hide_symbol_choice()
                            self.shadow_buffer.inject_and_record(
                                text_to_inject=inject_text,
                                raw_text=result.text,
                                alternatives=seg_alternatives,
                                audio_pcm=segment,
                            )
                            if self._spelling_mode:
                                # Miroir dans la fenêtre d'épellation (insertion directe)
                                self.hud.append_spelling_text(inject_text)
                            alt_preview = (
                                f"(Alt: {arbitrated.ranked_alternatives[0]})"
                                if arbitrated.ranked_alternatives and not self._spelling_mode
                                else ""
                            )
                            display_text = inject_text
                            if self._spelling_mode:
                                alt_preview = "[Épellation]"
                            elif show_symbol_popup:
                                alt_preview = (
                                    f"[Symbole « {processed.symbol_char} » — « choix un » = symbole, "
                                    "« choix deux » = mot — proposition à valider]"
                                )
                            self.hud.set_transcript(
                                display_text, result.total_ms, alt_preview
                            )
                            if show_symbol_popup:
                                self.hud.show_symbol_choice(
                                    processed.symbol_form,
                                    [
                                        f"{processed.symbol_char} (symbole)",
                                        f"{processed.symbol_form} (mot)",
                                    ],
                                )
                                self.injection_logger.log_action(
                                    "symbol_choice_popup",
                                    form=processed.symbol_form,
                                    symbol=processed.symbol_char,
                                    text=inject_text,
                                )
                    else:
                        if spelling_rejected is not None:
                            # Rejet explicite en mode épellation : on montre ce qui
                            # n'a pas été reconnu (l'utilisateur sait qu'il faut
                            # redire la lettre) — plus jamais de silence.
                            self.hud.set_transcript(
                                f"❌ Épellation non reconnue : « {spelling_rejected} »",
                                result.total_ms,
                                "[Mode épellation — dites une lettre (alphabet radio), "
                                "« espace », « chiffre X » ou « Fin épellation »]",
                            )
                            self.injection_logger.log_action(
                                "spelling_rejected",
                                raw_stt=result.text,
                                spelling_mode=True,
                            )
                        else:
                            self.injection_logger.log_action(
                                "dictation_empty",
                                spelling_mode=self._spelling_mode,
                                raw_stt=result.text,
                            )

                    if not self.is_sleeping and not self.is_muted:
                        self.hud.set_state(MicState.LISTENING)
                    self.injection_logger.clear_segment_context()
            except Exception as e:
                self.injection_logger.log_action(
                    "exception",
                    where="stt_worker_loop",
                    error=repr(e),
                    traceback=traceback.format_exc(),
                )
                try:
                    self.injection_logger.clear_segment_context()
                except Exception:
                    pass
                try:
                    if not self.is_sleeping and not self.is_muted:
                        self.hud.set_state(MicState.LISTENING)
                except Exception:
                    pass

    def shutdown(self) -> None:
        if not self._running:
            return
        self.injection_logger.log_action(
            "session_end",
            reason="shutdown",
            muted=self.is_muted,
            sleeping=self.is_sleeping,
            spelling_mode=self._spelling_mode,
        )
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
