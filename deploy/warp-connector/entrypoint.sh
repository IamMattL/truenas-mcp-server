#!/usr/bin/env bash
# Headless launcher for cloudflare-warp running as a Mesh node (connector).
#
# Sequence:
#   1. Validate required env. CONNECTOR_TOKEN is the only mandatory input —
#      generated when you "Add a node" in the CF Mesh dashboard.
#   2. Start warp-svc in the background. warp-cli talks to it over a unix
#      socket; if it isn't running, every cli call hangs.
#   3. Wait for warp-svc to accept cli traffic before issuing any command.
#      Without this poll the first `warp-cli` call races the daemon and
#      fails roughly half the time on cold start.
#   4. Register the connector if the persistent state volume doesn't already
#      hold a registration. The token is single-use per registration; once
#      state is persisted, subsequent restarts skip this step (and won't
#      consume a fresh token even if one is set).
#   5. Issue `warp-cli connect`. warp-svc owns reconnection from there.
#   6. Forward SIGTERM/SIGINT to a graceful disconnect, then wait on the
#      warp-svc process so the container exits when warp-svc does.
set -euo pipefail

if [ -z "${CONNECTOR_TOKEN:-}" ]; then
    echo "FATAL: CONNECTOR_TOKEN env var is required (Mesh node registration token from the CF dashboard)" >&2
    exit 1
fi

mkdir -p /var/run/cloudflare-warp

# warp-svc writes its log to stdout when run in foreground. Background it
# so the entrypoint can drive warp-cli, then `wait` on it at the end so
# the container's lifecycle tracks the daemon.
warp-svc &
SVC_PID=$!

# Poll until the daemon's unix socket answers. `warp-cli status` is cheap
# and returns non-zero until warp-svc is ready. Bound the wait at 30s so a
# permanently-broken daemon surfaces as a container exit rather than a
# silent hang.
for i in $(seq 1 30); do
    if warp-cli --accept-tos status >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "FATAL: warp-svc did not become ready within 30s" >&2
        kill "$SVC_PID" 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Idempotent registration. `registration show` returns 0 only when the
# state volume already holds a valid registration. If it does, skip the
# `connector new` call so a fresh token isn't required on every restart.
if ! warp-cli --accept-tos registration show >/dev/null 2>&1; then
    echo "Registering connector with the provided CONNECTOR_TOKEN..."
    warp-cli --accept-tos connector new "$CONNECTOR_TOKEN"
else
    echo "Existing registration found in /var/lib/cloudflare-warp; skipping connector new."
fi

warp-cli --accept-tos connect

# Graceful shutdown: tell warp-svc to disconnect (which cleans up the tun
# device and routes), then signal the daemon and wait for it.
shutdown() {
    echo "Received signal; disconnecting and stopping warp-svc..."
    warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
    kill -TERM "$SVC_PID" 2>/dev/null || true
}
trap shutdown SIGTERM SIGINT

wait "$SVC_PID"
