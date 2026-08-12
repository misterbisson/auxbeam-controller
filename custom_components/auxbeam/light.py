"""Whole-panel RGB backlight.

Unlike the ESPHome YAML (which pinned the panel's brightness byte to 0xFF and let ESPHome
scale RGB), the Python path honors the panel's real protocol: HA brightness -> the FFF4
brightness byte, HA color -> the RGB bytes, independently.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AuxbeamEntity
from .panel import AuxbeamPanel


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    panel: AuxbeamPanel = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AuxbeamBacklight(panel)])


class AuxbeamBacklight(AuxbeamEntity, LightEntity):
    """Panel legend backlight (single color, whole panel)."""

    _attr_name = "Backlight"
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    def __init__(self, panel: AuxbeamPanel) -> None:
        super().__init__(panel)
        self._attr_unique_id = f"{panel.address}_backlight"

    @property
    def is_on(self) -> bool:
        return self._panel.backlight["brightness"] > 0

    @property
    def brightness(self) -> int:
        return self._panel.backlight["brightness"]

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        return self._panel.backlight["rgb"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        current = self._panel.backlight
        brightness = kwargs.get(ATTR_BRIGHTNESS, current["brightness"] or 255)
        rgb = kwargs.get(ATTR_RGB_COLOR, current["rgb"])
        await self._panel.set_backlight(brightness, rgb)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._panel.set_backlight(0, self._panel.backlight["rgb"])
