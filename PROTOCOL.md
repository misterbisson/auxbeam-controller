# Auxbeam / Qunchen "SwitchPanel" BLE protocol

Reverse-engineered from `com.qunchen.ble.switchpanel` v2.1.2 (46), decompiled with jadx.
Source of truth: `jadx-out/sources/com/qunchen/ble/switchpanel/util/BleUtil.java` +
`entity/LoopState.java`. All facts below are read straight out of the app; items marked
**(verify)** are inferences to confirm against real hardware.

## TL;DR
- It's the best case: a **fixed-UUID GATT profile with short, unencrypted command frames** over
  Write-Without-Response. No pairing/PIN in the code path, no cloud, no account — 100% local BLE.
- One BLE central at a time (standard for these modules). If you never run the vendor app, your
  ESP32 owns the link uncontested; the wired panel and RF remote are separate paths and keep working.
- "Loop" = 回路 = **circuit/channel**. A 12-gang panel = 12 loops.

## Device identity
- Panels advertise a BLE **name containing `Controller<N>`**: `Controller12`, `Controller10`,
  `Controller8`, `Controller6`, `Controller4` (a momentary variant appends `M`, e.g. `Controller6M`).
  → The **AC-1200 (12-gang) should advertise as `Controller12`**. Use a name-contains filter on the ESP.
- BLE library in the app: `com.inuker.bluetooth.library` (BluetoothKit). Writes use `writeNoRsp`
  (Write **Without** Response). Connect uses defaults — **no bonding/PIN observed (verify)**.

## GATT table
Service **`0000fff0-0000-1000-8000-00805f9b34fb`** (short **FFF0**). Characteristics (short form):

| Char | Dir (app POV)     | Purpose                                   | App method            |
|------|-------------------|-------------------------------------------|-----------------------|
| FFF1 | write             | **Channel control** (on/off/mode)         | `writeControl`        |
| FFF2 | read + **notify** | **Channel state** (pushed on change)      | `readState`/parseState|
| FFF3 | read + notify     | Group definitions                         | `readGroup`           |
| FFF4 | write + notify    | RGB backlight color                       | `writeColor`          |
| FFF5 | write             | Save/remove group                         | `writeSaveGroup`      |
| FFF6 | read/write/notify | "K9" variant data (not on this panel)     | `writeK9`/readK9      |
| FFFA | read + write      | Pulse-mode timing config                  | `writePulse`/readPulse|
| FFFF | read              | Anti-clone CRC check — **ignore**         | `checkArc`            |

Notifications are subscribed on **FFF2, FFF3, FFF4**. **FFF2 is the important one** — the panel pushes
channel state here, so state changes made from the physical panel or RF remote *should* be reflected
without polling (**verify the firmware actually notifies on hardware-initiated changes**). There is
also a 500 ms-delayed `readState()` after every write as a belt-and-suspenders resync.

## Channel control — FFF1 (the money frame)
Frame = **1 header byte + N/2 packed nibbles**, one nibble per channel. For the 12-gang: **7 bytes**.

- **byte[0] = loop count** = `0x0C` (12). (8-gang → `0x08` and a 5-byte frame; 6-gang → 7 bytes.)
- Remaining bytes pack channel nibbles **big-endian, channel 1 = high nibble of byte[1]**:
  `byte[1] = (ch1<<4)|ch2`, `byte[2] = (ch3<<4)|ch4`, … `byte[6] = (ch11<<4)|ch12`.

### Nibble values (from `LoopState`)
`value = mode*2 + on`, where `on` is the low bit (**odd = ON**):

| Nibble | Meaning                          |
|--------|----------------------------------|
| 0 / 1  | Toggle mode — OFF / ON           |
| 2 / 3  | Momentary ("Stroke") — OFF / ON  |
| 4 / 5  | Pulsed ("Flash") — OFF / ON      |
| 8      | **Leave this channel unchanged** |

Every command sets the target channel's nibble and **8 (no-change) for all others**, so each write
touches exactly one channel. Same nibble encoding is used in the FFF2 state readback.

### Ready-made toggle-mode frames (write to FFF1, no response)
```
Ch   ON                        OFF
 1   0C 18 88 88 88 88 88       0C 08 88 88 88 88 88
 2   0C 81 88 88 88 88 88       0C 80 88 88 88 88 88
 3   0C 88 18 88 88 88 88       0C 88 08 88 88 88 88
 4   0C 88 81 88 88 88 88       0C 88 80 88 88 88 88
 5   0C 88 88 18 88 88 88       0C 88 88 08 88 88 88
 6   0C 88 88 81 88 88 88       0C 88 88 80 88 88 88
 7   0C 88 88 88 18 88 88       0C 88 88 88 08 88 88
 8   0C 88 88 88 81 88 88       0C 88 88 88 80 88 88
 9   0C 88 88 88 88 18 88       0C 88 88 88 88 08 88
10   0C 88 88 88 88 81 88       0C 88 88 88 88 80 88
11   0C 88 88 88 88 88 18       0C 88 88 88 88 88 08
12   0C 88 88 88 88 88 81       0C 88 88 88 88 88 80
```
Momentary ON ch1 = `0C 38 88 88 88 88 88`; pulsed ON ch1 = `0C 58 88 88 88 88 88`.
**No checksum on the control frame** — the bytes above are the entire payload.

## State readback — FFF2 (read or notify)
Payload is the same nibble packing (channel 1 = first nibble). Per channel: `odd = ON`, and the
mode is `nibble/2` (0=toggle, 1=momentary, 2=pulsed). **(verify)** the app's parser treats every hex
char as a nibble with **no** leading count byte — so FFF2 likely returns just the packed nibbles
(6 bytes for 12ch), unlike the FFF1 write which carries the `0x0C` header. Confirm on hardware.

## RGB backlight — FFF4 (write + notify, decoded)
Whole-panel backlight (there is **no per-channel color** — one color for all switch legends).
4-byte frame, Write-Without-Response, readback is the identical 4 bytes:

```
[ brightness, R, G, B ]      each byte 0x00–0xFF
```
- `brightness` = the app's backlight slider, **`android:max=255`** → **0–255** (a separate master-
  brightness byte, independent of the RGB values). Confirmed in `fgm_color.xml` + `parseColorData`.
- `R/G/B` = full 24-bit color from the picker (default presets: red/green/blue/yellow/purple/white).
- App throttles slider drags to one write per 100 ms; the final value is always sent.
- Example — full-brightness pure red: `FF FF 00 00`; half-brightness white: `80 FF FF FF`.

## Pulse config — FFFA (read + write, decoded)
1-byte pulse/flash timing used by channels in pulsed ("Flash") mode. **The wire byte is inverted
relative to the app slider**, which trips you up if you only read the layout:
- App slider is `android:max="46"` (range 0–46), but the app writes `value = 50 − sliderProgress`
  and reads back `sliderProgress = 50 − value` (`ModeFgm` `onStopTrackingTouch` / `onPulseEvent`).
- ⇒ **actual FFFA byte range = 4–50.** Slider left (0) → `0x32` (50); slider right (46) → `0x04` (4).
  Empty/default read → 4. So a **lower byte = longer travel on the slider** (units unconfirmed —
  likely tens of ms; **verify** on hardware).
- Single byte, Write-Without-Response, applies panel-wide to pulsed-mode channels.

## Other writes (for later)
- **Group save — FFF5**: `[0x01, groupIndex, memberCount, memberIdx1, memberIdx2, …]`.
- **Group remove — FFF5**: `[0x00, groupIndex]`.
- **FFFF**: app reads it and validates with an internal CRC (`ArrayCrcUtil`) purely to detect clones;
  it disconnects on mismatch. Irrelevant to controlling the panel — don't touch it.

## Hardware verification checklist (day one with the panel)
1. Scan (LightBlue/nRF): confirm name `Controller12` and service **FFF0** with chars FFF1/FFF2/FFF4…
2. Confirm connect needs **no PIN/bond**.
3. Write `0C 18 88 88 88 88 88` to **FFF1** (no response) → channel 1 should switch ON. Then `…08…` → OFF.
4. Subscribe to **FFF2** notify. Flip a **physical** switch → do you get a notification? (make-or-break
   for perfect HA state sync). Also read FFF2 and confirm the nibble layout / whether a header byte is present.
5. Note the panel's BLE **MAC** for the ESPHome `ble_client`.
