"""Extracteur Log-Mel Spectrogramme ultra-rapide en NumPy pur (compatible OpenAI Whisper)."""

from __future__ import annotations

from functools import lru_cache
import numpy as np


def _hz_to_mel_slaney(freq_hz: np.ndarray | float) -> np.ndarray | float:
    """Convertit des fréquences Hz en échelle Mel Slaney (identique à librosa / Whisper)."""
    f_min = 0.0
    f_sp = 200.0 / 3.0
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0

    freq = np.asarray(freq_hz, dtype=np.float64)
    mels = (freq - f_min) / f_sp
    log_mask = freq >= min_log_hz
    if np.any(log_mask):
        if freq.ndim == 0:
            mels = min_log_mel + np.log(freq / min_log_hz) / logstep
        else:
            mels[log_mask] = min_log_mel + np.log(freq[log_mask] / min_log_hz) / logstep
    return mels


def _mel_to_hz_slaney(mels: np.ndarray) -> np.ndarray:
    """Convertit l'échelle Mel Slaney vers des fréquences en Hz."""
    f_min = 0.0
    f_sp = 200.0 / 3.0
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0

    mels_arr = np.asarray(mels, dtype=np.float64)
    freqs = f_min + f_sp * mels_arr
    log_mask = mels_arr >= min_log_mel
    freqs[log_mask] = min_log_hz * np.exp(logstep * (mels_arr[log_mask] - min_log_mel))
    return freqs


@lru_cache(maxsize=4)
def get_mel_filters(
    sr: int = 16000,
    n_fft: int = 400,
    n_mels: int = 128,
) -> np.ndarray:
    """Construit la matrice de filtres Mel normalisée Slaney `(n_mels, 1 + n_fft // 2)`."""
    n_freqs = 1 + n_fft // 2
    fft_freqs = np.linspace(0.0, sr / 2.0, n_freqs, dtype=np.float64)

    mel_min = _hz_to_mel_slaney(0.0)
    mel_max = _hz_to_mel_slaney(sr / 2.0)
    mel_pts = np.linspace(mel_min, mel_max, n_mels + 2, dtype=np.float64)
    filter_freqs = _mel_to_hz_slaney(mel_pts)
    filter_diff = np.diff(filter_freqs)

    ramps = np.subtract.outer(filter_freqs, fft_freqs)
    weights = np.zeros((n_mels, n_freqs), dtype=np.float64)
    for i in range(n_mels):
        lower = -ramps[i] / filter_diff[i]
        upper = ramps[i + 2] / filter_diff[i + 1]
        weights[i] = np.maximum(0.0, np.minimum(lower, upper))

    # Normalisation Slaney (surface unitaire par canal)
    enorm = 2.0 / (filter_freqs[2 : n_mels + 2] - filter_freqs[:n_mels])
    weights *= enorm[:, np.newaxis]
    return weights.astype(np.float32)


@lru_cache(maxsize=2)
def _get_hann_window(n_fft: int = 400) -> np.ndarray:
    """Fenêtre de Hann périodique identique à `torch.hann_window(n_fft, periodic=True)`."""
    return np.hanning(n_fft + 1)[:-1].astype(np.float32)


def compute_log_mel_spectrogram(
    audio_pcm: np.ndarray,
    n_mels: int = 128,
    target_frames: int = 3000,
    n_fft: int = 400,
    hop_length: int = 160,
    sr: int = 16000,
) -> np.ndarray:
    """Calcule le spectrogramme Log-Mel `(1, n_mels, target_frames)` attendu par Whisper.

    Le signal `audio_pcm` (float32 mono 16 kHz dans [-1, 1]) est complété par du silence
    jusqu'à `target_frames * hop_length` échantillons (ex: 300 frames = 3s, 500 frames = 5s,
    3000 frames = 30s).
    """
    audio = np.asarray(audio_pcm, dtype=np.float32).reshape(-1)
    target_samples = target_frames * hop_length

    if len(audio) >= target_samples:
        audio = audio[:target_samples]
    else:
        audio = np.pad(audio, (0, target_samples - len(audio)), mode="constant")

    # Padding reflect centré de n_fft // 2 comme torch.stft(..., center=True)
    pad = n_fft // 2
    padded = np.pad(audio, (pad, pad), mode="reflect")

    # Découpage vectorisé en trames sans copie mémoire (stride_tricks)
    num_frames = 1 + (len(padded) - n_fft) // hop_length
    shape = (num_frames, n_fft)
    strides = (padded.strides[0] * hop_length, padded.strides[0])
    frames = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)

    windowed = frames * _get_hann_window(n_fft)
    stft_spec = np.fft.rfft(windowed, n=n_fft, axis=1)
    # Whisper ignore la toute dernière trame pour obtenir exactement target_frames
    magnitudes = np.abs(stft_spec[:-1, :]) ** 2  # (target_frames, 201)

    filters = get_mel_filters(sr=sr, n_fft=n_fft, n_mels=n_mels)  # (n_mels, 201)
    mel_spec = filters @ magnitudes.T  # (n_mels, target_frames)

    log_spec = np.log10(np.maximum(mel_spec, 1e-10))
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0

    return log_spec[np.newaxis, :, :].astype(np.float32)
