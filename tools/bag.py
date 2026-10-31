#!/usr/bin/env python3
"""
bag.py - record a pass, replay it. The rosbag idea without the middleware.

Why this exists: a live demo has one chance. If the LAN misbehaves in front of
judges, you should be able to play a known-good pass back into the ground
station and keep talking.

Recording happens on the ground station (it already receives everything):

    python ground/server.py --port 8000 --record

Every /ingest payload is appended to ground/received/bag_<timestamp>.jsonl, one
JSON object per line, in arrival order.

Replaying pushes those payloads back into a ground station:

    python tools/bag.py replay ground/received/bag_20261031_071500.jsonl \
        --url http://127.0.0.1:8000/ingest

    --speed 1     original timing (default)
    --speed 10    ten times faster
    --speed 0     as fast as the socket allows

    python tools/bag.py info ground/received/bag_....jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def read_bag(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def cmd_info(args):
    rows = read_bag(args.bag)
    if not rows:
        print("empty bag")
        return 1

    kinds = {}
    total = 0
    for r in rows:
        k = r.get("kind") or "crop"
        kinds[k] = kinds.get(k, 0) + 1
        total += len(json.dumps(r))

    first = rows[0].get("ts")
    last = rows[-1].get("ts")
    print("bag        : %s" % os.path.basename(args.bag))
    print("payloads   : %d" % len(rows))
    print("wire bytes : %.1f kB" % (total / 1024))
    print("window     : %s -> %s" % (first, last))
    for k, v in sorted(kinds.items()):
        print("  %-8s %d" % (k, v))

    # rough duration from the sequence numbers, since wall-clock is not stored
    seqs = [r.get("seq") for r in rows if isinstance(r.get("seq"), int)]
    if len(seqs) > 1:
        print("seq range  : %d -> %d" % (min(seqs), max(seqs)))
    return 0


def cmd_replay(args):
    rows = read_bag(args.bag)
    if not rows:
        print("empty bag", file=sys.stderr)
        return 1

    speed = max(0.0, float(args.speed))
    sent = failed = 0
    t0 = time.time()
    prev = None

    print("replaying %d payloads into %s at speed %s" % (
        len(rows), args.url, "max" if speed == 0 else speed))

    for i, row in enumerate(rows):
        if speed > 0 and prev is not None:
            # no wall-clock in the bag, so pace on a fixed cadence scaled by speed
            time.sleep(max(0.0, args.interval / speed))
        prev = row

        body = json.dumps(row).encode("utf-8")
        req = urllib.request.Request(args.url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= resp.status < 300:
                    sent += 1
                else:
                    failed += 1
        except (urllib.error.URLError, OSError) as exc:
            failed += 1
            print("  failed: %s" % exc, file=sys.stderr)

        if (i + 1) % 10 == 0 or i + 1 == len(rows):
            print("  %d/%d" % (i + 1, len(rows)))

    dt = time.time() - t0
    print("done: %d sent, %d failed in %.1f s" % (sent, failed, dt))
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="record and replay a downlink pass")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="summarise a bag")
    p_info.add_argument("bag")
    p_info.set_defaults(func=cmd_info)

    p_rep = sub.add_parser("replay", help="push a bag into a ground station")
    p_rep.add_argument("bag")
    p_rep.add_argument("--url", default="http://127.0.0.1:8000/ingest")
    p_rep.add_argument("--speed", default="1",
                       help="1 = original cadence, 10 = faster, 0 = as fast as possible")
    p_rep.add_argument("--interval", type=float, default=0.5,
                       help="seconds between payloads at speed 1")
    p_rep.set_defaults(func=cmd_replay)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
