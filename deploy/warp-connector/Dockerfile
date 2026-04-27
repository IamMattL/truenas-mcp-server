# Cloudflare Mesh node (formerly WARP Connector) packaged for headless
# deployment as a TrueNAS Custom App. Bakes the Cloudflare apt install into
# the image so the container can start cleanly without re-downloading the
# package on every restart.
#
# Image is intentionally small — only what's needed to run warp-svc and
# register a connector. The host running the container must have
# `net.ipv4.ip_forward` and `net.ipv6.conf.all.forwarding` enabled (set via
# TrueNAS Tunables, NOT /etc/sysctl.d/ which is wiped on OS upgrade).
FROM debian:bookworm-slim

# - ca-certificates: TLS for the apt repo and warp connections.
# - curl + gnupg: install the Cloudflare apt repo signing key.
# - iproute2: warp-svc shells out to `ip` for routing table maintenance.
# - iptables: warp-svc installs forwarding rules via the legacy iptables
#   binary (warp-svc 2024.x predates nftables-only environments).
# - dumb-init: PID 1 that reaps zombies and forwards SIGTERM cleanly to
#   the entrypoint (warp-svc's own SIGTERM handling is reliable, but a
#   bare bash PID 1 doesn't reap zombie children of warp-svc).
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        ca-certificates curl gnupg iproute2 iptables dumb-init \
    && curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" \
        > /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends cloudflare-warp \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# warp-svc listens on a unix socket under /var/run/cloudflare-warp; the
# entrypoint creates this on each start. State (registration, keys) lives
# under /var/lib/cloudflare-warp and should be mounted as a volume so
# re-registration isn't required across restarts.
VOLUME ["/var/lib/cloudflare-warp"]

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/entrypoint.sh"]
