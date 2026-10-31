#!/usr/bin/env bash
# =====================================================================
# shape_link.sh - make the LAN behave like a satellite downlink
# ---------------------------------------------------------------------
# Pace alone is a software illusion: the sender sleeps, but the OS still
# moves the packets at gigabit speed. This shapes the interface itself so
# the link is genuinely slow, and adds the latency and loss a real pass has.
#
#   sudo ./tools/shape_link.sh apply  <iface> [kbit] [delay_ms] [loss_pct]
#   sudo ./tools/shape_link.sh status <iface>
#   sudo ./tools/shape_link.sh clear  <iface>
#
# Example, matching the brief's S-band budget:
#   sudo ./tools/shape_link.sh apply eth0 256 600 1
#
# Linux only (tc is part of iproute2). On Windows use the notes below.
# =====================================================================
set -euo pipefail

ACTION="${1:-status}"
IFACE="${2:-}"
RATE="${3:-256}"
DELAY="${4:-600}"
LOSS="${5:-1}"

if [[ -z "$IFACE" ]]; then
  echo "usage: $0 {apply|status|clear} <iface> [kbit] [delay_ms] [loss_pct]" >&2
  echo "interfaces:" >&2
  ip -o link show | awk -F': ' '{print "  " $2}' >&2
  exit 1
fi

case "$ACTION" in
  apply)
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    # tbf: token bucket, the rate ceiling.  netem: delay, jitter and loss.
    tc qdisc add dev "$IFACE" root handle 1: tbf rate "${RATE}kbit" burst 32kbit latency 400ms
    tc qdisc add dev "$IFACE" parent 1:1 handle 10: netem delay "${DELAY}ms" 40ms loss "${LOSS}%"
    echo "shaped $IFACE -> ${RATE} kbit/s, ${DELAY} ms delay, ${LOSS}% loss"
    ;;
  status)
    tc -s qdisc show dev "$IFACE"
    ;;
  clear)
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    echo "cleared $IFACE"
    ;;
  *)
    echo "unknown action: $ACTION" >&2; exit 1;;
esac
