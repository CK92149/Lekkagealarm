"""Constants for the LekkageAlarm integration."""

DOMAIN = "lekkagealarm"

# Configuration keys
CONF_COLLECTOR_URL = "collector_url"
CONF_PAIRING_CODE = "pairing_code"
CONF_TOKEN = "token"
CONF_ENTITY_ID = "entity_id"
CONF_ATTRIBUTE = "attribute"
CONF_MONITORED_STATES = "monitored_states"
CONF_HEARTBEAT_INTERVAL = "heartbeat_interval"

# Default values
DEFAULT_HEARTBEAT_INTERVAL = 3600  # seconds (1 hour)
DEFAULT_ATTRIBUTE = None

# Endpoints (appended to collector URL)
PAIR_ENDPOINT = "/pair"
EVENT_ENDPOINT = "/event"
HEARTBEAT_ENDPOINT = "/heartbeat"

# Other constants
ATTR_LAST_CONTACT = "last_contact"
