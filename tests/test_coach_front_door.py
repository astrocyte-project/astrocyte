"""Front-door invariants for the coach stack (#91, ADR-015).

These read the deployment files rather than start anything. Each one pins a
property that is easy to undo by accident and silent when undone: a socket mount
that comes back, a bind default that widens, a guard that drifts below the
upstreams it protects. The running behaviour is asserted by
``deploy/coach/e2e/assert_front_door.sh`` in the e2e workflow.
"""

import re
from pathlib import Path
from typing import Any

import yaml

COACH = Path("deploy/coach")
COMPOSE = COACH / "compose.yaml"
CADDYFILE = COACH / "config" / "caddy" / "Caddyfile"
HOMEPAGE = COACH / "config" / "homepage"
HA_CONFIG = COACH / "config" / "homeassistant" / "configuration.yaml"

# The variables the default profile has always required. A hard `${VAR:?}`
# guard on anything else breaks every profile that does not need that variable,
# because compose interpolates all services whatever profile is active.
REQUIRED_BY_DEFAULT_PROFILE = {
    "POSTGRES_PASSWORD",
    "ASTROCYTE_API_TOKEN",
    "ASTROCYTE_HA_TOKEN",
}


def _services() -> dict[str, dict[str, Any]]:
    compose = yaml.safe_load(COMPOSE.read_text())
    services: dict[str, dict[str, Any]] = compose["services"]
    return services


def _mount_sources(service: dict[str, Any]) -> list[str]:
    return [str(v).split(":")[0] for v in service.get("volumes", [])]


def _strings(node: Any) -> list[str]:
    """Every string value in a YAML document (comments are not values)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for value in node for s in _strings(value)]
    return []


def test_only_the_socket_proxy_holds_the_docker_socket() -> None:
    holders = [
        name
        for name, service in _services().items()
        if any("docker.sock" in source for source in _mount_sources(service))
    ]
    assert holders == ["socket-proxy"]


def test_socket_proxy_allows_container_reads_and_nothing_else() -> None:
    proxy = _services()["socket-proxy"]
    assert proxy["environment"] == {"CONTAINERS": "1", "POST": "0"}
    assert proxy["ports"] == ["127.0.0.1:2375:2375"]


def test_socket_proxy_is_pinned_by_digest() -> None:
    """The project publishes no version tags; a bare tag would move under us."""
    assert re.search(r"@sha256:[0-9a-f]{64}$", _services()["socket-proxy"]["image"])


def test_homepage_is_not_root_and_binds_loopback() -> None:
    homepage = _services()["homepage"]
    assert homepage["user"] == "1000:1000"
    # Since Homepage 2.0 an unset HOSTNAME binds every interface.
    assert homepage["environment"]["HOSTNAME"] == "127.0.0.1"


def test_homepage_answers_only_for_the_proxy_domain() -> None:
    allowed = _services()["homepage"]["environment"]["HOMEPAGE_ALLOWED_HOSTS"]
    assert allowed == "${ASTROCYTE_PROXY_DOMAIN:-localhost}"
    assert "*" not in allowed


def test_homepage_defines_its_own_health_check() -> None:
    """The 2.x image carries none, and no check reads as 'nothing unhealthy'."""
    test = _services()["homepage"]["healthcheck"]["test"]
    assert "/api/healthcheck" in " ".join(test)


def test_homepage_config_is_a_tmpfs_with_read_only_files_on_top() -> None:
    homepage = _services()["homepage"]
    assert homepage["tmpfs"] == ["/app/config:rw,mode=1777"]
    mounts = [str(v) for v in homepage["volumes"]]
    assert len(mounts) == 5
    for mount in mounts:
        assert mount.startswith("${ASTROCYTE_PORTAL_CONFIG:-./config/homepage}/")
        assert mount.endswith(":ro,z")


def test_caddy_defaults_never_widen_what_is_published() -> None:
    caddy = _services()["caddy"]
    env = caddy["environment"]
    assert caddy["profiles"] == ["proxy"]
    assert env["ASTROCYTE_PROXY_BIND"] == "${ASTROCYTE_PROXY_BIND:-127.0.0.1}"
    assert env["ASTROCYTE_PROXY_TLS"] == "${ASTROCYTE_PROXY_TLS:-internal}"
    # `:-` (not `-`): an empty value in .env falls back to the ranges too.
    allow = env["ASTROCYTE_PROXY_ALLOW"]
    assert allow.startswith("${ASTROCYTE_PROXY_ALLOW:-127.0.0.0/8 ")
    assert "0.0.0.0/0" not in allow
    assert "::/0" not in allow


def test_caddy_keeps_one_capability() -> None:
    caddy = _services()["caddy"]
    assert caddy["cap_drop"] == ["ALL"]
    assert caddy["cap_add"] == ["NET_BIND_SERVICE"]


def test_no_new_hard_guards_in_compose() -> None:
    values = "\n".join(_strings(yaml.safe_load(COMPOSE.read_text())))
    guarded = set(re.findall(r"\$\{([A-Z0-9_]+):\?", values))
    assert guarded == REQUIRED_BY_DEFAULT_PROFILE


def test_caddyfile_guard_runs_before_every_upstream() -> None:
    text = CADDYFILE.read_text()
    route = text.index("route {")
    guard = text.index("respond @outside 403")
    first_upstream = text.index("reverse_proxy ")
    deployment_sites = text.index("import /etc/caddy/sites.d/*.caddy")
    # Inside `route` the order is literal; outside it Caddy would sort `handle`
    # ahead of `respond` and the guard would no longer be first.
    assert route < guard < first_upstream < deployment_sites


def test_caddyfile_guard_has_no_fallback_ranges() -> None:
    """Unset means the matcher is empty, which refuses everyone: it fails closed."""
    assert "@outside not remote_ip {$ASTROCYTE_PROXY_ALLOW}\n" in CADDYFILE.read_text()


def test_caddyfile_falls_back_to_loopback() -> None:
    assert "default_bind {$ASTROCYTE_PROXY_BIND:127.0.0.1}" in CADDYFILE.read_text()


def test_caddyfile_publishes_only_the_three_pages() -> None:
    upstreams = re.findall(r"reverse_proxy @\w+ (\S+)", CADDYFILE.read_text())
    # The portal, Grafana, Home Assistant. Not the API (:8000) and not
    # VictoriaMetrics (:8428), which has no authentication and can delete series.
    assert upstreams == ["127.0.0.1:3001", "127.0.0.1:3000", "127.0.0.1:8123"]


def test_example_portal_has_no_loopback_links() -> None:
    """A link is opened by someone's browser, on another machine."""
    groups = yaml.safe_load((HOMEPAGE / "services.yaml").read_text())
    hrefs = [
        tile["href"]
        for group in groups
        for tiles in group.values()
        for entry in tiles
        for tile in entry.values()
        if "href" in tile
    ]
    assert hrefs == [
        "https://ha.{{HOMEPAGE_VAR_DOMAIN}}",
        "https://grafana.{{HOMEPAGE_VAR_DOMAIN}}",
    ]


def test_example_portal_reads_docker_through_the_proxy() -> None:
    servers = yaml.safe_load((HOMEPAGE / "docker.yaml").read_text())
    assert servers == {"my-docker": {"host": "127.0.0.1", "port": 2375}}


def test_home_assistant_trusts_the_proxy_on_loopback_only() -> None:
    text = HA_CONFIG.read_text()
    http = text[text.index("\nhttp:\n") : text.index("\nrecorder:\n")]
    assert "use_x_forwarded_for: true" in http
    trusted = re.findall(r"^    - (\S+)$", http, flags=re.MULTILINE)
    assert trusted == ["127.0.0.1", "::1"]
