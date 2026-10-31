# tinyml/ — the model

`model_int8.onnx`, 1.34 MB, four heads, quantised with onnxruntime. `adapter.py`
implements the `BaseCubeSatModelAdapter` interface from `wrapper_1.py` with real
inference — the wrapper it replaced returned `np.random.uniform` values.

`leo_tinyml_triage.ipynb` is the training notebook that produced it: MobileNetV3-small
backbone, structured L2 pruning, INT8 quantisation, temperature scaling fitted on a
validation split.

## Signature

```
input   x                [batch, 3, 160, 160]  float32, 0-1
output  cloud_logit      [batch, 1]     sigmoid -> cloud / not-cloud
output  cloud_frac_logit [batch, 1]     sigmoid -> cloud fraction
output  class_logits     [batch, 10]    softmax -> EuroSAT land-use class
output  embedding        [batch, 576]   feature vector, used for novelty
```

## Does it work

Measured on 100 patches from `dataset/eurosat`, 10 per class: **62% top-1 accuracy**,
against 10% for random guessing.

| class | | class | |
| --- | --- | --- | --- |
| Residential | 10/10 | PermanentCrop | 5/10 |
| AnnualCrop | 8/10 | River | 4/10 |
| Forest | 8/10 | HerbaceousVegetation | 3/10 |
| Industrial | 8/10 | Pasture | 1/10 |
| SeaLake | 8/10 | | |
| Highway | 7/10 | | |

The cloud heads track reality: a 30%-cloud cyclone reads `p_cloud` 0.31 against a
measured 0.30; clear dunes and clear cropland read 0.00.

**Known weakness:** bright snow reads `cloud_frac` 0.24 while `p_cloud` correctly
reads 0.00. The regression head mistakes bright ground for cloud. Trust `p_cloud`
over `cloud_frac` on snow and ice.

## The triage policy

The decision logic lives in `satellite/pipeline/scoring.py` and is configured in
`satellite/config.json` under `policy`. It comes from the training notebook.

```
p_cloud  = sigmoid(cloud_logit / T_cloud)        T_cloud = 1.1704
probs    = softmax(class_logits / T_class)       T_class = 1.4297
salience = probs . salience_weights              Industrial 1.0 ... Forest 0.3
novelty  = cosine distance to what we have seen
score    = salience x novelty x (1 - cloud_frac)
```

Four actions, in this order:

| condition | action |
| --- | --- |
| cloud and confident about it (>= 0.95) | **discard** — not worth the bytes |
| cloud, not confident | **hold** — keep, do not prioritise |
| clear, class confidence >= 0.95 | **alert** — the thing worth sending |
| clear, lower confidence | **queue_crop** — keep, lower priority |

The temperature values were fitted on a validation split in the notebook. They matter:
without them the softmax is overconfident and every frame trips the 0.95 alert
threshold.

## Novelty

The notebook computes novelty per tile against the other clear tiles in the same
frame. Here one frame *is* one tile, so `scoring.Novelty` compares each frame's
embedding against the mean of the clear frames seen so far. The first frame of a
session scores 1.0 — there is nothing to compare it to.

A per-tile reference embedding from an earlier pass is supported and is the hook for
change detection: score the same ground on two dates and the cosine distance is the
change signal.

## Replacing the model

Drop a new `model_int8.onnx` in this folder. The adapter reads the input shape from
the session rather than assuming a size, but the SRAM tensor is built at `tensor_res`
in `satellite/config.json`, so the two must agree.
