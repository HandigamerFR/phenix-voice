# -*- coding: utf-8 -*-
"""Banc d'essai LoRA sur ROCm / RX 5700 XT — validation de bout en bout de l'étape 5.

Objectif (décision 13/11, test ROCm validé 15/11) : prouver qu'un vrai pas
d'entraînement LoRA de Whisper Large-v3-Turbo (809 M, gel du modèle de base,
adaptateurs q_proj/v_proj) s'exécute sur le GPU local via HIP/ROCm.

Données SYNTHÉTIQUES (features mel et labels aléatoires) : on mesure le
chemin d'entraînement (forward + backward + AdamW), pas la qualité.

Réglages de référence mesurés 16/11 (RX 5700 XT, 8,6 Go) :
    ...\\python.exe tools\\lora_bench.py --steps 4 --bf16-weights --frames 500 --batch 8
    -> 2,21 s/step, 6,31 Go, ~13 000 segments/heure (utterance 5 s type)

Autres mesures : 30 s padde batch 1 = 6,46 s/step (558 seg/h) ; batch 16 =
moins efficace (7 299 seg/h) ; 10 s batch 4 = 5 747 seg/h. Le patch
variable-length (--frames < 3000) est ce qui change tout : les utterances
réelles font 3-10 s, pas la fenêtre 30 s.

Usage :
    %TEMP%\\opencode\\venv-rocm\\Scripts\\python.exe tools\\lora_bench.py [--steps N]
        [--bf16-weights] [--frames PAIR] [--batch N] [--no-checkpointing]
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
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="segments synthétiques par pas (batch plus large = plus de segments/heure si la VRAM suit)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=3000,
        help="trames mel par segment (3000 = fenêtre 30s imposée par HF ; <3000 = patch variable-length)",
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

    if args.frames != 3000:
        # Whisper impose 3000 trames (check strict) et calcule les positions
        # pour 1500 jetons : pour un segment plus court on assouplit les 2
        # points (conv1 s=1, conv2 s=2 -> jetons = trames/2 ; trames paires).
        # Utile car les utterances reelles font 3-10 s, pas la fenetre 30 s.
        if args.frames % 2:
            raise SystemExit("--frames doit etre pair (conv2 stride 2)")
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
        print(f"  patch variable-length actif : {args.frames} trames ({args.frames // 100:g} s) au lieu de 3000")

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

    # Batch synthetique : mel (large-v3/turbo = 128 bandes, pas 80).
    # 3000 trames = fenêtre 30s imposée par HF par defaut ; --frames < 3000
    # utilise le patch variable-length (utterances reelles 3-10 s).
    n_mel = int(getattr(model.config, "num_mel_bins", 80))
    input_features = torch.randn(args.batch, n_mel, args.frames, device="cuda")
    labels = torch.randint(0, model.config.vocab_size, (args.batch, 44), device="cuda")

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
    print(f"temps/step moyen         : {avg:.2f} s (x{args.steps}, batch {args.batch} x {args.frames // 100:g} s)")
    print(f"pic mémoire (allocateur) : {peak:.2f} Go reserve {reserved:.2f} Go")
    print(f"mémoire pilote           : {total_b / 1e9:.1f} Go total, {(total_b - free_b) / 1e9:.1f} Go occupés, {free_b / 1e9:.1f} Go libres")
    print(f"debit                    : ~{args.batch * 3600 / avg:.0f} segments/heure ({args.batch} x 3600/{avg:.2f})")
    print("RESULTAT: OK - pas LoRA reel execute sur GPU ROCm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
