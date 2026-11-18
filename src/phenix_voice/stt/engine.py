"""Moteur de transcription local Whisper accéléré sur GPU AMD via ONNX Runtime DirectML."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
import json
from pathlib import Path
import time
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from phenix_voice.stt.mel import compute_log_mel_spectrogram


@dataclass
class TranscriptionResult:
    """Résultat enrichi d'une transcription vocale."""

    text: str
    alternatives: list[str] = field(default_factory=list)
    confidence: float = 1.0
    encoder_ms: float = 0.0
    decoder_ms: float = 0.0
    total_ms: float = 0.0
    audio_duration_s: float = 0.0
    bucket_frames: int = 0
    provider: str = "DmlExecutionProvider"


def build_alternatives(
    generated_tokens: list[int],
    runner_up_candidates: list[tuple[int, int, float]],
    decode: Callable[[list[int]], str],
    main_text: str,
    num_alternatives: int,
) -> list[str]:
    """Construit les alternatives de correction à partir des seconds choix du décodage.

    1. Substitutions unitaires, positions les plus ambiguës d'abord ;
    2. si le quota n'est pas atteint, combinaisons de DEUX substitutions —
       c'est ce qui permet de remplir jusqu'à **9 choix** dans la fenêtre
       « Corriger ça » (au lieu des 1 à 3 obtenus avec les substitutions
       seules).

    `decode` est injecté (tokeniseur réel en production) : la logique reste
    testable sans GPU. Dédoublonnage insensible à la casse.
    """
    alternatives: list[str] = []
    seen: set[str] = set()
    main_key = main_text.strip().casefold()

    def _try(seq: list[int]) -> None:
        if len(alternatives) >= num_alternatives:
            return
        text = decode(seq).strip()
        key = text.casefold()
        if text and key != main_key and key not in seen:
            seen.add(key)
            alternatives.append(text)

    ordered = sorted(runner_up_candidates, key=lambda c: c[2], reverse=True)

    # 1) substitutions unitaires
    for pos, tok, _ in ordered:
        if len(alternatives) >= num_alternatives:
            break
        seq = list(generated_tokens)
        seq[pos] = tok
        _try(seq)

    # 2) combinaisons de deux substitutions si le quota n'est pas atteint
    for i in range(len(ordered)):
        if len(alternatives) >= num_alternatives:
            break
        for j in range(i + 1, len(ordered)):
            if len(alternatives) >= num_alternatives:
                break
            pos1, tok1, _ = ordered[i]
            pos2, tok2, _ = ordered[j]
            if pos1 == pos2:
                continue
            seq = list(generated_tokens)
            seq[pos1] = tok1
            seq[pos2] = tok2
            _try(seq)

    return alternatives


def _resolve_local_or_download(repo_id: str, filename: str) -> str:
    """Charge le fichier du modèle 100 % hors-ligne depuis le disque local s'il est déjà présent
    (aucune requête réseau émise, même au démarrage). Ne télécharge qu'à la toute première installation.
    """
    try:
        return hf_hub_download(repo_id, filename, local_files_only=True)
    except Exception:
        return hf_hub_download(repo_id, filename, local_files_only=False)


def build_or_get_dynamic_encoder(
    repo_id: str,
    cache_dir: Path,
    subfolder_file: str = "onnx/encoder_model_fp16.onnx",
) -> Path:
    """Patche une seule fois le graphe ONNX de l'encodeur Whisper pour autoriser des durées
    audio courtes dynamiques (ex: 3s, 5s, 8s au lieu de 30s fixes), divisant la latence GPU par 4 à 10.

    Le patch vit dans ``phenix_voice.stt.onnx_dynamic_encoder`` (partage avec
    ``tools/export_onnx.py``) : il retrouve les cibles par structure plutot que
    par nom de noeud, donc valide aussi bien pour le graphe onnx-community que
    pour un graphe re-exporte apres fusion LoRA.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = repo_id.replace("/", "--") + "__encoder_fp16_dynamic.onnx"
    patched_path = cache_dir / safe_name
    if patched_path.exists() and patched_path.stat().st_size > 1_000_000:
        return patched_path

    raw_enc_path = _resolve_local_or_download(repo_id, subfolder_file)
    from phenix_voice.stt.onnx_dynamic_encoder import build_dynamic_encoder_file

    return build_dynamic_encoder_file(Path(raw_enc_path), patched_path)


class WhisperDirectMLEngine:
    """Moteur Whisper Large-v3-Turbo (ou Small/Medium) accéléré sur GPU AMD via DirectML."""

    # Palier rapide par défaut (1200 trames = 12,0s) : garantit une reconnaissance précise de la diction
    # dysarthrique et des commandes tout en maintenant ~450-700 ms sur l'AMD Radeon RX 5700 XT
    FAST_BUCKET_FRAMES: int = 1200
    BUCKETS_FRAMES: tuple[int, ...] = (1200, 3000)
    DEFAULT_CALIBRATED_PROMPT: str = (
        "Écoute, Au repos, Corriger ça, Annuler sans apprendre, Mode épellation, Fin épellation, "
        "point à la ligne, point d'interrogation, point d'exclamation, virgule, reconnaissance vocale adaptée."
    )

    def __init__(
        self,
        repo_id: str = "onnx-community/whisper-large-v3-turbo",
        language: str = "fr",
        cache_dir: str | Path = "models/cache",
        prefer_dml: bool = True,
        warmup_buckets: tuple[int, ...] = (1200,),
        finetuned_dir: str | Path | None = Path("models/finetuned"),
    ) -> None:
        self.repo_id = repo_id
        self.language = language
        self.cache_dir = Path(cache_dir)
        self.finetuned_dir = Path(finetuned_dir) if finetuned_dir else None

        available_providers = ort.get_available_providers()
        if prefer_dml and "DmlExecutionProvider" in available_providers:
            self.providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            self.active_provider = "DmlExecutionProvider"
            self.use_gpu_iobinding = True
        else:
            self.providers = ["CPUExecutionProvider"]
            self.active_provider = "CPUExecutionProvider"
            self.use_gpu_iobinding = False

        # Configuration du modèle et du tokenizer (100 % hors-ligne si déjà présent sur le SSD)
        cfg_path = _resolve_local_or_download(repo_id, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            self.config = json.load(f)
        self.n_mels: int = int(self.config.get("num_mel_bins", 128))

        tok_path = _resolve_local_or_download(repo_id, "tokenizer.json")
        self.tokenizer = Tokenizer.from_file(tok_path)

        # Tokens spéciaux Whisper
        self.sot_token = self.tokenizer.token_to_id("<|startoftranscript|>")
        self.eot_token = self.tokenizer.token_to_id("<|endoftext|>")
        self.prev_token = self.tokenizer.token_to_id("<|startofprev|>")
        self.lang_token = self.tokenizer.token_to_id(f"<|{language}|>")
        self.transcribe_token = self.tokenizer.token_to_id("<|transcribe|>")
        self.notimestamps_token = self.tokenizer.token_to_id("<|notimestamps|>")

        # Chargement des sessions ONNX (100 % local, zéro requête réseau)
        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        # Modeles finetunes locaux (fusion LoRA -> tools/export_onnx.py) :
        # pris en priorite s'ils sont complets (encodeur + 2 decodeurs).
        enc_path, dec_path, dec_past_path = self._resolve_model_paths()
        if enc_path is not None:
            print(f"[stt] modeles finetunes locaux : {self.finetuned_dir}")
        else:
            enc_path = build_or_get_dynamic_encoder(repo_id, self.cache_dir)
            dec_path = _resolve_local_or_download(repo_id, "onnx/decoder_model_fp16.onnx")
            dec_past_path = _resolve_local_or_download(
                repo_id, "onnx/decoder_with_past_model_fp16.onnx"
            )

        self.enc_session = ort.InferenceSession(
            str(enc_path), so, providers=self.providers
        )
        self.dec_session = ort.InferenceSession(dec_path, so, providers=self.providers)
        self.dec_past_session = ort.InferenceSession(
            dec_past_path, so, providers=self.providers
        )

        self.dec_out_names = [o.name for o in self.dec_session.get_outputs()]
        self.dec_past_out_names = [o.name for o in self.dec_past_session.get_outputs()]

        if warmup_buckets:
            self._warmup(warmup_buckets)

    def _resolve_model_paths(self) -> tuple[Path | None, str | None, str | None]:
        """Cherche les 3 graphes finetunes (fusion LoRA) dans ``finetuned_dir``.

        Retourne ``(None, None, None)`` si le dossier est absent ou incomplet :
        l'appelant bascule alors sur le modele de base onnx-community.
        """
        ft = self.finetuned_dir
        if not ft or not ft.is_dir():
            return None, None, None
        dec = ft / "decoder_model_fp16.onnx"
        dec_past = ft / "decoder_with_past_model_fp16.onnx"
        dyn = ft / "encoder_model_fp16_dynamic.onnx"
        raw = ft / "encoder_model_fp16.onnx"
        if not (dec.is_file() and dec_past.is_file()):
            return None, None, None
        if dyn.is_file():
            enc: Path | None = dyn
        elif raw.is_file():
            patched = self.cache_dir / "finetuned__encoder_fp16_dynamic.onnx"
            if not (patched.exists() and patched.stat().st_size > 1_000_000):
                from phenix_voice.stt.onnx_dynamic_encoder import build_dynamic_encoder_file

                build_dynamic_encoder_file(raw, patched)
            enc = patched
        else:
            enc = None
        if enc is None:
            return None, None, None
        return enc, str(dec), str(dec_past)

    def _warmup(self, buckets: tuple[int, ...]) -> None:
        """Pré-compile les shaders DirectML sur la carte AMD Radeon pour éviter tout pic à la 1re phrase."""
        dummy_ids = self._build_prompt_ids(self.DEFAULT_CALIBRATED_PROMPT)
        next_id = np.array([[self.eot_token]], dtype=np.int64)
        for frames in buckets:
            mel = np.zeros((1, self.n_mels, frames), dtype=np.float32)
            hs = self.enc_session.run(None, {"input_features": mel})[0]
            dec_outs = self.dec_session.run(
                None, {"input_ids": dummy_ids, "encoder_hidden_states": hs}
            )
            past = {
                name.replace("present.", "past_key_values."): val
                for name, val in zip(self.dec_out_names[1:], dec_outs[1:])
            }
            self.dec_past_session.run(None, {"input_ids": next_id, **past})

    def _select_bucket_frames(self, audio_samples: int, sr: int = 16000) -> int:
        """Utilise le palier fixe rapide (600 trames = 6s) pour 98 % des souffles de dictée (<= 5,4s)
        afin que DirectML conserve son plan d'exécution GPU compilé sans aucune recompilation.
        """
        needed_frames = int(np.ceil((audio_samples / sr + 0.6) * 100))
        for bucket in self.BUCKETS_FRAMES:
            if needed_frames <= bucket:
                return bucket
        return 3000

    def _build_prompt_ids(
        self, initial_prompt: str | None = None, language: str | None = None
    ) -> np.ndarray:
        """Construit la séquence d'amorçage du décodeur avec support optionnel du vocabulaire personnel.

        `language` : langue du segment (`"fr"` par défaut, `"en"` pour les segments
        d'épellation — les mots de l'alphabet radio sont anglais et Whisper les
        transforme en mots anglais proches « Make » / « Bank » en décodage français).
        """
        lang_id = self.lang_token
        if language:
            candidate = self.tokenizer.token_to_id(f"<|{language}|>")
            if candidate is not None:
                lang_id = candidate
        prefix: list[int] = []
        if initial_prompt and initial_prompt.strip():
            encoded = self.tokenizer.encode(" " + initial_prompt.strip()).ids
            # Limiter le prompt initial aux 120 derniers tokens
            encoded = encoded[-120:]
            if self.prev_token is not None:
                prefix.append(self.prev_token)
                prefix.extend(encoded)

        prefix.extend(
            [
                self.sot_token,
                lang_id,
                self.transcribe_token,
                self.notimestamps_token,
            ]
        )
        return np.array([prefix], dtype=np.int64)

    def transcribe(
        self,
        audio_pcm: np.ndarray,
        initial_prompt: str | None = None,
        max_new_tokens: int = 96,
        # Quota de la fenêtre « Corriger ça » : grille 3×3 = 9 choix.
        num_alternatives: int = 9,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcrit un segment audio 16 kHz mono float32 et génère également des alternatives proches."""
        t_start = time.perf_counter()
        audio = np.asarray(audio_pcm, dtype=np.float32).reshape(-1)
        audio_duration_s = len(audio) / 16000.0
        peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
        if audio_duration_s < 0.15 or peak < 8e-4:
            return TranscriptionResult(
                text="",
                audio_duration_s=audio_duration_s,
                provider=self.active_provider,
            )

        # Normalisation automatique du gain (AGC) : ramène la voix à 0.85 pleine échelle
        audio = audio * (0.85 / peak)

        if initial_prompt is None:
            initial_prompt = self.DEFAULT_CALIBRATED_PROMPT

        bucket_frames = self._select_bucket_frames(len(audio))
        mel = compute_log_mel_spectrogram(
            audio, n_mels=self.n_mels, target_frames=bucket_frames
        )

        # 1. Passage Encodeur (GPU DirectML)
        t_enc0 = time.perf_counter()
        if self.use_gpu_iobinding:
            io_enc = self.enc_session.io_binding()
            io_enc.bind_cpu_input("input_features", mel)
            io_enc.bind_output("last_hidden_state", "dml", 0)
            self.enc_session.run_with_iobinding(io_enc)
            hs_gpu = io_enc.get_outputs()[0]
        else:
            hs_cpu = self.enc_session.run(None, {"input_features": mel})[0]
        encoder_ms = (time.perf_counter() - t_enc0) * 1000.0

        # 2. Premier pas Décodeur (calcul des clés/valeurs d'attention croisée)
        t_dec0 = time.perf_counter()
        prompt_ids = self._build_prompt_ids(initial_prompt, language=language)

        if self.use_gpu_iobinding:
            io_dec = self.dec_session.io_binding()
            io_dec.bind_cpu_input("input_ids", prompt_ids)
            io_dec.bind_ortvalue_input("encoder_hidden_states", hs_gpu)
            io_dec.bind_output("logits", "cpu")
            for name in self.dec_out_names[1:]:
                io_dec.bind_output(name, "dml", 0)
            self.dec_session.run_with_iobinding(io_dec)
            dec_outs = io_dec.get_outputs()
            logits = dec_outs[0].numpy()[0, -1, :].astype(np.float64)
            past_gpu = dict(zip(self.dec_out_names[1:], dec_outs[1:]))
            enc_kv_gpu = {
                k.replace("present.", "past_key_values."): v
                for k, v in past_gpu.items()
                if ".encoder." in k
            }
            dec_kv_gpu = {
                k.replace("present.", "past_key_values."): v
                for k, v in past_gpu.items()
                if ".decoder." in k
            }
        else:
            dec_outs = self.dec_session.run(
                None, {"input_ids": prompt_ids, "encoder_hidden_states": hs_cpu}
            )
            logits = dec_outs[0][0, -1, :].astype(np.float64)
            past_cpu = dict(zip(self.dec_out_names[1:], dec_outs[1:]))
            enc_kv_cpu = {
                k.replace("present.", "past_key_values."): v
                for k, v in past_cpu.items()
                if ".encoder." in k
            }
            dec_kv_cpu = {
                k.replace("present.", "past_key_values."): v
                for k, v in past_cpu.items()
                if ".decoder." in k
            }

        generated_tokens: list[int] = []
        token_probs: list[float] = []
        # Stocker les meilleurs seconds choix (position, second_token_id, ratio_prob) pour générer les alternatives
        runner_up_candidates: list[tuple[int, int, float]] = []

        for step in range(max_new_tokens):
            # Masquer les tokens spéciaux (> eot_token) sauf eot_token lui-même
            logits[self.eot_token + 1 :] = -1e9
            if step == 0:
                # Éviter de terminer à vide au tout premier token si de la parole est présente
                logits[self.eot_token] -= 2.0

            # Pénalité anti-boucle sur les tokens déjà générés récemment
            if len(generated_tokens) >= 2:
                for prev_tok in set(generated_tokens[-8:]):
                    if logits[prev_tok] > 0:
                        logits[prev_tok] /= 1.2
                    else:
                        logits[prev_tok] *= 1.2

            # Recherche ultra-rapide des 2 meilleurs tokens avant calcul des probabilités
            top2_idx = np.argpartition(logits, -2)[-2:]
            if logits[top2_idx[0]] < logits[top2_idx[1]]:
                top2_idx = top2_idx[::-1]
            best_tok = int(top2_idx[0])
            second_tok = int(top2_idx[1])

            shifted = logits - logits[best_tok]
            denom = float(np.sum(np.exp(shifted)))
            best_prob = 1.0 / denom
            second_prob = float(np.exp(logits[second_tok] - logits[best_tok])) / denom

            if best_tok == self.eot_token:
                break

            # Seconds choix conservés pour les alternatives de correction :
            # seuil abaissé (0.04 -> 0.01) pour proposer davantage de choix
            # dans « Corriger ça » (objectif : 9 alternatives remplies).
            if second_tok < self.eot_token and second_prob > 0.01:
                runner_up_candidates.append(
                    ( len(generated_tokens), second_tok, second_prob / max(best_prob, 1e-6) )
                )

            generated_tokens.append(best_tok)
            token_probs.append(best_prob)

            # Pas suivant avec KV-cache
            next_id_arr = np.array([[best_tok]], dtype=np.int64)
            if self.use_gpu_iobinding:
                io = self.dec_past_session.io_binding()
                io.bind_cpu_input("input_ids", next_id_arr)
                for k, ov in enc_kv_gpu.items():
                    io.bind_ortvalue_input(k, ov)
                for k, ov in dec_kv_gpu.items():
                    io.bind_ortvalue_input(k, ov)
                io.bind_output("logits", "cpu")
                for name in self.dec_past_out_names[1:]:
                    io.bind_output(name, "dml", 0)
                self.dec_past_session.run_with_iobinding(io)
                ort_outs = io.get_outputs()
                logits = ort_outs[0].numpy()[0, -1, :].astype(np.float64)
                for name, ov in zip(self.dec_past_out_names[1:], ort_outs[1:]):
                    dec_kv_gpu[name.replace("present.", "past_key_values.")] = ov
            else:
                feed = {"input_ids": next_id_arr, **enc_kv_cpu, **dec_kv_cpu}
                res = self.dec_past_session.run(None, feed)
                logits = res[0][0, -1, :].astype(np.float64)
                for name, val in zip(self.dec_past_out_names[1:], res[1:]):
                    dec_kv_cpu[name.replace("present.", "past_key_values.")] = val

        decoder_ms = (time.perf_counter() - t_dec0) * 1000.0
        total_ms = (time.perf_counter() - t_start) * 1000.0

        # Si le souffle dépassait 5,4s (palier > 600), ré-amorcer immédiatement le palier rapide 600
        if bucket_frames != self.FAST_BUCKET_FRAMES:
            self._warmup((self.FAST_BUCKET_FRAMES,))

        main_text = self.tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
        mean_conf = float(np.mean(token_probs)) if token_probs else 0.0

        # Construction des alternatives les plus plausibles (fenêtre « Corriger ça »,
        # jusqu'à 9 choix : substitutions unitaires puis combinaisons de deux)
        alternatives = build_alternatives(
            generated_tokens,
            runner_up_candidates,
            lambda seq: self.tokenizer.decode(seq, skip_special_tokens=True),
            main_text,
            num_alternatives,
        )

        return TranscriptionResult(
            text=main_text,
            alternatives=alternatives,
            confidence=mean_conf,
            encoder_ms=encoder_ms,
            decoder_ms=decoder_ms,
            total_ms=total_ms,
            audio_duration_s=audio_duration_s,
            bucket_frames=bucket_frames,
            provider=self.active_provider,
        )
