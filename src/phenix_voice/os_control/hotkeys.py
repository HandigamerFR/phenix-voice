"""Écoute globale des raccourcis clavier physiques et des clics souris de repositionnement."""

from __future__ import annotations

from typing import Callable
from pynput import keyboard, mouse


class GlobalInputMonitor:
    """Surveille en arrière-plan :
    - Le raccourci physique de bascule du micro (`F8` par défaut : Actif <-> Au repos).
    - Les clics souris ou touches de navigation (`Entrée`, `Flèches`) pour informer
      le post-processeur que la position du curseur a pu changer.
    """

    def __init__(
        self,
        on_toggle_mic: Callable[[], None],
        on_cursor_moved: Callable[[], None] | None = None,
        toggle_key: keyboard.Key = keyboard.Key.f8,
    ) -> None:
        self.on_toggle_mic = on_toggle_mic
        self.on_cursor_moved = on_cursor_moved
        self.toggle_key = toggle_key

        self._kb_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key == self.toggle_key:
            self.on_toggle_mic()
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
                self.on_cursor_moved()

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        if pressed and self.on_cursor_moved:
            self.on_cursor_moved()

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
