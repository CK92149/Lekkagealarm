"""Diagnostics support for LekkageAlarm."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    monitor = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    config_data = {**entry.data}
    if CONF_TOKEN in config_data:
        token = config_data[CONF_TOKEN]
        if isinstance(token, str) and len(token) > 4:
            config_data[CONF_TOKEN] = token[:4] + "****"
        else:
            config_data[CONF_TOKEN] = "****"

    diagnostics: dict = {
        "config_entry": {
            "data": config_data,
            "title": entry.title,
        },
        "monitor_status": None,
    }

    if monitor:
        diagnostics["monitor_status"] = {
            "entity_id": monitor.entity_id,
            "last_event_time": monitor.last_event_time.isoformat()
            if monitor.last_event_time
            else None,
            "last_event_value": monitor.last_event_value,
            "last_heartbeat_time": monitor.last_heartbeat_time.isoformat()
            if monitor.last_heartbeat_time
            else None,
            "last_contact_time": monitor.last_contact_time.isoformat()
            if monitor.last_contact_time
            else None,
        }

    return diagnostics
