"""Écoute globale des raccourcis clavier physiques (F8 : Allumer/Couper Micro, F9 : Veille vocale)."""

from __future__ import annotations

from typing import Callable
from pynput import keyboard, mouse


class GlobalInputMonitor:
    """Surveille en arrière-plan :
    - `F8` : Bascule Allumer / Couper totalement le micro (comme le bouton micro de Dragon).
    - `F9` : Bascule Écoute Active <-> Veille vocale (« Phénix repos »).
    - Clics souris / touches de navigation pour réinitialiser le contexte de début de phrase.
    """

    def __init__(
        self,
        on_toggle_mute: Callable[..., None],
        on_toggle_sleep: Callable[..., None] | None = None,
        on_cursor_moved: Callable[..., None] | None = None,
        mute_key: keyboard.Key = keyboard.Key.f8,
        sleep_key: keyboard.Key = keyboard.Key.f9,
        on_debug: Callable[..., None] | None = None,
    ) -> None:
        self.on_toggle_mute = on_toggle_mute
        self.on_toggle_sleep = on_toggle_sleep
        self.on_cursor_moved = on_cursor_moved
        self.mute_key = mute_key
        self.sleep_key = sleep_key
        # Journal de diagnostic (F8/F9 vus, erreurs du callback) : une exception
        # non interceptée dans le callback tue silencieusement le listener
        # pynput — plus aucun raccourci après ça.
        self.on_debug = on_debug

        self._kb_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None

    def _debug(self, event: str, **details) -> None:
        if self.on_debug is not None:
            try:
                self.on_debug(event, **details)
            except Exception:
                pass

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        try:
            self._handle_key_press(key)
        except Exception as exc:  # ne jamais laisser mourir le listener
            self._debug("hotkey_error", error=repr(exc))

    def _handle_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        # Pas de repli "sans argument" sur TypeError : si le callback plante
        # APRÈS avoir basculé l'état, un second appel annule la premiere
        # bascule (bug F8 du 19/11). Tous les callbacks acceptent **details ;
        # une exception est journalisee par _on_key_press sans tuer le listener.
        if key == self.mute_key:
            self._debug("hotkey_seen", key="F8")
            self.on_toggle_mute(source="hotkey", key="F8")
        elif key == self.sleep_key and self.on_toggle_sleep:
            self._debug("hotkey_seen", key="F9")
            self.on_toggle_sleep(source="hotkey", key="F9")
        elif key in (
            keyboard.Key.enter,
            keyboard.Key.up,
            keyboard.Key.down,
            keyboard.Key.left,
            keyboard.Key.right,
            keyboard.Key.home,
            keyboard.Key.end,
        ):
            if self.on_cursor_moved:
                self.on_cursor_moved(source="hotkey_nav", key=str(key))

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        if pressed and self.on_cursor_moved:
            self.on_cursor_moved(source="mouse_click", button=str(button))

    def start(self) -> None:
        if self._kb_listener is None:
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kb_listener.daemon = True
            self._kb_listener.start()
        if self._mouse_listener is None:
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

    def stop(self) -> None:
        if self._kb_listener is not None:
            self._kb_listener.stop()
            self._kb_listener = None
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
