# Sites a deployment adds to the front door

Every `*.caddy` file in this directory is imported into the front door's `route`
block, after the client guard and before the final 404. A file holds a host
matcher and what answers it:

```caddyfile
@unifi host unifi.{$ASTROCYTE_PROXY_DOMAIN}
reverse_proxy @unifi https://127.0.0.1:8443 {
	transport http {
		tls_insecure_skip_verify
	}
}
```

The name is covered by the wildcard certificate, so a new site needs no DNS or
certificate work. A site here is reachable by every client the guard lets in:
think before publishing something that was management-only.

This directory ships empty. A deployment keeps its files with its own
configuration and points `ASTROCYTE_PROXY_SITES` at them rather than editing this
checkout (see `.env.example`).
