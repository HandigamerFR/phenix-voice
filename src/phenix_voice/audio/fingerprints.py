"""Reconnaissance d'empreintes acoustiques directes (Log-Mel + Dynamic Time Warping)
pour protéger les commandes vitales (« Écoute », « Au repos », « Corriger ça », « Oups »)
contre toute dérive du moteur de transcription textuelle.
"""

from __future__ import annotations

import json
from pathlib import Path
import wave
import numpy as np

from phenix_voice.audio.vad import CHUNK_SAMPLES, SileroVAD
from phenix_voice.stt.mel import compute_log_mel_spectrogram


def _extract_compact_mel_embedding(audio_pcm: np.ndarray) -> np.ndarray:
    """Extrait une séquence compacte de vecteurs Mel normalisés (L2 par trame) sur la partie active."""
    audio = np.asarray(audio_pcm, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    if peak > 1e-4:
        audio = audio * (0.85 / peak)

    # Découper aux bornes d'énergie vocale pour aligner le début et la fin du mot
    frame_len = 400
    hop = 160
    if len(audio) < frame_len:
        audio = np.pad(audio, (0, frame_len - len(audio)))

    n_frames = max(10, int(np.ceil(len(audio) / hop)))
    mel = compute_log_mel_spectrogram(audio, n_mels=80, target_frames=n_frames)[0]  # (80, T)

    # Sous-échantillonnage temporel par facteur 2 (pas de 20 ms) pour un DTW ultra-rapide (< 1 ms)
    mel_ds = mel[:, ::2].T  # (T', 80)
    # Centrage-réduction par canal + normalisation L2 par trame
    mel_ds = mel_ds - np.mean(mel_ds, axis=0, keepdims=True)
    norms = np.linalg.norm(mel_ds, axis=1, keepdims=True) + 1e-6
    return (mel_ds / norms).astype(np.float32)


def dtw_cosine_distance(seq_a: np.ndarray, seq_b: np.ndarray) -> float:
    """Calcule la distance DTW normalisée (dans [0, 2], 0 = identique) entre deux séquences (N, D) et (M, D)."""
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0:
        return 2.0
    # Ratio de durée trop différent -> rejet rapide
    if max(n, m) / max(1, min(n, m)) > 2.2:
        return 2.0

    # Matrice de coût cosinus : 1 - (A @ B.T)
    cost = 1.0 - np.clip(seq_a @ seq_b.T, -1.0, 1.0)
    dtw = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    dtw[0, 0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = cost[i - 1, j - 1]
            dtw[i, j] = c + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])

    return float(dtw[n, m] / (n + m))


class AcousticCommandProtector:
    """Compare un segment audio court aux empreintes vocales enregistrées par l'utilisateur
    dans `user_data/calibration/manifest.json`.
    """

    def __init__(
        self,
        manifest_path: str | Path = "user_data/calibration/manifest.json",
        distance_threshold: float = 0.24,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.distance_threshold = distance_threshold
        self.templates: dict[str, tuple[str, np.ndarray]] = {}
        self.reload_templates()

    def reload_templates(self) -> None:
        """Charge et pré-calcule les empreintes des commandes vitales depuis le manifeste d'étalonnage."""
        self.templates.clear()
        if not self.manifest_path.exists():
            return

        with open(self.manifest_path, encoding="utf-8") as f:
            data = json.load(f)

        vad = SileroVAD()
        for item in data.get("samples", []):
            item_id = item.get("id", "")
            if not item_id.startswith("cmd_"):
                continue
            wav_path = Path(item.get("norm_wav", ""))
            if not wav_path.exists():
                continue
            with wave.open(str(wav_path), "rb") as wf:
                pcm = (
                    np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(
                        np.float32
                    )
                    / 32768.0
                )
            vad.reset_states()
            probs = [
                vad.process_chunk(pcm[i : i + CHUNK_SAMPLES])
                for i in range(0, len(pcm), CHUNK_SAMPLES)
            ]
            active = [i for i, p in enumerate(probs) if p >= 0.35]
            if active:
                s = max(0, (active[0] - 4) * CHUNK_SAMPLES)
                e = min(len(pcm), (active[-1] + 6) * CHUNK_SAMPLES)
                pcm = pcm[s:e]

            emb = _extract_compact_mel_embedding(pcm)
            self.templates[item_id] = (item["expected_text"], emb)

    def match_command(self, audio_pcm: np.ndarray, sr: int = 16000) -> tuple[str, float] | None:
        """Si `audio_pcm` (court, <= 2,5s) correspond fortement à une commande vitale enregistrée,
        retourne `(expected_text, distance_dtw)`, sinon `None`.
        """
        if not self.templates:
            return None
        dur_s = len(audio_pcm) / sr
        if dur_s < 0.25 or dur_s > 2.6:
            return None

        emb = _extract_compact_mel_embedding(audio_pcm)
        best_text: str | None = None
        best_dist = 999.0

        for _, (expected_text, ref_emb) in self.templates.items():
            dist = dtw_cosine_distance(emb, ref_emb)
            if dist < best_dist:
                best_dist = dist
                best_text = expected_text

        if best_text is not None and best_dist <= self.distance_threshold:
            return best_text, best_dist
        return None
