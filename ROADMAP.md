# Roadmap — Pi-first, graduate to ESP32 only if needed

The bridge logic is the same everywhere; only **which radio holds the BLE link** changes. So we start
with Home Assistant's own Bluetooth on the Raspberry Pi, and treat a dedicated ESP32 as a later,
optional upgrade — structured so graduating is a *radio move, not a rewrite*.

The one design choice that makes that true: **build the Pi integration on HA's Bluetooth stack**
(`bleak` via `bleak-retry-connector`/`habluetooth`), not against a raw local adapter. Connections then
route through *whatever* adapter HA knows about — the Pi's onboard radio today, or a remote ESP32
**Bluetooth Proxy** later — with no change to the integration or its entities.

## Phase 0 — Bench validation (any machine, ~30 min)
Run **[`tools/panel_bench.py`](tools/panel_bench.py)** (`pip install -r tools/requirements.txt`) against
the real panel before building anything. It scans for `Controller12`, connects (checks it's really
no-PIN), dumps the GATT table, reads/decodes **FFF2** state, watches for a notification when you flip a
*physical* switch, and — only if you pass `--channel N` — proves a write toggles that relay. It prints a
PASS/---- checklist mapping straight to [PROTOCOL.md](PROTOCOL.md)'s open *verify* items (no-PIN connect,
FFF2-on-physical-change, FFF2 framing, MAC/name, RSSI). **Read-only by default; it never actuates a
circuit unless you name one.** This de-risks every later phase.

```bash
python3 tools/panel_bench.py --scan-only                       # find it, check signal
python3 tools/panel_bench.py --address AA:BB:CC:DD:EE:FF        # connect + GATT + read + notify watch
python3 tools/panel_bench.py --address AA:BB:CC:DD:EE:FF --channel 1   # + prove a write (toggles ch1)
```

## Phase 1 — Pi-direct integration (ship it)
A small HA **custom integration** running on the Pi that:
- connects via HA's Bluetooth stack (proxy-transparent — see below),
- exposes stable entities: `switch.panel_ch_01…12`, `light.panel_backlight`, `number.panel_pulse_time`,
- writes FFF1 / FFF4 / FFFA and subscribes FFF2 for state.

Runs on the Pi's onboard BLE. If the Pi's Bluetooth is busy with other devices, drop in a **dedicated
USB BLE dongle** for the panel to avoid adapter contention. Pick the entity IDs now and keep them fixed
— dashboards and automations built on them survive the graduation untouched.

> **Faster-but-less-portable alternative:** a standalone `bleak`→MQTT systemd service (MQTT discovery
> entities). Quickest to ship and decoupled from HA internals, but it binds to a *specific local
> adapter*, so it does **not** get the free proxy graduation below — you'd switch to the ESPHome YAML
> instead. Use it if you want to hack fast; use the custom integration if you want the clean path.

## Phase 2 — Graduate to ESP32 (only if a trigger fires)
Default, **no-rewrite** route: flash an ESP32 as an **active-connection Bluetooth Proxy**
(ESPHome `bluetooth_proxy`) and mount it by the control box. HA's Bluetooth stack transparently routes
the Phase-1 integration's connection through it based on signal — **same code, same entities, you just
added a radio** near the panel. (Each proxy supports a few simultaneous active connections; one panel
is well within that.)

Alternative route: move the logic onto the ESP with the existing
[switchpanel-bridge.esphome.yaml](switchpanel-bridge.esphome.yaml) (`ble_client`). This fully decouples
panel control from Pi/HA uptime, at the cost of swapping the entity source (keep the same entity IDs to
minimize churn). Choose this if you specifically want the panel to keep working across HA restarts.

## What signals a graduation ("depending on need")
- HA logs show BLE **connect failures / timeouts**, or the panel's **RSSI is weak** from the Pi.
- Holding the panel's persistent connection **destabilizes other Pi BLE devices**.
- You **relocate the Pi** away from the control box, or box it behind metal.
- You want panel control to **survive HA restarts** → the `ble_client`-on-ESP alternative above.

## Why this ordering
Fewest moving parts first (no extra hardware to power/mount/flash), the protocol is already decoded, and
the Pi is in the van next to everything on an always-on local network. The ESP earns its place only if
range, adapter contention, or decoupling actually demand it — and because Phase 1 is built on HA's
Bluetooth stack, adding it then is cheap.
