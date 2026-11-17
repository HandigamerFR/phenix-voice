"""Studio mixte (décision 13/11) : prompts OTAN + corpus naturel + navigation.

- 26 mots OTAN (`nato_*`) → filet acoustique DTW du mode épellation ;
- 12 phrases naturelles (`corpus_*`) → corpus de l'étape 5 (MFA + LoRA) ;
- démarrage au premier prompt non enregistré + bouton « ⬅️ Précédent ».
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from phenix_voice.ui.calibration_studio import (
    CORPUS_PROMPTS,
    CORPUS_TEXTS,
    ENRICHED_PROMPTS,
    FULL_CORPUS_PROMPTS,
    GUIDED_MAX_ATTEMPTS,
    NATO_PROMPTS,
    NATO_VOCABULARY,
    CalibrationStudioWindow,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_nato_prompts_cover_the_26_word_alphabet() -> None:
    assert len(NATO_VOCABULARY) == 26
    assert len(NATO_PROMPTS) == 26
    letters = {p.expected_text for p in NATO_PROMPTS}
    assert len(letters) == 26
    for prompt in NATO_PROMPTS:
        assert prompt.id.startswith("nato_")
        assert "filet acoustique" in prompt.category.lower() or "otan" in prompt.category.lower()


def test_corpus_prompts_cover_the_12_natural_texts() -> None:
    assert len(CORPUS_TEXTS) == 12
    assert len(CORPUS_PROMPTS) == 12
    assert [p.id for p in CORPUS_PROMPTS] == [f"corpus_{i:02d}" for i in range(1, 13)]
    for prompt, text in zip(CORPUS_PROMPTS, CORPUS_TEXTS):
        assert prompt.expected_text == text


def test_enriched_prompts_are_unique_and_complete() -> None:
    # 12 commandes/ponctuation + 26 OTAN + 12 corpus + 384 phrases d'étalonnage
    assert len(ENRICHED_PROMPTS) == 50 + len(FULL_CORPUS_PROMPTS)
    assert len(FULL_CORPUS_PROMPTS) == 384
    ids = [p.id for p in ENRICHED_PROMPTS]
    assert len(ids) == len(set(ids)), "ids de prompts en double"
    assert set(ids) >= {p.id for p in NATO_PROMPTS} | {p.id for p in CORPUS_PROMPTS}
    assert [p.id for p in FULL_CORPUS_PROMPTS] == [
        f"utt{i:04d}" for i in range(1, 385)
    ]


def test_first_missing_index_starts_at_first_unrecorded_prompt() -> None:
    fake = SimpleNamespace(prompts=ENRICHED_PROMPTS, recorded_entries=[])
    assert CalibrationStudioWindow._first_missing_index(fake) == 0
    # Les 3 premiers sont enregistrés → on démarre au 4e
    fake.recorded_entries = [{"id": p.id} for p in ENRICHED_PROMPTS[:3]]
    assert CalibrationStudioWindow._first_missing_index(fake) == 3
    # Tout est enregistré → reboucle au début (aucun manquant)
    fake.recorded_entries = [{"id": p.id} for p in ENRICHED_PROMPTS]
    assert CalibrationStudioWindow._first_missing_index(fake) == 0


def test_prev_button_is_disabled_on_first_prompt() -> None:
    loaded: list[int] = []
    fake = SimpleNamespace(current_index=0, _load_prompt=loaded.append)
    CalibrationStudioWindow._prev_current(fake)
    assert loaded == [], "rien avant le premier prompt"


def test_prev_button_goes_back_one_prompt() -> None:
    loaded: list[int] = []
    fake = SimpleNamespace(current_index=5, _load_prompt=loaded.append)
    CalibrationStudioWindow._prev_current(fake)
    assert loaded == [4]
    fake.current_index = 1
    CalibrationStudioWindow._prev_current(fake)
    assert loaded == [4, 0]


def test_replay_button_plays_the_recording_before_validation(
    qapp, tmp_path, monkeypatch
) -> None:
    """🔊 « Réécouter » : rejoue l'enregistrement avant de trancher valider/fourcher."""
    import numpy as np

    from phenix_voice.ui import calibration_studio as cs

    played: list[tuple] = []
    stops: list[int] = []
    monkeypatch.setattr(cs.sd, "play", lambda audio, sr: played.append((audio, sr)))
    monkeypatch.setattr(cs.sd, "stop", lambda: stops.append(1))

    win = cs.CalibrationStudioWindow(output_dir=tmp_path / "calib")
    try:
        # Présent, mais inactif tant qu'aucun enregistrement n'a été analysé
        assert hasattr(win, "play_btn")
        assert not win.play_btn.isEnabled()
        assert win._current_audio is None

        # Enregistrement prêt -> bouton activé (via la zone de validation)
        audio = np.zeros(1600, dtype=np.float32)
        win._current_audio = audio
        win.play_btn.setEnabled(True)

        # Lecture : rejoue exactement l'audio en attente, au bon taux
        win._play_current_audio()
        assert played, "sd.play jamais appelé"
        assert played[-1][0] is audio
        assert played[-1][1] == win.sample_rate

        # Valider -> la lecture en cours est coupée avant sauvegarde
        win._stop_playback()
        assert stops, "sd.stop jamais appelé"
    finally:
        win.close()


def test_validation_auto_starts_the_next_recording_without_click(
    qapp, tmp_path, monkeypatch
) -> None:
    """✅ Valider -> l'enregistrement suivant démarre SEUL (accessibilité 16/11)."""
    import numpy as np
    from PySide6.QtTest import QTest

    from phenix_voice.ui import calibration_studio as cs

    class FakeStream:
        def __init__(self, **kwargs) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    streams: list[FakeStream] = []

    def make_stream(**kwargs):
        s = FakeStream(**kwargs)
        streams.append(s)
        return s

    monkeypatch.setattr(cs.sd, "InputStream", make_stream)
    monkeypatch.setattr(cs.sd, "play", lambda *a, **k: None)
    monkeypatch.setattr(cs.sd, "stop", lambda *a, **k: None)

    win = cs.CalibrationStudioWindow(output_dir=tmp_path / "calib")
    try:
        assert not win._is_recording
        # Simule un enregistrement analysé, prêt à valider
        win._current_audio = np.zeros(1600, dtype=np.float32)
        win._current_heard_text = ""
        first_index = win.current_index

        win._validate_and_next()

        # On est passé au prompt suivant
        assert win.current_index == first_index + 1
        # L'enregistrement suivant démarre SEUL (délai 500 ms), sans clic
        QTest.qWait(900)
        assert win._is_recording, "l'enregistrement automatique n'a pas demarre"
        assert streams and streams[-1].started
        # Le bouton reflète l'état « en train d'enregistrer »
        assert "Parlez" in win.record_btn.text()
    finally:
        if win._is_recording:
            win._toggle_recording()
        win.close()


def test_open_studio_from_app_sleeps_dictation_and_wakes_on_close(
    monkeypatch
) -> None:
    """Accès depuis l'app (bouton 🎙️ / « Ouvrir le studio ») : veille dictée + réveil."""
    import phenix_voice.ui.calibration_studio as cs
    from phenix_voice.main import PhenixVoiceController

    created: dict = {}

    class FakeStudio:
        def __init__(self, on_close=None) -> None:
            created["on_close"] = on_close
            self.visible = False
            self.loaded_index = None

        def isVisible(self) -> bool:
            return self.visible

        def _load_prompt(self, index: int) -> None:
            self.loaded_index = index

        def _first_missing_index(self) -> int:
            return 7

        def show(self) -> None:
            self.visible = True

        def raise_(self) -> None:
            pass

        def activateWindow(self) -> None:
            pass

    monkeypatch.setattr(cs, "CalibrationStudioWindow", FakeStudio)

    sleep_calls: list[str] = []
    fake = SimpleNamespace(
        _studio_window=None,
        _sleep_before_studio=False,
        is_sleeping=False,
        is_muted=False,
        injection_logger=SimpleNamespace(log_action=lambda *a, **k: None),
    )

    def fake_toggle_sleep(source_or_checked="ui", **details) -> None:
        sleep_calls.append(str(source_or_checked))
        fake.is_sleeping = not fake.is_sleeping

    fake.toggle_sleep = fake_toggle_sleep
    fake._on_studio_closed = lambda: PhenixVoiceController._on_studio_closed(fake)

    # Ouverture : reprise au premier manquant + dictée en veille
    PhenixVoiceController.open_calibration_studio(fake)
    assert fake._studio_window is not None
    assert fake._studio_window.loaded_index == 7
    assert fake._studio_window.visible
    assert sleep_calls == ["studio"]
    assert fake.is_sleeping is True

    # Fermeture du Studio : réveil automatique de la dictée
    PhenixVoiceController._on_studio_closed(fake)
    assert sleep_calls == ["studio", "studio_closed"]
    assert fake.is_sleeping is False


def test_hud_studio_signal_opens_the_studio(qapp) -> None:
    """La commande vocale (thread STT) passe par le signal → le callback d'ouverture."""
    from PySide6.QtTest import QSignalSpy

    from phenix_voice.ui.hud import HUDSignals

    opened: list[int] = []
    signals = HUDSignals()
    spy = QSignalSpy(signals.studio_requested)
    signals.studio_requested.connect(lambda: opened.append(1))

    signals.studio_requested.emit()  # équivalent de l'émission depuis le thread STT
    assert spy.count() == 1
    assert opened == [1]


# --- Mode « Lecture guidée » (zéro clic, exigence 17/11) ---------------------


def test_text_similarity_ignores_accents_case_and_punctuation() -> None:
    from phenix_voice.ui.calibration_studio import text_similarity

    assert text_similarity("Écoute.", "écoute") == 1.0
    assert text_similarity("J'ai écrit une lettre", "jai ecrit une lettre !") == 1.0
    assert text_similarity("", "") == 1.0
    assert text_similarity("Le renard brun saute.", "xyz") < 0.3
    assert text_similarity("", "phrase entière") == 0.0


def test_stutter_command_detection() -> None:
    from phenix_voice.ui.calibration_studio import is_stutter_command

    assert is_stutter_command("J'ai fourché")
    assert is_stutter_command("jai fourche.")
    assert is_stutter_command("Oups")
    # Une phrase du corpus qui ressemble à une commande reste de la dictée
    assert not is_stutter_command("Le renard brun saute près du vieux pont.")
    assert not is_stutter_command("J'ai écrit une lettre à ma sœur.")


def _make_guided_window(qapp, tmp_path, monkeypatch):
    """Fenêtre de test : moteur GPU et flux audio réels neutralisés."""
    import numpy as np

    from phenix_voice.ui import calibration_studio as cs

    monkeypatch.setattr(
        cs.CalibrationStudioWindow,
        "_init_gpu_engine",
        lambda self: None,  # pas de chargement Whisper dans les tests
    )
    monkeypatch.setattr(cs.sd, "play", lambda *a, **k: None)
    monkeypatch.setattr(cs.sd, "stop", lambda *a, **k: None)

    class FakeStream:
        def __init__(self, **kwargs) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    streams: list[FakeStream] = []
    monkeypatch.setattr(
        cs.sd,
        "InputStream",
        lambda **kw: streams.append(FakeStream(**kw)) or streams[-1],
    )

    win = cs.CalibrationStudioWindow(output_dir=tmp_path / "calib")
    win._test_streams = streams
    return win


class _FakeEngine:
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, audio):
        from types import SimpleNamespace

        return SimpleNamespace(text=self.text, alternatives=[], total_ms=12.0)


def _simulate_segment(win, heard_text: str) -> None:
    """Simule un enregistrement complet avec la transcription donnée."""
    import numpy as np

    win.stt_engine = _FakeEngine(heard_text)
    win._is_recording = True
    win._recorded_chunks = [np.zeros(512, dtype=np.float32)]
    win._auto_stop_requested = False
    win._stop_recording()


def test_guided_auto_validates_good_match_without_any_click(
    qapp, tmp_path, monkeypatch
) -> None:
    """Lecture guidée : transcription conforme -> validation + phrase suivante, 0 clic."""
    from PySide6.QtTest import QTest

    win = _make_guided_window(qapp, tmp_path, monkeypatch)
    try:
        assert win._guided
        first = win.current_index
        expected = win.prompts[first].expected_text

        _simulate_segment(win, expected)

        assert win.current_index == first + 1, "aucun passage à la phrase suivante"
        assert len(win.recorded_entries) == 1
        entry = win.recorded_entries[0]
        assert entry["id"] == win.prompts[first].id
        assert entry["review"] is False
        assert entry["heard_text"] == expected
        # La phrase suivante enregistre SEULE (aucun clic « Démarrer »)
        QTest.qWait(900)
        assert win._is_recording, "l'enregistrement automatique n'a pas demarre"
    finally:
        if win._is_recording:
            win._toggle_recording()
        win.close()


def test_guided_retries_same_prompt_on_bad_match(
    qapp, tmp_path, monkeypatch
) -> None:
    """Échec de vérification -> même phrase relue, audio abandonné (jamais de moyenne)."""
    from PySide6.QtTest import QTest

    win = _make_guided_window(qapp, tmp_path, monkeypatch)
    try:
        first = win.current_index
        _simulate_segment(win, "complètement différent de la phrase attendue")

        assert win.current_index == first, "il ne faut PAS avancer sur un échec"
        assert win._current_audio is None, "l'audio raté doit être abandonné"
        assert win._attempts == 1
        assert not win.recorded_entries
        # Reprise automatique du MÊME prompt (sans clic)
        QTest.qWait(900)
        assert win._is_recording
    finally:
        if win._is_recording:
            win._toggle_recording()
        win.close()


def test_guided_keeps_last_attempt_marked_review_after_three_failures(
    qapp, tmp_path, monkeypatch
) -> None:
    """3 échecs -> dernier essai conservé + marqué « à réviser » (pas de blocage)."""
    from PySide6.QtTest import QTest

    import numpy as np

    win = _make_guided_window(qapp, tmp_path, monkeypatch)
    try:
        first = win.current_index
        for _ in range(GUIDED_MAX_ATTEMPTS):
            win._current_audio = np.zeros(1600, dtype=np.float32)
            win._current_heard_text = "toujours pas la phrase attendue"
            win._guided_decide()

        assert win.current_index == first + 1, "après 3 essais, on avance quand même"
        assert len(win.recorded_entries) == 1
        assert win.recorded_entries[0]["review"] is True
        assert win._review_ids == [win.prompts[first].id]
        assert win.review_btn.text().endswith("1")
    finally:
        QTest.qWait(700)
        if win._is_recording:
            win._toggle_recording()
        win.close()


def test_guided_jai_fourche_rejects_the_last_validated_phrase(
    qapp, tmp_path, monkeypatch
) -> None:
    """« J'ai fourché » dit après avancement -> rejette la PREMIÈRE phrase validée."""
    from PySide6.QtTest import QTest

    import numpy as np

    win = _make_guided_window(qapp, tmp_path, monkeypatch)
    try:
        first = win.current_index
        # Phrase N validée automatiquement (transcription conforme)
        win._current_audio = np.zeros(1600, dtype=np.float32)
        win._current_heard_text = win.prompts[first].expected_text
        win._pending_review = False
        win._validate_and_next()
        assert win.current_index == first + 1
        assert any(e["id"] == win.prompts[first].id for e in win.recorded_entries)

        # Sur la phrase N+1, il dit « j'ai fourché » (sans lire la phrase)
        _simulate_segment(win, "j'ai fourché")

        # Retour sur N, entrée retirée du manifeste
        assert win.current_index == first, "il faut revenir sur la phrase rejetée"
        assert not any(
            e["id"] == win.prompts[first].id for e in win.recorded_entries
        )
    finally:
        QTest.qWait(900)
        if win._is_recording:
            win._toggle_recording()
        win.close()


def test_guided_validation_preserves_existing_manifest_entries(
    qapp, tmp_path, monkeypatch
) -> None:
    """Les enregistrements déjà effectués (78 en conditions réelles) sont conservés."""
    import json

    import numpy as np

    calib = tmp_path / "calib"
    (calib / "samples").mkdir(parents=True)
    existing = [
        {"id": "nato_alpha", "expected_text": "Alpha", "raw_wav": "x.wav"},
        {"id": "utt0001", "expected_text": "phrase un", "raw_wav": "y.wav"},
    ]
    (calib / "manifest.json").write_text(
        json.dumps({"samples": existing}), encoding="utf-8"
    )

    win = _make_guided_window(qapp, tmp_path, monkeypatch)
    try:
        assert len(win.recorded_entries) == 2
        # On démarre au premier prompt non enregistré (ni nato_alpha ni utt0001)
        assert win.prompts[win.current_index].id not in {"nato_alpha", "utt0001"}

        win._current_audio = np.zeros(1600, dtype=np.float32)
        win._current_heard_text = ""
        win._pending_review = False
        win._validate_and_next()

        ids = [e["id"] for e in win.recorded_entries]
        assert "nato_alpha" in ids and "utt0001" in ids, "perte d'enregistrements !"
        assert len(win.recorded_entries) == 3
    finally:
        from PySide6.QtTest import QTest

        QTest.qWait(700)
        if win._is_recording:
            win._toggle_recording()
        win.close()
