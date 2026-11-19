# -*- coding: utf-8 -*-
"""Raccourcis globaux F8/F9 — dispatch et survie du listener (17/11).

Une exception non interceptée dans le callback pynput tue silencieusement le
thread du listener : plus aucun raccourci après ça. Le diagnostic du 17/11
(hook muet en conditions réelles) impose que `_on_key_press` n'ait jamais de
propagation et que les erreurs soient journalisées.

Régression du 19/11 : le repli `except TypeError: on_toggle_mute()` était
appelé APRÈS une bascule déjà appliquée — la seconde bascule annulait la
première et F8 ne changeait jamais l'état. Le doublon venait de
`source="hotkey"` arrivant dans `**details` de toggle_mute.
"""

from __future__ import annotations

from types import SimpleNamespace

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


def test_typeerror_in_callback_is_not_called_twice() -> None:
    """Régression 19/11 : le repli sur TypeError provoquait une double bascule.

    F8 appelait on_toggle_mute(source="hotkey") -> toggle_mute basculait puis
    plantait dans log_action (source en double) -> le repli rappelait
    on_toggle_mute() -> seconde bascule qui annulait la premiere. Un callback
    qui plante ne doit etre invoque qu'une seule fois.
    """
    calls: list[dict] = []

    def boom(**kwargs) -> None:
        calls.append(kwargs)
        raise TypeError("source en double (bug 19/11)")

    monitor = GlobalInputMonitor(on_toggle_mute=boom, on_debug=None)
    monitor._on_key_press(keyboard.Key.f8)
    assert calls == [{"source": "hotkey", "key": "F8"}]  # appele UNE fois


def test_toggle_mute_and_sleep_accept_the_hotkey_kwarg_without_typeerror() -> None:
    """F8/F9 avec source="hotkey" ne doivent plus planter dans log_action."""
    from phenix_voice.main import PhenixVoiceController

    logs: list[tuple[str, dict]] = []
    fake = SimpleNamespace(
        engine=object(),  # pret : le toggle n'est pas ignore
        is_muted=False,
        is_sleeping=False,
        capture=SimpleNamespace(set_paused=lambda _paused: None),
        hud=SimpleNamespace(set_state=lambda _state: None),
        processor=SimpleNamespace(reset_context=lambda: None),
        injection_logger=SimpleNamespace(
            log_action=lambda action, **details: logs.append((action, details))
        ),
        _exit_spelling_mode=lambda: None,
    )
    fake._normalize_source_arg = (
        lambda value: PhenixVoiceController._normalize_source_arg(fake, value)
    )

    # Meme chemin d'appel que hotkeys.py (source + key en mots-cles).
    PhenixVoiceController.toggle_mute(fake, source="hotkey", key="F8")
    assert fake.is_muted is True  # bascule appliquee une seule fois
    assert logs == [
        (
            "mic_state_changed",
            {
                "source": "hotkey",
                "previous_muted": False,
                "muted": True,
                "sleeping": False,
                "key": "F8",
            },
        )
    ]

    logs.clear()
    PhenixVoiceController.toggle_sleep(fake, source="hotkey", key="F9")
    assert fake.is_sleeping is True
    assert logs[0][0] == "sleep_state_changed"
    assert logs[0][1]["source"] == "hotkey"


def test_mute_mic_completely_logs_without_typeerror() -> None:
    """La commande vocale « Couper Phénix » ne doit plus tuer le tour de boucle.

    Régression 19/11 : log_action recevait action="mute_completely" alors que
    le paramètre positionnel s'appelle deja action -> TypeError journalise
    dans _stt_worker_loop.
    """
    from phenix_voice.main import PhenixVoiceController

    logs: list[tuple[str, dict]] = []
    fake = SimpleNamespace(
        engine=object(),
        is_muted=False,
        is_sleeping=False,
        capture=SimpleNamespace(set_paused=lambda _paused: None),
        hud=SimpleNamespace(set_state=lambda _state: None),
        injection_logger=SimpleNamespace(
            log_action=lambda action, **details: logs.append((action, details))
        ),
    )

    PhenixVoiceController.mute_mic_completely(fake)
    assert fake.is_muted is True
    assert logs == [
        (
            "mic_state_changed",
            {
                "source": "voice",
                "previous_muted": False,
                "muted": True,
                "sleeping": False,
                "via": "voice_command",
            },
        )
    ]
