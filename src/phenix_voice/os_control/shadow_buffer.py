"""Shadow Buffer (Tampon Mémoire Synchronisé) et sélecteur/remplaceur direct Win32 SendInput.

Permet à Phénix Voice d'écrire, de sélectionner un mot (« Sélectionner [X] ») et de remplacer
le dernier souffle ou un mot (« Corriger ça », « Choisir 1/2/3 ») directement dans 100 % des
fenêtres Windows, sans jamais ouvrir de boîte de dictée intermédiaire.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable
import numpy as np

from phenix_voice.os_control.injector import (
    INPUT,
    VK_BACK,
    VK_RETURN,
    _make_unicode_events,
    _make_vk_events,
    _send_inputs,
    choose_send_path,
    get_window_class_name,
    send_backspaces_via_messages,
    send_text_via_messages,
    user32 as _injector_user32,
)

VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002


@dataclass
class ShadowSegment:
    """Représente un souffle dicté et injecté dans la fenêtre active."""

    injected_text: str
    raw_text: str
    backspace_count: int
    alternatives: list[str] = field(default_factory=list)
    audio_pcm: np.ndarray | None = None


class ShadowBuffer:
    """Conserve en mémoire vive les derniers souffles dictés avec leurs alternatives et leur audio."""

    def __init__(
        self,
        max_segments: int = 25,
        action_logger: Callable[..., Any] | None = None,
    ) -> None:
        self._segments: deque[ShadowSegment] = deque(maxlen=max_segments)
        self._active_selection_len: int = 0
        self._action_logger = action_logger

    def _log_action(self, action: str, **details) -> None:
        if self._action_logger:
            try:
                self._action_logger(action, **details)
            except Exception:
                pass

    @property
    def last_segment(self) -> ShadowSegment | None:
        return self._segments[-1] if self._segments else None

    def clear_context(self) -> None:
        """Appelé lorsque l'utilisateur clique ailleurs à la souris."""
        self._active_selection_len = 0

    def inject_and_record(
        self,
        text_to_inject: str,
        raw_text: str,
        alternatives: list[str] | None = None,
        audio_pcm: np.ndarray | None = None,
    ) -> ShadowSegment | None:
        """Injecte `text_to_inject` dans la fenêtre active et l'enregistre dans le Shadow Buffer."""
        if not text_to_inject:
            return None

        bs_count, send_stats = self._send_text(text_to_inject)
        self._log_action(
            "inject_text",
            text=text_to_inject,
            raw_text=raw_text,
            backspace_equiv=bs_count,
            **send_stats,
        )
        seg = ShadowSegment(
            injected_text=text_to_inject,
            raw_text=raw_text,
            backspace_count=bs_count,
            alternatives=list(alternatives or []),
            audio_pcm=audio_pcm,
        )
        self._segments.append(seg)
        self._active_selection_len = 0
        return seg

    def scratch_last(self, discard_audio: bool = True) -> ShadowSegment | None:
        """Efface le dernier segment injecté dans la fenêtre active via VK_BACK."""
        if not self._segments:
            self._log_action("scratch_last", result="no_segment")
            return None
        seg = self._segments.pop()
        bs_stats = self._send_backspaces(seg.backspace_count) if seg.backspace_count > 0 else self._send_backspaces(0)
        self._log_action(
            "scratch_last",
            result="erased",
            erased_text=seg.injected_text,
            discard_audio=discard_audio,
            **bs_stats,
        )
        if discard_audio:
            seg.audio_pcm = None
        self._active_selection_len = 0
        return seg

    def replace_last(
        self,
        new_text: str,
        discard_audio: bool = False,
    ) -> tuple[ShadowSegment | None, ShadowSegment | None]:
        """Remplace le dernier segment dicté par `new_text` directement dans la fenêtre active.
        Retourne `(ancien_segment, nouveau_segment)`.
        """
        if not self._segments:
            self._log_action("replace_last", result="no_prior_segment", new_text=new_text)
            new_seg = self.inject_and_record(new_text, raw_text=new_text)
            return None, new_seg

        old_seg = self._segments.pop()
        bs_stats = self._send_backspaces(old_seg.backspace_count) if old_seg.backspace_count > 0 else self._send_backspaces(0)
        self._log_action(
            "replace_last_backspace",
            erased_text=old_seg.injected_text,
            **bs_stats,
        )

        # Préserver l'espace initial si l'ancien segment commençait par une espace
        formatted_new = new_text
        if (
            old_seg.injected_text.startswith(" ")
            and not formatted_new.startswith(" ")
            and not formatted_new.startswith("\n")
        ):
            formatted_new = " " + formatted_new

        new_bs, send_stats = self._send_text(formatted_new)
        self._log_action(
            "replace_last_inject",
            text=formatted_new,
            raw_text=new_text,
            backspace_equiv=new_bs,
            **send_stats,
        )
        new_seg = ShadowSegment(
            injected_text=formatted_new,
            raw_text=new_text,
            backspace_count=new_bs,
            alternatives=[],
            audio_pcm=None if discard_audio else old_seg.audio_pcm,
        )
        self._segments.append(new_seg)
        if discard_audio:
            old_seg.audio_pcm = None
        return old_seg, new_seg

    def select_word_in_last_segments(self, target_word: str) -> bool:
        """Recherche `target_word` dans le texte récemment dicté et le sélectionne dans la fenêtre
        active via des déplacements curseur (`Left` puis `Shift + Left`).
        """
        target_clean = target_word.strip().lower()
        if not target_clean or not self._segments:
            self._log_action("select_word", target=target_word, result="no_match_or_context")
            return False

        # Reconstruire la chaîne récente sur la ligne courante (sans traverser un saut de ligne)
        full_recent = "".join(s.injected_text for s in self._segments)
        last_nl = full_recent.rfind("\n")
        current_line = full_recent[last_nl + 1 :] if last_nl != -1 else full_recent

        idx = current_line.lower().rfind(target_clean)
        if idx == -1:
            self._log_action("select_word", target=target_word, result="not_found")
            return False

        chars_from_end_to_word_end = len(current_line) - (idx + len(target_clean))
        word_len = len(target_clean)

        events: list[INPUT] = []
        # 1. Reculer jusqu'à la fin du mot cible
        for _ in range(chars_from_end_to_word_end):
            events.extend(_make_vk_events(VK_LEFT))

        # 2. Maintenir Shift et reculer sur la longueur du mot pour le sélectionner
        shift_down, shift_up = _make_vk_events(VK_SHIFT)
        events.append(shift_down)
        for _ in range(word_len):
            events.extend(_make_vk_events(VK_LEFT))
        events.append(shift_up)

        send_stats = self._send_events_batched(events)
        self._active_selection_len = word_len
        self._log_action(
            "select_word",
            target=target_word,
            result="ok",
            left_moves_to_end=chars_from_end_to_word_end,
            shift_left_count=word_len,
            **send_stats,
        )
        return True

    def press_enter_key(self) -> None:
        """Envoie une pression franche sur la touche Entrée (`VK_RETURN`).

        Réutilise :meth:`_send_text` pour bénéficier du choix automatique de chemin
        (Bloc-notes Win11 : VK_RETURN envoyé en messages, sinon SendInput).
        """
        _bs_count, send_stats = self._send_text("\n")
        self._log_action("press_enter", **send_stats)
        self._segments.append(
            ShadowSegment(
                injected_text="\n",
                raw_text="Presser Entrée",
                backspace_count=1,
            )
        )

    @staticmethod
    def _send_events_batched(events: list[INPUT], batch_size: int = 64) -> dict:
        requested = len(events)
        inserted_total = 0
        batches: list[list[int]] = []
        for idx in range(0, len(events), batch_size):
            batch = events[idx : idx + batch_size]
            inserted = _send_inputs(batch)
            inserted_total += inserted
            batches.append([len(batch), inserted])
        return {
            "events_requested": requested,
            "events_inserted": inserted_total,
            "send_ok": inserted_total == requested,
            "batch_count": len(batches),
            "batch_results": batches if len(batches) != 1 else batches,  # compact: keep always for diagnosis
        }

    @staticmethod
    def _text_send_stats(text: str) -> dict:
        stats: dict = {"char_count": len(text), "newline_count": text.count("\n")}
        if not text:
            return stats
        last = text[-1]
        stats["last_char"] = last
        stats["last_char_codepoint"] = f"U+{ord(last):04X}"
        try:
            stats["last_char_utf16_units"] = len(last.encode("utf-16-le")) // 2
        except Exception:
            pass
        return stats

    @classmethod
    def _send_text(cls, text: str) -> tuple[int, dict]:
        # Nombre de retours arrière nécessaires pour annuler l'injection :
        # chaque caractère non-\\r vaut 1 (le '\\n' est envoyé comme une seule Entrée).
        bs_count = sum(1 for ch in text if ch != "\r")

        path = choose_send_path()
        target_hwnd = int(_injector_user32.GetForegroundWindow() or 0)
        target_class = get_window_class_name(target_hwnd)

        if path == "messages":
            result = send_text_via_messages(text, target_hwnd)
            if result.get("ok"):
                msgs = int(result.get("message_count", 0))
                send_stats: dict = {
                    "events_requested": msgs,
                    "events_inserted": msgs,
                    "send_ok": True,
                    "batch_count": 1,
                    "batch_results": [[msgs, msgs]],
                    "send_path": "messages",
                    "target_class": target_class,
                    "focus_hwnd": result.get("focus_hwnd"),
                }
                send_stats.update(cls._text_send_stats(text))
                return bs_count, send_stats
            # repli SendInput (fenêtre focalisée indisponible, etc.)
            fallback_reason = result.get("reason")
        else:
            fallback_reason = None

        events: list[INPUT] = []
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                events.extend(_make_vk_events(VK_RETURN))
            else:
                raw = ch.encode("utf-16-le")
                for i in range(0, len(raw), 2):
                    code_unit = int.from_bytes(raw[i : i + 2], byteorder="little")
                    events.extend(_make_unicode_events(code_unit))

        send_stats = cls._send_events_batched(events)
        send_stats.update(cls._text_send_stats(text))
        send_stats["target_class"] = target_class
        if path == "messages":
            send_stats["send_path"] = "sendinput_fallback"
            send_stats["messages_fallback_reason"] = fallback_reason
        else:
            send_stats["send_path"] = "sendinput"
        return bs_count, send_stats

    @classmethod
    def _send_backspaces(cls, count: int) -> dict:
        if count <= 0:
            return {
                "events_requested": 0,
                "events_inserted": 0,
                "send_ok": True,
                "batch_count": 0,
                "batch_results": [],
                "backspace_count": count,
                "send_path": "none",
            }

        path = choose_send_path()
        target_hwnd = int(_injector_user32.GetForegroundWindow() or 0)
        target_class = get_window_class_name(target_hwnd)

        if path == "messages":
            result = send_backspaces_via_messages(count, target_hwnd)
            if result.get("ok"):
                msgs = int(result.get("message_count", 0))
                return {
                    "events_requested": msgs,
                    "events_inserted": msgs,
                    "send_ok": True,
                    "batch_count": 1,
                    "batch_results": [[msgs, msgs]],
                    "backspace_count": count,
                    "send_path": "messages",
                    "target_class": target_class,
                    "focus_hwnd": result.get("focus_hwnd"),
                }
            fallback_reason = result.get("reason")
        else:
            fallback_reason = None

        events: list[INPUT] = []
        for _ in range(count):
            events.extend(_make_vk_events(VK_BACK))
        send_stats = cls._send_events_batched(events)
        send_stats["backspace_count"] = count
        send_stats["target_class"] = target_class
        if path == "messages":
            send_stats["send_path"] = "sendinput_fallback"
            send_stats["messages_fallback_reason"] = fallback_reason
        else:
            send_stats["send_path"] = "sendinput"
        return send_stats
