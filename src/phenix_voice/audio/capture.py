"""Capture microphone faible latence (16 kHz Mono float32) via PortAudio / sounddevice."""

from __future__ import annotations

import queue
import threading
from typing import Callable
import numpy as np
import sounddevice as sd

from phenix_voice.audio.vad import BreathSegmenter, CHUNK_SAMPLES


class MicrophoneCapture:
    """Capture continue du microphone par blocs de 512 échantillons (32 ms à 16 kHz)
    et transmission des segments de souffle complets à une fonction de rappel.
    """

    def __init__(
        self,
        on_segment_ready: Callable[[np.ndarray], None],
        segmenter: BreathSegmenter | None = None,
        device: int | str | None = None,
        sample_rate: int = 16000,
    ) -> None:
        self.on_segment_ready = on_segment_ready
        self.segmenter = segmenter or BreathSegmenter()
        self.device = device
        self.sample_rate = sample_rate

        self._chunk_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=256)
        self._stream: sd.InputStream | None = None
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        """Coupe ou reprend l'analyse vocale instantanément."""
        self._paused = paused
        if paused:
            self.segmenter.reset()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if self._paused or not self._running:
            return
        try:
            self._chunk_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def _worker_loop(self) -> None:
        while self._running:
            chunk = self._chunk_queue.get()
            if chunk is None:
                break
            if self._paused:
                continue
            segment = self.segmenter.feed_chunk(chunk)
            if segment is not None:
                self.on_segment_ready(segment)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="PhenixAudioVADWorker", daemon=True
        )
        self._worker_thread.start()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=CHUNK_SAMPLES,
            device=self.device,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._chunk_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None
        self.segmenter.reset()
