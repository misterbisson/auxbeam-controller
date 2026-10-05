"""Config flow — discover the panel over Bluetooth or pick it from a scan."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_FRAME_LENGTH, CONF_LOOPS, DOMAIN, NAME_PREFIX
from .protocol import control_frame_length, loop_count_from_name


def _title(info: BluetoothServiceInfoBleak) -> str:
    # Identical panels advertise the same name, so add a short address suffix to tell them apart.
    short_id = info.address.replace(":", "").replace("-", "")[-4:].upper()
    return f"{info.name or 'Switch Panel'} {short_id}"


def _entry_data(info: BluetoothServiceInfoBleak) -> dict[str, Any]:
    loops = loop_count_from_name(info.name)
    return {CONF_LOOPS: loops, CONF_FRAME_LENGTH: control_frame_length(loops, info.name)}


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
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        if user_input is not None:
            return self.async_create_entry(
                title=_title(self._discovered), data=_entry_data(self._discovered)
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": _title(self._discovered)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual entry point: choose from scanned panels."""
        if user_input is not None:
            address = user_input["address"]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            info = self._discoveries[address]
            return self.async_create_entry(title=_title(info), data=_entry_data(info))

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
                        {a: _title(i) for a, i in self._discoveries.items()}
                    )
                }
            ),
        )
