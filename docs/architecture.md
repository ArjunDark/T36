# Architecture

Two processes on two laptops. The split is not cosmetic — it follows the
constraint that actually shapes a CubeSat mission: you cannot downlink
everything, so the decision has to be made on board.

## The chain

| # | stage | where | what it costs |
| --- | --- | --- | --- |
| 1 | ingest | satellite | 3 PSRAM slots, 0.42 MB per raw frame |
| 2 | tensor | satellite | 160²×3 int8 = 75.0 kB, checked against 4.2 MB SRAM |
| 3 | features | satellite | measured on the de-quantised tensor |
| 4 | score | satellite | relevance + visibility, 0–100 each |
| 5 | store | satellite | real JPEG bytes, 16 MB capacity |
| 6 | queue | satellite | priority ordered by effective score |
| 7 | downlink | link | 9.6 kbit/s during a 20 s pass |
| 8 | display | ground | mirror of 5 and 6, plus thumbnails |

Stages 1–6 are `satellite/`. Stage 8 is `ground/`. Stage 7 is the only thing they
share, and it is deliberately narrow.

## What the ground knows

Only what arrived. The ground holds no pipeline state of its own: it renders the
satellite's mass-memory index, the satellite's event log and the thumbnails that
came down. If the link never opens, the ground stays empty — which is the
correct behaviour and a useful way to test that nothing is being faked locally.

## Payload format

```json
{
  "station": "SAT-1",
  "seq": 12,
  "ts": "2026-10-31T04:12:33+00:00",
  "f": {
    "i": "PIVOT_0012", "t": "pivot", "b": 64958,
    "q": 0.90, "r": 88.4, "v": 82.9, "p": 86.2, "e": 86.2,
    "tr": "data:image/jpeg;base64,…",
    "tt": "data:image/jpeg;base64,…",
    "fe": { "c": 12.6, "e": 0.268, "h": 6.91 }
  },
  "tel": { "psram": "1/3", "tensor_b": 76800, "res": 160,
           "queue": 4, "queue_b": 50176, "pass": "OPEN", "pass_s": 18, "kbps": 9.6 },
  "store": { "used": 440000, "cap": 16777216, "index": [ … ],
             "compressed": 0, "evicted": 0 },
  "ev": [ { "t": "04:12:31", "s": "INFO", "g": "COMMIT", "m": "stored …" } ]
}
```

`tr` is the frame at thumbnail resolution, `tt` the de-quantised tensor rendered
back to an image. Both are sent because the ground shows the pair side by side —
it is the only way an operator can see what the model was actually looking at.

State is stamped at **transmit** time, not when the frame was queued. A payload
can sit in the queue for several passes; shipping the store index it had when it
was queued would show the ground a stale picture.

## Why the ground is a server

The satellite is the one with something to say, and it says it during a pass. If
the satellite were the server, the ground would have to poll a machine that is
only reachable for 20 seconds in every 90 — possible, but it makes the ground
responsible for knowing when the pass is. As built, the satellite owns its own
pass clock and pushes when it is open; the ground just listens.

## Failure behaviour

- **Ground down mid-pass.** The POST fails, the payload goes back on the queue,
  and it is retried next pass. Nothing is lost.
- **Pass closes mid-transmission.** The sender checks the clock after the dwell
  and aborts before sending, so a frame is never half-transmitted.
- **SRAM breach.** `SramFault` is raised before the frame reaches storage; the
  satellite logs a FAULT and drops it. Raise the tensor resolution in
  `config.json` past ~1210 px to see this.
- **Ground restarts.** `received/feed.json` is reloaded at startup, so the
  dashboard comes back with its history.
