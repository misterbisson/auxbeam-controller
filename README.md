# auxbeam-controller

Control an **Auxbeam AC-1200** 12-gang RGB switch panel from **Home Assistant** and **HomeKit** using
an **ESP32 (ESPHome)** as a Bluetooth LE bridge — no vendor app required. This repo documents the
panel's BLE protocol and provides a ready-to-flash ESPHome config.

> **Unofficial.** Not affiliated with, authorized by, or endorsed by Auxbeam or Qunchen. Product and
> app names are used only to describe interoperability.

## Why
The panel is a two-part system (dash panel + engine-bay control box, 12 circuits, ≤100 A, in
toggle/momentary/pulsed modes) with **no local API, no MQTT, no HTTP** — the only programmable
interface is BLE, and the vendor app is a closed box. Reverse-engineering that BLE link turns every
circuit into a normal Home Assistant entity, and HomeKit follows for free via HA's HomeKit Bridge.
The ESP32 rides in the vehicle as the sole BLE client, so range and the single-connection limit stop
being problems, and the wired panel + RF remote keep working as independent overrides.

## What's here
- **[PROTOCOL.md](PROTOCOL.md)** — the full decoded BLE protocol (GATT map, frame formats, state
  feedback) plus a hardware-verification checklist.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the whole system fits together: diagram, entity map,
  and the power/RF/single-central realities that make or break it.
- **[switchpanel-bridge.esphome.yaml](switchpanel-bridge.esphome.yaml)** — the ESP32 bridge: 12
  switches, an RGB backlight light, a pulse-timing number, and FFF2 state feedback.
- **[HARDWARE.md](HARDWARE.md)** — a rugged in-vehicle build (Olimex ESP32-GATEWAY-EA + automotive
  power front-end + external antenna): bill of materials, wiring, and ESPHome board notes.

## Status
The protocol was decoded **from the vendor app, ahead of hardware.** The frame bytes are exact, but
items marked *verify* in PROTOCOL.md (no-PIN connect, whether the panel notifies on physical/RF
changes, readback framing, pulse units) still want a bench check against a real panel.
**Bench reports welcome** — see [Contributing](#contributing).

## Quick start
1. Flash `switchpanel-bridge.esphome.yaml` to an ESP32 (needs BLE — not an S2). Fill the two TODOs:
   your WiFi creds and the panel's BLE MAC (grab it with LightBlue/nRF Connect once the panel is powered).
2. Adopt the device in Home Assistant (ESPHome native API). You get 12 switches, a backlight light,
   and a pulse-time number.
3. For HomeKit, enable HA's **HomeKit Bridge** (or Homebridge) and expose those entities.

See ARCHITECTURE.md for the design, and PROTOCOL.md if you want to build your own client.

## Compatibility
The vendor app is `com.qunchen.ble.switchpanel` ("SwitchPanel"), a **Qunchen white-label** app
rebadged across brands. The same BLE core appears to back other `Controller4/6/8/10/12` panels and
rebrands (e.g. Rough Country's "Switch Control", `com.qunchen.ble.another2.switchpanel`), so this
protocol **may** apply to those too — unverified; confirm against your own hardware. The AC-1200
advertises a BLE name containing `Controller12`.

## How this was made / reproduce it
This is clean interoperability work: the protocol is documented from the app's own logic. This repo
does **not** redistribute the vendor app — reproduce the analysis yourself:

- App: `com.qunchen.ble.switchpanel`, version **2.1.2 (46)**,
  SHA-256 `77ff2ce1128ca9b49700afdc2c5635f0b45907921cbb542bdbec9bbbe94a6de3`.
- Obtain the APK (Play Store or a mirror), verify the hash, then `jadx -d out <apk>` and read
  `com/qunchen/ble/switchpanel/util/BleUtil.java` + `entity/LoopState.java`.

Reverse engineering for interoperability is protected in the US (DMCA §1201(f)) and EU (Software
Directive Art. 6); protocols and API facts aren't copyrightable. We publish the description, not the code.

## Contributing
Have an AC-1200 (or a sibling `Controller*` panel)? The most valuable contributions right now are
bench confirmations of the *verify* items in PROTOCOL.md, and reports of which other panels/brands
share the protocol. Open an issue with your panel model, the `nRF Connect` GATT dump, and what worked.

## ⚠️ Safety
This controls **high-current vehicle circuits** — some may drive winches or other momentary/
high-consequence loads. Keep those out of any automation (or manual-only). No warranty; use at your
own risk.

## License
[MIT](LICENSE) © 2026 Casey Bisson.
