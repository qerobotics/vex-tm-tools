# QEComp — VEX TM Manager Modernisation Plan
**Version:** 3.0  
**Last Updated:** 2026-07-22  
**Status:** Approved for Execution

> [!IMPORTANT]
> **This document describes a finished, fully functional product.** Every feature listed must be implemented end-to-end. There are no stubs, placeholders, or "future work" items. If a feature is listed, it ships.
>
> **Everything must be manageable from the UI.** No operator should ever need to edit a file, SSH into a server, or run a command to configure or operate the system. The only exception is the initial deployment (k8s manifests and the `ADMIN_LOCAL_PASSWORD` environment variable for the emergency local admin account).

---

## Table of Contents

1. [Overview & Goals](#1-overview--goals)
2. [What Changed vs Current System](#2-what-changed-vs-current-system)
3. [Architectural Decisions](#3-architectural-decisions)
4. [Repository Structure (Target)](#4-repository-structure-target)
5. [Feature Pipelines & Analysis](#5-feature-pipelines--analysis)
6. [Tags — First-Class Concept](#6-tags--first-class-concept)
7. [Timer-Teleprompter Instances](#7-timer-teleprompter-instances)
8. [Database Schema](#8-database-schema)
9. [Integration Module Specification](#9-integration-module-specification)
10. [Automation & Scripting Engine](#10-automation--scripting-engine)
11. [API Specification](#11-api-specification)
12. [Frontend — All Pages](#12-frontend--all-pages)
13. [RBAC & Permissions](#13-rbac--permissions)
14. [Unit Testing](#14-unit-testing)
15. [Deployment & Infrastructure](#15-deployment--infrastructure)
16. [File-by-File Change Summary](#16-file-by-file-change-summary)
17. [Verification Plan](#17-verification-plan)

---

## 1. Overview & Goals

QEComp is a complete rewrite of the existing VEX TM Manager monolith. It must evolve from a single-instance, file-based Python/Flask application into a **fully featured, highly available, clustered production system** deployable on k3s, with a rich React-based admin UI through which every aspect of the system is managed.

### Core Goals

| Goal | Description |
|------|-------------|
| **Finished Product** | Every feature is fully implemented. No stubs. |
| **UI-Only Management** | Every integration, automation, timer, overlay, and permission is configured from the UI |
| **HA Cluster** | Active-passive 2-node cluster on k3s with Redis Sentinel leader election |
| **Postgres Backend** | Replace all JSON file storage with Postgres HA + Redis caching |
| **Modular Integrations** | Dynamic folder-based loading; multiple instances per integration type |
| **Entity IDs & Tags** | Every entity has a unique `entity_id` and zero or more tags |
| **YAML Automations** | Home Assistant-style trigger/condition/action scripting with Jinja2, folder-grouped |
| **Reusable Scripts** | Named reusable action sequences callable from automations |
| **Static Frontend** | React + Vite + Tailwind SPA communicating via REST/WebSocket API |
| **OIDC Auth** | Authentik OIDC with fine-grained, group-mapped RBAC configurable from UI |
| **Emergency Admin** | Local `admin_local` account at `/admin_login` with password from env var |
| **New Services** | Team Profiles, Green-Screen Media Pipeline, Multiple Overlay Instances, Timer-Teleprompter, AI Predictor, OBS/Stream Deck Control |

---

## 2. What Changed vs Current System

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Config Format** | JSON files | Postgres (managed via UI) |
| **Config Editing** | Manual file edit | Admin UI only |
| **State Storage** | Local JSON files | Postgres + Redis cache |
| **Message Queue** | In-memory asyncio | Redis pub/sub (distributed) |
| **HA Support** | None | Active-passive 2-node cluster |
| **Auth** | Basic token | OIDC (Authentik) + local emergency admin |
| **Frontend** | Flask Jinja2 templates | React/Vite SPA |
| **Styling** | Bootstrap | TailwindCSS + vmd1.dev design tokens |
| **Integrations** | Linked to FieldSet, single instance | Decoupled, multiple named instances, entity IDs + tags |
| **Automations** | Hard-coded mappings in EventProcessor | YAML-driven engine with Jinja2, folders, scripts |
| **Scripting** | None | Home Assistant-style scripts + timers |
| **Timer system** | Custom in-memory timers | Timer-Teleprompter instances linked to fields |
| **Database** | None | Postgres with HA |
| **Cache** | None | Redis + Sentinel |
| **Deployment** | Single Docker instance | k3s cluster (2-node) |
| **Team Data** | None | Full team profiles, scraper, AI predictor |
| **Media** | None | Video upload, server-side FFmpeg keying, S3, multi-instance overlays |

---

## 3. Architectural Decisions

### 3.1 High Availability — Active-Passive

- **2-node k3s cluster** (vmd1 k3scluster).
- Both pods run the full application stack (API + static file serving).
- Leader election via Redis distributed lock (`qecomp:leader:lock`, 30s TTL, renewed every 10s by a dedicated asyncio task).
- The lock value is set to `<pod_ip>:<internal_port>` (e.g. `10.0.0.5:8000`), not just a pod ID. This allows the passive node to forward requests directly to the leader by reading this value.
- **Only the leader** instantiates integration clients and runs the automation engine.
- **Passive node command forwarding:** When the passive node receives a request that requires the leader (e.g. `POST /api/v1/integrations/.../service/...`), it reads the leader address from Redis and **HTTP-proxies the request to the leader** using `httpx.AsyncClient`. The leader's response is forwarded back to the caller transparently. This avoids complex Redis request/response queuing.
- Write operations (config changes) are persisted to Postgres and a `config_change` Redis pub/sub message is published; the leader picks up the change and hot-reloads the affected component.
- **Split-brain protection**: If the leader fails to renew its lock, it immediately calls `teardown()` on all integration instances before releasing the lock, preventing dual-command conflicts on ATEM, OSC, or Spotify.
- If Redis is unavailable on startup, retry with exponential backoff (1s → 2s → 4s … capped at 5 minutes). Do not crash.

### 3.2 Dynamic Module Loading

- All integration definitions live under `modules/integrations/<domain>/`.
- Each folder contains **only** client logic and schema manifests (`manifest.yaml`, `services.yaml`). No credentials or instance config live here.
- At startup, `loader.py` scans this directory, imports each integration's `integration.py`, and registers its class in `INTEGRATION_REGISTRY[domain]`.
- Instance configurations (credentials, IPs, names, tags) are stored in Postgres and managed exclusively through the WebUI.
- When an instance is created/updated/deleted via the UI, the backend persists the change to Postgres, publishes a `config_change` event on Redis pub/sub, and the active leader hot-reloads the affected instance with no server restart.
- If an integration's `setup()` raises, mark the instance as `DEGRADED` in Redis and retry in the background with exponential backoff. Never crash the loader.

### 3.3 Entity IDs & Tags

- Every configured integration instance, Timer-Teleprompter instance, and overlay instance has a unique system-wide `entity_id` in the format `<domain>.<name>`, e.g.:
  - `vex_tm.division_1`, `vex_tm.skills`
  - `spotify.fs1_field1`, `spotify.fs1_field2`
  - `atem.main_switcher`
  - `zeros.lighting_board`
  - `timer.fs1_field1`, `timer.fs1_field2`
  - `overlay.main_stream`, `overlay.pit_display`
- Tags are a **first-class concept** across all entity types. Any entity can have zero or more tags (e.g., `fieldCountdown`, `main_stage`, `fs1`).
- Automations can target entities by `entity_id` or by tag. Targeting a tag fires the action on all entities with that tag.
- The field context of a tagged entity is accessible in Jinja2 templates via `entity.field` (e.g., `timer.fs1_field1.field` resolves to the TM field ID bound to that timer).

### 3.4 Configuration — UI Only

- No YAML file editing is required by operators. YAML is used internally as the storage/evaluation format for automations. The UI provides:
  - A **form-based builder** for simple automations.
  - A **raw YAML editor** for advanced users.
  - Full CRUD for every entity type.

### 3.5 Spotify Browser-Based Authentication (PKCE)

The existing `SpotifyOAuth` server-side redirect is not viable in a containerised environment. The new flow:
1. Frontend generates a PKCE challenge and redirects the user to `accounts.spotify.com/authorize`.
2. Spotify redirects to the frontend callback with an authorisation code.
3. Frontend exchanges the code + PKCE verifier for `access_token` + `refresh_token` client-side.
4. Frontend POSTs tokens to `POST /api/v1/integrations/<entity_id>/oauth_token`.
5. Backend persists encrypted tokens in Postgres; loads them into the active Spotify client.
6. Backend auto-refreshes tokens before expiry.

### 3.6 Spotify & Timer Field Convention (Convention-Based, Automation-Driven)

Rather than hard-coding per-field Spotify/timer links, the system uses **convention-based naming + tags**:
- Timer-Teleprompter instances are named `timer.<fieldset_id>_<field_id>` and tagged `fieldCountdown` + `fs<fieldset_id>`.
- Spotify instances for field music are named `spotify.<fieldset_id>_<field_id>` and tagged `fieldAudio` + `fs<fieldset_id>`.
- A **single automation** handles all fields:
  ```yaml
  alias: "Field Countdown — Spotify at T-10s"
  trigger:
    - platform: timer_milestone
      tag: fieldCountdown
      remaining: "00:00:10"
  action:
    - service: spotify.play_playlist_track
      target_tag: fieldAudio
      target_filter: "{{ trigger.entity.tags | intersect(target.tags) }}"
      data:
        playlist_uri: "{{ states('spotify.' + trigger.entity_id.split('.')[1], 'match_playlist') }}"
  ```
  The `target_filter` uses tag intersection: the Spotify instance that shares the same field tags as the triggering timer is selected automatically. This means one automation handles unlimited fields with no duplication.

### 3.7 VEX TM API — Known Issues & Fixes

| Issue | Fix |
|-------|-----|
| Token cached to flat file (`.auth_token`) | Redis, keyed by `entity_id`. Multi-instance safe. |
| `time.sleep()` in async context (rate limiting) | `await asyncio.sleep()` throughout. |
| HMAC `StringToSign` missing query strings | Parse full URI path + query string for signature. |
| Port in `Host` header for standard ports 80/443 | Only include port when non-standard. |
| API key not always stripped of whitespace | Strip at config load time. |
| `schedule_fetcher.py` writes to local filesystem | Migrate to Redis. |
| No exponential backoff on auth failure | Backoff capped at 5 minutes. |
| `InvalidStatusCode` removed in `websockets` ≥11 | Handle `websockets.exceptions.InvalidHandshake`. |

### 3.8 S3 Media Storage

- Credentials (endpoint URL, bucket name, access key, secret key, region) configured in the Settings page and stored encrypted in Postgres.
- Pre-signed URLs with 15-minute TTL generated server-side for overlay video requests.

### 3.9 Local Emergency Admin

- A local `admin_local` account exists **outside** the OIDC flow.
- Password is set via the `ADMIN_LOCAL_PASSWORD` environment variable at deploy time.
- Login page is at `/admin_login` (separate from the main OIDC login).
- `admin_local` always has all permissions regardless of RBAC group mappings.
- This account is **not** configurable from the UI. It is the break-glass account.

### 3.10 Frontend Design

- **React + Vite** static SPA.
- **TailwindCSS** with a custom `tailwind.config.ts` extending Tailwind's theme with CSS variables from [vmd1.dev](file:///c:/Users/VivaanModi/Projects/vmd1.dev/themes/vmd-theme/static/css/style.css):
  - Font: `Inter` (Google Fonts).
  - Background: `#000000`.
  - Surface: `rgba(8,8,8,0.43)` with glassmorphism.
  - Border: `rgba(255,255,255,0.08)`.
  - Text colours, shadow tokens, and success/danger colours all from `style.css` variables.
  - Navbar: animated icon + sliding label on hover, consistent with vmd1.dev.
- Served as static files from the k3s ingress.

---

## 4. Repository Structure (Target)

```
qecomp/
├── main.py                            # Entry point: leader election + task orchestration
├── server.py                          # Flask REST API + WebSocket server
├── loader.py                          # Dynamic integration module loader
├── requirements.txt
├── Dockerfile                         # Includes ffmpeg, libvpx-vp9
├── compose.yml                        # Local dev compose (Postgres, Redis Sentinel, app)
├── implementation_plan.md             # This document
│
├── modules/
│   ├── leader.py                      # Redis leader election logic
│   ├── automation/
│   │   └── engine.py                  # Jinja2 + YAML automation + scripts engine
│   ├── timer/
│   │   └── manager.py                 # Timer-Teleprompter instance manager
│   ├── scraper/
│   │   └── scraper.py                 # VEX TM + Robot Events data scraper
│   ├── predictor/
│   │   └── predictor.py               # Local OPR/DPR match predictor
│   ├── media/
│   │   ├── processor.py               # FFmpeg green-screen keying pipeline
│   │   └── s3.py                      # S3 upload/download/presign helpers
│   └── integrations/
│       ├── vex_tm/
│       │   ├── manifest.yaml
│       │   ├── services.yaml
│       │   └── integration.py         # Async TM client (all fixes applied)
│       ├── spotify/
│       │   ├── manifest.yaml
│       │   ├── services.yaml
│       │   └── integration.py         # PKCE browser-auth Spotify client
│       ├── atem/
│       │   ├── manifest.yaml
│       │   ├── services.yaml
│       │   └── integration.py
│       ├── zeros/
│       │   ├── manifest.yaml
│       │   ├── services.yaml
│       │   └── integration.py
│       └── obs/
│           ├── manifest.yaml
│           ├── services.yaml
│           └── integration.py         # OBS WebSocket control
│
├── models/
│   ├── integration.py
│   ├── automation.py
│   ├── script.py
│   ├── timer.py
│   ├── overlay.py
│   ├── team.py
│   ├── events.py
│   └── audit.py
│
├── storage/
│   └── schema.sql                     # Postgres schema + seed data
│
├── frontend/                          # React + Vite static SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx          # Live telemetry + integration health
│   │   │   ├── FieldMonitor.tsx       # Live field states per TM instance
│   │   │   ├── MatchControl.tsx       # Match queue, manual overrides per TM instance
│   │   │   ├── Integrations.tsx       # CRUD for all integration instances
│   │   │   ├── Automations.tsx        # Folder-grouped automations (form + YAML)
│   │   │   ├── Scripts.tsx            # Reusable script library
│   │   │   ├── Timers.tsx             # Timer-Teleprompter instance management
│   │   │   ├── Overlays.tsx           # Overlay instance management + preview
│   │   │   ├── Teams.tsx              # Team profiles, video upload, keying sliders
│   │   │   ├── AuditLog.tsx           # Filterable audit log viewer
│   │   │   ├── Settings.tsx           # S3, RE API key, global defaults
│   │   │   └── Users.tsx              # OIDC group → permission mapping
│   │   ├── components/
│   │   └── App.tsx
│   ├── public/
│   │   ├── prompter/[id].html         # EMCEE iPad teleprompter (per Timer instance)
│   │   └── overlay/[id].html          # OBS browser source (per Overlay instance)
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
│
├── tests/
│   ├── test_api_client.py
│   ├── test_loader.py
│   ├── test_engine.py
│   ├── test_rbac.py
│   ├── test_media.py
│   ├── test_scraper.py
│   ├── test_timer.py
│   └── test_predictor.py
│
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── configmap.yaml
│
└── docs/
    └── API.md
```

---

## 5. Feature Pipelines & Analysis

### 5.1 HA Leader Election

**Pipeline:**
1. Pod starts → connects to Postgres + Redis Sentinel (retry with exponential backoff if unavailable).
2. Attempts `SET qecomp:leader:lock <pod_id> NX EX 30`.
3. **If acquired** → calls `start_active_services()`: loads all integration instances from Postgres, calls `await instance.setup()` on each, starts automation engine, schedule fetchers, timer managers.
4. A dedicated asyncio task renews the lock every 10s via `EXPIRE qecomp:leader:lock 30`.
5. **If not acquired** → standby: serve API requests normally; read-only state available; no integrations active.
6. On failure to renew → calls `await stop_active_services()` (teardown all integration clients) before the lock expires.

---

### 5.2 Dynamic Integration Loading

**Pipeline:**
1. `loader.py` scans `modules/integrations/` for folders containing `manifest.yaml` + `integration.py`.
2. Registers each class in `INTEGRATION_REGISTRY[domain]`.
3. On leader promotion, queries Postgres for all `integration_instances` rows and instantiates each.
4. On `config_change` Redis pub/sub event, diffs running instances against the new Postgres state, tears down removed/changed, spins up new/updated — all live with no restart.

---

### 5.3 VEX TM Integration

**Config fields (set in UI):** `base_url`, `client_id`, `client_secret`, `api_key`, `field_set_id`, `poll_interval_seconds`, tags.

**setup():**
1. Fetches OAuth2 Bearer token from `https://auth.vextm.dwabtech.com/oauth2/token`. Token cached in Redis.
2. Opens WebSocket to `ws(s)://<base_url>/api/fieldsets/<field_set_id>` with HMAC-signed headers (all fixes applied — see §3.7).
3. Starts background loop: receive WS messages → publish to `qecomp:events` Redis pub/sub with `entity_id` context.
4. Starts schedule fetcher: polls `/api/divisions`, `/api/matches/<div_id>`, `/api/rankings/<div_id>/QUAL`, `/api/skills` periodically. Results cached in Redis.

**Events emitted (with `entity_id` context):**
- `fieldMatchAssigned` → triggers scraper to pre-fetch team data for upcoming teams.
- `fieldActivated` → `field_activated`
- `matchStarted` → `match_started`
- `matchStopped` → `match_stopped`
- `audienceDisplayChanged` → `audience_display_changed`

**Services exposed:**
- `start_match`, `end_early`, `abort`, `reset`, `queue_next_match`, `queue_prev_match`
- `set_audience_display` → `{"cmd": "setAudienceDisplay", "display": <value>}`
- `queue_skills` → `{"cmd": "queueSkills", "skillsID": <id>}`

**Data exposed to scraper/UI:**
- `/api/event` → event name + RE SKU code
- `/api/teams` and `/api/teams/<div_id>` → team list
- `/api/matches/<div_id>` → full match schedule + results
- `/api/rankings/<div_id>/<round>` → rankings
- `/api/skills` → skills rankings
- `/api/fieldsets` and `/api/fieldsets/<id>/fields` → field topology

---

### 5.4 Spotify Integration

**Config fields (set in UI):** `client_id`, `client_secret`, `device_name`, tags.  
**Auth:** Browser-based PKCE flow (see §3.5). The Integrations page shows an "Authenticate with Spotify" button per instance; clicking it initiates the PKCE redirect. Token status shown in real-time.

**Services exposed:**
- `play` (with optional `context_uri`)
- `play_playlist_track` (`playlist_uri`, optional `track_number`; random if omitted)
- `play_track` (`track_uri`, optional `start_time_s`)
- `pause`, `next`, `previous`
- `set_volume` (`volume` 0–100)

**Playlist/track picker:** The automation builder integrates a live Spotify library browser (fetched via the Spotify Web API using the stored access token) so operators can search for and select playlists or tracks by name rather than pasting URIs. URI input is also available for advanced use.

---

### 5.5 ATEM Integration

**Config fields (set in UI):** `ip`, `field_to_input` mapping (UI table: field ID → ATEM input number), tags.

**Services exposed:**
- `switch_input` (`input_index`)
- `set_preview` (`input_index`)

---

### 5.6 ZerOS Lighting Integration

**Config fields (set in UI):** `ip`, `port` (OSC UDP port), tags.  
**Preset management:** Operators define presets by name and number in the UI (stored in Postgres). The preset list is available in the automation builder as a dropdown.

**Services exposed:**
- `set_preset` (`preset_id` or `preset_name`)

---

### 5.7 OBS Integration

**Config fields (set in UI):** `host`, `port`, `password`, tags.

**Services exposed:**
- `switch_scene` (`scene_name`) — scene list fetched live from OBS and shown as dropdown in automation builder.
- `trigger_hotkey` (`hotkey_name`)

---

### 5.8 YAML Automation & Jinja2 Engine

**Pipeline:**
1. Automation rules stored in Postgres (grouped into folders). Engine subscribes to `qecomp:events` Redis pub/sub.
2. For each event, evaluates all enabled automations:
   - **Trigger check**: Does the event `entity_id`, `type`, `attribute`, and tags match?
   - **Condition check**: Render Jinja2 condition templates with event context + current state from Redis.
   - **Action execution**: Render Jinja2 template fields, resolve target entities (by `entity_id` or tag), call services.
3. `delay:` actions spawn child `asyncio.create_task()` — never block the engine loop.
4. `repeat:` actions repeat a block N times or while a condition holds.
5. `script:` actions call a named reusable script from the scripts library.
6. Config changes trigger immediate reload via Redis pub/sub.

**Jinja2 context:**
- `trigger` — the raw event (`.entity_id`, `.payload`, `.entity.tags`, `.entity.field`).
- `states(entity_id, attribute)` — fetch current state from Redis.
- `is_state(entity_id, state)` — boolean state check.
- `entities_with_tag(tag)` — list of entity IDs with a given tag.
- `now()` — current UTC datetime.

**Automation YAML schema:**
```yaml
alias: "Match Start — Full Sequence"
folder: "Match Day"
enabled: true
trigger:
  - platform: state
    entity_id: vex_tm.division_1
    event_type: matchStarted
condition:
  - "{{ trigger.payload.fieldID in [1, 2, 3] }}"
action:
  - service: atem.switch_input
    target: atem.main_switcher
    data:
      input_index: "{{ trigger.payload.fieldID }}"
  - service: zeros.set_preset
    target: zeros.lighting_board
    data:
      preset_name: "field_{{ trigger.payload.fieldID }}_active"
  - delay: "00:00:01"
  - script: field_spotify_play
    data:
      field_tag: "fs{{ trigger.entity_id.split('.')[1] }}"
```

**Tag-based targeting example:**
```yaml
alias: "Field Countdown — Spotify at T-10s"
folder: "Timers"
trigger:
  - platform: timer_milestone
    tag: fieldCountdown
    remaining: "00:00:10"
action:
  - service: spotify.play_playlist_track
    target_tag: fieldAudio
    target_filter: "{{ trigger.entity.tags | intersect(target.tags) | length > 0 }}"
    data:
      playlist_uri: "{{ states(trigger.entity_id, 'match_playlist') }}"
```

---

### 5.9 Reusable Scripts

Named action sequences stored in Postgres. Callable from automations via `script: <name>`. Managed in the Scripts page of the UI with the same form builder / YAML editor as automations.

---

### 5.10 Timer-Teleprompter Instances

**Concept:** Each Timer-Teleprompter instance is a system entity with:
- A unique `entity_id` (e.g., `timer.fs1_field1`)
- A bound TM `field_set_id` + `field_id` (chosen in UI)
- One timer (count-up or count-down, configurable duration)
- Tags (e.g., `fieldCountdown`, `fs1`)
- A generated teleprompter URL: `<app_url>/prompter/<entity_id>`

**Config (set in UI):** name, field set, field, tags. Timer milestones and Spotify links are configured via automations referencing the timer entity.

**Timer events emitted:**
- `timer_started` — when EMCEE triggers countdown
- `timer_milestone` — at configured time points (e.g., T-10s, T-3s), referencing `timer.remaining`
- `timer_finished` — when timer reaches zero
- `timer_stopped` — manual stop

**Automations reference timer state:**
```yaml
trigger:
  - platform: timer_milestone
    entity_id: timer.fs1_field1
    remaining: "00:00:03"
action:
  - service: vex_tm.start_match
    target: vex_tm.division_1
```

**Teleprompter display (iPad page per instance):**
- Large countdown timer (server-synced — all connected iPads show the same time)
- Current script cue (Markdown-rendered)
- Upcoming match preview card: team names, robot names, rankings, previous awards
- AI predictor flag (⚡ High-potential match) when applicable
- "Start Countdown" button (requires `prompter:control` permission) — only EMCEE triggers this

**Cue persistence:** Cues are stored in Postgres and streamed live via WebSocket. A reconnecting iPad re-receives all active cues immediately.

---

### 5.11 Team Profile & Stats Scraper

**Auto-creation:** When a `fieldMatchAssigned` event fires, the scraper checks if a profile exists for each team in the match. If not, it creates one automatically from TM data.

**Data fetched from TM instance:**
- `GET /api/teams` — name, organisation, location, age group
- `GET /api/rankings/<div_id>/QUAL` — qual ranking, W/L/T, WP/AP/SP, avg/high score
- `GET /api/skills` — skills rank, prog/driver high scores
- `GET /api/matches/<div_id>` — all match results for the team (to compute avg/high/low)
- `GET /api/event` — event name + RE SKU

**Data fetched from Robot Events API** (token in Settings page):
- Team biography, robot name
- Previous season results: rankings, awards, highest qual scores, previous competition data
- World skills ranking, UK skills ranking

**Caching:** Redis with 24h TTL. Cache key: `qecomp:team:<number>:profile`.

**Derived computed stats:**
- Qualification average, highest, lowest scores
- OPR/DPR for predictor

---

### 5.12 AI Match Predictor

- Runs locally using OPR (linear regression over all scored matches in the event so far).
- Fires on `fieldMatchAssigned`.
- Flags match as **"high potential"** if predicted combined alliance scores exceed the top X% threshold (X configurable from Settings page).
- **The predicted score is never shown to anyone except internally.** Only the flag appears on the teleprompter.

---

### 5.13 Video Upload & Green-Screen Keying Pipeline

1. Operator selects a team on the Teams page and uploads a raw `.mp4` or `.mov` robot video (recorded against a green screen background).
2. UI shows a **live WebGL preview** with chroma key applied, using configurable parameters:
   - **Key Colour**: hex colour picker (default `#00B140`).
   - **Similarity**: 0.0–1.0 slider.
   - **Blend**: 0.0–1.0 slider.
3. Each team has one robot 360 video slot.
4. Operator clicks "Process & Upload". Frontend POSTs file + parameters to `POST /api/v1/teams/<number>/video`.
5. Backend runs FFmpeg as an asyncio subprocess:
   ```
   ffmpeg -i input.mp4 \
     -vf "colorkey=0x00B140:<similarity>:<blend>,format=yuva420p" \
     -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 \
     output.webm
   ```
6. Processed transparent WebM uploaded to S3. `team_profiles.video_360_s3_key` updated in Postgres.
7. Frontend polls `GET /api/v1/teams/<number>/video/status` for completion.

---

### 5.14 Overlay Instances

Each overlay instance is a system entity with:
- `entity_id` (e.g., `overlay.main_stream`)
- A bound field set (determines which field's match data it watches)
- A generated URL: `<app_url>/overlay/<entity_id>` (loaded as OBS browser source)
- Tags

**OBS overlay page pipeline:**
1. Page loads, connects to `WS /ws/overlay/<entity_id>`.
2. On `fieldMatchAssigned`, backend pushes:
   ```json
   { "type": "upcoming_match", "teams": ["1234A", "5678B", "9101C", "1121D"] }
   ```
3. Page requests pre-signed S3 URLs from `GET /api/v1/teams/batch/videos?teams=…`.
4. Pre-buffers transparent WebM videos.
5. Renders all teams on a **transparent background** (OBS natively composites this on top of the live stream). Layout:
   - **VEX V5 (4 teams)**: 2×2 grid, red alliance colour-coded on left, blue on right.
   - **VEX IQ (2 teams)**: 2×1 side by side, no alliance colour coding.
   - The match data from the connected TM instance determines the team count and programme type.
6. The overlay page has no background. OBS provides the background via the chroma key filter OR the operator uses the transparent WebM directly composited in OBS.

**Admin UI Overlay preview:** The Overlays page in the UI includes a preview panel showing exactly what the OBS browser source will render for the next queued match, without triggering the live OBS transition.

---

### 5.15 Stream Deck Integration

1. Stream Deck uses the HTTP Webhook plugin → `POST /api/v1/automations/trigger/<id>` or `POST /api/v1/integrations/<entity_id>/service/<service>`.
2. Auth: `Authorization: Bearer <api_key>` (API keys created in Settings → API Keys, scoped to specific permissions).
3. Stream Deck can: trigger automations, switch OBS scenes, cut ATEM inputs, fire the prompter countdown.

---

### 5.16 Match Control Page

Dedicated admin page with:
- Live field state display for every field across all `vex_tm.*` instances.
- Current match and queued teams per field.
- Manual override buttons: Queue Next, Queue Prev, Queue Skills, Start Match, End Early, Abort, Reset.
- Audience Display selector per TM instance.
- Real-time updates via WebSocket.

---

### 5.17 Dashboard

- Integration health cards: `entity_id`, connection status (CONNECTED/DEGRADED/DISCONNECTED), last event timestamp.
- Live telemetry per integration type:
  - Spotify: now-playing track, artist, progress bar.
  - ATEM: current input.
  - ZerOS: last preset fired.
  - TM: current match state per field (aggregated across all instances).
- Recent event stream (last 50 events).
- Cluster status: which node is leader, both node heartbeats.

---

## 6. Tags — First-Class Concept

Tags are a general-purpose labelling system applied to any entity:
- Integration instances
- Timer-Teleprompter instances
- Overlay instances

**Storage:** Tags stored as a `TEXT[]` column in Postgres on each entity table. Indexed with GIN for fast lookup.

**UI management:** Tags are created and edited inline on each entity's config form. There is no separate tag management page — tags are ad-hoc strings.

**Automation targeting by tag:**
```yaml
# Target all entities tagged 'fieldAudio'
target_tag: fieldAudio

# Target entities sharing tags with the triggering entity (for same-field resolution)
target_filter: "{{ trigger.entity.tags | intersect(target.tags) | length > 0 }}"
```

---

## 7. Timer-Teleprompter Instances

### UI Config (minimal — rest via automations)
| Field | Description |
|-------|-------------|
| Name | Human-readable name |
| entity_id | Auto-generated from name |
| Field Set | Bound TM field set |
| Field | Bound TM field within the set |
| Tags | e.g., `fieldCountdown`, `fs1` |

### Timer Events Published
| Event | Payload |
|-------|---------|
| `timer_started` | `{entity_id, field, tags}` |
| `timer_milestone` | `{entity_id, remaining, elapsed, field, tags}` |
| `timer_finished` | `{entity_id, field, tags}` |
| `timer_stopped` | `{entity_id, field, tags}` |

Milestones are configured in automation triggers:
```yaml
trigger:
  - platform: timer_milestone
    tag: fieldCountdown
    remaining: "00:00:10"  # fires at T-10s
```

### Teleprompter URL
Each instance auto-generates a URL: `<app_url>/prompter/<entity_id>` (e.g., `/prompter/timer.fs1_field1`).

### Runsheet (Pre-built + Live)
- **Pre-built runsheet:** Operators write a full ordered list of cue items in the admin UI (Timers page → select instance → Runsheet tab). Saved in Postgres.
- **Live cue push:** During the event, the operator can push ad-hoc cues from the admin UI that appear immediately on all connected teleprompter iPads.
- All cues support **Markdown** formatting.
- Active cues persist; reconnecting iPads re-receive them from Postgres.

---

## 8. Database Schema

```sql
-- Postgres schema for QEComp
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "intarray";

-- ────────────────────────────────────────────────
-- Integration instances
-- ────────────────────────────────────────────────
CREATE TABLE integration_instances (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id    VARCHAR(100) UNIQUE NOT NULL,
    domain       VARCHAR(50)  NOT NULL,        -- 'vex_tm', 'spotify', 'atem', 'zeros', 'obs'
    display_name VARCHAR(150) NOT NULL,
    config       JSONB        NOT NULL,         -- Encrypted at rest; credentials + connection params
    enabled      BOOLEAN      DEFAULT TRUE,
    status       VARCHAR(20)  DEFAULT 'DISCONNECTED', -- CONNECTED, DEGRADED, DISCONNECTED
    tags         TEXT[]       DEFAULT '{}',
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX ON integration_instances USING GIN (tags);

-- ────────────────────────────────────────────────
-- Timer-Teleprompter instances
-- ────────────────────────────────────────────────
CREATE TABLE timer_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       VARCHAR(100) UNIQUE NOT NULL,
    display_name    VARCHAR(150) NOT NULL,
    field_set_id    INT          NOT NULL,
    field_id        INT          NOT NULL,
    tags            TEXT[]       DEFAULT '{}',
    enabled         BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX ON timer_instances USING GIN (tags);

-- ────────────────────────────────────────────────
-- Overlay instances
-- ────────────────────────────────────────────────
CREATE TABLE overlay_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       VARCHAR(100) UNIQUE NOT NULL,
    display_name    VARCHAR(150) NOT NULL,
    field_set_id    INT          NOT NULL,
    tags            TEXT[]       DEFAULT '{}',
    enabled         BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX ON overlay_instances USING GIN (tags);

-- ────────────────────────────────────────────────
-- Automation folders
-- ────────────────────────────────────────────────
CREATE TABLE automation_folders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(150) NOT NULL,
    parent_id    UUID REFERENCES automation_folders(id),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- Automations
-- ────────────────────────────────────────────────
CREATE TABLE automations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id         UUID REFERENCES automation_folders(id),
    alias             VARCHAR(200) NOT NULL,
    enabled           BOOLEAN      DEFAULT TRUE,
    trigger_yaml      TEXT         NOT NULL,
    condition_yaml    TEXT,
    action_yaml       TEXT         NOT NULL,
    last_triggered_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- Scripts (reusable action sequences)
-- ────────────────────────────────────────────────
CREATE TABLE scripts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(150) UNIQUE NOT NULL,
    description  TEXT,
    action_yaml  TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- ZerOS presets (managed from UI)
-- ────────────────────────────────────────────────
CREATE TABLE zeros_presets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id  UUID NOT NULL REFERENCES integration_instances(id),
    preset_number   INT  NOT NULL,
    preset_name     VARCHAR(100) NOT NULL,
    description     TEXT,
    UNIQUE (integration_id, preset_number),
    UNIQUE (integration_id, preset_name)
);

-- ────────────────────────────────────────────────
-- Team profiles
-- ────────────────────────────────────────────────
CREATE TABLE team_profiles (
    team_number              VARCHAR(20)  PRIMARY KEY,
    pit_location             VARCHAR(100),
    bio                      TEXT,
    robot_name               VARCHAR(100),
    video_360_s3_key         VARCHAR(512),
    video_processing_status  VARCHAR(20)  DEFAULT 'NONE', -- NONE, PROCESSING, DONE, FAILED
    cached_stats             JSONB,
    extra_notes              TEXT,
    updated_at               TIMESTAMPTZ  DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- EMCEE prompter cues
-- ────────────────────────────────────────────────
CREATE TABLE prompter_cues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timer_entity_id VARCHAR(100) NOT NULL,  -- Which timer instance this cue belongs to
    content         TEXT         NOT NULL,  -- Markdown
    type            VARCHAR(30)  DEFAULT 'script', -- 'script', 'note', 'runsheet'
    sort_order      INT          DEFAULT 0,
    is_active       BOOLEAN      DEFAULT TRUE,
    created_by      VARCHAR(100),
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- RBAC: Authentik group → permission mapping
-- ────────────────────────────────────────────────
CREATE TABLE role_permissions (
    authentik_group VARCHAR(100) NOT NULL,
    permission      VARCHAR(80)  NOT NULL,
    PRIMARY KEY (authentik_group, permission)
);

-- ────────────────────────────────────────────────
-- Machine API keys (Stream Deck, etc.)
-- ────────────────────────────────────────────────
CREATE TABLE api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100)  NOT NULL,
    key_hash     TEXT          NOT NULL,
    permissions  TEXT[]        NOT NULL,
    created_by   VARCHAR(100),
    last_used_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ   DEFAULT NOW(),
    revoked      BOOLEAN       DEFAULT FALSE
);

-- ────────────────────────────────────────────────
-- Audit log
-- ────────────────────────────────────────────────
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       VARCHAR(100),
    action        VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id   TEXT,
    changes       JSONB,
    ip_address    INET,
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- ────────────────────────────────────────────────
-- System settings
-- ────────────────────────────────────────────────
CREATE TABLE system_settings (
    key        VARCHAR(100) PRIMARY KEY,
    value      JSONB        NOT NULL,
    updated_by VARCHAR(100),
    updated_at TIMESTAMPTZ  DEFAULT NOW()
);
-- Seed required settings keys
INSERT INTO system_settings (key, value) VALUES
  ('s3', '{}'),
  ('robot_events_api', '{"token": ""}'),
  ('predictor', '{"high_potential_threshold_pct": 15}'),
  ('chroma_key_defaults', '{"colour": "#00B140", "similarity": 0.1, "blend": 0.05}')
ON CONFLICT DO NOTHING;
```

**Redis key space:**

| Key | Type | TTL | Contents |
|-----|------|-----|----------|
| `qecomp:leader:lock` | String | 30s | Pod ID of current leader |
| `qecomp:tm:<entity_id>:token` | String | token expiry | OAuth bearer token |
| `qecomp:tm:<entity_id>:schedule` | String | configurable | Cached division schedule JSON |
| `qecomp:team:<number>:profile` | String | 24h | Cached team profile JSON |
| `qecomp:integration:<entity_id>:status` | String | — | CONNECTED / DEGRADED / DISCONNECTED |
| `qecomp:integration:<entity_id>:state` | Hash | — | Current integration state dict |
| `qecomp:events` | Pub/Sub | — | All internal events |
| `qecomp:config_change` | Pub/Sub | — | Config reload notifications |
| `qecomp:timer:<entity_id>:state` | Hash | — | `start_ts`, `duration_s`, `running` |
| `qecomp:session:<id>` | Hash | 24h | OIDC session data |

---

## 9. Integration Module Specification

### `manifest.yaml` contract
```yaml
domain: spotify
name: "Spotify"
version: "1.0.0"
description: "Spotify playback control (PKCE browser auth)"
requires_oauth: true
config_schema:
  client_id:
    type: string
    label: "Spotify Client ID"
    secret: false
  client_secret:
    type: string
    label: "Spotify Client Secret"
    secret: true
  device_name:
    type: string
    label: "Playback Device Name"
    secret: false
```

### `integration.py` interface
```python
class Integration:
    def __init__(self, entity_id: str, config: dict, redis, db_pool): ...
    async def setup(self) -> None: ...       # Raise on fatal error
    async def teardown(self) -> None: ...    # Gracefully close connections
    async def call_service(self, service: str, data: dict) -> dict: ...
    async def get_state(self) -> dict: ...   # Current state for dashboard telemetry
```

---

## 10. Automation & Scripting Engine

See §5.8 for full pipeline. Key implementation notes:

### Action types
| Type | Description |
|------|-------------|
| `service` | Call an integration service on a target entity or tag |
| `script` | Call a named reusable script |
| `delay` | `asyncio.create_task()` sleep — non-blocking |
| `condition` | Inline condition; stops chain if false |
| `repeat` | Repeat block N times or while condition holds |

### Jinja2 context globals
| Variable | Description |
|----------|-------------|
| `trigger` | Raw event: `.entity_id`, `.payload`, `.entity.tags`, `.entity.field` |
| `states(entity_id, attr)` | Fetch Redis state attribute |
| `is_state(entity_id, state)` | Boolean state check |
| `entities_with_tag(tag)` | List of entity IDs with tag |
| `now()` | Current UTC datetime |

---

## 11. API Specification

Full detail in `docs/API.md`. Summary:

### Health & Status
| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe |
| GET | `/api/v1/status` | Cluster status, leader, integration health |

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/login` | OIDC redirect |
| GET | `/auth/callback` | OIDC callback |
| POST | `/auth/logout` | Clear session |
| GET | `/admin_login` | Local emergency admin login page |
| POST | `/admin_login` | Submit local admin credentials |

### Integrations
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/integrations/schemas` | — |
| GET | `/api/v1/integrations` | `integrations:read` |
| POST | `/api/v1/integrations` | `integrations:edit` |
| PUT | `/api/v1/integrations/<entity_id>` | `integrations:edit` |
| DELETE | `/api/v1/integrations/<entity_id>` | `integrations:edit` |
| POST | `/api/v1/integrations/<entity_id>/service/<service>` | Varies by integration |
| POST | `/api/v1/integrations/<entity_id>/oauth_token` | `integrations:edit` |
| GET | `/api/v1/integrations/<entity_id>/state` | `integrations:read` |
| GET | `/api/v1/integrations/<entity_id>/spotify/library` | `integrations:read` |

### Automations & Scripts
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/automations/folders` | `automations:read` |
| POST | `/api/v1/automations/folders` | `automations:edit` |
| GET | `/api/v1/automations` | `automations:read` |
| POST | `/api/v1/automations` | `automations:edit` |
| PUT | `/api/v1/automations/<id>` | `automations:edit` |
| DELETE | `/api/v1/automations/<id>` | `automations:edit` |
| POST | `/api/v1/automations/<id>/trigger` | `automations:trigger` |
| GET | `/api/v1/scripts` | `automations:read` |
| POST | `/api/v1/scripts` | `automations:edit` |
| PUT | `/api/v1/scripts/<id>` | `automations:edit` |
| DELETE | `/api/v1/scripts/<id>` | `automations:edit` |

### Timers
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/timers` | `timers:read` |
| POST | `/api/v1/timers` | `timers:edit` |
| PUT | `/api/v1/timers/<entity_id>` | `timers:edit` |
| DELETE | `/api/v1/timers/<entity_id>` | `timers:edit` |
| POST | `/api/v1/timers/<entity_id>/start` | `prompter:control` |
| POST | `/api/v1/timers/<entity_id>/stop` | `prompter:control` |
| POST | `/api/v1/timers/<entity_id>/reset` | `prompter:control` |
| GET | `/api/v1/timers/<entity_id>/cues` | `prompter:view` |
| POST | `/api/v1/timers/<entity_id>/cues` | `prompter:edit` |
| PUT | `/api/v1/timers/<entity_id>/cues/<id>` | `prompter:edit` |
| DELETE | `/api/v1/timers/<entity_id>/cues/<id>` | `prompter:edit` |

### Overlays
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/overlays` | `overlays:read` |
| POST | `/api/v1/overlays` | `overlays:edit` |
| PUT | `/api/v1/overlays/<entity_id>` | `overlays:edit` |
| DELETE | `/api/v1/overlays/<entity_id>` | `overlays:edit` |
| GET | `/api/v1/overlays/<entity_id>/preview` | `overlays:read` |

### Teams
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/teams` | `teams:read` |
| GET | `/api/v1/teams/<number>` | `teams:read` |
| PUT | `/api/v1/teams/<number>` | `teams:edit` |
| POST | `/api/v1/teams/<number>/video` | `video:upload` |
| GET | `/api/v1/teams/<number>/video/status` | `teams:read` |
| GET | `/api/v1/teams/batch/videos` | — |

### Settings & Users
| Method | Path | Permission |
|--------|------|-----------|
| GET | `/api/v1/settings` | `settings:read` |
| PUT | `/api/v1/settings` | `settings:edit` |
| GET | `/api/v1/api-keys` | `settings:edit` |
| POST | `/api/v1/api-keys` | `settings:edit` |
| DELETE | `/api/v1/api-keys/<id>` | `settings:edit` |
| GET | `/api/v1/users/roles` | `settings:edit` |
| PUT | `/api/v1/users/roles` | `settings:edit` |
| GET | `/api/v1/zeros/presets` | `integrations:read` |
| POST | `/api/v1/zeros/presets` | `integrations:edit` |
| PUT | `/api/v1/zeros/presets/<id>` | `integrations:edit` |
| DELETE | `/api/v1/zeros/presets/<id>` | `integrations:edit` |

### WebSocket Channels
| Path | Description |
|------|-------------|
| `WS /ws/events` | Live event stream: field states, automation triggers, integration status |
| `WS /ws/prompter/<entity_id>` | EMCEE teleprompter: cues, countdown, match info, predictor flag |
| `WS /ws/overlay/<entity_id>` | OBS browser source: upcoming match videos, transition triggers |

---

## 12. Frontend — All Pages

### Dashboard (`/`)
- Integration health cards (entity_id, status, last event time).
- Live telemetry: Spotify now-playing, ATEM current input, ZerOS last preset, TM field states.
- Recent event stream (last 50, live-updating).
- Cluster status: leader node, both node heartbeats.

### Field Monitor (`/fields`)
- One card per field across all `vex_tm.*` instances.
- Shows: field name, current state, current match (teams, round, match number), last 5 events.
- Real-time WebSocket updates.

### Match Control (`/match-control`)
- Per-TM instance section.
- Manual buttons: Queue Next, Queue Prev, Queue Skills (dropdown), Start Match, End Early, Abort, Reset.
- Audience Display selector (dropdown of TM display modes).
- Live current match + queue display.

### Integrations (`/integrations`)
- List of all integration instances with status badges.
- "Add Integration" → choose type from schema list → fill form (fields from `config_schema`).
- Edit / Delete existing instances.
- "Test Connection" button per instance.
- Spotify instances show OAuth status and "Authenticate with Spotify" button (PKCE flow).
- Tags editable inline.

### Automations (`/automations`)
- Folder-tree sidebar (create, rename, delete folders).
- Automation list per folder with enable/disable toggle.
- Create/Edit automation via form builder (trigger picker, condition builder, action chain builder with drag-and-drop order).
- Optional raw YAML editor tab on each automation.
- "Test Run" button (triggers immediately regardless of trigger conditions).

### Scripts (`/scripts`)
- List of reusable scripts.
- Create/Edit scripts via same action chain builder + YAML editor.

### Timer-Teleprompter (`/timers`)
- List of Timer-Teleprompter instances.
- Create/Edit: set name, field set, field, tags.
- Per-instance: Runsheet tab (ordered Markdown cues — add, reorder, delete); Live Cues tab (push ad-hoc cues during event).
- Teleprompter URL displayed with copy button.

### Overlays (`/overlays`)
- List of Overlay instances.
- Create/Edit: set name, field set, tags.
- Preview panel showing the overlay as it will appear in OBS for the next queued match.
- Overlay URL displayed with copy button.

### Teams (`/teams`)
- List of all known teams (auto-populated from TM scraper).
- Search/filter by team number, name, division.
- Team detail page:
  - Editable fields: pit location, extra notes.
  - Stats panel (live from scraper): qual ranking, skills ranking, match history.
  - Video upload slot with live WebGL chroma-key preview (colour picker + similarity/blend sliders).
  - Upload progress indicator + processing status.

### Audit Log (`/audit`)
- Table of all audit events.
- Filters: user, action type, resource type, date range.
- Live-updates via WebSocket for new entries.

### Settings (`/settings`)
- **S3 Config:** endpoint, bucket, access key, secret key, region.
- **Robot Events API:** API token input.
- **AI Predictor:** high-potential threshold percentage slider.
- **Chroma Key Defaults:** global defaults for similarity and blend.
- **API Keys:** list, create (shows key once on creation), revoke.

### Users & Roles (`/users`)
- Table of Authentik group → permission mappings.
- Add/remove permission for a group.
- Permission list comes from the system's defined permission constants.

### Teleprompter (per instance: `/prompter/<entity_id>`)
- iPad-optimised full-screen layout.
- Large countdown timer (server-synced).
- Current active cue (Markdown rendered).
- Next cue preview.
- Upcoming match preview card: team names, robot names, qual rankings, previous awards, ⚡ flag.
- "Start Countdown" button (visible only with `prompter:control` permission).

### OBS Overlay (per instance: `/overlay/<entity_id>`)
- Transparent background.
- Robot 360 videos for all teams in the upcoming match.
- VEX V5: 2×2 grid, red/blue alliance colour-coded borders.
- VEX IQ: 2×1 side by side, no alliance colours.
- Videos loop until next match is queued.

### Emergency Admin Login (`/admin_login`)
- Simple username/password form.
- Username always `admin_local`.
- Password from `ADMIN_LOCAL_PASSWORD` env var.
- Does not go through Authentik.

---

## 13. RBAC & Permissions

### Permission List

| Permission | Description |
|-----------|-------------|
| `integrations:read` | View integration instances and status |
| `integrations:edit` | Create, update, delete integration instances |
| `automations:read` | View automations and scripts |
| `automations:edit` | Create, update, delete automations and scripts |
| `automations:trigger` | Manually trigger an automation |
| `timers:read` | View timer instances |
| `timers:edit` | Create, update, delete timer instances |
| `teams:read` | View team profiles and stats |
| `teams:edit` | Edit team profile fields, notes |
| `video:upload` | Upload and process team videos |
| `overlays:read` | View overlay instances |
| `overlays:edit` | Create, update, delete overlay instances |
| `vfx:control` | Call services on `zeros.*` instances |
| `video:control` | Call services on `atem.*` and `obs.*` instances |
| `audio:control` | Call services on `spotify.*` instances |
| `tm:control` | Call services on `vex_tm.*` instances |
| `prompter:view` | View the EMCEE teleprompter |
| `prompter:control` | Trigger countdown on the teleprompter |
| `prompter:edit` | Push/remove cues, edit runsheet |
| `settings:read` | View global settings |
| `settings:edit` | Modify global settings, manage API keys |

### Suggested Default Group Mappings (seeded in DB, editable from UI)

| Authentik Group | Suggested Permissions |
|----------------|----------------------|
| `qecomp-admin` | All permissions |
| `qecomp-operator` | `integrations:read`, `automations:read`, `automations:trigger`, `timers:read`, `teams:read`, `teams:edit`, `video:upload`, `vfx:control`, `video:control`, `audio:control`, `tm:control`, `overlays:read`, `prompter:edit` |
| `qecomp-lighting` | `vfx:control`, `integrations:read` |
| `qecomp-video` | `video:control`, `video:upload`, `overlays:read`, `overlays:edit` |
| `qecomp-emcee` | `prompter:view`, `prompter:control` |
| `qecomp-viewer` | `teams:read`, `integrations:read`, `automations:read` |

---

## 14. Unit Testing

All tests in `tests/`, run with `pytest`. Minimum coverage target: **80%**.

### Test Stack (all self-resolved — no further input needed)

| Library | Role |
|---------|------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support (`asyncio_mode = "auto"` in `pytest.ini`) |
| `httpx` (`AsyncClient`) | FastAPI test client (replaces `TestClient` for async routes) |
| `pytest-mock` | Mocking (wraps `unittest.mock`) |
| `fakeredis` | In-memory Redis mock for tests (no real Redis needed) |
| `factory_boy` | Test fixture factories for SQLAlchemy models |
| `pytest-cov` | Coverage reporting |

### Test Files

| File | Coverage |
|------|----------|
| `test_api_client.py` | HMAC sig generation, port edge cases, query strings, whitespace API keys, token refresh, rate limit backoff |
| `test_loader.py` | Module scanning, schema parsing, missing manifest handling, hot-reload diffing |
| `test_engine.py` | Trigger matching, Jinja2 conditions, action resolution, template rendering, delay non-blocking, tag targeting, tag intersection filter, simultaneous multi-target via `asyncio.gather` |
| `test_rbac.py` | Group → permission mapping, API endpoint enforcement (403/200), API key scope, force-logout via session deletion |
| `test_media.py` | FFmpeg command construction (including 1080p downscale), S3 multipart upload mocking, processing status polling, re-process flow |
| `test_scraper.py` | TM API fetch, Redis cache hit/miss, Robot Events caching, rate limit handling, skills match exclusion |
| `test_timer.py` | Timer start/stop/reset, milestone event emission at correct times, multi-instance isolation, match-running state transition at T-0 |
| `test_predictor.py` | OPR regression with mock match data, high-potential flagging threshold, fallback to Robot Events data before in-event scores exist |
| `test_ha.py` | Leader election lock acquisition, passive→leader HTTP proxy, split-brain teardown on lock renewal failure |

---

## 15. Deployment & Infrastructure

### Dockerfile
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y ffmpeg libvpx-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_DSN` | Yes | Postgres connection string |
| `REDIS_SENTINELS` | Yes | Comma-separated `host:port` list |
| `REDIS_MASTER_NAME` | Yes | Sentinel master name |
| `OIDC_ISSUER_URL` | Yes | Authentik issuer URL |
| `OIDC_CLIENT_ID` | Yes | OIDC client ID |
| `OIDC_CLIENT_SECRET` | Yes | OIDC client secret |
| `ADMIN_LOCAL_PASSWORD` | Yes | Password for `admin_local` emergency account |
| `SECRET_KEY` | Yes | Flask secret key for session signing |
| `ENCRYPTION_KEY` | Yes | Key for encrypting credentials in Postgres |

### k8s Manifests

**`deployment.yaml`:**
- 2 replicas, `RollingUpdate`.
- `podAntiAffinity` `requiredDuringSchedulingIgnoredDuringExecution` → one pod per node.
- Init container: `alembic upgrade head` before app starts.
- Liveness: `GET /healthz`. Readiness: `GET /readyz`.

**`ingress.yaml`:**
- Routes to QEComp service via cluster ingress controller.
- TLS via cert-manager (wildcard cert on vmd1 cluster).
- A CNAME `qerobotics.<tld>` → `ingress.vmd1.dev` (configured externally by operator).

**Postgres HA:** CloudNativePG operator. 1 primary + 1 replica. PgBouncer connection pooling.

**Redis Sentinel:** Bitnami Redis Helm chart. 1 primary + 1 replica + 1 sentinel.

---

## 16. File-by-File Change Summary

| File | Status | Description |
|------|--------|-------------|
| `main.py` | MODIFY | Leader election; wire loader, automation engine, timer manager |
| `server.py` | MODIFY | OIDC middleware; `/admin_login`; all new REST endpoints; drop all JSON file I/O |
| `userManager.py` | DELETE | Replaced by Authentik OIDC + RBAC |
| `loader.py` | NEW | Dynamic integration scanner + hot-reload registry |
| `modules/leader.py` | NEW | Redis Sentinel leader election |
| `modules/automation/engine.py` | NEW | YAML + Jinja2 engine (automations + scripts) |
| `modules/timer/manager.py` | NEW | Timer-Teleprompter instance manager |
| `modules/scraper/scraper.py` | NEW | VEX TM + Robot Events scraper |
| `modules/predictor/predictor.py` | NEW | Local OPR/DPR predictor |
| `modules/media/processor.py` | NEW | FFmpeg keying pipeline |
| `modules/media/s3.py` | NEW | S3 helpers |
| `modules/integrations/vex_tm/` | NEW | Replaces `modules/tm_manager/` (all fixes applied) |
| `modules/integrations/spotify/` | NEW | Replaces `modules/audio/spotify/` (browser PKCE auth) |
| `modules/integrations/atem/` | NEW | Replaces `modules/video/atem/` |
| `modules/integrations/zeros/` | NEW | Replaces `modules/vfx/zeros/` |
| `modules/integrations/obs/` | NEW | New OBS WebSocket integration |
| `modules/tm_manager/` | DELETE | Superseded |
| `modules/audio/spotify/` | DELETE | Superseded |
| `modules/video/atem/` | DELETE | Superseded |
| `modules/vfx/zeros/` | DELETE | Superseded |
| `models/` | REWRITE | New dataclasses for all entity types |
| `storage/schema.sql` | NEW | Full Postgres schema + seeds |
| `storage/*.json` | DELETE | All JSON file storage eliminated |
| `frontend/` | NEW | Full React + Vite SPA with all pages |
| `tests/` | NEW | Full pytest suite (≥80% coverage) |
| `k8s/` | NEW | All Kubernetes manifests |
| `docs/API.md` | NEW | Full API documentation |
| `implementation_plan.md` | THIS FILE | — |

---

## 17. Verification Plan

### Automated Tests
```bash
pytest tests/ --cov=. --cov-report=term-missing
```
All tests must pass. Coverage must be ≥80%.

### Manual End-to-End Checklist

**Infrastructure:**
- [ ] Deploy to vmd1 k3s staging namespace.
- [ ] Verify leader election: kill leader pod → standby promotes within 30s → integrations re-connect on new leader.
- [ ] Verify passive node serves API requests during failover window.

**Auth:**
- [ ] OIDC login via Authentik redirects and returns a session.
- [ ] Local admin login at `/admin_login` with `admin_local` + env var password works.
- [ ] User in group without `tm:control` gets HTTP 403 on match start endpoint.

**Integrations:**
- [ ] Add a `vex_tm` instance via UI → connects to local TM server → events appear in event stream.
- [ ] Add a `spotify` instance → complete PKCE browser auth → play/pause controls work.
- [ ] Add a `zeros` instance → define 3 presets in UI → fire them via automation.
- [ ] Add an `obs` instance → scene list populates from live OBS → scene switch works.

**Automations:**
- [ ] Create a multi-step automation via form builder, trigger it manually → all actions fire.
- [ ] Edit automation as raw YAML → save → fires correctly.
- [ ] Create a reusable script → call it from automation → works.
- [ ] Tag-based automation: timer with tag `fieldCountdown` at T-10s → Spotify with tag `fieldAudio` (same field) plays.

**Timer-Teleprompter:**
- [ ] Create timer instance, open `/prompter/<entity_id>` on iPad.
- [ ] Push a Markdown cue from admin UI → appears rendered on iPad.
- [ ] Pre-build runsheet → appears in order on iPad.
- [ ] Press "Start Countdown" on iPad → timer counts down → Spotify plays at T-10s → TM match starts at T-3s.
- [ ] Open same prompter URL on two iPads → countdown stays in sync on both.

**Teams & Media:**
- [ ] TM event starts → teams auto-created from scraper.
- [ ] Upload a green-screen video → WebGL preview shows keyed result live → process → WebM appears in S3.
- [ ] Predictor flags a match as high-potential → ⚡ appears on teleprompter.

**Overlay:**
- [ ] Create overlay instance → open URL in OBS browser source.
- [ ] Queue a match in TM → overlay page loads correct team videos.
- [ ] Admin UI overlay preview shows same layout as OBS source.
- [ ] VEX IQ match (2 teams) → 2-column layout; VEX V5 match (4 teams) → 2×2 grid with alliance colours.

**Stream Deck:**
- [ ] Create API key in UI → paste into Stream Deck webhook action → trigger automation → fires correctly.

**Audit Log:**
- [ ] All create/update/delete operations appear in audit log with user, timestamp, before/after.
- [ ] Filter by user and date range works.

---

## Appendix A — Resolved Design Decisions

This appendix records every design decision resolved through clarification questions. Implementing agents must treat these as fixed constraints and not re-derive them.

### A.1 Authentication & OIDC

| Decision | Resolution |
|----------|-----------|
| Authentik application | Created after the app is built; include required Authentik config (application type, redirect URIs, scopes, group claim) in docs |
| OIDC group claim field | To be confirmed when the Authentik app is created; the system must make the claim field name configurable via env var `OIDC_GROUPS_CLAIM` (default: `groups`) |
| Teleprompter auth | URL contains an embedded read-only token (HMAC-derived from the timer instance ID + a server secret). No OIDC login required. Token is shown in the Timer UI as a "Teleprompter link" with copy button. The token must be regeneratable from the UI. |
| OBS overlay auth | No auth. The overlay URL (`/overlay/<entity_id>`) is publicly accessible. Security is by obscurity of the entity_id. |

### A.2 OBS Integration

| Decision | Resolution |
|----------|-----------|
| OBS WebSocket protocol | Protocol **v5** (OBS 28+). Use `obs-websocket-py` v1.x. |
| Scene list retrieval | Fetched live from connected OBS instance via `GetSceneList` request on `setup()` and cached in Redis. Refreshed on-demand via a "Refresh Scenes" button in the integration config UI. |

### A.3 Timer-Teleprompter

| Decision | Resolution |
|----------|-----------|
| Countdown duration | Configurable per Timer instance in the UI (a number field, in seconds). Not inside automation YAML. |
| Timer mode | Count-down from configured duration to zero. |
| At zero | Switch to **"Match Running" state**: display an elapsed count-up timer from 0:00. This continues until `matchStopped` is received from the bound TM field, at which point the timer shows a "Match Complete" screen. |
| Second match timer | Yes — after T-0, show a count-up match elapsed timer (e.g., 1:23 elapsed). |
| Teleprompter team info | Full match preview card: team number, team name, qual rank, robot name (if available), previous awards, ⚡ flag from predictor. |
| Countdown trigger | EMCEE only, via "Start Countdown" button on their teleprompter page. Field operators cannot trigger it from the Match Control page. |

### A.4 VEX Programme Support

| Decision | Resolution |
|----------|-----------|
| Programmes supported | **VEX V5** (4-team, 2 alliances) and **VEX IQ** (2-team, co-operative). Programme type is auto-detected from the TM instance's match data. |
| Overlay layout | VEX V5 → 2×2 grid, red alliance (left) / blue alliance (right) with colour-coded borders. VEX IQ → 2×1 side-by-side, no alliance colours. |
| VEX U | Not required. |

### A.5 Video Upload & FFmpeg Pipeline

| Decision | Resolution |
|----------|-----------|
| Raw video retention | Kept in S3 permanently (allows re-processing). Both raw and processed keys stored in `team_profiles`. |
| Re-process | A "Re-process" button on the Teams page (with chroma key sliders) re-runs FFmpeg on the stored raw S3 video without requiring a new upload. |
| Resolution cap | FFmpeg pipeline **always** downscales to a maximum of **1920×1080** if the source is larger. Uses `scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2` before the colorkey filter. |
| File size limit | No enforced limit. FFmpeg pipeline handles any size. |
| Upload mechanism | Backend uses **S3 multipart upload** (chunked) for all video uploads — never a single PUT. |
| FFmpeg full command | `ffmpeg -i input.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,colorkey=0xKEY:SIM:BLEND,format=yuva420p" -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 output.webm` |

### A.6 OBS Overlay

| Decision | Resolution |
|----------|-----------|
| Text labels | Each robot video cell shows a configurable text label. **Default template:** `{{ team.name }}\n{{ team.number }}`. Template is configurable per overlay instance in the UI. |
| When no match is queued | Overlay shows **transparent/empty** — OBS background shows through. No placeholder or logo. |
| Transitions | **Fade in** when new team videos load for a new match. **Fade out** when match is cleared. Fade duration: 500ms (not user-configurable). |

### A.7 Automation Engine

| Decision | Resolution |
|----------|-----------|
| Action chain error handling | On action failure: **retry once** (immediately), then **continue** to the next action in the chain. The failure is logged to the automation execution history. |
| Automation execution history | Yes — a per-automation execution log. Shows: triggered at, trigger event, success/failure status, which action failed (if any). Accessible in the UI on the Automations page (detail view per automation). |
| YAML validation | A **"Validate" button** in the automation editor checks YAML syntax and Jinja2 expression syntax before saving. Does not execute any services. |
| Automation folders | Arbitrary nesting of folders allowed (recursive parent_id reference in schema). |

### A.8 Notifications (ntfy)

| Decision | Resolution |
|----------|-----------|
| ntfy type | Self-hosted ntfy server. Operator configures server URL + topic in Settings page. |
| Events that trigger ntfy | Integration goes DEGRADED, leader failover occurs, automation action fails after retry, video processing job fails. |
| ntfy settings location | Settings page → Notifications section: `server_url`, `topic`, `enabled`. |

### A.9 Deployment Stack

| Decision | Resolution |
|----------|-----------|
| Docker registry | `registry.kmnet.uk` (self-hosted). Credentials passed as k8s image pull secret. |
| Deployment method | Manual `kubectl apply`. No CI/CD pipeline. |
| Postgres | External managed Postgres on vmd1. DSN provided as `POSTGRES_DSN` env var. Project init container runs `alembic upgrade head` on first boot to create schema. |
| Redis | Standard Redis connection string (pointing to HAProxy frontend for the Sentinel cluster) provided as `REDIS_URL` env var. App treats it as a single Redis endpoint — no Sentinel client configuration needed in the app; HAProxy handles failover transparently. |
| Ingress | **Traefik IngressRoute CRD** (not standard Kubernetes Ingress). |
| TLS | cert-manager is installed on vmd1 with a wildcard cert. IngressRoute references the existing wildcard TLS secret. |

### A.10 Redis Degradation

| Decision | Resolution |
|----------|-----------|
| Redis unavailable | App degrades gracefully. Without Redis: no leader election (the instance that comes up runs all services as if it is leader), no event fan-out to WebSocket clients, no schedule/team caching. Postgres remains the source of truth. App **does not halt**. The Dashboard shows a "Redis unavailable" warning banner. |

### A.11 Developer/Debug Views

| Decision | Resolution |
|----------|-----------|
| Debug pages in UI | Three debug views, accessible to users with `settings:edit` permission: (1) **Automation Execution History** (per-automation log of runs, trigger context, result); (2) **Integration Debug Log** (raw events received from each integration instance, last 100 per instance); (3) **Live Event Bus** (raw Redis pub/sub feed, developer view). |

### A.12 Audit Log

| Decision | Resolution |
|----------|-----------|
| Retention | Kept for the lifetime of the server (no auto-deletion). Manual deletion is not exposed in the UI. |

### A.13 UI Responsiveness

| Decision | Resolution |
|----------|-----------|
| Admin pages | Responsive enough for iPad landscape (≥768px breakpoint). Optimised for desktop. Not required to be usable on a phone. |
| Teleprompter | Fully iPad-optimised (portrait and landscape, ≥768px). |

### A.14 WebSocket Resilience

| Decision | Resolution |
|----------|-----------|
| On disconnect | Client shows a **"Reconnecting…"** banner/indicator and auto-reconnects with exponential backoff (1s, 2s, 4s… capped at 30s). Banner disappears on successful reconnect. Applies to: Dashboard, Field Monitor, Match Control, Teleprompter, Overlay, Audit Log live feed. |

### A.15 Authentik Setup Documentation

Since Authentik is configured after the app is built, the `docs/` directory must include an `AUTHENTIK_SETUP.md` file with:
- Required Authentik application type (OAuth2/OIDC Provider).
- Required scopes: `openid`, `profile`, `email`, plus a custom scope that exposes group memberships.
- Required redirect URIs (`<app_url>/auth/callback`).
- How to create groups matching the default role names (`qecomp-admin`, `qecomp-operator`, etc.).
- The env var `OIDC_GROUPS_CLAIM` to set based on what claim Authentik uses.

---

## Appendix B — Additional Resolved Design Decisions

This appendix records all decisions resolved in the third round of clarification. **These decisions are as binding as those in Appendix A.** Implementing agents must use the exact technology choices specified here — do not substitute alternatives.

### B.1 Backend Technology Stack (CRITICAL)

> [!IMPORTANT]
> The existing codebase uses Flask (synchronous WSGI). The new backend is a **complete rewrite** using FastAPI. Do not use Flask, Quart, or any other framework. Every file in `server.py` and `main.py` is replaced.

| Component | Choice | Notes |
|-----------|--------|-------|
| **Web framework** | **FastAPI** | Native async/await, built-in WebSocket support, auto OpenAPI docs at `/docs` |
| **ASGI server** | **Uvicorn** with **`--workers 1`** | **CRITICAL: Use exactly 1 worker per pod.** Multiple workers = multiple OS processes, each trying to acquire the leader lock independently. k8s pod restarts replace the role of Gunicorn/multi-worker process management. Run: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1` |
| **Database ORM** | **SQLAlchemy 2.x async** + **asyncpg** driver | Async session factory, models defined as SQLAlchemy `DeclarativeBase` subclasses |
| **Migrations** | **Alembic** | Init container runs `alembic upgrade head` before the app starts |
| **WebSockets** | FastAPI native `WebSocket` (via Starlette) | No Flask-SocketIO, no external library |
| **Auth middleware** | `python-jose` for JWT validation + `httpx` for OIDC discovery | FastAPI dependency injection for per-route permission checks |
| **Redis client** | `redis-py` async (`redis.asyncio`) | Single `REDIS_URL` env var |
| **Session middleware** | `itsdangerous` for signed cookies + Redis for session store | Cookie contains a signed session ID; session data (user info, groups, permissions) stored in Redis hash at `qecomp:session:<id>` with 24h TTL |
| **Credential encryption** | `cryptography` library — **Fernet** symmetric encryption | `ENCRYPTION_KEY` env var is a Fernet key (32-byte base64url). All `secret: true` fields in integration config are encrypted before writing to Postgres JSONB. |
| **Leader proxy** | `httpx.AsyncClient` | Passive node forwards integration service calls to the leader pod address read from Redis (`qecomp:leader:lock` value = `<pod_ip>:8000`) |

### B.2 Frontend Technology Stack (CRITICAL)

> [!IMPORTANT]
> Use exactly this stack. Do not substitute alternatives.

| Component | Choice | Notes |
|-----------|--------|-------|
| **Framework** | React 18 + Vite 5 | TypeScript throughout |
| **Routing** | React Router v6 | `createBrowserRouter`, nested routes |
| **Global state** | Zustand | Small stores per domain (auth, ws, ui) |
| **Server data** | TanStack Query v5 (React Query) | All REST API calls go through TanStack Query hooks |
| **Styling** | TailwindCSS v3 | Extended with vmd1.dev CSS variable tokens |
| **HTTP client** | `fetch` API (native) wrapped by TanStack Query | No Axios |
| **WebSocket** | Custom hook wrapping native `WebSocket` | Reconnect logic built into the hook |
| **Component library** | None — fully custom components | Built on Tailwind primitives |
| **Icons** | Lucide React | Consistent icon set |
| **Markdown rendering** | `react-markdown` | For EMCEE cue content in teleprompter |

### B.3 Overlay and Teleprompter Pages

> [!IMPORTANT]
> The `/overlay/<entity_id>` and `/prompter/<entity_id>` pages are **NOT** part of the React SPA. They are standalone HTML files with vanilla JS, served directly by FastAPI as static files.

| Aspect | Decision |
|--------|----------|
| Technology | Standalone HTML + vanilla JS (no React, no build step) |
| Location | `backend/static/overlay.html` and `backend/static/prompter.html` (templated at runtime with entity_id injected into a `<script>` block) |
| Serving | FastAPI serves them at `/overlay/{entity_id}` and `/prompter/{entity_id}` as rendered HTML responses |
| WebSocket | Native browser `WebSocket` API with exponential backoff reconnect |
| Overlay auth | None — publicly accessible |
| Teleprompter auth | HMAC token validated server-side on WebSocket upgrade (`?token=<hmac_token>`) |
| Overlay canvas | Designed for **1920×1080**. Document in OBS setup guide. |

### B.4 Teleprompter Index Page

| Aspect | Decision |
|--------|----------|
| URL | `/prompter` (no entity ID) |
| Type | Standalone HTML page served by FastAPI |
| Auth | Protected by a static token set in Settings → `prompter_index_token`. Passed as `?token=<token>` in the URL. No OIDC required. |
| Content | Lists all active Timer-Teleprompter instances with their names and direct teleprompter links. Read-only. |
| Token | Set by admin in Settings page. Shown in Settings with a copy button. If changed, all existing links using the old token are immediately invalidated. |

### B.5 VEX TM Instance Model

| Aspect | Decision |
|--------|----------|
| Mapping | **One `vex_tm` integration instance = one field set** on a TM server |
| Multiple field sets | Create multiple `vex_tm` instances (one per field set). Each has its own `entity_id`, `field_set_id` config, tags, and schedule fetcher. |
| Fields within a field set | A single `vex_tm` instance manages **all fields** within its bound field set. Events from all fields carry a `fieldID` in the payload. |
| Poll interval | Configurable per instance in the UI (`poll_interval_seconds`, default 60s) |
| Skills matches | **Not shown** on overlay or teleprompter. Skills runs do not trigger `fieldMatchAssigned` overlay/prompter updates. The underlying TM events are still published to the event bus so automations can react to them if needed. |
| Elimination matches | Handled identically to qual matches for overlay/teleprompter. The automation engine receives the same events. Automations may check `trigger.payload.round` (e.g. `FINAL`, `SEMIFINAL`) to fire additional actions (e.g. special lighting preset). |

### B.6 Automation Tag Targeting Semantics

| Aspect | Decision |
|--------|----------|
| Tag target | When `target_tag` is set, the service fires on **all entities** with that tag **simultaneously** (concurrent `asyncio.gather`) |
| `target_filter` | An optional Jinja2 boolean expression evaluated per candidate entity. If provided, only entities where the expression evaluates to `true` are targeted. Context: `trigger` (triggering event), `target` (the candidate entity being evaluated). |
| Example | `target_filter: "{{ trigger.entity.tags \| intersect(target.tags) \| length > 0 }}"` — targets only entities that share at least one tag with the triggering entity |
| Ordering | Simultaneous (not sequential) when targeting multiple entities |
| Failure | If one entity's service call fails, the others still proceed (per §A.7 error handling) |

### B.7 API Key Format

| Aspect | Decision |
|--------|----------|
| Format | Cryptographically random 32-byte value, **base64url-encoded** (produces 43-character string with no padding, e.g. `xK2mN7...`) |
| Generation | `secrets.token_urlsafe(32)` in Python |
| Storage | SHA-256 hash stored in `api_keys.key_hash`. The raw key is **shown exactly once** in a modal on creation and never retrievable again. |
| Prefix | Keys are prefixed with `qec_` so they are recognisable (e.g. `qec_xK2mN7...`). Total length: 47 chars. |
| Transmission | Always as `Authorization: Bearer qec_xK2mN7...` header |

### B.8 Teleprompter Token

| Aspect | Decision |
|--------|----------|
| Generation | HMAC-SHA256 of `entity_id + server_secret` where `server_secret` is derived from the `SECRET_KEY` env var |
| Expiry | Never expires unless the operator clicks "Regenerate Token" on the Timer instance config in the UI |
| Regeneration | Creates a new HMAC using a per-instance nonce stored in Postgres. Old tokens are immediately invalid. |
| Format | URL-safe base64 string embedded in the URL: `/prompter/timer.fs1_field1?token=<hmac>` |
| Validation | FastAPI WebSocket endpoint validates HMAC on connection upgrade. Rejects with 403 if invalid. |

### B.9 Session and RBAC Policy

| Aspect | Decision |
|--------|----------|
| Group re-evaluation | Groups (and therefore permissions) are evaluated at **session login time** and stored in the server-side session. Group changes take effect on next login. |
| Session storage | Redis (`qecomp:session:<session_id>` hash, 24h TTL) |
| Force logout | The admin can force session invalidation for a user from the Users page. This deletes their session key from Redis immediately. |

### B.10 Repository Layout Corrections

Given the switch from Flask to FastAPI and the standalone overlay/prompter pages, the repository structure is updated:

```
qecomp/
├── backend/
│   ├── main.py                   # FastAPI app factory + startup/shutdown lifecycle
│   ├── routers/                  # FastAPI APIRouter modules (one per resource)
│   │   ├── integrations.py
│   │   ├── automations.py
│   │   ├── timers.py
│   │   ├── overlays.py
│   │   ├── teams.py
│   │   ├── settings.py
│   │   ├── auth.py
│   │   └── ws.py                 # WebSocket endpoints
│   ├── models/                   # SQLAlchemy ORM models
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── static/
│   │   ├── overlay.html          # Standalone overlay page (templated)
│   │   └── prompter.html         # Standalone teleprompter page (templated)
│   ├── modules/                  # (unchanged from main plan)
│   ├── alembic/                  # Migration scripts
│   └── alembic.ini
│
├── frontend/                     # React + Vite SPA (admin UI only)
│   └── (unchanged from main plan)
│
├── k8s/
├── tests/
└── docs/
    ├── API.md
    └── AUTHENTIK_SETUP.md
```

- **OpenAPI**: Auto-generated by FastAPI at `/docs` (Swagger UI) and `/redoc`.

---

## Appendix C — Strict Modular Boundaries

> [!IMPORTANT]
> These boundaries are **enforced rules**, not suggestions. Every implementing agent must respect them. Violating import rules will cause circular imports, tight coupling, or split-brain bugs. When in doubt: communicate via the event bus or the Loader public API — never import directly across boundary lines.

---

### C.1 Dependency Graph (Backend)

```
                    ┌─────────────┐
                    │  backend/   │
                    │   core/     │  ← DB, Redis, settings, encryption
                    └──────┬──────┘
                           │ (all modules may import core)
          ┌────────────────┼─────────────────────┐
          │                │                     │
   ┌──────▼──────┐  ┌──────▼──────┐   ┌─────────▼────────┐
   │  models/    │  │   loader/   │   │    modules/       │
   │ (SQLAlchemy)│  │  (registry) │   │  (integrations,  │
   └──────┬──────┘  └──────┬──────┘   │   engine, timer, │
          │                │          │   scraper, media, │
   ┌──────▼──────┐         │          │   predictor,      │
   │  schemas/   │         │          │   leader)         │
   │  (Pydantic) │         │          └─────────┬─────────┘
   └──────┬──────┘         │                    │
          │                │            (publish to event bus only)
   ┌──────▼────────────────▼────────────────────▼──────┐
   │                    routers/                        │
   │          (FastAPI APIRouter, HTTP handlers)        │
   └───────────────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   main.py   │
                    │ (app factory│
                    │  + lifespan)│
                    └─────────────┘
```

**Golden rule:** Dependencies flow **downward** in this graph. No module may import from a layer above it. All cross-module communication at the same layer goes through the event bus (Redis pub/sub) or the Loader public API.

---

### C.2 Module-by-Module Boundary Definitions

---

#### `backend/core/`
**Owns:** Database engine + async session factory, Redis async client, application settings (loaded from env vars), Fernet encryption/decryption utilities, shared exceptions.

**Exports (public API):**
```python
get_db() -> AsyncSession          # FastAPI Depends()
get_redis() -> Redis              # FastAPI Depends()
settings: Settings                # Pydantic BaseSettings instance
encrypt(value: str) -> str        # Fernet encrypt
decrypt(value: str) -> str        # Fernet decrypt
```

**May import from:** nothing in the backend (stdlib + third-party only).

**Must NOT import from:** `models/`, `schemas/`, `routers/`, `loader/`, `modules/`.

---

#### `backend/models/`
**Owns:** All SQLAlchemy ORM table definitions. One file per logical group (e.g. `integration.py`, `automation.py`, `team.py`, `timer.py`, `overlay.py`, `audit.py`, `settings.py`).

**Exports:** SQLAlchemy `DeclarativeBase` model classes.

**May import from:** `backend/core/` (for `Base` declarative base only).

**Must NOT import from:** `schemas/`, `routers/`, `loader/`, `modules/`.

---

#### `backend/schemas/`
**Owns:** All Pydantic v2 request/response models. Mirrors the model structure (e.g. `integration.py`, `automation.py`, etc.). One schema file per router file.

**Exports:** Pydantic `BaseModel` subclasses.

**May import from:** stdlib + pydantic only. **No backend imports.**

**Must NOT import from:** anything in `backend/`.

---

#### `backend/loader.py`
**Owns:** Scanning `modules/integrations/` for `manifest.yaml` + `integration.py`. Registering integration classes. Instantiating and managing live integration objects. Handling hot-reload on `config_change` pub/sub.

**Public API (the only way other modules access integration instances):**
```python
INTEGRATION_REGISTRY: dict[str, type[Integration]]   # domain → class
get_instance(entity_id: str) -> Integration | None
get_instances_by_tag(tag: str) -> list[Integration]
get_all_instances() -> list[Integration]
get_instance_status(entity_id: str) -> str            # CONNECTED/DEGRADED/DISCONNECTED
```

**May import from:** `backend/core/` (DB session, Redis), `backend/models/` (to read integration_instances rows).

**Must NOT import from:** `routers/`, `modules/automation/`, `modules/timer/`, `modules/scraper/`, `modules/media/`, `modules/predictor/`. Integration modules are loaded dynamically via `importlib` — not imported statically.

---

#### `backend/modules/integrations/<domain>/integration.py`
**Owns:** All client connection logic, reconnection, service execution, and state reporting for that specific integration.

**Must implement this exact interface — no deviations:**
```python
class Integration:
    entity_id: str
    config: dict        # Decrypted config dict from Postgres
    tags: list[str]

    async def setup(self) -> None:
        """Establish connections. Raise on unrecoverable error."""

    async def teardown(self) -> None:
        """Gracefully close all connections. Must not raise."""

    async def call_service(self, service_name: str, data: dict) -> dict:
        """Execute a service. Return result dict. Raise ValueError for unknown service."""

    async def get_state(self) -> dict:
        """Return current state for dashboard telemetry. Must not raise."""
```

**May import from:** `backend/core/` (Redis for token/state caching, settings for config decryption). stdlib + domain-specific third-party libraries only.

**Must NOT import from:** `loader/`, `routers/`, `models/`, `schemas/`, `modules/automation/`, `modules/timer/`, other integration domains.

**Communication with other modules:** ONLY by publishing events to the Redis pub/sub channel `qecomp:events`. Never call other modules directly.

---

#### `backend/modules/leader.py`
**Owns:** Redis distributed lock acquisition, renewal, and release. Detecting pod IP for the lock value. Notifying the application of promotion and demotion.

**Public API:**
```python
class LeaderElection:
    async def start(self) -> None          # Begin election loop (asyncio.create_task)
    async def stop(self) -> None           # Release lock and stop renewal task
    def is_leader(self) -> bool
    def get_leader_address(self) -> str | None   # Returns '<ip>:8000' of current leader
    on_promoted: Callable[[], Awaitable]   # Set by main.py; called when this node wins
    on_demoted: Callable[[], Awaitable]    # Set by main.py; called when lock is lost
```

**May import from:** `backend/core/` (Redis only).

**Must NOT import from:** `loader/`, `routers/`, `models/`, `schemas/`, any `modules/` submodule except `core`.

---

#### `backend/modules/automation/engine.py`
**Owns:** Loading automation rows from Postgres, YAML parsing, Jinja2 template evaluation, action dispatch, script execution, delay handling, automation execution history logging.

**Public API:**
```python
class AutomationEngine:
    async def start(self) -> None     # Subscribe to qecomp:events, begin processing
    async def stop(self) -> None
    async def reload(self) -> None    # Re-read all automations from DB
    async def trigger(self, automation_id: UUID, context: dict = {}) -> dict
```

**May import from:** `backend/core/` (DB, Redis), `backend/models/` (read-only for automation rows), `backend/loader` (to resolve entity instances by `entity_id` or tag).

**Must NOT import from:** `routers/`, `schemas/`, integration modules directly, `modules/timer/`, `modules/scraper/`, `modules/media/`.

**Communication:** Subscribes to `qecomp:events` via Redis pub/sub. Calls integration services exclusively via `loader.get_instance(entity_id).call_service(...)` or `loader.get_instances_by_tag(tag)`. Never imports integration classes.

**Jinja2 sandbox:** The Jinja2 environment must use `SandboxedEnvironment`. No filesystem access, no `os`, no `subprocess` in templates.

---

#### `backend/modules/timer/manager.py`
**Owns:** Timer-Teleprompter instance lifecycle (load from DB, start/stop/reset countdown, emit milestone events, track elapsed time in Redis, detect `matchStopped` to transition to "match complete" state).

**Public API:**
```python
class TimerManager:
    async def start(self) -> None
    async def stop(self) -> None
    async def reload(self) -> None
    async def start_countdown(self, entity_id: str) -> None
    async def stop_timer(self, entity_id: str) -> None
    async def reset_timer(self, entity_id: str) -> None
    def get_state(self, entity_id: str) -> dict
```

**May import from:** `backend/core/` (DB, Redis), `backend/models/` (timer_instances, prompter_cues), `backend/loader` (to verify bound field entity exists).

**Must NOT import from:** `routers/`, `modules/automation/`, `modules/scraper/`, `modules/media/`, integration modules directly.

**Communication:** Publishes all timer events to `qecomp:events` Redis pub/sub using the canonical event format (see §C.4). Subscribes to `qecomp:events` to detect `matchStopped` events from TM and transition timer state.

---

#### `backend/modules/scraper/scraper.py`
**Owns:** Triggering team data fetches when `fieldMatchAssigned` fires, fetching from TM REST API and Robot Events API, computing derived stats, writing to `team_profiles` Postgres table, Redis caching.

**Public API:**
```python
class Scraper:
    async def start(self) -> None     # Subscribe to qecomp:events, listen for fieldMatchAssigned
    async def stop(self) -> None
    async def fetch_team(self, team_number: str, tm_entity_id: str) -> dict
    async def invalidate_cache(self, team_number: str) -> None
```

**May import from:** `backend/core/` (DB, Redis), `backend/models/` (team_profiles), `backend/loader` (to get the vex_tm instance for REST calls).

**Must NOT import from:** `routers/`, `modules/automation/`, `modules/timer/`, `modules/media/`, `modules/predictor/`.

**Communication:** Subscribes to `qecomp:events`. After fetching a team profile, publishes a `team_profile_updated` event to `qecomp:events`. The predictor subscribes to this to recompute OPR.

---

#### `backend/modules/predictor/predictor.py`
**Owns:** OPR computation from match history, high-potential match flagging, result caching in Redis.

**Public API:**
```python
class Predictor:
    async def start(self) -> None     # Subscribe to qecomp:events
    async def stop(self) -> None
    def predict_match(self, red_teams: list[str], blue_teams: list[str]) -> dict
    def get_flag(self, match_id: str) -> bool | None
```

**May import from:** `backend/core/` (DB for match history, Redis for cached OPR), `backend/models/` (team_profiles read-only).

**Must NOT import from:** `routers/`, `loader/`, `modules/scraper/`, `modules/automation/`, `modules/timer/`, `modules/media/`, integration modules.

**Communication:** Subscribes to `fieldMatchAssigned` events on `qecomp:events`. Publishes `match_prediction` events with the high-potential flag back to `qecomp:events`.

---

#### `backend/modules/media/processor.py`
**Owns:** FFmpeg subprocess management, async polling of subprocess output, progress reporting, temp file lifecycle.

**Public API:**
```python
async def process_video(
    input_path: str,
    output_path: str,
    key_colour: str,      # hex e.g. '#00B140'
    similarity: float,
    blend: float,
) -> None
# Raises ProcessingError on failure
```

**May import from:** `backend/core/` (settings for temp dir), stdlib only.

**Must NOT import from:** `loader/`, `routers/`, `models/`, any other `modules/` submodule.

---

#### `backend/modules/media/s3.py`
**Owns:** S3 multipart upload, presigned URL generation, raw/processed key conventions, download.

**Key naming convention (must be followed exactly):**
```
raw videos:       teams/{team_number}/video/raw.{ext}
processed videos: teams/{team_number}/video/processed.webm
```

**Public API:**
```python
async def upload_multipart(local_path: str, s3_key: str) -> None
async def generate_presigned_url(s3_key: str, expires_in: int = 900) -> str
async def delete_object(s3_key: str) -> None
async def object_exists(s3_key: str) -> bool
```

**May import from:** `backend/core/` (settings for S3 credentials). `boto3`/`aioboto3` only.

**Must NOT import from:** `loader/`, `routers/`, `models/`, other `modules/` submodules.

---

#### `backend/routers/`
**Owns:** FastAPI `APIRouter` definitions. HTTP request parsing, permission checking, response serialisation. One file per resource group.

**May import from:** `backend/core/`, `backend/models/`, `backend/schemas/`, `backend/loader` (via `Depends()`), any `modules/` submodule's public API (via `Depends()` or direct call).

**Must NOT import from:** other routers. Inter-router dependencies go via shared `Depends()` utilities in `backend/core/dependencies.py`.

**Must NOT:** contain any business logic. Routers are thin — validate input, call the appropriate module/loader, return a response. All logic lives in modules.

---

#### `backend/routers/ws.py`
**Owns:** `ConnectionManager` class, all WebSocket route handlers (`/ws/events`, `/ws/prompter/{entity_id}`, `/ws/overlay/{entity_id}`).

**`ConnectionManager` public API:**
```python
class ConnectionManager:
    async def connect(self, entity_id: str, ws: WebSocket) -> None
    async def disconnect(self, entity_id: str, ws: WebSocket) -> None
    async def broadcast(self, entity_id: str, message: dict) -> None
    async def broadcast_all(self, message: dict) -> None
```

**May import from:** `backend/core/` (Redis for pub/sub subscription), `backend/loader` (for entity_id validation), `backend/models/` (to validate prompter token).

**Must NOT import from:** integration modules, `modules/automation/`, `modules/timer/`, `modules/scraper/`.

**Communication:** Subscribes to `qecomp:events` Redis pub/sub and fans out messages to the appropriate connected WebSocket clients.

---

#### `backend/main.py`
**Owns:** FastAPI app factory, lifespan context manager, router mounting, middleware registration, static file mounting, startup orchestration.

**Is the ONLY file permitted to:**
- Import and instantiate `LeaderElection`, `AutomationEngine`, `TimerManager`, `Scraper`, `Predictor`, `Loader`.
- Set `on_promoted` and `on_demoted` callbacks on `LeaderElection`.
- Call `start()` and `stop()` on all top-level managers.

**Must NOT** contain business logic. Startup/shutdown orchestration only.

---

### C.3 Frontend Module Boundaries

---

#### `frontend/src/api/`
**Owns:** All TanStack Query query functions, mutation functions, and custom hooks that wrap them. One file per backend resource (e.g. `integrations.ts`, `automations.ts`, `teams.ts`).

**Exports:** Query/mutation hooks (e.g. `useIntegrations()`, `useCreateAutomation()`).

**May import from:** `frontend/src/schemas/` (TypeScript types), stdlib/TanStack Query.

**Must NOT import from:** `pages/`, `components/`, `stores/`. The API layer has no knowledge of UI.

---

#### `frontend/src/stores/`
**Owns:** Zustand global state stores. Separate store files per domain:
- `auth.ts` — current user, permissions, session status
- `ws.ts` — WebSocket connection state, reconnect logic
- `ui.ts` — sidebar open/close, theme, toast notifications

**Exports:** Zustand store hooks (e.g. `useAuthStore()`, `useWsStore()`).

**May import from:** nothing in frontend (no circular dependency risk). Third-party only.

**Must NOT import from:** `api/`, `components/`, `pages/`.

---

#### `frontend/src/hooks/`
**Owns:** Custom React hooks that are reusable across pages:
- `useWebSocket(entityId, url)` — manages WebSocket lifecycle, reconnect, message dispatch
- `usePermission(permission)` — reads from auth store, returns boolean
- `useDebounce(value, delay)`

**May import from:** `stores/` (to read auth/ws state), stdlib/React.

**Must NOT import from:** `pages/`, `components/`, `api/`.

---

#### `frontend/src/components/`
**Owns:** All reusable UI components. Organised by type:
- `components/ui/` — primitives (Button, Input, Select, Modal, Badge, Card, Table)
- `components/layout/` — Navbar, Sidebar, PageHeader, PageLayout
- `components/integrations/` — IntegrationCard, StatusBadge, ServiceCallPanel
- `components/automations/` — AutomationRow, ActionBuilder, ConditionBuilder
- `components/teams/` — TeamCard, VideoUploader, ChromaKeyPreview
- `components/ws/` — ReconnectingBanner, LiveEventFeed

**May import from:** `api/` (query hooks for data), `stores/` (auth/ui state), `hooks/`, other `components/`.

**Must NOT import from:** `pages/`. Components are page-agnostic.

**Rule:** If a component needs data, it fetches it itself via a TanStack Query hook — pages do not pass raw data as props. Props should be IDs or simple primitives, not full entity objects fetched by the parent.

---

#### `frontend/src/pages/`
**Owns:** Top-level page components mounted by React Router. One file per route.

**May import from:** `components/`, `api/`, `stores/`, `hooks/`.

**Must NOT import from:** other pages directly. Navigation between pages is done via React Router `<Link>` or `useNavigate()` — never by importing another page component.

**Rule:** Pages are responsible for layout composition only. No raw `fetch` calls in pages — all data fetching goes through TanStack Query hooks (either from `api/` or used directly in components).

---

### C.4 Canonical Event Bus Message Schema

**All events published to `qecomp:events` Redis pub/sub must use this exact JSON schema.** No exceptions.

```typescript
interface EventBusMessage {
  // Who fired the event
  entity_id: string;          // e.g. 'vex_tm.division_1', 'timer.fs1_field1'
  entity_tags: string[];      // Tags of the firing entity at time of event

  // What happened
  type: string;               // e.g. 'matchStarted', 'timer_milestone', 'team_profile_updated'

  // When
  timestamp: number;          // Unix epoch float (time.time())

  // Event-specific data
  payload: Record<string, unknown>;
}
```

**Standard `payload` fields by event type:**

| `type` | Required `payload` fields |
|--------|--------------------------|
| `matchStarted` | `fieldID`, `matchNum`, `round`, `redTeams[]`, `blueTeams[]`, `divisionId` |
| `matchStopped` | `fieldID`, `matchNum`, `round` |
| `fieldMatchAssigned` | `fieldID`, `matchNum`, `round`, `redTeams[]`, `blueTeams[]`, `divisionId` |
| `fieldActivated` | `fieldID` |
| `audienceDisplayChanged` | `fieldID`, `display` |
| `timer_started` | `field_set_id`, `field_id`, `duration_s` |
| `timer_milestone` | `field_set_id`, `field_id`, `remaining`, `elapsed` |
| `timer_finished` | `field_set_id`, `field_id` |
| `timer_stopped` | `field_set_id`, `field_id`, `elapsed` |
| `team_profile_updated` | `team_number` |
| `match_prediction` | `matchNum`, `divisionId`, `high_potential`, `predicted_red`, `predicted_blue` |
| `config_change` | `resource_type`, `entity_id`, `action` (`created`/`updated`/`deleted`) |
| `integration_status` | `entity_id`, `status` (`CONNECTED`/`DEGRADED`/`DISCONNECTED`) |

---

### C.5 Cross-Cutting Rules

1. **No circular imports.** If module A imports module B, module B must never import module A.

2. **No singleton state in modules.** All state is stored in Redis or Postgres. Modules read from these stores — they do not maintain in-memory state that would be lost on restart or differ between the two k8s pods.

3. **Integration modules never call each other.** An ATEM integration never imports or calls the ZerOS integration. Cross-integration coordination is the exclusive responsibility of the automation engine.

4. **The automation engine never imports integration modules.** It resolves integration instances at runtime via `loader.get_instance(entity_id)`. This is how new integrations can be added (by dropping a folder into `modules/integrations/`) without touching the engine.

5. **The event bus is the only broadcast mechanism.** If module A needs to notify module B that something happened, it publishes to `qecomp:events`. Module B subscribes. They do not call each other's methods directly.

6. **Routers are stateless.** Every router handler must be completable within a single request/response cycle. No background asyncio tasks may be spawned from route handlers (use the pre-started managers in `main.py` instead).

7. **Frontend: no raw fetch in pages.** All API communication in the frontend goes through TanStack Query hooks defined in `api/`. Pages never call `fetch()` directly.

8. **Frontend: TypeScript strict mode.** `tsconfig.json` must have `"strict": true`. No `any` types except where unavoidable (e.g. external library interop), and those must be commented with a justification.

---

### C.7 Async Discipline — Non-Blocking Execution in All Integration Clients

> [!IMPORTANT]
> Every integration client runs inside the single asyncio event loop of the FastAPI process. **Any blocking call in any integration will stall the entire server** — incoming HTTP requests, WebSocket messages, timer ticks, and automation triggers will all freeze until the blocking call returns. This is not a guideline; it is a hard correctness requirement.

#### C.7.1 Banned Patterns (apply to all 5 integration clients without exception)

| Banned | Reason | Replacement |
|--------|--------|-------------|
| `time.sleep(n)` | Blocks the event loop | `await asyncio.sleep(n)` |
| `requests.get(...)` | Synchronous HTTP | `await httpx.AsyncClient().get(...)` — reuse a single `httpx.AsyncClient` instance per integration, created in `setup()` and closed in `teardown()` |
| `socket.recv(...)` | Blocking socket I/O | Use async socket library or `asyncio.to_thread()` |
| `open(file).read()` | Blocking file I/O | `await aiofiles.open(file).read()` |
| `subprocess.run(...)` | Blocking subprocess | `await asyncio.create_subprocess_exec(...)` with `await proc.communicate()` |
| Synchronous ORM queries (`session.execute()` without `await`) | Blocks DB thread pool | Always `await session.execute(...)` via SQLAlchemy async session |
| Infinite `while True` with no `await` | Starves the event loop | Every loop iteration must `await` something (e.g. `await asyncio.sleep(0)` at minimum, but prefer meaningful awaits) |
| `threading.Event.wait()` | Blocks the calling coroutine | `await asyncio.Event.wait()` |

#### C.7.2 Approved Async Patterns

```python
# ✅ Correct: shared async HTTP client, created once in setup()
class MyIntegration(Integration):
    async def setup(self):
        self._http = httpx.AsyncClient(base_url=self.config["url"], timeout=10.0)

    async def teardown(self):
        await self._http.aclose()

    async def call_service(self, service_name, data):
        response = await self._http.post(f"/api/{service_name}", json=data)
        response.raise_for_status()
        return response.json()

# ✅ Correct: reconnect loop with async sleep
async def _reconnect_loop(self):
    backoff = 1
    while not self._shutdown.is_set():
        try:
            await self._connect()
            backoff = 1
        except Exception as e:
            await asyncio.sleep(min(backoff, 60))
            backoff *= 2

# ✅ Correct: wrapping a synchronous library in a thread
result = await asyncio.to_thread(sync_library_call, arg1, arg2)
```

#### C.7.3 Per-Integration Async Requirements

**`vex_tm` integration:**
- HTTP polling of the TM REST API: use a single persistent `httpx.AsyncClient` with connection pooling. Do **not** create a new client per poll tick.
- TM WebSocket event stream: use the `websockets` library (`async for msg in ws`). The receive loop runs as an `asyncio.Task` created in `setup()` and cancelled in `teardown()`.
- Schedule poll timer: implemented as `asyncio.create_task(_poll_loop())` with `await asyncio.sleep(poll_interval_seconds)` at the end of each iteration. Never use `threading.Timer`.
- HMAC signing: is CPU-bound but fast (<1ms). No special handling needed — call synchronously inside the coroutine.

**`spotify` integration:**
- All Spotify Web API calls use a single persistent `httpx.AsyncClient`.
- Token refresh: implemented as an `asyncio.Task` that wakes `await asyncio.sleep(expires_in - 60)` before expiry. Never refresh inside a `call_service()` call if it can be avoided — pre-refresh in the background task.
- Rate limit (HTTP 429): catch the response, extract `Retry-After` header, `await asyncio.sleep(retry_after)`, then retry **once**. Do not busy-loop.
- Playback state polling (for "currently playing" telemetry on the dashboard): poll at most every 5 seconds via `asyncio.sleep(5)` in a background task. Never poll in `get_state()` directly — return the last cached state.

**`atem` integration:**
- `PyATEMMax` is a **synchronous** library. It must **never** be called directly from a coroutine.
- Wrap all `PyATEMMax` calls in `asyncio.to_thread()`:
  ```python
  await asyncio.to_thread(self._atem.setPreviewInput, mix_effect, source)
  ```
- The ATEM connection heartbeat and receive loop (which PyATEMMax runs internally) must be started in a `threading.Thread` (not asyncio), and that thread must be started in `setup()` and joined in `teardown()`.
- Use `asyncio.Event` (not `threading.Event`) to signal between the ATEM thread and the main event loop. Set it from the thread using `loop.call_soon_threadsafe(event.set)`.

**`zeros` integration:**
- ZerOS uses OSC over UDP. `python-osc`'s `SimpleUDPClient` is synchronous and lightweight.
- OSC sends are fire-and-forget UDP datagrams. Wrap in `asyncio.to_thread()`:
  ```python
  await asyncio.to_thread(self._osc_client.send_message, address, args)
  ```
- If listening for OSC replies (e.g. for state feedback), use `python-osc`'s `AsyncioOSCUDPServer`:
  ```python
  self._transport, self._protocol = await self._loop.create_datagram_endpoint(
      lambda: AsyncioOSCUDPServer(...),
      local_addr=("0.0.0.0", listen_port),
  )
  ```
  Store `self._transport` and close it in `teardown()`.

**`obs` integration:**
- `obs-websocket-py` v1.x is **async-native** — it wraps `websockets` internally. Use it directly within coroutines with `await`.
- Connection setup: `await obs.connect()` in `setup()`. `await obs.disconnect()` in `teardown()`.
- All request calls: `await obs.call(requests.GetSceneList())` etc.
- The library's internal event loop is managed by the library itself — do not create a second event loop or run it in a thread.
- If the OBS server disconnects, the library raises `websockets.exceptions.ConnectionClosedError`. Catch it in `call_service()`, set status to `DEGRADED`, and trigger the reconnect loop.

#### C.7.4 Shutdown Discipline

Every integration's `teardown()` must:
1. Set a `self._shutdown = asyncio.Event()` flag that all background tasks check.
2. Cancel all `asyncio.Task` objects created in `setup()` using `task.cancel()` and `await asyncio.gather(*tasks, return_exceptions=True)`.
3. Close all network connections (`await client.aclose()`, `await ws.close()`, `transport.close()`).
4. **Never raise** from `teardown()`. Wrap everything in `try/except Exception`.
5. Complete within **5 seconds**. The leader election gives up split-brain protection after 5s.

---

### C.8 Frontend Real-Time State Isolation

> [!IMPORTANT]
> The React frontend has two distinct data channels: **REST** (request/response via TanStack Query) and **WebSocket** (push events via `useWebSocket` → Zustand). These two channels must **never be entangled**. A component must read a given piece of data from exactly one source — never both.

#### C.8.1 Data Ownership Table

| Data | Owner | Source |
|------|-------|--------|
| Integration config (name, host, tags, enabled) | **TanStack Query** | `GET /api/v1/integrations` |
| Integration connection status (CONNECTED/DEGRADED) | **Zustand `ws.ts`** | `integration_status` WebSocket event |
| Automation YAML, name, folder | **TanStack Query** | `GET /api/v1/automations` |
| Automation last-run result, triggered-at | **Zustand `ws.ts`** | `automation_executed` WebSocket event |
| Team profile (name, number, videos) | **TanStack Query** | `GET /api/v1/teams/:id` |
| Currently queued match teams (live) | **Zustand `ws.ts`** | `fieldMatchAssigned` WebSocket event |
| Timer countdown value (live tick) | **Zustand `ws.ts`** | `timer_milestone` WebSocket event |
| Timer instance config (duration, name, field binding) | **TanStack Query** | `GET /api/v1/timers` |
| Dashboard event stream (live feed) | **Zustand `ws.ts`** | All events on `qecomp:events` |
| Audit log entries (paginated history) | **TanStack Query** | `GET /api/v1/audit` |
| Live audit log (real-time append) | **Zustand `ws.ts`** | `audit_entry` WebSocket event |
| User list and permissions | **TanStack Query** | `GET /api/v1/users` |
| Current logged-in user and permissions | **Zustand `auth.ts`** | Set at login, not refreshed via WS |

#### C.8.2 The Separation Rule

```
REST data    → TanStack Query cache → components read via useQuery() hooks
WebSocket data → Zustand ws store  → components read via useWsStore() hooks
```

**These two stores must never write to each other.** Specifically:

- ❌ **Forbidden:** A WebSocket message handler calling `queryClient.setQueryData(...)` to update the TanStack Query cache with live WS data.
- ❌ **Forbidden:** A TanStack Query `onSuccess` callback writing to the Zustand WS store.
- ❌ **Forbidden:** A component reading the same logical piece of data from both sources and merging them (e.g. `{ ...queryData, status: wsStatus }`).

#### C.8.3 Permitted Interaction: Cache Invalidation Only

The **only** permitted interaction between the two channels is **cache invalidation**: a WebSocket event may signal that REST data is now stale, causing TanStack Query to refetch.

```typescript
// ✅ Correct: WS event triggers a refetch, does NOT write cache directly
useEffect(() => {
  const unsub = useWsStore.subscribe(
    (state) => state.lastEvent,
    (event) => {
      if (event?.type === 'config_change' && event.payload.resource_type === 'integration') {
        queryClient.invalidateQueries({ queryKey: ['integrations'] });
      }
    }
  );
  return unsub;
}, [queryClient]);
```

This pattern must live in a dedicated `useCacheSync()` hook in `frontend/src/hooks/useCacheSync.ts`, mounted once at the app root. It is the **only** place where WS state triggers TanStack Query behaviour.

#### C.8.4 Component Rules

- A component that shows **live status** (e.g. `IntegrationCard` showing CONNECTED/DEGRADED) reads status from `useWsStore()`. It reads config (name, host) from `useQuery()`. It never merges them into a single derived object inside the component — it renders them in separate JSX expressions.
- A component that shows **live timer ticks** reads `remaining` and `elapsed` from `useWsStore()`. It reads timer configuration (duration, name) from `useQuery()`. Never pass live tick data as props down through parent components — let the timer display component subscribe to the WS store directly.
- A component that shows **audit log history** reads paginated entries from `useQuery()`. Live new entries (appended in real-time) come from `useWsStore()` and are rendered as a separate prepended list. When the user navigates away and back, the WS buffer in the store is cleared; the query refetches the full list.

#### C.8.5 `useWebSocket` Hook Contract

The `useWebSocket(url: string)` hook in `frontend/src/hooks/useWebSocket.ts` must:

1. Open a native `WebSocket` to the given URL.
2. On message: parse JSON and call `useWsStore.getState().dispatch(message)` — a single entry point into the WS Zustand store.
3. On disconnect: show the "Reconnecting…" banner via `useUiStore.getState().setReconnecting(true)`. Reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s cap). On reconnect: `setReconnecting(false)`.
4. On unmount: close the WebSocket cleanly.
5. **Never return data directly.** Consumers read from the Zustand store, not from the hook's return value.

```typescript
// ✅ Correct usage
function Dashboard() {
  useWebSocket('/ws/events');           // side-effect only — no return value used
  const events = useWsStore(s => s.recentEvents);   // read from store
  const integrations = useIntegrations();            // read from TanStack Query
  ...
}
```

The `dispatch(message)` function in `ws.ts` Zustand store is a reducer-style function that routes incoming events to the correct slice of WS state:

```typescript
dispatch: (event: EventBusMessage) => set((state) => {
  switch (event.type) {
    case 'integration_status':
      return { integrationStatuses: { ...state.integrationStatuses, [event.entity_id]: event.payload.status } };
    case 'timer_milestone':
      return { timerStates: { ...state.timerStates, [event.entity_id]: event.payload } };
    case 'fieldMatchAssigned':
      return { currentMatches: { ...state.currentMatches, [event.payload.fieldID]: event.payload } };
    // ... etc
    default:
      return { recentEvents: [event, ...state.recentEvents].slice(0, 50) };
  }
})
```


### C.6 Agent-to-Module Assignment

When implementing in parallel, each agent owns the following and only the following:

| Agent | Owns | Depends on (must be built first) |
|-------|------|----------------------------------|
| **Backend Core** | `backend/core/`, `backend/models/`, `backend/schemas/`, `backend/main.py` structure, `alembic/`, `backend/modules/leader.py` | Nothing — build first |
| **Loader & Integrations** | `backend/loader.py`, all `modules/integrations/<domain>/` | Backend Core (for `core/` imports + `Integration` interface) |
| **Automation Engine** | `backend/modules/automation/engine.py`, `backend/routers/automations.py`, `backend/routers/scripts.py` | Backend Core, Loader |
| **Timer & Prompter** | `backend/modules/timer/manager.py`, `backend/routers/timers.py`, `backend/static/prompter.html` | Backend Core, Event bus schema (§C.4) |
| **Media & Scraper** | `backend/modules/media/`, `backend/modules/scraper/`, `backend/modules/predictor/`, `backend/routers/teams.py` | Backend Core |
| **Routers & WebSocket** | All remaining `backend/routers/`, `backend/routers/ws.py`, `backend/static/overlay.html` | Backend Core, Loader, all modules |
| **Frontend** | Entire `frontend/` directory | Backend Core (needs API schema from OpenAPI `/docs`) |
| **Tests & DevOps** | `tests/`, `Dockerfile`, `k8s/`, `compose.yml`, `docs/` | All of the above |

**Build order constraint:** Backend Core must be committed and its public APIs frozen before any other backend agent starts. The `Integration` interface in §C.2 and the event schema in §C.4 are frozen at that point and must not change without coordinating all dependent agents.

---

## Appendix D — `vmd1.dev` Design System Integration

> [!IMPORTANT]
> The WebUI MUST match the design tokens, visual aesthetics, dark glassmorphism, and component styling of `vmd1.dev`. All UI components (cards, navbar, modals, buttons, chips, code snippets) must utilize this design system.

### D.1 Design System Tokens & CSS Variables

The following CSS variables extracted directly from `vmd1.dev` must be declared in `frontend/src/index.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --primary-color: #52525b;
  --secondary-color: #27272a;
  --highlight-color: #f5f5f5;
  --accent-color: #d4d4d8;
  --background-start: #000000;
  --color-bg-elevated: #0b0b0b;
  --color-surface: rgba(8, 8, 8, 0.43);
  --color-surface-strong: rgba(11, 11, 11, 0.95);
  --color-surface-subtle: rgba(20, 24, 40, 0.38);
  --color-border: rgba(255, 255, 255, 0.08);
  --color-border-strong: rgba(255, 255, 255, 0.18);
  --color-text: #e5e7eb;
  --color-text-strong: #f5f5f5;
  --color-text-muted: #9ca3af;
  --color-text-subtle: #6b7280;
  --color-link: #d4d4d8;
  --color-link-hover: #ffffff;
  --color-success: #86efac;
  --color-danger: #fca5a5;
  --shadow-card: 0 8px 24px 0 rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.18);
  --shadow-card-hover: 0 10px 28px 0 rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  --shadow-glass: 0 10px 30px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.14);
  --shadow-glass-hover: 0 14px 34px rgba(0, 0, 0, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  --shadow-chip: 0 2px 8px rgba(0, 0, 0, 0.2);
  --shadow-chip-hover: 0 6px 16px rgba(255, 255, 255, 0.12);
}

body {
  font-family: 'Inter', sans-serif;
  background-color: var(--background-start);
  color: var(--color-text);
  overflow-y: scroll;
}
```

### D.2 Glassmorphism & Core Component Classes

In `frontend/src/index.css`:

```css
/* vmd1.dev Glassmorphism Cards */
.vmd-card {
  background: var(--color-surface);
  backdrop-filter: blur(10px) saturate(155%);
  -webkit-backdrop-filter: blur(10px) saturate(155%);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 1.5rem;
  box-shadow: var(--shadow-card);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.vmd-card:hover {
  box-shadow: var(--shadow-card-hover);
}

/* Glass Navbar */
.vmd-navbar {
  position: sticky !important;
  top: 1rem;
  z-index: 50;
  margin-bottom: 2rem;
  width: 100%;
  padding: 1rem 1.5rem;
  background: var(--color-surface);
  backdrop-filter: blur(12px) saturate(160%);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  box-shadow: var(--shadow-card);
}

/* Animated Navbar Link & Label */
.navbar-anim-link {
  position: relative;
  overflow: visible;
  display: flex;
  align-items: center;
  padding-left: 0.5rem;
}
.navbar-anim-link .nav-label {
  opacity: 0;
  max-width: 0;
  margin-left: 0;
  white-space: nowrap;
  transition: opacity 0.25s, max-width 0.25s, margin-left 0.25s;
  color: #e0e0e0;
  font-size: 0.95rem;
  font-weight: 600;
  pointer-events: none;
}
.navbar-anim-link.active .nav-label,
.navbar-anim-link:hover .nav-label,
.navbar-anim-link:focus .nav-label {
  opacity: 1;
  max-width: 140px;
  margin-left: 0.4rem;
  pointer-events: auto;
}
.navbar-anim-link i, .navbar-anim-link svg {
  transition: transform 0.25s;
}
.navbar-anim-link:hover i,
.navbar-anim-link:hover svg,
.navbar-anim-link:focus i,
.navbar-anim-link:focus svg {
  transform: translateX(-0.12rem);
}

/* Interactive Chips / Status Badges */
.vmd-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  padding: 0.25rem 0.75rem;
  font-size: 0.85rem;
  font-weight: 500;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-chip);
  transition: transform 280ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 280ms cubic-bezier(0.22, 1, 0.36, 1);
}
.vmd-chip:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-chip-hover);
}

/* Code Snippets & YAML Editor */
.vmd-code-block {
  background: var(--color-bg-elevated) !important;
  border: 1px solid var(--color-border);
  border-radius: 0.9rem;
  padding: 1.1rem;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  font-family: 'JetBrains Mono', monospace;
}
```

### D.3 Tailwind CSS Configuration (`frontend/tailwind.config.js`)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        vmd: {
          bg: '#000000',
          elevated: '#0b0b0b',
          surface: 'rgba(8, 8, 8, 0.43)',
          surfaceStrong: 'rgba(11, 11, 11, 0.95)',
          surfaceSubtle: 'rgba(20, 24, 40, 0.38)',
          border: 'rgba(255, 255, 255, 0.08)',
          borderStrong: 'rgba(255, 255, 255, 0.18)',
          text: '#e5e7eb',
          textStrong: '#f5f5f5',
          textMuted: '#9ca3af',
          textSubtle: '#6b7280',
          link: '#d4d4d8',
          success: '#86efac',
          danger: '#fca5a5',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        vmdCard: '0 8px 24px 0 rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.18)',
        vmdCardHover: '0 10px 28px 0 rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.2)',
        vmdGlass: '0 10px 30px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.14)',
        vmdChip: '0 2px 8px rgba(0, 0, 0, 0.2)',
      },
    },
  },
  plugins: [],
};
```
