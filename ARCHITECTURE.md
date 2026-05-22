# VEX TM Manager - Architecture & Modernization Plan

**Document Version:** 1.0  
**Last Updated:** 2026-05-22  
**Status:** Modernization Planning Phase

---

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [Technology Stack](#technology-stack)
3. [Component Overview](#component-overview)
4. [Data Flow & State Management](#data-flow--state-management)
5. [Integration Modules](#integration-modules)
6. [Proposed Architecture (HA & Modern Stack)](#proposed-architecture-ha--modern-stack)
7. [Migration Strategy](#migration-strategy)
8. [Deployment Infrastructure](#deployment-infrastructure)

---

## Current Architecture

### Overview

VEX TM Manager is a monolithic Python/Flask application designed to integrate with VEX Tournament Manager (TM) and control multi-system orchestration (Spotify, ATEM camera switcher, ZerOS lighting board). The application monitors match events from TM, processes them through an event pipeline, and triggers synchronized actions across integrated systems.

**Repository:** `vmd1/vex-tm-tools-priv`  
**Language Composition:** HTML (55.8%), Python (43.8%), Other (0.4%)  
**License:** Proprietary / Private  

### Key Characteristics

- **Single-instance deployment** with file-based configuration and state persistence
- **File-based storage** (JSON) for configuration, state, and timers
- **In-memory event queues** (asyncio) for inter-component communication
- **No database backend** - all state stored in JSON files
- **Monolithic architecture** - all integrations in one process
- **Manual JSON editing** required for configuration changes
- **No built-in HA/clustering support**
- **Thread + async hybrid** - Flask in daemon thread, asyncio event loop for core logic

### Repository Structure

```
vex-tm-tools-priv/
├── main.py                          # Application entry point, event loop orchestration
├── server.py                        # Flask web server (81KB, substantial codebase)
├── userManager.py                   # User authentication/authorization
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container image definition
├── compose.yml                      # Docker Compose for local development
├── README.md                        # High-level project description
├── ARCHITECTURE.md                  # This file
│
├── models/                          # Data models & type definitions
│   └── README.md
│
├── modules/                         # Integration plugins
│   ├── tm_manager/
│   │   ├── api_client.py           # VEX TM REST API client
│   │   ├── connector.py            # WebSocket connector to TM
│   │   └── schedule_fetcher.py     # Periodic schedule polling
│   ├── audio/
│   │   └── spotify/
│   │       └── controller.py       # Spotify API integration
│   ├── video/
│   │   └── atem/
│   │       └── controller.py       # ATEM switcher control
│   └── vfx/
│       └── zeros/
│           └── controller.py       # ZerOS lighting board (OSC)
│
├── static/                          # Frontend assets (CSS, JS, images)
├── templates/                       # Flask Jinja2 templates (HTML)
├── storage/                         # Persistent data (runtime files)
│   ├── config.json                 # Main configuration
│   ├── timer_state.json            # Active timer states
│   ├── timers_saved.json           # Timer definitions
│   └── action_lists.json           # Action list definitions
├── tools/                           # Utility scripts
├── docs/                            # Documentation
└── .github/                         # GitHub actions/workflows
```

---

## Technology Stack

### Current Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.12 | Core application logic |
| **Web Framework** | Flask 2.0+ | REST API & web UI |
| **Async Runtime** | asyncio | Event processing pipeline |
| **Message Protocol** | WebSocket | TM event streaming |
| **HTTP Client** | requests, aiohttp | External API calls |
| **Configuration** | JSON files | App & integration settings |
| **State Storage** | JSON files (local filesystem) | Config, state, timers |
| **Audio** | Spotipy 2.23+ | Spotify API integration |
| **Video** | PyATEMMax | ATEM switcher control |
| **Lighting** | python-osc 1.8+ | OSC commands to ZerOS |
| **Container** | Docker + Docker Compose | Development & deployment |
| **Auth** | Custom (userManager.py) | Basic user management |

### Current Dependencies

```
Werkzeug>=2.0              # WSGI utilities (Flask dependency)
Flask>=2.0                 # Web framework
websockets>=10.0,<12.0     # WebSocket client for TM
requests>=2.20             # HTTP library
spotipy>=2.23              # Spotify API Python library
PyATEMMax                  # ATEM switcher control
python-osc>=1.8            # Open Sound Control protocol
aiohttp>=3.8               # Async HTTP client
psutil>=5.9                # System/process utilities
```

---

## Component Overview

### 1. Main Entry Point (`main.py`, 449 lines)

**Responsibility:** Application initialization and event loop orchestration

**Key Classes/Functions:**
- `main()` - Async application initializer
- `run_flask()` - Runs Flask in daemon thread
- `TimerTickWorker` - Background worker for timer milestone triggers (every 50ms)

**Initialization Sequence:**
1. Load configuration from `storage/config.json`
2. Create VEX TM API client with credentials
3. Initialize VEX TM WebSocket connector
4. Create EventProcessor (core event pipeline)
5. Start ScheduleFetcher (periodic schedule polling)
6. Start MatchScheduler (match timing logic)
7. Start TimerTickWorker (50ms timer checks)
8. Start Flask server in daemon thread
9. Run asyncio event loop with all tasks

**State Management:**
- Reads timer states from `storage/timer_state.json`
- Monitors timer milestones and auto-triggers actions
- Caches schedule data (10-second TTL)
- Queues events to shared `asyncio.Queue`

### 2. Web Server & REST API (`server.py`, ~81KB)

**Responsibility:** HTTP REST API, WebSocket handling, HTML template serving

**Key Routes & Functionality:**
- Config management endpoints (GET/POST JSON)
- Timer CRUD operations
- Action list management
- Field state queries
- Spotify playback controls
- ATEM camera presets
- Lighting board controls
- Match queue management
- Real-time WebSocket connections (client notifications)

**Authentication:**
- Integrated with `userManager.py`
- Current: Basic token-based or session-based (to be replaced with OIDC)

**Frontend:**
- Serves static HTML/CSS/JS from `static/` and `templates/`
- Real-time updates via WebSocket
- Form-based configuration (currently requires manual JSON editing as fallback)

### 3. Event Processor (`modules/event_processor.py`)

**Responsibility:** Core event pipeline - processes events and triggers integrations

**Flow:**
1. Consumes events from asyncio queue
2. Evaluates event type (TM match state, timer milestone, manual command, etc.)
3. Applies action mappings (which integrations to trigger)
4. Calls appropriate controller methods (Spotify, ATEM, OSC)
5. Persists state changes
6. Logs audit trail

**Supported Event Types:**
- `match_start` / `match_end` / `match_update` - from TM
- `timer_finished` / `timer_milestone` - from timer worker
- `tm_command` - manual commands to TM
- `field_state_change` - field status updates
- Custom automation-triggered events

### 4. TM Manager Integration (`modules/tm_manager/`)

#### API Client (`api_client.py`)
- REST API calls to VEX TM Manager
- Handles OAuth2 token management
- Methods: `get()`, `post()`, `put()`, `delete()`
- Endpoints: `/api/fieldsets/{id}/matches`, `/api/fieldsets/{id}/fields`, etc.

#### WebSocket Connector (`connector.py`)
- Opens persistent WebSocket connection to TM
- Streams real-time field updates
- Pushes `field_state_change` events to queue
- Handles reconnection logic

#### Schedule Fetcher (`schedule_fetcher.py`)
- Periodic polling (configurable interval)
- Fetches match schedule from TM API
- Caches results locally
- Enables match-based automation triggers

**Configuration Keys** (from `config.json`):
```json
{
  "vex_tm_api": {
    "client_id": "...",
    "client_secret": "...",
    "api_key": "...",
    "base_url": "http://10.8.136.2",
    "field_set_id": 1,
    "enabled": true
  }
}
```

### 5. Audio Integration (`modules/audio/spotify/`)

**Controller:** Spotipy-based Spotify API integration

**Capabilities:**
- Play/pause/resume tracks from predefined playlists
- Trigger music on match start / custom events
- Timer-based music playback (e.g., entrance music duration)

**Configuration Keys**:
```json
{
  "device_ips": {
    "spotify": {
      "client_id": "...",
      "client_secret": "...",
      "redirect_uri": "https://..."
    }
  },
  "spotify_device_id": "Gaurav's MacBook Pro"
}
```

### 6. Video Integration (`modules/video/atem/`)

**Controller:** PyATEMMax-based ATEM switcher control

**Capabilities:**
- Automatically switch camera inputs based on active field
- Preset camera configurations (field 1 on input 1, etc.)
- Manual override via API

**Configuration Keys**:
```json
{
  "device_ips": {
    "atem": "10.8.142.254"
  },
  "field_to_camera": {
    "1": 1,
    "2": 2,
    "3": 3
  }
}
```

### 7. Lighting Integration (`modules/vfx/zeros/`)

**Controller:** python-osc-based ZerOS lighting board control

**Preset Allocations:**
- **1-4:** Field 1 ready (R), countdown (C), active (A), finish (F)
- **7-10:** Field 2 ready (R), countdown (C), active (A), finish (F)
- **13-16:** Field 3 ready (R), countdown (C), active (A), finish (F)
- **19:** Lectern (1 blue on each field, 1 white on lectern)
- **20:** Standby (1 blue on each field, 1 white on table)
- **21:** Stage (4 white on stage)
- **22:** Light show (Master of Puppets intro)

**Lighting States:**
- **Ready:** 2 red on field, 1 blue on other 2
- **Countdown:** 2 red on field, other 2 blue lights flash
- **Match:** 2 white on active field, 1 blue on other 2
- **Finish:** All lights flash white, spin, return to standby

---

## Data Flow & State Management

### Event Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     EVENT SOURCES                           │
└─────────────────────────────────────────────────────────────┘
         │              │                  │
         ▼              ▼                  ▼
    ┌─────────┐  ┌──────────┐       ┌────────────┐
    │   TM    │  │ Timer    │       │   REST API │
    │ WebSocket│ │ Worker   │       │  (Manual)  │
    │Connector │  │(50ms)    │       │            │
    └──────────┘  └──────────┘       └────────────┘
         │              │                  │
         └──────────────┼──────────────────┘
                        │
                        ▼
            ┌─────────────────────────┐
            │  asyncio.Queue()        │
            │  (Event Queue)          │
            └─────────────────────────┘
                        │
                        ▼
            ┌─────────────────────────┐
            │  EventProcessor         │
            │  .process_events()      │
            └─────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
    ┌────────┐   ┌──────────┐   ┌──────────┐
    │ Spotify│   │  ATEM    │   │  ZerOS   │
    │Control │   │ Control  │   │   OSC    │
    └────────┘   └──────────┘   └──────────┘
        │               │               │
        ▼               ▼               ▼
    ┌────────┐   ┌──────────┐   ┌──────────┐
    │ Spotify│   │  ATEM    │   │ ZerOS    │
    │ Server │   │ Switcher │   │ Board    │
    └────────┘   └──────────┘   └──────────┘
```

### State Persistence (File-Based)

**Current Approach:** JSON files in `storage/` directory

```
storage/
├── config.json              # Main app configuration (integrations, credentials)
├── timer_state.json         # Active timer runtime states (is_running, timestamps)
├── timers_saved.json        # Timer definitions (name, milestones, action_lists)
├── action_lists.json        # Action definitions (what to do on timer milestones)
└── audit.log                # Optional audit trail
```

**Limitations:**
- No concurrent access safety
- No transaction support
- Difficult to query or analyze state
- Cannot support multiple instances
- No built-in backup/replication
- Manual file editing required for configuration

---

## Integration Modules

### Module Structure

Each integration module follows a plugin-like pattern:

```python
class Controller:
    def __init__(self, config):
        self.config = config
        self.is_connected = False
    
    async def connect(self):
        # Establish connection to external system
        pass
    
    async def execute_action(self, action_type, payload):
        # Perform action based on event
        pass
    
    async def disconnect(self):
        # Cleanup
        pass
```

### Integration Coupling

**Current Design:**
- Integrations linked to **FieldSet** (TM concept)
- Event → FieldSet → Mapping → Integration action
- Hard to support multiple instances of same integration
- Difficult to decouple action logic from field state

**Proposed Design** (see Modernization Plan):
- Integrations decoupled from FieldSet
- Event → Automation Engine → YAML-defined trigger/condition/action
- Support N instances of each integration
- Home Assistant Automations-style configuration

---

## Proposed Architecture (HA & Modern Stack)

### High-Level Vision

Transform from a single-instance monolithic application to a **highly available, clustered system** with modern DevOps practices.

### Target Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      KUBERNETES (k3s)                            │
│                 (vmd1 k3scluster, 2-node HA)                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Ingress Controller                         │   │
│  │  qerobotics.com → CNAME → ingress.vmd1.dev            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                    │
│    ┌────────────────────────┼────────────────────────┐          │
│    │                        │                        │          │
│    ▼                        ▼                        ▼          │
│  ┌──────────┐          ┌──────────┐          ┌──────────┐     │
│  │ QEComp   │          │ Admin UI │          │  Auth    │     │
│  │ Server   │          │(React)   │          │(OIDC)    │     │
│  └──────────┘          └──────────┘          └──────────┘     │
│                             │                                    │
│    ┌────────────────────────┴────────────────────────┐          │
│    │                                                 │          │
│    ▼                                                 ▼          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │         VEX TM Manager (Python Backend)                │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │ Primary Instance (Active)    Primary Instance   │  │   │
│  │  │ - Event Processing           - Health Check    │  │   │
│  │  │ - Automation Engine          - Ready for FO    │  │   │
│  │  │ - Integration Controllers                      │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │ Secondary Instance (Passive/Standby)           │  │   │
│  │  │ - Ready to take over on Primary failure        │  │   │
│  │  │ - Replicates state from Primary               │  │   │
│  │  │ - Runs no integrations (hot-standby)          │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  │                                                         │   │
│  │  Both instances connected to:                         │   │
│  │  - Postgres HA (primary + replica)                    │   │
│  │  - Redis (Sentinel-managed, 3-node)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┐      ┌──────────────────┐               │
│  │ Postgres HA      │      │ Redis Sentinel   │               │
│  │ (2-node)         │      │ (3-node)         │               │
│  │ Primary/Standby  │      │ Cluster Manager  │               │
│  └──────────────────┘      └──────────────────┘               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Key Changes

#### 1. **Configuration Management**

**Current:** JSON files in `storage/`

**Proposed:**
- Move to YAML-based configuration (`.yaml` files)
- Config stored in Postgres + Redis cache
- Admin UI for configuration (no more file editing)
- Version control for config changes
- Role-based access control (RBAC)
- Config validation before apply

**Example YAML Structure:**
```yaml
# config.yaml
integrations:
  vex_tm:
    - name: "vex_tm_instance_1"
      enabled: true
      field_set_id: 1
      credentials:
        client_id: "..."
        client_secret: "..."
        api_key: "..."
      base_url: "http://10.8.136.2"
  
  spotify:
    - name: "spotify_instance_1"
      enabled: true
      credentials:
        client_id: "..."
        client_secret: "..."
      device_id: "..."
  
  atem:
    - name: "atem_switcher_main"
      enabled: true
      ip: "10.8.142.254"
      field_mapping:
        "1": 1
        "2": 2
        "3": 3

automations:
  - name: "match_start_music"
    trigger:
      type: "match_start"
      field_set_id: 1
    conditions:
      - field: "status"
        operator: "equals"
        value: "ACTIVE"
    actions:
      - integration: "spotify"
        instance: "spotify_instance_1"
        action: "play_playlist"
        params:
          playlist_id: "xyz"
  
  - name: "field_1_camera_switch"
    trigger:
      type: "field_state_change"
      field: 1
    conditions:
      - field: "state"
        operator: "equals"
        value: "ACTIVE"
    actions:
      - integration: "atem"
        instance: "atem_switcher_main"
        action: "switch_input"
        params:
          input: 1
```

#### 2. **Database Backend (Postgres HA)**

**Current:** No database (files only)

**Proposed:** PostgreSQL with High Availability

**Schema Overview:**
```sql
-- Core Tables
TABLE configurations (
  id UUID PRIMARY KEY,
  key TEXT UNIQUE,
  value JSONB,
  version INT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  updated_by UUID (FK users)
);

TABLE integrations (
  id UUID PRIMARY KEY,
  name TEXT,
  type TEXT, -- 'vex_tm', 'spotify', 'atem', 'zeros'
  enabled BOOLEAN,
  config JSONB, -- credentials, params
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

TABLE automations (
  id UUID PRIMARY KEY,
  name TEXT,
  enabled BOOLEAN,
  trigger JSONB,
  conditions JSONB,
  actions JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

TABLE field_states (
  id UUID PRIMARY KEY,
  field_id INT,
  state TEXT, -- 'QUEUED', 'COUNTDOWN', 'ACTIVE', 'FINISHED'
  current_match JSONB,
  updated_at TIMESTAMP
);

TABLE timers (
  id UUID PRIMARY KEY,
  name TEXT,
  field_id INT,
  is_running BOOLEAN,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  milestones JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

TABLE events (
  id UUID PRIMARY KEY,
  type TEXT, -- 'match_start', 'timer_milestone', etc.
  source TEXT, -- 'vex_tm', 'manual', 'automation'
  payload JSONB,
  processed BOOLEAN,
  created_at TIMESTAMP
);

TABLE audit_log (
  id UUID PRIMARY KEY,
  user_id UUID,
  action TEXT,
  resource TEXT,
  resource_id UUID,
  changes JSONB, -- before/after
  timestamp TIMESTAMP
);

TABLE users (
  id UUID PRIMARY KEY,
  username TEXT UNIQUE,
  email TEXT UNIQUE,
  oidc_sub TEXT UNIQUE, -- OIDC subject ID
  roles TEXT[], -- 'admin', 'operator', 'viewer'
  created_at TIMESTAMP,
  last_login TIMESTAMP
);
```

**HA Setup:**
- Primary + Hot Standby replica
- Automatic failover (via Patroni or Kubernetes operator)
- Encrypted replication
- Automated backups (daily snapshots to cloud storage)

#### 3. **Cache Layer (Redis HA with Sentinel)**

**Current:** In-memory asyncio queues (lost on restart)

**Proposed:** Redis with Sentinel for high availability

**Usage:**
- **Event Queue:** Distributed queue for inter-instance communication
- **State Cache:** Cache field states, match data (TTL-based)
- **Session Store:** HTTP sessions, auth tokens
- **Lock Manager:** Distributed locks for leader election (active-passive)
- **Rate Limiting:** API rate limit counters

**Sentinel Configuration:**
- 3-node Sentinel cluster
- Monitors Redis primary + replica
- Auto-promotes replica on primary failure
- Quorum-based failover

**Example Redis Keys:**
```
vex_tm:field:1:state         → HSET (field state JSON)
vex_tm:event:queue           → LPUSH/RPOP (event serialization)
vex_tm:config:cache          → SET (YAML parsed to JSON, TTL 300s)
vex_tm:lock:leader           → SET NX EX (leader election)
vex_tm:automation:last_run:* → HSET (last execution time/result)
```

#### 4. **Active-Passive HA Architecture**

**Node Configuration (2-node k3s cluster):**

| Role | Node | VEX TM Instance | Status | Function |
|------|------|-----------------|--------|----------|
| Primary | Node 1 | Active | RUNNING | Processing events, controlling integrations |
| Standby | Node 2 | Passive | STANDBY | Replicating state, ready for failover |

**Leader Election Mechanism:**
- Both instances try to acquire distributed lock in Redis: `vex_tm:lock:leader`
- Lock TTL: 30 seconds (with heartbeat renewal every 10s)
- On lock loss → standby promotes itself
- Both listen to Redis pub/sub for state sync

**Failover Logic:**
```python
# Pseudo-code
async def maintain_leadership():
    while True:
        try:
            # Try to acquire leader lock
            acquired = redis.set(
                "vex_tm:lock:leader",
                instance_id,
                ex=30,  # 30 second TTL
                nx=True  # Only if not exists
            )
            
            if acquired:
                # I'm the leader - run integrations
                self.is_leader = True
                await self.event_processor.start()
                await self.integration_controllers.start()
                
                # Renew lock every 10s
                while self.is_leader:
                    await asyncio.sleep(10)
                    redis.expire("vex_tm:lock:leader", 30)
            else:
                # Not leader - standby mode
                self.is_leader = False
                await self.event_processor.stop()
                await self.integration_controllers.stop()
                
                # Wait for lock to expire (30s) before retry
                await asyncio.sleep(5)
        
        except Exception as e:
            logger.error(f"Leader election error: {e}")
            await asyncio.sleep(5)
```

#### 5. **Automation Engine (YAML-Driven)**

**Current:** Hard-coded action mappings in EventProcessor

**Proposed:** Home Assistant Automations-style engine

**Features:**
- **Triggers:** Event-based (match_start, field_change, timer_end, etc.)
- **Conditions:** Boolean logic (field==active AND team==xyz)
- **Actions:** Multi-step integration calls with templating
- **Scripts:** Reusable action sequences
- **Performance:** Sub-100ms execution

**Example Automation:**
```yaml
automation:
  - id: "match_start_sync"
    alias: "Sync all systems on match start"
    trigger:
      platform: "vex_tm"
      event_type: "match_state_change"
      new_state: "ACTIVE"
    condition:
      - condition: "template"
        value_template: "{{ trigger.payload.field_id in [1, 2, 3] }}"
    action:
      - service: "integration.atem"
        data:
          action: "switch_input"
          params:
            input: "{{ trigger.payload.field_id }}"
      - service: "integration.zeros"
        data:
          action: "set_preset"
          params:
            preset_id: "{{ 3 + trigger.payload.field_id }}"  # Lighting preset
      - delay: "00:00:01"
      - service: "integration.spotify"
        data:
          action: "play_from_playlist"
          params:
            playlist: "match_music"

script:
  field_ready_sequence:
    sequence:
      - service: "integration.zeros"
        data:
          action: "set_preset"
          params:
            preset_id: "{{ field_id }}"
      - delay: "00:00:00.5"
      - service: "integration.atem"
        data:
          action: "switch_input"
          params:
            input: "{{ field_id }}"
```

#### 6. **Frontend Modernization**

**Current:** Flask-rendered HTML + basic Bootstrap UI

**Proposed:**
- **Framework:** React or Vue.js (modern SPA)
- **Styling:** TailwindCSS + vmd1.dev design system
- **Dynamic Navbar:** Generated from page routes/permissions
- **Real-time Updates:** WebSocket for live state sync
- **Admin Panels:**
  - Integration management (CRUD, test connections)
  - Automation builder (visual editor + YAML)
  - Field/match monitoring (live state, stats)
  - Timer management (create, edit, trigger)
  - User management & audit log viewer
- **Responsive Design:** Mobile-friendly admin dashboard

**Example UI Components:**
- Integration cards (connected/disconnected status, last action)
- Automation list with enable/disable toggles
- Field status board (real-time state, current match, active actions)
- Timer builder with milestone UI
- Match queue visualization
- Audit log with filters

#### 7. **Authentication (OIDC)**

**Current:** Basic token-based (insecure for production)

**Proposed:** OpenID Connect integration

**Flow:**
```
User → Login Button → Redirect to OIDC Provider (e.g., vmd1's OIDC)
  ↓
OIDC Provider → Verify credentials → Redirect back with ID token
  ↓
App validates token → Create session → Grant access

```

**Implementation:**
- Use `authlib` or `python-oauth2-lib` for OIDC
- Support multiple OIDC providers (configurable)
- JWT token validation + refresh
- Role claims from OIDC (admin, operator, viewer)
- Audit log OIDC events

**Configuration:**
```yaml
auth:
  oidc_enabled: true
  oidc_providers:
    - name: "vmd1_oidc"
      client_id: "..."
      client_secret: "..."
      authorization_url: "https://auth.vmd1.dev/authorize"
      token_url: "https://auth.vmd1.dev/token"
      userinfo_url: "https://auth.vmd1.dev/userinfo"
      jwks_uri: "https://auth.vmd1.dev/.well-known/jwks.json"
      scope: "openid profile email"
      role_claim: "roles"
```

#### 8. **Navbar (Dynamic Generation)**

**Current:** Static HTML navbar

**Proposed:** Generated from routes + user permissions

```python
# Example: Backend exposes navbar definition
GET /api/navigation
{
  "items": [
    {
      "label": "Dashboard",
      "href": "/dashboard",
      "icon": "dashboard",
      "required_roles": ["viewer"]
    },
    {
      "label": "Integrations",
      "href": "/integrations",
      "icon": "plug",
      "required_roles": ["admin", "operator"],
      "children": [
        {"label": "Spotify", "href": "/integrations/spotify"},
        {"label": "ATEM", "href": "/integrations/atem"},
        {"label": "ZerOS", "href": "/integrations/zeros"}
      ]
    },
    {
      "label": "Automations",
      "href": "/automations",
      "icon": "automation",
      "required_roles": ["admin"]
    },
    {
      "label": "Audit Log",
      "href": "/audit",
      "icon": "log",
      "required_roles": ["admin"]
    },
    {
      "label": "Settings",
      "href": "/settings",
      "icon": "settings",
      "required_roles": ["admin"]
    }
  ]
}

# Frontend filters by user's roles, renders dynamic navbar
```

#### 9. **Domain & Routing**

**Current:** Deployed on GitHub Codespaces with auto-generated URL

**Proposed:**
- Acquire `qerobotics.com` domain
- Set CNAME: `qerobotics.com → ingress.vmd1.dev`
- k3s Ingress controller routes HTTP/HTTPS to:
  - `/qecomp` → QEComp server (separate service)
  - `/vex-tm-manager` → VEX TM Manager app
  - `/auth` → OIDC relay (optional)

**Ingress Configuration:**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: vex-tm-ingress
  namespace: vex-tm
spec:
  ingressClassName: traefik
  rules:
    - host: qerobotics.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: vex-tm-manager
                port:
                  number: 5000
          - path: /qecomp
            pathType: Prefix
            backend:
              service:
                name: qecomp-server
                port:
                  number: 8080
  tls:
    - hosts:
        - qerobotics.com
      secretName: qerobotics-tls
```

---

## Migration Strategy

### Phase 1: Foundation (Weeks 1-3)

**Goals:** Set up infrastructure, database schema, basic HA support

**Deliverables:**
1. Postgres HA cluster deployed to k3s
   - Schema migration from config.json → tables
   - Migration scripts for existing data
2. Redis Sentinel cluster deployed
   - Monitors + manages Redis instances
   - Configuration for state cache + queues
3. Configuration loader refactored
   - Support both JSON (legacy) and YAML (new)
   - Postgres as source of truth
   - Redis caching layer
4. Leader election implemented in app
   - Acquire/maintain lock in Redis
   - Standby mode detection
   - Failover tests

**Technical Tasks:**
- Write Postgres migration scripts
- Create Helm charts for Postgres + Sentinel deployment
- Refactor `models.config.Config` to load from Postgres
- Implement `RedisLeaderElection` class
- Unit tests for leader election logic

### Phase 2: Core Application (Weeks 4-6)

**Goals:** Refactor event processing, enable multi-instance support

**Deliverables:**
1. Event processor refactored
   - Use Redis queues instead of asyncio.Queue
   - Distributed lock for processing (prevent duplication)
   - Event batching for performance
2. Automation engine built
   - YAML trigger/condition/action evaluation
   - Support for templating (Jinja2)
   - Action executor with integration dispatch
3. Integration controllers decoupled
   - Each integration instance is independent
   - No hardcoded FieldSet mapping
   - Configuration-driven (from Postgres)
4. Health check endpoints
   - `/health` for K8s liveness/readiness probes
   - `/health/postgres` for DB connectivity
   - `/health/redis` for cache connectivity

**Technical Tasks:**
- Refactor `EventProcessor` to use Redis queues
- Build `AutomationEngine` class (YAML evaluation)
- Refactor integration controllers to support multiple instances
- Write Postgres queries for automation lookup/execution
- Add health check endpoints to Flask

### Phase 3: Frontend & UI (Weeks 7-9)

**Goals:** Build modern UI, implement OIDC auth

**Deliverables:**
1. React/Vue SPA scaffold
   - TailwindCSS + vmd1.dev design system
   - Dynamic navbar from `/api/navigation`
   - Responsive layout
2. Admin dashboards
   - Integration management CRUD
   - Automation builder (list + form-based editor)
   - Field/match status dashboard
   - Timer management
3. OIDC authentication
   - Login/logout flow
   - JWT token handling (storage, refresh)
   - Role-based UI elements (RBAC)
4. WebSocket real-time updates
   - Field state changes
   - Event log stream
   - Integration status

**Technical Tasks:**
- Set up React/Vue build (Vite)
- Create API client library (typed)
- Build integration management UI component
- Implement automation builder (list view + editor modal)
- Add WebSocket client for real-time updates
- OIDC auth module (authlib integration)

### Phase 4: Configuration & YAML Migration (Weeks 10-11)

**Goals:** Move from .json to YAML, provide UI-based configuration

**Deliverables:**
1. YAML configuration system
   - Full schema for integrations, automations, field mappings
   - Validation (JSONSchema or Pydantic)
   - Version control (git-backed configs)
2. Config UI editor
   - YAML syntax highlighting
   - Live validation & preview
   - Diff viewer (before/apply)
   - Rollback capability
3. Migration scripts
   - Auto-convert existing config.json → YAML
   - Preserve all settings
   - Validation of migrated configs

**Technical Tasks:**
- Design YAML schema (config.schema.yaml)
- Create YAML config loader (Pydantic models)
- Build YAML editor UI component
- Migration script (config.json → YAML)
- Config validation/preview endpoints

### Phase 5: Testing & Hardening (Weeks 12-13)

**Goals:** Ensure HA reliability, performance, security

**Deliverables:**
1. Comprehensive test suite
   - Unit tests for automation engine
   - Integration tests (local Docker Compose)
   - HA failover tests (primary crash → secondary takeover)
   - Load tests (event throughput)
2. Documentation
   - Operator runbook (deploy, monitor, troubleshoot)
   - Admin guide (add integrations, create automations)
   - Architecture decision records (ADRs)
   - Troubleshooting guide
3. Security hardening
   - Input validation (OWASP)
   - SQL injection prevention (parameterized queries)
   - XSS prevention (template escaping)
   - CSRF tokens
   - Rate limiting on APIs
4. Monitoring & observability
   - Prometheus metrics (event count, latency, errors)
   - Loki logging (centralized logs)
   - Grafana dashboards
   - Alert rules (high error rates, low disk space, etc.)

**Technical Tasks:**
- Write pytest tests (event processor, automation engine, integrations)
- Create k3s test environment (2-node cluster)
- Failover test scripts
- Load test (k6 or Locust)
- Prometheus instrumentation
- Loki log aggregation
- Grafana dashboard templates

### Phase 6: Domain & External Integration (Weeks 14-15)

**Goals:** Connect to qerobotics domain, finalize deployment

**Deliverables:**
1. Domain registration & DNS
   - Register `qerobotics.com`
   - Create CNAME: `qerobotics.com → ingress.vmd1.dev`
   - SSL certificate (Let's Encrypt via cert-manager)
2. QEComp server integration
   - Deploy QEComp alongside VEX TM Manager
   - Ingress routing (`/qecomp` → QEComp, `/` → VEX TM)
3. Production deployment
   - Production k3s cluster configuration
   - Backup/restore procedures
   - Disaster recovery plan (2-hour RTO, 30min RPO target)

**Technical Tasks:**
- Domain registration
- DNS configuration
- Cert-manager + Let's Encrypt setup
- QEComp deployment manifests
- Ingress routing rules
- Backup automation (daily snapshots)
- Runbooks for common failures

### Phase 7: Launch & Monitoring (Weeks 16+)

**Goals:** Go live, monitor, optimize

**Deliverables:**
1. Staged rollout
   - Canary deployment (10% traffic)
   - Monitor error rates, latency
   - Full production rollout
2. Post-launch support
   - Monitor metrics, logs, alerts
   - Respond to incidents
   - Gather user feedback
3. Optimization
   - Performance tuning (caching, query optimization)
   - Cost optimization (right-size resources)
   - Feature requests + improvements

---

## Deployment Infrastructure

### Kubernetes (k3s) Cluster

**Cluster Configuration:**
- **Distribution:** k3s (lightweight Kubernetes)
- **Nodes:** 2 nodes in vmd1 k3scluster
- **Load Balancer:** Traefik (built-in with k3s)
- **Storage:** Local persistent volumes

**Namespaces:**
```
vex-tm/              # VEX TM Manager app + Postgres + Redis
monitoring/          # Prometheus, Loki, Grafana
ingress/             # Traefik ingress controller
cert-manager/        # SSL/TLS certificate management
```

### Helm Charts (to be created)

**Chart Structure:**
```
helm/
├── vex-tm-manager/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── templates/
│   │   ├── deployment.yaml      # 2 replicas (1 active, 1 standby)
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   └── hpa.yaml             # Auto-scaling (optional)
│   └── README.md
│
├── postgres-ha/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── templates/
│   │   ├── primary.yaml
│   │   ├── replica.yaml
│   │   ├── service.yaml
│   │   └── backup.yaml
│   └── README.md
│
└── redis-sentinel/
    ├── Chart.yaml
    ├── values.yaml
    ├── templates/
    │   ├── redis-master.yaml
    │   ├── redis-replica.yaml
    │   ├── sentinel.yaml
    │   └── service.yaml
    └── README.md
```

### Docker Image

**Proposed Multi-Stage Dockerfile:**
```dockerfile
# Build stage
FROM python:3.12-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.12-slim
WORKDIR /srv/vex-tm
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/health')"

EXPOSE 5000
CMD ["python", "main.py"]
```

### Docker Compose (Development)

**Updated compose.yml:**
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: vex_tm
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: vex_tm
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vex_tm"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    build: .
    environment:
      DATABASE_URL: postgresql://vex_tm:changeme@postgres:5432/vex_tm
      REDIS_URL: redis://redis:6379
      FLASK_ENV: development
      LOG_LEVEL: DEBUG
    ports:
      - "5000:5000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - .:/srv/vex-tm
    command: python main.py

volumes:
  postgres_data:
  redis_data:
```

---

## Summary of Transformations

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Config Format** | JSON files | YAML + Postgres |
| **Config Editing** | Manual file edit | Admin UI |
| **State Storage** | Local JSON files | Postgres + Redis cache |
| **Message Queue** | In-memory asyncio | Redis (distributed) |
| **HA Support** | None | Active-passive 2-node cluster |
| **Auth** | Basic token | OIDC (external provider) |
| **Frontend** | Flask templates | React/Vue SPA |
| **Styling** | Bootstrap | TailwindCSS + vmd1.dev |
| **Navbar** | Static HTML | Dynamic (from routes) |
| **Integrations** | Linked to FieldSet | Decoupled, multiple instances |
| **Automations** | Hard-coded mappings | YAML-driven engine |
| **Scripting** | None | Home Assistant-style |
| **Database** | None | Postgres with HA |
| **Cache** | None | Redis + Sentinel |
| **Deployment** | Single instance | k3s cluster (2-node) |
| **Domain** | GitHub Codespaces URL | qerobotics.com via k3s Ingress |
| **Monitoring** | Logs only | Prometheus + Loki + Grafana |

---

## Appendix: Glossary

- **HA (High Availability):** System continues operating despite component failures
- **Active-Passive:** Only one instance actively processes work; other is standby
- **Leader Election:** Distributed algorithm to select single active instance
- **TTL (Time-To-Live):** Automatic expiration of cache/session data
- **Sentinel:** Redis component for monitoring and failover
- **Replica:** Copy of primary database for redundancy
- **OIDC:** OpenID Connect - modern authentication standard
- **k3s:** Lightweight Kubernetes distribution for edge/small clusters
- **Ingress:** Kubernetes object for external HTTP(S) routing
- **SPA (Single Page Application):** Frontend loaded once, updates via API
- **Jinja2:** Templating engine (used for condition/action evaluation)
- **OSC (Open Sound Control):** Protocol for controlling music/audio systems

---

## References

**VEX TM Documentation:**
- API Guide: https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit
- API Intro: https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API

**Integration Libraries:**
- Spotipy: https://spotipy.readthedocs.io/
- PyATEMMax: https://clvlabs.github.io/PyATEMMax/
- python-osc: https://python-osc.readthedocs.io/

**Kubernetes & Deployment:**
- k3s: https://k3s.io/
- Helm: https://helm.sh/
- Traefik: https://traefik.io/

**Home Assistant (Inspiration for Automations):**
- https://www.home-assistant.io/docs/automation/

---

**Document prepared for:** Next-generation development team  
**Questions/Clarifications:** Refer to vmd1/vex-tm-tools-priv repository issues  
**Last Reviewed:** 2026-05-22

