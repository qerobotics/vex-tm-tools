# QEComp backend image (plan §15 / Appendix B.1).
#
# Base image note: the plan's §15 example pins `python:3.12-slim`. Verified
# against `backend/requirements.txt`'s actual pins (fastapi==0.115.6,
# sqlalchemy[asyncio]==2.0.36, pydantic==2.10.4, numpy>=1.26,<2.3, etc.) —
# all ship manylinux wheels for 3.12, so the plan's pin is used as-is (no
# newer interpreter is required, and 3.12 has broader wheel availability
# than 3.13 for some transitive deps at time of writing).
#
# Wave 4a's `frontend/` has since landed (React/Vite SPA), so this is now a
# multi-stage build: an earlier `node:20-slim` stage runs
# `npm ci && npm run build` in `frontend/`, and its build output (a static
# `dist/`) is copied into the backend stage at `backend/static/frontend/`,
# which `backend/main.py` mounts and serves — same origin as the API, per
# the Traefik IngressRoute in `k8s/ingress.yaml` fronting a single `qecomp`
# service/port for both.
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

# ffmpeg: required by backend/modules/media/processor.py's green-screen
# keying pipeline. libvpx-dev: WebM/VP9 encoding support for the same
# pipeline (plan §5.13 / Appendix A.5).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libvpx-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini ./

# Built SPA static assets, served by backend/main.py at the same origin
# (see `_FRONTEND_DIST` there). Absent entirely in a backend-only dev
# checkout — main.py no-ops the mount/fallback route when this directory
# doesn't exist, so this COPY is the only place the two are wired together.
COPY --from=frontend-builder /app/frontend/dist backend/static/frontend/

# Drop root after all install/copy steps are done. The app only talks to
# Postgres/Redis/S3 over the network and writes media temp files via
# Python's tempfile module (defaults to world-writable /tmp), so no extra
# writable dirs are needed. UID/GID 1000 matches k8s/deployment.yaml's
# securityContext.
RUN groupadd --system --gid 1000 qecomp && useradd --system --uid 1000 --gid qecomp --no-create-home qecomp
RUN chown -R qecomp:qecomp /app
USER qecomp

# Exactly 1 worker per pod (Appendix B.1, critical) — multiple workers
# would each independently run their own LeaderElection/TimerManager/
# AutomationEngine/Loader instance inside the SAME pod, causing duplicate
# `qecomp:events` publishers and dual-command integration conflicts. HA is
# achieved via multiple k8s replicas (see k8s/deployment.yaml), each with
# its own single-worker process contending for the one Redis leader lock.
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
