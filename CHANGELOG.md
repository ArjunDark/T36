# Changelog

Every change ships as a tagged release. Minor bump for anything visible, patch
for fixes. Roll back by downloading the source of the tag you want.

## [3.6.1] — the console gets its six tabs

### Added
- the satellite console is now the **tabbed build**: Mission Control, Image
  Intelligence, Transmission Queue, Downlink Optimizer, Model Performance,
  Simulation. All six run against the real pipeline.
- `?view=<name>` deep-links to a tab.

### Wired so the tabs have real data
- `infer_ms` in the satellite's telemetry, so Model Performance shows a real
  average latency and a latency chart instead of zeros
- bandwidth history feeds the Downlink Optimizer throughput chart
- the model badge reads **ONBOARD MODEL**, not "LOCAL HEURISTIC" — the ONNX is
  running on the spacecraft, and the old label was wrong
- `SAT.model`, `SAT.dataset` and `SAT.preprocess` shims, because the original UI
  was a browser simulator and those objects were its local stand-ins

### Notes
- the Simulation tab's Run Control buttons are inert on purpose: they drove the
  browser simulator, and on the spacecraft the pipeline is the Python process.
  Clicking one logs "the pipeline runs in Python; this console only observes".

## [3.6.0] — the two screens, in the right places

### Added
- **the satellite has its own console.** `satellite/web/` is the SMART-TRIAGE
  mission view exactly as delivered — Earth, the capture → analysis chain, PSRAM,
  mass memory, priority card, transmission queue, mission telemetry — served by
  the satellite on `http://localhost:8001` and fed by its **own** pipeline
  instead of simulating in the browser.
- `satellite/webserver.py` — a small server that exposes the onboard state at
  `/feed` and serves the console. Binds to `127.0.0.1` only: the ground cannot
  open it, which is the point.
- `--web-port` and `--no-web` flags on `sat.py`.

### Changed
- the ground keeps only the simple view. `full.html` moved to the satellite,
  where that dashboard always belonged.
- only `js/app.js` was replaced in the satellite console. Every other file is
  byte-identical to the original; the class vocabulary and the hardcoded pass
  total were the only other edits, because the model emits 10 EuroSAT classes and
  the original UI listed 5.

### Verified
- satellite console: 18 onboard frames, SRAM 1.0/4.2 MB, storage 1.0/16.0 MB,
  TRANSMIT/QUEUED badges, 10-class distribution populating, pass 00:00 / 00:25
- ground view: 12 received frames, verification log showing match and differs
- both run at the same time and show different things

## [3.5.2] — the setup guide was teaching a broken install

### Fixed in SETUP.md
- **it told you to run `py -3.12 -m pip install` inside an activated venv.** The
  `py` launcher resolves the system interpreter by version tag and ignores the
  venv, so every package landed in user site-packages and the very next
  `python -c "import cv2"` failed. Inside a venv it must be plain
  `python -m pip install`.
- it now names the giveaway: `Defaulting to user installation because normal
  site-packages is not writeable` means the install went to the wrong place.
- it now says explicitly that the **import name and the package name differ**:
  you import `cv2`, you install `opencv-python-headless`. `pip install cv2`
  always fails.

### Added
- `tools/doctor.py` — one command that checks the interpreter, the venv, all four
  packages, the model file, every folder, the config, and whether the model
  actually loads, then prints the exact fix for whatever is wrong.

## [3.5.1] — Windows setup

### Changed
- **SETUP.md rewritten for Windows throughout.** `py -3.12` rather than
  `python3`, `.venv\Scripts\activate` rather than `source`, `ipconfig` rather
  than `ip addr`, `del` rather than `rm`, the `netsh` firewall rule instead of
  `ufw`. No Linux commands remain.
- a new section 0 on `py -0p` (a zero) and why plain `py` runs the wrong
  interpreter — the failure that cost the most time during setup.
- `docs/link.md` now leads with the Windows options (software pacing, Clumsy,
  WSL2) and treats `tc`/`netem` as a Linux aside.
- README says Windows.

## [3.5.0] — the scorecard covers every criterion

### Added
- `tools/benchmark.py` now reports all five judging criteria in a summary block,
  each with PASS / FAIL / n-a and the bar it is measured against:
  RAM compression, flash compression, accuracy retention, bandwidth reduction,
  peak RAM against the envelope, whether the run fits the pass window, and live
  responsiveness.
- **RAM compression** measured properly: activation element count, INT8
  weights+activations against FP32 weights+activations.
- **latency** per frame (median and p95) and throughput in frames per second.
- **pass simulation**: how many seconds of link the run's payloads need, against
  the window.
- `--fp32 <path>` for the accuracy-retention reference, with auto-detection of
  `tinyml/model_fp32.onnx`.

### Not measured
- accuracy retention still needs a real FP32 model. The harness computes it the
  moment one is present; without it the row reads `not measured` and names the
  fix. Dequantising the INT8 graph would produce a float model with the *same*
  weights and therefore a 0.00 drop — a true number about the wrong thing, so it
  is not reported as retention.

## [3.4.1] — the benchmark says which Python is wrong

### Changed
- `tools/benchmark.py` now prints the interpreter path and version when the model
  or OpenCV is missing, and the exact `pip install` command for *that*
  interpreter. On Windows, `py` runs the newest Python — usually not the one
  packages were installed into — so the failure was indistinguishable from a
  genuinely missing package.
- `SETUP.md` gains a Windows benchmark section.

## [3.4.0] — runs by itself, and a ground UI that works

### Added
- **auto-feed.** The satellite tops its own inbox up from `dataset/` every few
  seconds. `python sat.py` alone now produces a full demo — no `feed_inbox.py`,
  no second terminal, nothing to remember. Configured under `auto_feed` in
  `config.json` (`enabled`, `set`, `interval_s`, `per_cycle`).
- **a new simple ground view** at `/`. Big received image, telemetry, last-frame
  detail, frame strip, event log. Responsive CSS grid — no fixed 1672x941 canvas,
  no absolute positioning, no scaling transform, so it cannot collapse the way the
  old one did.
- `/?phase=2` starts the simple view already listening, for bookmarking.
- the old mission view is preserved at `/full.html`.

### Fixed
- the image now fills its panel instead of floating in black bars
- the frame strip and the class bar were clipped at their panel edges
- `sent` was blank because the satellite never reported it; telemetry now carries
  `sent`, `failed`, `degraded` and `dropped`
- a coordinate alert showed `size 0 kB`; it now says "no pixels" and explains why

### Why the UI changed
The mission view depends on `ui.js fit()` setting `--dx` so that a dozen
`calc()` offsets resolve. Miss that one call — which is exactly what happened in
v3.0.0 — and every absolutely-positioned block collapses to the left edge. A
responsive grid has no such failure mode.

## [3.3.1] — the ground station starts clean

### Fixed
- the ground station restored the previous session's frames from
  `received/feed.json` on startup, and the dashboard polls `since=0`, so every
  frame from an earlier run came back. Starting the ground alone showed a
  populated dashboard with no satellite anywhere. **Clean start is now the
  default**; `--restore` brings the old session back deliberately.
- startup now says what it did: `starting clean - N frames from a previous
  session were NOT loaded`

### Notes
- `SETUP.md` gains a section on `ground/received/`: what accumulates there, how
  to wipe it, and how to tell a restore from a real `/ingest` posting.

## [3.3.0] — setup guide

### Added
- `SETUP.md` — the full two-laptop procedure on Arch: packages, venv, ground
  address discovery, link check, running a pass, `tc` shaping, the scorecard, the
  one-laptop fallback and record/replay. Written from the steps that were being
  given in chat, so they are versioned and in the repo.
- README links it at the top

### Notes
- both machines need the whole repository. The ground loads `tinyml/` for
  verification and the satellite loads `dataset/` and `tools/` from beside it;
  copying folders is the most common way to break the install.
- Arch's Python is externally managed, so the venv is required rather than
  optional. If the rolling release has moved past 3.14, `python312` from the AUR
  is the fix.

## [3.2.1] — record and replay

### Added
- `ground/server.py --record` appends every received payload to
  `received/bag_<ts>.jsonl`, one JSON object per line
- `tools/bag.py info|replay` — inspect a bag, or push it back into a ground
  station at the original cadence or faster
- `docs/link.md` gains the record/replay section and a note on why ROS 2 was
  considered and rejected

### Fixed
- a local variable named `stamp` shadowed the module's `stamp()` function, so the
  server crashed on startup whenever `--record` was passed

### Why this exists
A live demo has one chance. Record a good pass, replay it if the LAN misbehaves
in front of judges. It is the `rosbag2` idea without the middleware.

## [3.2.0] — link planner, real leak fixed, 25 s cycle

### Fixed — pre-labelling leak
The alert flag and the interest weighting were read from the **filename**, not
from the model. The same image named `smoke` raised an alert; named `Forest_1141`
it did not. The model was genuinely running (identical prediction either way) but
the decision was contaminated. `verdict()` no longer takes a category at all —
alert comes from the triage action, which comes from model confidence.

### Added — the second compression round
Before every transmission the sender asks how many bytes are left in the pass and
degrades the payload until it fits:

| level | payload | size |
| --- | --- | --- |
| 0 | thumbnail + tensor preview | ~15 kB |
| 1 | thumbnail only | ~9 kB |
| 2 | coordinates and verdict, no pixels | ~400 B |

Below level 2 it is dropped if under the priority floor, otherwise held for the
next pass. Nothing is lost silently. `link_overhead` (0.15, standing in for
framing + FEC + retransmits) and `min_priority` (0.20) are config values.

### Changed
- demo profile is now the 25 s cycle: 25 s capture, 25 s downlink, 256 kbit/s.
  The satellite keeps capturing during the downlink, so the queue grows while it
  drains.
- `tools/shape_link.sh` — `tc`/`netem` shaping so the OS itself is throttled, not
  just the sender. Linux only; Windows guidance is in `docs/link.md`.
- `docs/link.md` rewritten: what is real, what is simulated, what CCSDS would
  replace, and how to run it across two laptops.

### Verified
- `tinyml-cloud-triage` INT8 vs FP32 agree to within 0.0005 on cloud fraction and
  to 2 decimals on priority — quantisation costs essentially nothing
- the ONNX artefacts in that project are exported at 128 but `infer.py` tiles at
  192, which raises an ONNX dimension error; `--tile 128` works

## [3.1.0] — compliance with the challenge brief

### Added
- **coordinate alerts.** A detection at >= 95% confidence now transmits a JSON
  coordinate block with no pixels at all: 226 bytes against ~14,000 for a crop.
  High-confidence detections are the cheapest thing the satellite sends.
- **crops only for uncertain frames.** `queue_crop` and `hold` are the only actions
  that cost image bandwidth. `discard` costs zero bytes.
- `tools/benchmark.py` — the judging scorecard: bandwidth reduction, flash
  compression, working RAM against the 4.2 MB envelope, INT8 accuracy, triage
  behaviour, pass capacity.
- `COMPLIANCE.md` — every requirement in the brief mapped to the code that meets it,
  with the measured number.

### Measured
- bandwidth reduction **98.4%** on 384x384 frames, **81.2%** on 64x64 EuroSAT patches
  (worst case, fixed payload overhead dominates at that size)
- working RAM **1.65 MB** against a 4.2 MB envelope — 2.5x headroom
- flash **1.34 MB** INT8 against 4.28 MB FP32 equivalent — 3.19x from quantisation
- INT8 top-1 **67%** on 100 labelled frames

### Not done
- accuracy retention needs the notebook's cell 10 output (paired FP32 baseline).
  Documented as the one number to produce from a fresh training run rather than
  estimated.
- the ground verifies with the same 1.34 MB model, not a larger foundation model.
  The hook is there; we say so rather than implying otherwise.

## [3.0.0] — the notebook's triage policy

### Changed
- **the decision logic is now the one from the training notebook**, not the
  hand-calibrated feature score. Temperature-scaled probabilities, per-class
  salience weights, a novelty term from the embedding, and four actions.
- `satellite/config.json` carries the policy block with the notebook's fitted
  values: T_cloud 1.1704, T_class 1.4297, cloud_drop_conf 0.95, conf_t 0.95,
  salience weights, frame_score_weights [0.6, 0.4]
- **link model is the notebook's**: 256 kbit/s over a 600 s pass, as the mission
  profile. `satellite/config.demo.json` keeps a fast profile for demos.
- `tinyml/leo_tinyml_triage.ipynb` is in the repo — the training pipeline that
  produced the model
- ground UI updated to the newer smart-triage build: two-phase control and the
  click-to-zoom image viewer
- the class bar and both legends show the 10 EuroSAT classes

### The policy, in one block
```
p_cloud  = sigmoid(cloud_logit / T_cloud)
probs    = softmax(class_logits / T_class)
salience = probs . salience_weights
novelty  = cosine distance to the mean of clear frames seen so far
score    = salience x novelty x (1 - cloud_frac)
action   = discard | hold | alert | queue_crop
```

### Fixed
- **stage cards collapsed to the left edge.** The layout depends on `--dx`, which
  `ui.js fit()` sets; the receiver never called it, so every `calc()` left in the
  stylesheet was invalid and four absolutely-positioned blocks stacked on top of
  each other. One missing call, four broken panels.
- the pass timer showed a hardcoded `10:00` total; it now reads the satellite's
  actual pass length from telemetry
- the 10-class legend overflowed its box in one column; it is a two-column grid now
- the store card overlapped the downlink block by 12 px

## [2.0.0] — smart-triage becomes the ground station

### Changed
- **ground/web/** is now the smart-triage dashboard: textured Earth, the capture →
  image → analysis chain, transmission queue, mission telemetry
- **the simulation is gone.** `js/app.js` is a receiver: it polls `/feed` and renders
  what came down the link. Nothing is captured locally any more.
- **verification path added.** Every arriving frame is re-scored through
  `POST /infer` on the thumbnail that actually arrived, and the event log records
  `VERIFY match` or `VERIFY differs` against the satellite's verdict.
- the class bar shows the model's **10 EuroSAT classes** instead of the old
  5-class vocabulary (Urban / Water / Vegetation / Bare Land / Cloud)
- satellite now emits a `v` verdict block: scene, alert, conf, util, prio, factors,
  classDist — the exact shape this dashboard reads
- the console and neon skins are gone with the old dashboard

### Fixed
- the verdict was nested inside `f`, where it collided with the visibility field of
  the same name and was silently dropped. It is now top-level.
- `class_probs` was not carried through the registry, so the class bar rendered empty

### Notes
- `ground/model_interface.py` runs the same `tinyml/model_int8.onnx` the satellite
  flies, so a verification mismatch is a real disagreement, not a different model.
- util is the calibrated relevance; conf and classDist come from the classifier.
  priority uses the dashboard's own weighting so the factor bars reconcile.

## [1.4.0] — the refined model

### Changed
- `tinyml/model_int8.onnx` replaced with the refined model: 1.34 MB, four heads,
  input `[batch, 3, 160, 160]`
- SRAM tensor back to **160x160** (75.0 kB) to match the model's input
- adapter decodes all four heads: class label, confidence, cloud probability,
  cloud fraction, plus the 576-d embedding (exposed, not yet transmitted)
- ground dashboard shows **Model class**, **Confidence**, **Cloud (model)** in
  place of the old single map value

### Verified
- **62% top-1 accuracy** on 100 patches from the bundled EuroSAT subset, against a
  10% random baseline. Residential 10/10, Pasture 1/10.
- cloud heads track reality: cyclone 0.31 p_cloud against a measured 0.30;
  clear dunes and cropland 0.00
- known weakness, documented: bright snow reads `cloud_frac` 0.24 while `p_cloud`
  correctly reads 0.00 — the regression head mistakes bright ground for cloud

### Notes
- ranking still uses the calibrated feature scorer. The model supplies label,
  confidence and cloud as telemetry; promoting it to drive keep/discard is a
  policy change that has not been made.

## [1.3.0] — two skins

### Added
- `css/neon.css` — the original retrowave surface as a switchable skin: deep
  blue-black, amber and cyan, a perspective grid behind the spacecraft view
- `js/theme.js` — skin switcher, persisted in `localStorage`, `T` to toggle
- `skin:` button in the header

### Changed
- the neon skin `@import`s `styles.css` and overrides only the surface, so the
  layout, the no-scroll behaviour and every element id are shared. Neither skin
  can drift from the other's geometry.
- ground README documents the skins

### Notes
- the first attempt swapped the stylesheet outright, which dropped the grid
  layout and collapsed the page into a single column. Caught in a render before
  it shipped; the import fixes it structurally rather than by copying rules.

## [1.2.0] — the ONNX model is in

### Added
- `tinyml/model_int8.onnx` — 154 kB, the quantised model
- `tinyml/adapter.py` — real inference over the ONNX session, implementing the
  `BaseCubeSatModelAdapter` interface from `wrapper_1.py`
- `tinyml/model_card.json` — verified signature, measured numbers, and what the
  model does not do
- `MODEL MAP` field on the ground dashboard

### Changed
- `activation_bytes` is now measured (262 kB, the buffers this inference actually
  allocates) instead of the 2.2 MB constant the wrapper simulated
- the model runs **alongside** the feature scorer, not instead of it: relevance and
  visibility still come from the calibrated scorer, the map travels as telemetry

### Found
- **the model is not a classifier.** Input `[b,3,128,128]`, output
  `[b,1,128,128]` — a per-pixel map. There is no 10-class vector, so label and
  confidence over the EuroSAT classes cannot come from this file.
- **it does not track cloud.** A 30% cloudy cyclone scores 0.233 mean while a
  clear Sahara dune scene scores 0.341. The opposite of a cloud head.
- it separates land cover weakly (Forest 0.04, PermanentCrop 0.84) with large
  within-class spread, so not a usable classifier either.
- `wrapper_1.py` returns `np.random.uniform` values — it is a scaffold, and it is
  not used.

### Still missing
- `headline_demo`, `headline_temporal`, `headline_gate`, `headline_policy`,
  `headline_train` — imported by `triagefinal_1.py`, not in this repo
- the 256 kbit/s / 600 s / truncate-at-180 gate those modules implement

## [1.1.1] — tensor 128

### Changed
- SRAM tensor is now 128x128 (was 160x160), so it is 48.0 kB and matches the input
  shape the ONNX classifier expects. The model can consume the tensor directly with
  no conversion step.
- Recalibrated check: the placeholder scorer still spreads the same way at 128 px
  (tiles 46-98, EuroSAT 33-92, Sentinel-2 46-94), so the constants did not need
  changing. Verified rather than assumed.

## [1.1.0] — expanded imagery

### Added
- `dataset/eurosat/` — 400 labelled Sentinel-2 patches (40 per class, 10 classes),
  the balanced subset of EuroSAT RGB
- `dataset/sentinel2/` — 8 real Sentinel-2 L2A scenes at 1024x1024, fetched from the
  public AWS Open Data bucket, screened for cloud cover and nodata
- `tools/fetch_eurosat.py` — pulls the full 27,000-image set (95 MB) on demand
- `tools/feed_inbox.py --set tiles|eurosat|sentinel2|all` — draw from any set
- `manifest.json` v2 — every set carries source, sensor, licence and provenance

### Changed
- dataset README rewritten around the three sets, with the resolution caveat spelled
  out: EuroSAT patches are 64 px and get upscaled to the 160 px tensor, so they score
  lower on relevance (median 48) than the native 384 px tiles (median 74). Measured,
  not corrected for.

### Not done
- Landsat: needs a USGS EarthExplorer account. The public mirrors that used to work
  without one now return AccessDenied or 403. Documented, not faked.

## [1.0.0]

First split build. The payload chain moves to the satellite laptop; the ground
laptop becomes a receiver with the dashboard.

### Added
- `satellite/` — Python station: inbox watcher, `CubeSatIngressModule` (PSRAM
  ring, INTER_AREA resize, INT8 quantisation, 4.2 MB SRAM guard), feature
  extraction, model connector, mass memory with compress-then-evict, priority
  downlink queue
- `ground/` — stdlib HTTP server serving the dashboard and receiving
  `POST /ingest`; thumbnails and state persisted to `received/`
- downlink model: bit-rate limit, priority queue, repeating pass window
- `tinyml/` and `stitching/` placeholders with fixed interfaces
- `tools/feed_inbox.py`, `tools/check_link.py`

### Changed from the single-station build
- frame sizes are now **measured**, not modelled: a frame is a real JPEG encode
  and compression is a real re-encode from the archive
- the ground no longer simulates anything — every number on screen arrived over
  the link
- the PSRAM ring releases a slot as soon as the tensor exists, so it reads 0–1/3
  rather than sitting full

### Known
- the scoring model is still a placeholder formula
- `stitching/` is documentation only
