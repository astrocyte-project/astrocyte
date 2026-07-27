# Runbooks

Operational procedures for maintaining Astrocyte's infrastructure and tooling.

| Runbook | Purpose |
|---------|---------|
| [github-project-setup.md](github-project-setup.md) | Configure the declarative PM sync, the `PROJECT_ADMIN_TOKEN` secret, and the org Project board. |
| [coach-node-provisioning.md](coach-node-provisioning.md) | Bring up the RV coach node: Pi 5 + Docker, tailscale, SocketCAN unit, the `deploy/coach` stack, HA integrations. |
| [rv-can-tap-install.md](rv-can-tap-install.md) | Physically tap the Firefly RV-C network (listen-only), record fixtures, and the gated TX-enablement procedure. |
| [rv-fuel-monitoring.md](rv-fuel-monitoring.md) | Engine-off chassis fuel monitoring via GX Tank 140 + Cerbo GX, with the generator-prime alarm. |
| [gpu-node-setup.md](gpu-node-setup.md) | The i9/RTX 5080 on-demand inference node: NVIDIA/Blackwell driver, tailscale, Ollama. |
| [vps-headscale.md](vps-headscale.md) | The Headscale control plane on a VPS: deploy, enroll nodes, ACLs, DERP for CGNAT. |

The four RV runbooks together are the physical-install path for the 1.0
reference deployment (ADR-010); software lands first, hardware bring-up
follows them in order: vps → coach node → CAN tap → fuel monitoring.
