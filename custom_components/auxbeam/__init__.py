"""The Auxbeam / Qunchen switch panel integration.

STATUS: theoretical sketch — written from the reverse-engineered protocol (PROTOCOL.md),
NOT yet run against real hardware. Validate with tools/panel_bench.py (Phase 0) first.
"""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_LOOPS, DEFAULT_LOOPS, DOMAIN, PLATFORMS
from .panel import AuxbeamPanel

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address: str = entry.unique_id  # BLE address (set by the config flow)
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise ConfigEntryNotReady(f"Panel {address} not found (out of range or no adapter/proxy)")

    panel = AuxbeamPanel(ble_device, entry.data.get(CONF_LOOPS, DEFAULT_LOOPS))

    @callback
    def _async_update_ble(service_info: bluetooth.BluetoothServiceInfoBleak, change) -> None:
        # Keep the BLEDevice fresh so connections route to the best adapter/proxy.
        panel.set_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            bluetooth.BluetoothCallbackMatcher(address=address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    try:
        await panel.start()
    except Exception as err:  # noqa: BLE001 - surface as retryable
        raise ConfigEntryNotReady(f"Could not connect to panel {address}: {err}") from err

    entry.async_on_unload(panel.stop)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = panel
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
