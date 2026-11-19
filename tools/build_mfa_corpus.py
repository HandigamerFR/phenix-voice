# -*- coding: utf-8 -*-
"""Construit le corpus d'entrée MFA à partir du manifeste du Studio (étape 5).

Étapes de l'étape 5 : enregistrement Studio (fait) -> **ce script** ->
`mfa validate` -> `mfa align` -> manifeste JSONL -> `tools/lora_train.py`.

- lit `user_data/calibration/manifest.json` (+ WAV `_norm.wav`) ;
- exclut par défaut les segments `review=true` (douteux, garde-fou anti-dérive) ;
- écrit `corpus/mfa_in/<locuteur>/<id>.wav` + `<id>.txt` (texte attendu) ;
- le WAV est **lien dur** vers l'original (même volume, zéro copie) sauf
  `--copy` (installation où les liens échouent).

Usage :
    python tools/build_mfa_corpus.py [--speaker camille] [--include-review] [--copy]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "user_data" / "calibration" / "manifest.json"
OUT_ROOT = ROOT / "corpus" / "mfa_in"


def link_or_copy(src: Path, dst: Path, copy: bool) -> str:
    if dst.exists():
        dst.unlink()
    if copy:
        shutil.copy2(src, dst)
        return "copy"
    try:
        dst.hardlink_to(src)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy-fallback"


def main() -> int:
    ap = argparse.ArgumentParser(description="Corpus MFA depuis le manifeste Studio")
    ap.add_argument("--speaker", default="camille", help="nom du locuteur (sous-dossier)")
    ap.add_argument("--include-review", action="store_true",
                    help="inclure les segments marques review=true (douteux)")
    ap.add_argument("--copy", action="store_true",
                    help="copier les WAV au lieu de liens durs")
    args = ap.parse_args()

    if not MANIFEST.is_file():
        print(f"ERREUR : manifeste absent ({MANIFEST})", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    samples = data.get("samples", [])

    out_dir = OUT_ROOT / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)

    kept, skipped_review, missing_wav, bad_text = [], [], [], []
    modes: set[str] = set()

    for e in samples:
        eid = str(e.get("id", ""))
        text = str(e.get("expected_text", "")).strip()
        if e.get("review") and not args.include_review:
            skipped_review.append(eid)
            continue
        if not text:
            bad_text.append(eid)
            continue
        # WAV normalisé (niveau constant) de preference, sinon le brut
        norm = Path(str(e.get("norm_wav", "")))
        raw = Path(str(e.get("raw_wav", "")))
        src = norm if norm.is_file() else (raw if raw.is_file() else None)
        if src is None:
            missing_wav.append(eid)
            continue
        # MFA : un .wav et un .txt de meme nom par segment
        modes.add(link_or_copy(src.resolve(), out_dir / f"{eid}.wav", args.copy))
        (out_dir / f"{eid}.txt").write_text(text + "\n", encoding="utf-8")
        kept.append(eid)

    print(f"segments retenus : {len(kept)}  (dossier {out_dir})")
    print(f"  WAV : {', '.join(sorted(modes)) or 'aucun'}")
    if skipped_review:
        print(f"  exclus review=true ({len(skipped_review)}) : {', '.join(skipped_review)}")
    if missing_wav:
        print(f"  WAV manquants ({len(missing_wav)}) : {', '.join(missing_wav)}")
    if bad_text:
        print(f"  texte vide ({len(bad_text)}) : {', '.join(bad_text)}")

    # Cohérence : chaque .wav doit avoir son .txt et inversement
    wavs = {p.stem for p in out_dir.glob("*.wav")}
    txts = {p.stem for p in out_dir.glob("*.txt")}
    if wavs != txts:
        print(f"  AVERTISSEMENT : desabordement wav/txt : wav-txt={sorted(wavs - txts)[:5]} "
              f"txt-wav={sorted(txts - wavs)[:5]}", file=sys.stderr)
        return 2

    print(f"pret pour `mfa validate corpus/mfa_in french_mfa_ext.dict french_mfa`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
