"""Channel switches (one per circuit)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities(
        AuxbeamChannelSwitch(panel, ch) for ch in range(1, panel.loop_count + 1)
    )


class AuxbeamChannelSwitch(AuxbeamEntity, SwitchEntity):
    """A single panel circuit."""

    def __init__(self, panel: AuxbeamPanel, channel: int) -> None:
        super().__init__(panel)
        self._channel = channel
        self._attr_unique_id = f"{panel.address}_ch{channel:02d}"
        self._attr_name = f"Channel {channel:02d}"

    @property
    def is_on(self) -> bool | None:
        return self._panel.channels.get(self._channel, {}).get("on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._panel.set_channel(self._channel, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._panel.set_channel(self._channel, False)
