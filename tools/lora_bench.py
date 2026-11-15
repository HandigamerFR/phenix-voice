# -*- coding: utf-8 -*-
"""Banc d'essai LoRA sur ROCm / RX 5700 XT — validation de bout en bout de l'étape 5.

Objectif (décision 13/11, test ROCm validé 15/11) : prouver qu'un vrai pas
d'entraînement LoRA de Whisper Large-v3-Turbo (809 M, gel du modèle de base,
adaptateurs q_proj/v_proj) s'exécute sur le GPU local via HIP/ROCm.

Données SYNTHÉTIQUES (features mel et labels aléatoires) : on mesure le
chemin d'entraînement (forward + backward + AdamW), pas la qualité.

Usage :
    %TEMP%\\opencode\\venv-rocm\\Scripts\\python.exe tools\\lora_bench.py
"""

from __future__ import annotations

import argparse
import time

import torch
import torch.nn.functional as F  # noqa: F401  (garde l'import utile aux diagnostics)


MODEL_ID = "openai/whisper-large-v3-turbo"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=5, help="pas d'entraînement chronométrés")
    parser.add_argument(
        "--no-checkpointing",
        action="store_true",
        help="désactive le checkpointing d'activations (diagnostic bug transformers+peft)",
    )
    parser.add_argument(
        "--bf16-weights",
        action="store_true",
        help="poids de base en bf16 (divise par 2 la mémoire — test anti-débordement WDDM)",
    )
    args = parser.parse_args()

    print(f"torch {torch.__version__} | HIP {torch.version.hip} | cuda={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("RESULTAT: ECHEC - pas de GPU ROCm")
        return 1
    print(f"GPU: {torch.cuda.get_device_name(0)} | VRAM {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} Go | bf16={torch.cuda.is_bf16_supported()}")

    from peft import LoraConfig, get_peft_model
    from transformers import WhisperForConditionalGeneration

    print(f"chargement {MODEL_ID} (telechargement ~1,6 Go la 1re fois) ...")
    t0 = time.perf_counter()
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

    # --- Shim de compatibilite PEFT 0.21 <-> transformers 5.23 ---------------
    # PeftModelForSeq2SeqLM.forward transmet toujours input_ids/inputs_embeds
    # (None) alors que WhisperForConditionalGeneration.forward est en
    # input_features : les deux valeurs passent par **kwargs jusqu'a l'appel du
    # decodeur (modeling_whisper.py l.962) qui recoit deja input_ids= en
    # nomme -> "got multiple values for keyword argument 'input_ids'".
    # A supprimer des que PEFT/transformers corrigent l'amont.
    _whisper = model.get_base_model()
    _orig_forward = _whisper.forward

    def _compat_forward(*args, **kwargs):
        for key in ("input_ids", "inputs_embeds"):
            if kwargs.get(key) is None:
                kwargs.pop(key, None)
        return _orig_forward(*args, **kwargs)

    _whisper.forward = _compat_forward
    n_train = sum(p.numel() for p in trainable)

    if args.bf16_weights:
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
    optimizer = torch.optim.AdamW(trainable, lr=1e-4)

    # Batch synthetique : mel (large-v3/turbo = 128 bandes, pas 80) 3000 trames
    # = 30 s. Whisper impose 3000 trames fixes (toute utterance reelle est
    # paddée a 3000) : le coup par pas est constant quelle que soit la duree.
    n_mel = int(getattr(model.config, "num_mel_bins", 80))
    input_features = torch.randn(1, n_mel, 3000, device="cuda")
    labels = torch.randint(0, model.config.vocab_size, (1, 44), device="cuda")

    def one_step() -> float:
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = model(input_features=input_features, labels=labels)
            loss = out.loss
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        optimizer.step()
        return float(loss), float(grad_norm)

    # 1 pas de chauffe (allocations + compilations) puis chronometre.
    loss, grad_norm = one_step()
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    times: list[float] = []
    for i in range(args.steps):
        t0 = time.perf_counter()
        loss, grad_norm = one_step()
        torch.cuda.synchronize()
        times.append(time.perf_counter() - t0)
        print(f"  step {i + 1}/{args.steps}: perte {loss:.4f} | norme grad {grad_norm:.3f} | {times[-1]:.2f} s")

    avg = sum(times) / len(times)
    peak = torch.cuda.max_memory_allocated() / 1e9
    reserved = torch.cuda.max_memory_reserved() / 1e9
    free_b, total_b = torch.cuda.mem_get_info()
    print()
    print(f"adaptateurs entraînables : {n_train:,} params ({n_train / sum(p.numel() for p in model.parameters()):.2%} du modèle, gelé sinon)")
    print(f"temps/step moyen         : {avg:.2f} s (x{args.steps}, segment 30 s padde, batch 1)")
    print(f"pic mémoire (allocateur) : {peak:.2f} Go reserve {reserved:.2f} Go")
    print(f"mémoire pilote           : {total_b / 1e9:.1f} Go total, {(total_b - free_b) / 1e9:.1f} Go occupés, {free_b / 1e9:.1f} Go libres")
    print(f"projection corpus        : ~{3600 / avg:.0f} pas/heure")
    print("RESULTAT: OK - pas LoRA reel execute sur GPU ROCm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
