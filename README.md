# VEX TM Manager — Spotify Sync & Tools

This repository is a small suite of integrations and automation tools intended to augment a TM Manager event: music sync (Spotify), ATEM camera switching, ZerOS lighting control and basic user-facing web UI for local control. The project is in early stages — several modules are scaffolds — but the repository layout and a secure-by-design implementation plan are provided below.

## Useful resources

- TM Manager API guide (internal): https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit?tab=t.0
- TM Manager Public API intro: https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API
- FLX S48 ZerOS manual (lighting): https://support.vikinglighting.co.uk/downloads/FLX%20S%20User%20Manual%20v1.pdf


## Project goals (short)

1. Connect to TM Manager and monitor field / match lifecycle events via Field Set websocket(s).
2. Play and control Spotify music in sync with match start/stop events (playlist/track schedule stored locally).
3. Control an ATEM switcher to select the camera mapped to the active field.
4. Drive ZerOS lighting presets that match the field / match lifecycle (reverse-engineered API or protocol).
5. (Optional) Expose a small web UI for manual override and user management.


## Current status and implemented methods (codebase snapshot)

High-level: the repo currently contains a working Flask UI skeleton, a robust user manager (file-backed, password-hashed), and several placeholder modules and models to be implemented.

- `server.py` — Flask web app. Routes: `/` (index), `/login`, `/logout`, `/profile`, and form endpoints for authentication and password change. Note: `app.secret_key` is currently an insecure hard-coded string — replace with a secure secret (env/config) before production.
- `main.py` — small runner that imports `app` from `server` and runs it. In the current layout, running `python main.py` will start the Flask server.
- `userManager.py` — Fully implemented user manager using `werkzeug.security.generate_password_hash` and `check_password_hash`. Users are stored under `userInfo/<username>/Me.txt` as CSV-like records. Includes migration support for legacy plaintext passwords (on first login the password file is migrated to a hashed password).
- `eventController.py` — present but currently empty; planned home for TM Manager subscription and event orchestration.
- `models/` — small domain models scaffolding:
  - `models/fields.py` defines Field and FieldSet skeletons.
  - `models/events.py` defines EventEntity and MatchEntity.
  - `models/audio.py` and `models/video.py` define simple entity classes.
- `modules/` contains the integration module scaffolds:
  - `modules/tm_manager/__init__.py` — a small TMManager client skeleton (connect/query/send_command/connect_to_field_set).
  - `modules/audio/spotify` — currently empty, intended for Spotify integration.
  - `modules/vfx/zeros` — placeholder for ZerOS lighting integration.
- `storage/config.json` — currently `{}`. Intended to hold local configuration (see configuration section below).
- `requirements.txt` — currently lists `Werkzeug` and `Flask`.

In short: the web UI and user management are most complete; everything else is scaffolding or TODOs.


## Project architecture and contracts

Contract (what each subsystem exposes and expected behavior):

- TM Manager connector
  - Inputs: TM Manager host/IP, API key (from config or env), FieldSet ID(s)
  - Outputs: Python callbacks/events for lifecycle events (queued, countdown, start, finish)
  - Error modes: reconnect/backoff on websocket failure; validate messages before acting

- Spotify controller
  - Inputs: OAuth credentials (client id/secret, refresh token) or device token; playlist/track schedule
  - Outputs: Play/pause/seek/volume commands executed against a Spotify Connect device
  - Error modes: missing premium account or missing device; token refresh failures

- ATEM controller
  - Inputs: mapping of Field -> Camera ID, ATEM connection details
  - Outputs: switch program/preview selection, transition commands
  - Error modes: connection loss, command timeouts

- ZerOS lighting controller
  - Inputs: preset mapping, board IP/protocol
  - Outputs: preset recall (ready/countdown/active/finish)
  - Error modes: unknown protocol (reverse-engineering blocker), network errors


## Implementation plan (detailed roadmap)

Priority order and incremental milestones (small, testable steps):

1) Safety & basics (1–2 days)
   - Replace insecure `app.secret_key` with configuration-driven secret (environment variable or `storage/config.json` with appropriate file permissions).
   - Move sensitive credentials to environment variables and/or a `.env` file (not checked into git). Add a short README note about these env var names.
   - Add unit tests for `userManager` (happy path + password migration + change password).

2) TM Manager connector (2–4 days)
   - Implement `modules/tm_manager` to: perform HTTP requests to the TM Manager API (query endpoints) and subscribe to Field Set websocket(s). Use `websockets` or `websocket-client` depending on preference.
   - Provide a simple `EventBus` or callback registration system in `eventController.py` to allow multiple consumers (Spotify, ATEM, ZerOS) to register for lifecycle events.
   - Implement reconnection/backoff and validation for incoming websocket messages.

3) Spotify integration (2–5 days)
   - Choose playback method: (A) Control external Spotify Connect device via the Web API (recommended) using `spotipy`, or (B) local playback using an audio library + track files (not recommended because of licensing and convenience).
   - Implement `modules/audio/spotify` to handle OAuth, token refresh, and playback commands. Build a small scheduler that maps a `MatchEntity` -> track or playlist and triggers play/pause at correct times.
   - Provide a sample `storage/playlist.json` format and loader.

4) ATEM camera switching (1–3 days)
   - Integrate existing ATEM control library or implement control over AMCP/HTTP interface depending on model. Add `modules/video/atem` and implement a `switch_to_camera(camera_id)` method.
   - Map Field -> Camera in `storage/config.json`.

5) ZerOS lighting (variable; exploratory)
   - If ZerOS API is documented/available use it. Otherwise implement a packet sniffer-based approach to discover protocol (offline research) and implement `modules/vfx/zeros` with preset recall functions.

6) UI and orchestration (1–2 days)
   - Add a small UI page under Flask to display current field/match state and manual override controls for Spotify/ATEM/lighting.
   - Add authentication hooks to the UI using `userManager` and role-based access control.

7) Testing, hardening, and deploy (2–3 days)
   - Add unit tests for modules where possible.
   - Add CI linting and test runner (GitHub Actions suggested).
   - Provide docker-compose (optional) for deployment and to run a dev web server + worker.


## Configuration and credentials

Recommendation: keep secrets out of git. Use environment variables for runtime secrets and `storage/config.json` only for non-sensitive configuration. Example environment variables you'll need later:

- SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN (or a single SPA-style token if using PKCE)
- TM_MANAGER_API_KEY, TM_MANAGER_HOST
- ATEM_HOST, ATEM_USER (if required)
- APP_SECRET_KEY (Flask secret key)

Example `storage/config.json` (non-sensitive):

{
  "field_camera_map": { "field1": "cam1", "field2": "cam2", "field3": "cam3" },
  "playlist_file": "storage/playlist.json",
  "tm_manager": { "host": "192.168.0.10" }
}


## Suggested file/format examples

- `storage/playlist.json` (create when implementing Spotify integration):
  - format: [{"match_type":"intro","spotify_uri":"spotify:track:...","start_offset":0}, ...]
- `storage/config.json` — see example above


## How the codebase maps to features (quick reference)

- Web UI & auth: `server.py`, `main.py`, `userManager.py`, `templates/*.html`
- TM Manager client & orchestration: `modules/tm_manager/`, `eventController.py`, `models/fields.py`, `models/events.py`
- Spotify control: `modules/audio/spotify/` (implement OAuth, token handling, playback control)
- ATEM switching: `modules/video/atem/` (to create)
- ZerOS lighting: `modules/vfx/zeros/` (to create)


## Security and operational notes

- Never commit client secrets or refresh tokens. Add a `.gitignore` entry for a local `.env` file.
- Use least-privilege roles for UI users; store role in the user file and check it prior to permitting critical actions.
- When controlling devices (ATEM, ZerOS), implement fail-safe behavior: if a command fails, log it and optionally fallback to a safe default (e.g., hold current camera; return lights to standby preset).


## Quick development commands

To prepare the environment and run the local dev server (assumes Python 3.10+):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```


## Next steps I recommend you try now

1. Replace the insecure Flask secret in `server.py` with an environment variable read (e.g., os.environ['APP_SECRET_KEY']).
2. Add tests for `userManager.py` (it is self-contained and a good first automated test).
3. Implement `eventController.py` to act as a small event bus; that will make integrating Spotify/ATEM easier.


## Contact / notes

If you want, I can implement one of the next steps for you now (pick: secure secret + unit tests for `userManager`, or a first-pass TM Manager websocket client). If you choose Spotify integration I can scaffold `modules/audio/spotify` and a sample `storage/playlist.json` and demonstrate token flow with `spotipy`.

---

Generated: snapshot of repository on disk. This README intentionally documents current code status and a recommended incremental plan.
# VEX TM Manager Spotify Sync + Other Tools
## Useful Resources: 
* API Guide: https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit?tab=t.0
* API Intro: https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API
* FLX S48 Manual: https://support.vikinglighting.co.uk/downloads/FLX%20S%20User%20Manual%20v1.pdf


## What will this do?
1. Connect to TM Manager via the TM Manager Public API and track match starts, ends, and updates to audience displays using the Field Set Websocket
2. Connect to the Spotify API and play music in time with match starts, from a predefined list stored in a json file
3. Connect to the ATEM Switcher and automatically switch cameras depending on which field is active
4. (Hopefully) Connect to a ZerOS lighting board and switch lighting after I reverse-engineer the API through intercepting the traffic between a device with the app installed, and the board, using WireShark. Lighting will follow this pattern: Queued field ready, Countdown, Active, Finish, Restart
5. (Hopefully) Control the PTZ Module attatched to the camera using a micro-controller connected to a servo, such as a Raspberry Pi or Arduino (Avi's Idea)

## TM Manager Connection
### API Key
```
waiting on this
```

## Spotify API
WIP

## ATEM Switching
WIP

## ZerOS Lighting Board
### Reverse Engineering
WIP

### API Docs
WIP

### Lighting patterns
#### Preset Allocations
1-4. field 1 ready, countdown, active, finish  
5-8. field 2 ready, countdown, active, finish  
9-12. field 3 ready, countdown, match, finish  
13. standby (1 blue on each field, 1 white on stage)  
14. stage (4 white on stage)  
15. light show  

#### Preset Info
ready= 2 red on field about to start match, 1 blue on other 2  
countdown= 2 red on field about to start match, other 2 blue lights flash with countdown  
match= 2 white on field with match, 1 blue on other 2   
finish= all lights flash white, spin around and go back to standby  

## PTZ Module
No clue how we're gonna do this
