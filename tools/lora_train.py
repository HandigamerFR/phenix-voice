# -*- coding: utf-8 -*-
"""Entraînement LoRA RÉEL de Whisper Large-v3-Turbo — étape 5 (JOURNAL session 13).

Réutilise le chemin validé par ``tools/lora_bench.py`` :
  - shim PEFT 0.21 <-> transformers 5.23 (à retirer dès que l'amont corrige) ;
  - patch variable-length (trames < 3000, positions < 1500 jetons) ;
  - config mesurée : poids gelés en bf16, adaptateurs q/v r=16 en fp32.

Entrée : manifeste JSONL, une ligne par segment :
    {"audio": "chemin/vers/segment.wav", "texte": "transcription"}   (cle "text")

Sortie (--out) : adaptateur LoRA (peft) + training_log.jsonl + run_config.json.

Usage (venv-rocm / ROCm) :
    %TEMP%\\opencode\\venv-rocm\\Scripts\\python.exe tools\\lora_train.py ^
        --manifest corpus\\train_manifest.jsonl --out adapters\\run1 --passages 3

Options utiles : --steps N (limite de pas, smoke test), --limit N (segments),
--batch, --max-frames (plafond de trames, 1000 = 10 s), --fp32-weights.

Surveillance thermique (tools/thermal_guard.py) : si le GPU depasse
--max-temp (defaut 80 C), les pas s'arretent (tout reste en RAM) jusqu'au
retour sous --resume-temp (defaut 70 C). Meme regime pour le CPU
(--max-cpu-temp / --resume-cpu-temp, defaut 90/80) si un capteur existe.
Un capteur absent est ignore silencieusement. --no-thermal pour desactiver.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

MODEL_ID = "openai/whisper-large-v3-turbo"
TARGET_SR = 16000
FRAMES_PER_SECOND = 100  # Whisper : 100 trames mel/s (3000 trames = 30 s)


def load_manifest(path: Path) -> list[tuple[Path, str]]:
    """Lit le manifeste JSONL -> [(wav, texte), ...] (chemins relatifs = au manifeste)."""
    base = path.parent
    items: list[tuple[Path, str]] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{lineno}: JSON invalide ({e})")
            if "audio" not in obj:
                raise SystemExit(f"{path}:{lineno}: cle 'audio' absente")
            wav = Path(obj["audio"])
            if not wav.is_absolute():
                wav = base / wav
            text = str(obj.get("text", "")).strip()
            if not wav.is_file():
                raise SystemExit(f"{path}:{lineno}: fichier audio introuvable : {wav}")
            if not text:
                continue
            items.append((wav, text))
    if not items:
        raise SystemExit(f"Manifeste vide ou sans texte exploitable : {path}")
    return items


class SpeechDataset(Dataset):
    """Segments (wav + texte) -> features mel variable-length + labels tokenisés."""

    def __init__(self, items: list[tuple[Path, str]], processor, max_frames: int):
        import soundfile as sf
        import soxr

        self._sf = sf
        self._soxr = soxr
        self.items = items
        self.fe = processor.feature_extractor
        self.tok = processor.tokenizer
        self.max_frames = max_frames

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> dict[str, torch.Tensor]:
        wav, text = self.items[i]
        audio, sr = self._sf.read(str(wav), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if audio.size == 0:
            raise SystemExit(f"Audio vide : {wav}")
        if sr != TARGET_SR:
            audio = self._soxr.resample(audio, sr, TARGET_SR)
        # Troncature de sécurité : max_frames trames = max_frames / 100 s
        max_samples = self.max_frames * (TARGET_SR // FRAMES_PER_SECOND)
        if audio.shape[0] > max_samples:
            audio = audio[:max_samples]
        feats = self.fe(
            audio, sampling_rate=TARGET_SR, padding=False, return_tensors="pt"
        ).input_features[0]
        # Trames paires exigées (conv2 stride 2 du encoder)
        if feats.shape[-1] % 2:
            feats = F.pad(feats, (0, 1))
        labels = torch.tensor(
            self.tok(text, truncation=True).input_ids, dtype=torch.long
        )
        return {"input_features": feats, "labels": labels}


def collate(batch: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    """Pad chaque batch au maximum du batch (pas à 3000 : le patch variable-length suit)."""
    n_mel = batch[0]["input_features"].shape[0]
    n_feat = max(b["input_features"].shape[-1] for b in batch)
    if n_feat % 2:
        n_feat += 1
    n_lab = max(b["labels"].shape[0] for b in batch)
    feats = torch.zeros(len(batch), n_mel, n_feat)
    labels = torch.full((len(batch), n_lab), -100, dtype=torch.long)
    for i, b in enumerate(batch):
        t = b["input_features"].shape[-1]
        feats[i, :, :t] = b["input_features"]
        labels[i, : b["labels"].shape[0]] = b["labels"]
    return {"input_features": feats, "labels": labels}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="manifeste JSONL (audio + text)")
    parser.add_argument("--out", type=Path, default=Path("adapters/lora_run"), help="dossier de sortie (adaptateur + logs)")
    parser.add_argument("--passages", type=int, default=3)
    parser.add_argument("--batch", type=int, default=8, help="segments par pas (config mesuree : 8)")
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--max-frames", type=int, default=1000, help="plafond trames mel (1000 = 10 s ; paires)")
    parser.add_argument("--steps", type=int, default=0, help="arreter apres N pas d'optimisation (0 = illimite)")
    parser.add_argument("--limit", type=int, default=0, help="n'utiliser que les N premiers segments (0 = tout)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-every", type=int, default=10, help="imprimer la perte tous les N pas")
    parser.add_argument("--fp32-weights", action="store_true", help="poids gelés en fp32 (defaut : bf16, config mesuree)")
    parser.add_argument("--no-checkpointing", action="store_true", help="desactiver le checkpointing d'activations")
    parser.add_argument("--max-temp", type=float, default=80.0, help="pause thermique GPU au-dela (C)")
    parser.add_argument("--resume-temp", type=float, default=70.0, help="reprise thermique GPU en dessous (C)")
    parser.add_argument("--max-cpu-temp", type=float, default=90.0, help="pause thermique CPU au-dela (C)")
    parser.add_argument("--resume-cpu-temp", type=float, default=80.0, help="reprise thermique CPU en dessous (C)")
    parser.add_argument("--thermal-every", type=float, default=15.0, help="intervalle de verif thermique (s)")
    parser.add_argument("--no-thermal", action="store_true", help="desactiver la surveillance thermique")
    args = parser.parse_args()

    if args.max_frames % 2:
        raise SystemExit("--max-frames doit etre pair (conv2 stride 2)")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    print(f"torch {torch.__version__} | HIP {torch.version.hip} | cuda={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("RESULTAT: ECHEC - pas de GPU ROCm")
        return 1
    print(f"GPU: {torch.cuda.get_device_name(0)} | bf16={torch.cuda.is_bf16_supported()}")

    from peft import LoraConfig, get_peft_model
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    items = load_manifest(args.manifest)
    if args.limit:
        items = items[: args.limit]
    print(f"manifeste : {len(items)} segments depuis {args.manifest}")

    print(f"chargement {MODEL_ID} ...")
    t0 = time.perf_counter()
    processor = WhisperProcessor.from_pretrained(MODEL_ID)
    model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID)
    print(f"  charge en {time.perf_counter() - t0:.0f} s | params totaux {sum(p.numel() for p in model.parameters()):,}")

    cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="SEQ_2_SEQ_LM",
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    trainable = [p for p in model.parameters() if p.requires_grad]
    n_train = sum(p.numel() for p in trainable)

    # --- Shim de compatibilite PEFT 0.21 <-> transformers 5.23 ---------------
    # (identique au banc ; voir l'explication detaillee dans tools/lora_bench.py)
    _whisper = model.get_base_model()
    _orig_forward = _whisper.forward

    def _compat_forward(*args, **kwargs):
        for key in ("input_ids", "inputs_embeds"):
            if kwargs.get(key) is None:
                kwargs.pop(key, None)
        return _orig_forward(*args, **kwargs)

    _whisper.forward = _compat_forward

    # --- Patch variable-length (les segments reels font 3-10 s, pas 30 s) ----
    # Whisper impose 3000 trames et 1500 positions : on ajuste les deux a la
    # taille reelle de chaque batch (trames paires garanties par le dataset).
    _enc = model.get_base_model().model.encoder
    _orig_enc_forward = _enc.forward

    def _enc_forward(input_features, attention_mask=None, **kwargs):
        n = input_features.shape[-1]
        saved = (_enc.config.max_source_positions, _enc.embed_positions.num_embeddings)
        _enc.config.max_source_positions = n // 2
        _enc.embed_positions.num_embeddings = n // 2
        try:
            return _orig_enc_forward(input_features, attention_mask=attention_mask, **kwargs)
        finally:
            _enc.config.max_source_positions, _enc.embed_positions.num_embeddings = saved

    _enc.forward = _enc_forward

    if not args.fp32_weights:
        # Poids gelés en bf16 (les adaptateurs LoRA restent fp32 pour AdamW).
        for name, p in model.named_parameters():
            if not p.requires_grad:
                p.data = p.data.to(torch.bfloat16)
        print("  poids gelés convertis en bf16")

    model = model.to("cuda")
    if not args.no_checkpointing:
        # Transformers 5.2x renomme l'API checkpoint (disparition v6) — on gère les deux.
        if hasattr(model, "activation_checkpointing_enable"):
            model.activation_checkpointing_enable()
        else:
            model.gradient_checkpointing_enable()
    model.config.use_cache = False
    model.train()
    optimizer = torch.optim.AdamW(trainable, lr=args.lr)

    dataset = SpeechDataset(items, processor, args.max_frames)
    loader = DataLoader(
        dataset,
        batch_size=args.batch,
        shuffle=True,
        collate_fn=collate,
        num_workers=0,
        generator=torch.Generator().manual_seed(args.seed),
    )

    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / "training_log.jsonl"
    log_f = log_path.open("w", encoding="utf-8")

    # --- Surveillance thermique (pause en cours de route, tout reste en RAM) --
    guard = None
    if not args.no_thermal:
        from thermal_guard import ThermalGuard

        guard = ThermalGuard(
            max_gpu=args.max_temp,
            resume_gpu=args.resume_temp,
            max_cpu=args.max_cpu_temp,
            resume_cpu=args.resume_cpu_temp,
            interval=args.thermal_every,
        )
        snap = guard.snapshot()
        if snap:
            print(f"  thermique initiale : {snap}")

    step = 0
    loss_vals: list[float] = []
    t_start = time.perf_counter()
    pauses_total = 0.0
    done = False
    for passage in range(1, args.passages + 1):
        for batch in loader:
            # Verif thermique : au-dela du seuil, on gele les pas (RAM intacte)
            # et on attend le refroidissement avant de continuer.
            if guard is not None:
                motif = guard.check()
                if motif:
                    duree = guard.wait_cool()
                    pauses_total += duree
                    log_f.write(
                        json.dumps(
                            {"step": step, "passage": passage,
                             "event": "thermal_pause", "motif": motif,
                             "duree_sec": round(duree, 1),
                             "mesures": guard.snapshot()}
                        )
                        + "\n"
                    )
                    log_f.flush()
            step += 1
            t0 = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(
                    input_features=batch["input_features"].to("cuda"),
                    labels=batch["labels"].to("cuda"),
                )
                loss = out.loss
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            torch.cuda.synchronize()
            dt = time.perf_counter() - t0
            loss_vals.append(float(loss.detach()))
            log_f.write(
                json.dumps(
                    {"step": step, "passage": passage, "loss": round(float(loss.detach()), 5),
                     "grad_norm": round(float(grad_norm), 4), "sec": round(dt, 3)}
                )
                + "\n"
            )
            log_f.flush()
            if step % args.log_every == 0 or step == 1:
                print(f"  passage {passage} step {step}: perte {loss_vals[-1]:.4f} | norme grad {grad_norm:.3f} | {dt:.2f} s")
            if args.steps and step >= args.steps:
                done = True
                break
        if done:
            break
        print(f"  passage {passage}/{args.passages} termine")
    log_f.close()

    elapsed = time.perf_counter() - t_start
    actif = elapsed - pauses_total
    if not loss_vals:
        raise SystemExit("Aucun pas effectue (manifeste trop petit ?)")

    # Sauvegarde de l'adaptateur (peft) + metadonnees de la course
    model.save_pretrained(str(args.out))
    config = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    config.update(
        model_id=MODEL_ID,
        segments=len(items),
        steps=step,
        loss_first=round(loss_vals[0], 5),
        loss_last=round(loss_vals[-1], 5),
        elapsed_sec=round(elapsed, 1),
        active_sec=round(actif, 1),
        thermal_pauses=guard.pauses if guard else 0,
        thermal_pause_sec=round(pauses_total, 1),
        finished=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    (args.out / "run_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    avg = actif / step
    print()
    print(f"adaptateurs entraînables : {n_train:,} params ({n_train / sum(p.numel() for p in model.parameters()):.2%})")
    print(f"pas effectues            : {step} ({args.passages} passages max, batch {args.batch})")
    print(f"perte                    : {loss_vals[0]:.4f} -> {loss_vals[-1]:.4f}")
    print(f"temps total / pas moyen  : {elapsed:.0f} s / {avg:.2f} s (hors pauses)")
    print(f"debit                    : ~{step * args.batch * 3600 / actif:.0f} segments/heure")
    if guard and guard.pauses:
        print(f"pauses thermiques        : {guard.pauses} ({pauses_total:.0f} s au total)")
    print(f"adaptateur sauvegarde    : {args.out}")
    print("RESULTAT: OK - entraînement LoRA reel termine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
