# Storage Directory

This directory contains JSON files that store the persistent state and configuration of the VEX TM Manager application.

---

## `actions.json`

This file defines the actions that are triggered in response to specific events or changes in field state.

### Structure

The root object has two main keys: `on_event` and `on_state_change`.

-   `"on_event"`: Actions triggered by a specific event from the Tournament Manager (e.g., `matchStarted`).
-   `"on_state_change"`: Actions triggered when a field transitions from one state to another (e.g., `standby->queued`).

Under each event or state transition, you can specify actions that apply to `"all"` fields or to a specific field ID (e.g., `"1"`, `"2"`).

### Example

```json
{
    "on_event": {
        "matchStarted": {
            "all": [
                {
                    "type": "audio",
                    "command": "play_playlist_track",
                    "metadata": {
                        "playlist_uri": "spotify:playlist:5paEjpgpPf5CkhuSHyJ66i"
                    }
                }
            ],
            "1": [
                {
                    "type": "lighting",
                    "command": "field_1_spotlight"
                }
            ]
        }
    },
    "on_state_change": {
        "standby->queued": {
            "all": [
                {
                    "type": "lighting",
                    "preset_id": "ready"
                }
            ]
        }
    }
}
```

---

## `config.json`

This file holds the main configuration for the application, including device IPs, credentials, and operational settings.

### Structure

-   `"device_ips"`: Contains connection details for external devices and services.
    -   `"spotify"`: `client_id`, `client_secret`, `redirect_uri`.
    -   `"atem"`: IP address of the ATEM switcher.
    -   `"zeros"`: IP and port for the ZerOS lighting console.
-   `"field_to_camera"`: Maps a field ID (string) to an ATEM camera ID (integer).
-   `"spotify_device_id"`: The name of the target Spotify device.
-   `"paused"`: A dictionary of booleans to globally pause control for `video`, `audio`, or `lighting`.
-   `"rooms"`: Configuration for different event rooms/layouts.

### Example

```json
{
    "device_ips": {
        "spotify": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "redirect_uri": "http://localhost:5000/spotify/callback"
        },
        "atem": "192.168.1.100",
        "zeros": {
            "ip": "192.168.1.101",
            "port": 8000
        }
    },
    "field_to_camera": {
        "1": 1,
        "2": 2
    },
    "spotify_device_id": "Main Speaker",
    "paused": {
        "video": false,
        "audio": false,
        "lighting": false
    },
    "rooms": {}
}
```

---

## `fields/field<N>.json`

Files in the `fields/` subdirectory store the real-time state of each competition field. Each file is named `field<N>.json`, where `<N>` is the field ID.

### Structure

-   `"field_id"`: The numeric ID of the field.
-   `"state"`: The current operational state of the field (e.g., `"standby"`, `"queued"`, `"active"`, `"finish"`).
-   `"match_name"`: The name of the match currently assigned to the field (e.g., `"Q25"`).
-   `"last_updated"`: An ISO 8601 timestamp of when the state was last modified.

### Example (`fields/field1.json`)

```json
{
    "field_id": 1,
    "state": "queued",
    "match_name": "Q25",
    "last_updated": "2023-10-28T10:00:00.000Z"
}
```

---

## Other Files

-   **`popups.json`**: Stores a list of currently active manual popups to be displayed on the frontend.
-   **`scheduled_matches.json`**: Contains information about the upcoming matches, used by the frontend to display scheduling information.

```
