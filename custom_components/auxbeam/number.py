"""Pulse-timing config (panel-wide, for pulsed-mode channels)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PULSE_MAX, PULSE_MIN
from .entity import AuxbeamEntity
from .panel import AuxbeamPanel


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    panel: AuxbeamPanel = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AuxbeamPulseTime(panel)])


class AuxbeamPulseTime(AuxbeamEntity, NumberEntity):
    """Raw FFFA pulse byte (4..50; inverted vs the app slider — see PROTOCOL.md)."""

    _attr_name = "Pulse Time"
    _attr_native_min_value = PULSE_MIN
    _attr_native_max_value = PULSE_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, panel: AuxbeamPanel) -> None:
        super().__init__(panel)
        self._attr_unique_id = f"{panel.address}_pulse"

    @property
    def native_value(self) -> float | None:
        return self._panel.pulse

    async def async_set_native_value(self, value: float) -> None:
        await self._panel.set_pulse(int(value))
