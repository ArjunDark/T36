# The link — how the two laptops actually talk

Short answer to the question you asked: **the transport is real, the radio is
simulated.** The satellite really does open a TCP connection to the ground over
your LAN and really does send bytes. What is modelled in software is how many
bytes per second are allowed through, and when the window opens.

Here is the whole thing, in the order the bytes travel.

---

## 1. What actually happens on the wire

```
SATELLITE LAPTOP                                    GROUND LAPTOP
────────────────                                    ────────────
pipeline produces a payload (JSON)
        │
        │  HTTP POST /ingest                     python server.py --port 8000
        │  Content-Type: application/json                 │
        ├─────────────── TCP over your LAN ──────────────►│
        │                                                 │ saves thumbnails to
        │◄────────────── 200 OK ──────────────────────────┤ received/
        │                                                 │ appends to STATE
        │                                                 │
        │                                     browser polls GET /feed?since=N
        │                                                 │ every 900 ms
        │                                                 │
        │                                     POST /infer → re-runs the model
```

So there are three protocols in play:

| Layer | What it is | Where it comes from |
| --- | --- | --- |
| TCP/IP | reliable byte stream between the two laptops | the operating system |
| HTTP/1.1 | request-response framing, `POST /ingest`, `GET /feed` | Python's `http.server`, `urllib` |
| JSON | the payload itself — one object per frame | our code |

Nothing about that is fake. If you unplug the LAN cable, the satellite logs
`push failed` and retries next pass, exactly as it would with a real radio.

---

## 2. What is simulated, and why

Two things are modelled rather than physical:

**The rate.** A real 256 kbit/s S-band downlink moves 32,000 bytes per second.
On a LAN you have 1 Gbit/s, so without a model every frame would arrive
instantly and the whole demonstration would be pointless. The sender therefore
paces itself: it computes `size / bytes_per_second` and sleeps for that long
before posting the next frame. One frame occupies the link for its full
transmission time.

**The window.** A satellite is only above the horizon for part of each orbit. The
`PassClock` models that: 25 seconds open, 25 seconds closed, repeating. Outside
the window the sender does nothing at all.

---

## 3. How slow the link really is

Software pacing is an illusion: the sender sleeps, but the operating system still
moves packets at gigabit speed. That is fine for the demo — frames arrive at the
modelled rate — but it means the *interface* is not actually throttled.

On **Windows**, which is what this project is set up for, the practical options
are:

1. **Software pacing (default, already running).** The sender computes
   `size / bytes_per_second` and waits before posting the next frame. Portable,
   honest, needs nothing installed. Say *"we pace at the application layer to
   model the link budget."*
2. **Clumsy** (open source, <https://jagt.github.io/clumsy/>) — injects lag and
   packet loss on Windows without a reboot. Not a rate limit, but it gives you
   the latency character on screen.
3. **WSL2** — run the ground server inside WSL and shape that interface with
   `tc`. Closest to the real thing, most setup.

**Do not claim the OS is throttled on Windows unless you did one of 2 or 3.**

### Linux aside

On Linux you can throttle the interface itself. `tc` (traffic control) is part of
`iproute2`; `netem` is the qdisc that adds delay, jitter and loss.

```bash
sudo ./tools/shape_link.sh apply eth0 256 600 1
```

That applies a `tbf` token bucket (hard ceiling 256 kbit/s, 32 kbit burst) and
`netem` (600 ms one-way delay, ±40 ms jitter, 1% loss). Clear it with
`sudo ./tools/shape_link.sh clear eth0`.

**Why 600 ms?** A LEO satellite at 550 km is at least ~1,200 km away, typically
much further. Round-trip time to LEO is commonly quoted at 20–40 ms for the space
segment alone, plus internet routing. 600 ms one-way is pessimistic but it makes
the link's character obvious on screen — you can *see* the latency.

---

## 4. What a real satellite link looks like

For the viva, so you can answer "how would this differ on real hardware":

| Ours | Real spacecraft | Why |
| --- | --- | --- |
| HTTP over TCP | CCSDS Space Packet Protocol over a framed link | CCSDS is the international standard for spacecraft telemetry; TCP's retransmit model is too slow for a one-way radio link |
| JSON | CCSDS packets with a 6-byte primary header (APID, sequence count, length) | fixed headers parse in hardware |
| Rate paced in the app | the radio's symbol rate and modulation (e.g. BPSK at 256 kbit/s) | the limit is physical, not policy |
| No forward error correction | Reed-Solomon or LDPC coding, typically 1/2 rate | a 1/2-rate code means half the bits are parity — which is exactly why our link model reserves 15% overhead |
| Pass = a timer | orbital propagation, look angles, antenna pointing | the window is geometry |
| No retransmission | selective repeat with a long timeout, or none at all | a retransmit may not fit in the pass |

The 15% overhead we reserve in `LinkBudget` stands in for framing, FEC and
retransmits. That is the honest way to model it without implementing CCSDS.

---

## 5. The second compression round

There are two places compression happens, and the brief only names one.

**Onboard, before queueing** — the model decides what each frame is worth and
whether it costs an image at all: discard (0 bytes), alert (226 bytes),
crop (a 160 px JPEG).

**At the link, against the remaining budget** — this is the second round. Before
each transmission the sender asks how many bytes are left in the pass, and
degrades the payload until it fits:

| level | payload | typical size |
| --- | --- | --- |
| 0 | thumbnail + tensor preview | ~15 kB |
| 1 | thumbnail only | ~9 kB |
| 2 | coordinates and verdict, no pixels | ~400 B |

If not even level 2 fits, the frame is dropped when its priority is below the
floor, or held for the next pass. Nothing is silently lost.

This is why the satellite can keep capturing through a pass: the queue is
re-planned against the budget on every single transmission, so a burst of new
high-priority frames degrades the older ones rather than overflowing the link.

---

## 6. Running it across two laptops

**Ground laptop:**

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
cd ground
python server.py --port 8000
```

Note its IPv4 address from `ipconfig` — the Wi-Fi adapter, not a VPN one. Allow
the firewall prompt on Private networks.

**Satellite laptop:**

```
cd /d C:\AllAtOnce
.venv\Scripts\activate
```

Put the ground address in `satellite\config.demo.json`:

```json
"ground": { "host": "192.168.1.42", "port": 8000 }
```

Then:

```
python tools\check_link.py --host 192.168.1.42     REM must print link : OK
cd satellite
python sat.py --config config.demo.json
```

**Nothing else.** The satellite tops its own inbox up from `dataset\`; you do
not need `feed_inbox.py`.

The satellite captures for 25 seconds while the ground dashboard shows nothing.
Then the window opens and the frames start arriving. The satellite keeps
capturing throughout — you will see `QUEUE` rise while `sent` also rises.

---

## 7. Troubleshooting the link specifically

| symptom | meaning |
| --- | --- |
| `check_link` times out | firewall. Allow port 8000 on private networks on the ground laptop. |
| `check_link` connection refused | the ground server is not running, or the wrong port |
| `push failed — Connection refused` mid-run | the ground server died. Restart it; queued frames are retried. |
| `push failed — timed out` | `tc` delay is too aggressive, or Wi-Fi is dropping. Clear the shaping. |
| Frames arrive but the dashboard is empty | the browser is on the wrong machine, or the ground is still in PHASE 1 |
| `degraded … to alert` on every frame | the pass budget is too small for full crops. Raise `pass_length_s` or lower `min_priority`. |


---

## 8. Record and replay — demo insurance

A live demo has one chance. Record a good pass, replay it if the LAN misbehaves.

**Record** on the ground station:

```bash
python ground/server.py --port 8000 --record
```

Every received payload is appended to `ground/received/bag_<timestamp>.jsonl`,
one JSON object per line, in arrival order.

**Inspect** it:

```bash
python tools/bag.py info ground/received/bag_20261031_080739.jsonl
```

```
payloads   : 6
wire bytes : 131.2 kB
  crop     6
seq range  : 1 -> 6
```

**Replay** it back into a ground station:

```bash
python tools/bag.py replay ground/received/bag_....jsonl \
    --url http://127.0.0.1:8000/ingest --speed 0
```

`--speed 1` is the original cadence, `--speed 10` ten times faster, `--speed 0`
as fast as the socket allows.

This is the `rosbag2` idea — record the pass, replay it deterministically —
without running ROS. If a judge asks how you would reproduce a run, this is the
answer.

---

## 9. Why not ROS 2

ROS 2 is robotics middleware: many heterogeneous nodes, sensor drivers, TF
trees, real-time control loops. This system is two processes exchanging a few
JSON messages every 25 seconds.

What ROS 2 would add: DDS discovery over multicast, a `colcon` build system, and
on Arch a source build from the AUR. What it would not add: any improvement to
the four things the rubric scores — RAM, flash, accuracy retention, bandwidth.

The parts of the ROS world that *are* worth having are here already:

| ROS 2 gives you | We have |
| --- | --- |
| `rosbag2` record/replay | `ground/server.py --record` + `tools/bag.py` |
| `ros2 topic hz` | the satellite's `LINK` log lines, one per transmission |
| `rqt_graph` | the payload-chain strip across the top of the dashboard |
| QoS reliability profiles | the degradation ladder and the retry-next-pass rule |

If the visual node graph matters for judging, `rqt_graph` can be pointed at a
small ROS 2 bridge that republishes `/ingest` as a topic. That is an optional
extra, not a rebuild.
