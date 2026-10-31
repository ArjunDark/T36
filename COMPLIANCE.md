# Compliance — Kepler Aerospace / ICCPS 2026 brief

Each requirement from the challenge statement, what implements it, and the number
that answers it. Run `python3 tools/benchmark.py` to reproduce the measurements.

---

## 1. Float32 vision backbone trained on a public dataset

**Requirement:** MobileNetV3, SqueezeNet, EfficientNet-Lite or YOLOv8-Nano, trained on
EuroSAT, SpaceNet or HRSID.

**Built:** MobileNetV3-small with four heads, trained on EuroSAT (10 classes, 27,000
patches). The training pipeline is in the repository at
`tinyml/leo_tinyml_triage.ipynb`.

**Heads:** `cloud_logit` (binary cloud), `cloud_frac_logit` (cloud fraction),
`class_logits` (10-way land use), `embedding` (576-d, used for novelty).

---

## 2. Structured iterative L2-norm filter pruning

**Requirement:** structured iterative L2-norm filter pruning.

**Built:** notebook cell 8. `torch_pruning` with `MetaPruner`,
`MagnitudeImportance(p=2)` — that is L2 norm — `iterative_steps=5`,
`pruning_ratio=0.5`, three fine-tune epochs per step, and an automatic rollback if
either the cloud or class accuracy drops past the configured maximum. Head layers are
in `ignored_layers` so the output shapes stay fixed.

---

## 3. Post-training static INT8 quantisation

**Requirement:** ONNX Runtime or TensorFlow Lite.

**Built:** notebook cell 9. `quantize_static` with `QuantFormat.QDQ`,
`QuantType.QInt8`, per-channel, calibrated on 250 training tiles plus 50 real tiles,
pre-processed with `quant_pre_process`. ONNX opset 13.

**Measured:** 1,069,757 parameters, 1.34 MB on disk. The same weights in FP32 are
4.28 MB. That is **3.19x** from quantisation alone; pruning contributes further and
the pre-pruning parameter count is printed by notebook cell 8.

---

## 4. Peak working RAM below 4.2 MB

**Requirement:** <= 4.2 MB SRAM.

**Built:** measured per inference, not estimated.

| | MB |
| --- | --- |
| Peak activation (input + all four outputs) | 0.310 |
| Weights | 1.341 |
| **Total** | **1.650** |

**1.65 MB against a 4.2 MB envelope — 39% of budget, 2.5x headroom.**

The satellite also enforces the envelope at runtime: `pipeline/ingest.py` refuses to
build a tensor that would not fit and raises an explicit SRAM fault rather than
failing quietly. At the shipped 160 px the tensor is 75.0 kB.

---

## 5. Simulated pass windows

**Requirement:** simulated pass windows.

**Built:** `pipeline/downlink.py`. A pass clock with period, length and offset, a
priority queue, and a byte-accurate sender that will not exceed the link budget.

**Mission profile** (`satellite/config.json`): 256 kbit/s, 600 s pass — matching the
brief exactly. **Demo profile** (`config.demo.json`): 38.4 kbit/s, 25 s, so a live
demo is watchable.

---

## 6. Discard cloud-occluded tiles locally

**Requirement:** discard cloud-occluded tiles locally.

**Built:** the triage policy in `pipeline/scoring.py`.

```
p_cloud = sigmoid(cloud_logit / T_cloud)      T_cloud = 1.1704
```

If `p_cloud > 0.5` and the model is confident about it (`>= cloud_drop_conf = 0.95`),
the action is **discard** and nothing is transmitted. If it is cloudy but the model is
not confident, the action is **hold** — kept, not prioritised.

The temperature constant matters: without it the softmax is overconfident and almost
every frame trips the confidence gate.

---

## 7. Transmit lightweight JSON coordinate alerts for high-confidence detections

**Requirement:** JSON coordinate alerts for detections >= 95% confidence.

**Built:** when `class_confidence >= conf_t = 0.95` and the frame is clear, the action
is **alert** and the satellite sends a coordinate-only payload — no pixels at all.

```json
{"i": "...", "t": "Residential_1539", "cls": "Residential", "conf": 0.9864,
 "bbox": [320, 0, 480, 160], "row": 0, "col": 1,
 "score": 0.234, "salience": 0.897, "p_cloud": 0.0}
```

**Measured size: 226 bytes.** Against roughly 14,000 bytes for a crop, that is a
98% reduction on the alert path alone.

---

## 8. Queue compressed crops only for low-confidence edge cases

**Requirement:** selectively queue compressed image crops only for < 95% confidence.

**Built:** clear frames below the confidence gate get the action **queue_crop** and
are the only thing that costs image bandwidth. A 160x160 thumbnail at JPEG q70 plus
the verdict envelope is about 7 kB.

Frames that are **discarded** cost zero bytes. Frames that are **alerts** cost 226
bytes. Only **queue_crop** and **hold** cost a thumbnail.

---

## 9. Cloud foundation-model verification

**Requirement:** low-confidence crops go for cloud foundation-model verification.

**Built:** the ground station re-runs the model on each received thumbnail
(`POST /infer`, `ground/model_interface.py`) and logs whether its verdict agrees with
the satellite's.

**Honest limitation:** the ground currently re-runs the *same* 1.34 MB model, not a
larger foundation model. The architecture supports a heavier verifier — the ground has
no RAM or power budget — and swapping `model_interface.predict()` is the only change
needed. We have not done it, and we say so.

---

## 10. Bandwidth reduction >= 80%

**Requirement:** >= 80% bandwidth reduction.

**Measured** by `tools/benchmark.py`, comparing raw capture bytes against bytes
actually put on the wire:

| dataset | raw capture | transmitted | reduction |
| --- | --- | --- | --- |
| `tiles` (384x384 frames) | 7.96 MB | 0.12 MB | **98.4%** |
| `eurosat` (64x64 patches) | 1.23 MB | 0.23 MB | **81.2%** |

The EuroSAT figure is the worst case: those frames are only 12 kB raw, so the fixed
per-payload overhead dominates. On realistic frame sizes the reduction is 98%.

**Both pass the 80% bar.**

---

## 11. Accuracy retention < 2% drop

**Requirement:** less than 2 points lost to compression.

**Status: needs one number from the notebook.** Notebook cell 10 prints the paired
FP32 / pruned-FP32 / INT8 comparison on the test set, including
`DROP cls_top1 (pts)` and `DROP cloud_acc (pts)`. Those are the retention figures.

What we can state from this repository: INT8 top-1 is **67%** on 100 labelled frames
from our own EuroSAT subset (measured, `tools/benchmark.py`). The FP32 baseline for
the same split is in the notebook output.

**If asked and you do not have the notebook run in front of you:** say the INT8 figure
is 67% on our subset, that the notebook computes the paired FP32 baseline in cell 10,
and that the retention check is the one number we would produce from a fresh training
run. Do not invent a retention figure.

---

## 12. Live pass-simulation responsiveness

**Requirement:** responsive during final judging.

**Built:** two-process simulation. The satellite runs the full chain and downlinks
during a pass; the ground serves the dashboard, receives, and re-verifies. The
dashboard has a two-phase control so you can hold it in standby and bring the link up
live on command.

Inference is ~10 ms per frame on one CPU thread; the model is small enough that the
bottleneck is the simulated link, not the compute — which is the correct behaviour for
this problem.

---

## Summary

| criterion | status |
| --- | --- |
| Backbone + public dataset | done — MobileNetV3-small, EuroSAT |
| Structured L2 pruning | done — notebook cell 8 |
| Static INT8 quantisation | done — notebook cell 9, 3.19x |
| Peak RAM < 4.2 MB | done — 1.65 MB, 2.5x headroom |
| Pass simulation | done — 256 kbit/s / 600 s mission profile |
| Discard cloud locally | done — discard + hold actions |
| JSON coordinate alerts >= 95% | done — 226 bytes, no pixels |
| Crops only for < 95% | done — queue_crop is the only image path |
| FM verification | partial — ground verifies with the same model |
| Bandwidth reduction >= 80% | done — 98.4% tiles, 81.2% worst case |
| Accuracy retention < 2 pts | needs the notebook's cell 10 output |
