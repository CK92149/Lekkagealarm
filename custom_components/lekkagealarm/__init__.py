"""LekkageAlarm integration initialization."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import aiohttp_client, dispatcher
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    DOMAIN,
    CONF_COLLECTOR_URL,
    CONF_PAIRING_CODE,
    CONF_TOKEN,
    CONF_ENTITY_ID,
    CONF_ATTRIBUTE,
    CONF_MONITORED_STATES,
    CONF_HEARTBEAT_INTERVAL,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_ATTRIBUTE,
    PAIR_ENDPOINT,
    EVENT_ENDPOINT,
    HEARTBEAT_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


def _validate_auth(obj: dict) -> dict:
    """Validate that at least one of token or pairing code is provided in YAML."""
    if not obj.get(CONF_TOKEN) and not obj.get(CONF_PAIRING_CODE):
        raise vol.Invalid(f"One of {CONF_TOKEN} or {CONF_PAIRING_CODE} must be provided.")
    return obj


# YAML configuration support
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.All(
                    vol.Schema(
                        {
                            vol.Required(CONF_COLLECTOR_URL): cv.url,
                            vol.Optional(CONF_TOKEN): cv.string,
                            vol.Optional(CONF_PAIRING_CODE): cv.string,
                            vol.Required(CONF_ENTITY_ID): cv.entity_id,
                            vol.Optional(CONF_ATTRIBUTE, default=DEFAULT_ATTRIBUTE): cv.string,
                            vol.Optional(CONF_MONITORED_STATES, default=[]): vol.All(
                                cv.ensure_list, [cv.string]
                            ),
                            vol.Optional(
                                CONF_HEARTBEAT_INTERVAL, default=DEFAULT_HEARTBEAT_INTERVAL
                            ): cv.positive_int,
                        }
                    ),
                    _validate_auth,
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the LekkageAlarm component from YAML configuration."""
    hass.data.setdefault(DOMAIN, {})
    _register_services(hass)

    if DOMAIN not in config:
        return True

    for conf in config[DOMAIN]:
        _LOGGER.debug("Importing LekkageAlarm config from YAML: %s", conf)
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "import"}, data=conf
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LekkageAlarm from a config entry (UI or import)."""
    hass.data.setdefault(DOMAIN, {})
    _register_services(hass)

    data = entry.data
    collector_url = data.get(CONF_COLLECTOR_URL)
    token = data.get(CONF_TOKEN)
    entity_id = data.get(CONF_ENTITY_ID)
    attribute = data.get(CONF_ATTRIBUTE) or None
    states = [s.lower().strip() for s in data.get(CONF_MONITORED_STATES, [])]
    interval = data.get(CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL)

    monitor = LekkageAlarmMonitor(
        hass, entry, collector_url, token, entity_id, attribute, states, interval
    )
    await monitor.async_start()
    hass.data[DOMAIN][entry.entry_id] = monitor

    try:
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    except AttributeError:
        await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    monitor: LekkageAlarmMonitor | None = hass.data[DOMAIN].pop(entry.entry_id, None)
    if monitor:
        await monitor.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    return bool(unloaded)


class LekkageAlarmMonitor:
    """Manage monitoring of one sensor and communication with the collector API."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        url: str,
        token: str,
        entity_id: str,
        attribute: str | None,
        trigger_states: list[str],
        interval: int,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.collector_url = url.rstrip("/")
        self.token = token
        self.entity_id = entity_id
        self.attribute = attribute
        self.trigger_states = [s.lower().strip() for s in trigger_states]
        self.heartbeat_interval = interval
        self._unsub_state = None
        self._unsub_heartbeat = None
        self.last_contact_time: datetime | None = None
        self.last_event_time: datetime | None = None
        self.last_event_value: str | None = None
        self.last_heartbeat_time: datetime | None = None

    async def async_start(self) -> None:
        """Start monitoring the sensor state and scheduling heartbeats."""

        @callback
        def _state_change_listener(event) -> None:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if new_state is None:
                return

            if self.attribute:
                new_val = new_state.attributes.get(self.attribute)
                old_val = old_state.attributes.get(self.attribute) if old_state else None
            else:
                new_val = new_state.state
                old_val = old_state.state if old_state else None

            if new_val is None:
                return

            str_new = str(new_val).lower()
            str_old = str(old_val).lower() if old_val is not None else None

            if str_new != str_old and (
                not self.trigger_states or str_new in self.trigger_states
            ):
                _LOGGER.info(
                    "LekkageAlarm: Detected state change for %s: %s -> %s",
                    self.entity_id,
                    str_old,
                    str_new,
                )
                self.hass.async_create_task(self._async_handle_trigger_event(str_new))

        self._unsub_state = async_track_state_change_event(
            self.hass, [self.entity_id], _state_change_listener
        )
        _LOGGER.debug("Started state change listener for %s", self.entity_id)

        if self.heartbeat_interval > 0:
            self._unsub_heartbeat = async_track_time_interval(
                self.hass,
                self._async_handle_heartbeat,
                timedelta(seconds=self.heartbeat_interval),
            )
            _LOGGER.debug(
                "Scheduled heartbeat every %s seconds for %s",
                self.heartbeat_interval,
                self.entity_id,
            )

        current_state = self.hass.states.get(self.entity_id)
        if current_state:
            if self.attribute:
                cur_val = current_state.attributes.get(self.attribute)
            else:
                cur_val = current_state.state
            if cur_val is not None:
                cur_val_str = str(cur_val).lower()
                if not self.trigger_states or cur_val_str in self.trigger_states:
                    _LOGGER.info(
                        "LekkageAlarm: Initial state of %s is '%s' which is a trigger, sending initial event.",
                        self.entity_id,
                        cur_val_str,
                    )
                    self.hass.async_create_task(
                        self._async_handle_trigger_event(cur_val_str)
                    )

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            lambda event: asyncio.create_task(self.async_stop()),
        )

    async def async_stop(self) -> None:
        """Stop monitoring and cancel scheduled tasks."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_heartbeat:
            self._unsub_heartbeat()
            self._unsub_heartbeat = None
        _LOGGER.debug("Stopped LekkageAlarm monitor for %s", self.entity_id)

    async def _async_handle_trigger_event(self, new_value: str) -> None:
        """Handle a state change that matches trigger states (send event to server)."""
        payload = {
            "token": self.token,
            "entity_id": self.entity_id,
            "attribute": self.attribute if self.attribute else "state",
            "new_state": new_value,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "state_change",
        }
        url = f"{self.collector_url}{EVENT_ENDPOINT}"
        success = await self._async_post_to_collector(url, payload)
        if success:
            self.last_event_time = datetime.utcnow()
            self.last_event_value = new_value
            self.last_contact_time = self.last_event_time
            dispatcher.async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.entry.entry_id}_update",
                self.last_contact_time,
            )

    async def _async_handle_heartbeat(self, now: datetime | None = None) -> None:
        """Send a periodic heartbeat to the collector server."""
        payload: dict[str, Any] = {
            "token": self.token,
            "entity_id": self.entity_id,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "heartbeat",
        }
        current_state = self.hass.states.get(self.entity_id)
        if current_state:
            if self.attribute:
                cur_val = current_state.attributes.get(self.attribute)
            else:
                cur_val = current_state.state
            if cur_val is not None:
                payload["current_state"] = str(cur_val)
        url = f"{self.collector_url}{HEARTBEAT_ENDPOINT}"
        success = await self._async_post_to_collector(url, payload)
        if success:
            self.last_heartbeat_time = datetime.utcnow()
            self.last_contact_time = self.last_heartbeat_time
            dispatcher.async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.entry.entry_id}_update",
                self.last_contact_time,
            )
            _LOGGER.debug("Heartbeat sent for %s", self.entity_id)

    async def _async_post_to_collector(self, url: str, payload: dict[str, Any]) -> bool:
        """Send a POST request to the collector URL with retries."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        for attempt in range(1, 4):
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        _LOGGER.debug(
                            "Collector response: %s",
                            text.strip() if text else "<no body>",
                        )
                        return True
                    _LOGGER.error(
                        "Collector API error (status %s) on attempt %d: %s",
                        resp.status,
                        attempt,
                        text.strip() if text else "<no body>",
                    )
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timeout connecting to collector API (attempt %d) for %s",
                    attempt,
                    url,
                )
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "Network error communicating with collector API (attempt %d): %s",
                    attempt,
                    err,
                )
            await asyncio.sleep(attempt)
        _LOGGER.error("Failed to send data to collector API %s after 3 attempts.", url)
        return False

    async def send_current_state(self) -> None:
        """Send the current state of the monitored sensor to the collector."""
        state_obj = self.hass.states.get(self.entity_id)
        if not state_obj:
            _LOGGER.error("Cannot send state: entity %s not found", self.entity_id)
            return

        if self.attribute:
            value = state_obj.attributes.get(self.attribute)
        else:
            value = state_obj.state

        if value is None:
            _LOGGER.error(
                "Cannot send state: attribute %s not found on entity %s",
                self.attribute,
                self.entity_id,
            )
            return

        await self._async_handle_trigger_event(str(value).lower())

    async def send_heartbeat(self) -> None:
        """Send a heartbeat immediately (manual trigger)."""
        await self._async_handle_heartbeat()


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if not hass.services.has_service(DOMAIN, "send_heartbeat"):
        hass.services.async_register(
            DOMAIN,
            "send_heartbeat",
            _async_handle_send_heartbeat,
            schema=vol.Schema({vol.Optional("entity_id"): cv.entity_ids}),
        )
    if not hass.services.has_service(DOMAIN, "send_state"):
        hass.services.async_register(
            DOMAIN,
            "send_state",
            _async_handle_send_state,
            schema=vol.Schema({vol.Optional("entity_id"): cv.entity_ids}),
        )


async def _async_handle_send_heartbeat(service_call: ServiceCall) -> None:
    """Service handler to send heartbeat(s) on demand."""
    hass = service_call.hass
    entity_ids = service_call.data.get("entity_id")
    targets: list[LekkageAlarmMonitor] = []

    if entity_ids:
        for monitor in hass.data.get(DOMAIN, {}).values():
            if isinstance(monitor, LekkageAlarmMonitor) and monitor.entity_id in entity_ids:
                targets.append(monitor)
    else:
        for monitor in hass.data.get(DOMAIN, {}).values():
            if isinstance(monitor, LekkageAlarmMonitor):
                targets.append(monitor)

    for monitor in targets:
        _LOGGER.info("Manual heartbeat trigger for %s", monitor.entity_id)
        await monitor.send_heartbeat()


async def _async_handle_send_state(service_call: ServiceCall) -> None:
    """Service handler to send current state on demand."""
    hass = service_call.hass
    entity_ids = service_call.data.get("entity_id")
    targets: list[LekkageAlarmMonitor] = []

    if entity_ids:
        for monitor in hass.data.get(DOMAIN, {}).values():
            if isinstance(monitor, LekkageAlarmMonitor) and monitor.entity_id in entity_ids:
                targets.append(monitor)
    else:
        for monitor in hass.data.get(DOMAIN, {}).values():
            if isinstance(monitor, LekkageAlarmMonitor):
                targets.append(monitor)

    for monitor in targets:
        _LOGGER.info("Manual state send trigger for %s", monitor.entity_id)
        await monitor.send_current_state()
