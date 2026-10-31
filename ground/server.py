#!/usr/bin/env python3
"""
server.py — STATION 1, the ground station

Serves the dashboard and receives what the satellite transmits. This machine is
the server: the satellite pushes to it during a pass.

    python3 server.py                 # http://localhost:8000
    python3 server.py --port 8080

Endpoints

    GET  /                 the dashboard
    GET  /feed?since=N     frames newer than N, plus current satellite state
    POST /ingest           the satellite's downlink payload
    GET  /health           liveness, for the satellite to test the link

Everything received is written to received/ — the thumbnails as JPEGs and the
state as feed.json — so the ground keeps a record of exactly what came down.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
RECEIVED = os.path.join(HERE, "received")
BAG = {"path": None, "n": 0}


def bag_write(payload: dict) -> None:
    """Append one payload to the current bag, if recording is on."""
    if not BAG["path"]:
        return
    try:
        with open(BAG["path"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        BAG["n"] += 1
    except OSError:
        pass

LOCK = threading.Lock()
STATE = {
    "frames": [],        # newest last
    "events": [],        # rolling, newest last
    "sat": {},           # last telemetry block
    "store": {},         # last mass memory index
    "link": {"last_seen": None, "count": 0, "bytes": 0},
    "alerts": [],        # coordinate-only detections, newest last
}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def save_state():
    os.makedirs(RECEIVED, exist_ok=True)
    with open(os.path.join(RECEIVED, "feed.json"), "w", encoding="utf-8") as fh:
        json.dump({k: STATE[k] for k in ("frames", "events", "sat", "store", "link")},
                  fh, indent=1)


def count_stale() -> int:
    path = os.path.join(RECEIVED, "feed.json")
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            return len(json.load(fh).get("frames") or [])
    except (OSError, ValueError):
        return 0


def load_state():
    """Restore the previous session. Only called when --restore is passed."""
    path = os.path.join(RECEIVED, "feed.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for k in ("frames", "events", "sat", "store", "link"):
            if k in data:
                STATE[k] = data[k]
    except (OSError, ValueError):
        pass


def write_thumb(name: str, data_url: str) -> str:
    """Persist a base64 data URL and return the path the browser can fetch."""
    if not data_url or "," not in data_url:
        return ""
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1])
    except (ValueError, IndexError):
        return ""
    os.makedirs(RECEIVED, exist_ok=True)
    fname = name + ".jpg"
    with open(os.path.join(RECEIVED, fname), "wb") as fh:
        fh.write(raw)
    return "/received/" + fname


def handle_ingest(payload: dict) -> dict:
    bag_write(payload)
    frame = payload.get("f") or {}
    fid = frame.get("i", "UNKNOWN")
    seq = int(payload.get("seq", 0))

    with LOCK:
        # A coordinate alert carries no pixels - that is the point of it.
        if payload.get("kind") == "alert":
            a = payload.get("a") or {}
            entry = {
                "seq": seq, "i": a.get("i", "ALERT"), "t": a.get("t", "?"),
                "b": 0, "q": 0, "r": 0, "v": 0, "p": 0, "e": 0,
                "ts": payload.get("ts"), "tr": "", "tt": "",
                "kind": "alert", "fe": None, "a": a,
                "v": payload.get("v") or {},
            }
            STATE["frames"].append(entry)
            del STATE["frames"][:-80]
            STATE["alerts"].append(entry)
            del STATE["alerts"][:-40]
            if payload.get("tel"):
                STATE["sat"] = payload["tel"]
            STATE["link"]["count"] = STATE["link"].get("count", 0) + 1
            return {"ok": True, "id": entry["i"], "kind": "alert"}

        if frame:
            entry = {
                "seq": seq,
                "i": fid,
                "t": frame.get("t", "?"),
                "b": frame.get("b", 0),
                "q": frame.get("q", 0),
                "r": frame.get("r", 0),
                "v": frame.get("v", 0),
                "p": frame.get("p", 0),
                "e": frame.get("e", 0),
                "ts": payload.get("ts"),
                "tr": write_thumb(f"{fid}_raw", frame.get("tr", "")),
                "tt": write_thumb(f"{fid}_int8", frame.get("tt", "")),
                "fe": frame.get("fe"),
                "kind": payload.get("kind") or "crop",
                "v": payload.get("v") or {},
            }
            STATE["frames"].append(entry)
            del STATE["frames"][:-80]

        if payload.get("tel"):
            STATE["sat"] = payload["tel"]
        if payload.get("store"):
            STATE["store"] = payload["store"]

        for ev in payload.get("ev") or []:
            STATE["events"].append(ev)
        del STATE["events"][:-60]

        STATE["link"] = {
            "last_seen": stamp(),
            "count": STATE["link"].get("count", 0) + (1 if frame else 0),
            "bytes": STATE["link"].get("bytes", 0) + len(json.dumps(payload)),
        }
        save_state()

    print(f"[{stamp()}] RX    {fid}  {frame.get('b', 0)/1024:.0f} kB  "
          f"rel {frame.get('r', 0):.1f}  queue {STATE['sat'].get('queue', '?')}  "
          f"pass {STATE['sat'].get('pass', '?')}", flush=True)
    return {"ok": True, "seq": seq}


class Handler(SimpleHTTPRequestHandler):
    server_version = "AllAtOnce-ground/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        pass  # the ingest log above is the useful one

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/feed":
            since = 0
            try:
                since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            except ValueError:
                pass
            with LOCK:
                frames = [f for f in STATE["frames"] if f["seq"] > since]
                return self._json({
                    "frames": frames,
                    "events": STATE["events"][-40:],
                    "sat": STATE["sat"],
                    "store": STATE["store"],
                    "link": STATE["link"],
                    "now": stamp(),
                })

        if path == "/infer":
            return self._json({"ok": False, "error": "POST only"}, 405)

        if path == "/health":
            return self._json({"ok": True, "station": "GS-1", "time": stamp()})

        if path.startswith("/received/"):
            fname = os.path.basename(path)
            full = os.path.join(RECEIVED, fname)
            if not os.path.exists(full):
                self.send_error(404)
                return
            with open(full, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def _infer(self):
        """Re-run the model on a received thumbnail and return its verdict."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return self._json({"ok": False, "error": "bad json"}, 400)

        rel = body.get("path") or ""
        name = os.path.basename(rel)
        full = os.path.join(RECEIVED, name)
        try:
            import model_interface
            result = model_interface.predict(full, frame_id=body.get("frame_id"))
            return self._json(result, 200)
        except Exception as exc:                      # noqa: BLE001
            return self._json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        route = urlparse(self.path).path
        if route == "/infer":
            return self._infer()
        if route != "/ingest":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return self._json({"ok": False, "error": "bad payload"}, 400)
        return self._json(handle_ingest(payload), 202)


def main() -> int:
    ap = argparse.ArgumentParser(description="ground station")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--restore", action="store_true",
                    help="reload the previous session's frames from received/feed.json")
    ap.add_argument("--record", action="store_true",
                    help="append every received payload to received/bag_<ts>.jsonl")
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    if args.record:
        os.makedirs(RECEIVED, exist_ok=True)
        bag_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        BAG["path"] = os.path.join(RECEIVED, "bag_%s.jsonl" % bag_stamp)
        print("recording ->", os.path.relpath(BAG["path"], HERE))

    os.makedirs(RECEIVED, exist_ok=True)

    if args.restore:
        load_state()
    else:
        stale = count_stale()
        if stale:
            print(f"[{stamp()}] GS-1  starting clean - {stale} frames from a previous "
                  f"session were NOT loaded (pass --restore to bring them back)", flush=True)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[{stamp()}] GS-1  ground station listening on http://{args.host}:{args.port}", flush=True)
    print(f"[{stamp()}] GS-1  dashboard  →  http://localhost:{args.port}", flush=True)
    print(f"[{stamp()}] GS-1  satellite should point at  http://<this-ip>:{args.port}/ingest", flush=True)
    if STATE["frames"]:
        print(f"[{stamp()}] GS-1  {len(STATE['frames'])} frames restored from received/feed.json")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n" + f"[{stamp()}] GS-1  shutdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
