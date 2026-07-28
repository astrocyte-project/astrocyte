# Coach Node Provisioning — Raspberry Pi 5

Brings up the always-on coach node (ADR-013): Raspberry Pi OS + Docker
running the `deploy/coach` stack (Home Assistant, Mosquitto, Postgres,
rvc-bridge, astrocyte API).

> **Superseded plan note:** the original §12A coach plan was Home Assistant
> OS + InfluxDB on this Pi. Both are superseded: the Pi also runs the
> astrocyte stack, so HA runs as a *container* (ADR-011), and time-series
> lives in Postgres + HA long-term statistics, not InfluxDB (ADR-012).

## Prerequisites — the coach network ⚠️ install-blocking

A coach LAN must exist before this runbook works. Requirements:

- A router in the coach (Starlink + cellular WAN); vendor/model is the
  owner's choice.
- **DHCP reservations or static IPs** for: the Pi, the **Victron Cerbo GX**
  (HA's `victron_gx` integration needs to reach it), and the i9 GPU
  workstation.
- The Pi and the i9 join the tailnet (below); the Cerbo only needs LAN.

## 1. Base OS

Pi 5 (8 GB) in the Argon NEO 5 case (thermal pads seated), Samsung PRO
Endurance SD. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi
Imager (enable SSH, set user). Then:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y can-utils curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

> SD endurance: the recorder is tuned in the shipped HA config
> (`commit_interval: 30`, `purge_keep_days: 30`). If write wear becomes a
> problem, the Argon NEO 5 NVMe variant is the tracked hardware follow-up.

## 2. Tailscale (host-level, ADR-013)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --login-server https://<your-headscale-host> \
  --authkey <preauth-key-from-vps-runbook>
tailscale ip -4   # -> ASTROCYTE_API_HOST in .env
```

See [vps-headscale.md](vps-headscale.md) for the control plane and pre-auth
keys.

## 3. SocketCAN interface (systemd)

`/etc/systemd/system/can0.service` — listen-only until TX validation
([rv-can-tap-install.md](rv-can-tap-install.md)):

```ini
[Unit]
Description=RV-C CAN interface (listen-only)
BindsTo=sys-subsystem-net-devices-can0.device
After=sys-subsystem-net-devices-can0.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/ip link set can0 up type can bitrate 250000 listen-only on
ExecStop=/usr/sbin/ip link set can0 down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now can0.service
```

## 4. The coach stack

```bash
git clone https://github.com/astrocyte-project/astrocyte.git && cd astrocyte/deploy/coach
cp .env.example .env   # fill in: see comments in the file
docker compose up -d
```

Fill `.env` in this order:

1. `POSTGRES_PASSWORD` (`openssl rand -hex 16`), `ASTROCYTE_API_TOKEN`
   (`openssl rand -hex 32`), `ASTROCYTE_API_HOST` (the tailnet IP from step 2).
2. Start the stack once with `ASTROCYTE_HA_TOKEN` blank → HA comes up →
   complete onboarding at `http://<pi>:8123`.
3. In HA: create a **long-lived access token** (profile → Security) → put it
   in `.env` → `docker compose up -d` again.

## 5. HA integrations (interactive, once)

- **MQTT**: Settings → Devices & Services → Add → MQTT → `127.0.0.1:1883`.
  RV-C devices appear as the bridge discovers them.
- **Victron GX**: Add → Victron GX → the Cerbo's LAN address. First enable
  MQTT on the Cerbo: GX device → Settings → Services → **MQTT on LAN (SSL +
  plaintext)**. Battery/solar (and the GX Tank 140 fuel sensor, see
  [rv-fuel-monitoring.md](rv-fuel-monitoring.md)) flow in automatically.
- **Companion app** on your phone (over the tailnet) — this is the delivery
  channel for alarms and pending-approval notifications (ADR-014).
- Harden Mosquitto: `config/mosquitto.conf` → `mosquitto_passwd`, set
  `allow_anonymous false`, fill `MQTT_USERNAME`/`MQTT_PASSWORD` in `.env`.
- **Deployment-specific config comes from your own inventory repo.** The stack ships
  `*.example.*` files and falls back to them, but a real coach supplies its own via
  `.env` — the instance map, dashboard, automations, HA packages and the energy-prefs
  entity ids:

  ```bash
  RVC_INSTANCE_MAP=/path/to/inventory/coach/rvc-instances.yml
  HA_DASHBOARD=/path/to/inventory/coach/homeassistant/coach-overview.yaml
  HA_AUTOMATIONS=/path/to/inventory/coach/homeassistant/automations.yaml
  HA_PACKAGES=/path/to/inventory/coach/homeassistant/packages
  ASTROCYTE_ENERGY_PREFS=/config/energy_prefs.json   # inside the api container
  ```

  Which instance drives which fixture, and which entity ids a dashboard addresses, are
  facts about *one coach* — they belong with that coach's records, not in this repo
  (ADR-012). The paths above are the only coupling.

  The same rule covers the scalar values that *address* a deployment, so no shipped
  file has to be edited on the node:

  ```bash
  COACH_ID=refcoach                  # this coach's identifier
  COACH_ROUTER_ADDR=192.0.2.1:9100   # substituted into scrape.yml
  VM_LONGTERM_ADDR=192.0.2.21:8428   # vmagent's second, independent write queue
  ```

  Note what is **not** here: the `host="coach-router"` label. The scrape config pins
  it regardless of what the router is called locally, and every WAN dashboard query
  keys on it. Localising that label is a silent break — the panels still render, they
  just match nothing.

- **Dashboards**: the curated **Coach** dashboard (home / lights / climate /
  power / tanks / system) is a YAML dashboard mounted from
  `config/homeassistant/coach-overview.yaml` — it appears in the sidebar
  automatically. Its cards address entities by id, and HA derives those ids from
  the names in `config/rvc-instances.yml`, so **after editing a fixture or zone
  name in that map, retire the old entities before restarting the bridge** — HA
  freezes an entity_id at first registration and would otherwise keep it:

  ```bash
  # 1. retire the retained discovery, then bring the bridge back
  docker compose stop rvc-bridge
  docker compose run --rm rvc-bridge astro-rvc-bridge --reset-discovery
  docker compose up -d --force-recreate rvc-bridge

  # 2. move the ids HA restored from its deleted-entity cache (see below)
  docker compose exec -T api python - < config/homeassistant/rename_entities.py
  docker compose exec -T api python - < config/homeassistant/rename_entities.py --apply
  ```

  **Step 2 is not optional.** HA keeps a `deleted_entities` record keyed by
  `unique_id` and restores the *old* entity_id when that unique_id reappears, so
  after the reset the entities come back under their previous names however many
  times discovery is republished. `rename_entities.py` moves them through the
  entity registry; run it without `--apply` first to see the plan, and `--show`
  to audit what every RV-C entity currently resolves to.

  The reset clears only `homeassistant/device/rvc_<coach_id>_*` configs; the
  Victron and other integrations are untouched. Recorder history under the old
  ids is dropped, which is why it is a deliberate step and not automatic.

  **Reset while the coach bus is awake.** Sensor devices are rediscovered from
  observed frames, so on a sleeping bus they stay missing until it next wakes
  (the v0.3.4 deploy went from 690 entities to 257 this way). Retained
  `rvc/state/#` topics survive, so values return with the entities. Re-run
  `rename_entities.py --apply` after the bus wakes to move the ids of devices
  that re-registered late.

  The **native Energy dashboard** (`/energy`)
  is WebSocket-configured, so run it once after the Victron entities exist
  (energy prefs live in HA's `.storage`, not git):

  ```bash
  docker compose exec -T api python - < config/homeassistant/energy_prefs.py
  ```

  Edit the entity ids in that script if the Cerbo's device ids differ from the
  reference coach.

## 6. Verify

```bash
curl http://$(tailscale ip -4):8000/health           # {"status":"ok"}
docker compose exec mosquitto mosquitto_sub -t 'rvc/state/#' -v -W 10
uv run aios rv status   # or: docker compose exec api aios rv status
```

Optional profiles: `--profile apps` (NextCloud), `--profile local-llm`
(small Ollama — watch memory; 8 GB is tight with everything resident).

## 7. WAN gateway quality poller (systemd user timer)

The gateway panels on the **"Coach WAN & Segments"** Grafana dashboard
(`--profile observability`) are fed by
[`deploy/coach/bin/coach-gw-metrics.py`](../../deploy/coach/bin/coach-gw-metrics.py),
which polls the OPNsense router's dpinger results over its API and pushes
`coach_gateway_{delay_ms,stddev_ms,loss_ratio,up}` into VictoriaMetrics.
It runs on the Pi rather than the router to keep a second agent off the
firewall.

First create a dedicated OPNsense API user (e.g. `svc-metrics`) holding
**only** the `page-system-gateways` privilege — the poller must not carry
credentials that could reconfigure the firewall — and save its key/secret
to `~/.config/opnsense-metrics-apikey.txt` (mode 600, two lines: key then
secret; the downloaded `key=`/`secret=` prefixes are fine). Then:

```bash
cp deploy/coach/bin/coach-gw-metrics.py ~/bin/
cp deploy/coach/systemd/coach-gw-metrics.{service,timer} ~/.config/systemd/user/
# The router's address is an input, never baked into the script or the unit:
printf 'COACH_ROUTER_URL=https://<router mgmt addr>\n' > ~/.config/coach-gw-metrics.env
chmod 600 ~/.config/coach-gw-metrics.env
systemctl --user daemon-reload
systemctl --user enable --now coach-gw-metrics.timer
loginctl enable-linger $USER   # required — otherwise the timer dies at logout, silently
```

The poller exits non-zero with `pass --router or set COACH_ROUTER_URL` if that
file is missing, so a skipped step fails visibly rather than polling nothing.
To override per-invocation (e.g. for `--dry-run`), pass `--router https://<addr>`.

Verify with `--dry-run` before trusting the dashboard: it prints the exact
metric names, and a panel on a wrong name renders **empty, not an error**
(loss is `coach_gateway_loss_ratio`, a 0–1 ratio — there is no `_loss_pct`).
Two deployment traps: VictoriaMetrics reloads `scrape.yml` only on
**restart**, not `SIGHUP`; and after any upstream change on the WAN2 device,
restart dpinger on the router (`pluginctl -s dpinger restart`) or its pinned
ICMP flow can report a working path as 100 % loss.
