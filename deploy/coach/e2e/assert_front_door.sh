#!/usr/bin/env bash
# Runtime assertions for the front door (#91, ADR-015), against a running coach
# stack with `--profile proxy --profile portal` and the defaults: the domain is
# `localhost`, TLS is Caddy's internal CA (hence `curl -k`), the bind is loopback.
#
# Each line is a property the front door promises. The ones that say what must
# NOT answer are the point: a proxy that serves the portal proves little unless
# the same run shows it refusing a client outside its list, a name it was not
# given, and a write to the Docker API.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Every compose command below must see the front door's services, whatever the
# caller passed to `up`.
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-sim,proxy,portal}"

resolve=(
  --resolve localhost:443:127.0.0.1 --resolve localhost:80:127.0.0.1
  --resolve ha.localhost:443:127.0.0.1 --resolve nope.localhost:443:127.0.0.1
)

fail() { echo "FAIL: $*" >&2; exit 1; }

code() { # the HTTP status, or 000 when there was no HTTP answer at all
  curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$@" 2>/dev/null || true
}

expect() { # expect <status> <what> <curl arguments>
  local want="$1" what="$2" got
  shift 2
  got="$(code "$@")"
  [ "$got" = "$want" ] || fail "$what: expected $want, got $got"
  echo "ok    $what ($got)"
}

reload_caddy() { # reload_caddy [-e VAR=value ...]: re-read the Caddyfile under this environment
  docker compose exec -T "$@" caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
    || fail "caddy reload failed ($*)"
  sleep 1
}

# --- the portal, by name, over HTTPS ----------------------------------------
for _ in $(seq 1 30); do
  [ "$(code "${resolve[@]}" https://localhost/)" = "200" ] && break
  sleep 2
done
expect 200 "the portal answers over HTTPS by name" "${resolve[@]}" https://localhost/
expect 308 "plain HTTP redirects to HTTPS" "${resolve[@]}" http://localhost/
expect 404 "an unknown name under the domain gets no site" "${resolve[@]}" https://nope.localhost/
expect 000 "a request by address gets no site at all" https://127.0.0.1/

listeners="$(docker compose exec -T caddy netstat -ltn | awk '$4 ~ /:(80|443)$/ {print $4}' | sort -u | tr '\n' ' ')"
case "$listeners" in
  "127.0.0.1:443 127.0.0.1:80 ") echo "ok    with no bind set, Caddy listens on loopback only ($listeners)" ;;
  *) fail "with no bind set, Caddy listens on: $listeners" ;;
esac

# --- the client guard ---------------------------------------------------------
reload_caddy -e ASTROCYTE_PROXY_ALLOW=192.0.2.0/24
expect 403 "a client outside the allowed ranges gets 403" "${resolve[@]}" https://localhost/
reload_caddy -e ASTROCYTE_PROXY_ALLOW=
expect 403 "an empty allow list refuses everyone, not no one" "${resolve[@]}" https://localhost/
reload_caddy
expect 200 "the default ranges let a loopback client back in" "${resolve[@]}" https://localhost/

# --- Homepage ---------------------------------------------------------------
homepage="$(docker compose ps -q homepage)"
[ -n "$homepage" ] || fail "the homepage container is not running"

uid="$(docker compose exec -T homepage id -u)"
[ "$uid" = "1000" ] || fail "Homepage runs as uid $uid, not 1000"
echo "ok    Homepage runs as a non-root user (uid $uid)"

if docker inspect "$homepage" --format '{{range .Mounts}}{{println .Source}}{{end}}' | grep -q 'docker.sock'; then
  fail "Homepage mounts the Docker socket"
fi
echo "ok    Homepage holds no Docker socket"

for _ in $(seq 1 30); do
  health="$(docker inspect "$homepage" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  [ "$health" = "healthy" ] && break
  sleep 2
done
[ "$health" = "healthy" ] || fail "Homepage's health is '$health' (a health check must exist and pass)"
echo "ok    Homepage has a health check, and it passes"

expect 400 "Homepage refuses a host name it was not given" -H 'Host: evil.example' http://127.0.0.1:3001/

statuses="$(curl -sk --max-time 10 "${resolve[@]}" 'https://localhost/api/docker/statuses?server=my-docker')"
echo "$statuses" | grep -q '"astrocyte-coach-homeassistant-1":{"status":"running"}' \
  || fail "container status did not arrive through the socket proxy: $statuses"
echo "ok    container status arrives through the socket proxy"

# --- the socket proxy ---------------------------------------------------------
expect 200 "the socket proxy lists containers" http://127.0.0.1:2375/containers/json
expect 403 "the socket proxy refuses a write (stop)" -X POST http://127.0.0.1:2375/containers/astrocyte-coach-caddy-1/stop
expect 403 "the socket proxy refuses an exec" -X POST http://127.0.0.1:2375/containers/astrocyte-coach-caddy-1/exec
expect 403 "the socket proxy refuses the image list" http://127.0.0.1:2375/images/json

# --- Home Assistant behind the proxy, and unchanged on its own port -------------
expect 200 "Home Assistant answers through the proxy" -L "${resolve[@]}" https://ha.localhost/
expect 200 "Home Assistant still answers on :8123" -L http://127.0.0.1:8123/

# --- the deploy tree stays clean (#68) ------------------------------------------
dirty="$(git status --porcelain -- config/homepage config/caddy)"
[ -z "$dirty" ] || fail "the stack wrote into the deploy tree: $dirty"
echo "ok    nothing was written into config/homepage or config/caddy"

echo "front door: runtime assertions passed"
