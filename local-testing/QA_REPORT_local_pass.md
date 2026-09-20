# QEComp Local QA Pass — Report

## Fixes applied (post-pass follow-up)

All 7 findings below were fixed and re-verified live against this same local
stack (fake integrations, existing test data, then a rebuild + restart of
the backend container — 2-replica for the HA-forwarding check, back to 1
after).

| # | Finding | Fix | Re-verified |
|---|---|---|---|
| 1 | Automation create/edit/delete never hot-reloads | [`routers/automations.py`](../backend/routers/automations.py) now publishes `qecomp:config_change` on create/update/delete (folders + automations), mirroring `routers/integrations.py`/`routers/timers.py` | Created a brand-new automation with no restart; it fired on a real `matchStarted` event immediately |
| 2 | Script edits invisible until restart, even via Test Run | [`routers/scripts.py`](../backend/routers/scripts.py) now publishes the same `config_change`, which `AutomationEngine.reload()` already listens for and rebuilds `_scripts` from wholesale | Edited a live script's `preset_id` from 2→9 and Test-Ran again with no restart; sniffer saw `9`, not stale `2` |
| 3 | S3 Settings page fully disconnected from the S3 client | [`modules/media/s3.py`](../backend/modules/media/s3.py) now reads the `system_settings` "s3" row per call (env vars as fallback) instead of only ever reading env vars; also added an optional `public_endpoint_url` field (+ `S3_PUBLIC_ENDPOINT_URL` env fallback) used only for presigning, fixing the `minio:9000`-unreachable-from-browser bug found during the Teams test | Set `s3` via `PUT /settings` to `endpoint_url: http://minio:9000` / `public_endpoint_url: http://localhost:9000`; a fresh presigned URL came back on `localhost:9000` and a real `GET` against it returned the video bytes |
| 4 | Chroma-key defaults disconnected (frontend hardcoded its own) | [`VideoUploader.tsx`](../frontend/src/components/teams/VideoUploader.tsx) now seeds its colour/similarity/blend sliders from the `chroma_key_defaults` system setting, falling back to the old hardcoded values only if that setting can't be read | `tsc --noEmit` + `npm run build` clean; not click-tested (still no browser this pass) |
| 5 | `audit_log.ip_address` always NULL | Added an ASGI middleware ([`core/request_context.py`](../backend/core/request_context.py)) that stashes the client IP (preferring `X-Forwarded-For`) in a contextvar every request; `log_action()` now defaults to it instead of requiring every one of its ~26 call sites to thread `Request` through | New audit rows show real IPs (`172.23.0.1`/`172.23.0.5` for the two HA replicas); pre-existing rows correctly stay `NULL`. **Caught a real latent bug while verifying**: `AuditLog.ip_address` is Postgres `INET`, which the asyncpg driver returns as `ipaddress.IPv4Address`, not `str` — `GET /api/v1/audit` 500'd until [`schemas/audit.py`](../backend/schemas/audit.py) got a `field_validator` to coerce it. This was invisible before since the column was always NULL. |
| 6 | No passive-node forwarding for `POST /automations/{id}/trigger` (~50% failure rate behind an LB) | Added `_proxy_trigger_to_leader` to `routers/automations.py`, same pattern as `routers/integrations.py`'s `_proxy_to_leader` | Re-ran the exact 2-replica repro: 10/10 `/trigger` calls now return 200 (was 5×200/5×503 alternating) |
| 7 | `zeros/presets` hooks existed but no UI ever called them | Added [`ZerosPresetsSection.tsx`](../frontend/src/components/integrations/ZerosPresetsSection.tsx), rendered under each `zeros`-domain integration card on the Integrations page, using the existing `useZerosPresets`/`useCreateZerosPreset`/`useDeleteZerosPreset` hooks | `tsc --noEmit` + `npm run build` clean; backend CRUD re-confirmed still working (`GET /zeros/presets` returns the existing preset); not click-tested (no browser) |

Not touched (out of scope / no clear single fix): the "still genuinely
untested" list at the bottom of the original report (real SPA click-testing,
Spotify OAuth completion, ATEM against a real switcher, a real second-user
OIDC login, 3-replica failover, audit filter UI params) — none of those are
"issues to fix," they're coverage gaps that need browser access or hardware
this environment doesn't have.

---


Environment: local Docker Compose stack (`compose.yml` + `local-testing/docker-compose.proxy.yml`
[+ `docker-compose.replicas.yml` for the HA test]), fresh-ish local Postgres/Redis/MinIO volumes,
backend built from source, frontend served statically by the backend container. Auth via the
`/admin_login` emergency-admin path (session cookie) and, for one test, a scoped API key.

**Note on method**: neither browser tool in this session could reach `vex.localhost` (the sandboxed
Browser pane has no route to host loopback/Docker networks; the Claude-in-Chrome extension wasn't
connected), so this pass is **API/WS/DB-level only** — no clicking through the React SPA. Everything
below was verified via `curl`/`httpx`/raw WebSocket clients against the real backend, or by reading
source and confirming behavior with live reproductions. UI-only concerns (layout, client-side
validation, visual polish) are out of scope for this pass and should be treated as untested.

To get real (not just "fails predictably") coverage of the hardware integrations, I built three
throwaway local fakes (per your go-ahead), all under `local-testing/fakes/`, not part of the app:

- `fake_obs.py` — real obs-websocket v5 server (hello/identify handshake, `GetSceneList`/
  `SetCurrentProgramScene`/`TriggerHotkeyByName`), port 4455.
- `fake_vex_tm.py` — real OAuth2 client-credentials token endpoint + HMAC-signature-verifying
  `/api/divisions`/`/api/matches/<id>` + a signature-verifying WebSocket at `/api/fieldsets/<id>`
  that echoes match-flow commands back as events, port 9500. Reachable via the manifest's documented
  `auth_url` "advanced/testing override" field — this integration was clearly built with exactly
  this kind of local testing in mind.
- `fake_zeros_listener.py` — passive OSC/UDP packet sniffer, port 8000.

All three ran on the host and were reached from the backend container via `host.docker.internal`.
ATEM was deliberately **not** faked (proprietary binary UDP protocol, no testing hook in the
manifest — not worth the risk of a subtly-wrong fake giving false confidence), so ATEM below is
still only exercised against an unreachable IP (same as the prod pass).

---

## Summary of new findings

| # | Severity | Finding |
|---|---|---|
| 1 | **High** | Creating, editing, or deleting an **automation** never hot-reloads the running engine — the change is silently invisible to real event-driven triggering until the backend process restarts. |
| 2 | **High** | Editing an existing **script** is silently ignored by anything that references it (`script: <name>` actions) for the rest of the process's life — even a manual "Test Run" of the calling automation still executes the *old* script body. |
| 3 | **Medium** | The Settings page's **S3 config** section (endpoint/bucket/keys) is fully disconnected from the app — it saves to Postgres but the actual S3 client only ever reads env vars. Editing it in the UI does nothing. |
| 4 | **Medium** | The Settings page's **chroma-key defaults** section is likewise disconnected — the video uploader's default colour/similarity/blend are hardcoded in the frontend, never fetched from `system_settings`. |
| 5 | **Low** | `audit_log.ip_address` is a real column, always `NULL` — no router ever passes it to `log_action()`, even routes that already have the `Request` object in scope. |
| 6 | (confirmed, not new) | `POST /api/v1/automations/{id}/trigger` has no passive-node forwarding (already found on the prod pass) — reproduced cleanly locally, exact 50% failure rate under a 2-replica LB. |
| 7 | (confirmed, not new) | `zeros/presets` frontend hooks (`useZerosPresets`, `useCreateZerosPreset`, `useDeleteZerosPreset`) exist in `frontend/src/api/integrations.ts` but are **never called from any page/component** — this is a real, confirmed gap, not something missed in the UI search. |

Everything else below is either a clean pass or explicitly noted as untested with a reason.

---

## Integrations

Created via `POST /api/v1/integrations`, one of each domain:

- **OBS** → fake obs-websocket server: real v5 handshake completed, `status: CONNECTED`.
  `switch_scene`/`trigger_hotkey` services both round-tripped for real (`SetCurrentProgramScene`,
  `TriggerHotkeyByName` seen server-side with correct payloads).
- **VEX TM** → fake TM server: full chain worked — OAuth2 client-credentials token fetch, Redis
  token caching, HMAC-signed `GET /api/divisions` and `GET /api/matches/1` (signature verified
  server-side against the shared key, not just accepted blindly), and a signed WebSocket connect to
  `/api/fieldsets/1`. `status: CONNECTED`. This is a genuinely strong result — it exercises the
  entire §3.7 HMAC-signing implementation for real and it's correct.
- **ZerOS** → real UDP send confirmed: `set_preset` by number produced the exact wire message
  `/zeros/playback/go/<N>` captured by the sniffer. `status: CONNECTED` (expected: UDP has no
  handshake, so this integration reports connected regardless of whether anything's listening —
  not a bug, just means "CONNECTED" doesn't mean much for this domain specifically).
- **ATEM** → fake/unreachable IP: `status: DEGRADED`, retry/backoff visible in logs
  (`Retry setup() failed for 'atem_test' (backoff=2s/4s/8s/16s/32s/64s)`), capped correctly. Matches
  the prod-pass finding, nothing new.
- **Spotify**: not re-tested this pass (no browser available to drive the PKCE redirect). Already
  verified on the prod pass as far as it can go without a real Spotify account.

### ZerOS presets — settled

Confirmed via API: `POST/GET/PUT/DELETE /api/v1/zeros/presets` all work correctly (created
`field_1_active` → 3, then `set_preset` by name correctly resolved it and sent the right OSC
message). The frontend question from the prod pass is now settled with certainty: `useZerosPresets`
/ `useCreateZerosPreset` / `useDeleteZerosPreset` exist in `frontend/src/api/integrations.ts:135-155`
but a repo-wide grep for their usage outside that file returns nothing. **This is a real, confirmed
gap** — the backend is complete, no page or component in the SPA ever calls these hooks.

---

## Automations & Scripts — the hot-reload gap (new, high-severity)

`backend/modules/automation/engine.py` only recompiles its in-memory automation/script cache in two
places: at startup, and on receiving a `qecomp:config_change` Redis pub/sub message
(`_config_change_listener`, engine.py:777-802). Compare who actually publishes that message:

```
$ grep -rl config_change backend/routers/
backend/routers/integrations.py   ✓ publishes on create/update/delete
backend/routers/overlays.py       ✓ publishes
backend/routers/timers.py         ✓ publishes
backend/routers/automations.py    ✗ never does
backend/routers/scripts.py        ✗ never does
```

**Reproduction (automations):**
1. Created integration `vextm_test` (fake VEX TM) and `obs_test` (fake OBS).
2. Created automation "Match start → switch scene": trigger `platform: state, entity_id: vextm_test,
   event_type: matchStarted` → action `service: obs.switch_scene, target: obs_test`.
3. Called `POST /api/v1/integrations/vextm_test/service/start_match` — the fake TM server echoes a
   real `matchStarted` event over the WS, which the integration publishes to `qecomp:events`.
4. **Nothing happened.** `GET /automations/{id}/runs` → `[]`. OBS fake server received no new
   `SetCurrentProgramScene` call.
5. `docker restart` the backend (forces a fresh `reload()` at startup).
6. Repeated step 3 — this time the automation fired for real: `runs` shows a `success` entry, and
   the OBS fake server logged a genuine `SetCurrentProgramScene({'sceneName': 'Field 1 Camera'})`
   call arriving ~26s after the restart.

This isolates the cause precisely: the automation's *trigger-matching* engine state is only ever
refreshed on restart or on `config_change`, and `routers/automations.py`'s `create_automation`/
`update_automation`/`delete_automation` never publish it.

**Why this is easy to miss in testing**: the "Test Run" button
(`POST /automations/{id}/trigger`) deliberately bypasses this cache —
`engine.trigger()`/`_load_single_automation()` re-reads the automation fresh from Postgres every
time (engine.py:320-326, explicitly commented as being for this reason). So a tester who creates an
automation and immediately hits "Test Run" to sanity-check it will see it work perfectly, and will
have no reason to suspect that the *actual* trigger path (a real match-start event, a timer
milestone, etc.) is silently dead until a restart happens to occur. This matches almost exactly what
happened on the prod pass ("initially thought edit-save was broken... re-tested cleanly" — the
Test Run button was masking the real gap the whole time).

**Reproduction (scripts — arguably worse, because even Test Run doesn't save you):**
1. Created script `flash_lights_red`: `service: zeros.set_preset, target: zeros_test, data:
   {preset_id: 1}`.
2. Created automation "Match end → flash lights script": action `script: flash_lights_red`.
3. `POST /automations/{id}/trigger` → fired correctly, sniffer sees `/zeros/playback/go/1`. This
   also opportunistically **warms** `engine._scripts["flash_lights_red"]` (engine.py:396).
4. `PUT /scripts/{id}` → change `preset_id: 1` to `preset_id: 2`.
5. `POST /automations/{id}/trigger` again → still fires "successfully" (`status: success`), but the
   sniffer shows **`/zeros/playback/go/1` again** — the stale, pre-edit value. `_do_script_action`
   (engine.py:631) checks `self._scripts.get(name)` first and only falls back to a fresh DB read if
   the name was never cached — so once a script has been used once, edits to it are invisible for
   the rest of the process's life, and unlike automations, **this isn't masked by Test Run** since
   Test Run only bypasses the automation-level cache, not the script-level one.

**Suggested fix** (not applied — testing/reporting only, per scope): have
`routers/automations.py` and `routers/scripts.py` publish `qecomp:config_change` on
create/update/delete, exactly like `integrations.py`/`overlays.py`/`timers.py` already do.

---

## Automations — trigger forwarding (confirmed from prod pass)

Reproduced locally with `docker compose ... --scale backend=2`. Traefik round-robins across both
replicas.

```
10x POST /api/v1/automations/{id}/trigger  →  200 503 200 503 200 503 200 503 200 503
10x POST /api/v1/integrations/obs_test/service/switch_scene →  200 200 200 200 200 200 200 200 200 200
```

The exact alternating pattern confirms: `routers/integrations.py`'s `_proxy_to_leader` forwarding
works correctly (all 10 succeed regardless of which pod took the request), while
`routers/automations.py`'s `_require_engine` (still just raising a bare 503 on the passive pod, per
the prod-pass finding) has no equivalent. Not re-investigating further since the prod pass already
pinpointed the exact code location — this local repro is just corroborating evidence with clean,
reproducible numbers.

---

## HA / Leader Election

Ran 2 backend replicas against the same Postgres/Redis (`docker-compose.replicas.yml`).

- Leader lock: `qecomp:leader:lock` in Redis correctly held the leader's IP (verified
  `172.23.0.4:8000` = `backend-1`).
- `docker kill` on the leader at `00:15:58`. Lock key went empty at `00:16:18`, new leader
  (`backend-2`, `172.23.0.5:8000`) acquired it by `00:16:23` — **~25s**, consistent with the ~30s
  TTL described.
- Post-promotion, the new leader correctly spun up its own integration clients from scratch: OBS/
  ZerOS/VEX TM all came back `CONNECTED` (fresh handshakes visible in the fake servers' logs), ATEM
  correctly went `DEGRADED` again. No stale state carried over.
- Minor observability gap, not a functional bug: grepped `backend-2`'s full log output for
  `leader`/`elect`/`acquir`/`promot` — **nothing**. The promotion is invisible in the logs; you can
  only tell it happened by reading the Redis key directly. Worth a one-line `logger.warning` on
  acquiring/losing leadership if you ever have to debug this at 2am during a real event.
- Did not get a clean "trigger keeps working through failover" measurement — killing one of only 2
  replicas leaves a single node, so of course 100% of requests succeed afterward (there's no longer
  a passive node to 503). To test that claim properly you'd want 3 replicas, kill 1, and keep hitting
  `/trigger` through the LB across the whole transition; didn't do this given time — flagging as
  untested rather than claiming it based on the 2-node result.

---

## Match Control / Field Monitor

Not click-tested (no browser), but the underlying integration is now fully live-testable thanks to
the fake VEX TM server, so I exercised the actual service calls these pages are built on:
`start_match`, and confirmed the WS command round-trip (`{"cmd": "start"}` sent, `matchStarted` event
came back and reached the event bus/automation engine/audit log correctly). ATEM-DEGRADED graceful
handling already confirmed above under Integrations. Recommend a follow-up UI-level pass once
browser access is sorted out — the API/event layer underneath these two pages is solid.

---

## Timers

- Created a timer instance (`field_set_id`, `field_id`, `duration_s: 90`) → got back a
  `prompter_token`.
- `GET /prompter/{id}` with no token → `403`. With `?token=...` → `200`, serves the real standalone
  teleprompter HTML/JS page (not part of the SPA build, per its own header comment).
- Added a cue (`POST /timers/{id}/cues`) with Markdown content — stored correctly.
- `start` → `phase: countdown, running: true, remaining: 90`. `stop` → `phase: idle, running: false,
  remaining: 0` (this looked odd at first — 90s countdown stopped after ~1s but `remaining: 0`
  instead of `~89` — but reading `_public_state()` in `backend/modules/timer/manager.py`, `remaining`
  is defined as always `0` outside `PHASE_COUNTDOWN` by design, not a bug).
- Connected a raw WebSocket to `/ws/prompter/{id}?token=...`: immediately received a correct
  `timer_state` event with the right `phase`/`running`/`duration_s`/`elapsed`/`remaining` fields.
  Without a token: rejected before the WS upgrade even completes (plain HTTP 403, not the WS
  close-code 4003 path in `ws.py` — there must be an earlier auth dependency gate for the
  fully-tokenless case; didn't chase this further, it's a stricter rejection, not a weaker one).
- Did not test `timer_milestone` triggers firing automations for real, given the automations
  hot-reload bug above (any freshly-created automation using this trigger wouldn't fire without a
  restart anyway) — recommend re-testing this specifically once that bug is fixed.

## Overlays

- Created an overlay instance bound to `field_set_id: 1`.
- `GET /overlay/{id}` → `200`, serves the standalone OBS-browser-source HTML page.
- `GET /overlays/{id}/preview` → `200`, sensible empty state (`match: null, teams: []`) when no
  match is in progress.
- Did not connect to `/ws/overlay/{id}` with real match data flowing (would need the scraper/TM
  match cache populated) — did verify the socket itself accepts a connection with no auth required
  (matches the public OBS-browser-source use case) and that predicted-score sanitization applies to
  it (see AI Predictor section below).

## Teams (full FFmpeg round trip completed)

- `GET /teams` → `[]` (empty, correct — team rows are populated by the Robot Events scraper, not
  created via this API; confirmed by reading `routers/teams.py:100-129`, no upsert path exists).
  Inserted one row directly into Postgres to unblock testing (`INSERT INTO team_profiles ...`).
- Generated a synthetic 320×240 green-screen test clip with `ffmpeg` (a red square moving over a
  green background) and ran it through the real upload endpoint:
  `POST /teams/1234A/video` (multipart) → `202 {"video_processing_status": "PROCESSING"}`.
- Polled `GET /teams/1234A/video/status` → reached `DONE` in ~7s, with
  `video_360_s3_key: "teams/1234A/video/processed.webm"`.
- Confirmed the processed object is real and presignable:
  `GET /teams/batch/videos?teams=1234A` → returned a valid S3 presigned URL.
- **Bug found in the process**: that presigned URL's host is `http://minio:9000/...` — the Docker
  *internal* network hostname for MinIO. A real browser (which is who this URL is ultimately handed
  to, for the video preview) cannot resolve `minio` at all. Root cause: `backend/modules/media/s3.py`
  has exactly one `S3_ENDPOINT_URL` setting, used both for the backend's own internal boto3 client
  *and* for presigned-URL generation — there's no separate "public/browser-facing endpoint" concept.
  This is invisible with real AWS S3 (a public bucket URL works from anywhere), but breaks for any
  self-hosted/internal S3-compatible endpoint (MinIO in this local stack, and plausibly whatever
  the k3s prod deployment uses internally — worth checking prod's actual `S3_ENDPOINT_URL` value to
  see if it's public-reachable there).

## Settings — two dead config sections found

`GET /api/v1/settings` returns 6 groups. Cross-checked each against actual backend consumers
(`grep -rn "SystemSetting" backend/`):

| Settings group | Actually read back by the app? |
|---|---|
| `robot_events_api` | ✅ `modules/scraper/scraper.py` |
| `predictor` (threshold) | ✅ `modules/predictor/predictor.py` |
| `notifications` (ntfy) | ✅ `core/ntfy.py` |
| `s3` | ❌ **never** — `modules/media/s3.py` only reads env-var `settings.S3_*`, never the DB row |
| `chroma_key_defaults` | ❌ **never** — `routers/teams.py`'s upload endpoint hardcodes `similarity=Form(0.1), blend=Form(0.05)`, and the frontend's `VideoUploader.tsx` independently hardcodes its own `useState('#00B140')`/`0.1`/`0.05` defaults rather than fetching this setting |

Both dead sections round-trip fine at the UI/API level (save → reload → shows the value you set),
which is exactly why this is easy to miss without cross-referencing consumers — the Settings page
itself gives no indication these fields don't do anything.

### API keys / webhook pattern (Stream Deck-style) — clean pass

- `POST /api/v1/api-keys {"name": "streamdeck-test", "permissions": ["automations:trigger"]}` →
  got a `raw_key` (shown once, per plan §B.7).
- `Authorization: Bearer <key>` against `POST /automations/{id}/trigger` → `200`, worked exactly
  like a real Stream Deck button press would.
- Same key against an out-of-scope endpoint (`/integrations/obs_test/service/switch_scene`) → `403
  Missing required permission: 'video:control'` — scoping is enforced correctly, not just "any valid
  key can do anything."
- Same key against `PUT /settings` → `403 Missing required permission: 'settings:edit'` — confirmed
  again on a different endpoint.
- `DELETE /api-keys/{id}` (revoke) → subsequent use of the same raw key → `401 Authentication
  required`. Revocation takes effect immediately.
- `last_used_at` correctly updates on each authenticated use.

## Audit Log

- Every write action I performed produced a row: integration CRUD, automation/script CRUD,
  timer/cue/overlay/team creation, API key create/delete, automation triggers (both session-auth and
  API-key-auth). `user_id` correctly distinguishes `"Emergency Admin"` vs. `"api_key:streamdeck-test"`
  for the same action type — attribution works.
- `changes` JSON is populated sensibly per action (e.g. a script edit's audit row contains the new
  `action_yaml`).
- **Found**: `ip_address` is `NULL` on literally every row in the table (533 pre-existing rows from
  earlier sessions, plus every new row this pass). `core/audit.py`'s `log_action()` accepts an
  `ip_address` parameter, but grepping all 26 call sites across `backend/routers/*.py` shows zero
  pass it — including handlers that already have a `Request` object in scope (e.g.
  `call_integration_service`). Low severity (nothing depends on it), but worth either wiring up or
  dropping the column/parameter since right now it's pure dead weight.
- Did not test the filter UI (no browser this pass) — the underlying `GET /api/v1/audit` accepts
  query params for filtering per the OpenAPI schema; didn't exercise them individually given time,
  recommend a quick pass once browser access works.

## Users / RBAC

- `GET /api/v1/users/roles` matches the DB `role_permissions` table exactly (25 rows,
  `qecomp-admin` → `*`, and 5 other groups with scoped permission sets) — the mapping UI (per its
  read path) has correct source-of-truth data to display.
- Did not create a second real Authelia user/group to test enforcement through an actual OIDC
  session (would need editing `authelia/users_database.yml` + a `claims_policies` group mapping and
  a full login flow — no browser available this pass to complete that login). Instead verified
  enforcement indirectly but concretely via the scoped API key tests above (a key with only
  `automations:trigger` was correctly blocked from `video:control`- and `settings:edit`-gated
  routes) — this exercises the exact same `require_permission()` dependency and permission-set logic
  a real non-admin OIDC session would go through, just via a different auth front door. Recommend a
  real second-user OIDC test once browser access is available, but I'm fairly confident the
  enforcement layer itself is sound based on this.

## AI Predictor — score-leak check (clean pass, verified for real)

Read `backend/modules/predictor/predictor.py`'s extensive docstring-level warning about never
leaking `predicted_red`/`predicted_blue`, then verified it live rather than just trusting the
comments: published a raw `match_prediction` event directly to Redis
(`{"predicted_red": 123.4, "predicted_blue": 98.7, "high_potential": true, "matchNum": "Q5", ...}`)
and connected a real WebSocket client to `/ws/events`. The event that arrived client-side was:

```json
{"entity_id":"predictor","entity_tags":[],"type":"match_prediction","timestamp":...,
 "payload":{"high_potential":true,"matchNum":"Q5","divisionId":1}}
```

`predicted_red`/`predicted_blue` were stripped exactly as designed
(`routers/ws.py:199`'s `sanitized_payload` dict comprehension). Also checked `routers/overlays.py`'s
REST preview path (`_resolve_high_potential`) — same sanitization pattern, separately implemented.
Confirmed: `predicted_red`/`predicted_blue` never reach a browser-facing surface via either channel
this pass covered. Did not check `/ws/prompter` specifically for this (lower risk — it only carries
timer state, no match_prediction relay was observed there), noting as lower-confidence-but-likely-fine
rather than fully verified.

## Debug pages

- `/api/v1/debug/integrations/{entity_id}/log`: empty for OBS/ZerOS/ATEM (correct — these
  integrations never publish to the event bus, this ring buffer only captures raw *events*, not
  service-call activity — confirmed by reading `backend/routers/debug.py`'s docstring). Populated
  correctly for `vextm_test`, showing the fake server's periodic `fieldStateChanged` heartbeat
  events in the right shape (last 100, newest first).
- `/ws/events` (backing `DebugEventBus`): connects fine with a valid session; gated on
  `settings:edit` per the page's own permission check (not independently re-verified with a
  restricted session this pass, but the code path is the same `require_permission` mechanism already
  confirmed working elsewhere).

## WebSocket channels — summary

| Channel | Result |
|---|---|
| `/ws/events` | Connects with session cookie; correctly sanitizes `match_prediction` payloads (see above) |
| `/ws/prompter/{id}` | Requires `?token=`; valid token → immediate correct `timer_state` push; no token → rejected pre-upgrade (HTTP 403) |
| `/ws/overlay/{id}` | Connects with no auth (intentional — public OBS browser-source use case); no message observed in a 4s window with no active match, which is the expected empty state |

---

## What's still genuinely untested, and why

- **Any real UI/SPA interaction** — layout, client-side form validation, the automation form
  builder's UX, the YAML raw-tab toggle, delete-button `confirm()` dialogs, drag-and-drop, dark
  mode, responsive layout. Blocked entirely on browser access this pass (sandboxed Browser pane
  can't reach `vex.localhost`; Claude-in-Chrome extension wasn't connected). Recommend a follow-up
  pass once one of those is sorted — happy to pick this up seamlessly since the backend/data state
  from this pass is still sitting in the local stack.
- **Spotify OAuth completion** — same as the prod pass, no test Spotify account.
- **ATEM against anything other than an unreachable IP** — deliberately not faked (see top of
  report); still only verified via the DEGRADED/backoff path.
- **A real second-user OIDC login for RBAC** — covered indirectly via scoped API keys (see Users/RBAC
  section) but not via an actual second Authelia account + browser login.
- **3-replica failover with continuous `/trigger` traffic across the whole transition** — only
  tested 2→1 replica, which trivially "succeeds after" since there's no longer a passive node.
- **`timer_milestone` triggers firing automations for real** — blocked on the same automations
  hot-reload bug (any automation created to test this wouldn't fire without a restart first); worth
  retesting once that's fixed.
- **Audit log filter UI params** — the endpoint accepts filters per its schema; didn't exercise them
  individually.

---

## State left behind

Local stack: scaled back down to 1 backend replica (per your instruction) after the HA test. Left
running: `qecomp-postgres`, `qecomp-redis`, `qecomp-minio`, `qecomp-traefik`, `qecomp-authelia`,
`vex-tm-tools-priv-backend-1`, plus the three fake servers (PIDs printed to
`/tmp/qecomp-fakes-logs/*.log`, started via `nohup` from `local-testing/fakes/`). Test data left in
Postgres (5 integrations, 2 automations, 1 script, 1 timer w/ 1 cue, 1 overlay, 1 team, 1 revoked +
1 active API key) since this is a disposable local DB and you said not to worry about cleanup here.
