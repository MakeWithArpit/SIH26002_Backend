# SIH26002 — Backend Development Rules & Guidelines

This document defines the strict development standards, library whitelist, architectural boundaries, and error handling patterns for the **SIH26002 Backend** (Smart India Hackathon 2026).

---

## 1. Core Principles (Ponytail Philosophy)

1. **Modular Monolith Over Microservices:** Build a single, well-structured Django project. Never break the MVP into microservices or separate AI services.
2. **Hackathon Demo First:** Prioritize the P0 Core Intelligence Pipeline:
   $$\text{Photo Analysis} \rightarrow \text{Risk Calculation} \rightarrow \text{Route Re-ranking} \rightarrow \text{ETA Prediction}$$
3. **YAGNI (You Aren't Gonna Need It):** No speculative abstractions. No generic repository layers, event buses, or hand-rolled caching frameworks.
4. **Fewest Files & Shortest Working Diff:** Use standard Django patterns and Python standard library before writing custom scaffolding.
5. **Always Use Ponytail Plugin & Strict Adherence to Rules:** The `ponytail` plugin must always remain active across all design, code, review, and test decisions. Every solution must be the simplest, shortest, and most minimal that actually works. All code and workflows must strictly adhere to `rules.md` without exception.

---

## 2. Library Whitelist & Tech Stack

Only install dependencies from this whitelist. Adding unapproved libraries requires explicit discussion.

### ✅ Allowed Dependencies

| Layer | Approved Library | Purpose |
|---|---|---|
| **Web Framework** | `django` (>= 5.0) | Core web framework |
| **REST API** | `djangorestframework` | Serializers, API views, viewsets |
| **Authentication** | `djangorestframework-simplejwt` | JWT access/refresh tokens |
| **CORS** | `django-cors-headers` | Cross-origin requests for web/mobile |
| **Database & GIS** | `psycopg2-binary` or `psycopg[binary]`, `GeoDjango` | PostgreSQL + PostGIS integration |
| **Task Queue & Cache** | `celery`, `redis`, `django-celery-beat` | Asynchronous jobs and periodic tasks |
| **In-Process AI/ML** | `scikit-learn`, `numpy`, `pandas`, `joblib` | Risk, ETA, route-ranking models |
| **Image / Media** | `Pillow` | Photo upload validation & processing |
| **Routing & Network** | `osmnx`, `networkx`, `requests` (for OSRM) | Road network graph extraction & pathfinding |
| **API Docs** | `drf-spectacular` | OpenAPI 3.0 / Swagger generation |
| **Testing & Quality** | `pytest`, `pytest-django`, `ruff`, `black` | Unit/API tests, formatting, linting |

### ❌ Strictly Forbidden / Out of Scope (Do NOT Use)

- **No WebSockets / Django Channels:** Use REST polling (10–15 second interval) for location tracking.
- **No Separate AI Microservices:** AI runs **in-process** via Python packages.
- **No Kubernetes / Swarm:** Run locally or via basic Docker Compose.
- **No MQTT / IoT Protocols:** Location pings come directly from the mobile app via REST.
- **No S3 / Cloud Storage:** Local media storage (`MEDIA_ROOT`) is mandatory for the hackathon MVP.
- **No GraphQL:** Stick strictly to standard REST endpoints (`/api/v1/`).

---

## 3. Architecture & Coding Boundaries

### 3.1 Views Stay Thin
- **Views only:** Authenticate, check permissions, validate request serializer, call service, return response serializer.
- **No business logic in `views.py`:** All domain operations belong in `apps/<domain>/services/` or `intelligence/services/`.

### 3.2 In-Process AI & Replaceable Service Interfaces
- **Rule-Based First, ML Drop-in Later:** For the MVP, risk scoring and ETA use explainable, rule-based algorithms (e.g. weighted hazard scoring, road-class speeds) so backend progress is never blocked by ML training datasets.
- **Stable Service Contracts:** All predictive capabilities live behind stable service classes (`RiskPredictionService`, `RouteOptimizationService`, `ETAEstimationService`, `ImageAnalysisService`).
- Views and serializers must **never** import ML internals or scikit-learn models directly. When trained models (Random Forest, XGBoost, CNN) are ready, they drop into the existing service wrappers with zero changes to controllers or database schemas.

### 3.3 Road Network & Field Incident Snapping
- **Selected Pilot Corridor:** Road network graphs are extracted for a bounded MVP area/corridor in the NER (e.g., Guwahati–Shillong transport corridor) rather than attempting whole-region downloads at once.
- **Infrastructure & Road Segments:** Roads and road segments are stored with PostGIS geometries (`LineStringField`).
- **Snapping Logic:** Field Officers submit `IncidentReport` (Point location + photo). The system snaps to the nearest road segment via spatial proximity:
  ```python
  nearest_segment = RoadSegment.objects.filter(
      geom__dwithin=(report.geom, D(m=100))
  ).annotate(
      distance=Distance('geom', report.geom)
  ).order_by('distance').first()
  ```
- An incident report dynamically updates or temporarily boosts the disruption risk of the snapped road segment without mutating historical base infrastructure records directly.

### 3.4 Ephemeral Route Candidates
- `RouteCandidate` is a **computed response shape**, never a database model.
- Do not create database migrations or tables for route candidates.

### 3.5 Vehicle Location Optimization
- Do not perform full-table scans on `LocationPing` for dashboard polling.
- `Vehicle` model maintains cached fields: `current_lat`, `current_lng`, and `last_ping_time`.
- Every incoming ping writes to `LocationPing` and atomically updates `Vehicle`.

### 3.6 Hackathon Synchronous Demo Trigger
- Periodic Celery Beat tasks handle routine polling (e.g. weather).
- For live presentations, submitting an `IncidentReport` must trigger an immediate recalculation pipeline:
  `Incident Upload → AI Vision → Update Infrastructure Risk → Recalculate Routes`

---

## 4. Offline Sync Boundaries

1. **Client Identity:** Every client record must supply a client-generated UUID (`client_id`) and ISO-8601 `client_timestamp`.
2. **Idempotency:** Re-submitting the same `client_id` must never create duplicate database rows.
3. **Conflict Resolution:** Strictly **Last-Write-Wins (LWW)** based on `client_timestamp`.
4. **Offline Photos:** Photos in batch JSON sync payloads must be transferred as `photo_base64` strings and decoded server-side.

---

## 5. Error Handling & API Response Standard

### 5.1 Error Response Envelope
Every failed API request must return HTTP status >= 400 with this standard JSON structure:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "User-friendly description of what failed.",
    "details": {}
  }
}
```

### 5.2 Success Response Envelope
```json
{
  "success": true,
  "data": {}
}
```

### 5.3 Standard Error Codes
- `AUTHENTICATION_REQUIRED`: Missing or invalid JWT.
- `PERMISSION_DENIED`: Role does not have access to this action.
- `INVALID_REQUEST`: Serializer validation failed or bad payload format.
- `RESOURCE_NOT_FOUND`: Target entity does not exist.
- `DUPLICATE_RECORD`: Unique constraint violation or sync conflict.
- `ROUTING_ERROR`: Waypoints unreachable or routing engine unavailable.
- `EXTERNAL_SERVICE_ERROR`: Weather or external API failed.
- `INTERNAL_ERROR`: Catch-all for unexpected server failures.

### 5.4 Safety Rule
**Never leak raw Python stack traces, SQL errors, or internal file paths to the API response.** Always catch and sanitize exceptions using custom DRF exception handling (`common/exceptions.py`).

---

## 6. Internationalization (i18n)

- Alert notification titles and recommended actions must support multilingual display (English, Hindi, Assamese, Bengali).
- API respects the standard `Accept-Language` HTTP header or a `?lang=` query parameter.
- Use Django's built-in translation utilities (`gettext`, `gettext_lazy`) for alert message templates.

---

## 7. Autonomous Git & Memory Management

### 7.1 Autonomous Git Commits
- **Do not ask the user for permission to commit.** The assistant must autonomously execute a local `git commit` whenever a logical milestone is completed and verified (e.g., new model added, service completed, tests passing, or config changes).
- Use clean Conventional Commits format (`feat(...)`, `fix(...)`, `docs(...)`, `chore(...)`, `test(...)`).
- Do not commit on mid-debug intermediate syntax failures, but immediately commit once the step is functional and tested.
- Push to remote (`git push`) at major phase checkpoints or when tests confirm full milestone completion.

### 7.2 Living Memory (`memory.md`)
- The file `.agents/memory.md` is the single source of truth for project progress, current tasks, technical environment facts, and next steps.
- The assistant must automatically update `.agents/memory.md` whenever a phase or significant milestone advances.
