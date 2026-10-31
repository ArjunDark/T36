# ground/ — the ground station

Two views, same data:

| page | what it is |
| --- | --- |
| `/` | **the simple view** — big received image, telemetry, last-frame detail, frame strip, event log. Responsive, no fixed canvas, no absolute positioning. This is the one to use. |
| `/full.html` | the full mission view — rotating Earth, the capture→analysis chain, the priority card. Prettier, more fragile; it depends on a fixed 1672x941 canvas. |

`/?phase=2` opens the simple view already listening, so you can bookmark it.

Serves the smart-triage dashboard and receives what the satellite downlinks.

```
python3 server.py --port 8000        # then open http://localhost:8000
```

Nothing needs installing beyond the standard library for the dashboard itself.
The verification path (`/infer`) needs `onnxruntime` and `opencv-python-headless`,
because it re-runs the model on what arrived.

## Routes

| route | what it does |
| --- | --- |
| `GET /` | the dashboard |
| `POST /ingest` | the satellite posts frames here during a pass |
| `GET /feed?since=N` | the dashboard polls this |
| `POST /infer` | re-runs the model on a received thumbnail |
| `GET /health` | station state and the model card |

## The dashboard is a receiver

`js/app.js` was the acquisition loop in the original smart-triage build. It is now
a receiver: it polls `/feed` every 900 ms and turns each arriving entry into the
frame object the UI draws. There is no local capture, no local simulation.

That means the empty state is real. Until a pass opens and a frame comes down, the
dashboard has nothing to show — which is the point.

## Verification

Every frame is scored twice: once on the satellite before downlink, once here on
the thumbnail that actually arrived.

```
VERIFY match · Forest 34% (ground)
VERIFY differs · Industrial 71% (ground)
```

A mismatch is not a bug. The model is 62% accurate, and the ground copy sees a
compressed thumbnail rather than the full frame, so some disagreement is expected.
What the line proves is that the verdict travelled with the frame and survived
the link.

`ground/model_interface.py` loads the same `tinyml/model_int8.onnx` the satellite
flies, so a mismatch is a genuine disagreement, not a different model.

## Layout

The dashboard is a fixed 1672x941 canvas scaled to the viewport by `js/config.js`.
At a smaller window it scales down rather than reflowing, which is deliberate —
nothing scrolls.
