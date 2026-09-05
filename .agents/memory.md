# SIH26002 Backend — Living Memory

> **Auto-maintained by the assistant.** Updated on every major milestone.
> Last updated: 2026-09-05

---

## 1. Project Identity

| Field          | Value                                                                           |
| -------------- | ------------------------------------------------------------------------------- |
| **Project**    | SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform (NER) |
| **Hackathon**  | Smart India Hackathon 2026                                                      |
| **Team Split** | Arpit = Django Backend; Omji = AI/ML models (CV, Risk, Route Ranking, ETA)      |
| **Repo**       | `MakeWithArpit/SIH26002_Backend` (GitHub `main` branch)                         |

---

## 2. Technical Environment (Local Dev)

| Item                  | Value                                                                                     |
| --------------------- | ----------------------------------------------------------------------------------------- |
| **OS**                | Windows 11                                                                                |
| **Python**            | 3.14 (via `.venv`)                                                                        |
| **Django**            | 5.1                                                                                       |
| **Database**          | PostgreSQL 18 (`localhost:5432`, db=`sih26002_db`, user=`postgres`)                       |
| **PostGIS**           | 3.6.2 enabled on `sih26002_db`                                                            |
| **GDAL**              | `libgdal-35.dll` from `C:\Program Files\PostgreSQL\18\bin` (auto-discovered in `base.py`) |
| **GeoDjango Backend** | `django.contrib.gis.db.backends.postgis`                                                  |
| **Settings Module**   | `DJANGO_SETTINGS_MODULE=config.settings.development`                                      |
| **DB Engine in .env** | `DB_ENGINE=django.contrib.gis.db.backends.postgis`                                        |
| **USE_SQLITE**        | `False`                                                                                   |

---

## 3. Phase Completion Status

| Phase        | Name                                 | Status      | Notes                                                                                                                                                           |
| ------------ | ------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phase 0**  | Backend Foundation                   | COMPLETE    | Django 5.1, DRF, JWT, PostGIS, GeoDjango, 4/4 tests passing                                                                                                     |
| **Phase 1**  | Field Intelligence & Photo Analysis  | COMPLETE    | IncidentReport (PointField, photo), photo analysis stub, Field Officer scoping, 5/5 tests passing                                                               |
| **Phase 2**  | Road Network Graph & Disruption Risk | COMPLETE    | District & Infrastructure GeoDjango models, Rule-based Risk Engine (AI-01), Pilot corridor seed data, spatial snap integration, 7/7 tests passing               |
| **Phase 3**  | Risk-Aware Route Optimization        | COMPLETE    | NetworkX graph pathfinding, dynamic risk penalties, ephemeral RouteCandidate, AI-03 ranking & explanation, POST /calculate/, 4/4 tests passing (20/20 total)    |
| **Phase 4**  | Condition-Aware ETA Estimation       | COMPLETE    | Vehicle (cached telemetry), Trip (AI-02 ETA fields), LocationPing, ETAEstimationService, atomic ping ingestion, 7/7 tests passing (27/27 total)                 |
| **Phase 5**  | End-to-End Intelligence Pipeline     | READY       | Next up: Demo pipeline script, end-to-end incident to detour & ETA recalc walkthrough                                                                           |
| **Phase 6**  | Weather Intelligence                 | NOT STARTED | P1                                                                                                                                                              |
| **Phase 7**  | Vehicle Tracking                     | NOT STARTED | P1                                                                                                                                                              |
| **Phase 8**  | Alerts & Automated Intelligence      | NOT STARTED | P1                                                                                                                                                              |
| **Phase 9**  | Offline Sync                         | NOT STARTED | P1/P2                                                                                                                                                           |
| **Phase 10** | Accessibility Intelligence           | NOT STARTED | P2                                                                                                                                                              |
| **Phase 11** | Dashboard APIs                       | NOT STARTED | P2                                                                                                                                                              |
| **Phase 12** | Production Hardening                 | NOT STARTED | P2                                                                                                                                                              |

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

- `apps/reports/` — `IncidentReport` model with GeoDjango `PointField(srid=4326, geography=True)`, photo uploads, AI prediction fields (`ai_issue_type`, `ai_severity`, `ai_confidence`, `analysis_status`), and foreign key `snapped_infrastructure`
- `apps/reports/services/photo_analysis.py` — Replaceable CV service wrapper (AI-08 stub matching AI/ML team contract)
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
- `apps/vehicles/tests.py` — 7 unit & API tests (Vehicle CRUD, location ping ingestion & atomic cache update, trip lifecycle, ETA penalty calculation, and recalculation endpoint).

---

## 5. Key Architectural Decisions (Locked)

- Modular Monolith — no microservices
- Rule-Based First, ML Drop-in Later — Risk & ETA use configurable weighted scoring; stable service contracts allow Omji models to plug in without changing controllers or DB
- `RoadSegment` / `Infrastructure` as Central Entity — Field reports spatially snap to nearest segment (PostGIS ST_DWithin); risk score lives on the segment
- `RouteCandidate` is ephemeral — never stored as DB model, always computed response
- Pilot Corridor — MVP covers bounded NER corridor (e.g., Guwahati-Shillong / NH-06)
- No WebSockets, No MQTT, No S3, No GraphQL, No Kubernetes
- REST polling (10-15s) for vehicle location tracking using cached fields on `Vehicle`
- Last-Write-Wins (LWW) for offline sync conflict resolution
- **Ponytail Plugin Always Active:** Every implementation strictly adheres to `rules.md` and chooses the simplest, shortest, most minimal working solution (YAGNI).

---

## 6. Currently Working On

> Phase 4 verified and COMPLETE (27/27 total backend tests passing).
> Next up: Phase 5 — End-to-End Intelligence Pipeline (Live Hackathon Demo script connecting photo incident -> spatial snap -> segment risk elevation -> route recalculation -> vehicle trip ETA delay update).

---

## 7. Immediate Next Steps (Phase 5 Checklist)

- [ ] Management command / test runner simulating the end-to-end incident-to-reroute-and-ETA pipeline
- [ ] Verify full corridor demo workflow (report landslide on NH-06 -> auto-snap to highway -> segment risk score surges to 85+ -> recalculate route selects safe MDR bypass -> trip ETA updates with delay explanation)
- [ ] Ensure seamless DRF API demonstration for hackathon presentation

---

## 8. Test Execution History

| Date       | Scope                              | Tests Run | Result    | Notes                                                                     |
| ---------- | ---------------------------------- | --------- | --------- | ------------------------------------------------------------------------- |
| 2026-09-04 | Phase 0 (Accounts & Health)        | 4         | 4 passed  | JWT auth, roles, error envelope                                           |
| 2026-09-05 | Phase 1 (Reports & Photo Analysis) | 5         | 5 passed  | Photo upload, PointField, AI stub, scoping, permissions                   |
| 2026-09-05 | Phase 2 (Road Network & Risk)      | 7         | 7 passed  | Districts, Infrastructure, Risk Engine, Proximity query, Snap integration |
| 2026-09-05 | Phase 3 (Route Optimization)       | 4 (11 in routes) | 11 passed | NetworkX pathfinding, safest detour ranking, coordinate resolution       |
| 2026-09-05 | Phase 4 (Vehicles & ETA Engine)    | 7         | 7 passed  | Telemetry ingestion, atomic cache, trip lifecycle, condition-aware ETA    |
| 2026-09-05 | Full Suite (Phases 0–4)            | 27        | 27 passed | 100% pass across accounts, reports, routes, and vehicles                  |
