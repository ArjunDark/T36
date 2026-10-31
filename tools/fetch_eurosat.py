#!/usr/bin/env python3
"""
fetch_eurosat.py — get the full EuroSAT RGB set (27,000 images, 95 MB).

The repo ships a balanced subset (40 per class, 400 images) so the pipeline works
the moment you clone it. This pulls the rest.

    python3 tools/fetch_eurosat.py                # download and expand into dataset/eurosat_full/
    python3 tools/fetch_eurosat.py --subset 200   # 200 per class instead
    python3 tools/fetch_eurosat.py --keep-zip     # leave the archive behind

Source : https://zenodo.org/records/7711810/files/EuroSAT_RGB.zip
Licence: Copernicus Sentinel data, free and open (ESA). EuroSAT packaging by
         Helber et al., 2019. 10 classes, 64x64 RGB patches at 10 m.
"""

from __future__ import annotations

import argparse
import io
import os
import random
import sys
import urllib.request
import zipfile

URL = "https://zenodo.org/records/7711810/files/EuroSAT_RGB.zip"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_PATH = os.path.join(ROOT, "dataset", "_eurosat_rgb.zip")


def main() -> int:
    ap = argparse.ArgumentParser(description="download EuroSAT RGB")
    ap.add_argument("--subset", type=int, default=0,
                    help="images per class (0 = everything)")
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset", "eurosat_full"))
    ap.add_argument("--keep-zip", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(ZIP_PATH):
        print("downloading 95 MB from zenodo ...")
        os.makedirs(os.path.dirname(ZIP_PATH), exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as r, open(ZIP_PATH, "wb") as fh:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if total:
                    sys.stdout.write("\r  %3d%%  %.0f / %.0f MB" % (
                        100 * got / total, got / 1048576, total / 1048576))
                    sys.stdout.flush()
        print()

    z = zipfile.ZipFile(ZIP_PATH)
    names = [n for n in z.namelist() if n.lower().endswith(".jpg")]
    by_class: dict[str, list[str]] = {}
    for n in names:
        by_class.setdefault(n.split("/")[1], []).append(n)

    random.seed(0)
    written = 0
    for cls, items in sorted(by_class.items()):
        picks = sorted(items)
        if args.subset:
            random.shuffle(picks)
            picks = sorted(picks[:args.subset])
        d = os.path.join(args.out, cls)
        os.makedirs(d, exist_ok=True)
        for p in picks:
            with open(os.path.join(d, os.path.basename(p)), "wb") as fh:
                fh.write(z.read(p))
            written += 1
        print("  %-24s %4d" % (cls, len(picks)))

    if not args.keep_zip:
        os.remove(ZIP_PATH)
    print("wrote %d images to %s" % (written, args.out))
    print("point the satellite at them with:  python3 tools/feed_inbox.py --set eurosat_full")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
