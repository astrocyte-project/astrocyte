# Engine-Off Fuel Monitoring — GX Tank 140 + Cerbo GX

The Freightliner Cascadia sleeps its chassis CAN with the ignition off, which
blinds every interior display to fuel level while parked. This install reads
the chassis fuel sender continuously through the (house-lithium-powered)
Victron Cerbo GX, so the 120-gal tank is visible 24/7 in Victron, Home
Assistant (via the `victron_gx` integration), and astrocyte.

**Why it matters:** the Onan 12.5 kW generator shares the chassis tank and its
pickup tube sucks air at roughly ¼ tank (~30 gal). The alarm at 28–30%
protects generator prime while boondocking.

## Hardware (on hand)

**Victron GX Tank 140** (USB). Do **not** wire the truck's sender directly
into the Cerbo's analog inputs — the Tank 140 isolates the signal and
prevents backfeed/dash errors.

## 1. Find the signal

Chassis fuel level is **Circuit 428** — typically pink or light blue
(**verify against the chassis wiring diagram before cutting anything**).
Analog voltage ≈ **0.5 V full → 4.5 V empty**.

Tap points, best → worst:

1. **Firefly G12 panel** (interior electrical cabinet) — look for a terminal
   block labeled "Chassis Interface" or a loose fuel-level pigtail.
2. **Back-of-Cab (BOC) plug** — large Deutsch connector, driver-side frame
   rail behind the cab (the standard upfitter point).
3. **At the tank** — 2-pin connector on top of the driver-side fuel tank.

## 2. Connect

- Y-tap the signal wire → Tank 140 **Input (+)** (tap, don't cut — the dash
  still needs the sender when the ignition is on).
- Tank 140 ground (−) → coach common DC ground.
- Tank 140 USB → Cerbo GX.

## 3. Configure the Cerbo

1. `Settings → I/O → Analog Inputs` — enable the tank input.
2. Sensor type **Voltage**; fluid type **Fuel**.
3. Calibrate with measured voltages: record the reading now, again after the
   next fill-up, and near ¼ tank; enter the full/empty points.
4. Enable the **Boat & Motorhome overview** so fuel sits next to battery
   status on the GX display.
5. Set the low-fuel alarm at **28–30%**.

## 4. Surface it in Home Assistant

With the Cerbo on the coach LAN (see
[coach-node-provisioning.md](coach-node-provisioning.md)), HA's native
**Victron GX** integration (2026.5+, MQTT-based) discovers the Cerbo — the
Tank 140 appears as a tank sensor automatically. Then:

- confirm the fuel entity's id (e.g. `sensor.cerbo_tank_fuel_level`),
- add an HA automation notifying the companion app at 30% (redundant with the
  Victron alarm on purpose — prime loss is expensive), and
- the entity flows into `rv_status()` / `aios rv status` via the `fuel`
  group automatically.
