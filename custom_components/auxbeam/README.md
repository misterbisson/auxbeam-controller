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
- **Advertised name** — the Bluetooth matcher + config-flow filter assume the name starts with
  `Controller`. Confirm the real advertisement.
- **No-PIN connect** — assumes just-works pairing.
