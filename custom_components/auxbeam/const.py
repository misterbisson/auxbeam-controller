"""Constants for the Auxbeam / Qunchen switch panel integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "auxbeam"
PLATFORMS = [Platform.SWITCH, Platform.LIGHT, Platform.NUMBER]

# GATT map — see PROTOCOL.md
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHAR_CONTROL = "0000fff1-0000-1000-8000-00805f9b34fb"   # write: channel control
CHAR_STATE = "0000fff2-0000-1000-8000-00805f9b34fb"     # read + notify: channel state
CHAR_BACKLIGHT = "0000fff4-0000-1000-8000-00805f9b34fb"  # write + notify: [bright,R,G,B]
CHAR_PULSE = "0000fffa-0000-1000-8000-00805f9b34fb"      # read + write: pulse timing byte

# Panels advertise a name like Controller12 / Controller8 ... (confirm in Phase 0).
NAME_PREFIX = "Controller"

CONF_LOOPS = "loops"
DEFAULT_LOOPS = 12

# Pulse-timing wire byte range (inverted vs the app slider) — see PROTOCOL.md
PULSE_MIN = 4
PULSE_MAX = 50
