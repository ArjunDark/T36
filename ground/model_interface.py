"""
ground/model_interface.py — ground-side verification

The satellite already scored every frame before it was downlinked. This module
re-runs the same ONNX model on the thumbnail that actually arrived, so the ground
can say whether the verdict survived the link.

    predict(image_path) -> dict

`image_path` is a filesystem path to a received JPEG (the server resolves
/received/<name>.jpg for you).

Returns the same shape the dashboard renders, so a mismatch is a straight
field-by-field comparison:

    scene_class, confidence, scientific_utility, priority, alert,
    priority_factors, class_distribution

The model is the same file the satellite flies — tinyml/model_int8.onnx. Both
stations read it from their own copy of the tree, so a disagreement is a genuine
disagreement about the same image, not two different models.

NOTE: this file must not be replaced by a heuristic scorer. An earlier merge
copied the starter repo's placeholder over it, which silently turned the
verification path into a fake. The check below raises rather than pretending.
"""

from __future__ import annotations

import os
import time

import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tinyml", "model_int8.onnx")

CLASS_NAMES = ["AnnualCrop", "Forest", "HerbaceousVegetation", "Highway", "Industrial",
               "Pasture", "PermanentCrop", "Residential", "River", "SeaLake"]

MODEL_INFO = {
    "name": "model_int8.onnx",
    "type": "multi-head ONNX (class + cloud), verification copy",
    "input": "160x160 RGB, 0-1",
    "classes": CLASS_NAMES,
}

_session = None


def _load():
    global _session
    if _session is not None:
        return _session
    import onnxruntime as ort
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            "verification model missing: %s (the ground station needs the tinyml "
            "folder beside it)" % MODEL_PATH)
    _session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    return _session


def predict(image_path=None, features=None, meta=None, frame_id=None):
    """Run the ONNX on a received thumbnail and return the dashboard verdict."""
    t0 = time.time()

    if not image_path or not os.path.exists(image_path):
        raise ValueError("no image for verification: %r" % (image_path,))

    import cv2
    bgr = cv2.imread(image_path)
    if bgr is None:
        raise ValueError("could not decode %s" % image_path)

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    x = cv2.resize(rgb, (160, 160), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]

    sess = _load()
    out = sess.run(None, {sess.get_inputs()[0].name: x})
    named = {o.name: v for o, v in zip(sess.get_outputs(), out)}

    cloud_p = float(1.0 / (1.0 + np.exp(-named["cloud_logit"][0][0])))
    logits = named["class_logits"][0]
    shifted = logits - logits.max()
    probs = np.exp(shifted) / np.exp(shifted).sum()
    idx = int(np.argmax(probs))

    scene = CLASS_NAMES[idx] if idx < len(CLASS_NAMES) else str(idx)
    conf = float(probs[idx]) * 100.0
    if cloud_p > 0.55:
        scene = "Cloudy"

    return {
        "scene_class": scene,
        "confidence": round(conf, 1),
        "scientific_utility": round(conf * (1.0 - cloud_p), 1),
        "priority": round(conf * (1.0 - cloud_p), 1),
        "alert": bool(cloud_p > 0.85),
        "priority_factors": {
            "confidence": round(conf / 100.0, 3),
            "utility": round(1.0 - cloud_p, 3),
        },
        "class_distribution": {CLASS_NAMES[i]: round(float(probs[i]) * 100.0, 1)
                               for i in range(len(CLASS_NAMES))},
        "cloud_prob": round(cloud_p, 3),
        "latency_ms": round((time.time() - t0) * 1000.0, 2),
        "model": MODEL_INFO["name"],
    }
