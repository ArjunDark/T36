# Pipeline notes

Discrepancies found while splitting the single-station build into two, and what
was done about them.

## Fixed

**Frame sizes were modelled, not measured.** The browser build estimated stored
bytes by scaling an encode of a 384² working tile up to a nominal 1024², and
estimated compression with `b = b₀·(q/q₀)^1.9`. On the satellite the frames are
real JPEGs at their real resolution, so the store holds actual bytes and
compression is an actual re-encode from the archive. What the index reports is
what is on disk.

**The PSRAM ring never drained.** Frames were pushed onto the 3-slot ring and
never released, so it read 3/3 permanently and the next capture would have been
refused. The ring is a staging buffer, not a store: `release()` is now called as
soon as the tensor exists, and it reads 0–1/3 in normal operation.

**The ground station was decorative.** In the single-station build it was a panel
labelled "not wired" with a marker on a globe. It is now an actual process on an
actual machine, and the dashboard renders nothing it did not receive.

**Store state was stale on the ground.** The index was snapshotted when a frame
was queued, which could be minutes before it was transmitted. Payloads are now
enriched at transmit time.

**Frame features never reached the ground.** The dashboard had columns for cloud,
edge density and entropy that always showed "—" because only the score was sent.
The feature vector now travels with the frame; it is three numbers and it is what
makes the score explainable.

## Deliberately not "fixed"

**The scoring model is a placeholder.** `stub-featurescore` is a hand-tuned
formula. Making it look more like a model would be worse than leaving the seam
obvious; `tinyml/README.md` describes what has to arrive.

**The tensor is sent to the ground as an image.** Strictly, the ground does not
need the model input — the model already ran. It is sent because an operator
should be able to see what the model saw, and 8 kB of preview is cheap against
the alternative of an unexplainable score. If link budget ever gets tight, this
is the first thing to drop.

**No attitude model.** The Earth view is a rotating globe, not a propagated orbit,
and the ground station marker does not reflect real geometry. It is context, not
telemetry — but it should not be mistaken for a ground track.

## Worth knowing

- **The 4.2 MB SRAM guard never fires at 160 px.** 160²×3 is 75.0 kB. It fires
  only if the tensor resolution is raised past ~1210 px. That is correct — the
  guard is a limit, not a target — but it means the guard is untested in normal
  operation. `config.json → tensor_res` exists so it can be exercised.
- **Compression degrades, eviction removes.** A frame is re-encoded in 0.15 steps
  down to `quality_floor` (0.35), then evicted. The top 3 frames by effective
  score are protected from both.
- **The store is the satellite's, not the ground's.** The ground's frame index is
  a mirror. Purging it on the ground would do nothing; the satellite would send
  the same index next pass.
