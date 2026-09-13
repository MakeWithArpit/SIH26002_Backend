# SIH26002 Backend — Implementation Phases

## 1. Purpose

This document defines the phased implementation plan for the SIH26002 backend.

The backend will not be built as one large implementation. Development is divided into phases so that the core intelligence pipeline can be demonstrated first, while the remaining platform capabilities are added later.

### Core priority

1. Shared Road Network Graph (Pilot MVP Corridor in NER)
2. Field Report Photo Analysis & Segment Snapping
3. Route Disruption Risk Prediction (Rule-based first, ML drop-in later)
4. Optimized Route Suggestion (Risk-penalized graph routing)
5. ETA Estimation (Road-type & condition calculation model)

These capabilities form one shared, connected end-to-end intelligence pipeline:

```text
Field Officer Geo-tagged Photo
      |
      v
Photo CV Analysis (Flood / Landslide / Damage)
      |
      v
PostGIS Spatial Snap to Nearest Road Segment
      |
      v
Disruption Risk Calculation (Weighted Scoring / ML)
      |
      v
Dynamic Edge Cost Adjustment in Road Graph
      |
      v
Risk-Aware Route Optimization (NetworkX)
      |
      v
Condition-Aware ETA Prediction
```

---

## 2. Phase Strategy & MVP Scope

- **Selected Pilot Corridor:** Rather than ingesting all 8 North-Eastern states, the MVP will operate on a selected key transport corridor (e.g., Guwahati–Shillong / NH-06 corridor) containing diverse topography (plains to hilly terrain) and alternative route options.
- **Shared Road Network Graph:** All intelligence (disruption risk, weather, field photos, travel times) attaches directly to road segments (`RoadSegment` in PostGIS).
- **Rule-Based First, ML Drop-in Later:** Risk prediction and ETA start with explainable, deterministic rule-based algorithms so backend development and live demos are never blocked by external ML training dependencies. Stable service wrappers enable 1-click model swapping once trained weights are delivered.

A later feature may require a small part of another domain earlier than its complete implementation.

Examples:
- ETA requires basic Trip and LocationPing data; full vehicle tracking can come later.
- Risk prediction requires weather input; complete weather ingestion can come later.
- Route ranking requires infrastructure and accessibility information; complete accessibility intelligence can come later.

This prevents unnecessary implementation while avoiding dead-end architecture.

---

# Phase 0 — Backend Foundation

**Priority: Required**

## Objective

Create the minimum Django backend foundation required by all subsequent phases.

## Scope

- Django project
- Django REST Framework
- PostgreSQL
- PostGIS / GeoDjango
- Environment configuration
- API versioning
- Basic authentication
- Basic role handling
- Common API response/error structure
- Media configuration for image uploads
- Basic project configuration
- Git/development conventions

## Roles

The PRD defines:
- Admin
- Field Officer
- Normal User

For the first demo, Field Officer and the minimum required authentication/authorization should be prioritized.

## Completion Criteria

The backend should:
- start successfully
- connect to PostgreSQL/PostGIS
- expose versioned API endpoints
- authenticate users
- support the required basic roles
- accept media uploads
- provide a clean foundation for application modules

## Not Yet Required

- Complete dashboard
- Complete alert system
- Full offline synchronization
- Complete vehicle tracking
- Production-scale monitoring

---

# Phase 1 — Field Intelligence & Photo Analysis

**Priority: P0 / Highest**

## Objective

Allow a Field Officer to submit a geo-tagged field report containing a real road/bridge image and pass that image to Om Ji's AI/ML component for analysis.

The Field Officer is a data collector and intelligence source, not a direct editor of infrastructure.

## Flow

```text
Field Officer
      |
      v
Photo + GPS + Timestamp + Description
      |
      v
IncidentReport API
      |
      v
Store report & Spatial Snap to Nearest RoadSegment (PostGIS)
      |
      v
Photo Analysis CV Service (In-process)
      |
      v
Structured AI Result (issue_type, severity, confidence)
      |
      v
Temporary Risk Boost on Nearest RoadSegment
```

## Backend Components

- `reports` app
- IncidentReport model (GeoDjango PointField, photo, issue_type, severity)
- Image upload handling (Local MEDIA_ROOT)
- Spatial snapping service (`ST_DWithin` / nearest `RoadSegment`)
- Field Officer permissions & JWT auth
- Replaceable Photo Analysis CV service wrapper

## Minimum IncidentReport Data

- officer
- photo
- geographic location (Point)
- snapped_road_segment (ForeignKey to RoadSegment, nullable)
- description
- incident type (flood, landslide, road_damage, obstruction)
- severity (low, medium, high, critical)
- client timestamp
- server/sync timestamp

## AI Analysis Contract

The backend receives a structured dictionary rather than model internals:

```json
{
  "issue_type": "flood",
  "severity": "high",
  "confidence": 0.91
}
```

---

# Phase 2 — Road Network Graph & Disruption Risk Intelligence

**Priority: P0**

## Objective

Build the digital road network graph for the pilot corridor in the NER, and calculate disruption risk for every road segment using a transparent, rule-based geospatial risk engine (with drop-in ML model support).

## Flow

```text
OpenStreetMap Pilot Corridor
          |
          v
  OSMnx Graph Extraction
          |
          v
PostGIS RoadSegments (LineString geometries)
          +
Static Hazard Layers (GSI Landslide, ISRO/Bhuvan Flood)
          +
Dynamic Data (Rainfall, Weather Warnings, Field Incidents)
          |
          v
Rule-Based Geospatial Risk Engine (Configurable Weights)
          |
          v
Segment Disruption Risk (0–100: Low / Medium / High)
```

## Backend Components

- `roads` / `routes` app
- `RoadSegment` model (PostGIS `LineStringField`, road classification, distance, base travel time, current risk score, disruption status)
- Road network graph loader (OSMnx / NetworkX)
- Configurable Rule-Based Geospatial Risk Service
- Stable `RiskPredictionService` interface (swappable to ML models like Random Forest/XGBoost)

## Rule-Based Risk Engine (Configurable Weights for MVP)

As defined in Omji's PRD, the initial MVP uses an explainable weighted scoring engine:

| Factor | Illustrative Contribution |
|---|---|
| High landslide susceptibility zone | +30 |
| Historical landslide concentration | +15 |
| Moderate/High flood hazard zone | +15 |
| Heavy recent rainfall (> 50mm) | +25 |
| IMD Weather warning | +10 |
| Recent field incident report (flood/landslide) | +20 |

**Total Score Range:** 0 to 100
- **Low Risk:** 0 – 35
- **Medium Risk:** 36 – 65
- **High Risk / Disrupted:** 66 – 100

## AI-01 Drop-In Interface

```json
{
  "risk_score": 0.82,
  "disruption_probability": 0.87,
  "risk_level": "high",
  "top_factors": [
    "heavy rainfall",
    "high landslide susceptibility",
    "recent flood report"
  ]
}
```
  ]
}
```

The exact fields and model contract must match the AI/ML team's agreed implementation.

## Important Rule

Field Officers do not directly modify Infrastructure.

The flow is:

```text
Field Report
     |
     v
AI Analysis
     |
     v
Validation / Risk Intelligence
     |
     v
Infrastructure Risk State
```

Infrastructure remains protected from uncontrolled direct edits.

## Completion Criteria

Given a road/bridge and its relevant intelligence inputs, the backend can return:
- risk score
- disruption probability
- risk level
- relevant risk factors

and use that state in route selection.

## Not Yet Required

- Full weather automation
- Automated alerts
- Complete accessibility AI
- Public satellite ingestion

---

# Phase 3 — Candidate Routes + Risk-Aware Route Optimization

**Priority: P0**

## Objective

Recommend the safest and most optimal route rather than just the shortest route by applying dynamic risk penalties to road segments in the NetworkX graph.

## Flow

```text
Origin + Destination
        |
        v
Road Network Graph (NetworkX)
        |
        +---- Segment Distances
        +---- Dynamic Disruption Risk Penalties
        +---- Road Status / Closures
        |
        v
Dynamic Pathfinding & Candidate Generation (Shortest vs Safest)
        |
        v
Route Evaluation & Ranking
        |
        v
Recommended Route (with explanation & risk breakdown)
```

## Backend Components

- `routing` app / services
- NetworkX graph pathfinding engine
- Dynamic edge weight calculation (Distance + Risk Penalty)
- Ephemeral `RouteCandidate` response builder (never stored in DB)
- Route comparison & explanation generator

## RouteCandidate Response Shape

Ephemeral computed response structure:
- `route_id`
- `distance_km`
- `base_eta_minutes`
- `risk_score` (0–100 aggregate)
- `risk_level` (low, medium, high)
- `recommended` (boolean)
- `polyline` (GeoJSON coordinates)
- `risk_explanation` (e.g., "Avoids NH-06 landslide-affected segment; +12 mins travel time for 75% lower risk")

---

# Phase 4 — Condition-Aware ETA Estimation

**Priority: P0**

## Objective

Provide explainable, condition-aware estimated arrival times based on road classifications, terrain speeds, dynamic risk, and weather severity (with ML regression model upgrade path).

## MVP Practical Calculation Model

For the MVP, base travel time is calculated from road distance and road-type specific speeds in NER terrain, adjusted by environmental factors:

$$\text{Base Time} = \sum \frac{\text{Segment Distance}}{\text{Road Class Speed}}$$

**Adjustments:**
- Road Type / Hill terrain speeds (e.g., National Highway: 50 km/h, State Highway: 35 km/h, Hill/Mountain Pass: 25 km/h)
- High-risk road segment penalty multiplier
- Active rainfall / weather severity delay (+10% to +35%)
- Reported road disruptions or partial blockages

**ML Upgrade Path:** Once historical travel data is accumulated, the stable `ETAEstimationService` seamlessly incorporates Omji's regression model without changing the API contract.

## LocationPing

The mobile app is the GPS source. Location pings contain:
- vehicle
- latitude
- longitude
- speed
- timestamp

Dedicated GPS hardware is not required.

## Trip Data

The Trip model carries:
- vehicle
- origin
- destination
- start/end time
- status
- base ETA
- predicted ETA
- expected delay

## Completion Criteria

The backend can:
- receive the required trip/location information,
- calculate or receive base ETA,
- run the agreed AI-02 model,
- return predicted ETA,
- return expected delay.

## Important Constraint

The exact ETA model features must follow Om Ji's AI/ML model contract. Do not invent additional model inputs merely to make the backend appear more complete.

---

# Phase 5 — End-to-End Intelligence Pipeline

**Priority: P0 / Hackathon Demo**

## Objective

Connect the first four phases into one demonstrable operational workflow.

## Main Scenario

A Field Officer discovers a damaged/flooded/landslide-affected road.

```text
1. Field Officer captures image
              |
              v
2. Django receives geo-tagged report
              |
              v
3. Photo AI detects the issue
              |
              v
4. Risk model recalculates disruption risk
              |
              v
5. Backend generates candidate routes
              |
              v
6. Route AI ranks the alternatives
              |
              v
7. Recommended route is selected
              |
              v
8. ETA model predicts travel time
```

## Example Demo

Before the field report:

```text
Route A → Low Risk → 7h 10m → Recommended
Route B → Moderate Risk → 7h 35m
```

After a high-severity flood report:

```text
Route A → High Risk → 8h 20m
Route B → Low Risk → 7h 40m → Recommended
```

The important demonstration is that new field intelligence changes the operational decision.

## Completion Criteria

The backend can demonstrate:

```text
Photo
  ↓
AI Detection
  ↓
Risk Change
  ↓
Route Recommendation Change
  ↓
ETA Update
```

This is the primary hackathon backend demonstration.

---

# Phase 6 — Weather Intelligence

**Priority: P1**

## Objective

Replace demo/seed weather values with actual weather intelligence.

## Scope

- Public weather API integration
- Weather provider adapter
- WeatherSnapshot persistence
- Rainfall data
- Weather condition classification
- Celery periodic fetching
- Failure/retry handling
- Risk model integration

## Completion Criteria

Weather data can be periodically retrieved and made available to the risk prediction pipeline.

---

# Phase 7 — Vehicle Tracking

**Priority: P1**

## Objective

Implement the complete vehicle location tracking flow.

## Scope

- Vehicle management
- Driver association
- Location ping endpoint
- Location history
- Latest vehicle location
- Ownership validation
- Periodic mobile-app updates

The PRD specifies REST location pings from the driver's mobile application rather than MQTT or dedicated GPS hardware.

## Completion Criteria

The backend can receive and serve live-ish vehicle locations through REST polling.

---

# Phase 8 — Alerts & Automated Intelligence

**Priority: P1**

## Objective

Convert risk, disruption, weather, route and ETA conditions into actionable alerts.

## Scope

- Alert model
- Rule-based thresholds
- Celery tasks
- AI-derived triggers
- Alert severity
- Alert persistence
- Alert resolution
- Recommended action

Examples:

```text
High disruption risk
        ↓
Blocked-road alert

High ETA delay
        ↓
Delivery delay alert

Flood detection
        ↓
Flood alert
```

## Completion Criteria

Relevant conditions automatically create or update Alert records.

---

# Phase 9 — Offline Sync

**Priority: P1/P2**

## Objective

Allow Field Officers and drivers to continue collecting data in low/no-connectivity areas.

## Scope

- Mobile local cache integration
- Batch sync endpoint
- Client IDs
- Idempotency
- Client timestamps
- Ordered processing
- Last-write-wins behavior
- Per-record sync result

## Completion Criteria

Cached incident reports/location records can be uploaded when connectivity returns without creating duplicate records.

---

# Phase 10 — Accessibility Intelligence

**Priority: P2**

## Objective

Implement the full AI-04 accessibility intelligence capability.

## Scope

- District accessibility data
- Accessibility scoring
- Road-condition component
- Healthcare access component
- Market access component
- Wheelchair accessibility where applicable
- AI-04 integration
- Route-ranking integration

## Completion Criteria

Accessibility becomes a dynamically generated intelligence signal rather than only seeded/static data.

---

# Phase 11 — Dashboard & Aggregation APIs

**Priority: P2**

## Objective

Provide read-only backend APIs for web/dashboard interfaces.

## Scope

- District summary
- Vehicle summary
- Active alerts
- Bottlenecks
- Connectivity
- Risk summary
- Route intelligence
- Field intelligence summaries

No unnecessary heavy dashboard-specific database models should be introduced.

---

# Phase 12 — Production Hardening

**Priority: P2**

## Objective

Make the backend reliable and deployable after the core functionality is proven.

## Scope

### Testing

- Unit tests
- API tests
- Permission tests
- AI integration tests
- Route tests
- End-to-end tests

### Security

- HTTPS
- JWT security
- CORS restrictions
- File upload validation
- Request-size limits
- Input validation
- Database constraints
- Secure environment secrets
- Production Django settings

### Observability

- Application logs
- AI inference failures
- External API failures
- Celery failures
- Request IDs
- Appropriate error logging

### Deployment

- Production configuration
- Static/media handling
- Database migration process
- Backup strategy
- Performance checks

---

# 3. Priority Summary

| Phase | Feature | Priority |
|---|---|---|
| 0 | Backend Foundation | Required |
| 1 | Field Intelligence + Photo Analysis | **P0** |
| 2 | Infrastructure + Risk Prediction | **P0** |
| 3 | Candidate Routes + Route Optimization | **P0** |
| 4 | ETA Estimation | **P0** |
| 5 | End-to-End Intelligence Pipeline | **P0** |
| 6 | Weather Intelligence | P1 |
| 7 | Vehicle Tracking | P1 |
| 8 | Alerts | P1 |
| 9 | Offline Sync | P1/P2 |
| 10 | Accessibility Intelligence | P2 |
| 11 | Dashboard APIs | P2 |
| 12 | Production Hardening | P2 |

---

# 4. Core MVP Dependency Graph

```text
                    PHASE 0
                  Foundation
                      |
                      v
              ┌───────────────┐
              │    Phase 1    │
              │ Field Report  │
              │ + Photo AI    │
              └───────┬───────┘
                      |
                      v
              ┌───────────────┐
              │    Phase 2    │
              │ Infrastructure│
              │ + Risk AI     │
              └───────┬───────┘
                      |
             ┌────────┴────────┐
             v                 v
      ┌─────────────┐   ┌─────────────┐
      │   Phase 3   │   │   Phase 4   │
      │ Route AI    │   │   ETA AI    │
      └──────┬──────┘   └──────┬──────┘
             │                 │
             └────────┬────────┘
                      v
              ┌───────────────┐
              │    Phase 5    │
              │ End-to-End    │
              │ Demo Pipeline │
              └───────────────┘
```

---

# 5. Architecture Rules for All Phases

1. Single modular Django project — do not split the MVP into microservices.
2. Views stay thin — business logic belongs in services.
3. AI stays behind service interfaces — APIs should not depend on model implementation details.
4. Database is the operational source of truth where persistence is required.
5. Field Officers report incidents; they do not directly edit Infrastructure.
6. RouteCandidate remains computed, not a permanent database model.
7. External weather/routing providers use adapters so they can be replaced.
8. Do not build speculative abstractions such as event buses or generic repository layers without a real requirement.
9. Use REST for the MVP; WebSockets are not required.
10. Build the demo first without creating a dead-end architecture.
11. Do not invent AI model inputs or outputs; AI contracts must match the AI/ML team's agreed model specification.
12. Later-phase components may have minimal early dependencies, but their complete implementation should remain in their designated phase.

---

# 6. Definition of Done for the First Hackathon Milestone

The first milestone is considered successful when the team can demonstrate this complete scenario:

```text
Field Officer
     ↓
Uploads real geo-tagged road image
     ↓
Photo AI identifies disruption
     ↓
Risk model calculates road disruption risk
     ↓
Backend generates alternative routes
     ↓
Route AI recommends the best route
     ↓
ETA model predicts arrival time
     ↓
Frontend displays the resulting decision
```

The four core intelligence capabilities are therefore treated as one system, not four unrelated backend features.

All other platform capabilities remain extensible phases and should not block this first demonstration.
