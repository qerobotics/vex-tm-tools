# QEComp

VEX TM competition-control system: connects to a VEX TM field-set
WebSocket/REST API and drives Spotify playback, an ATEM switcher, a ZerOS
lighting board, and OBS scenes off match events, via a YAML/Jinja2
automation engine. Full rewrite of the original single-instance Flask/
JSON-file tool into a clustered FastAPI + Postgres + Redis backend with a
React admin SPA — see [`tm_update_plan.md`](tm_update_plan.md) for the
complete design (architecture decisions, schema, API surface, RBAC model,
deployment plan) and [`docs/API.md`](docs/API.md) for the generated REST
API reference.

## Layout

| Path | What |
|---|---|
| [`backend/`](backend/) | FastAPI app: leader election, the integration loader + clients (VEX TM/Spotify/ATEM/ZerOS/OBS), the automation engine, REST routers, WebSocket fan-out |
| [`frontend/`](frontend/) | React + Vite admin SPA |
| [`alembic/`](alembic/) | Postgres schema migrations |
| [`k8s/`](k8s/) | Kubernetes manifests for the real k3s deployment |
| [`docs/`](docs/) | Generated API reference, Authentik/OIDC setup guide, third-party hardware/API reference docs |
| [`local-testing/`](local-testing/) | Throwaway local Traefik + Authelia stack for exercising real OIDC login — **not** the real infrastructure (that's `k8s/`) |
| [`tools/`](tools/) | One-off operational scripts |

## Running it locally

```bash
docker compose up -d postgres redis minio   # backend/frontend run on the host, not in this compose file

cd backend && python3 -m venv .venv-backend && source .venv-backend/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Visit `http://localhost:5173`, and use the emergency admin login at
`/admin_login` (username `admin_local`, password from the
`ADMIN_LOCAL_PASSWORD` env var) — no OIDC provider is required for this
path. To exercise a real OIDC login instead, see
[`local-testing/README.md`](local-testing/README.md).

## Tests

```bash
cd backend && pytest --cov=backend --cov-report=term-missing
```

Needs Postgres/Redis reachable (`docker compose up -d postgres redis`) and,
for the media-pipeline tests, MinIO (`docker compose up -d minio`) plus a
local `ffmpeg` binary.

## Contribution guidelines

Open a pull request rather than committing directly to `main` so changes
get reviewed.

## Hardware reference

Links and notes for the physical equipment this system drives, carried
over from the project's original notes:

**VEX TM Public API**
- [API guide](https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit?tab=t.0)
- [API intro](https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API)

**Spotify** — [Web API docs](https://developer.spotify.com/documentation/web-api)

**ATEM switching** (V5RC only) — [PyATEMMax](https://clvlabs.github.io/PyATEMMax/)

**ZerOS lighting board** (OSC control)
- [FLX S48 manual](https://support.vikinglighting.co.uk/downloads/FLX%20S%20User%20Manual%20v1.pdf)
- [ZerOS OSC triggers](https://www.zero88.com/manuals/zeros/setup/triggers/osc), [python-osc](https://python-osc.readthedocs.io/en/latest/)
- Rogue R2X Wash: [manual](https://www.chauvetprofessional.com/wp-content/uploads/2019/10/Rogue_R2X_Wash_UM_Rev2.pdf), [quick reference](https://www.chauvetprofessional.com/wp-content/uploads/2020/01/Rogue_wash_VW_QRG_ML5_Rev4.pdf)

<details>
<summary>Lighting patterns (preset allocations)</summary>

| Presets | Meaning |
|---|---|
| 1–4 | Field 1: ready (R), countdown (C), active (A), finish (F) |
| 7–10 | Field 2: ready (R), countdown (C), active (A), finish (F) |
| 13–16 | Field 3: ready (R), countdown (C), active (A), finish (F) |
| 19 | Lectern (1 blue on each field, 1 white on lectern) |
| 20 | Standby (1 blue on each field, 1 white on table) |
| 21 | Stage (4 white on stage) |
| 22? | Light show (Master of Puppets intro) |

**Preset info**
- **ready** — 2 red on the field about to start, 1 blue on the other 2
- **countdown** — 2 red on the field about to start, other 2 blue lights flash with the countdown
- **match** — 2 white on the field with a match, 1 blue on the other 2
- **finish** — all lights flash white, spin around, and return to standby

</details>
