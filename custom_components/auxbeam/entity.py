"""Shared base entity."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .panel import AuxbeamPanel


class AuxbeamEntity(Entity):
    """Base for all panel entities: device info, availability, state callbacks."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, panel: AuxbeamPanel) -> None:
        self._panel = panel
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, panel.address)},
            identifiers={(DOMAIN, panel.address)},
            manufacturer="Auxbeam / Qunchen",
            model=f"{panel.loop_count}-gang switch panel",
            name="Auxbeam Panel",
        )

    @property
    def available(self) -> bool:
        return self._panel.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._panel.register_callback(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
