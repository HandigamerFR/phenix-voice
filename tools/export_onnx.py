# -*- coding: utf-8 -*-
"""Fusionne l'adaptateur LoRA dans Whisper puis re-exporte les 3 graphes ONNX.

Pipeline (execute dans venv-onnx, PAS dans venv-rocm) :
    1. charge la base openai/whisper-large-v3-turbo (cache HF local) ;
    2. fusionne l'adaptateur (merge_and_unload) -> poids reels finetunes ;
    3. exporte ONNX fp16 via optimum : encoder_model.onnx, decoder_model.onnx,
       decoder_with_past.onnx (meme format que le repo onnx-community utilise
       par l'app) ;
    4. rend l'encodeur dynamique (paliers 1200/3000 trames) via le patch
       partage phenix_voice.stt.onnx_dynamic_encoder.

Sortie : models/finetuned/  (l'app la prefere automatiquement si presente)

Usage :
    %TEMP%\\opencode\\venv-onnx\\Scripts\\python.exe tools\\export_onnx.py ^
        --adapter adapters\\lora_full --out models\\finetuned
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

BASE_MODEL = "openai/whisper-large-v3-turbo"


def merge_lora(adapter: Path, out_hf: Path) -> None:
    """Fusionne l'adaptateur LoRA dans la base -> checkpoint HF complet."""
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration

    if out_hf.exists():
        shutil.rmtree(out_hf)
    print(f"chargement de la base {BASE_MODEL} ...", flush=True)
    t0 = time.perf_counter()
    base = WhisperForConditionalGeneration.from_pretrained(
        BASE_MODEL, low_cpu_mem_usage=True
    )
    print(f"  base chargee en {time.perf_counter() - t0:.0f} s", flush=True)
    model = PeftModel.from_pretrained(base, str(adapter))
    model = model.merge_and_unload()
    print(f"fusion LoRA -> poids reels ({out_hf})", flush=True)
    out_hf.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_hf), safe_serialization=True)
    # Config/tokenizer separes : optimum a besoin d'un dossier HF complet.
    for fname in ("config.json", "generation_config.json", "preprocessor_config.json",
                  "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt"):
        try:
            from huggingface_hub import hf_hub_download

            src = hf_hub_download(BASE_MODEL, fname, local_files_only=True)
            shutil.copy(src, out_hf / fname)
        except Exception:
            pass
    del model, base
    print("  sauvegarde terminee", flush=True)


def export_onnx(hf_dir: Path, out_dir: Path, fp16: bool = True) -> None:
    """Exporte encoder/decoder/decoder_with_past via optimum (fp32 d'abord).

    Le fp16 est applique ensuite par ``convert_models_fp16`` : le parametre
    ``dtype`` d'optimum 2.x ne convertit que les entrees dummy et produit un
    graphe mixte (LayerNormalization f32/f16) refuse par ONNX Runtime.
    """
    from optimum.exporters.onnx import main_export

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"export ONNX -> {out_dir} ...", flush=True)
    t0 = time.perf_counter()
    main_export(
        str(hf_dir),
        str(out_dir),
        # "-with-past" est indispensable : sans lui, optimum n'exporte pas
        # decoder_with_past (le decodage avec cache KV de l'app).
        task="automatic-speech-recognition-with-past",
        device="cpu",
        no_post_process=False,
    )
    print(f"  export termine en {time.perf_counter() - t0:.0f} s", flush=True)
    # decoder_model_merged : variante sans/avec past en un seul graphe, jamais
    # utilisee par l'app (qui alterne decoder_model + decoder_with_past).
    merged = out_dir / "decoder_model_merged.onnx"
    for leftover in (merged, out_dir / "decoder_model_merged.onnx_data"):
        if leftover.exists():
            leftover.unlink()
    if fp16:
        convert_models_fp16(out_dir)


def _repair_keep_io_artifacts(model) -> None:
    """Repare les 2 artefacts de ``convert_float_to_float16(keep_io_types=True)``.

    1. Casts ``to=f32`` devenus obsolètes : entree ET sortie en f16 dans les
       value_info (l'attribut ``to`` n'a pas suivi) -> conflit de type ORT.
    2. Consommateurs internes d'une sortie de graphe : le convertisseur insere
       un cast f16->f32 avant la sortie mais laisse les noeuds internes lire
       la tenseur f32 du cast -> MatMul f16/f32. On rebranche ces noeuds sur
       l'entree f16 du cast (la sortie de graphe reste f32 via le cast).

    Puis purge + re-inference des value_info (types recalcules proprement).
    """
    from onnx import TensorProto
    from onnx.shape_inference import infer_shapes

    g = model.graph
    # --- 1. casts obsolètes (entree et sortie deja f16) ---
    types = {
        v.name: v.type.tensor_type.elem_type
        for v in list(g.value_info) + list(g.input) + list(g.output)
    }
    for node in g.node:
        if node.op_type != "Cast":
            continue
        to = next((a.i for a in node.attribute if a.name == "to"), None)
        if to == TensorProto.FLOAT and types.get(node.input[0]) == TensorProto.FLOAT16 and types.get(node.output[0]) == TensorProto.FLOAT16:
            for attr in node.attribute:
                if attr.name == "to":
                    attr.i = TensorProto.FLOAT16

    # --- 2. consommateurs internes des sorties de graphe ---
    outputs = {o.name for o in g.output}
    for cast in [n for n in g.node if n.op_type == "Cast"]:
        to = next((a.i for a in cast.attribute if a.name == "to"), None)
        if to != TensorProto.FLOAT or cast.output[0] not in outputs:
            continue
        f16_tensor, out_name = cast.input[0], cast.output[0]
        for node in g.node:
            if node is cast:
                continue
            for idx, inp in enumerate(node.input):
                if inp == out_name:
                    node.input[idx] = f16_tensor

    # --- 3. value_info recalcules depuis le graphe corrige ---
    del g.value_info[:]
    infer_shapes(model)


def convert_models_fp16(out_dir: Path) -> None:
    """fp32 -> fp16 : poids internes en f16, IO graph en f32 (como la reference).

    L'encodeur fp32 pese ~2,4 Go : ``infer_shapes`` (serialisation protobuf)
    echoue au-dela de 2 Go, et ``convert_float_to_float16_model_path`` ouvre
    un NamedTemporaryFile encore verrouille sous Windows. On fait donc :
    inference de formes SANS les donnees externes (le proto reste leger),
    rechargement des donnees dans le proto, puis conversion avec
    ``disable_shape_infer`` (les value_info sont deja renseignes).
    """
    import onnx
    from onnx.external_data_helper import load_external_data_for_model
    from onnx.shape_inference import infer_shapes
    from onnxconverter_common.float16 import convert_float_to_float16

    for path in sorted(out_dir.glob("*.onnx")):
        print(f"  fp16 : {path.name} ...", flush=True)
        model = onnx.load(str(path), load_external_data=False)
        model = infer_shapes(model)
        load_external_data_for_model(model, str(path.parent))
        for init in model.graph.initializer:
            if init.data_location == onnx.TensorProto.EXTERNAL:
                init.ConvertFromExternalData()
        model16 = convert_float_to_float16(
            model, keep_io_types=True, disable_shape_infer=True
        )
        del model
        _repair_keep_io_artifacts(model16)
        onnx.save(model16, str(path))
        del model16
        data = out_dir / (path.name + "_data")
        if data.exists():
            data.unlink()  # orpheline : le fichier est desormais autonome
    print("  conversion fp16 terminee", flush=True)


def patch_encoder(out_dir: Path) -> None:
    """Rend l'encodeur exporte compatible paliers 1200/3000 trames."""
    import onnx

    from phenix_voice.stt.onnx_dynamic_encoder import make_encoder_dynamic

    # Nom canonique de l'app (meme convention que le repo onnx-community).
    candidates = [
        out_dir / "encoder_model_fp16.onnx",
        out_dir / "encoder_model.onnx",
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        raise SystemExit(f"encodeur absent de {out_dir} : {list(p for p in out_dir.iterdir())}")
    print(f"patch dynamique de {src.name} ...", flush=True)
    model = onnx.load(str(src))
    make_encoder_dynamic(model)
    onnx.checker.check_model(model)
    dst = out_dir / "encoder_model_fp16_dynamic.onnx"
    onnx.save(model, str(dst))
    if dst != src:
        src.unlink()
        data = out_dir / (src.name + "_data")
        if data.exists():
            data.unlink()
    print(f"  -> {dst.name}", flush=True)


def rename_outputs(out_dir: Path) -> None:
    """Renomme les fichiers selon la convention de l'app (suffixe fp16).

    Gere les donnees externes (``*.onnx_data``) : le modele est rechargé et
    resauvegarde en fichier unique pour que la reference interne soit juste.
    """
    import onnx

    mapping = {
        "encoder_model.onnx": "encoder_model_fp16.onnx",
        "decoder_model.onnx": "decoder_model_fp16.onnx",
        "decoder_with_past_model.onnx": "decoder_with_past_model_fp16.onnx",
        "decoder_model_fp16.onnx": "decoder_model_fp16.onnx",
        "decoder_with_past_fp16.onnx": "decoder_with_past_model_fp16.onnx",
    }
    for src_name, dst_name in mapping.items():
        src = out_dir / src_name
        if not src.exists() or src.name == dst_name:
            continue
        data = out_dir / (src_name + "_data")
        if data.exists():
            model = onnx.load(str(src))  # charge les donnees en memoire
            onnx.save(model, str(out_dir / dst_name))
            src.unlink()
            data.unlink()
        else:
            src.rename(out_dir / dst_name)
    print("fichiers : " + ", ".join(sorted(p.name for p in out_dir.glob('*.onnx'))), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, default=Path("adapters/lora_full"))
    parser.add_argument("--out", type=Path, default=Path("models/finetuned"))
    parser.add_argument("--hf-tmp", type=Path, default=Path("models/finetuned_hf"))
    parser.add_argument("--fp32", action="store_true", help="export fp32 (defaut : fp16)")
    parser.add_argument("--skip-merge", action="store_true",
                        help="reutiliser un checkpoint deja fusionne (--hf-tmp)")
    parser.add_argument("--no-patch", action="store_true",
                        help="ne pas appliquer le patch dynamique de l'encodeur (1er export)")
    parser.add_argument("--fp16-only", action="store_true",
                        help="ne faire que la conversion fp16 + rename + patch (export deja fait)")
    args = parser.parse_args()

    if args.fp16_only:
        convert_models_fp16(args.out)
    else:
        if not args.skip_merge:
            if not (args.adapter / "adapter_model.safetensors").is_file():
                raise SystemExit(f"adaptateur introuvable : {args.adapter}")
            merge_lora(args.adapter, args.hf_tmp)
        export_onnx(args.hf_tmp, args.out, fp16=not args.fp32)
    rename_outputs(args.out)
    if args.no_patch:
        print("patch dynamique ignore (--no-patch)", flush=True)
    else:
        patch_encoder(args.out)

    info = {
        "adapter": str(args.adapter),
        "base_model": BASE_MODEL,
        "fp16": not args.fp32,
        "exported": sorted(p.name for p in args.out.glob("*.onnx")),
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (args.out / "finetune_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("RESULTAT: OK - fusion + export ONNX termines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
