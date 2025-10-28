# VEX TM Manager Tools

This README documents the runtime architecture used by this project.

## Overview

The application runs five main concurrent threads (or worker processes) that cooperate via a single event queue and a set of JSON files used as the persistent configuration/state store.


Threads:

1. Frontend / UI thread
2. Event processor (worker) that reads events from the queue
3. Schedule fetcher thread (fetches match schedule and persists it locally)
4. Match scheduler thread (reads local schedule and enqueues timed "match_scheduled" events)
5. Websocket connector that subscribes to the VEX/TM Manager API and dumps incoming events into the queue


## Shared components

- Event queue: a reliable in-process or IPC-backed queue (e.g., Python Queue, Redis list, or an OS queue) — all events received by the websocket connector are pushed into this queue. The event processor consumes events from this queue. The frontend may also push manual events into the same queue for immediate processing.
- JSON files (single-source JSON storage for now):
  - `fieldX.json` — per-field state files (one file per field; e.g., `field1.json`, `field2.json`, ...). Each contains the canonical state for that field (queued, countdown, active, finish, timestamps, current match id, etc.).
  - `actions.json` — mapping of event types and field state transitions to actions. Actions can define lighting, video, audio commands (referenced by name/ID) to be executed when triggered.
  - `config.json` — constants and global configuration editable by the frontend (device IPs, mappings like field->camera, spotify device id, websocket endpoints, and other non-secret runtime constants).
  - `schedule.json` — the raw match schedule fetched from an external source by the schedule fetcher thread. This will be updated periodically and written atomically.
  - `scheduled_matches.json` — a derived, time-indexed view (or subset) of the schedule that the match scheduler will write when matches become imminent; this file will be consumed by the frontend API to drive room pop-ups and display pages.
  - `popups.json` — a short-lived list of active manual or system-generated pop-ups for rooms (message, room id, start, end, priority). The event processor will write this file atomically when it processes `manual_popup` events or other popup-producing events.

All state and configuration uses plain JSON files. The system reads and writes these files atomically (e.g., write to a temp file and rename) to avoid corruption.

## Object & model architecture

- The codebase will adopt a small, explicit domain model to make processing, validation, and testing straightforward. Domain classes will live under the `models/` package and will be the canonical in-memory representations that are serialized to/from JSON when persisting state or exchanging events.
- Key model types that will be implemented:
  - `Event` — will represent a normalized incoming event. It will include: `id` (string), `type` (string), `timestamp` (ISO 8601 string), optional `field` (string), and `payload` (object). `Event` instances will be validated on ingest.
  - `FieldState` — will represent the canonical state for a field and mirror `fieldX.json` shape: `field_id`, `state`, `match_id`, `last_updated`, plus optional metadata (countdowns, timer values). The event processor will be the authoritative writer of `FieldState` instances.
  - `Action` — will represent a single device action and will be implemented as a small class hierarchy. There will be a base `Action` parent class with common fields (id, type, optional target device, metadata, and retry policy), plus concrete subclasses for categories like `LightingAction`, `VideoAction`, and `AudioAction` that carry typed payloads (preset id, camera id, spotify command, etc.).
    - Example hierarchy:
      - `Action` (base)
        - `LightingAction` (preset id, intensity, transition)
        - `VideoAction` (camera id, transition type, duration)
        - `AudioAction` (device id, command, volume)
          - `SpotifyAction` (playlist/track id, start offset, play/pause/seek semantics)
    - `Action` objects (and their concrete subclasses) will be the unit the processor sends to device controller modules. Controller modules will prefer typed `Action` subclasses over raw JSON for clarity and type safety.
  - `ActionMapping` — will represent mappings loaded from `actions.json` (for example: on_event or on_state_change entries). `ActionMapping` objects will be used by the processor to translate `Event` or `FieldState` transitions into zero or more `Action` instances.
  - `Config` — will represent values in `config.json` (device addresses, field->camera map, paused categories). `Config` will be reloaded on change and keyed by a version or timestamp so the processor can make decisions against a consistent snapshot.
  - `Config` — will represent values in `config.json` (device addresses, field->camera map, paused categories). `Config` will be reloaded on change and keyed by a version or timestamp so the processor can make decisions against a consistent snapshot. It will also include schedule-related controls such as `schedule_lead_matches` and a `match_queue_pause` object with `start` and `end` ISO-8601 timestamps for temporary suspensions of match-queue notifications.
  - `AuditEntry` — will represent a minimal runtime log entry written to `events.log` for processed events and action outcomes.

- Implementation notes and contracts:
  - All model types will implement JSON (de)serialization and schema validation. A lightweight validation layer will ensure backward-compatible schema evolution (versioned fields or tolerant parsing for missing keys).
  - The `Event` model will be the single shape accepted into the central event queue; the websocket connector and the frontend will both produce `Event`-compatible JSON.
  - `FieldState` instances will only be written by the event processor. Writes will be atomic (write temp + rename) and guarded by a file lock or in-process mutex when the JSON store is used.
  - `Action` instances will be executed by device controller modules (located under `modules/`); controllers will accept typed model objects rather than raw JSON where practical.
  - The event processor will consult a `Config` snapshot immediately before executing any `Action` (for pause toggles and other runtime flags). `Config` will include explicit `paused` flags for categories like `video`, `audio`, and `lighting`.
  - Model classes will be small and focused to make unit testing easy. Unit tests will cover: event validation, state transitions, action mapping, and config-driven short-circuiting (pauses).

- Extensibility:
  - New action types or device drivers will be added by introducing a new `Action` subtype and a matching controller module. `actions.json` will remain the mapping surface and will be versioned when adding new semantics.
  - Action mapping logic will be pluggable so custom processors or rules engines can be introduced later without changing the on-disk mapping format.


## Thread responsibilities

1) Frontend / UI thread
- Hosts the Flask web UI.
- Responsibilities:
  - Display `fieldX.json` status for each field in real time (polling or server-sent events/websockets from the local backend).
  - Allow editing of `config.json` (saving updates back to disk immediately).
  - Provide manual controls to trigger actions (lighting presets, camera switches, audio cues). Manual triggers typically post a structured JSON event into the event queue so the event processor handles execution and keeps canonical state in sync.
  - Provide a dedicated "Pause" page in the UI that exposes toggles to pause/resume each category of automated actions: video, audio, and lighting. Toggling a pause will update `config.json` (atomically) with the new pause state for the relevant category, which persists across restarts and is visible to all components.
  - Show the event queue status (optional): recent events received and their processing state.
  - Public room page: add a new page accessible without login where an operator (or audience member) can enter a room number. This page will:
    - Display the room's configured YouTube live stream embed.
    - Subscribe (via polling or SSE/websocket) to the scheduled matches API and show lightweight pop-ups/notifications when a team assigned to that room has a scheduled match that is imminent.
    - Not require authentication; room access will be guarded only by the room number entry.
  - Admin room management page: add an admin-only UI where administrators can add rooms, assign a YouTube stream URL to a room, and edit the list of teams assigned to each room. Changes will be written to `config.json` (or a small `rooms.json` if preferred) and will take effect immediately.
  - Manual pop-ups UI: add a small admin/operator page to compose and send immediate pop-ups to a specific room. The form will include: room id, message/title, optional attached team or match id, duration (seconds), and priority. Submitting the form will POST to a server API (for example, `/api/send_popup`) which will create a normalized `Event` of type `manual_popup` and push it into the central event queue. The event processor will handle these events and write `popups.json` so room pages receive the notification.

Notes:
- When a user applies a manual action via the primary controls, the frontend should normally post a structured JSON event to the queue (same schema as events from the websocket connector) so the event processor handles execution and canonical state updates.
- The "Pause" toggles update `config.json`. The event processor MUST consult `config.json` immediately before executing any mapped action and must skip or short-circuit actions for categories that are currently paused. This ensures manual pauses via the UI are honored by automated processing.

- API surface for schedule display:
  - The server will expose a small read-only API endpoint (for example, `/api/scheduled_matches`) which will serve the contents of `scheduled_matches.json`. The frontend's public room page will use this endpoint to detect upcoming matches and fire pop-ups for the relevant room.
  - The server will also expose a small read-only endpoint (for example, `/api/popups`) which will serve `popups.json` for the public room page to consume in near-real-time (polling or SSE). The `/api/send_popup` POST endpoint will accept manual pop-up requests from the admin/operator UI, validate them, and enqueue a `manual_popup` event.


2) Event processor thread
- Single consumer of the event queue (or a pool of workers consuming safely) that performs business logic.
- Responsibilities:
  - Dequeue events and determine intent.
  - Filter out irrelevant or "useless" events. The websocket connector (or frontend) may push many events; some will have no effect on canonical field state or mapped actions. The processor is responsible for ignoring or archiving such events rather than treating them as errors.
  - If an event implies a change to the canonical field state, update the corresponding `fieldX.json` atomically.
    - Example: an incoming "field queued" event for field 2 should update `field2.json` with state="queued", timestamp, and match id.
  - Look up any actions associated with the event or resulting state transition using `actions.json`, and trigger those actions when configured. Note: events themselves do not intrinsically "contain" device commands — they are interpreted by the processor and mapped (via `actions.json`) to concrete device actions.
    - Actions can include:
      - Lighting: call the ZerOS controller with a preset ID.
      - Video: call the ATEM controller to switch camera or perform a transition.
      - Audio: call the Spotify controller to play/pause/seek a device or playlist.
  - The processor should decide whether an event requires both state update and actions, only a state update, or only an action. This decision is driven by the event type and the mappings in `actions.json`.
  - Log the result of processing and persist minimal audit info (e.g., append to a rolling `events.log` file).

  - Special handling for scheduler events: when the processor receives a `match_scheduled` event (enqueued by the Match scheduler thread), it will translate that into an update of `scheduled_matches.json` (or another display file). That file will be written atomically and will be served by the Flask web server API for the room page to consume. This processing path will ensure the event queue → processor → display JSON workflow is used for scheduled-match notifications.
  - The processor will consult `config.json` for an active `match_queue_pause` window and, if a pause is in effect, will short-circuit updates to `scheduled_matches.json` (or defer processing) until the pause window ends. This ensures operator-configured quiet periods will suppress match notifications end-to-end.

  - Special handling for manual pop-ups: when the processor receives a `manual_popup` event (originating from the admin/operator UI via `/api/send_popup`, or other sources), it will validate the payload and append or update an entry in `popups.json`. `popups.json` will hold active pop-ups (start/end timestamps) and will be served by `/api/popups` for room pages to display immediate notifications. Pop-ups will be short-lived; the processor will also periodically garbage-collect expired pop-ups or mark them as expired in the file.

Behavior contract for the processor:
- Read event E from queue.
- Validate E (schema/type). If invalid, log and drop (or push to a dead-letter queue if implemented).
- Determine whether E is relevant. Many events may be informational or redundant; if E is irrelevant to state or actions, archive or discard it without side effects.
- Determine target field (if any) and whether E changes canonical state.
- If E changes state: write `field{N}.json` with updated state.
- Consult `actions.json` for actions mapped to this event or the resulting state transition. Because events don't directly encode device commands, the processor must translate the event into one or more actions using the configured mappings.
- For each configured action, send the command to the appropriate device driver/module, if the action is enabled in `config.json` and log the outcome.
- Report success/failure per action and optionally retry transient failures.

3) Schedule fetcher thread
- Periodically fetch the official match schedule from an external API (or a configured source) and write it to `schedule.json` atomically. Responsibilities:
  - Authenticate and fetch schedule data on a configurable interval.
  - Normalize and validate the fetched schedule into a predictable JSON shape and persist to `schedule.json`.
  - Optionally keep a raw copy or timestamped backups for debugging/replay.

4) Match scheduler thread
- Read `schedule.json` and enqueue `match_scheduled` events into the central event queue when a match reaches a configured notification threshold expressed in matches (not minutes). Responsibilities:
  - Load the schedule (and watch for updates) and compute upcoming notifications based on schedule ordering.
  - When a match becomes N matches away in the schedule (for example, `schedule_lead_matches = 5`), create a normalized `Event` of type `match_scheduled` (including match id, teams, scheduled time, and room assignments) and push it into the event queue for processing.
  - Handle schedule updates and missed windows (idempotency) to avoid duplicate enqueues for the same scheduled match.
  - Before enqueuing a `match_scheduled` event, the Match scheduler will consult `config.json` for a `match_queue_pause` window. If the current time falls within an active pause window, the scheduler will defer enqueuing until the pause window ends (or the schedule is updated) to avoid emitting notifications during operator-configured quiet periods.
    - The match scheduler will compute the notification condition by counting matches in the schedule: when the configured `schedule_lead_matches` count is reached for a particular team/room, it will emit the `match_scheduled` event. This makes notifications relative to match ordering rather than wall-clock time.
    - The scheduler will read `schedule_lead_matches` from `config.json` (or a runtime-config snapshot) so operators can adjust how early notifications are emitted in terms of matches remaining.
    - The scheduler will ensure idempotency by marking or remembering which matches have already had a `match_scheduled` event emitted for a given schedule version/timestamp so it will not re-enqueue duplicates if the schedule file is reloaded or the order changes.

5) Websocket connector thread
- Connects to TM Manager / VEX API websocket(s) and writes every received event into the shared queue.
- Responsibilities:
  - Establish and maintain websocket(s) to the VEX API (handle reconnect/backoff).
  - Convert VEX events into an internal event JSON schema and push them to the queue.
  - Optionally persist raw events to a `raw_events.log` for debugging or replay.

Notes on event schema:
- All events pushed to the queue must be JSON-serializable and include at minimum:
  - `id`: unique event id
  - `type`: event type (string)
  - `timestamp`: ISO 8601
  - `field`: optional field identifier
  - `payload`: event-specific object

This uniform schema allows the frontend to post manual events and the websocket connector to post API events interchangeably.


## `actions.json` (how it's used)

- `actions.json` contains mappings like:

  {
    "on_event": {
      "match_start": [
        {"type": "lighting", "preset": "match"},
        {"type": "video", "camera": "cam3", "transition": "cut"},
        {"type": "audio", "action": "play", "track": "intro_song"}
      ]
    },
    "on_state_change": {
      "queued->countdown": [ {"type":"lighting","preset":"countdown"} ]
    }
  }

- The event processor interprets these mappings: when an event arrives (or a state transition occurs), it finds matching action lists and executes them.


## `fieldX.json` (state store)

- Each `fieldX.json` contains the canonical state for that field. Example minimal structure:

  {
    "field_id": "1",
    "state": "standby",
    "match_id": null,
    "last_updated": "2025-10-27T12:34:56Z"
  }

- The event processor is the authoritative writer for these files; the frontend is a reader and may request reads to display current state. The frontend must not directly write these files — instead it should post events to the queue for the processor to handle so the canonical update logic remains centralized.


## `config.json` (editable by UI)

- `config.json` holds runtime constants, for example:

  {
    "tm_manager_host": "192.168.0.10",
    "fields": ["field1","field2","field3"],
    "field_camera_map": {"field1":"cam1","field2":"cam2","field3":"cam3"},
    "spotify_device_id": "my_spotify_device",
    "schedule_lead_matches": 5,
    "match_queue_pause": {
      "start": null,
      "end": null
    }
  }

- The frontend allows editing this file; changes are written atomically and take effect immediately for subsequent events.


## Concurrency & file integrity notes

- Because all canonical state is JSON-file-backed, all writes must be atomic (write temp + rename) to avoid partial files.
- A simple file lock (e.g., fcntl-based) or an in-process mutex should guard read-modify-write sections when the file store is local. If multiple processes or machines may access the same JSON files, use an external store (Redis, etcd, or a small DB) instead.


## Logging and observability

- Keep `raw_events.log` for raw incoming events from the websocket connector.
- Keep `events.log` for processed events and action outcomes.
- The frontend should present recent logs and current queue depth for debugging and operational visibility.


## Example event flow

1. Websocket connector receives a VEX event indicating field 2 queued for match 123.
2. Connector converts to internal JSON event and pushes to queue.
3. Event processor dequeues event, validates schema, determines it updates `field2.json` (state="queued", match_id=123) and writes the file.
4. Event processor consults `actions.json` and finds a mapping for `on_state_change` `standby->queued` — triggers lighting preset "ready" and schedules a countdown audio cue via the Spotify controller.
5. Each action is sent to the respective device driver; results are logged to `events.log`.