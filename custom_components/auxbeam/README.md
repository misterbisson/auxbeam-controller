# Auxbeam / Qunchen panel — Home Assistant custom integration (sketch)

> ⚠️ **THEORETICAL — NOT YET TESTED ON HARDWARE.** Every line here is written from the
> reverse-engineered protocol in [../../PROTOCOL.md](../../PROTOCOL.md); none of it has run against a
> real panel. Treat it as a design sketch that demonstrates feasibility, not a working integration.
> **Run [`tools/panel_bench.py`](../../tools/panel_bench.py) (Phase 0) first** and reconcile its
> findings before trusting any of this.

Phase 1 of the [roadmap](../../ROADMAP.md): a Pi-side integration built on Home Assistant's Bluetooth
stack (`bleak-retry-connector`), so connections route over the Pi's adapter today or an ESPHome
**Bluetooth Proxy** later with no code change.

## What it exposes
- `switch.*` — one per circuit (12 on an AC-1200), state fed by FFF2 notifications
- `light.*` "Backlight" — whole-panel RGB, honoring the panel's independent brightness byte
- `number.*` "Pulse Time" — the raw FFFA byte (4–50)

The backlight and pulse entities are only created when the panel actually has the FFF4 / FFFA
characteristic; older generations may not.

## Multiple panels and other gang counts
- **Add the integration once per control box.** Each panel is its own config entry, connection and
  device, keyed on its BLE address. Devices are named from the advertised name plus a short address
  suffix (e.g. `Controller12 A1B2`), because identical panels advertise the same name — rename them in HA.
- **Gang count is auto-detected** from the advertised name using the vendor app's own rule
  (`Controller12` → 12, `Controller6` → 6, `Controller4` → 4, `Controller10` → 10, anything else → 8), so
  an 8-gang AR-800 and a 12-gang AC-1200 can coexist.
- **All three 8-gang generations are matched.** Like the vendor app, the integration accepts any name
  containing `Controller` or `SwitchDevice` (see the table in [PROTOCOL.md](../../PROTOCOL.md#device-identity)).
  Auto-discovery only fires when the name *starts* with one of those; anything else can still be added
  by hand from **Add integration**. `Controller*` is a broad pattern, so HA may occasionally offer an
  unrelated Bluetooth device — just ignore it.
- **Control-frame length follows the vendor app:** it sends a fixed-size, zero-padded buffer — 7 bytes for
  12-gang, 6-gang and panels whose name contains `Controller8`, 5 bytes for everything else. The length is
  worked out from the advertised name at setup. The app's own 10-gang path does not fit its 5-byte buffer,
  so 10-gang frames are sent unpadded at 6 bytes and are the least certain case.

## Layout
| File | Role |
|------|------|
| `protocol.py` | frame encode/decode (mirrors the verified `tools/panel_bench.py`) |
| `panel.py` | persistent BLE connection, notify subscription, write helpers |
| `entity.py` | shared base (device info, availability, state callbacks) |
| `switch.py` / `light.py` / `number.py` | the three platforms |
| `__init__.py` | entry setup, BLE device refresh, platform forwarding |
| `config_flow.py` | Bluetooth auto-discovery + manual pick |
| `manifest.json` | deps, Bluetooth matchers, requirements |

## Install (once validated)
Copy `custom_components/auxbeam/` into your HA config's `custom_components/`, restart, then add the
integration (it should auto-discover a nearby `Controller*` panel).

## Open items that gate correctness (from Phase 0)
- **FFF2 framing** — does the state readback carry the leading `0x0C` header byte? `protocol.parse_state`
  auto-detects, but confirm.
- **Notify on physical/RF change** — the switch/light state only stays in sync if the panel actually
  pushes FFF2 on non-app changes.
- **Advertised name** — the Bluetooth matcher assumes the name starts with `Controller` or
  `SwitchDevice`; the config-flow filter accepts either anywhere in the name. Confirm the real
  advertisement.
- **8-gang generation** — which of the three name generations a given 8-gang (e.g. AR-800) is decides
  the frame length. Read it off a scan; `tools/panel_bench.py --frame-length` tests the other variant.
- **No-PIN connect** — assumes just-works pairing.
