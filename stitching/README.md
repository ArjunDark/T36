# stitching/ — the USP

**Placeholder. No code here yet.**

Frame-to-frame stitching and examination: instead of treating each capture as an
independent frame, treat consecutive frames as overlapping views of the same
ground strip and stitch them into one continuous scene, then examine that scene
rather than the frames.

Why it matters for this pipeline: scoring frames independently throws away the
information that only exists *between* them. A frame that looks unremarkable on
its own may be the only one covering a gap in the strip. Stitching changes what
"worth downlinking" means — the unit of value becomes coverage of the mosaic, not
the score of a single frame.

## Where it plugs in

Between the model connector and mass memory:

```
features ─► model ─► [ stitching ] ─► mass memory ─► downlink
```

A stitched mosaic is also the natural thing to downlink: one 1024² mosaic of a
strip costs less link time than the eight 384² frames that made it, and carries
more.

## Interface to agree on before implementing

```python
def stitch(frames: list[Frame]) -> Mosaic:
    """frames are consecutive captures, possibly with overlap.
       Returns a mosaic plus the transform of each frame into it."""
```

Open questions that need answering first:

- **Overlap.** Consecutive captures only stitch if the ground track advances less
  than the frame width between them. The capture interval and the ground speed
  set this; today the inbox is fed by hand, so overlap is whatever the operator
  drops in.
- **Attitude.** Without knowing the spacecraft's pointing, the transform is a
  translation estimate, not a measurement. A real system would use the ADCS
  quaternion as a prior and refine it against the image.
- **Where it runs.** On board (needs memory and compute, saves bandwidth) or on
  the ground (needs the frames to be downlinked first, which is what stitching is
  meant to avoid).

None of this is decided. Do not build against this README without settling the
three points above.
