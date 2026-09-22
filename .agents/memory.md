# SIH26002 Backend — Living Memory

> **Auto-maintained by the assistant.** Updated on every major milestone.  
> **Last updated:** 2026-09-22  
> **Milestone:** All Phases 0 to 12 COMPLETE & Production Ready on Render.com  

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project** | SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform (NER) |
| **Hackathon** | Smart India Hackathon (SIH) |
| **Team Split** | Arpit = Django Backend; Omji = AI/ML models (CV, Risk, Route Ranking, ETA) |
| **Repo** | `MakeWithArpit/SIH26002_Backend` (GitHub `main` branch) |
| **Backend Hosting** | Render.com (Private API service behind frontend proxy) |
| **API Base Path** | `/api/v1` |

---

## 2. Technical Environment (Production & Docker)

| Item | Value |
|---|---|
| **Production Host** | Render.com (Private API Web Service) |
| **Local Runtime** | Docker Container (`python:3.12-slim-bookworm`) via Docker Compose |
| **Python** | 3.12 |
| **Django** | 5.x / 6.x |
| **Containerization** | Docker + Docker Compose (`web`, `redis`, `celery_worker`, `celery_beat`) |
| **Database** | PostgreSQL 16 + PostGIS 3.4 (`django.contrib.gis.db.backends.postgis`) |
| **Task Queue & Cache** | Redis 7 (`redis:6379/0`), Celery 5.3+ worker & scheduler beat |
| **API Documentation** | OpenAPI 3.0 / Swagger UI (`drf-spectacular`) |
| **CDN Integration** | ImageKit.io for incident photo storage |

---

## 3. Phase Completion Status (100% Complete)

| Phase | Name | Status | Notes |
|:---:|---|:---:|---|
| **Phase 0** | Backend Foundation | COMPLETE | Django foundation, DRF, JWT Auth, PostGIS setup, standardized response envelope |
| **Phase 1** | Field Intelligence & Photo Analysis | COMPLETE | IncidentReport (PointField, photo_url ImageKit), CV model wrapper, spatial snap integration |
| **Phase 2** | Road Network Graph & Disruption Risk | COMPLETE | District & Infrastructure PostGIS models, Rule-based Risk Engine (AI-01), GSI hazard layers |
| **Phase 3** | Risk-Aware Route Optimization | COMPLETE | NetworkX graph pathfinding, dynamic risk penalties, RouteCandidate, AI-03 route ranking |
| **Phase 4** | Condition-Aware ETA Estimation | COMPLETE | Telemetry-driven speed models, weather degradation factor, ETA delay breakdown (AI-02) |
| **Phase 5** | End-to-End Pipeline Demo | COMPLETE | Atomic `POST /api/v1/routes/simulate-pipeline/` orchestrating 6 stages in 1 call |
| **Phase 6** | Weather Intelligence | COMPLETE | Open-Meteo live sync, IMD warnings parser, 7-day forecast, Celery 6-hour periodic beat |
| **Phase 7** | Vehicle Tracking | COMPLETE | Driver ownership validation, O(1) cached location lookup, GPS breadcrumb history |
| **Phase 8** | Alerts & Automated Intelligence | COMPLETE | `Alert` model, multi-severity hazard warnings, district geofencing, acknowledgement flow |
| **Phase 9** | Offline Resilient Batch Sync | COMPLETE | `POST /api/v1/sync/batch/`, `client_sync_id` idempotency, Last-Write-Wins (LWW) conflict resolution |
| **Phase 10** | Accessibility Intelligence | COMPLETE | Dynamic multi-factor scoring (Roads 40%, Risk 30%, Connectivity 20%, Weather 10%), breakdown API |
| **Phase 11** | Dashboard & Aggregation APIs | COMPLETE | 6 high-performance read-only endpoints (`/summary/`, `/districts/`, `/vehicles/`, `/alerts/active/`, etc.) |
| **Phase 12** | Production Hardening & Role Management | COMPLETE | Live Render deployment, Root status API (`GET /`), DB Health Check (`GET /health/`), automatic user role sync command |

---

## 4. User Role Management & Security Architecture

### Role-Based Access Control (RBAC)
1. **Admin (`admin`)**:
   - Access to Django Admin (`/admin/auth/user/`) with inlined `ProfileInline`.
   - Access to user role administration APIs (`GET /api/v1/accounts/users/`, `PATCH /api/v1/accounts/users/<id>/role/`).
   - Authority to trigger network-wide accessibility recomputations and role auto-synchronization.
2. **Field Officer (`field_officer`)**:
   - Authorized to submit incident reports (`POST /api/v1/reports/incidents/`) and offline batches (`POST /api/v1/sync/batch/`).
3. **Normal User / Driver (`normal_user`)**:
   - Authorized to view routes, stream telemetry, query vehicle locations, and manage trips.

### Automatic Synchronization
- Command: `python manage.py assign_user_roles`
- Mapped in `entrypoint.sh`: Runs automatically on container startup so Render database users are always in sync.

---

## 5. Key Architectural Decisions (Locked)

- **Modular Monolith**: Single Django codebase divided into focused domain apps (`accounts`, `common`, `dashboard`, `intelligence`, `reports`, `routes`, `sync`, `vehicles`).
- **Rule-Based First, ML Drop-in Later**: Explainable weighted risk and ETA algorithms with clean service contracts.
- **Ephemeral Route Candidates**: `RouteCandidate` is never saved as a database model; always computed dynamically on the fly.
- **ImageKit CDN Integration**: Mobile client uploads photos directly to ImageKit; backend stores and serves only `photo_url` strings.
- **Last-Write-Wins (LWW)**: Offline synchronization resolves concurrent updates using `client_timestamp`.
- **White-box Testing**: Dedicated test suites in each app covering all edge cases.

---

## 6. Test Suite Coverage Summary

- `apps.accounts.test_phase12_roles`: **10 / 10 passed** ✅
- `apps.dashboard.test_phase11_dashboard`: **9 / 9 passed** ✅
- `apps.routes.test_phase10_accessibility`: **10 / 10 passed** ✅
- `apps.sync.test_phase9_sync`: **8 / 8 passed** ✅
- `apps.routes.test_phase8_alerts`: **6 / 6 passed** ✅
- `apps.intelligence.tests`: **19 / 19 passed** ✅
- `apps.routes.test_weather`: **11 / 11 passed** ✅
- Overall project test status: **100% PASS**
