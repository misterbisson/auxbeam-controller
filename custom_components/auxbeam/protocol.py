"""Frame encode/decode for the Auxbeam / Qunchen switch panel.

Pure logic, no Home Assistant or BLE imports — mirrors PROTOCOL.md and the
already-verified builder in tools/panel_bench.py so the two can't drift.
"""
from __future__ import annotations

NONE_NIBBLE = 8  # "leave this channel unchanged"

# nibble mode field (value >> 1)
MODE_TOGGLE = 0
MODE_MOMENTARY = 1
MODE_PULSED = 2
_MODE_NAMES = {MODE_TOGGLE: "toggle", MODE_MOMENTARY: "momentary", MODE_PULSED: "pulsed"}


def loop_count_from_name(name: str | None) -> int:
    """Gang count from the advertised BLE name, mirroring the vendor app's own rule:
    Controller12 -> 12, Controller6 -> 6, Controller4 -> 4, Controller10 -> 10, anything else 8."""
    name = name or ""
    if "Controller12" in name:
        return 12
    if "Controller6" in name:
        return 6
    if "Controller4" in name:
        return 4
    return 10 if "Controller10" in name else 8


def control_frame_length(loop_count: int, name: str | None = None) -> int:
    """Total FFF1 frame length the vendor app sends: 7 bytes for 12-gang, 6-gang and panels
    whose name contains Controller8; 5 bytes for everything else."""
    if loop_count in (12, 6) or "Controller8" in (name or ""):
        return 7
    return 5


def build_control_frame(channel: int, on: bool, loop_count: int = 12, mode: int = MODE_TOGGLE,
                        frame_length: int | None = None) -> bytes:
    """[loop_count][packed nibbles]; target channel = mode*2+on, others = 8. 1-based channel.
    The app sends a fixed-size buffer, so the frame is zero-padded up to frame_length."""
    if not 1 <= channel <= loop_count:
        raise ValueError(f"channel {channel} out of range 1..{loop_count}")
    nibbles = [NONE_NIBBLE] * loop_count
    nibbles[channel - 1] = mode * 2 + (1 if on else 0)
    if len(nibbles) % 2:
        nibbles.append(NONE_NIBBLE)
    body = bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))
    frame = bytes([loop_count]) + body
    return frame.ljust(frame_length or control_frame_length(loop_count), b"\x00")


def build_backlight_frame(brightness: int, rgb: tuple[int, int, int]) -> bytes:
    """FFF4: [brightness, R, G, B], each 0-255. Whole-panel; brightness is independent of RGB."""
    r, g, b = rgb
    return bytes([brightness & 0xFF, r & 0xFF, g & 0xFF, b & 0xFF])


def build_pulse_frame(value: int) -> bytes:
    """FFFA: single byte (wire range 4..50; inverted vs the app slider — see PROTOCOL.md)."""
    return bytes([value & 0xFF])


def _has_state_header(data: bytes, loop_count: int) -> bool:
    # The FFF1 write carries a leading loop-count byte; PROTOCOL.md flags whether the
    # FFF2 readback does too. Detect heuristically. TODO: pin down in Phase 0.
    return len(data) == loop_count // 2 + 1 and data[0] == loop_count


def parse_state(data: bytes, loop_count: int = 12) -> dict[int, dict]:
    """FFF2 payload -> {channel: {"on": bool|None, "mode": str|None}}. None = unchanged/none."""
    body = data[1:] if _has_state_header(data, loop_count) else data
    nibbles: list[int] = []
    for byte in body:
        nibbles.extend((byte >> 4, byte & 0xF))
    out: dict[int, dict] = {}
    for ch in range(1, loop_count + 1):
        nib = nibbles[ch - 1] if ch - 1 < len(nibbles) else NONE_NIBBLE
        if nib == NONE_NIBBLE:
            out[ch] = {"on": None, "mode": None}
        else:
            out[ch] = {"on": bool(nib & 1), "mode": _MODE_NAMES.get(nib >> 1)}
    return out


def parse_backlight(data: bytes) -> dict:
    """FFF4 payload -> {"brightness": int, "rgb": (r,g,b)}."""
    if len(data) >= 4:
        return {"brightness": data[0], "rgb": (data[1], data[2], data[3])}
    if data:
        return {"brightness": data[0], "rgb": (255, 255, 255)}
    return {"brightness": 0, "rgb": (255, 255, 255)}
