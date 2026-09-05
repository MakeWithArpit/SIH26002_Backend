# SIH26002 Backend — Living Memory

> **Auto-maintained by the assistant.** Updated on every major milestone.
> Last updated: 2026-09-05

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project** | SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform (NER) |
| **Hackathon** | Smart India Hackathon 2026 |
| **Team Split** | Arpit = Django Backend; Omji = AI/ML models (CV, Risk, Route Ranking, ETA) |
| **Repo** | `MakeWithArpit/SIH26002_Backend` (GitHub `main` branch) |

---

## 2. Technical Environment (Local Dev)

| Item | Value |
|---|---|
| **OS** | Windows 11 |
| **Python** | 3.14 (via `.venv`) |
| **Django** | 5.1 |
| **Database** | PostgreSQL 18 (`localhost:5432`, db=`sih26002_db`, user=`postgres`) |
| **PostGIS** | 3.6.2 enabled on `sih26002_db` |
| **GDAL** | `libgdal-35.dll` from `C:\Program Files\PostgreSQL\18\bin` (auto-discovered in `base.py`) |
| **GeoDjango Backend** | `django.contrib.gis.db.backends.postgis` |
| **Settings Module** | `DJANGO_SETTINGS_MODULE=config.settings.development` |
| **DB Engine in .env** | `DB_ENGINE=django.contrib.gis.db.backends.postgis` |
| **USE_SQLITE** | `False` |

---

## 3. Phase Completion Status

| Phase | Name | Status | Notes |
|---|---|---|---|
| **Phase 0** | Backend Foundation | COMPLETE | Django 5.1, DRF, JWT, PostGIS, GeoDjango, 4/4 tests passing |
| **Phase 1** | Field Intelligence & Photo Analysis | COMPLETE | IncidentReport (PointField, photo), photo analysis stub, Field Officer scoping, 5/5 tests passing |
| **Phase 2** | Road Network Graph & Disruption Risk | COMPLETE | District & Infrastructure GeoDjango models, Rule-based Risk Engine (AI-01), Pilot corridor seed data, spatial snap integration, 7/7 tests passing (16/16 total) |
| **Phase 3** | Risk-Aware Route Optimization | READY | Next up |
| **Phase 4** | Condition-Aware ETA Estimation | NOT STARTED | |
| **Phase 5** | End-to-End Intelligence Pipeline | NOT STARTED | Hackathon Demo |
| **Phase 6** | Weather Intelligence | NOT STARTED | P1 |
| **Phase 7** | Vehicle Tracking | NOT STARTED | P1 |
| **Phase 8** | Alerts & Automated Intelligence | NOT STARTED | P1 |
| **Phase 9** | Offline Sync | NOT STARTED | P1/P2 |
| **Phase 10** | Accessibility Intelligence | NOT STARTED | P2 |
| **Phase 11** | Dashboard APIs | NOT STARTED | P2 |
| **Phase 12** | Production Hardening | NOT STARTED | P2 |

---

## 4. What Was Built (Phases 0–2)

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

---

## 5. Key Architectural Decisions (Locked)

- Modular Monolith — no microservices
- Rule-Based First, ML Drop-in Later — Risk & ETA use configurable weighted scoring; stable service contracts allow Omji models to plug in without changing controllers or DB
- `RoadSegment` / `Infrastructure` as Central Entity — Field reports spatially snap to nearest segment (PostGIS ST_DWithin); risk score lives on the segment
- `RouteCandidate` is ephemeral — never stored as DB model, always computed response
- Pilot Corridor — MVP covers bounded NER corridor (e.g., Guwahati-Shillong / NH-06)
- No WebSockets, No MQTT, No S3, No GraphQL, No Kubernetes
- REST polling (10-15s) for vehicle location tracking
- Last-Write-Wins (LWW) for offline sync conflict resolution
- **Ponytail Plugin Always Active:** Every implementation strictly adheres to `rules.md` and chooses the simplest, shortest, most minimal working solution (YAGNI).

---

## 6. Currently Working On

> Phase 2 verified and COMPLETE (16/16 total backend tests passing).
> Next up: Phase 3 — Candidate Routes & Risk-Aware Route Optimization (`apps/routes/services/routing/`, NetworkX graph routing, route candidate feature generation, AI-03 route ranker wrapper).

---

## 7. Immediate Next Steps (Phase 3 Checklist)

- [ ] NetworkX graph loader from `Infrastructure` database segments
- [ ] Candidate route generator (`routing/base.py`, `mock.py`, `factory.py`)
- [ ] Risk-penalized edge weights & pathfinding (shortest distance vs safest risk-aware route)
- [ ] Ephemeral `RouteCandidate` dataclass/serializer (not a DB model)
- [ ] AI-03 Route Ranking service wrapper (`intelligence/services/route_ranking.py`)
- [ ] Endpoint: `POST /api/v1/routes/calculate/`
- [ ] Phase 3 unit & integration tests
- [ ] Verify full test suite and update `memory.md`

---

## 8. Test Execution History

| Date | Scope | Tests Run | Result | Notes |
|---|---|---|---|---|
| 2026-09-04 | Phase 0 (Accounts & Health) | 4 | 4 passed | JWT auth, roles, error envelope |
| 2026-09-05 | Phase 1 (Reports & Photo Analysis) | 5 | 5 passed | Photo upload, PointField, AI stub, scoping, permissions |
| 2026-09-05 | Phase 2 (Road Network & Risk) | 7 | 7 passed | Districts, Infrastructure, Risk Engine, Proximity query, Snap integration |
| 2026-09-05 | Full Suite (Phases 0–2) | 16 | 16 passed | 100% pass across accounts, reports, and routes |
