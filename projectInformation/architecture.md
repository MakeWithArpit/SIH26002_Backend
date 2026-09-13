# SIH26002 Backend Architecture

## 1. Purpose

This document defines the implementation architecture for the SIH26002
backend based on the Backend PRD v2.

The backend will be a **single modular Django monolith**, not a
microservice architecture. The design prioritizes hackathon delivery
speed, clear separation of responsibilities, testability, and
straightforward integration with the frontend and AI/ML package.

The PRD explicitly defines Django + Django REST Framework, PostgreSQL +
PostGIS, GeoDjango, Celery + Redis, in-process Python AI/ML integration,
REST-based mobile location tracking, periodic weather ingestion, local
media storage, and Django i18n. The backend therefore follows those
choices rather than introducing unnecessary infrastructure.

------------------------------------------------------------------------

## 2. Architecture Decision

### 2.1 High-level architecture

``` text
                    ┌──────────────────────────┐
                    │       Web Frontend       │
                    └────────────┬─────────────┘
                                 │ REST / JSON
                    ┌────────────▼─────────────┐
                    │     Django REST API      │
                    │   Authentication/JWT     │
                    └────────────┬─────────────┘
                                 │
             ┌───────────────────┼───────────────────┐
             │                   │                   │
      ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐
      │ Domain Apps │     │ Intelligence│     │ Aggregation │
      │ accounts    │     │ AI/ML pkg   │     │ dashboard   │
      │ routes      │     │ in-process   │     │ APIs        │
      │ vehicles    │     └──────┬──────┘     └─────────────┘
      │ alerts      │            │
      │ reports     │            │ model inputs/outputs
      │ sync        │            │
      └──────┬──────┘            │
             │                   │
             └──────────┬────────┘
                        │
                ┌───────▼────────┐
                │ PostgreSQL      │
                │ + PostGIS       │
                └─────────────────┘

          Background processing
                ┌──────────────────────┐
                │ Celery Workers       │
                │ Celery Beat          │
                │        │             │
                │        ▼             │
                │      Redis           │
                └──────────────────────┘

 External systems:
   Mobile App ──REST──> Django API
   Mobile App ──SDK──> ImageKit.io CDN (photo upload; backend stores URL only)
   Weather API ──Celery──> Django
   AI/ML package <──service calls──> Django
   photo_analysis.py (Phase 5) ──HTTP GET──> ImageKit CDN URL
```

### 2.2 Architectural style

Use:

-   **Modular monolith**
-   **REST API**
-   **Domain-oriented Django apps**
-   **Service layer for business logic**
-   **Repository/query helpers only where query complexity justifies
    them**
-   **PostgreSQL + PostGIS for persistence and spatial queries**
-   **Celery + Redis for asynchronous/scheduled work**
-   **In-process AI/ML package**
-   **JWT authentication**
-   **Role-based permissions**
-   **Versioned API: `/api/v1/`**

Do **not** introduce:

-   Microservices
-   Kubernetes
-   Django Channels/WebSockets
-   Separate AI service
-   MQTT
-   Dedicated GPS hardware
-   S3/object storage (replaced by ImageKit.io CDN — mobile uploads direct, backend stores URL)
-   Complex event buses
-   GraphQL

These are unnecessary for the stated MVP scope.

------------------------------------------------------------------------

# 3. Technology Stack

  -----------------------------------------------------------------------
  Layer                               Decision
  ----------------------------------- -----------------------------------
  Language                            Python 3.12+

  Web framework                       Django

  API                                 Django REST Framework

  Authentication                      JWT using
                                      `djangorestframework-simplejwt`

  Database                            PostgreSQL

  Spatial database                    PostGIS

  Spatial ORM                         GeoDjango

  Background jobs                     Celery

  Scheduler                           Celery Beat

  Broker / cache                      Redis

  AI/ML                               In-process Python package,
                                      scikit-learn

  Routing                             Backend graph logic initially;
                                      routing provider/OSRM behind an
                                      adapter

  Weather                             Public weather API behind a
                                      service/adapter

  Media                               ImageKit.io CDN — mobile app uploads
                                      photos directly via ImageKit SDK;
                                      backend stores only the CDN URL
                                      (`photo_url` URLField). No local
                                      media/ volume required.

  i18n                                Django translation framework

  API documentation                   OpenAPI/Swagger via
                                      `drf-spectacular`

  Testing                             pytest + pytest-django

  Code quality                        Ruff + Black

  Environment config                  `.env`

  Containerization                    Docker + Docker Compose

  Production app server               Gunicorn

  Reverse proxy                       Nginx

  Version control                     Git + GitHub
  -----------------------------------------------------------------------

### Routing decision

The PRD leaves the final routing provider open between self-hosted OSRM
and a third-party Directions API.

Therefore, **do not couple the domain logic directly to either
provider**.

Create:

``` text
routes/
    services/
        routing/
            base.py
            osrm.py
            mock.py
            factory.py
```

The application should depend on a routing interface.
- `base.py`: Routing provider interface.
- `osrm.py`: Real OSRM / external directions API adapter.
- `mock.py`: NetworkX / pre-computed fallback graph for North-Eastern corridors (ensures demo never breaks if OSRM container fails).
- `factory.py`: Instantiates active provider based on `ROUTING_PROVIDER` env variable.

------------------------------------------------------------------------

# 4. Project Structure

Recommended repository:

``` text
backend/
│
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
│
├── config/
│   ├── __init__.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py
│   │
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── development.py
│       └── production.py
│
├── apps/
│   ├── accounts/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── permissions.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   └── tests/
│   │
│   ├── routes/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── permissions.py
│   │   ├── selectors.py
│   │   ├── services/
│   │   │   ├── candidate_routes.py
│   │   │   ├── accessibility.py
│   │   │   └── routing/
│   │   │       ├── base.py
│   │   │       ├── osrm.py
│   │   │       ├── mock.py
│   │   │       └── factory.py
│   │   └── tests/
│   │
│   ├── intelligence/
│   │   ├── apps.py
│   │   ├── serializers.py
│   │   ├── services/
│   │   │   ├── photo_analysis.py
│   │   │   ├── risk.py
│   │   │   ├── eta.py
│   │   │   ├── route_ranking.py
│   │   │   ├── accessibility.py
│   │   │   └── alerts.py
│   │   └── tests/
│   │
│   ├── vehicles/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── permissions.py
│   │   ├── selectors.py
│   │   └── tests/
│   │
│   ├── alerts/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── tasks.py
│   │   ├── services.py
│   │   └── tests/
│   │
│   ├── reports/
│   │   ├── migrations/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── permissions.py
│   │   └── tests/
│   │
│   ├── sync/
│   │   ├── apps.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── services.py
│   │   └── tests/
│   │
│   ├── dashboard/
│   │   ├── apps.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── selectors.py
│   │   └── tests/
│   │
│   └── common/
│       ├── exceptions.py
│       ├── pagination.py
│       ├── permissions.py
│       ├── responses.py
│       ├── validators.py
│       └── utils.py
│
├── ml/
│   ├── models/
│   ├── artifacts/
│   ├── preprocessing/
│   ├── photo_analyzer.py
│   ├── risk_classifier.py
│   ├── eta_regressor.py
│   ├── route_ranker.py
│   └── __init__.py
│
├── scripts/
│   ├── seed_data.py
│   ├── import_districts.py
│   └── import_infrastructure.py
│
├── media/
├── static/
├── tests/
│   └── integration/
│
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pytest.ini
└── README.md
```

------------------------------------------------------------------------

# 5. Django App Responsibilities

## `accounts`

Responsible for:

-   Authentication
-   JWT login/refresh
-   User profile
-   Role management
-   Role-based permissions

Roles:

``` text
admin
field_officer
normal_user
```

The Django `User` remains the authentication identity. `Profile` stores
the role and phone information as defined by the PRD.

------------------------------------------------------------------------

## `routes`

This is the core GIS domain.

Responsible for:

-   `District`
-   `Infrastructure`
-   Accessibility status
-   Infrastructure condition/risk
-   Spatial queries
-   Candidate route generation
-   Route response construction

The route-generation pipeline:

``` text
Origin + Destination
        │
        ▼
Routing Provider / Graph
        │
        ▼
2–3 Candidate Routes
        │
        ▼
Collect route features
        │
        ├── distance
        ├── base ETA
        ├── traffic
        ├── infrastructure risk
        └── accessibility
        │
        ▼
AI Route Ranker
        │
        ▼
Ranked RouteCandidate response
```

`RouteCandidate` is **not a database model**.

------------------------------------------------------------------------

## `vehicles`

Responsible for:

-   Vehicle CRUD
-   Driver-associated vehicle
-   Location ping ingestion
-   Latest vehicle location
-   Location history

The mobile app sends:

``` json
{
  "vehicle_id": "AS01AB1234",
  "lat": 26.1445,
  "lng": 91.7362,
  "speed": 32.5,
  "timestamp": "2026-09-03T15:30:00Z"
}
```

The backend stores the record as `LocationPing`.

No MQTT or GPS hardware is required.

------------------------------------------------------------------------

## `alerts`

Responsible for:

-   Alert generation
-   Alert persistence
-   Alert resolution
-   Severity
-   Rule-based triggers
-   AI-derived alert inputs

Celery periodically evaluates:

``` text
Infrastructure status
WeatherSnapshot
Trip status
Predicted ETA
Risk score
Disruption probability
Incident reports
```

and creates/updates `Alert` records when conditions are met.

------------------------------------------------------------------------

## `reports`

Responsible for:

-   Field Officer incident reports
-   Geo-tagging
-   Photo upload
-   Incident classification
-   Severity
-   Offline-created report timestamps

Important rule:

**Field Officers do not directly modify Infrastructure.**

Instead:

``` text
Field Officer
     │
     ▼
IncidentReport
     │
     ▼
Validation / Review
     │
     ├── System intelligence
     │
     └── Admin
           │
           ▼
     Infrastructure update
```

This follows the PRD's data-integrity rule.

------------------------------------------------------------------------

## `sync`

Responsible only for offline synchronization.

The mobile app caches:

-   Location pings
-   Incident reports

When online:

``` text
Mobile Local DB
      │
      ▼
POST /api/v1/sync/batch/
      │
      ▼
Validate batch
      │
      ▼
Deduplicate
      │
      ▼
Order by client_timestamp
      │
      ▼
Insert
      │
      ▼
Return sync result
```

Conflict strategy:

**Last-write-wins by `client_timestamp`.**

Do not build a complicated synchronization engine for the MVP.

------------------------------------------------------------------------

## `dashboard`

Read-only aggregation layer.

It should provide APIs for:

-   District accessibility
-   Connectivity
-   Infrastructure bottlenecks
-   Active alerts
-   Vehicle live status
-   Trip status
-   Risk summaries
-   Weather summaries

Do not create redundant dashboard database models unless profiling
proves they are required.

------------------------------------------------------------------------

# 6. Database Architecture

Use:

``` text
PostgreSQL
    +
PostGIS
```

The nine PRD models are:

``` text
User
  │
  └── Profile

District
  │
  └── Infrastructure

Vehicle
  │
  ├── LocationPing
  └── Trip

Infrastructure ─────┐
                    ├── Alert
Trip ───────────────┘

User
  │
  └── IncidentReport

District
  │
  └── WeatherSnapshot
```

### IncidentReport and Infrastructure Spatial Linkage

`IncidentReport` captures field intelligence with a Point location. Because Field Officers cannot directly edit `Infrastructure`, the linkage is resolved via spatial proximity or optional reference:
1. **Spatial Proximity Query**: When an `IncidentReport` is submitted, PostGIS finds intersecting or nearby infrastructure:
   ```python
   # Within 50 meters buffer of the reported point
   nearby_infra = Infrastructure.objects.filter(
       geom__dwithin=(report.geom, D(m=50))
   ).first()
   ```
2. **AI & Validation Confirmation**: The report's AI result (`issue_type`, `severity`, `confidence`) validates or escalates the operational risk of the matched `Infrastructure`.
3. **Model fields**: `IncidentReport` includes AI output fields (`ai_issue_type`, `ai_severity`, `ai_confidence`) and an optional `infrastructure = ForeignKey(Infrastructure, null=True, blank=True)`.

### Vehicle Optimization for Tracking

To avoid expensive full-table scans of `LocationPing` on every 10–15s dashboard/app poll:
- `Vehicle` caches: `current_lat`, `current_lng`, and `last_ping_time`.
- Ingesting a `LocationPing` creates the history record and updates the `Vehicle` fields in a single atomic transaction.

### Spatial fields

Use GeoDjango fields:

``` python
District.geom
    -> PolygonField

Infrastructure.geom
    -> LineStringField

IncidentReport.geom
    -> PointField
```

For `Trip.origin` and `Trip.destination`, use spatial `PointField`
internally while preserving human-readable location information if
required by the frontend contract.

------------------------------------------------------------------------

# 7. Request Flow

## 7.1 Normal API request

``` text
Client
  │
  ▼
Nginx
  │
  ▼
Gunicorn
  │
  ▼
Django URL Router
  │
  ▼
DRF View
  │
  ├── Authentication
  ├── Permission
  ├── Validation
  │
  ▼
Serializer
  │
  ▼
Service Layer
  │
  ▼
Django ORM / PostGIS
  │
  ▼
Serializer
  │
  ▼
JSON Response
```

Views should remain thin.

Avoid putting complex business logic directly inside `views.py`.

------------------------------------------------------------------------

# 8. Service Layer Rule

Use this rule:

``` text
View
 ↓
Serializer validation
 ↓
Service
 ↓
Model / Query
```

Example:

``` python
# views.py

def create_trip(...):
    validated_data = serializer.validated_data
    trip = trip_service.create_trip(
        user=request.user,
        data=validated_data,
    )
```

Business logic belongs in services.

Examples:

``` text
routes/services/candidate_routes.py
routes/services/accessibility.py
intelligence/services/risk.py
intelligence/services/eta.py
intelligence/services/route_ranking.py
alerts/services.py
sync/services.py
```

Do not create services merely to wrap a single ORM `.get()` call.

------------------------------------------------------------------------

# 9. AI/ML Architecture

The AI layer is **in-process**.

``` text
Django
  │
  ▼
intelligence/services/
  │
  ├── risk.py
  ├── eta.py
  ├── route_ranking.py
  └── accessibility.py
          │
          ▼
       ml/
          │
          ├── risk_classifier
          ├── eta_regressor
          └── route_ranker
```

### AI-01: Risk prediction

Inputs include:

-   Infrastructure condition
-   Weather
-   Incident data
-   Existing operational features

Output:

``` text
disruption_probability
risk_score
risk_level
top_factors
```

### AI-02: ETA / delay prediction

Inputs include:

-   Location pings
-   Speed
-   Trip information
-   Route information

Output:

``` text
predicted_eta
expected_delay
```

### AI-03: Route ranking

Input:

``` text
RouteCandidate[]
```

Output:

``` text
ranked RouteCandidate[]
recommended = true/false
explanation
```

### AI-04: Accessibility intelligence

Reads/writes district accessibility fields.

### AI-06: Alert intelligence

Combines AI outputs with deterministic rules.

------------------------------------------------------------------------

# 10. Background Task Architecture

Use Celery for work that does not need to block an API request.

``` text
                    ┌───────────────┐
                    │ Django API    │
                    └───────┬───────┘
                            │
                       enqueue task
                            │
                            ▼
                         Redis
                            │
                            ▼
                    ┌───────────────┐
                    │ Celery Worker │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         Weather Pull   Risk Update   Alert Check
```

Celery Beat schedules:

-   Weather API pulls
-   Alert condition checks
-   Periodic AI recalculation where necessary
-   Other periodic maintenance tasks

Do not run long-running work inside normal HTTP request handlers.

------------------------------------------------------------------------

# 11. Weather Data Flow

``` text
Celery Beat
    │
    ▼
Weather Task
    │
    ▼
Public Weather API
    │
    ▼
Validate / normalize response
    │
    ▼
WeatherSnapshot
    │
    ├──────────────► Risk service
    │
    └──────────────► Alert service
```

The actual weather provider remains configurable because the PRD lists
it as an open item.

------------------------------------------------------------------------

# 12. Vehicle Tracking Flow

``` text
Driver Mobile App
      │
      │ every few seconds
      ▼
POST /api/v1/vehicles/{vehicle_id}/locations/
      │
      ▼
JWT Authentication
      │
      ▼
Permission: owner of vehicle
      │
      ▼
Validate lat/lng/speed/timestamp
      │
      ▼
LocationPing
      │
      ▼
PostgreSQL/PostGIS
```

Latest location:

``` text
GET /api/v1/vehicles/{vehicle_id}/location/latest/
```

The frontend can poll this endpoint at approximately 10--15 second
intervals for MVP real-time behavior.

No WebSocket infrastructure is required.

------------------------------------------------------------------------

# 13. Offline Sync Flow

## Client payload

For offline incident reports, photos are transferred using base64 encoded strings within the JSON payload, or via direct multipart sync:

``` json
{
  "records": [
    {
      "type": "location_ping",
      "client_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "client_timestamp": "2026-09-03T10:00:00Z",
      "data": {
        "vehicle_id": "AS01AB1234",
        "lat": 26.1445,
        "lng": 91.7362,
        "speed": 35.0
      }
    },
    {
      "type": "incident_report",
      "client_id": "5f3a9e22-8d7b-4a11-8a99-9c2b4d5e6f7a",
      "client_timestamp": "2026-09-03T10:02:00Z",
      "data": {
        "lat": 26.1550,
        "lng": 91.7480,
        "description": "Flash flood washing over bridge approach",
        "incident_type": "flood",
        "severity": "high",
        "photo_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
      }
    }
  ]
}
```

## Server flow

``` text
Receive batch
    │
    ▼
Authenticate
    │
    ▼
Validate every record
    │
    ▼
Sort by client_timestamp
    │
    ▼
Check duplicate client_id
    │
    ├── exists → skip/update according to LWW
    │
    └── new    → insert
    │
    ▼
Return per-record sync status
```

The sync endpoint should be idempotent.

------------------------------------------------------------------------

# 14. API Structure

Base URL:

``` text
/api/v1/
```

Suggested endpoint groups:

``` text
/api/v1/auth/
/api/v1/users/

/api/v1/districts/
/api/v1/infrastructure/
/api/v1/routes/

/api/v1/vehicles/
/api/v1/vehicles/{id}/locations/
/api/v1/trips/

/api/v1/alerts/

/api/v1/reports/

/api/v1/sync/

/api/v1/dashboard/

/api/v1/weather/
```

### Example route API

``` text
POST /api/v1/routes/calculate/
```

Request:

``` json
{
  "origin": {
    "lat": 26.1445,
    "lng": 91.7362
  },
  "destination": {
    "lat": 27.4728,
    "lng": 94.9120
  }
}
```

Response:

``` json
{
  "routes": [
    {
      "route_id": "route-1",
      "distance_km": 381.4,
      "base_eta": 510,
      "traffic_level": "moderate",
      "risk_level": "low",
      "accessibility_score": 8.4,
      "recommended": true,
      "polyline": "...",
      "legs": [],
      "explanation": "Lower infrastructure risk and better accessibility."
    }
  ]
}
```

------------------------------------------------------------------------

# 15. Authentication and Authorization

Use JWT.

Flow:

``` text
POST /auth/login/
        │
        ▼
access token + refresh token
        │
        ▼
Authorization: Bearer <access>
```

Permissions must be enforced server-side.

Never rely on the frontend to hide unauthorized functionality.

### Role rules

``` text
ADMIN
  - Full administrative access
  - Infrastructure management
  - Fleet monitoring
  - Trip override
  - Alert management
  - Incident review

FIELD_OFFICER
  - Own profile
  - Read districts/infrastructure
  - Create/read own incident reports
  - Read alerts/weather
  - No direct infrastructure editing

NORMAL_USER
  - Own profile
  - Own vehicle/trips
  - Own location pings
  - Route consumption
  - Alerts/weather
  - No incident reporting in MVP
```

These rules must be implemented using DRF permission classes and
queryset filtering.

------------------------------------------------------------------------

# 16. Error Handling

Use a consistent API error format:

``` json
{
  "success": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Invalid coordinates.",
    "details": {}
  }
}
```

Common error codes:

``` text
AUTHENTICATION_REQUIRED
PERMISSION_DENIED
INVALID_REQUEST
RESOURCE_NOT_FOUND
DUPLICATE_RECORD
SYNC_CONFLICT
ROUTING_ERROR
EXTERNAL_SERVICE_ERROR
INTERNAL_ERROR
```

Do not expose Python stack traces or internal database errors to
clients.

------------------------------------------------------------------------

# 17. Data Validation

Validation belongs at multiple levels:

### Serializer level

-   Required fields
-   Type validation
-   Enum validation
-   Basic coordinate validation

### Service level

-   Ownership
-   State transitions
-   Cross-model business rules

### Database level

-   Unique constraints
-   Foreign keys
-   Check constraints where practical

Example:

``` text
Vehicle.registration_no → UNIQUE
```

Coordinates must be validated before inserting spatial data.

------------------------------------------------------------------------

# 18. Trip State Machine

Trip status:

``` text
on_route
delayed
at_risk
delivered
```

Recommended transition logic:

``` text
created
   │
   ▼
on_route
   │
   ├── delay detected ──► delayed
   │
   ├── risk threshold ──► at_risk
   │
   └── delivery complete ► delivered
```

Do not allow arbitrary status changes from the frontend.

The service layer should validate state transitions.

------------------------------------------------------------------------

# 19. Infrastructure State Logic

Infrastructure status:

``` text
accessible
blocked
risky
```

Condition:

``` text
good
moderate
poor
damaged
```

Risk:

``` text
risk_score
disruption_probability
risk_level
top_factors
```

A Field Officer report should not directly mutate these values.

Instead:

``` text
IncidentReport
      │
      ▼
AI / validation
      │
      ▼
Admin/system decision
      │
      ▼
Infrastructure update
```

------------------------------------------------------------------------

# 20. Performance Strategy

For the hackathon MVP:

1.  Use PostgreSQL indexes on frequently filtered fields.
2.  Add PostGIS spatial indexes to geometry fields.
3.  Use `select_related()` / `prefetch_related()` where needed.
4.  Avoid N+1 queries.
5.  Paginate large vehicle/location/alert lists.
6.  Cache only expensive, frequently reused data.
7.  Keep dashboard endpoints aggregation-oriented.
8.  Move external API calls to Celery where possible.
9.  Do not prematurely introduce distributed infrastructure.

Potential indexes:

``` text
LocationPing(vehicle, timestamp)
Trip(vehicle, status)
Alert(severity, resolved, created_at)
Infrastructure(district, status, risk_level)
WeatherSnapshot(district, recorded_at)
IncidentReport(officer, client_timestamp)
```

------------------------------------------------------------------------

# 21. Testing Architecture

Use:

``` text
pytest
pytest-django
```

Testing layers:

``` text
Unit tests
   │
   ├── services
   ├── validators
   ├── AI adapters
   └── permission logic

API tests
   │
   ├── authentication
   ├── authorization
   ├── serializers
   └── endpoint behavior

Integration tests
   │
   ├── PostgreSQL/PostGIS
   ├── Celery tasks
   ├── routing integration
   └── weather integration
```

Critical flows that must have tests:

-   JWT authentication
-   Role permissions
-   Vehicle location ownership
-   Route candidate generation
-   AI route ranking integration
-   Incident report creation
-   Offline batch sync
-   Duplicate sync records
-   Alert creation
-   Infrastructure protection from Field Officers

------------------------------------------------------------------------

# 22. Environment Configuration

Use environment variables.

Example:

``` env
DEBUG=False

SECRET_KEY=...
ALLOWED_HOSTS=...

DATABASE_URL=postgresql://...
REDIS_URL=redis://...

JWT_ACCESS_MINUTES=30
JWT_REFRESH_DAYS=7

WEATHER_API_URL=...
WEATHER_API_KEY=...

ROUTING_PROVIDER=osrm
OSRM_BASE_URL=...

MEDIA_ROOT=/app/media
```

Never commit:

``` text
.env
API keys
JWT secrets
database passwords
production credentials
```

Commit only:

``` text
.env.example
```

------------------------------------------------------------------------

# 23. Docker Architecture

For development:

``` text
docker-compose
│
├── django
├── postgres-postgis
├── redis
└── celery-worker
```

Optional:

``` text
celery-beat
```

Production:

``` text
Internet
   │
   ▼
Nginx
   │
   ▼
Gunicorn
   │
   ▼
Django
   │
   ├── PostgreSQL/PostGIS
   ├── Redis
   └── Celery
```

For the hackathon demo, this is sufficient. Kubernetes is not justified.

------------------------------------------------------------------------

# 24. Development Workflow

Recommended branch strategy:

``` text
main
  │
  ├── develop
  │
  ├── feature/auth
  ├── feature/routes
  ├── feature/vehicles
  ├── feature/alerts
  ├── feature/reports
  ├── feature/offline-sync
  └── feature/dashboard
```

Before merging:

``` text
ruff check .
black --check .
pytest
python manage.py check
python manage.py makemigrations --check
```

------------------------------------------------------------------------

# 25. Implementation Order

To ensure the team delivers the winning hackathon demonstration first, the implementation directly follows the phased dependency pipeline from `phases.md`:

### Phase 0 — Backend Foundation
- Django project & DRF setup
- PostgreSQL / PostGIS configuration
- JWT authentication (`djangorestframework-simplejwt`)
- Roles (`Admin`, `Field Officer`, `Normal User`)
- Common API response / error structure
- Media upload configuration

### Phase 1 — Field Intelligence & Photo Analysis (P0)
- `reports` app & `IncidentReport` model
- Photo upload handling + PostGIS `PointField`
- `intelligence/services/photo_analysis.py` (AI-08 wrapper)
- Structured AI analysis persistence (`issue_type`, `severity`, `confidence`)

### Phase 2 — Infrastructure + Risk Intelligence (P0)
- `routes` app with `District` and `Infrastructure` models
- Spatial proximity lookup (linking reports to roads/bridges)
- `intelligence/services/risk.py` (AI-01 risk wrapper)
- Seeded/configurable weather input

### Phase 3 — Candidate Routes + Optimization (P0)
- Candidate route generation (`routing/base.py`, `mock.py`, `osrm.py`)
- Route feature aggregation (distance, risk, condition)
- `intelligence/services/route_ranking.py` (AI-03 wrapper)
- Computed `RouteCandidate` serialization

### Phase 4 — ETA Estimation (P0)
- `vehicles` app with `Vehicle`, `Trip`, `LocationPing` models
- `intelligence/services/eta.py` (AI-02 ETA wrapper)
- Base ETA vs predicted ETA & delay output

### Phase 5 — End-to-End Intelligence Pipeline (P0 Hackathon Milestone)
- Connect Phases 1–4 into an immediate, demonstrable workflow:
  `Photo Upload → AI Detection → Risk Recalculation → Route Recommendation Switch → ETA Update`
- Verification with mock/demo scenarios for the jury

### Phase 6 — Weather Intelligence (P1)
- `WeatherSnapshot` persistence & public weather API adapter
- Celery periodic task ingestion

### Phase 7 — Vehicle Tracking (P1)
- Driver location ping endpoint
- O(1) `latest_location` retrieval via cached `Vehicle` fields
- Location history queries

### Phase 8 — Alerts & Automated Intelligence (P1)
- `Alert` model & rule triggers
- Automated alert generation on risk threshold or ETA delay
- Multilingual notification template support (`Accept-Language` / i18n)

### Phase 9 — Offline Sync (P1/P2)
- Batch sync endpoint (`/api/v1/sync/batch/`)
- Client ID deduplication & Last-Write-Wins ordering
- Base64 offline photo processing

### Phase 10 — Accessibility Intelligence (P2)
- Dynamic AI-04 scoring integration
- District-level accessibility breakdown

### Phase 11 — Dashboard APIs (P2)
- Read-only aggregation views (district summaries, active bottlenecks)

### Phase 12 — Production Hardening (P2)
- Test suite (`pytest`), API documentation (`drf-spectacular`), seed scripts, Docker Compose

------------------------------------------------------------------------

# 26. Logging and Observability

For the MVP:

``` text
Django application logs
Celery logs
Nginx access/error logs
```

Log:

-   Request method/path
-   Status code
-   Request ID
-   User ID where appropriate
-   Celery task failures
-   External API failures
-   Sync failures
-   AI inference failures

Do not log:

-   Passwords
-   JWT tokens
-   API secrets
-   Sensitive personal data unnecessarily

------------------------------------------------------------------------

# 27. Security Baseline

Minimum requirements:

-   HTTPS in production
-   JWT authentication
-   Secure secret management
-   CORS restricted to known frontend origins
-   CSRF protection where applicable
-   DRF permission classes
-   File upload validation
-   Request size limits
-   Input validation
-   Database constraints
-   Secure Django settings
-   No debug mode in production

For incident photos:

-   Validate MIME type
-   Validate file extension
-   Limit upload size
-   Generate safe filenames
-   Do not trust the client-provided filename

------------------------------------------------------------------------

# 28. Architecture Principles

The backend team should follow these rules:

### Rule 1 --- Keep it modular, not distributed

One Django project is enough.

### Rule 2 --- Views stay thin

Business logic belongs in services.

### Rule 3 --- AI stays behind an interface

The API should not know whether the model is Random Forest, another
scikit-learn estimator, or a future implementation.

### Rule 4 --- Database is the source of truth

AI predictions can update operational fields, but API responses should
be based on persisted domain state where appropriate.

### Rule 5 --- Offline sync must be idempotent

Repeated sync requests must not create duplicate records.

### Rule 6 --- Field reports protect infrastructure integrity

Field Officers report; they do not directly edit infrastructure.

### Rule 7 --- REST polling is enough for MVP

Do not waste hackathon time implementing WebSockets.

### Rule 8 --- External integrations use adapters

Weather and routing providers must be replaceable.

### Rule 9 --- Avoid speculative abstractions

Do not build repositories, event buses, generic CRUD frameworks, or
microservices unless a real requirement appears.

### Rule 10 --- Build for the demo first, but do not create dead-end architecture

The MVP should remain simple without making future replacement of
routing, weather, storage, or AI impossible.

------------------------------------------------------------------------

# 29. Final Architecture Decision

``` text
                    SIH26002 BACKEND
                         │
              ┌──────────▼──────────┐
              │ Django + DRF        │
              │ Modular Monolith    │
              └──────────┬──────────┘
                         │
       ┌─────────────────┼──────────────────┐
       │                 │                  │
   Domain Apps       Intelligence       Dashboard
       │                 │                  │
       │                 ▼                  │
       │              scikit-learn         │
       │                 │                  │
       └─────────────────┼──────────────────┘
                         │
                  PostgreSQL/PostGIS
                         │
              ┌──────────┴──────────┐
              │                     │
            Redis               Geo queries
              │
          Celery/Beat
              │
      ┌───────┴────────┐
      │                │
 Weather Pull      Alert Engine

Clients:
  Web Frontend ──REST──> API
  Mobile App ───REST──> API
```

### Final stack

``` text
Python
Django
Django REST Framework
PostgreSQL
PostGIS
GeoDjango
Celery
Redis
scikit-learn
JWT
Docker
Gunicorn
Nginx
pytest
drf-spectacular
Ruff
Black
```

This architecture is intentionally conservative. The PRD is a hackathon
MVP, so adding microservices, WebSockets, Kubernetes, MQTT, a separate
AI server, or a complicated event-driven architecture would increase
implementation and debugging cost without solving a stated MVP
requirement.
