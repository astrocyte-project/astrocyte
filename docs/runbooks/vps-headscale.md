# VPS — Headscale Control Plane

The neutral coordination point of the tailnet (ADR-013). Starlink and
cellular are both CGNAT'd, so the coach can never accept inbound connections;
Headscale (plus its embedded DERP relay) lets every node reach every other
regardless. It lives on a VPS so neither coach nor home strands the other.

A small instance (1 vCPU / 1 GB) is plenty — Headscale only coordinates;
WireGuard payloads flow peer-to-peer (or through DERP, still end-to-end
encrypted).

## 1. Deploy

```bash
cd astrocyte/deploy/vps
mkdir -p config && $EDITOR config/config.yaml   # starter below
docker compose up -d
```

Starter `config/config.yaml` (see the Headscale docs for the full schema):

```yaml
server_url: https://headscale.example.com   # your DNS name, TLS-fronted
listen_addr: 0.0.0.0:8080
private_key_path: /var/lib/headscale/private.key
noise:
  private_key_path: /var/lib/headscale/noise_private.key
database:
  type: sqlite
  sqlite:
    path: /var/lib/headscale/db.sqlite
derp:
  server:
    enabled: true            # the relay that beats CGNAT
    region_id: 999
    stun_listen_addr: 0.0.0.0:3478
dns:
  magic_dns: true
  base_domain: coach.internal
```

Front port 8080 with TLS (Caddy/your reverse proxy) at
`https://headscale.example.com`. Open 8080/tcp (via the proxy) and 3478/udp.

## 2. Users and pre-auth keys

```bash
docker compose exec headscale headscale users create coach
docker compose exec headscale headscale preauthkeys create --user coach \
  --expiration 24h
```

Generate one key per node (coach Pi, gpu-node, phones/laptops); the coach and
GPU runbooks consume them. Name nodes stably:

```bash
docker compose exec headscale headscale nodes rename <id> gpu-node
```

## 3. ACLs (least privilege)

Start restrictive — operator devices see everything; the GPU node only needs
to be *reached*, and the coach only exposes its services:

```json
{
  "acls": [
    {"action": "accept", "src": ["tag:operator"], "dst": ["*:*"]},
    {"action": "accept", "src": ["tag:coach"], "dst": ["tag:gpu:11434"]}
  ]
}
```

## 4. Verify

From any enrolled device: `tailscale status` shows coach + gpu-node;
`curl http://<coach-tailnet-ip>:8000/health` answers from anywhere with
internet — no port forwarding anywhere (ADR-005's promise, kept).
