"""Fixtures partagées pour éviter d'instancier plusieurs moteurs GPU en VRAM pendant les tests."""

from __future__ import annotations

import pytest
from phenix_voice.stt.engine import WhisperDirectMLEngine


@pytest.fixture(scope="session")
def shared_engine() -> WhisperDirectMLEngine:
    return WhisperDirectMLEngine()
