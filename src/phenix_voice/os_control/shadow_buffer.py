"""Shadow Buffer (Tampon Mémoire Synchronisé) et sélecteur/remplaceur direct Win32 SendInput.

Permet à Phénix Voice d'écrire, de sélectionner un mot (« Sélectionner [X] ») et de remplacer
le dernier souffle ou un mot (« Corriger ça », « Choisir 1/2/3 ») directement dans 100 % des
fenêtres Windows, sans jamais ouvrir de boîte de dictée intermédiaire.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import numpy as np

from phenix_voice.os_control.injector import (
    INPUT,
    VK_BACK,
    VK_RETURN,
    _make_unicode_events,
    _make_vk_events,
    _send_inputs,
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

    def __init__(self, max_segments: int = 25) -> None:
        self._segments: deque[ShadowSegment] = deque(maxlen=max_segments)
        self._active_selection_len: int = 0

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

        bs_count = self._send_text(text_to_inject)
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
            return None
        seg = self._segments.pop()
        if seg.backspace_count > 0:
            self._send_backspaces(seg.backspace_count)
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
            new_seg = self.inject_and_record(new_text, raw_text=new_text)
            return None, new_seg

        old_seg = self._segments.pop()
        if old_seg.backspace_count > 0:
            self._send_backspaces(old_seg.backspace_count)

        # Préserver l'espace initial si l'ancien segment commençait par une espace
        formatted_new = new_text
        if (
            old_seg.injected_text.startswith(" ")
            and not formatted_new.startswith(" ")
            and not formatted_new.startswith("\n")
        ):
            formatted_new = " " + formatted_new

        new_bs = self._send_text(formatted_new)
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
            return False

        # Reconstruire la chaîne récente sur la ligne courante (sans traverser un saut de ligne)
        full_recent = "".join(s.injected_text for s in self._segments)
        last_nl = full_recent.rfind("\n")
        current_line = full_recent[last_nl + 1 :] if last_nl != -1 else full_recent

        idx = current_line.lower().rfind(target_clean)
        if idx == -1:
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

        _send_inputs(events)
        self._active_selection_len = word_len
        return True

    def press_enter_key(self) -> None:
        """Envoie une pression franche sur la touche Entrée (`VK_RETURN`)."""
        _send_inputs(_make_vk_events(VK_RETURN))
        self._segments.append(
            ShadowSegment(
                injected_text="\n",
                raw_text="Presser Entrée",
                backspace_count=1,
            )
        )

    @staticmethod
    def _send_text(text: str) -> int:
        events: list[INPUT] = []
        bs_count = 0
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                events.extend(_make_vk_events(VK_RETURN))
                bs_count += 1
            else:
                raw = ch.encode("utf-16-le")
                for i in range(0, len(raw), 2):
                    code_unit = int.from_bytes(raw[i : i + 2], byteorder="little")
                    events.extend(_make_unicode_events(code_unit))
                bs_count += 1

        batch_size = 64
        for idx in range(0, len(events), batch_size):
            _send_inputs(events[idx : idx + batch_size])
        return bs_count

    @staticmethod
    def _send_backspaces(count: int) -> None:
        events: list[INPUT] = []
        for _ in range(count):
            events.extend(_make_vk_events(VK_BACK))
        batch_size = 64
        for idx in range(0, len(events), batch_size):
            _send_inputs(events[idx : idx + batch_size])
