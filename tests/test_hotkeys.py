# -*- coding: utf-8 -*-
"""Raccourcis globaux F8/F9 — dispatch et survie du listener (17/11).

Une exception non interceptée dans le callback pynput tue silencieusement le
thread du listener : plus aucun raccourci après ça. Le diagnostic du 17/11
(hook muet en conditions réelles) impose que `_on_key_press` n'ait jamais de
propagation et que les erreurs soient journalisées.
"""

from __future__ import annotations

from pynput import keyboard

from phenix_voice.os_control.hotkeys import GlobalInputMonitor


def test_f8_and_f9_dispatch_to_the_right_callback() -> None:
    calls: list[tuple[str, dict]] = []
    monitor = GlobalInputMonitor(
        on_toggle_mute=lambda **kw: calls.append(("mute", kw)),
        on_toggle_sleep=lambda **kw: calls.append(("sleep", kw)),
    )
    monitor._on_key_press(keyboard.Key.f8)
    monitor._on_key_press(keyboard.Key.f9)
    assert calls == [
        ("mute", {"source": "hotkey", "key": "F8"}),
        ("sleep", {"source": "hotkey", "key": "F9"}),
    ]


def test_callback_exception_is_logged_and_never_propagates() -> None:
    """Le callback utilisateur plante -> journalisé, le listener survit."""
    events: list[tuple[str, dict]] = []

    def boom(**_kwargs) -> None:
        raise RuntimeError("panne simulee")

    monitor = GlobalInputMonitor(
        on_toggle_mute=boom,
        on_debug=lambda event, **details: events.append((event, details)),
    )
    monitor._on_key_press(keyboard.Key.f8)  # ne doit pas lever
    assert [e[0] for e in events] == ["hotkey_seen", "hotkey_error"]
    assert "RuntimeError" in events[1][1]["error"]


def test_unknown_keys_are_ignored() -> None:
    calls: list[dict] = []
    monitor = GlobalInputMonitor(on_toggle_mute=lambda **kw: calls.append(kw))
    monitor._on_key_press(keyboard.KeyCode.from_char("a"))
    monitor._on_key_press(None)
    assert calls == []


def test_without_debug_callback_errors_still_swallowed() -> None:
    def boom(**_kwargs) -> None:
        raise ValueError("sans journal")

    monitor = GlobalInputMonitor(on_toggle_mute=boom, on_debug=None)
    monitor._on_key_press(keyboard.Key.f8)  # ne doit pas lever
