"""Config flow — discover the panel over Bluetooth or pick it from a scan."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, NAME_PREFIX


def _is_panel(info: BluetoothServiceInfoBleak) -> bool:
    # TODO(Phase 0): confirm the advertised name really starts with "Controller".
    # FFF0 alone is too generic to match on; the name prefix is the reliable signal.
    return (info.name or "").startswith(NAME_PREFIX)


class AuxbeamConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the panel."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: BluetoothServiceInfoBleak | None = None
        self._discoveries: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Triggered automatically when HA sees a matching advertisement."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_panel(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovered = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered.name or self._discovered.address, data={}
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self._discovered.name or self._discovered.address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual entry point: choose from scanned panels."""
        if user_input is not None:
            address = user_input["address"]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discoveries[address].name or address, data={}
            )

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            if info.address in current or not _is_panel(info):
                continue
            self._discoveries[info.address] = info

        if not self._discoveries:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): vol.In(
                        {a: (i.name or a) for a, i in self._discoveries.items()}
                    )
                }
            ),
        )
