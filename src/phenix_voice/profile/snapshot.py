"""Snapshots / points de restauration du profil vocal et journal de session avec audio.

Objectifs :
- Garder une trace des dictées (audio + texte reconnu/injecté) pour le développement,
  avec une rotation bornée pour ne pas saturer le disque.
- Journaliser les actions d'injection/frappes (par action) et les commandes reconnues
  pour diagnostiquer les écarts entre audio, reconnaissance et texte réellement envoyé.
- Permettre la sauvegarde et la restauration du profil vocal (règles apprises,
  corrections apprises, calibration) avant/après des opérations sensibles.
"""

from __future__ import annotations

import ctypes
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import wave

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
except Exception:
    _user32 = None


@dataclass
class SnapshotInfo:
    name: str
    path: Path
    created_at: str
    size_bytes: int


PROFILE_DIRS = (
    "user_data/calibration",
    "user_data/corrections_learned",
)
PROFILE_FILES = (
    "user_data/learned_rules.json",
)


class ProfileSnapshotManager:
    """Crée et restaure des instantanés du profil vocal (règles, corrections, calibration)."""

    def __init__(self, snapshots_dir: str | Path = "user_data/snapshots") -> None:
        self.snapshots_dir = Path(snapshots_dir)

    def create_snapshot(self, label: str = "") -> SnapshotInfo | None:
        try:
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_label = "".join(
                ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label.strip()
            )[:40]
            name = f"{ts}" + (f"_{safe_label}" if safe_label else "")
            dest = self.snapshots_dir / name
            dest.mkdir(parents=True, exist_ok=True)

            for rel_dir in PROFILE_DIRS:
                src = Path(rel_dir)
                if src.exists():
                    shutil.copytree(src, dest / src.name, dirs_exist_ok=True)
            for rel_file in PROFILE_FILES:
                src = Path(rel_file)
                if src.exists():
                    shutil.copy2(src, dest / src.name)

            size_bytes = sum(
                p.stat().st_size for p in dest.rglob("*") if p.is_file()
            )
            return SnapshotInfo(
                name=name,
                path=dest,
                created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                size_bytes=size_bytes,
            )
        except Exception:
            return None

    def list_snapshots(self) -> list[SnapshotInfo]:
        infos: list[SnapshotInfo] = []
        if not self.snapshots_dir.exists():
            return infos
        for p in sorted(self.snapshots_dir.iterdir(), key=lambda x: x.name, reverse=True):
            if not p.is_dir():
                continue
            size_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            infos.append(
                SnapshotInfo(
                    name=p.name,
                    path=p,
                    created_at=time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)
                    ),
                    size_bytes=size_bytes,
                )
            )
        return infos

    def restore_snapshot(self, name: str) -> bool:
        snap = self.snapshots_dir / name
        if not snap.exists():
            return False
        try:
            for rel_dir in PROFILE_DIRS:
                src = snap / Path(rel_dir).name
                if src.exists():
                    dest = Path(rel_dir)
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(src, dest)
            for rel_file in PROFILE_FILES:
                src = snap / Path(rel_file).name
                if src.exists():
                    dest = Path(rel_file)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
            return True
        except Exception:
            return False


class SessionTraceLogger:
    """Journalise les dictées avec audio (rotation bornée) pour le développement."""

    def __init__(
        self,
        audio_dir: str | Path = "user_data/session_audio",
        log_path: str | Path = "logs/session_trace.jsonl",
        max_audio_files: int = 300,
    ) -> None:
        self.audio_dir = Path(audio_dir)
        self.log_path = Path(log_path)
        self.max_audio_files = max_audio_files

    def log(
        self,
        audio_pcm: np.ndarray | None,
        raw_stt: str,
        arbitrated: str,
        intent: str,
        injected: str,
        alternatives: list[str] | None = None,
        extra: dict | None = None,
    ) -> str | None:
        try:
            self.audio_dir.mkdir(parents=True, exist_ok=True)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            audio_rel: str | None = None
            if audio_pcm is not None and len(audio_pcm) > 0:
                wav_path = self.audio_dir / f"seg_{ts}.wav"
                pcm16 = np.clip(audio_pcm * 32767.0, -32768, 32767).astype(np.int16)
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm16.tobytes())
                audio_rel = str(wav_path)
                self._prune_audio()

            record = {
                "ts": ts,
                "clock": time.strftime("%H:%M:%S"),
                "raw_stt": raw_stt,
                "arbitrated": arbitrated,
                "intent": intent,
                "injected": injected,
                "alts": (alternatives or [])[:4],
                "audio": audio_rel,
            }
            if extra:
                record.update(extra)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return ts
        except Exception:
            return None

    def _prune_audio(self) -> None:
        try:
            files = sorted(
                self.audio_dir.glob("seg_*.wav"),
                key=lambda p: p.stat().st_mtime,
            )
            excess = len(files) - self.max_audio_files
            for p in files[: max(0, excess)]:
                try:
                    p.unlink()
                except Exception:
                    pass
        except Exception:
            pass


def _get_foreground_window_info() -> tuple[int, str]:
    if _user32 is None:
        return 0, ""
    try:
        hwnd = int(_user32.GetForegroundWindow() or 0)
        if not hwnd:
            return 0, ""
        buf = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, buf, 512)
        return hwnd, (buf.value or "").strip()
    except Exception:
        return 0, ""


class InjectionTraceLogger:
    """Journal de session des actions d'injection/frappes (par action) et des commandes reconnues."""

    def __init__(
        self,
        log_path: str | Path = "logs/injection_trace.jsonl",
        session_id: str | None = None,
    ) -> None:
        self.log_path = Path(log_path)
        self.session_id = session_id or time.strftime("session_%Y%m%d_%H%M%S")
        self._current_segment: dict | None = None

    def set_segment_context(
        self,
        segment_ts: str | None = None,
        audio: str | None = None,
        intent: str | None = None,
        raw_stt: str | None = None,
        arbitrated: str | None = None,
    ) -> None:
        self._current_segment = {
            "segment_ts": segment_ts,
            "audio": audio,
            "intent": intent,
            "raw_stt": raw_stt,
            "arbitrated": arbitrated,
        }

    def clear_segment_context(self) -> None:
        self._current_segment = None

    def log_action(self, action: str, **details) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            hwnd, title = _get_foreground_window_info()
            record = {
                "ts": time.strftime("%Y%m%d_%H%M%S"),
                "clock": time.strftime("%H:%M:%S"),
                "mono": round(time.monotonic(), 6),
                "session_id": self.session_id,
                "action": action,
                "target_hwnd": hwnd,
                "target_window": title[:200],
            }
            if self._current_segment:
                record.update({k: v for k, v in self._current_segment.items() if v is not None})
            for k, v in details.items():
                if v is not None:
                    record[k] = v
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass
