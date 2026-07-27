# GPU Node Setup — i9 / RTX 5080 Workstation (Linux)

The on-demand inference node (ADR-013). It travels in the coach, powers up
when in use, auto-joins the tailnet, and serves Ollama; the coach's
ModelRouter health-probes it per question and degrades gracefully when it's
off. No astrocyte services run here — just Ollama + tailscaled.

## Power budget (read first)

This machine idles ~100–150 W and can exceed 700 W under inference load,
drawn through an inverter leg. On the coach's split-leg 120 V system, know
which leg its outlet is on (Leg 1: middle AC / microwave / general outlets;
Leg 2: front+rear AC / induction cooktop) and avoid stacking it with that
leg's heavy loads on battery. On generator, unrestricted.

## 1. NVIDIA driver (Blackwell)

The RTX 5080 needs the **open kernel modules ≥ 570** and CUDA 12.8+:

```bash
# Fedora/RHEL-family:
sudo dnf install nvidia-open kmod-nvidia-open-dkms   # or distro equivalent
nvidia-smi   # must show the 5080 before continuing
```

Container runtime:

```bash
sudo dnf install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## 2. Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --login-server https://<your-headscale-host> \
  --authkey <preauth-key>
```

Give the node a stable name (`gpu-node`) in Headscale — the coach's
`deploy/coach/config/models.yml` points at `http://gpu-node:11434`.

## 3. Ollama

```bash
cd astrocyte/deploy/gpu
docker compose up -d
docker compose exec ollama ollama pull qwen3:32b   # match models.yml
```

Enable Docker (and thus Ollama) on boot so a cold power-up needs zero
interaction: `sudo systemctl enable docker`. Keep the host firewall closed on
the coach LAN — 11434 is reached over the tailnet only.

## 4. Verify the routing path

From the coach node:

```bash
curl http://gpu-node:11434/api/tags        # the ModelRouter's health probe
aios rv ask "what's the battery state of charge?"
```

Power the workstation down and ask again: the router should fall back to the
Pi's `local-llm` profile if enabled, or answer with the explicit
"AI unavailable" message — never hang.
