#!/usr/bin/env bash
# Static checks for the front door (#91, ADR-015). No stack is started.
#
#   check_front_door_static.sh <caddy image>
#
# Proves that the image carries the DNS provider module, that the Caddyfile is
# formatted and valid in every supported mode, and — the half that matters — that
# every unsupported setting is REFUSED rather than quietly tolerated. A Caddyfile
# that "validates" tells you nothing if a typo'd TLS mode also validates.
#
# DOCKER=podman runs it against podman.
set -euo pipefail

image="${1:?usage: check_front_door_static.sh <caddy image>}"
docker="${DOCKER:-docker}"
coach="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
caddyfile="$coach/config/caddy/Caddyfile"
sites="$coach/config/caddy/sites.d"

# A syntactically plausible token: the provider module checks the shape at load.
dummy_token="0123456789abcdefghijABCDEFGHIJ0123456789"
ranges="127.0.0.0/8 ::1/128 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 fc00::/7"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok    $*"; }

caddy() { # caddy [-e VAR=value ...] -- <caddy arguments>
  local env=()
  while [ "$1" != "--" ]; do env+=("$1"); shift; done
  shift
  "$docker" run --rm "${env[@]}" \
    -v "$caddyfile:/etc/caddy/Caddyfile:ro,z" -v "$sites:/etc/caddy/sites.d:ro,z" \
    "$image" caddy "$@"
}

valid() { # valid <what> [-e VAR=value ...]
  local what="$1"; shift
  caddy "$@" -- validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
    || fail "$what: expected a valid configuration"
  ok "valid:   $what"
}

refused() { # refused <what> [-e VAR=value ...]
  local what="$1"; shift
  if caddy "$@" -- validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    fail "$what: expected Caddy to refuse this, and it did not"
  fi
  ok "refused: $what"
}

"$docker" run --rm "$image" caddy list-modules 2>/dev/null | grep -qx 'dns.providers.cloudflare' \
  || fail "the image does not carry dns.providers.cloudflare"
ok "the image carries dns.providers.cloudflare"

diff <(caddy -- fmt /etc/caddy/Caddyfile) "$caddyfile" >/dev/null \
  || fail "the Caddyfile is not formatted: run 'caddy fmt --overwrite' on it"
ok "the Caddyfile is formatted"

valid "no environment at all"
valid "a domain, internal TLS, the default client ranges" \
  -e ASTROCYTE_PROXY_DOMAIN=portal.example.com -e ASTROCYTE_PROXY_TLS=internal \
  -e "ASTROCYTE_PROXY_ALLOW=$ranges"
valid "cloudflare TLS with a token" \
  -e ASTROCYTE_PROXY_DOMAIN=portal.example.com -e ASTROCYTE_PROXY_TLS=cloudflare \
  -e "ASTROCYTE_PROXY_DNS_TOKEN=$dummy_token"
valid "several listen addresses" \
  -e "ASTROCYTE_PROXY_BIND=127.0.0.1 192.0.2.10"

refused "an unknown TLS mode" -e ASTROCYTE_PROXY_TLS=bogus
refused "an empty TLS mode" -e ASTROCYTE_PROXY_TLS=
refused "cloudflare TLS with no token" -e ASTROCYTE_PROXY_TLS=cloudflare
refused "a client range that is not a range" -e "ASTROCYTE_PROXY_ALLOW=10.0.0.0/8 not-a-range"
refused "an empty domain" -e ASTROCYTE_PROXY_DOMAIN=

echo "front door: static checks passed"
