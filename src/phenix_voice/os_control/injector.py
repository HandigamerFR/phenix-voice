"""Injection clavier universelle directe (Win32 SendInput Unicode) sans boîte de dictée."""

from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_RETURN = 0x0D

ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _make_vk_events(vk_code: int) -> list[INPUT]:
    """Crée une paire d'événements Appui + Relâchement pour une touche virtuelle (ex: Entrée, Backspace)."""
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUT_UNION(
            ki=KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        ),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0
            )
        ),
    )
    return [down, up]


def _make_unicode_events(utf16_unit: int) -> list[INPUT]:
    """Crée une paire d'événements Appui + Relâchement Unicode direct."""
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=0,
                wScan=utf16_unit,
                dwFlags=KEYEVENTF_UNICODE,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=0,
                wScan=utf16_unit,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    return [down, up]


def _send_inputs(events: list[INPUT]) -> int:
    if not events:
        return 0
    arr_type = INPUT * len(events)
    arr = arr_type(*events)
    return int(user32.SendInput(len(events), ctypes.byref(arr), ctypes.sizeof(INPUT)))


class DirectTextInjector:
    """Injecte directement le texte dicté dans 100 % des fenêtres Windows (Zéro Boîte de Dictée)
    et conserve l'historique des derniers segments injectés pour permettre l'annulation sur place.
    """

    def __init__(self, max_history: int = 20) -> None:
        # Pile des derniers segments injectés (nombre de pressions Backspace nécessaires pour effacer)
        self._history_lengths: deque[int] = deque(maxlen=max_history)
        self._history_texts: deque[str] = deque(maxlen=max_history)

    @property
    def last_injected_text(self) -> str:
        return self._history_texts[-1] if self._history_texts else ""

    def inject_text(self, text: str) -> int:
        """Écrit `text` directement à la position du curseur de la fenêtre active."""
        if not text:
            return 0

        events: list[INPUT] = []
        backspace_count = 0

        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                events.extend(_make_vk_events(VK_RETURN))
                backspace_count += 1
            else:
                # Encodage UTF-16LE (supporte accents français, symboles et emojis)
                raw = ch.encode("utf-16-le")
                for i in range(0, len(raw), 2):
                    code_unit = int.from_bytes(raw[i : i + 2], byteorder="little")
                    events.extend(_make_unicode_events(code_unit))
                backspace_count += 1

        # Envoi par lots de 64 événements pour éviter toute saturation du tampon d'entrée d'Electron/Chrome
        total_sent = 0
        batch_size = 64
        for idx in range(0, len(events), batch_size):
            batch = events[idx : idx + batch_size]
            total_sent += _send_inputs(batch)
            if idx + batch_size < len(events):
                time.sleep(0.002)

        self._history_lengths.append(backspace_count)
        self._history_texts.append(text)
        return backspace_count

    def scratch_last(self) -> bool:
        """Efface immédiatement le dernier souffle dicté dans la fenêtre active via VK_BACK."""
        if not self._history_lengths:
            return False
        count = self._history_lengths.pop()
        if self._history_texts:
            self._history_texts.pop()
        if count <= 0:
            return False

        events: list[INPUT] = []
        for _ in range(count):
            events.extend(_make_vk_events(VK_BACK))

        batch_size = 64
        for idx in range(0, len(events), batch_size):
            _send_inputs(events[idx : idx + batch_size])
            if idx + batch_size < len(events):
                time.sleep(0.002)
        return True
