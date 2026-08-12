"""BLE connection manager for the panel.

Holds a persistent active connection via bleak-retry-connector (which routes over the
Pi's local adapter *or* an ESPHome Bluetooth Proxy transparently — that's the Phase 2
graduation path). Subscribes FFF2 for state and exposes write helpers.

STATUS: theoretical — not yet exercised against real hardware. Reconnect/notify behavior
and the FFF2 framing are pending Phase 0 validation (tools/panel_bench.py).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol
from .const import CHAR_BACKLIGHT, CHAR_CONTROL, CHAR_PULSE, CHAR_STATE

_LOGGER = logging.getLogger(__name__)


class AuxbeamPanel:
    """Owns the BLE link and the last-known panel state."""

    def __init__(self, ble_device: BLEDevice, loop_count: int = 12) -> None:
        self._ble_device = ble_device
        self._loop_count = loop_count
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._stopped = False
        self._callbacks: set[Callable[[], None]] = set()

        # last-known state (populated by reads + notifications)
        self.channels: dict[int, dict] = {ch: {"on": None, "mode": None}
                                           for ch in range(1, loop_count + 1)}
        self.backlight: dict = {"brightness": 0, "rgb": (255, 255, 255)}
        self.pulse: int | None = None

    # --- lifecycle ---------------------------------------------------------
    @property
    def loop_count(self) -> int:
        return self._loop_count

    @property
    def address(self) -> str:
        return self._ble_device.address

    @property
    def available(self) -> bool:
        return bool(self._client and self._client.is_connected)

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """HA hands us a fresh BLEDevice when routing changes (e.g. local <-> proxy)."""
        self._ble_device = ble_device

    def register_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.add(cb)
        return lambda: self._callbacks.discard(cb)

    def _notify_listeners(self) -> None:
        for cb in list(self._callbacks):
            cb()

    async def start(self) -> None:
        await self._ensure_connected()
        await self._read_all()

    async def stop(self) -> None:
        self._stopped = True
        if self._client:
            try:
                await self._client.stop_notify(CHAR_STATE)
            except Exception:  # noqa: BLE001 - best effort
                pass
            await self._client.disconnect()
            self._client = None

    # --- connection --------------------------------------------------------
    async def _ensure_connected(self) -> None:
        if self.available:
            return
        async with self._lock:
            if self.available:
                return
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.name or "auxbeam-panel",
                disconnected_callback=self._on_disconnect,
                ble_device_callback=lambda: self._ble_device,
            )
            self._client = client
            await client.start_notify(CHAR_STATE, self._on_notify)
            _LOGGER.debug("connected to panel %s", self.address)
        self._notify_listeners()

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("panel %s disconnected", self.address)
        self._client = None
        self._notify_listeners()
        if not self._stopped:
            # push device: reconnect proactively so we keep receiving FFF2 notifications
            asyncio.get_running_loop().create_task(self._reconnect())

    async def _reconnect(self) -> None:
        try:
            await self._ensure_connected()
            await self._read_all()
        except Exception as err:  # noqa: BLE001 - establish_connection already retried
            _LOGGER.debug("panel %s reconnect failed: %s", self.address, err)

    # --- reads / notifications --------------------------------------------
    async def _read_all(self) -> None:
        if not self._client:
            return
        try:
            self.channels = protocol.parse_state(
                bytes(await self._client.read_gatt_char(CHAR_STATE)), self._loop_count)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("read FFF2 failed: %s", err)
        try:
            self.backlight = protocol.parse_backlight(
                bytes(await self._client.read_gatt_char(CHAR_BACKLIGHT)))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("read FFF4 failed: %s", err)
        try:
            data = bytes(await self._client.read_gatt_char(CHAR_PULSE))
            self.pulse = data[0] if data else None
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("read FFFA failed: %s", err)
        self._notify_listeners()

    def _on_notify(self, _sender, data: bytearray) -> None:
        # FFF2 pushes channel state (incl. changes from the dash panel / RF remote —
        # PENDING Phase 0 confirmation that physical changes actually notify).
        self.channels = protocol.parse_state(bytes(data), self._loop_count)
        self._notify_listeners()

    # --- writes ------------------------------------------------------------
    async def set_channel(self, channel: int, on: bool, mode: int | None = None) -> None:
        if mode is None:
            # preserve the channel's configured mode so we don't flip momentary->toggle
            name = self.channels.get(channel, {}).get("mode")
            mode = {"momentary": 1, "pulsed": 2}.get(name, 0)
        await self._ensure_connected()
        frame = protocol.build_control_frame(channel, on, self._loop_count, mode)
        await self._client.write_gatt_char(CHAR_CONTROL, frame, response=False)
        self.channels[channel] = {"on": on, "mode": self.channels.get(channel, {}).get("mode")}
        self._notify_listeners()  # optimistic; FFF2 notify will correct if needed

    async def set_backlight(self, brightness: int, rgb: tuple[int, int, int]) -> None:
        await self._ensure_connected()
        await self._client.write_gatt_char(
            CHAR_BACKLIGHT, protocol.build_backlight_frame(brightness, rgb), response=False)
        self.backlight = {"brightness": brightness, "rgb": rgb}
        self._notify_listeners()

    async def set_pulse(self, value: int) -> None:
        await self._ensure_connected()
        await self._client.write_gatt_char(
            CHAR_PULSE, protocol.build_pulse_frame(value), response=False)
        self.pulse = value
        self._notify_listeners()
