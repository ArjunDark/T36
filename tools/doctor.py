#!/usr/bin/env python3
"""
doctor.py - check the install before you waste time on a demo.

    python tools\\doctor.py

Prints one line per check and a verdict at the end. Run it from the repo root,
with the virtual environment activated.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK, BAD, WARN = "  ok  ", " FAIL ", " warn "

problems = []
warnings = []


def line(status, label, detail=""):
    print("[%s] %-28s %s" % (status, label, detail))


def main() -> int:
    print()
    print("AllAtOnce doctor")
    print("-" * 62)

    # ---- interpreter -------------------------------------------------
    in_venv = sys.prefix != sys.base_prefix
    ver_ok = sys.version_info >= (3, 11)
    line(OK if ver_ok else BAD, "interpreter",
         "%s  %s" % (sys.version.split()[0], sys.executable))
    if in_venv:
        line(OK, "virtual environment", sys.prefix)
    else:
        line(BAD, "virtual environment", "not active")
        problems.append(
            "The venv is not active. Run:  .venv\\Scripts\\activate\n"
            "         If you used `py -3.12 -m pip install`, the packages went to the\n"
            "         system Python instead. Reinstall with `python -m pip install ...`\n"
            "         after activating.")

    if sys.version_info < (3, 11):
        problems.append("Python %d.%d is too old; onnxruntime needs 3.11 or newer."
                        % sys.version_info[:2])

    # ---- packages ----------------------------------------------------
    print()
    for mod, pkg in (("numpy", "numpy"),
                     ("cv2", "opencv-python-headless"),
                     ("onnxruntime", "onnxruntime"),
                     ("onnx", "onnx")):
        try:
            m = __import__(mod)
            v = getattr(m, "__version__", "?")
            line(OK, "import %s" % mod, v)
        except Exception as exc:                       # noqa: BLE001
            line(BAD, "import %s" % mod, str(exc)[:40])
            problems.append(
                "Missing %s. Install it into THIS interpreter:\n"
                "         python -m pip install %s\n"
                "         (the import name is `%s`; the package is `%s`)"
                % (mod, pkg, mod, pkg))

    # ---- files -------------------------------------------------------
    print()
    model = os.path.join(ROOT, "tinyml", "model_int8.onnx")
    if os.path.exists(model):
        line(OK, "model", "%.2f MB" % (os.path.getsize(model) / 1e6))
    else:
        line(BAD, "model", model)
        problems.append("tinyml\\model_int8.onnx is missing. Extract the whole repo, "
                        "not selected folders.")

    for rel in ("satellite", "ground", "tinyml", "dataset", "tools"):
        p = os.path.join(ROOT, rel)
        if os.path.isdir(p):
            n = sum(len(f) for _d, _s, f in os.walk(p))
            line(OK, "folder %s" % rel, "%d files" % n)
        else:
            line(BAD, "folder %s" % rel, "missing")
            problems.append("%s\\ is missing beside the others. Extract the whole repo." % rel)

    cfg = os.path.join(ROOT, "satellite", "config.demo.json")
    if os.path.exists(cfg):
        import json
        with open(cfg, encoding="utf-8") as fh:
            c = json.load(fh)
        host = c.get("ground", {}).get("host", "?")
        line(OK, "config", "ground %s:%s" % (host, c.get("ground", {}).get("port")))
        if host in ("127.0.0.1", "localhost"):
            line(WARN, "ground address", "localhost - fine for one laptop, wrong for two")
            warnings.append("satellite/config.demo.json still points at 127.0.0.1. "
                            "For two laptops put the ground machine's IP there.")
    else:
        line(BAD, "config", "satellite/config.demo.json missing")
        problems.append("satellite\\config.demo.json is missing.")

    # ---- the model actually loads -----------------------------------
    print()
    try:
        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "satellite"))
        from pipeline import scoring                     # noqa: E402
        reg = scoring.build_registry(os.path.join(ROOT, "tinyml"))
        if reg.adapter is not None:
            line(OK, "model loads", "%s, input %d px"
                 % (reg.adapter.id, reg.adapter.input_size))
        else:
            line(BAD, "model loads", "returned None")
            problems.append("The model did not load even though the file exists - "
                            "onnxruntime is probably from another Python.")
    except Exception as exc:                             # noqa: BLE001
        line(BAD, "model loads", str(exc)[:50])
        problems.append("Could not load the model: %s" % exc)

    # ---- verdict -----------------------------------------------------
    print()
    print("-" * 62)
    if problems:
        print(" %d problem(s):" % len(problems))
        for p in problems:
            print("   - " + p)
        print()
        return 1

    if warnings:
        print(" Ready, with %d warning(s):" % len(warnings))
        for w in warnings:
            print("   - " + w)
    else:
        print(" Ready.")
    print()
    print(" Next:")
    print("   ground laptop   :  cd ground    &&  python server.py --port 8000")
    print("   satellite laptop:  cd satellite &&  python sat.py --config config.demo.json")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
