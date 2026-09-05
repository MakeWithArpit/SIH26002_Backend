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
| **Phase 1** | Field Intelligence & Photo Analysis | COMPLETE | IncidentReport (PointField, photo), photo analysis stub, Field Officer scoping, 5/5 tests passing (9/9 total) |
| **Phase 2** | Road Network Graph & Disruption Risk | READY | Next up |
| **Phase 3** | Risk-Aware Route Optimization | NOT STARTED | |
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

## 4. Phase 0 & Phase 1 — What Was Built

### Phase 0 — Foundation
- `manage.py`, `config/settings/base.py`, `development.py`, `production.py`
- `config/wsgi.py`, `config/asgi.py`, `config/urls.py`
- `apps/accounts/` — Custom `Profile` model, `Role` choices (admin, field_officer, normal_user), JWT login/refresh views, 4 tests passing
- `apps/common/` — Unified success/data/error API envelope (responses.py, exceptions.py), `/api/v1/health/` endpoint
- PostGIS extension enabled, GeoDjango backend configured with Windows GDAL auto-discovery
- `requirements.txt` with approved dependencies

### Phase 1 — Field Intelligence & Photo Analysis
- `apps/reports/` — `IncidentReport` model with GeoDjango `PointField(srid=4326, geography=True)`, photo uploads, AI prediction fields (`ai_issue_type`, `ai_severity`, `ai_confidence`, `analysis_status`), and `snapped_road_segment_id`
- `apps/reports/services/photo_analysis.py` — Replaceable CV service wrapper (AI-08 stub matching AI/ML team contract)
- `apps/reports/services/spatial_snap.py` — Spatial snap service stub
- `apps/reports/serializers.py` — Write (`IncidentReportCreateSerializer`) & Read (`IncidentReportSerializer`) with lat/lng conversion
- `apps/reports/views.py` — `IncidentReportViewSet` with `IsFieldOfficer` permissions, immutable reports, and officer vs admin query scoping
- `apps/reports/urls.py` — `/api/v1/reports/incidents/`
- `apps/reports/admin.py` — GeoDjango OSM admin registration
- `apps/reports/tests.py` — 5 unit/API tests (photo upload, AI execution, role permissions, officer scoping, validation error envelope)

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

> Phase 1 verified and COMPLETE (9/9 total tests passing).
> Next up: Phase 2 — Road Network Graph & Disruption Risk Intelligence (`apps/routes`, District & Infrastructure models, Rule-based Risk Engine, Pilot Corridor seed data, Report spatial snap).

---

## 7. Immediate Next Steps (Phase 2 Checklist)

- [ ] Create `apps/routes/` Django app (`District` & `Infrastructure` GeoDjango models)
- [ ] Implement `apps/routes/services/risk.py` (Rule-based Geospatial Risk Service matching AI-01 contract)
- [ ] Connect `apps/reports/services/spatial_snap.py` to snap reports to `Infrastructure` and trigger risk updates
- [ ] Pilot corridor seed command (`seed_pilot_corridor` for Guwahati–Shillong / NH-06)
- [ ] Endpoints for `/api/v1/routes/districts/` and `/api/v1/routes/infrastructure/`
- [ ] Comprehensive unit/API tests for Phase 2 (`apps/routes/tests.py`)
- [ ] Verify test suite passes and update `memory.md`

---

## 8. Test Execution History

| Date | Scope | Tests Run | Result | Notes |
|---|---|---|---|---|
| 2026-09-04 | Phase 0 (Accounts & Health) | 4 | 4 passed | JWT auth, roles, error envelope |
| 2026-09-05 | Phase 1 (Reports & Photo Analysis) | 5 | 5 passed | Photo upload, PointField, AI stub, scoping, permissions |
| 2026-09-05 | Full Suite (Phase 0 + Phase 1) | 9 | 9 passed | Complete pass across all apps |
