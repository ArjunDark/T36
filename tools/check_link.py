#!/usr/bin/env python3
"""
check_link.py — can the satellite reach the ground?

    python3 tools/check_link.py --host 192.168.1.42 --port 8000

Sends a synthetic frame to POST /ingest and reports the round trip. Use it before
a full pass: a link that fails here will fail silently at 3 a.m. when the queue
is full.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description="test the ground link")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"

    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            print(f"health   : {r.status} {json.loads(r.read())}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"health   : FAILED — {exc}", file=sys.stderr)
        return 1

    payload = {
        "station": "SAT-1", "seq": 9999,
        "ts": "2026-01-01T00:00:00+00:00",
        "f": {"i": "LINKTEST_9999", "t": "linktest", "b": 1024, "q": 0.9,
              "r": 50.0, "v": 50.0, "p": 50.0, "e": 50.0,
              "tr": "", "tt": "", "fe": {"c": 0, "e": 0, "h": 0}},
    }
    body = json.dumps(payload).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(base + "/ingest", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            dt = (time.time() - t0) * 1000
            print(f"ingest   : {r.status} in {dt:.0f} ms — {r.read().decode()}")
    except (urllib.error.URLError, OSError) as exc:
        print(f"ingest   : FAILED — {exc}", file=sys.stderr)
        return 1

    print(f"link     : OK  ({base})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
