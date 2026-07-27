# Astrocyte

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Astrocyte isn't just a "suite"; it's a Self-Hosted AI Operating System.

The project aims to sit at a level above NextCloud, etc. and use an Agentic AI approach management.

## Feature Comparison

|Feature    | Standard (Nextcloud/CasaOS) | Astrocyte            |
|-----------|-----------------------------|----------------------|
|Search     | App-specific keywords       | Cross-app semantic reasoning |
|Updates    | Manual / Click-per-app	  | Agent-verified (Autonomously tests if service is up post-update) |
|Security   | Manual Firewall/VPN config  | Native Zero-Trust Tunneling |
|Automation | "If This Then That" rules   |	Intent-based ("Monitor my power usage and alert if it's weird") |

* * *

This is not just replicating the "App Store" model—that’s been solved. Instead, this solves these current pain points in the community:

- Unified Search: Currently, if I have docs in Nextcloud and notes in SilverBullet, I can't search them both from one place. A suite with cross-app search would be revolutionary.

- Unified Backup: Backing up 20 different Docker containers is a nightmare. A suite that offers a single, encrypted, off-site "Atomic Backup" for the entire system is highly sought after.

- True Local-First AI: Most suites are just adding "wrappers" for OpenAI. A suite built from the ground up to use a local LLM (like Llama 3) to organize your files and automate your home would be a 2026-era killer feature.

- Networking/Zero-Trust: Setting up Port Forwarding or VPNs is still the biggest hurdle for newbies. If your suite built-in a seamless "Tunnelling" solution (like Cloudflare Tunnels or Tailscale) natively, it would win on ease of use.

By shifting the focus from "hosting apps" to "managing data via agents," you are targeting the biggest weakness of the current ecosystem: fragmentation. In 2026, the community is moving away from "App Hoarding" and toward "Data Sovereignty," where the specific app matters less than the ability to interact with the data it holds.

Here is how your project can bridge the gap and surpass existing solutions:
1. Unified Search (The "RAG" Layer)

Current tools like Nextcloud search their own database. Your project would act as a Retrieval-Augmented Generation (RAG) aggregator.

    The Tech: Use a vector database (like Milvus or ChromaDB) as the "system brain."

    The Difference: Instead of searching for "Tax Return 2025," an agent can answer, "How much did I spend on taxes last year?" by pulling from your PDFs in the file server and your entries in your accounting app.

    Killer Feature: A "System-Wide Context" that apps feed into via a unified API or filesystem watcher.

2. Agentic Management (The "Ops" Agent)

Standard suites require you to be a SysAdmin. Your project uses an Infrastructure-as-Code (IaC) Agent.

    The Concept: You don't "install Docker containers." You tell the AI, "I want to start a recipe blog," and the agent chooses the stack, configures the reverse proxy, and sets up the database.

    The Gap: Most AI "wrappers" just chat. An agentic suite has execution permissions—it can pull images, edit .env files, and restart services based on natural language commands.

3. Atomic Backup (The "Time Machine" Approach)

The nightmare of self-hosting is the "state." Database files, config files, and media are often scattered.

    The Fix: Use a file system like ZFS or Btrfs with integrated snapshots.

    The Difference: Your suite doesn't just back up files; it backs up the entire system state as a single encrypted volume to S3 or a secondary peer.

    Killer Feature: "One-Click Restoration." If an update breaks the AI, the agent rolls back the entire filesystem snapshot to 5 minutes ago.

4. Built-in Zero-Trust (The "Invisible" Network)

Newbies quit when they hit "Port Forwarding" or "DNS Records."

    The Fix: Deep integration with Tailscale (Headscale) or Cloudflare Tunnels natively in the kernel level of your suite.

    The Experience: When you initialize the project, it gives you a private URL. No ports are ever opened on the router. It is "Secure by Default," not "Secure if you're an expert."

* * *

## Architect's Analysis, Plan, and Naming

### Senior Open-Source Architect's Analysis

This document provides a strong, compelling vision. It correctly identifies critical pain points in the existing self-hosting ecosystem and proposes innovative, AI-centric solutions that are highly relevant for 2026 and beyond. The four core features—Unified Search, Agentic Management, Atomic Backup, and Zero-Trust Networking—are ambitious and well-articulated.

However, to mature this from a visionary document into a credible open-source project blueprint, several key areas must be addressed.

#### What's Missing or Needs Clarification

1.  **Core Architecture & Technology Choices:**
    *   **The "Kernel":** What is the base platform? Is this a new Linux distribution (highly ambitious), a container-based OS (like Fedora CoreOS), or an application layer running on a standard OS (e.g., Debian)? This is the most critical missing architectural decision.
    *   **Agent Framework:** What technology will power the agents? A framework like LangChain, LlamaIndex, Autogen, or a custom solution needs to be chosen.
    *   **API & Interoperability:** The "unified API" is a great concept, but its specification is crucial. How will existing, non-compliant apps be integrated? Will it require app-specific plugins, or will it rely on more general methods like file watchers and database connectors?

2.  **Project Governance and Community:**
    *   **License:** This is non-negotiable. An OSI-approved license (e.g., MIT, Apache 2.0, AGPLv3) must be chosen to define the terms of use, modification, and distribution. AGPLv3 is a strong candidate for ensuring the project remains open.
    *   **Contribution Guidelines:** A clear `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` are essential for building a healthy community.
    *   **Governance Model:** How are decisions made? A transparent governance model (e.g., BDFL, core team, meritocracy) is key to a project's long-term viability.

3.  **Security Model:**
    *   **Agent Permissions:** Granting agents execution permissions is powerful but risky. A robust security model, such as a sandboxed environment with fine-grained, Role-Based Access Control (RBAC) for agents, is absolutely critical to prevent misuse or damage.
    *   **Data Privacy:** With a central RAG layer indexing all user data, strong safeguards are needed to prevent data leakage and ensure privacy.

#### What Might Be Overly Ambitious (for a V1)

*   **"Kernel Level" Integration:** True kernel-level work is exceedingly complex. A more pragmatic approach would be to build this as a well-integrated application layer on a stable, existing base OS.
*   **Fully Autonomous Stack Selection:** The "I want a recipe blog" vision is powerful but is a long-term goal. A realistic V1 should focus on a curated marketplace of pre-vetted, agent-compatible applications.

### Phased Development Plan

This phased approach focuses on delivering value incrementally and building a solid foundation for future growth.

#### Phase 0: Foundation & Community (1-2 Months)
*   **Goal:** Establish the project's core infrastructure and attract initial contributors.
*   **Tasks:**
    1.  Finalize the open-source license (e.g., AGPLv3).
    2.  Create a GitHub organization, repository, and initial documentation (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`).
    3.  Define and document the core architecture: Base OS, container runtime, and agent framework.
    4.  Set up basic CI for linting and testing.

#### The RV Reference Deployment (v0.3)
*   **Goal:** Make Astrocyte 1.0 real by validating it against a physical reference deployment: a Class A motor coach ([ADR-010](docs/adr/ADR-010-rv-reference-deployment.md)).
*   **Why:** The coach exercises every pillar harder than a homelab — live sensors and actuators (RV-C over CAN, Victron energy systems), a hard power budget, intermittent connectivity, and multi-node compute (always-on Pi 5 + on-demand GPU workstation).
*   **Tasks:**
    1.  RV-C CAN→MQTT bridge with a typed decoder, feeding Home Assistant as the hardware abstraction layer ([ADR-011](docs/adr/ADR-011-home-assistant-hardware-layer.md), [ADR-012](docs/adr/ADR-012-rvc-telemetry-architecture.md)).
    2.  A Home Assistant MCP server so agents can read every sensor and — behind a tiered actuation safety policy ([ADR-014](docs/adr/ADR-014-actuation-safety-policy.md)) — control the safe subset.
    3.  Multi-node topology with model routing and graceful degradation ([ADR-013](docs/adr/ADR-013-multi-node-topology.md)).
    4.  Deployable compose stacks for the coach, GPU, and VPS nodes.

This re-sequenced the original milestones: Ops Agent & curated apps moved to v0.4 and the RAG layer to v0.5; 1.0 now includes RV reference-deployment validation.

#### Phase 1: The Ops Agent & Curated Apps (3-6 Months)
*   **Goal:** Deliver a Minimum Viable Product (MVP) focused on agent-based application management and secure networking.
*   **Tasks:**
    1.  Develop the "Ops Agent" with a secure, sandboxed execution environment.
    2.  Create a CLI for interacting with the Ops Agent (e.g., `aios deploy photoprism`).
    3.  Build a curated marketplace of 3-5 well-known applications.
    4.  Implement the **Built-in Zero-Trust Networking** feature, likely using Headscale. A user should be able to install the OS and access their first app via a secure tunnel with zero manual network configuration.

#### Phase 2: The RAG Layer & Unified Search (4-8 Months)
*   **Goal:** Implement the system-wide semantic search.
*   **Tasks:**
    1.  Integrate a vector database (e.g., ChromaDB).
    2.  Develop the "RAG Agent" and the unified data-ingestion API.
    3.  Create data connectors/plugins for the curated apps to feed data into the vector database.
    4.  Build a basic web UI with a single search bar to query the RAG Agent.

#### Phase 3: Atomic Backups & System Polish (3-5 Months)
*   **Goal:** Introduce robust backup/restore functionality and improve the user experience.
*   **Tasks:**
    1.  Implement the **Atomic Backup** feature, focusing first on a reliable method of bundling and encrypting all relevant application volumes and database state.
    2.  Add support for pushing/pulling backup bundles to S3-compatible storage.
    3.  Develop a more comprehensive Web UI for managing apps, users, backups, and interacting with the agents.

### The Competitive Landscape in 2026

While projects like Octelium (Zero-Trust/MCP gateway) and Umbrel are moving in this direction, they still feel like "Launchers."

The "Gap" this project is filling is the Model Context Protocol (MCP) integration. If the suite is built as a series of MCP servers, the Local LLM doesn't just "talk" to you; it becomes the user interface for the entire server.

### Why Astrocyte?

Astrocytes are star-shaped cells that support the brain's neurons and form a protective barrier. This perfectly mirrors the project's dual roles: acting as the "system brain" (RAG layer) and providing robust security (Zero-Trust).

## Development & Project Status

Astrocyte is in **early/primary development**. The repository carries a
runnable skeleton — a FastAPI service (`src/astrocyte`), a React 19 + Vite web
app (`web/`), Docker packaging, and a full CI/CD pipeline — and the first real
subsystems are landing as part of the **RV reference deployment**
([ADR-010](docs/adr/ADR-010-rv-reference-deployment.md)): RV-C telemetry, the
Home Assistant integration, and the actuation safety policy. The Ops Agent,
RAG, and backup subsystems follow in later milestones (see issue
[#2](https://github.com/astrocyte-project/astrocyte/issues/2)).

```bash
make install        # set up Python (uv), web (npm), and git hooks
make check          # lint + type-check + tests (mirrors CI)
docker compose up   # run the API; then curl http://localhost:8000/health
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[development guide](docs/development.md) for details. Architecture decisions
live in [docs/adr/](docs/adr/), and the issue/label/milestone/board workflow is
documented in [docs/project-management.md](docs/project-management.md).

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) - see the [LICENSE](LICENSE) file for details.

The AGPLv3 ensures that this project remains open source and that any modifications or derivative works are also shared under the same license, maintaining the community's access to improvements and preventing proprietary forks from undermining the project's goals.
