# SIH26002 Backend — Living Memory

> **Auto-maintained by the assistant.** Updated on every major milestone.
> Last updated: 2026-09-04

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
| **Phase 1** | Field Intelligence & Photo Analysis | NOT STARTED | Next up |
| **Phase 2** | Road Network Graph & Disruption Risk | NOT STARTED | After Phase 1 |
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

## 4. Phase 0 — What Was Built

- `manage.py`, `config/settings/base.py`, `development.py`, `production.py`
- `config/wsgi.py`, `config/asgi.py`, `config/urls.py`
- `apps/accounts/` — Custom `Profile` model, `Role` choices (admin, field_officer, normal_user), JWT login/refresh views, tests
- `apps/common/` — Unified success/data/error API envelope (responses.py, exceptions.py), `/api/v1/health/` endpoint
- PostGIS extension enabled, GeoDjango backend configured with Windows GDAL auto-discovery
- `requirements.txt` with approved dependencies

---

## 5. Key Architectural Decisions (Locked)

- Modular Monolith — no microservices
- Rule-Based First, ML Drop-in Later — Risk & ETA use configurable weighted scoring; stable service contracts allow Omji models to plug in without changing controllers or DB
- `RoadSegment` as Central Entity — Field reports spatially snap to nearest RoadSegment (PostGIS ST_DWithin); risk score lives on the segment
- `RouteCandidate` is ephemeral — never stored as DB model, always computed response
- Pilot Corridor — MVP covers bounded NER corridor (e.g., Guwahati-Shillong / NH-06)
- No WebSockets, No MQTT, No S3, No GraphQL, No Kubernetes
- REST polling (10-15s) for vehicle location tracking
- Last-Write-Wins (LWW) for offline sync conflict resolution

---

## 6. Currently Working On

> Phase 1 — Field Intelligence & Photo Analysis
> Nothing started yet. Next task: create apps/reports/ app with IncidentReport model.

---

## 7. Immediate Next Steps (Phase 1 Checklist)

- [ ] Create `apps/reports/` Django app
- [ ] `IncidentReport` model (PointField, photo, issue_type, severity, snapped_road_segment, client_id)
- [ ] `ImageAnalysisService` stub (returns mock CV result until Omji model ready)
- [ ] Field Officer permission class
- [ ] `POST /api/v1/reports/incidents/` endpoint + serializer
- [ ] Unit tests for upload, permission, and stub AI result
- [ ] Commit & push Phase 1

---

## 8. Git History (Major Commits)

| Commit | Message |
|---|---|
| `5d1a5e4` | Phase 0 complete — foundation, accounts, common app, 4 tests passing |
| `859eaed` | feat(database): enable GeoDjango PostGIS backend with Windows GDAL discovery |
| `a1a1990` | docs(rules): align rules with Omji PRD (osmnx, replaceable services, road snapping) |
