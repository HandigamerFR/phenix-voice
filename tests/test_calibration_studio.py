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
