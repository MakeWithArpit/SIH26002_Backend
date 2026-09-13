# SIH26002 Backend — Living Memory

> **Auto-maintained by the assistant.** Updated on every major milestone.
> Last updated: 2026-09-13

---

## 1. Project Identity

| Field          | Value                                                                           |
| -------------- | ------------------------------------------------------------------------------- |
| **Project**    | SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform (NER) |
| **Hackathon**  | Smart India Hackathon 2026                                                      |
| **Team Split** | Arpit = Django Backend; Omji = AI/ML models (CV, Risk, Route Ranking, ETA)      |
| **Repo**       | `MakeWithArpit/SIH26002_Backend` (GitHub `main` branch)                         |

---

## 2. Technical Environment (Local & Docker)

| Item                  | Value                                                                                                     |
| --------------------- | --------------------------------------------------------------------------------------------------------- |
| **OS / Runtime**      | Docker Container (`python:3.12-slim-bookworm`) on Windows 11 / WSL2                                       |
| **Python**            | 3.12 (in Docker)                                                                                          |
| **Django**            | 6.1                                                                                                       |
| **Containerization**  | Docker + Docker Compose (`web`, `redis`, `celery_worker`, `celery_beat`)                                  |
| **Shared Image**      | `sih26002_app:latest` (built once in `web`, reused across Celery worker & beat for 3x faster builds)       |
| **Database**          | Cloud Supabase PostgreSQL + PostGIS (`aws-0-ap-southeast-2.pooler.supabase.com:5432`)                     |
| **Database Pooler**   | Supabase Connection Pooler (IPv4 session mode on port 5432, user: `postgres.jjubqbdntgpuvsnipmcc`)         |
| **Database Fallback** | Local SQLite (`USE_SQLITE=True`) or local PostgreSQL 18                                                   |
| **PostGIS**           | PostGIS extension enabled on Supabase `postgres` DB                                                       |
| **GeoDjango Backend** | `django.contrib.gis.db.backends.postgis`                                                                  |
| **Task Queue & Cache**| Redis 7 (`redis:6379/0`), Celery 5.6+ worker & persistent scheduler beat (`celery-beat`)                  |
| **Settings Module**   | `DJANGO_SETTINGS_MODULE=config.settings.development`                                                      |
| **API Documentation** | OpenAPI 3.0 / Swagger UI at `/api/docs/`, Redoc at `/api/redoc/` (`drf-spectacular`)                      |

---

## 3. Phase Completion Status

| Phase        | Name                                 | Status      | Notes                                                                                                                                                           |
| ------------ | ------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phase 0**  | Backend Foundation                   | COMPLETE    | Django 6.1, DRF, JWT, PostGIS, GeoDjango, 4/4 tests passing                                                                                                     |
| **Phase 1**  | Field Intelligence & Photo Analysis  | COMPLETE    | IncidentReport (PointField, photo_url URLField via ImageKit CDN), photo analysis stub, Field Officer scoping, 5/5 tests passing (JSON payloads)                |
| **Phase 2**  | Road Network Graph & Disruption Risk | COMPLETE    | District & Infrastructure GeoDjango models, Rule-based Risk Engine (AI-01), Pilot corridor seed data, spatial snap integration, 7/7 tests passing               |
| **Phase 3**  | Risk-Aware Route Optimization        | COMPLETE    | NetworkX graph pathfinding, dynamic risk penalties, ephemeral RouteCandidate, AI-03 ranking & explanation, POST /calculate/, 4/4 tests passing (20/20 total)    |
| **Phase 4**  | Condition-Aware ETA Estimation       | COMPLETE    | Vehicle (cached telemetry), Trip (AI-02 ETA fields), LocationPing, ETAEstimationService, atomic ping ingestion, 7/7 tests passing (27/27 total)                 |
| **Phase 5**  | End-to-End Intelligence Pipeline     | COMPLETE    | Management command `demo_pipeline`, `POST /api/v1/routes/simulate-pipeline/` API, 7/7 tests passing (34/34 total backend tests passing)                          |
| **Phase 6**  | Weather Intelligence                 | COMPLETE    | Open-Meteo & IMD providers, WeatherSnapshot, sync_weather_task Celery periodic task, landslide & weather spatial enrichment                                      |
| **Phase 7**  | Vehicle Tracking                     | IN PROGRESS | Vehicle telemetry ingestion and O(1) polling endpoints live; trip lifecycle underway                                                                           |
| **Phase 8**  | Alerts & Automated Intelligence      | IN PROGRESS | AlertsView (`/api/v1/alerts/`) implemented; dynamic alert generation underway                                                                                   |
| **Phase 9**  | Offline Sync                         | NOT STARTED | P1/P2                                                                                                                                                           |
| **Phase 10** | Accessibility Intelligence           | NOT STARTED | P2                                                                                                                                                              |
| **Phase 11** | Dashboard APIs                       | NOT STARTED | P2                                                                                                                                                              |
| **Phase 12** | Production Hardening & Docker        | COMPLETE    | Dockerfile (Python 3.12 + GDAL), Docker Compose (`web`, `celery_worker`, `celery_beat`, `redis`), Supabase cloud PostgreSQL/PostGIS integration via Pooler      |

---

## 4. What Was Built (Phases 0–4)

### Phase 0 — Foundation

- `manage.py`, `config/settings/base.py`, `development.py`, `production.py`
- `config/wsgi.py`, `config/asgi.py`, `config/urls.py`
- `apps/accounts/` — Custom `Profile` model, `Role` choices (admin, field_officer, normal_user), JWT login/refresh views, 4 tests passing
- `apps/common/` — Unified success/data/error API envelope (responses.py, exceptions.py), `/api/v1/health/` endpoint
- PostGIS extension enabled, GeoDjango backend configured with Windows GDAL auto-discovery
- `requirements.txt` with approved dependencies

### Phase 1 — Field Intelligence & Photo Analysis

- `apps/reports/` — `IncidentReport` model with GeoDjango `PointField(srid=4326, geography=True)`, `photo_url` URLField (ImageKit CDN URL stored; no local media), AI prediction fields (`ai_issue_type`, `ai_severity`, `ai_confidence`, `analysis_status`), and foreign key `snapped_infrastructure`
- `apps/reports/services/photo_analysis.py` — Replaceable CV service wrapper (AI-08 stub matching AI/ML team contract; Phase 5 will fetch image via `requests.get(report.photo_url)`)
- `apps/reports/serializers.py` — Write (`IncidentReportCreateSerializer`) & Read (`IncidentReportSerializer`) with lat/lng conversion
- `apps/reports/views.py` — `IncidentReportViewSet` with `IsFieldOfficer` permissions, immutable reports, and officer vs admin query scoping
- `apps/reports/urls.py` — `/api/v1/reports/incidents/`
- `apps/reports/admin.py` — GeoDjango OSM admin registration
- `apps/reports/tests.py` — 5 unit/API tests (photo upload, AI execution, role permissions, officer scoping, validation error envelope)

### Phase 2 — Road Network Graph & Disruption Risk Intelligence

- `apps/routes/models.py` — `District` (`MultiPolygonField`, accessibility score, connectivity status) and `Infrastructure` (`LineStringField`, road classification, graph start/end nodes, static hazard ratings, dynamic rainfall/weather warnings, calculated disruption risk scores)
- `apps/routes/services/risk.py` — `RiskPredictionService` implementing explainable weighted rule-based scoring matching the AI-01 interface (0–100 score, disruption probability, risk level, top factors)
- `apps/reports/services/spatial_snap.py` — Live PostGIS proximity snapping (`ST_DWithin` 1000m buffer & fallback nearest neighbor) that snaps incoming incident reports to `Infrastructure` and automatically triggers risk recalculation
- `apps/routes/management/commands/seed_pilot_corridor.py` — Seeds Guwahati–Shillong (NH-06 / GS Road) corridor with 3 districts (Kamrup Metropolitan, Ri-Bhoi, East Khasi Hills) and 6 road segments
- `apps/routes/serializers.py` & `views.py` — `/api/v1/routes/districts/` and `/api/v1/routes/infrastructure/` with proximity filters (`?lat=...&lng=...&radius_m=...`) and custom `/assess-risk/` action
- `apps/routes/tests.py` — 7 unit & API tests (district listing, infrastructure filters, proximity queries, risk calculation contract, risk assess action, spatial snap integration, and role permissions)

### Phase 3 — Candidate Routes & Risk-Aware Route Optimization

- `apps/routes/services/routing/graph.py` — `RoadNetworkGraphService` building NetworkX graph from PostGIS `Infrastructure` records, coordinate-to-node snapping, and dual pathfinding:
  - Shortest Path (pure distance/travel time)
  - Safest Path (dynamic risk-penalized edge weights: $\text{distance} \times (1 + \frac{\text{risk}}{15}) \times 100 \text{ if blocked}$)
  - Ephemeral `RouteCandidate` dataclass with polylines and segment breakdowns (never a DB model)
- `apps/routes/services/route_ranking.py` — `RouteRankingService` (AI-03 wrapper) comparing candidates, weighing risk tradeoff against distance/time, picking recommended route, and generating transparent explanations
- `apps/routes/serializers.py` — `RouteCalculationRequestSerializer` (supports lat/lng coords or node IDs) and `RouteCandidateSerializer`
- `apps/routes/views.py` & `urls.py` — `POST /api/v1/routes/calculate/` endpoint returning ranked route candidates with polylines and explanations
- `apps/routes/tests.py` — 4 new tests (11 total in routes): safe bypass recommendation when highway is hazardous, shortest route recommendation when risk is low, coordinate-based calculation, and 401 unauthenticated protection

### Phase 4 — Condition-Aware ETA Estimation & Vehicle Tracking

- `apps/vehicles/models.py` —
  - `Vehicle`: registration number, vehicle type, cached telemetry (`current_lat`, `current_lng`, `current_speed`, `last_ping_time`) for O(1) polling per rules.md section 3.5.
  - `LocationPing`: historical telemetry breadcrumbs (timestamp, lat, lng, speed, heading, accuracy).
  - `Trip`: linked to vehicle, GeoDjango `origin` & `destination` (`PointField`), `base_eta_minutes`, `predicted_eta_minutes`, `expected_delay_minutes`, `delay_reasons`, and status lifecycle (PLANNED, IN_TRANSIT, COMPLETED, CANCELLED).
- `apps/vehicles/services/eta.py` — `ETAEstimationService` (AI-02 wrapper) implementing condition-aware travel time calculation:
  - Base speed by NER road classification (NH: 50 km/h, SH: 40 km/h, MDR: 30 km/h, Rural: 20 km/h).
  - Severe risk elevation (risk score > 66 increases travel time by 40%–75%).
  - Heavy rainfall & weather penalties (e.g. >50mm adds 25% travel time).
  - Real-time telemetry speed deficit calculation.
- `apps/vehicles/serializers.py` & `views.py` —
  - `VehicleViewSet`: CRUD + `POST /api/v1/vehicles/{id}/locations/` with atomic cache updates and `GET /api/v1/vehicles/{id}/location/latest/` for O(1) polling.
  - `TripViewSet`: CRUD + `POST /api/v1/trips/{id}/start/`, `POST /api/v1/trips/{id}/complete/`, `POST /api/v1/trips/{id}/recalculate-eta/`.
- `apps/vehicles/urls.py` & `admin.py` — Standard REST registration and GIS admin.
### Phase 5 — End-to-End Intelligence Pipeline

- `apps/routes/management/commands/demo_pipeline.py` — Management command running the 6-step intelligence pipeline demo on the NH-06 corridor:
  1. Field Officer submits geo-tagged critical incident report
  2. Spatial snap to nearest road segment (`Infrastructure`)
  3. Disruption risk engine recalculates (risk surges from MEDIUM to HIGH)
  4. Road network graph rebuilds with elevated edge weights
  5. Route ranking engine automatically switches recommendation from highway to safe detour
  6. ETA estimation computes delay and explanations; demo entities cleaned up automatically
- `apps/routes/views.py` & `urls.py` — `POST /api/v1/routes/simulate-pipeline/` endpoint orchestrating the full pipeline simulation in a single API call for hackathon judges and frontends.
- `apps/routes/test_pipeline.py` — 7 comprehensive integration tests covering individual pipeline stages, spatial snap, risk surges, route reranking, ETA estimations, and API endpoints.

### Phase 6 — Weather Intelligence & Landslide Enrichment
- `apps/routes/services/weather/` — Weather provider abstraction (Open-Meteo live API + mock/IMD fallback)
- `apps/routes/services/spatial_enrichment.py` — Spatial enrichment for weather snapshots and landslide susceptibility across the corridor
- `apps/routes/tasks.py` — Celery task `sync_weather_task` scheduled via Celery Beat for continuous background ingestion
- Dynamic rainfall integration updating `recent_rainfall_mm` and active weather warnings

### Phase 12 — Production Hardening, Docker & Cloud Database
- Multi-container architecture via `docker-compose.yml`:
  - `sih26002_web`: Django WSGI dev/production server (port 8000)
  - `sih26002_redis`: Redis 7 Alpine cache and Celery message broker
  - `sih26002_celery_worker`: Celery worker executing background tasks
  - `sih26002_celery_beat`: Celery beat periodic scheduler
- Optimized build pipeline: shared image `sih26002_app:latest` built once and reused across worker & beat
- Cloud Database: Supabase PostgreSQL with PostGIS extension connected via IPv4 Connection Pooler (Session mode, port 5432)
- Automated startup lifecycle: `entrypoint.sh` handles database readiness check, auto-migrations, and static collection

---

## 5. Key Architectural Decisions (Locked)

- Modular Monolith — no microservices
- Rule-Based First, ML Drop-in Later — Risk & ETA use configurable weighted scoring; stable service contracts allow Omji models to plug in without changing controllers or DB
- `RoadSegment` / `Infrastructure` as Central Entity — Field reports spatially snap to nearest segment (PostGIS ST_DWithin); risk score lives on the segment
- `RouteCandidate` is ephemeral — never stored as DB model, always computed response
- Pilot Corridor — MVP covers bounded NER corridor (e.g., Guwahati-Shillong / NH-06)
- Docker Compose Environment — Multi-container (`web`, `celery_worker`, `celery_beat`, `redis`) with shared image build
- Cloud Supabase PostgreSQL + PostGIS via IPv4 Connection Pooler (`aws-0-ap-southeast-2.pooler.supabase.com:5432`)
- No WebSockets, No MQTT, No S3, No GraphQL, No Kubernetes
- **ImageKit.io CDN for Photo Storage** — Mobile app uploads photos directly to ImageKit SDK, receives CDN URL, sends URL to backend. Backend stores only `photo_url` (URLField). No local `media/` volume. Phase 5 CV model fetches image via `requests.get(report.photo_url)` (CDN is public, no auth needed for GET).
- REST polling (10-15s) for vehicle location tracking using cached fields on `Vehicle`
- Last-Write-Wins (LWW) for offline sync conflict resolution
- **Ponytail Plugin Always Active:** Every implementation strictly adheres to `rules.md` and chooses the simplest, shortest, most minimal working solution (YAGNI).

---

## 6. Currently Working On

> Phase 6 (Weather) and Phase 12 (Containerization & Supabase) COMPLETE.
> Next up: Phase 7 (Vehicle Tracking & Trip Lifecycle Polish) & Phase 8 (Alerts Engine).

---

## 7. Immediate Next Steps

- [ ] Vehicle tracking live trip simulation and telemetry replay
- [ ] Push/pull alert generation triggered by elevated infrastructure risks
- [ ] Offline sync endpoints (Phase 9) with LWW resolution

---

## 8. Test Execution History

| Date       | Scope                              | Tests Run | Result    | Notes                                                                     |
| ---------- | ---------------------------------- | --------- | --------- | ------------------------------------------------------------------------- |
| 2026-09-04 | Phase 0 (Accounts & Health)        | 4         | 4 passed  | JWT auth, roles, error envelope                                           |
| 2026-09-05 | Phase 1 (Reports & Photo Analysis) | 5         | 5 passed  | Photo upload, PointField, AI stub, scoping, permissions                   |
| 2026-09-05 | Phase 2 (Road Network & Risk)      | 7         | 7 passed  | Districts, Infrastructure, Risk Engine, Proximity query, Snap integration |
| 2026-09-05 | Phase 3 (Route Optimization)       | 4 (11 in routes) | 11 passed | NetworkX pathfinding, safest detour ranking, coordinate resolution       |
| 2026-09-05 | Phase 4 (Vehicles & ETA Engine)    | 7         | 7 passed  | Telemetry ingestion, atomic cache, trip lifecycle, condition-aware ETA    |
| 2026-09-05 | Phase 5 (E2E Intelligence Pipeline)| 7 (18 in routes) | 18 passed | End-to-end simulation, spatial snap, risk spike, reranking, demo API      |
| 2026-09-05 | Full Suite (Phases 0–5)            | 34        | 34 passed | 100% pass across accounts, reports, routes, and vehicles                  |
| 2026-09-13 | Phase 1 (Reports — ImageKit migration) | 5     | 5 passed  | `photo` ImageField → `photo_url` URLField; multipart → JSON; migration 0003 applied cleanly |
