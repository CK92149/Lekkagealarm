# LekkageAlarm

[![Open your Home Assistant instance and show the add repository dialog with a specific repository URL.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lekkagealarm&repository=lekkagealarm)
> **If you are installing from a fork:** update the `owner` query parameter in the badge link to match your GitHub username (e.g., `owner=your-name&repository=lekkagealarm`). Using the placeholder `your-username` will result in a “repository not found” error in HACS.

**LekkageAlarm** is a Home Assistant custom integration that monitors a chosen sensor (or other entity) for specific states (e.g., a water leak sensor reporting "wet") and sends alerts to a remote collector service. It also periodically sends heartbeat messages to the remote server to confirm that your Home Assistant is online. This integration supports configuration via the Home Assistant UI (config flow) or via YAML, and uses a secure pairing process to exchange a one-time code for a permanent authentication token.

## Features

- **Configurable Sensor Monitoring:** Select any entity (sensor, binary_sensor, etc.) and an attribute (optional) to monitor. Specify which state value(s) (e.g., `"wet"`, `"dry"`, `"on"`, `"off"`) will trigger an alert.
- **Cloud Notifications:** On a state change that matches the configured trigger values, the integration sends an HTTP request to your configured collector API URL with details of the event.
- **Heartbeat Signal:** Sends periodic heartbeat messages (by default every hour) to the collector API to indicate the system is running. The interval is configurable.
- **Secure Pairing:** Uses a one-time pairing code (provided by your leak monitoring service) to fetch a permanent token from the collector server. The token is stored securely in Home Assistant's config storage and used for all subsequent requests.
- **Dual Configuration Modes:** Supports both **UI setup** (via Integrations UI with a config flow) and **YAML configuration** (for users who prefer `configuration.yaml`). You can choose either method.
- **Error Handling & Retries:** Handles network failures with retries and logs errors to Home Assistant logs for troubleshooting. The integration also supports Home Assistant's diagnostics feature for detailed troubleshooting info.
- **Manual Trigger Services:** Provides services `lekkagealarm.send_heartbeat` and `lekkagealarm.send_state` to manually trigger data sending and supports diagnostic information for troubleshooting.
- **Latest Home Assistant Compatible:** Designed for compatibility with recent Home Assistant versions (no specific minimum version is hard-coded).

## Installation

### HACS (Home Assistant Community Store)

1. **Add Custom Repository:** In HACS, go to **Integrations**, click the three dots menu > **Custom repositories**, and add this repository's URL (GitHub `lekkagealarm/lekkagealarm`) as an Integration. If you are using a fork, replace the owner with your GitHub username (e.g., `your-name/lekkagealarm`).
2. **Install Integration:** After adding the repo, find **LekkageAlarm** in the HACS integrations list and click **Download**. Alternatively, click the blue **Add to HACS** badge above to open HACS directly with this repository (ensure the `owner` query parameter matches the repository you are installing).
3. **Restart Home Assistant:** After installation, restart Home Assistant to load the new integration.

### Manual Installation

1. Download or clone this repository.
2. Copy the `custom_components/lekkagealarm` folder into your Home Assistant configuration's `custom_components` directory (usually `/config/custom_components/`).
3. Restart Home Assistant to recognize the new integration.

## Configuration

You can configure the integration either via the UI or via YAML:

### Option 1: UI Configuration (Config Flow)

1. After installation and restart, go to **Settings > Devices & Services > Add Integration** and search for "**LekkageAlarm**".
2. Select **LekkageAlarm**. In the config flow:
   - **Collector URL:** Enter the base URL of the collector API provided by your leak monitoring service (e.g., `https://api.example.com/leak`).
   - **Pairing Code:** Enter the one-time pairing code obtained from your collector service (to retrieve an auth token).
   - **Entity to Monitor:** Choose the Home Assistant entity (device or helper) you want to monitor for leaks/alerts (for example, your water leak sensor).
   - **Attribute (optional):** If you want to monitor a specific attribute of the entity (e.g., `battery_level` or a `battery_low` flag) instead of the entity's main state, enter the attribute name. Leave blank to monitor the entity's state.
   - **Trigger States:** Enter one or more state values that should trigger an alert, comma-separated. For example, for a leak sensor you might enter `wet,dry` (to report both transitions) or just `wet` to only report when a leak is detected. **Note:** For binary sensors, use the actual state values (`"on"`, `"off"`) or their equivalent (e.g., `"wet"` corresponds to `"on"` if device class is moisture).
   - **Heartbeat Interval:** Optionally adjust the heartbeat interval (in seconds). The default is 3600 seconds (1 hour).
3. Submit the form. The integration will contact the collector server at the provided URL to exchange the pairing code for a token. If successful, the config entry will be created. If pairing fails (invalid code or network error), you will be notified to correct the inputs.
4. Once configured, the integration will start monitoring the chosen entity and sending data to the collector service. A new sensor entity named **"LekkageAlarm Last Contact"** will be created, showing the timestamp of the last successful communication (event or heartbeat) with the server.

You can edit the integration later by clicking **Configure** on the LekkageAlarm entry in **Settings > Devices & Services**, or remove and re-add it to change the monitored entity or pairing.

### Option 2: YAML Configuration (alternative)

Instead of the UI, you can add configuration in your `configuration.yaml`. This is optional; the UI method is recommended. Example YAML configuration:

```yaml
lekkagealarm:
  - collector_url: "https://api.example.com/leak"
    pairing_code: "ABC12345"
    entity_id: binary_sensor.water_leak_sensor_1
    attribute: water  # optional, e.g., an attribute name to monitor (leave out for main state)
    monitored_states: ["wet", "dry"]
    heartbeat_interval: 3600  # in seconds
```

**YAML notes:** On Home Assistant startup, the integration will use the `pairing_code` to retrieve a token from the `collector_url` (unless a token is provided directly). The token will not be written back to YAML, but will be stored in Home Assistant's internal storage. It is recommended to switch to UI configuration after initial pairing, or manually update the YAML with the token once obtained (you can find it in the logs or diagnostics for verification). You can also provide `token` in YAML instead of `pairing_code` if you already have it, to skip the pairing step.

## How It Works
- **State Change Monitoring:** The integration listens for changes on the specified entity (and attribute, if set). When the entity's state (or the chosen attribute's value) changes, it checks if the new value matches any of the configured trigger states. If it matches, LekkageAlarm will send an HTTP POST request to the collector API's event endpoint (`${collector_url}/event`) containing the sensor's ID, the new state, and a timestamp, along with the authentication token.
- **Heartbeat:** Independently, LekkageAlarm will send a heartbeat POST to the collector API (`${collector_url}/heartbeat`) at the configured interval. This message indicates that Home Assistant is alive and includes the token (and optionally the current status of the sensor).
- **Pairing Token:** During setup, a call is made to `${collector_url}/pair` with your pairing code. The server should respond with a permanent token (e.g., a UUID or key). This token is stored in the integration's config entry (not visible in the UI for security). All future requests include this token for authentication. If pairing fails, no config entry is created.
- **Data Format:** The integration sends JSON in the request body. For example, an event might be sent as:

  ```json
  {
    "token": "<your_token>",
    "entity_id": "binary_sensor.water_leak_sensor_1",
    "attribute": "water",
    "new_state": "wet",
    "timestamp": "2026-01-01T12:00:00Z",
    "type": "state_change"
  }
  ```

  A heartbeat message is similar but may have `"type": "heartbeat"` and omit sensor specifics or include current state.
- **Retries:** If the HTTP request to the collector fails (due to network issues or server error), LekkageAlarm will log an error and retry a few times with a short delay. If all retries fail, it will wait until the next state change or heartbeat interval to try again. All errors are logged with the integration name for visibility.

## Services

This integration registers two services in Home Assistant:
- `lekkagealarm.send_heartbeat` – Triggers an immediate heartbeat ping to the collector API, outside the regular schedule. You can call this service (e.g., from Developer Tools > Services) to force a heartbeat. By default it will send for all configured LekkageAlarm instances. You can specify `entity_id` of the monitored sensor (or a list of them) in the service data to send heartbeat only for specific instance(s).
- `lekkagealarm.send_state` – Immediately sends the current state of the monitored sensor to the collector API (same as if an event just occurred). Useful for testing or on-demand sync. It accepts an optional `entity_id` (of the monitored sensor) in service data; if none is given, it sends updates for all configured instances.

Example use in an automation (triggering a heartbeat every day at noon):

```yaml
automation:
  - alias: Daily Leak Alarm Heartbeat
    schedule:
      - cron: "0 12 * * *"
    action:
      - service: lekkagealarm.send_heartbeat
```

## Diagnostics & Logging

- **Logging:** To assist with troubleshooting, this integration logs significant events and errors. If you need more detailed logs, enable debug logging for `custom_components.lekkagealarm` in your Home Assistant `configuration.yaml`:

  ```yaml
  logger:
    default: info
    logs:
      custom_components.lekkagealarm: debug
  ```

  This will output detailed debug information about pairing, state changes, and HTTP requests in your Home Assistant log.

- **Diagnostics:** Home Assistant's Download Diagnostics feature is supported. You can retrieve a diagnostics report for the LekkageAlarm integration (via Settings > Devices & Services > ... > Download Diagnostics on the integration) which will include the integration configuration and recent status (token information is redacted). This can be useful to provide to developers or support if you're troubleshooting an issue.

## Security

The authentication token obtained from the collector is stored in Home Assistant's config entry (not in plaintext YAML) and is not exposed in the UI. If you need to revoke or change the token, remove and re-add the integration (or update the YAML config with a new token). The integration communicates with the collector URL you provide; ensure this is over HTTPS for security if sending over the internet.

## License

This project is provided as open-source under the MIT license.
