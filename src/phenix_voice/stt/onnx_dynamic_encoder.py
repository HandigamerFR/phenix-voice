# -*- coding: utf-8 -*-
"""Rend un encodeur Whisper ONNX dynamique (paliers 1200/3000 trames).

Extrait du patch historique de ``engine.py`` (graphe onnx-community) et
généralisé : les cibles sont trouvées par **structure** (consommateur de
``embed_positions.weight``, constantes Reshape contenant 1500) plutôt que par
nom de nœud, afin de fonctionner aussi avec les graphes exportés par
``tools/export_onnx.py`` (optimum 2.x / torch 2.15).

Trois opérations, toutes nécessaires pour accepter T != 3000 trames :
  1. formes statiques (3000/1500) -> symboliques + purge des value_info ;
  2. constantes Reshape [-1, 1500, ...] -> [0, -1, ...] (inférence dynamique) ;
  3. découpe dynamique de embed_positions.weight [1500, 1280] -> [T, 1280]
     juste avant l'Add qui combine positions et hidden states.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

SEQ_IN = "encoder_sequence_length"
SEQ_OUT = "encoder_sequence_length_out"


def _reshape_const_names(model: onnx.ModelProto) -> set[str]:
    """Noms d'initialisers utilisés comme cible d'un Reshape."""
    return {
        inp
        for node in model.graph.node
        if node.op_type == "Reshape"
        for inp in node.input[1:]
        if inp
    }


def _make_dims_dynamic(model: onnx.ModelProto) -> None:
    g = model.graph
    del g.value_info[:]
    # Entree : input_features [B, 128, 3000] -> 3e dim symbolique
    dims_in = g.input[0].type.tensor_type.shape.dim
    if len(dims_in) >= 3:
        dims_in[2].ClearField("dim_value")
        dims_in[2].dim_param = SEQ_IN
    # Sortie : last_hidden_state [B, 1500, 1280] -> 2e dim symbolique
    dims_out = g.output[0].type.tensor_type.shape.dim
    if len(dims_out) >= 2:
        dims_out[1].ClearField("dim_value")
        dims_out[1].dim_param = SEQ_OUT


def _fix_reshape_constants(model: onnx.ModelProto) -> int:
    """[-1, 1500, ...] -> [0, -1, ...] sur les constantes de Reshape."""
    reshape_inputs = _reshape_const_names(model)
    fixes = 0
    for init in model.graph.initializer:
        if init.name not in reshape_inputs:
            continue
        arr = numpy_helper.to_array(init)
        # Constantes Reshape 1D : [ -1, 1500, ... ] -> [ 0, -1, ... ]
        if arr.ndim == 1 and len(arr) >= 2 and arr[0] == -1 and arr[1] == 1500:
            new_arr = arr.copy()
            new_arr[0] = 0
            new_arr[1] = -1
            init.CopyFrom(numpy_helper.from_array(new_arr, init.name))
            fixes += 1
    return fixes


def _find_positions_add(model: onnx.ModelProto):
    """Retourne (noeud Add, index de l'entree positions, nom positions)."""
    g = model.graph
    pos_names = {
        i.name
        for i in g.initializer
        if "embed_positions" in i.name.lower()
    }
    if not pos_names:
        # Repli : initialiser 2D de forme [1500, 1280] (poids de positions)
        for i in g.initializer:
            arr = numpy_helper.to_array(i)
            if arr.ndim == 2 and arr.shape == (1500, 1280):
                pos_names.add(i.name)
                break
    if not pos_names:
        raise RuntimeError("embed_positions introuvable dans le graphe")
    for node in g.node:
        if node.op_type != "Add":
            continue
        for idx, inp in enumerate(node.input):
            if inp in pos_names:
                return node, idx, inp
    raise RuntimeError("Add consommant embed_positions introuvable")


def _slice_positions_dynamically(model: onnx.ModelProto) -> None:
    """Insere Slice(positions, 0, T) avant l'Add (T = longueur reelle)."""
    g = model.graph
    add_node, pos_idx, pos_name = _find_positions_add(model)
    hidden_idx = 1 - pos_idx
    hidden = add_node.input[hidden_idx]

    # Constantes de l'operation
    starts = helper.make_tensor("dyn_pos_starts", TensorProto.INT64, [1], [0])
    axes = helper.make_tensor("dyn_pos_axes", TensorProto.INT64, [1], [0])
    gather_idx = helper.make_tensor("dyn_pos_gather_idx", TensorProto.INT64, [1], [1])
    for tensor in (starts, axes, gather_idx):
        if not any(i.name == tensor.name for i in g.initializer):
            g.initializer.append(tensor)

    shape_node = helper.make_node(
        "Shape", inputs=[hidden], outputs=["dyn_pos_hidden_shape"], name="dyn_pos_shape"
    )
    gather_node = helper.make_node(
        "Gather",
        inputs=["dyn_pos_hidden_shape", "dyn_pos_gather_idx"],
        outputs=["dyn_pos_seq_len"],
        name="dyn_pos_gather",
        axis=0,
    )
    slice_node = helper.make_node(
        "Slice",
        inputs=[pos_name, "dyn_pos_starts", "dyn_pos_seq_len", "dyn_pos_axes"],
        outputs=["dyn_pos_sliced"],
        name="dyn_pos_slice",
    )

    # L'Add doit consommer "dyn_pos_sliced" a la place du poids brut
    add_node.input[pos_idx] = "dyn_pos_sliced"
    pos = next(i for i in g.node if i.name == add_node.name)
    insert_at = list(g.node).index(pos)
    for offset, node in enumerate((shape_node, gather_node, slice_node)):
        g.node.insert(insert_at + offset, node)


def make_encoder_dynamic(model: onnx.ModelProto) -> onnx.ModelProto:
    """Patche le modele en place : formes dynamiques + positions decoupees."""
    _make_dims_dynamic(model)
    _fix_reshape_constants(model)
    _slice_positions_dynamically(model)
    return model


def build_dynamic_encoder_file(src: Path, dst: Path) -> Path:
    """Charge ``src``, applique le patch, sauvegarde dans ``dst``."""
    model = onnx.load(str(src))
    make_encoder_dynamic(model)
    onnx.checker.check_model(model)
    dst.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(dst))
    return dst
