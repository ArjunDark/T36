#!/usr/bin/env python3
"""
feed_inbox.py — stage images from the dataset into the satellite's inbox.

    python3 tools/feed_inbox.py                 # 5 tiles, random
    python3 tools/feed_inbox.py --count 10      # more
    python3 tools/feed_inbox.py --tile pivot    # one specific tile
    python3 tools/feed_inbox.py --watch 4       # one every 4 s, like a capture cadence

Copying files is how the operator feeds this station for now: there is no camera
and no dedicated UI on the satellite laptop.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "dataset")
INBOX = os.path.join(ROOT, "satellite", "inbox")

# every set under dataset/ that holds images, plus the balanced EuroSAT subset
SETS = {
    "tiles": os.path.join(DATASET, "tiles"),
    "eurosat": os.path.join(DATASET, "eurosat"),
    "eurosat_full": os.path.join(DATASET, "eurosat_full"),
    "sentinel2": os.path.join(DATASET, "sentinel2"),
}


def images_in(root):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="stage tiles into the satellite inbox")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--tile", help="specific tile id (filename without extension)")
    ap.add_argument("--set", default="tiles",
                    choices=sorted(SETS) + ["all"],
                    help="which dataset to draw from")
    ap.add_argument("--watch", type=float, default=0,
                    help="seconds between drops, to mimic a capture cadence")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(INBOX, exist_ok=True)

    roots = list(SETS.values()) if args.set == "all" else [SETS[args.set]]
    available = []
    for r in roots:
        if os.path.isdir(r):
            available += images_in(r)
    if not available:
        print("no images found for set '%s'" % args.set, file=sys.stderr)
        print("available sets:", ", ".join(sorted(SETS)), file=sys.stderr)
        return 1

    if args.tile:
        matches = [a for a in available if os.path.splitext(os.path.basename(a))[0] == args.tile]
        if not matches:
            print(f"no such tile: {args.tile}", file=sys.stderr)
            return 1
        picks = [matches[0]] * args.count
    else:
        if args.seed is not None:
            random.seed(args.seed)
        picks = [random.choice(available) for _ in range(args.count)]

    stamp = int(time.time())
    for i, src in enumerate(picks):
        # unique name per drop so the watcher treats each as a new capture
        dst = os.path.join(INBOX, f"{stamp}_{i:03d}_{os.path.basename(src)}")
        shutil.copy(src, dst)
        print(f"→ {dst}")
        if args.watch:
            time.sleep(args.watch)

    print(f"staged {len(picks)} frame(s) in {INBOX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
