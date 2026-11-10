"""Détection d'activité vocale (Silero VAD v5 ONNX) et découpage temps réel par souffle."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Callable
import numpy as np
import onnxruntime as ort
import requests

SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
CHUNK_SAMPLES = 512  # 32 ms à 16 kHz
CONTEXT_SAMPLES = 64  # Contexte requis par Silero VAD v5 à 16 kHz


def ensure_silero_vad_model(model_path: str | Path = "models/silero_vad.onnx") -> Path:
    """Télécharge le modèle léger Silero VAD ONNX (~2 Mo) s'il n'est pas déjà présent."""
    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size < 100_000:
        resp = requests.get(SILERO_VAD_URL, timeout=30)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return path


class SileroVAD:
    """Wrapper ONNX ultra-rapide (< 0,2 ms/trame) pour Silero VAD v5 à 16 kHz."""

    def __init__(self, model_path: str | Path = "models/silero_vad.onnx") -> None:
        resolved = ensure_silero_vad_model(model_path)
        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(resolved), so, providers=["CPUExecutionProvider"]
        )
        self.sr_tensor = np.array(16000, dtype=np.int64)
        self.reset_states()

    def reset_states(self) -> None:
        """Réinitialise l'état récurrent LSTM/GRU et le tampon de contexte."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)

    def process_chunk(self, chunk_512: np.ndarray) -> float:
        """Évalue la probabilité de parole [0.0, 1.0] sur un bloc de 512 échantillons (32 ms)."""
        arr = np.asarray(chunk_512, dtype=np.float32).reshape(1, -1)
        if arr.shape[1] < CHUNK_SAMPLES:
            arr = np.pad(arr, ((0, 0), (0, CHUNK_SAMPLES - arr.shape[1])), mode="constant")
        elif arr.shape[1] > CHUNK_SAMPLES:
            arr = arr[:, :CHUNK_SAMPLES]

        x = np.concatenate([self._context, arr], axis=1)
        out, self._state = self.session.run(
            None,
            {
                "input": x,
                "state": self._state,
                "sr": self.sr_tensor,
            },
        )
        self._context = x[:, -CONTEXT_SAMPLES:]
        return float(out[0, 0])


class BreathSegmenter:
    """Découpe un flux audio continu 16 kHz en segments de parole par souffle (micro-pauses).

    Pensé pour une diction dysarthrique :
    - Conserve un pré-tampon (`pre_roll_ms`) pour ne jamais tronquer l'attaque du premier mot.
    - Tolère les micro-hésitations internes avant de valider une fin de souffle (`silence_pause_ms`).
    - Découpe automatiquement à `max_segment_s` (5,2s par défaut) pour garantir une transcription
      dans le palier GPU ultra-rapide (< 250 ms).
    """

    def __init__(
        self,
        vad: SileroVAD | None = None,
        speech_threshold: float = 0.45,
        silence_threshold: float = 0.30,
        pre_roll_ms: int = 288,
        min_speech_ms: int = 224,
        silence_pause_ms: int = 384,
        max_segment_s: float = 5.2,
        on_speech_state_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.vad = vad or SileroVAD()
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold

        chunk_ms = 32  # 512 / 16000 = 32 ms
        self.pre_roll_chunks = max(1, pre_roll_ms // chunk_ms)
        self.min_speech_chunks = max(1, min_speech_ms // chunk_ms)
        self.silence_pause_chunks = max(2, silence_pause_ms // chunk_ms)
        self.max_segment_chunks = int((max_segment_s * 1000) // chunk_ms)

        self.on_speech_state_change = on_speech_state_change

        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_chunks)
        self._active_chunks: list[np.ndarray] = []
        self._is_speaking = False
        self._speech_chunks_count = 0
        self._silence_chunks_count = 0

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def reset(self) -> None:
        self.vad.reset_states()
        self._pre_roll.clear()
        self._active_chunks.clear()
        if self._is_speaking and self.on_speech_state_change:
            self.on_speech_state_change(False)
        self._is_speaking = False
        self._speech_chunks_count = 0
        self._silence_chunks_count = 0

    def feed_chunk(self, chunk_512: np.ndarray) -> np.ndarray | None:
        """Ingère un bloc de 512 échantillons (32 ms). Retourne un segment audio complet
        dès qu'une fin de souffle est détectée, ou `None` sinon.
        """
        chunk = np.asarray(chunk_512, dtype=np.float32).reshape(-1)
        prob = self.vad.process_chunk(chunk)

        if not self._is_speaking:
            self._pre_roll.append(chunk)
            if prob >= self.speech_threshold:
                self._is_speaking = True
                self._speech_chunks_count = 1
                self._silence_chunks_count = 0
                self._active_chunks = list(self._pre_roll)
                self._pre_roll.clear()
                if self.on_speech_state_change:
                    self.on_speech_state_change(True)
            return None

        # En cours de parole
        self._active_chunks.append(chunk)
        if prob >= self.silence_threshold:
            self._speech_chunks_count += 1
            self._silence_chunks_count = 0
        else:
            self._silence_chunks_count += 1

        # Fin de souffle par micro-pause ou atteinte de la durée maximale du palier rapide
        reached_pause = self._silence_chunks_count >= self.silence_pause_chunks
        reached_max = len(self._active_chunks) >= self.max_segment_chunks

        if reached_pause or reached_max:
            valid_speech = self._speech_chunks_count >= self.min_speech_chunks
            segment = (
                np.concatenate(self._active_chunks, axis=0) if valid_speech else None
            )
            self._active_chunks.clear()
            self._is_speaking = False
            self._speech_chunks_count = 0
            self._silence_chunks_count = 0
            if self.on_speech_state_change:
                self.on_speech_state_change(False)
            return segment

        return None
