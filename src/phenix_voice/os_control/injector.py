"""Injection clavier universelle directe (Win32 SendInput Unicode) sans boîte de dictée.

Deux chemins d'envoi coexistent :

* ``sendinput`` — chemin PRODUCTION historique : rafales SendInput KEYEVENTF_UNICODE.
  Fonctionne dans la grande majorité des applications (Word, Notepad++, LibreOffice,
  navigateurs Chromium, contrôles Win32 natifs… vérifié par le banc ``tools/injection_bench.py``).
* ``messages`` — chemin de repli pour les fenêtres dont le pipeline d'entrée corrompt les
  rafales SendInput (Bloc-notes redessiné de Windows 11 : bug documenté et reproductible —
  le dernier caractère de chaque lot est répété en conservant la longueur du texte).
  Il envoie WM_CHAR / WM_KEYDOWN / WM_KEYUP directement à la fenêtre focalisée
  (SendMessage synchrone, aucune rafale à travers le flux d'entrée système).

Le choix est automatique via :func:`choose_send_path` (classe de la fenêtre active),
surchargeable avec la variable d'environnement ``PHENIX_INJECTION_PATH``
(``sendinput`` | ``messages``).
"""

from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes
import os
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_RETURN = 0x0D

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

# Classes de fenêtres pour lesquelles les rafales SendInput sont corrompues par
# l'application réceptrice (voir docstring du module) => chemin « messages ».
MESSAGE_PATH_WINDOW_CLASSES = frozenset({"Notepad"})

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


# --------------------------------------------------------------------------- chemin « messages »


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", _RECT),
    ]


user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SendMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL


def get_window_class_name(hwnd: int) -> str:
    """Classe Win32 de la fenêtre (ex: ``Notepad``, ``OpusApp``, ``Chrome_WidgetWin_1``)."""
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    try:
        if not user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256):
            return ""
        return buf.value or ""
    except Exception:
        return ""


def focused_child_window(target_hwnd: int) -> int:
    """Fenêtre réellement focalisée dans le thread de `target_hwnd` (0 si indisponible)."""
    if not target_hwnd:
        return 0
    try:
        gti = _GUITHREADINFO()
        gti.cbSize = ctypes.sizeof(_GUITHREADINFO)
        tid = user32.GetWindowThreadProcessId(wintypes.HWND(target_hwnd), None)
        if not tid or not user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
            return 0
        return int(gti.hwndFocus or 0)
    except Exception:
        return 0


def choose_send_path() -> str:
    """``"messages"`` pour les cibles connues pour corrompre les rafales SendInput, sinon ``"sendinput"``.

    Surcharge : variable d'environnement ``PHENIX_INJECTION_PATH`` = ``sendinput`` | ``messages``.
    """
    override = (os.environ.get("PHENIX_INJECTION_PATH") or "").strip().lower()
    if override in ("sendinput", "messages"):
        return override
    try:
        hwnd = int(user32.GetForegroundWindow() or 0)
        if not hwnd:
            return "sendinput"
        return (
            "messages"
            if get_window_class_name(hwnd) in MESSAGE_PATH_WINDOW_CLASSES
            else "sendinput"
        )
    except Exception:
        return "sendinput"


def send_text_via_messages(text: str, target_hwnd: int) -> dict:
    """Écrit `text` en envoyant WM_CHAR directement à la fenêtre focalisée de la cible.

    Retourne ``{"ok": bool, ...}`` ; ``ok=False`` => l'appelant doit replier sur SendInput.
    ``\n`` est envoyé comme VK_RETURN (WM_CHAR ``\r`` seul est ignoré par le Bloc-notes).
    """
    focus = focused_child_window(target_hwnd)
    if not focus:
        return {"ok": False, "reason": "focus_child_not_found", "message_count": 0}
    count = 0
    try:
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                user32.SendMessageW(focus, WM_KEYDOWN, VK_RETURN, 1)
                user32.SendMessageW(focus, WM_KEYUP, VK_RETURN, 1)
                count += 2
                continue
            raw = ch.encode("utf-16-le")  # paires de substituts pour les emojis (hors-BMP)
            for i in range(0, len(raw), 2):
                user32.SendMessageW(
                    focus, WM_CHAR, int.from_bytes(raw[i : i + 2], "little"), 1
                )
                count += 1
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"send_failed:{exc}", "message_count": count}
    return {"ok": True, "focus_hwnd": focus, "message_count": count}


def send_backspaces_via_messages(count: int, target_hwnd: int) -> dict:
    """Efface `count` caractères via WM_KEYDOWN/WM_KEYUP VK_BACK sur la fenêtre focalisée."""
    if count <= 0:
        return {"ok": True, "focus_hwnd": 0, "message_count": 0, "reason": "empty"}
    focus = focused_child_window(target_hwnd)
    if not focus:
        return {"ok": False, "reason": "focus_child_not_found", "message_count": 0}
    sent = 0
    try:
        for _ in range(count):
            user32.SendMessageW(focus, WM_KEYDOWN, VK_BACK, 1)
            user32.SendMessageW(focus, WM_KEYUP, VK_BACK, 1)
            sent += 2
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"send_failed:{exc}", "message_count": sent}
    return {"ok": True, "focus_hwnd": focus, "message_count": sent}


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
