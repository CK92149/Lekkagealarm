"""Config flow for the LekkageAlarm integration."""
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import aiohttp_client

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
    PAIR_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class LekkageAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LekkageAlarm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step (UI setup)."""
        errors = {}
        if user_input is not None:
            states_str = user_input.get(CONF_MONITORED_STATES, "")
            monitored_states = [s.strip() for s in states_str.split(",") if s.strip()]
            if not monitored_states:
                errors["base"] = "pair_failed"
            else:
                try:
                    token = await self._async_pair(
                        user_input[CONF_COLLECTOR_URL], user_input[CONF_PAIRING_CODE]
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("Pairing failed in config flow: %s", err)
                    errors["base"] = "pair_failed"
                if not errors:
                    data = {
                        CONF_COLLECTOR_URL: user_input[CONF_COLLECTOR_URL],
                        CONF_TOKEN: token,
                        CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                        CONF_ATTRIBUTE: user_input.get(CONF_ATTRIBUTE) or None,
                        CONF_MONITORED_STATES: monitored_states,
                        CONF_HEARTBEAT_INTERVAL: user_input.get(
                            CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL
                        ),
                    }
                    await self.async_set_unique_id(
                        f"{data[CONF_COLLECTOR_URL].rstrip('/')}-"
                        f"{data[CONF_ENTITY_ID]}-{data[CONF_ATTRIBUTE] or 'state'}"
                    )
                    self._abort_if_unique_id_configured()
                    name = data[CONF_ENTITY_ID]
                    state_obj = self.hass.states.get(data[CONF_ENTITY_ID])
                    if state_obj and state_obj.name:
                        name = state_obj.name
                    return self.async_create_entry(
                        title=f"{name} LekkageAlarm", data=data
                    )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_COLLECTOR_URL): str,
                vol.Required(CONF_PAIRING_CODE): str,
                vol.Required(CONF_ENTITY_ID): str,
                vol.Optional(CONF_ATTRIBUTE, default=""): str,
                vol.Required(CONF_MONITORED_STATES): str,
                vol.Optional(
                    CONF_HEARTBEAT_INTERVAL, default=DEFAULT_HEARTBEAT_INTERVAL
                ): int,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_import(self, import_config: dict):
        """Handle YAML import setup."""
        await self.async_set_unique_id(
            f"{import_config[CONF_COLLECTOR_URL].rstrip('/')}-"
            f"{import_config[CONF_ENTITY_ID]}-"
            f"{import_config.get(CONF_ATTRIBUTE) or 'state'}"
        )
        self._abort_if_unique_id_configured()

        if not import_config.get(CONF_TOKEN) and import_config.get(CONF_PAIRING_CODE):
            try:
                token = await self._async_pair(
                    import_config[CONF_COLLECTOR_URL], import_config[CONF_PAIRING_CODE]
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Pairing failed during YAML import: %s", err)
                return self.async_abort(reason="pair_failed")
            import_config[CONF_TOKEN] = token

        import_config.pop(CONF_PAIRING_CODE, None)
        return self.async_create_entry(title=import_config[CONF_ENTITY_ID], data=import_config)

    async def _async_pair(self, base_url: str, code: str) -> str:
        """Call the pairing endpoint and return the token."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        pair_url = f"{base_url.rstrip('/')}" + PAIR_ENDPOINT
        async with session.post(pair_url, json={"code": code}, timeout=10) as resp:
            if resp.status != 200:
                _LOGGER.error("Pairing API returned status %s", resp.status)
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json(content_type=None)
            token = data.get("token")
            if not token:
                _LOGGER.error("No token in pairing response.")
                raise Exception("No token received")
            _LOGGER.info("LekkageAlarm paired successfully (token received).")
            return token
