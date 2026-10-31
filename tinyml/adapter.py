"""
tinyml/adapter.py — the model adapter

Implements BaseCubeSatModelAdapter from wrapper_1.py with real inference.

The model
---------
model_int8.onnx, 1.34 MB, quantised with onnxruntime.quant. A MobileNet-style
backbone with four heads:

    input   x                [batch, 3, 160, 160]  float32, 0-1
    output  cloud_logit      [batch, 1]    binary cloud / not-cloud
    output  cloud_frac_logit [batch, 1]    cloud fraction, sigmoid to 0-1
    output  class_logits     [batch, 10]   EuroSAT land-use classes
    output  embedding        [batch, 576]  feature vector, for stitching later

Measured on the bundled EuroSAT subset (10 patches per class, 100 total):
62% top-1 accuracy, against 10% for random guessing. Per class: Residential
10/10, AnnualCrop 8/10, Forest 8/10, Industrial 8/10, SeaLake 8/10, Highway
7/10, PermanentCrop 5/10, River 4/10, HerbaceousVegetation 3/10, Pasture 1/10.

Cloud heads track reality: a 30%-cloud cyclone scene reads p_cloud 0.31 and
fraction 0.20 against a measured 0.30, while clear dunes and clear cropland both
read 0.00. Bright snow is the known weak case — p_cloud 0.00 but fraction 0.24,
so the regression head mistakes bright ground for cloud. Trust p_cloud over
cloud_frac on snow and ice.
"""

from __future__ import annotations

import json
import os

import numpy as np

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None

CLASSES = [
    "AnnualCrop", "Forest", "HerbaceousVegetation", "Highway", "Industrial",
    "Pasture", "PermanentCrop", "Residential", "River", "SeaLake",
]


class BaseCubeSatModelAdapter:
    """Abstract interface. Any TinyML model must inherit from this."""

    def load_model(self):
        raise NotImplementedError

    def predict(self, int8_tensor):
        raise NotImplementedError


class OnnxSegmentationAdapter(BaseCubeSatModelAdapter):
    """Real inference over model_int8.onnx — four heads, no simulated values."""

    id = "model_int8.onnx"
    version = "2.0.0"
    kind = "multi-head"
    mode = "onnx"

    def __init__(self, weights_path: str, classes=None):
        self.weights_path = weights_path
        self.classes = classes or CLASSES
        self.session = None
        self.input_name = None
        self.input_shape = None
        self.weight_bytes = 0
        self.load_model()

    def load_model(self):
        if ort is None:
            raise RuntimeError("onnxruntime is not installed — pip install onnxruntime")
        if not os.path.exists(self.weights_path):
            raise FileNotFoundError(self.weights_path)
        self.weight_bytes = os.path.getsize(self.weights_path)
        self.session = ort.InferenceSession(self.weights_path, providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.input_shape = inp.shape
        return self

    @property
    def input_size(self) -> int:
        shape = self.input_shape
        return shape[2] if isinstance(shape[2], int) else 160

    def predict(self, int8_tensor: np.ndarray) -> dict:
        """
        int8_tensor: (H, W, 3) int8, the SRAM scratchpad contents.

        Returns the decoded heads plus the bytes this call actually allocates.
        """
        from satellite.pipeline.preprocess import dequantise

        rgb = dequantise(int8_tensor).astype(np.float32) / 255.0
        x = np.transpose(rgb, (2, 0, 1))[None]

        out = self.session.run(None, {self.input_name: x})
        named = {o.name: v for o, v in zip(self.session.get_outputs(), out)}

        cloud_p = float(1.0 / (1.0 + np.exp(-named["cloud_logit"][0][0])))
        frac = float(1.0 / (1.0 + np.exp(-named["cloud_frac_logit"][0][0])))

        logits = named["class_logits"][0]
        shifted = logits - logits.max()
        probs = np.exp(shifted) / np.exp(shifted).sum()
        idx = int(np.argmax(probs))

        return {
            "label": self.classes[idx] if idx < len(self.classes) else str(idx),
            "confidence": float(probs[idx]),
            "class_probs": probs.tolist(),
            "cloud_prob": cloud_p,
            "cloud_frac": frac,
            # raw values, for the temperature-scaled triage policy
            "cloud_logit": float(named["cloud_logit"][0][0]),
            "cloud_frac_logit": float(named["cloud_frac_logit"][0][0]),
            "class_logits": logits.astype(float).tolist(),
            "embedding": named["embedding"][0].astype(float).tolist(),
            "embedding_dim": int(named["embedding"].shape[-1]),
            "activation_bytes": int(x.nbytes + sum(v.nbytes for v in out)),
            "weight_bytes": self.weight_bytes,
            "input_size": self.input_size,
        }


def load_card(directory: str) -> dict:
    path = os.path.join(directory, "model_card.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
