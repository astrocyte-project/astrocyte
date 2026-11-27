# ADR-015: Ingress and TLS — the Caddy Front Door

## Status

Accepted

## Context

A coach node runs three pages meant for people: the portal (Homepage), Grafana
and Home Assistant. Under [ADR-014](ADR-014-actuation-safety-policy.md)'s interim
posture everything but Home Assistant bound loopback, and the way in was an SSH
tunnel. That was a holding position, written while there was no authenticated
path to the node and "until the tailnet lands".

Several things have since changed or become clear:

- **The tailnet landed, and the LAN grew a firewall.** The reference deployment
  now sits on a segmented network (default-deny between segments) and a tailnet.
  There is an authenticated path. Nothing took the loopback posture down with
  it; #54 lists that decision as open.
- **A tunnel-only portal is not a portal.** Every link on it pointed at
  `127.0.0.1`. Publishing the page alone would publish a page of links that work
  on one machine.
- **The page was unfit to publish.** It ran as root (#73) and mounted the Docker
  socket. A read-only mount protects the socket file, not the API behind it:
  whatever can make the page issue Docker API calls has root on the node.
- **The page described one node.** A deployment wants one front door for
  everything it runs, on whichever machines. That list is deployment data and
  does not belong in this repository (ADR-010's rule that the core stays
  generic).
- **Certificates for private names are their own problem.** A name that resolves
  to a LAN or tailnet address cannot pass an HTTP-01 challenge, and a private CA
  means installing a root on every client, phones included.

[ADR-005](ADR-005-zero-trust-networking.md) already chose Caddy as the reverse
proxy, and #16 plans to drive it from the application registry. Neither the
registry nor the ops engine exists yet, and the front door needs neither.

## Decision

Run Caddy on the coach node as **the one component that listens beyond
loopback**, with a static configuration, publishing the node's human-facing
pages over HTTPS. This is the first slice of #16.

### What is published

| Name | Upstream | Why it is safe to publish |
|------|----------|---------------------------|
| `<domain>` | Homepage, `127.0.0.1:3001` | Links and status; hardened as below |
| `grafana.<domain>` | Grafana, `127.0.0.1:3000` | Has its own login |
| `ha.<domain>` | Home Assistant, `127.0.0.1:8123` | Has its own login; `:8123` is unchanged |

A deployment can add sites of its own from a directory it supplies
(`ASTROCYTE_PROXY_SITES`). They are imported after the client guard.

**Deliberately not published:**

- **The API and `/mcp/*`.** ADR-014 keeps the actuation surface off the LAN
  until it sits behind authentication. That is #16's work, not this ADR's.
- **VictoriaMetrics.** It has no authentication and its HTTP API can delete
  series. Grafana is the reader.

### Who can reach it: three independent limits

1. **Bind addresses.** Caddy listens only on the addresses named in
   `ASTROCYTE_PROXY_BIND`. The default is loopback, and the Caddyfile's own
   fallback is loopback too, so a Caddy started without its environment
   publishes nothing.
2. **A client allow list.** Requests from outside `ASTROCYTE_PROXY_ALLOW` get
   403 before any upstream is consulted. Unset or empty means the private, CGNAT
   and unique-local ranges. The Caddyfile itself carries no fallback list: with
   nothing set, the matcher is empty and every client is refused. **It fails
   closed.**
3. **The network's own firewall**, which this project does not manage and does
   not rely on alone.

The guard lives in a `route` block because Caddy otherwise orders directives
itself, `handle` ahead of `respond`, and the guard would stop being first.

### TLS

`ASTROCYTE_PROXY_TLS` selects one of two modes:

- **`internal`** (default): Caddy's own CA. Needs no domain and no credentials,
  and is what CI uses. Each client must trust the root.
- **`cloudflare`**: ACME **DNS-01** through the Cloudflare API, which is what
  makes a publicly trusted certificate possible for a name that resolves to a
  private address. Two certificates are issued, the name and a wildcard under
  it, so adding a site needs no certificate or DNS work.

An unknown mode stops Caddy at load. It never falls back to another mode.

Stock Caddy carries no DNS provider modules, so the repository builds its own
image (`docker/caddy/Dockerfile`), pinned to a Caddy release and a module
release, built for amd64 and arm64 and published by the release workflow as
`<repository>-caddy`.

### The portal

- Homepage stays on loopback; the proxy is the only way in. It answers only for
  the proxy's domain (`HOMEPAGE_ALLOWED_HOSTS`), no longer `*`.
- It runs as a non-root user with a tmpfs for its scratch files (#73).
- It holds no Docker socket. A socket proxy on loopback answers container reads
  and refuses everything else, and is the only container that mounts the socket.
- Its five config files come from a directory the deployment supplies
  (`ASTROCYTE_PORTAL_CONFIG`), the way the Home Assistant files already do. The
  repository ships a generic example.
- Compose defines its health check. The 2.x image carries none, and a container
  with no health state passes any check for "nothing unhealthy".

### A host prerequisite: listen addresses that come up late

**A listen address that is absent when Caddy starts stops Caddy altogether**, on
every address, not only the missing one. A tailnet address at boot is exactly
that case, and a tailnet that stayed down would keep the LAN side down with it.

Where a deployment names such an address, the host sets
`net.ipv4.ip_nonlocal_bind=1`. Caddy then starts without the address, serves it
as soon as it appears with no restart, and keeps serving the others when it goes
away. Compose cannot set this for a host-networked container, so it is a host
setting and the runbook says so.

### What #16 changes later, and what it keeps

#16 replaces the static Caddyfile with configuration rendered by the API from
the deployed-app set, adds a route per app, and moves the API and web UI behind
the proxy with authentication. It keeps the service, the image, the TLS modes,
the bind and allow-list rules, and this ADR's list of what is never published
without authentication.

## Consequences

### Positive

- One name per page, from every trusted machine and over the tailnet, with a
  certificate clients already trust. No tunnel.
- The node's exposure is one process with one capability
  (`NET_BIND_SERVICE`), and each limit on it defaults to the narrow side.
- Homepage loses root and the Docker socket, closing #73 and the socket concern
  it raised.
- The portal can describe a whole site without site data entering this
  repository.

### Negative

- A custom image to build, scan and keep current, and a second package to
  publish at each release.
- In `cloudflare` mode a DNS API token lives on the node. Cloudflare scopes a
  token to a zone, not a record, so that token can edit the whole zone.
- Home Assistant now trusts `X-Forwarded-For` from loopback. Any process on the
  node can therefore assert a client address to it. Local processes could
  already reach Home Assistant directly, so this adds no reach, but its log and
  IP-ban decisions are only as good as the proxy's word.
- The portal has no authentication of its own. Everyone the three limits let in
  can read it.

### Risks and mitigations

- **A forgotten default widens exposure.** Mitigated by tests that pin the bind
  fallback, the fail-closed guard, the guard's position, the absence of any
  Docker socket in Homepage, and the list of published upstreams.
- **The DNS token is stolen with the node.** Use a token for this purpose only,
  limited to DNS on the one zone. A deployment that wants less can point the
  challenge at a throwaway zone with a CNAME and scope the token to that.
- **A certificate silently fails to renew.** Caddy retries on its own, but the
  deployment should watch the page from outside the node.
- **Upstream changes defaults again.** Homepage 2.0 changed an unset `HOSTNAME`
  from loopback to every interface; the bind is now explicit and tested.

## Alternatives Considered

### Bind each service to the LAN on its own port

Quicker. Plain HTTP, a port per service to remember, nothing for the links, and
as many listening processes as there are services.

### A separate ACME client, with stock Caddy reading certificate files

Keeps the stock image. Costs a second moving part on the host, a reload on every
renewal, and a split of the certificate story across two tools. A deployment
that prefers it can still add its own site file.

### The internal CA only

No credentials and no custom image, but every client has to install a root, and
phones make that painful enough that people stop using the page.

### Wait for #16

It depends on the app registry and the ops engine. The front door is useful now
and constrains #16 only in ways #16 wants anyway.

## Related Decisions

- [ADR-005](ADR-005-zero-trust-networking.md) — Caddy as the reverse proxy; this
  is the first part of its Phase 1.
- [ADR-010](ADR-010-rv-reference-deployment.md) — the core stays generic;
  deployment data lives with the deployment.
- [ADR-013](ADR-013-multi-node-topology.md) — the coach node and the tailnet.
- [ADR-014](ADR-014-actuation-safety-policy.md) — amended by this ADR: three
  pages leave loopback; the API does not.

## Notes

- Tracking issue: #91. Advances #16 and #54; closes #73.
- The bind, guard, TLS-mode, Homepage and socket-proxy behaviours were each
  verified before implementation; the results are recorded on #91.
- Operator steps: `docs/runbooks/coach-node-provisioning.md` §8.
