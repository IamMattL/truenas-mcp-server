# Mesh Connector for the TrueNAS MCP Server

Headless Cloudflare Mesh node packaged for TrueNAS Custom Apps. Puts the
TrueNAS host on Cloudflare's Mesh network so the MCP server (running with
`MCP_TRANSPORT=http` on `localhost:8080`) is reachable from a Mesh-enrolled
client or, ultimately, a Cloudflare MCP Server Portal — no public hostname,
no port forward.

## Files

- `Dockerfile` — Debian Bookworm slim with `cloudflare-warp` baked in.
- `entrypoint.sh` — starts `warp-svc`, registers the connector if needed,
  issues `warp-cli connect`, forwards SIGTERM to a graceful disconnect.
- `docker-compose.yml` — TrueNAS Custom App definition (host network, NET_ADMIN, tun device passthrough, state volume).

## Prerequisites

1. **Mesh setup wizard** complete in the Cloudflare dashboard
   (`Networking → Mesh`). One-time per CF account.
2. **A node created** in the same dashboard. The wizard issues a connector
   token — keep it out of git, paste it directly into the TrueNAS UI as a
   secret env var.
3. **Host sysctls** on TrueNAS, set via *System Settings → Advanced →
   Sysctl* with "Apply on boot" enabled:
   - `net.ipv4.ip_forward = 1`
   - `net.ipv6.conf.all.forwarding = 1`
   - `net.ipv6.conf.all.accept_ra = 2`

   These need to live in TrueNAS Tunables, not `/etc/sysctl.d/` — the
   `/etc` path is rewritten on OS upgrades.

## Build and publish the image

The Compose file references `ghcr.io/iammattl/warp-connector:latest`. Build
and push from any machine with Docker:

```bash
cd deploy/warp-connector
docker build -t ghcr.io/iammattl/warp-connector:latest .
echo "$GITHUB_TOKEN" | docker login ghcr.io -u IamMattL --password-stdin
docker push ghcr.io/iammattl/warp-connector:latest
```

`$GITHUB_TOKEN` needs `write:packages` scope. The package can stay private
or be made public — the TrueNAS host needs read access either way (for
private packages, configure registry credentials in the TrueNAS Apps UI).

## Deploy on TrueNAS

1. *Apps → Discover Apps → Custom App* (or *Install Custom App*; menu name
   varies by Scale version).
2. Paste `docker-compose.yml` into the Compose field.
3. Add `CONNECTOR_TOKEN` as a secret environment variable; paste the token
   value from the CF dashboard. **Do not commit the value anywhere.**
4. If using a private GHCR image, supply registry credentials when prompted.
5. Deploy.

The container should reach Running state within ~10 seconds. The CF
dashboard will move the node from *Pending* to *Online* and assign a
Mesh IP (`100.96.0.0/12`).

## Verify

From any Mesh-enrolled client device (laptop with the Cloudflare One Client
in Mesh mode):

```bash
# Replace 100.96.X.Y with the Mesh IP shown in the dashboard for this node.
ping 100.96.X.Y
curl -sS http://100.96.X.Y:8080/health
```

`/health` should return `{"status":"healthy","service":"truenas-mcp-server","transport":"http"}`
once the MCP server is also running with `MCP_TRANSPORT=http`. Until that's
deployed, expect `Connection refused` on port 8080 — the node itself is
reachable, there's just nothing listening yet. That's Phase 3.

## Rotating the token

The connector token is single-use against fresh registration; once the
state volume holds a registration, the token isn't read again. To rotate
proactively (after a leak, lost laptop, or just on schedule):

1. CF dashboard → Networking → Mesh → click the node.
2. Delete the node. The old token becomes invalid immediately.
3. Re-add a node with the same name. New token is generated.
4. Wipe the `warp-state` volume on TrueNAS (so the next start triggers a
   fresh `connector new`).
5. Update `CONNECTOR_TOKEN` in the TrueNAS app's env, restart.

## Troubleshooting

- **Container starts then exits immediately, "operation not permitted".**
  `/dev/net/tun` isn't passed through, or the host kernel's tun module
  isn't loaded. Check `lsmod | grep tun` on the TrueNAS host; load with
  `modprobe tun` if missing (and persist via tunables).
- **Container runs but node stays Offline in dashboard.** The host sysctls
  for IP forwarding aren't set, or `accept_ra=2` is missing. Check
  `sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding net.ipv6.conf.all.accept_ra`
  in a TrueNAS shell.
- **`warp-cli connect` succeeds but other Mesh members can't reach the
  node's services.** The Mesh node has its own Mesh IP, but services
  bound to `0.0.0.0` or the host's LAN IP need the host firewall to
  permit traffic from the Mesh address space. TrueNAS's firewall is
  permissive by default, but check if Apps-level network isolation has
  been enabled.
