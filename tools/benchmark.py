#!/usr/bin/env python3
"""
benchmark.py - the scorecard the judging criteria ask for.

Runs the real pipeline offline over a labelled set and reports, in one table:

  * bandwidth reduction   raw capture bytes vs bytes actually transmitted
  * flash compression     INT8 on disk vs the FP32 equivalent of the same weights
  * working RAM           peak activation + weights against the 4.2 MB envelope
  * accuracy              INT8 top-1 on labelled data, with the FP32 baseline
  * triage behaviour      how many frames were discarded, alerted, queued
  * pass capacity         what one 10-minute 256 kbit/s pass can carry

    python3 tools/benchmark.py
    python3 tools/benchmark.py --set eurosat --limit 200
    python3 tools/benchmark.py --config satellite/config.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

try:
    import cv2
except ImportError:
    sys.stderr.write(
        "\n  OpenCV is missing for this interpreter.\n"
        "  python : %s\n"
        "  version: %s\n\n"
        "  Install it into THIS interpreter:\n"
        "      %s -m pip install opencv-python-headless onnx onnxruntime\n\n"
        "  On Windows, 'py' picks the newest Python, which may not be the one\n"
        "  you installed into. Name it explicitly: py -3.12 -m pip install ...\n\n"
        % (sys.executable, sys.version.split()[0], sys.executable))
    raise SystemExit(2)

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "satellite"))

from pipeline import ingest, preprocess, scoring      # noqa: E402

CLASSES = scoring.CLASSES


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def images_in(root, limit):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                out.append(os.path.join(dirpath, f))
    out.sort()
    return out[:limit] if limit else out


def main() -> int:
    ap = argparse.ArgumentParser(description="judging scorecard")
    ap.add_argument("--config", default=os.path.join(ROOT, "satellite", "config.json"))
    ap.add_argument("--set", default="eurosat")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--fp32", default=None,
                    help="FP32 ONNX reference for accuracy retention "
                         "(default: auto-detect tinyml/model_fp32.onnx)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    policy = cfg.get("policy") or scoring.DEFAULT_POLICY
    link = cfg["downlink"]

    ingress = ingest.CubeSatIngressModule(cfg["sram_limit_mb"], cfg["psram_slots"],
                                         cfg["tensor_res"])
    registry = scoring.build_registry(os.path.join(ROOT, "tinyml"))
    adapter = registry.adapter
    if adapter is None:
        sys.stderr.write(
            "\n  The model did not load.\n\n"
            "  python : %s\n"
            "  version: %s\n\n"
            "  The usual cause is that onnxruntime is installed for a different\n"
            "  Python than the one running this script. Check both:\n\n"
            "      %s -m pip show onnxruntime\n"
            "      %s -m pip install onnxruntime opencv-python-headless onnx\n\n"
            "  On Windows, 'py' runs the newest Python. If you installed into\n"
            "  3.12, run this with:  py -3.12 tools\\benchmark.py\n\n"
            % (sys.executable, sys.version.split()[0], sys.executable, sys.executable))
        return 1

    root = os.path.join(ROOT, "dataset", args.set)
    files = images_in(root, args.limit)
    if not files:
        print("no images under", root, file=sys.stderr)
        return 1

    novelty = scoring.Novelty()
    actions = {"discard": 0, "hold": 0, "alert": 0, "queue_crop": 0}
    raw_bytes = tx_bytes = 0
    correct = total = 0
    peak_act = 0
    per_class = {}
    latencies = []
    labels = []          # (tensor, true class) for the FP32 comparison

    thumb_px = link["thumbnail_px"]
    thumb_q = link["thumbnail_quality"] / 100

    for path in files:
        try:
            result = ingress.run(path)
        except Exception:
            continue
        tensor = result["tensor"]
        packet = result.get("psram_reference") or {}
        feats = preprocess.features(tensor)

        t_infer = time.perf_counter()
        out = registry.infer(feats, {"tile": os.path.basename(path)}, tensor)
        latencies.append((time.perf_counter() - t_infer) * 1000.0)

        nov, _src = novelty.score(os.path.basename(path), out.get("embedding") or [])
        tri = scoring.triage(out, policy, nov)
        if tri is None:
            continue
        novelty.observe(os.path.basename(path), out.get("embedding") or [],
                        tri["p_cloud"] <= 0.5)

        actions[tri["action"]] = actions.get(tri["action"], 0) + 1
        peak_act = max(peak_act, out.get("activation_bytes", 0))

        # what the frame costs on the wire
        h, w = packet["raw_data"].shape[:2]
        raw_bytes += w * h * 3
        if tri["action"] == "discard":
            tx = 0
        elif tri["action"] == "alert":
            tx = 226                      # measured JSON alert, see the alert block
        else:
            small = cv2.resize(packet["raw_data"], (thumb_px, thumb_px),
                               interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                                   [cv2.IMWRITE_JPEG_QUALITY, int(thumb_q * 100)])
            tx = len(buf) + 420           # thumbnail + verdict envelope
        tx_bytes += tx

        # accuracy, where the folder name is the label
        cls = os.path.basename(os.path.dirname(path))
        if cls in CLASSES:
            total += 1
            hit = int(tri["cls"] == cls)
            correct += hit
            per_class.setdefault(cls, [0, 0])
            per_class[cls][0] += hit
            per_class[cls][1] += 1
            labels.append((tensor, cls))

    if not files:
        return 1

    flash = os.path.getsize(os.path.join(ROOT, "tinyml", "model_int8.onnx"))
    import onnx
    m = onnx.load(os.path.join(ROOT, "tinyml", "model_int8.onnx"))
    params = sum(int(np.prod(i.dims)) for i in m.graph.initializer if i.dims)
    fp32_bytes = params * 4

    # ---- accuracy retention: needs a real FP32 reference -------------------
    fp32_path = args.fp32 or os.path.join(ROOT, "tinyml", "model_fp32.onnx")
    fp32_acc = None
    fp32_note = ""
    if labels and os.path.exists(fp32_path):
        try:
            import onnxruntime as ort
            fs = ort.InferenceSession(fp32_path, providers=["CPUExecutionProvider"])
            iname = fs.get_inputs()[0].name
            hits = 0
            for tensor, truth in labels:
                rgb = preprocess.dequantise(tensor).astype(np.float32) / 255.0
                x = np.transpose(rgb, (2, 0, 1))[None]
                o = fs.run(None, {iname: x})
                named = {d.name: v for d, v in zip(fs.get_outputs(), o)}
                logits = named["class_logits"][0]
                hits += int(CLASSES[int(np.argmax(logits))] == truth)
            fp32_acc = 100.0 * hits / len(labels)
        except Exception as exc:                       # noqa: BLE001
            fp32_note = "FP32 reference could not run: %s" % exc
    elif labels:
        fp32_note = ("no tinyml/model_fp32.onnx — export it from the training "
                     "notebook (cell 10) or pass --fp32 <path>")

    int8_acc = 100.0 * correct / total if total else None
    retention = (fp32_acc - int8_acc) if (fp32_acc is not None and int8_acc is not None) else None

    reduction = 100.0 * (1 - tx_bytes / raw_bytes) if raw_bytes else 0
    act_elems = peak_act / 4 if peak_act else 0          # onnxruntime activations are float32
    ram_int8 = flash + act_elems
    ram_fp32 = fp32_bytes + peak_act
    ram_ratio = (ram_fp32 / ram_int8) if ram_int8 else 0
    sram = cfg["sram_limit_mb"] * 1024 * 1024
    pass_bytes = link["kbps"] * 1000 / 8 * link["pass_length_s"]

    med_lat = statistics.median(latencies) if latencies else 0.0
    p95_lat = (statistics.quantiles(latencies, n=20)[-1] if len(latencies) >= 20
               else max(latencies or [0]))
    fps = 1000.0 / med_lat if med_lat else 0
    drain_s = (tx_bytes / (link["kbps"] * 1000 / 8)) if tx_bytes else 0
    fits_pass = drain_s <= link["pass_length_s"]

    W = 66
    print()
    print("=" * W)
    print(" ALLATONCE - judging scorecard")
    print("=" * W)
    print(" config      : %s" % os.path.relpath(args.config, ROOT))
    print(" frames      : %d from dataset/%s" % (len(files), args.set))
    print()
    print(" TRIAGE BEHAVIOUR")
    for k in ("discard", "alert", "queue_crop", "hold"):
        pct = 100.0 * actions[k] / max(1, sum(actions.values()))
        print("   %-12s %4d  (%4.1f%%)" % (k, actions[k], pct))
    print()
    print(" BANDWIDTH")
    print("   raw capture      %10.2f MB" % (raw_bytes / 1e6))
    print("   transmitted      %10.2f MB" % (tx_bytes / 1e6))
    print("   per frame avg    %10.0f bytes" % (tx_bytes / max(1, len(files))))
    print()
    print(" FLASH")
    print("   INT8 on disk     %10.2f MB" % (flash / 1e6))
    print("   FP32 equivalent  %10.2f MB  (%d params x 4 B)" % (fp32_bytes / 1e6, params))
    print()
    print(" WORKING RAM  (envelope %.1f MB)" % cfg["sram_limit_mb"])
    print("   activations      %10.0f elements" % act_elems)
    print("   INT8  weights+act%10.3f MB" % (ram_int8 / 1e6))
    print("   FP32  weights+act%10.3f MB" % (ram_fp32 / 1e6))
    if total:
        print(" ACCURACY  (%d labelled frames)" % total)
        print("   INT8 top-1       %10.1f %%" % int8_acc)
        if fp32_acc is not None:
            print("   FP32 top-1       %10.1f %%" % fp32_acc)
            print("   drop             %10.2f pts" % retention)
        else:
            print("   FP32 baseline    not measured")
            print("                    %s" % fp32_note)
    print()
    print(" PASS SIMULATION  (%.0f kbit/s, %.0f s window)" % (link["kbps"], link["pass_length_s"]))
    print("   payload budget   %10.2f MB" % (pass_bytes / 1e6))
    print("   this run needs   %10.1f s of link" % drain_s)
    print("   latency median   %10.1f ms/frame   (p95 %.1f)" % (med_lat, p95_lat))
    print("   throughput       %10.0f frames/s" % fps)
    print()
    print("=" * W)
    print(" JUDGING CRITERIA")
    print("=" * W)

    def row(name, value, ok, note=""):
        mark = "PASS" if ok else ("n/a " if ok is None else "FAIL")
        print("   %-22s %-18s %s %s" % (name, value, mark, note))

    row("RAM compression", "%.2fx" % ram_ratio, ram_ratio > 1.0,
        "(%.2f MB vs %.2f MB)" % (ram_int8 / 1e6, ram_fp32 / 1e6))
    row("Flash compression", "%.2fx" % (fp32_bytes / flash), (fp32_bytes / flash) > 1.0,
        "(%.2f MB vs %.2f MB)" % (flash / 1e6, fp32_bytes / 1e6))
    if retention is None:
        row("Accuracy retention", "not measured", None, "- needs the FP32 reference")
    else:
        row("Accuracy retention", "%.2f pts drop" % retention, retention < 2.0,
            "(INT8 %.1f%%, FP32 %.1f%%)" % (int8_acc, fp32_acc))
    row("Bandwidth reduction", "%.1f %%" % reduction, reduction >= 80.0, "(bar: >= 80%)")
    row("Peak RAM < envelope", "%.2f MB" % (ram_int8 / 1e6), ram_int8 < sram,
        "(envelope %.1f MB)" % cfg["sram_limit_mb"])
    row("Pass fits the window", "%.1f s" % drain_s, fits_pass,
        "(window %.0f s)" % link["pass_length_s"])
    row("Live responsiveness", "%.0f ms/frame" % med_lat, med_lat < 100.0,
        "(%.0f frames/s)" % fps)
    print()
    print("=" * W)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
