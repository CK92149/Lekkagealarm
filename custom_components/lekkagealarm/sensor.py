"""Sensor platform for the LekkageAlarm integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers import device_registry, dispatcher, entity_registry

from .const import DOMAIN


class LekkageAlarmSensor(SensorEntity):
    """Sensor entity to show the last contact time with the collector server."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry_id: str, monitor=None) -> None:
        self._entry_id = entry_id
        self._monitor = monitor
        self._last_contact = monitor.last_contact_time if monitor else None
        self._attr_name = "LekkageAlarm Last Contact"
        self._attr_unique_id = f"{entry_id}_last_contact"

    @property
    def native_value(self):
        """Return the state (timestamp of last contact in ISO format)."""
        if not self._last_contact:
            return None
        return self._last_contact.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def async_added_to_hass(self) -> None:
        """Entity added to Home Assistant - set up dispatcher and device info."""
        ent_reg = entity_registry.async_get(self.hass)
        ent_entry = None
        if self._monitor:
            ent_entry = ent_reg.async_get(self._monitor.entity_id)
        if ent_entry and ent_entry.device_id:
            self._attr_device_info = device_registry.DeviceInfo(
                identifiers={(DOMAIN, self._entry_id)},
                name=(ent_entry.original_name or ent_entry.entity_id),
                via_device_id=ent_entry.device_id,
            )
        else:
            self._attr_device_info = device_registry.DeviceInfo(
                identifiers={(DOMAIN, self._entry_id)},
                name="LekkageAlarm Monitor",
            )

        self.async_on_remove(
            dispatcher.async_dispatcher_connect(
                self.hass, f"{DOMAIN}_{self._entry_id}_update", self._handle_update
            )
        )

    def _handle_update(self, last_time) -> None:
        """Handle an update from the LekkageAlarm monitor."""
        self._last_contact = last_time
        self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the LekkageAlarm sensor entity from a config entry."""
    monitor = hass.data[DOMAIN].get(entry.entry_id)
    sensor = LekkageAlarmSensor(entry.entry_id, monitor)
    async_add_entities([sensor])
