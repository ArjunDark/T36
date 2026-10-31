# Setup — two Windows laptops

Everything from a clean machine to a running pass. About fifteen minutes if the
network behaves.

**Read this first:** both machines need the **whole repository**, not selected
folders. The ground station loads `tinyml\model_int8.onnx` for verification, and
the satellite loads `dataset\` and `tools\` from beside it. Copying folders
around is the most common way to break the install.

Every command below is for **Command Prompt** (`cmd`) or **PowerShell** on
Windows. There is no Linux in this document.

---

## 0. Which Python you are using

This trips up almost everyone. `py` runs the **newest** Python on the machine,
which is usually *not* the one you installed packages into.

See what you have:

```
py -0p
```

That is a **zero**, not the letter O. It lists every interpreter with its path:

```
 -V:3.15 *        C:\Users\arjun\AppData\Local\Python\pythoncore-3.15-64\python.exe
 -V:3.12          C:\Users\arjun\AppData\Local\Programs\Python\Python312\python.exe
```

**You want 3.12** (3.11 to 3.14 all work). The `*` marks the default — if it is
on 3.15, then plain `py` will not have onnxruntime, because onnxruntime has no
build for 3.15 yet.

Everything below writes `py -3.12`. If your 3.12 is a different version number,
substitute it.

---

## 1. Both laptops — get the code

Download the release zip from GitHub (**Releases → v3.5.0 → Source code (zip)**)
and extract it somewhere simple, for example:

```
C:\AllAtOnce
```

Avoid `C:\Windows\System32` and avoid a path with spaces. If you extract from
the browser you will get a folder named `AllAtOnce-main` inside another
`AllAtOnce-main` — open folders until you see `satellite`, `ground`, `tinyml`,
`dataset`, `tools` at the same level. That is the repo root.

Then:

```
cd /d C:\AllAtOnce
dir
```

You should see `satellite`, `ground`, `tinyml`, `dataset`, `tools`, `SETUP.md`.

---

## 2. Both laptops — the environment

```
cd /d C:\AllAtOnce
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install numpy opencv-python-headless onnx onnxruntime
```

The prompt changes to `(.venv)` at the start of the line. That prefix is how you
know the environment is active.

Verify before going further:

```
python tools\doctor.py
```

It checks the interpreter, whether the venv is active, all four packages, the
model file, every folder, the config, and whether the model actually loads — and
prints the exact fix for anything wrong. If it ends with **Ready**, the hard part
is over.

Or the short version:

```
python -c "import cv2, numpy, onnxruntime; print('deps ok')"
```

Note this line says `python`, not `py -3.12` — once the venv is active, `python`
already points at 3.12.

**Inside an activated venv, always use plain `python` — never `py -3.12`.**
The `py` launcher resolves the *system* interpreter by version tag and ignores
the venv, so `py -3.12 -m pip install` puts packages outside your environment
and the very next `python -c "import cv2"` fails. If you see

```
Defaulting to user installation because normal site-packages is not writeable
```

that is the giveaway: it went to the wrong place. Drop the `py -3.12`.

**The import name and the package name are not the same thing.** You import
`cv2`; you install `opencv-python-headless`. `pip install cv2` will always fail.

**A new terminal does not remember the venv.** Every time you open one:

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
```

---

## 3. Ground laptop

Find its address:

```
ipconfig
```

Look for the **IPv4 Address** under your Wi-Fi or Ethernet adapter — something
like `192.168.1.42`. Not the one under a VPN adapter.

Start the station:

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
cd ground
python server.py --port 8000 --record
```

Windows will pop up a firewall dialog the first time. **Allow access on Private
networks.** If you dismiss it, the satellite will never connect — this is the
single most common reason a demo fails.

If you missed the dialog, add the rule by hand in an **Administrator** prompt:

```
netsh advfirewall firewall add rule name="AllAtOnce ground" dir=in action=allow protocol=TCP localport=8000
```

Leave this window running.

---

## 4. Satellite laptop

Open `satellite\config.demo.json` in Notepad and put the ground laptop's address
in it:

```json
"ground": { "host": "192.168.1.42", "port": 8000 }
```

Test the link **before starting anything else**:

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
python tools\check_link.py --host 192.168.1.42
```

It must print `link : OK`. If it does not, it is the IP or the firewall —
nothing downstream can fix it, so sort it out now.

Then start the satellite:

```
cd satellite
python sat.py --config config.demo.json
```

You will see the status line and a pass countdown.

---

## 5. Run a pass

That is all of it. The satellite feeds itself:

```
[08:50:01] SYS  auto-feed on — drawing 2 frame(s) every 4s from dataset/tiles (18 images)
[08:50:01] SYS  inbox is topped up automatically — you do not need to run anything else
```

**On the satellite laptop**, open the onboard console:

```
http://localhost:8001
```

That is the spacecraft's own view — the SMART-TRIAGE console with six tabs:

| tab | what it shows |
| --- | --- |
| **Mission Control** | Earth, the capture → analysis chain, live feed, scene analysis, queue, telemetry |
| **Image Intelligence** | every captured frame as a grid, plus the model output for the selected one |
| **Transmission Queue** | the full manifest, sortable, with per-frame status |
| **Downlink Optimizer** | the knapsack selection against the pass budget, with throughput chart |
| **Model Performance** | connector, frames scored, latency chart, mean score per class |
| **Simulation** | pipeline configuration and the live trace |

`?view=intel` (or queue, downlink, model, sim) deep-links straight to a tab.
It shows what the satellite knows. It cannot show what the ground has received,
because the satellite cannot see the ground.

**On the ground laptop**, open the browser to:

```
http://localhost:8000/?phase=2
```

The `?phase=2` starts it already listening. The dashboard stays dark until frames
arrive — that is the point. The satellite captures for 25 seconds while the
ground shows nothing, then the window opens and frames come down. The satellite
keeps capturing throughout, so you will see the queue and `sent` climbing at the
same time.

---

## 6. Before you present

Run the scorecard and have the numbers in your head:

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
python tools\benchmark.py --set tiles --limit 18
```

It ends with a criteria block:

```
 JUDGING CRITERIA
   RAM compression        3.24x        PASS (1.42 MB vs 4.59 MB)
   Flash compression      3.19x        PASS (1.34 MB vs 4.28 MB)
   Accuracy retention     not measured n/a  - needs the FP32 reference
   Bandwidth reduction    98.4 %       PASS (bar: >= 80%)
   Peak RAM < envelope    1.42 MB      PASS (envelope 4.2 MB)
   Pass fits the window   3.9 s        PASS (600 s window)
   Live responsiveness    4 ms/frame   PASS (244 frames/s)
```

To fill in accuracy retention, export `base_fp32.onnx` from the training notebook
(cell 10), then either copy it to `tinyml\model_fp32.onnx` or point at it:

```
python tools\benchmark.py --set eurosat --fp32 C:\path\to\base_fp32.onnx
```

**Test the one-laptop fallback once**, so you know it works if the Wi-Fi dies:

```
REM terminal 1
cd /d C:\AllAtOnce && .venv\Scripts\activate && cd ground && python server.py --port 8000

REM terminal 2
cd /d C:\AllAtOnce && .venv\Scripts\activate && cd satellite && python sat.py --config config.demo.json
```

---

## 7. Replay a recorded pass

If the live demo misbehaves in front of judges, play back a good one. The
`--record` flag on the ground server wrote every payload to
`ground\received\bag_<timestamp>.jsonl`.

```
dir ground\received\bag_*.jsonl
python tools\bag.py info ground\received\bag_20261031_080739.jsonl
python tools\bag.py replay ground\received\bag_20261031_080739.jsonl --url http://127.0.0.1:8000/ingest
```

---

## 8. About throttling the link

`tools\shape_link.sh` uses `tc`, which is **Linux only**. It will not run on
Windows. Do not try.

The satellite already paces itself in software — it computes `size / bytes_per_second`
and waits that long before sending the next frame, so frames arrive at the link
rate regardless of your LAN speed. That is the honest, portable behaviour.

If you want the operating system itself to be slow, the options are:

1. **WSL2** on the satellite laptop, with the ground server inside it and `tc`
   shaping the WSL interface. Closest to the real thing, most setup.
2. **Clumsy** (open source, <https://jagt.github.io/clumsy/>) — injects lag and
   packet loss on Windows without a reboot. Not a rate limit, but it gives you
   the latency character.

If you use neither, say *"we pace at the application layer to model the link
budget"* and do not claim the OS is throttled.

---

## Troubleshooting

| symptom | cause |
| --- | --- |
| `'py' is not recognized` | Python not installed with the launcher — reinstall from python.org and tick "py launcher" |
| `py -3.12` not found | check `py -0p`; your 3.12 may be a different version number |
| `No module named cv2` | venv not activated in this window |
| `pip` refuses: externally managed | you are outside the venv — `.venv\Scripts\activate` |
| **model did not load** | onnxruntime installed for a different Python. Activate the venv, then `python -m pip install onnxruntime` |
| `pip install cv2` fails | the package is `opencv-python-headless`; `cv2` is only the import name |
| `Defaulting to user installation` | you used `py -3.12 -m pip` inside the venv — use `python -m pip` |
| `check_link` times out | firewall — see the `netsh` rule in section 3 |
| `check_link` connection refused | ground server not running, or wrong port |
| dashboard fills with no satellite | old frames restored — see below |
| `verification model missing` | `tinyml\` is not beside `ground\` — extract the whole repo |
| `push failed — Connection refused` | the ground server died; restart it, queued frames retry next pass |
| `degraded … to alert` on every frame | pass budget too small for full crops; raise `pass_length_s` in the config |

---

## A note on `ground\received\`

The ground station writes everything it receives into `ground\received\`: the
thumbnails (`*_raw.jpg`, `*_int8.jpg`), `feed.json` with the last session's
frames, and any bags if you ran with `--record`.

**On startup the station begins clean.** If a previous session left frames
behind, it says so and ignores them:

```
[08:35:04] GS-1  starting clean - 2 frames from a previous session were NOT
                  loaded (pass --restore to bring them back)
```

That is why the dashboard is empty when you start the ground station alone — it
should be. To bring the previous session back, add `--restore`.

To wipe everything and start completely fresh:

```
del /q ground\received\*.jpg ground\received\feed.json ground\received\*.jsonl
```

If you see frames with no satellite running **and no such startup line**, then
something really is posting to `/ingest`. Check for a second terminal with
`sat.py` still running:

```
tasklist | findstr python
```

---

## The two screens

| | Satellite laptop | Ground laptop |
| --- | --- | --- |
| **open** | `http://localhost:8001` | `http://localhost:8000/?phase=2` |
| **what it is** | the onboard console — SMART-TRIAGE, Earth, chain, PSRAM, storage, queue | the received view — one image, telemetry, frame strip, log |
| **shows** | what the spacecraft captured and decided | what came down the link |
| **sees the other side?** | no | only what was transmitted |
| runs | `satellite\sat.py` | `ground\server.py` |

The asymmetry is the demonstration. The satellite console can show sixteen frames
queued while the ground view is still empty — same moment, two machines.

The satellite console is reachable only from the satellite laptop
(`127.0.0.1`). The ground cannot open it. Use `--web-port` to change the port,
or `--no-web` to run terminal-only.
