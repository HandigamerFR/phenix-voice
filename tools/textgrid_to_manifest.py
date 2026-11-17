# -*- coding: utf-8 -*-
"""Convertit l'alignement MFA (TextGrid) en manifeste JSONL pour `lora_train.py`.

Entrée : `corpus/mfa_aligned/<locuteur>/*.TextGrid` (sortie de `mfa align`) +
         les WAV de `corpus/mfa_in/<locuteur>/` (MFA n'exporte pas l'audio).
Sortie : `corpus/lora_manifest.jsonl` — une ligne par segment d'entraînement :

    {"audio": "lora_segments/utt0001.wav", "text": "Le soleil se leve..."}

Particularités (ce que MFA apporte réellement) :
- **recoupe aux bornes de parole** (premier/dernier mot, marge 0,1 s) : moins
  de silence inutile dans l'audio d'entraînement ;
- **découpe les phrases plus longues que `--max-seconds`** aux frontières de
  mots (jamais de troncature brute par `lora_train --max-frames`) ;
- **filtre par ratio de parole** (`--min-speech-ratio`) : un segment où les
  mots n'occupent qu'une petite part du temps = lecture douteuse ;
- le **texte de référence est celui du .txt original** (casse + ponctuation
  conservées — les TextGrid MFA sont en minuscules, inutilisables tels quels).

Usage :
    python tools/textgrid_to_manifest.py [--speaker laure] [--max-seconds 9.5]
        [--min-speech-ratio 0.45] [--out corpus/lora_manifest.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ALIGNED_ROOT = ROOT / "corpus" / "mfa_aligned"
SOURCE_ROOT = ROOT / "corpus" / "mfa_in"

_WORD_RE = re.compile(
    r'xmin\s*=\s*([0-9.]+)\s*\n\s*xmax\s*=\s*([0-9.]+)\s*\n\s*text\s*=\s*"([^"]*)"',
    re.MULTILINE,
)


def parse_textgrid_words(path: Path) -> list[tuple[float, float, str]]:
    """Mots du tier « words » uniquement : [(xmin, xmax, texte), ...].

    MFA produit 2 tiers (words puis phones) au même format — sans ce filtre,
    les phones seraient comptés deux fois (speech_ratio > 1).
    """
    content = path.read_text(encoding="utf-8", errors="replace")
    # On ne garde que le premier tier (item [1] = « words ») : la fin est
    # tronquée à « item [2] » (phones).
    words_tier = content.split('name = "phones"')[0]
    if 'name = "words"' not in words_tier:
        words_tier = content  # format inattendu : on garde tout (meilleur que rien)
    return [
        (float(a), float(b), t.strip())
        for a, b, t in _WORD_RE.findall(words_tier)
        if t.strip()
    ]


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        width = wf.getsampwidth()
        ch = wf.getnchannels()
    if width != 2:
        raise SystemExit(f"Largeur PCM non geree ({width * 8} bits) : {path}")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    return audio, sr


def write_wav_mono(path: Path, audio: np.ndarray, sr: int) -> None:
    """Écrit un WAV neuf (le fichier est d'abord détaché : jamais d'écrasement
    accidentel d'un fichier lié en dur vers l'enregistrement d'origine)."""
    if path.exists():
        path.unlink()
    pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def split_words_into_chunks(
    words: list[tuple[float, float, str]], max_seconds: float
) -> list[list[tuple[float, float, str]]]:
    """Découpe la liste de mots en chunks <= max_seconds (frontière de mot)."""
    chunks: list[list[tuple[float, float, str]]] = []
    current: list[tuple[float, float, str]] = []
    for w in words:
        if current and (w[1] - current[0][0]) > max_seconds:
            chunks.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        chunks.append(current)
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description="TextGrid MFA -> manifeste LoRA JSONL")
    ap.add_argument("--speaker", default="laure")
    ap.add_argument("--max-seconds", type=float, default=9.5,
                    help="durée max d'un segment (au-dela : découpe aux mots)")
    ap.add_argument("--min-speech-ratio", type=float, default=0.45,
                    help="part minimale du temps occupée par les mots")
    ap.add_argument("--margin", type=float, default=0.1,
                    help="marge avant/apres la premiere/derniere parole (s)")
    ap.add_argument("--out", type=Path, default=ROOT / "corpus" / "lora_manifest.jsonl")
    ap.add_argument("--audio-out", type=Path, default=ROOT / "corpus" / "lora_segments",
                    help="dossier des WAV recoupés")
    args = ap.parse_args()

    aligned_dir = ALIGNED_ROOT / args.speaker
    source_dir = SOURCE_ROOT / args.speaker
    if not aligned_dir.is_dir():
        print(f"ERREUR : dossier d'alignement absent ({aligned_dir})", file=sys.stderr)
        return 1
    tgs = sorted(aligned_dir.glob("*.TextGrid"))
    if not tgs:
        print(f"ERREUR : aucun TextGrid dans {aligned_dir}", file=sys.stderr)
        return 1

    args.audio_out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    stats = {"segments": 0, "seconds": 0.0, "trimmed": 0, "split": 0}
    excluded: list[tuple[str, str]] = []

    for tg in tgs:
        sid = tg.stem
        wav_path = source_dir / f"{sid}.wav"
        txt_path = source_dir / f"{sid}.txt"
        if not wav_path.is_file():
            excluded.append((sid, "wav source absent"))
            continue
        if not txt_path.is_file():
            excluded.append((sid, "txt absent"))
            continue
        ref_text = " ".join(txt_path.read_text(encoding="utf-8").split())
        if not ref_text:
            excluded.append((sid, "texte vide"))
            continue

        words = parse_textgrid_words(tg)
        if not words:
            excluded.append((sid, "aucun mot aligne"))
            continue

        audio, sr = read_wav_mono(wav_path)
        total_s = len(audio) / sr

        # Bornes de parole (recoupe le silence de tete/queue)
        s0 = max(0.0, words[0][0] - args.margin)
        e1 = min(total_s, words[-1][1] + args.margin)
        if e1 - s0 < 0.3:
            excluded.append((sid, "segment trop court"))
            continue

        # Ratio de parole : temps reellement occupe par les mots
        speech = sum(max(0.0, w[1] - w[0]) for w in words)
        ratio = speech / max(1e-6, e1 - s0)
        if ratio < args.min_speech_ratio:
            excluded.append((sid, f"ratio parole faible ({ratio:.0%})"))
            continue

        # Decoupage en chunks (1 par phrase normale)
        if (e1 - s0) <= args.max_seconds:
            chunks = [words]
        else:
            chunks = split_words_into_chunks(words, args.max_seconds)
            stats["split"] += 1

        ref_words = ref_text.split()
        for i, chunk in enumerate(chunks):
            cs0 = max(s0, chunk[0][0] - (0.0 if i == 0 else 0.0))
            ce1 = min(e1, chunk[-1][1] + (0.0 if i == len(chunks) - 1 else 0.0))
            # Texte : reference originale (casse/ponctuation) ; si decoupe aux
            # mots et meme nombre de jetons, on reprend les mots d'origine.
            if len(chunks) == 1:
                text = ref_text
            elif len(ref_words) == len(words):
                start = words.index(chunk[0])
                text = " ".join(ref_words[start: start + len(chunk)])
            else:
                text = " ".join(w[2] for w in chunk)
            if not text.strip():
                continue

            seg_audio = audio[int(cs0 * sr): int(ce1 * sr)]
            if seg_audio.size < int(0.3 * sr):
                continue

            needs_trim = cs0 > 0.01 or ce1 < total_s - 0.01
            out_wav = args.audio_out / (
                f"{sid}.wav" if len(chunks) == 1 else f"{sid}_c{i + 1}.wav"
            )
            if needs_trim or len(chunks) > 1:
                write_wav_mono(out_wav, seg_audio, sr)  # recoupe reel
                if len(chunks) == 1:
                    stats["trimmed"] += 1
            else:
                # Pas de recoupage : lien dur vers la source (zero copie)
                if out_wav.exists():
                    out_wav.unlink()
                try:
                    out_wav.hardlink_to(wav_path)
                except OSError:
                    shutil.copy2(wav_path, out_wav)

            rel = out_wav.relative_to(args.out.parent)
            lines.append(
                json.dumps(
                    {
                        "audio": str(rel).replace("\\", "/"),
                        "text": text,
                        "id": sid if len(chunks) == 1 else f"{sid}_c{i + 1}",
                        "speech_ratio": round(ratio, 3),
                    },
                    ensure_ascii=False,
                )
            )
            stats["segments"] += 1
            stats["seconds"] += len(seg_audio) / sr

    if not lines:
        print("ERREUR : aucun segment exploitable", file=sys.stderr)
        return 2

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"manifeste : {args.out}")
    print(f"  segments      : {stats['segments']}  ({stats['seconds'] / 60:.1f} min d'audio)")
    print(f"  recoupes      : {stats['trimmed']}  (silences de tete/queue retires)")
    print(f"  phrases coupees: {stats['split']}  (> {args.max_seconds} s, decoupe aux mots)")
    print(f"  exclus        : {len(excluded)}")
    for sid, why in excluded[:20]:
        print(f"    - {sid}: {why}")
    if len(excluded) > 20:
        print(f"    ... et {len(excluded) - 20} autres")
    return 0


if __name__ == "__main__":
    sys.exit(main())
