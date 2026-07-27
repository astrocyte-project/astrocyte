# RV-C CAN Tap — Physical Install & Bring-Up

Physically connects the coach node to the Firefly RV-C network and validates
it **listen-only** (ADR-012). Nothing in this runbook transmits on the bus;
TX enablement is the final, separate section with its own gate.

## Hardware (on hand)

| Item | Spec |
|------|------|
| Isolated USB CAN adapter | CANable-class (CANable Pro / Makerbase / InnoMaker), green screw-terminal block, USB-C |
| Molex Micro-Fit 3.0 pigtail | **Square 2×2** connector (not inline 1×4), 4 wires |
| Coach node | Raspberry Pi 5 (see [coach-node-provisioning.md](coach-node-provisioning.md)) |

## 1. Flash candleLight firmware

Before first use, flash the adapter with **candleLight** firmware via the
vendor's web flasher (Chrome/WebUSB). candleLight presents as `gs_usb`, which
the Pi kernel drives natively as a SocketCAN interface.

## 2. Wire the pigtail → adapter

| Pigtail wire | Terminal |
|--------------|----------|
| Yellow | CAN-H |
| Green | CAN-L |
| Black | GND |
| **Red (12 V)** | **CUT AND TAPE OFF** — the Pi is AC-powered; 12 V here damages equipment |

## 3. Tap the network

The RV-C network is accessible at the **Firefly G12 board** (interior
electrical cabinet) or the **Vegatouch Eclipse module** — the square 2×2
Molex Micro-Fit socket. Snap in the pigtail; connect the adapter's USB-C to
the Pi.

## 4. Bring up the interface — listen-only

The systemd unit from the provisioning runbook configures:

```
ip link set can0 up type can bitrate 250000 listen-only on
```

RV-C runs at 250 kbit/s. `listen-only on` is a *kernel-level* guarantee no
frame (not even ACK bits) leaves the adapter — the bridge's `listen_only`
setting is the second, software-level layer (ADR-014).

## 5. Verify raw traffic

```bash
sudo apt install can-utils
candump -tA can0 | head -50
```

Expect a steady stream of extended-id frames (`1FFxx`/`1FExx`-pattern DGNs)
while any coach system is awake. No traffic → check pigtail seating and
CAN-H/CAN-L orientation.

## 6. Record the fixture session (do not skip)

Capture ≥15 minutes while exercising the coach — toggle lights, run a fan,
change a thermostat setpoint, watch tank levels:

```bash
candump -L can0 > coach-$(date +%Y%m%d).log
```

This capture:

1. replaces the synthetic fixtures in `tests/fixtures/rvc/` (same candump-L
   format — trim and commit a representative slice), and
2. reveals Firefly-proprietary DGNs (decoded as `UNKNOWN_*`) that need spec
   extensions — file findings on the RV deployment epic.

## 6a. Map fixtures to instances — one press at a time ⚠️

The bus says *instance 70 changed*, never *the bedroom ceiling changed*. Only a
narrated press links the two, and **how you narrate decides whether the result
is right**.

The obvious method — toggle every fixture in a stated order, then match the
first-ON transition per instance against the list — is how the reference coach's
first map was built, and **half of it was wrong**. One fixture that was already
on (so it never produced a first-ON) shifted every later name by one position.
The error survived review because the review re-checked the same ordering rather
than the fixtures. Ten of twenty entries were mislabelled, including a light
mapped onto a scene button.

Do this instead:

1. **One fixture per observation.** Press it, wait ~15 s, press it off, wait
   ~15 s. The gaps are the segmentation boundary.
2. **Confirm each before moving on**, or at minimum record which instance each
   press produced and check the list afterwards. A press that produces *no*
   frame is a finding, not a reason to press again.
3. **Start with a fixture you already know** as a sync marker — it proves your
   presses reach the bus, so a later silent fixture is unambiguous.
4. **Predict, then test.** Once a pattern appears (colour fixtures put their
   switch immediately below their R/G/B triplet), state the prediction and let
   the next press falsify it.

Useful signals while mapping:

- Colour fixtures animate continuously, so their channels are noisy. Take a
  quiet baseline first and compare **mean level per channel group** before and
  after a press — set membership is defeated by the animation.
- Level often partitions the coach: on the reference coach interior fixtures
  command at 250 and exterior ones at 200, which cross-checks the grouping.
- A master-off broadcasts the null instance (0xFF) and/or enumerates its group,
  which reveals group membership for free.

The finished map is **deployment inventory, not repo content** — keep it with
the operator's own records and mount it via `RVC_INSTANCE_MAP`
(`deploy/coach/config/rvc-instances.example.yml` documents the schema).

## 7. Start the bridge

With the coach stack up ([coach-node-provisioning.md](coach-node-provisioning.md)),
watch entities appear:

```bash
docker compose -f deploy/coach/compose.yaml logs -f rvc-bridge
docker compose -f deploy/coach/compose.yaml exec mosquitto \
  mosquitto_sub -t 'rvc/state/#' -v
```

In HA: Settings → Devices & Services → MQTT — one device per RV-C
(DGN, instance).

## 8. Enable TX — only after validation ⚠️

Gate: real captures decoded cleanly for days, command encodings verified
against observed Firefly command frames (compare `rvc/raw` captures of
touchscreen actions against `astrocyte.rvc.encoder` output for the same
action), and the policy file reviewed.

1. Remove `listen-only on` from the systemd unit; restart the interface.
2. Set `ASTROCYTE_RVC_LISTEN_ONLY=false` in `deploy/coach/.env`;
   `docker compose up -d rvc-bridge`.
3. Test one `control`-tier light command with a hand on the physical switch.
4. Only then consider flipping generator start from `deny` to `guarded` in
   `config/policy.yml` (ADR-014) — a deliberate, reviewed change.
