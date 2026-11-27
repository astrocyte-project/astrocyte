# Caddy with the Cloudflare DNS provider module (ADR-015).
#
# Stock Caddy carries no DNS provider modules, and ACME DNS-01 is the only way to
# get a publicly trusted certificate for a name that resolves to a private
# address — which is what a front door on a LAN or tailnet has.
#
# The build stage runs on the build machine's own architecture and cross-compiles,
# so producing the arm64 image needs no emulation.
#
# The two Caddy tags below are literal, and must match: Dependabot bumps literal
# tags and cannot follow one passed in as a build argument. (An argument named
# CADDY_VERSION would also be shadowed: the builder image exports its own, with a
# leading "v", and xcaddy would be asked for "vv2.11.9".) xcaddy builds the Caddy
# version of the builder image it runs in.
FROM --platform=$BUILDPLATFORM docker.io/library/caddy:2.11.9-builder AS build
ARG TARGETOS
ARG TARGETARCH
ARG CADDY_DNS_CLOUDFLARE_VERSION=v0.2.4
# Caddy 2.11.9 pins golang.org/x/net v0.60.0, which carries CVE-2026-78661 (HIGH,
# x/net/html). Requiring the fixed version raises it for this build; Go picks the
# highest version anything asks for, so this can never pull x/net *down* once
# Caddy itself moves past it. Drop the line when the Caddy tags above do.
ARG GOLANG_X_NET_VERSION=v0.62.0
RUN GOOS=${TARGETOS} GOARCH=${TARGETARCH} xcaddy build \
      --with github.com/caddy-dns/cloudflare@${CADDY_DNS_CLOUDFLARE_VERSION} \
      --with golang.org/x/net/html@${GOLANG_X_NET_VERSION} \
      --output /out/caddy

FROM docker.io/library/caddy:2.11.9
COPY --from=build /out/caddy /usr/bin/caddy
