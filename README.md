# AllAtOnce

> **Setting it up on two laptops?** Read [SETUP.md](SETUP.md) — it walks from a
> clean **Windows** install to a running pass, including the firewall rule, the
> benchmark scorecard and the record/replay fallback.

A two-station CubeSat imaging payload: one laptop on the satellite, one on the
ground, talking over the local network the way a real downlink works.

The payload chain runs **on board**. The ground station receives results, never
the pipeline.

```
   SATELLITE LAPTOP                              GROUND LAPTOP
   ────────────────                              ─────────────
   inbox/  ← operator drops images
      │
      ▼
   CubeSatIngressModule     raw frame → 3-slot PSRAM ring
      │
      ▼
   tensor                   160² int8, clip(x−128)
      │
      ▼
   features                 cloud, edge, entropy, contrast
      │
      ▼
   model connector          relevance / visibility        ──►  POST /ingest  ──►  server.py
      │                                                                              │
      ▼                                                                              ▼
   mass memory              compress / evict on watermark                    GET /feed (poll)
      │                                                                              │
      ▼                                                                              ▼
   downlink queue           priority ordered                                 dashboard: thumbnails,
      │                                                                      scores, store index,
      ▼                                                                      event log, Earth
   pass window              9.6 kbit/s, 20 s every 90 s
```

## Two downloads, one per station

| station | what runs there | needs |
| --- | --- | --- |
| **satellite** | `satellite/` — capture, preprocess, scoring, storage, downlink | python3, numpy, opencv |
| **ground** | `ground/` — HTTP server and the dashboard | python3 (stdlib only) |

They are independent. Copy `satellite/` to one laptop and `ground/` to the other;
neither needs the other's files.

```
pip install numpy opencv-python-headless
```

## Run it

**Ground laptop** — find its address first (`ip addr` / `ipconfig`):

```
cd ground
python3 server.py --port 8000
# dashboard: http://localhost:8000
```

**Satellite laptop** — point it at the ground, then feed it images:

```
cd satellite
# edit config.json → "ground": { "host": "192.168.1.42", "port": 8000 }
python3 sat.py
```

Drop JPEGs into `satellite/inbox/` and they are picked up within half a second.
Or stage a batch from the bundled dataset:

```
python3 tools/feed_inbox.py --count 6
```

## What you will see

The satellite terminal prints one line per stage and a status line:

```
SAT-1 │ PASS CLOSED  63s │ QUEUE  4   49.0 kB │ STORE  0.20/16.00 MB │ PSRAM 1/3 │ sent 1 fail 0
```

The ground dashboard shows the frames that came down, their scores, the
satellite's mass-memory index and its event log.

Because the link is modelled at 9.6 kbit/s, a 20-second pass carries roughly one
frame. That is the point: the queue backs up, the operator sees it, and the
on-board ranking decides what the ground ever gets to see.

## Why the split is honest

- **Bandwidth is the constraint.** A real CubeSat downlink is a few kbit/s for a
  few minutes per orbit. Sending every frame is not an option, so frames are
  scored on board and queued by priority.
- **Storage is the constraint.** 16 MB of mass memory against 50 kB frames means
  roughly 320 frames; the manager compresses the lowest-ranked ones and evicts at
  the quality floor.
- **Compute is the constraint.** The model sees a 160² INT8 tensor, 75.0 kB,
  because that is what fits an SRAM scratchpad and a small accelerator.

## Folders

```
satellite/     station 2 — the payload chain and the downlink
ground/        station 1 — receiver and dashboard
tinyml/        PLACEHOLDER — where the trained model goes
stitching/     PLACEHOLDER — the USP: frame-to-frame stitching and examination
dataset/       3 sets, 426 images: 18 hand-picked scenes, 400 labelled EuroSAT
               patches, 8 full Sentinel-2 scenes. Full EuroSAT (27,000) on demand.
tools/         helpers (feed the inbox, check the link)
docs/          architecture, link model, pipeline notes
```

`tinyml/` and `stitching/` are deliberately empty of code. Both are described in
their READMEs so the interface is fixed before anything is written against it.

## Imagery

Three sets: 18 hand-picked public-domain scenes (NASA / USGS / NOAA / ESA via
Wikimedia), 400 labelled Sentinel-2 patches from EuroSAT, and 8 full Sentinel-2
scenes from AWS Open Data. The full 27,000-image EuroSAT set is one command away
via `tools/fetch_eurosat.py`. Licences and provenance are in `dataset/README.md`.

## Releases

Every change ships as a tagged release. See `CHANGELOG.md`; roll back by
downloading the source of the tag you want.
