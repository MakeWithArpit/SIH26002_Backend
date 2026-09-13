# SIH26002 Backend — Frontend API Documentation

> **Target Audience:** Frontend Web & Mobile App Developers  
> **Base URL:** `http://localhost:8000/api/v1` (Local Dev & Docker Compose)  
> **Interactive Swagger UI:** `http://localhost:8000/api/docs/`  
> **Interactive ReDoc:** `http://localhost:8000/api/redoc/`  
> **OpenAPI 3.0 Schema:** `http://localhost:8000/api/schema/`  
> **Content-Type:** `application/json` (unless specified as `multipart/form-data` for file uploads)  
> **Standard Response Format:** All endpoints return a standardized JSON envelope.

---

## Table of Contents
1. [Standard API Envelope & Authentication](#1-standard-api-envelope--authentication)
2. [Phase 0: Authentication Endpoints](#2-phase-0-authentication-endpoints)
3. [Phase 1: Field Intelligence & Incident Photo Reporting](#3-phase-1-field-intelligence--incident-photo-reporting)
4. [Phase 2: Road Network Graph & Disruption Risk Intelligence](#4-phase-2-road-network-graph--disruption-risk-intelligence)
5. [Phase 3: Risk-Aware Route Optimization & Recommendations](#5-phase-3-risk-aware-route-optimization--recommendations)
6. [Phase 4: Vehicle Telemetry & Condition-Aware Trip ETAs](#6-phase-4-vehicle-telemetry--condition-aware-trip-etas)
7. [Phase 5: End-to-End Pipeline Simulation](#7-phase-5-end-to-end-pipeline-simulation)
8. [Phase 8: Road & Infrastructure Alerts](#8-phase-8-road--infrastructure-alerts)
9. [Enum & Choice Values Reference](#9-enum--choice-values-reference)

---

## 1. Standard API Envelope & Authentication

### Success Response Envelope
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully",
  "status_code": 200
}
```

### Error Response Envelope
```json
{
  "success": false,
  "data": null,
  "message": "Descriptive error message",
  "errors": {
    "field_name": ["Specific validation error explanation"]
  },
  "status_code": 400
}
```

### Authorization Header
All protected endpoints require the JWT Bearer token:
```http
Authorization: Bearer <access_token>
```

---

## 2. Phase 0: Authentication Endpoints

### 2.1 User Login
* **Method:** `POST`
* **URL:** `/api/v1/accounts/login/`
* **Access:** Public
* **Request Body:**
```json
{
  "username": "officer_rahul",
  "password": "SecurePassword123!"
}
```
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "username": "officer_rahul",
      "email": "rahul@assam.gov.in",
      "first_name": "Rahul",
      "last_name": "Sharma",
      "role": "field_officer",
      "phone_number": "+919876543210",
      "department": "Public Works Department (PWD)"
    }
  },
  "message": "Login successful",
  "status_code": 200
}
```

### 2.2 Refresh Token
* **Method:** `POST`
* **URL:** `/api/v1/accounts/token/refresh/`
* **Access:** Public
* **Request Body:**
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "message": "Token refreshed",
  "status_code": 200
}
```

### 2.3 Get Current User Profile
* **Method:** `GET`
* **URL:** `/api/v1/accounts/profile/`
* **Access:** Authenticated (`Bearer <token>`)
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "officer_rahul",
    "email": "rahul@assam.gov.in",
    "first_name": "Rahul",
    "last_name": "Sharma",
    "role": "field_officer",
    "phone_number": "+919876543210",
    "department": "Public Works Department (PWD)"
  },
  "message": "Profile retrieved successfully",
  "status_code": 200
}
```

---

## 3. Phase 1: Field Intelligence & Incident Photo Reporting

### 3.1 Submit Incident Report (With Photo Upload)
* **Method:** `POST`
* **URL:** `/api/v1/reports/incidents/`
* **Access:** `field_officer` or `admin`
* **Content-Type:** `multipart/form-data`
* **Form Fields:**

| Field Name | Type | Required | Description / Example |
|---|---|---|---|
| `photo` | File | **Yes** | Image file (JPEG, PNG). Max 10MB. |
| `latitude` | Float | **Yes** | `26.1300` |
| `longitude` | Float | **Yes** | `91.8200` |
| `incident_type` | String | **Yes** | `landslide`, `flood`, `road_damage`, `bridge_collapse`, `blockage`, `other` |
| `severity` | String | **Yes** | `low`, `medium`, `high`, `critical` |
| `description` | String | No | `"Major rockfall blocking both lanes of NH-06 near Jorabat."` |
| `client_timestamp` | ISO8601 | No | `"2026-09-07T14:30:00Z"` (Timestamp captured by mobile app offline/online) |

* **Success Response (`201 Created`):**
```json
{
  "success": true,
  "data": {
    "id": 12,
    "officer_name": "Rahul Sharma",
    "photo_url": "http://127.0.0.1:8000/media/reports/photos/2026/09/07/rockfall_jorabat.jpg",
    "latitude": 26.1300,
    "longitude": 91.8200,
    "description": "Major rockfall blocking both lanes of NH-06 near Jorabat.",
    "incident_type": "landslide",
    "severity": "critical",
    "client_timestamp": "2026-09-07T14:30:00Z",
    "server_timestamp": "2026-09-07T14:30:02.158Z",
    "ai_issue_type": "landslide",
    "ai_severity": "critical",
    "ai_confidence": 0.94,
    "analysis_status": "completed",
    "snapped_infrastructure": {
      "id": 1,
      "name": "NH-06 Guwahati City to Jorabat Segment",
      "risk_score": 69.0,
      "risk_level": "high"
    }
  },
  "message": "Incident report submitted and processed successfully",
  "status_code": 201
}
```

### 3.2 List Incident Reports
* **Method:** `GET`
* **URL:** `/api/v1/reports/incidents/`
* **Access:** Authenticated (Field officers see their own submissions; Admins see all)
* **Optional Query Parameters:**
  * `?incident_type=landslide`
  * `?severity=critical`
  * `?analysis_status=completed`
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": [
    {
      "id": 12,
      "officer_name": "Rahul Sharma",
      "photo_url": "http://127.0.0.1:8000/media/reports/photos/2026/09/07/rockfall_jorabat.jpg",
      "latitude": 26.1300,
      "longitude": 91.8200,
      "description": "Major rockfall blocking both lanes of NH-06 near Jorabat.",
      "incident_type": "landslide",
      "severity": "critical",
      "client_timestamp": "2026-09-07T14:30:00Z",
      "server_timestamp": "2026-09-07T14:30:02.158Z",
      "ai_issue_type": "landslide",
      "ai_severity": "critical",
      "ai_confidence": 0.94,
      "analysis_status": "completed",
      "snapped_infrastructure_id": 1
    }
  ],
  "message": "Incident reports retrieved successfully",
  "status_code": 200
}
```

### 3.3 Get Single Incident Report
* **Method:** `GET`
* **URL:** `/api/v1/reports/incidents/{id}/`
* **Access:** Authenticated

---

## 4. Phase 2: Road Network Graph & Disruption Risk Intelligence

### 4.1 List Districts
* **Method:** `GET`
* **URL:** `/api/v1/routes/districts/`
* **Access:** Authenticated
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Kamrup Metropolitan",
      "state": "Assam",
      "accessibility_score": 9.2,
      "status": "connected",
      "geojson": {
        "type": "MultiPolygon",
        "coordinates": [
          [[[91.60, 26.05], [91.95, 26.05], [91.95, 26.25], [91.60, 26.25], [91.60, 26.05]]]
        ]
      }
    }
  ],
  "message": "Districts retrieved successfully",
  "status_code": 200
}
```

### 4.2 List Road Infrastructure Segments
* **Method:** `GET`
* **URL:** `/api/v1/routes/infrastructure/`
* **Access:** Authenticated
* **Available Query Filters:**
  * `?district=1`
  * `?status=accessible` (`accessible`, `compromised`, `blocked`)
  * `?risk_level=high` (`low`, `medium`, `high`)
  * `?infra_type=road` (`road`, `bridge`, `culvert`, `tunnel`)
  * **Proximity Spatial Search:** `?lat=26.15&lng=91.76&radius_m=5000` (Finds road segments within `radius_m` meters of GPS position)
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "NH-06 Guwahati City to Jorabat Segment",
      "district_name": "Kamrup Metropolitan",
      "infra_type": "road",
      "road_classification": "national_highway",
      "start_node": 1001,
      "end_node": 1002,
      "oneway": false,
      "length_km": 16.5,
      "base_speed_kmh": 55.0,
      "base_travel_time_min": 18.0,
      "status": "accessible",
      "condition": "good",
      "landslide_susceptibility": "medium",
      "flood_hazard_zone": "low",
      "historical_landslide_count": 1,
      "recent_rainfall_mm": 38.0,
      "weather_warning": false,
      "risk_score": 49.0,
      "risk_level": "medium",
      "disruption_probability": 0.49,
      "top_factors": [
        "moderate landslide susceptibility",
        "historical landslide area (1 recorded)",
        "moderate rainfall (38.0mm)"
      ],
      "coordinates": [
        [26.1833, 91.7500],
        [26.1600, 91.7850],
        [26.1300, 91.8200],
        [26.1030, 91.8650]
      ]
    }
  ],
  "message": "Infrastructure segments retrieved successfully",
  "status_code": 200
}
```

### 4.3 Dynamically Assess / Simulate Segment Disruption Risk
* **Method:** `POST`
* **URL:** `/api/v1/routes/infrastructure/{id}/assess-risk/`
* **Access:** Authenticated
* **Request Body (Optional Simulation Overrides):**
```json
{
  "simulated_rainfall_mm": 65.0,
  "simulated_weather_warning": true,
  "simulated_condition": "damaged"
}
```
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "infrastructure_id": 1,
    "name": "NH-06 Guwahati City to Jorabat Segment",
    "risk_score": 85.0,
    "risk_level": "high",
    "disruption_probability": 0.85,
    "top_factors": [
      "moderate landslide susceptibility",
      "historical landslide area (1 recorded)",
      "heavy rainfall (65.0mm)",
      "active IMD weather warning",
      "infrastructure physically damaged"
    ]
  },
  "message": "Risk assessed successfully",
  "status_code": 200
}
```

---

## 5. Phase 3: Risk-Aware Route Optimization & Recommendations

### 5.1 Calculate Candidate Routes & AI Recommendation
* **Method:** `POST`
* **URL:** `/api/v1/routes/calculate/`
* **Access:** Authenticated

#### Payload Option A: By GPS Lat/Lng Coordinates (Recommended for Maps/Mobile)
```json
{
  "origin_lat": 26.1833,
  "origin_lng": 91.7500,
  "destination_lat": 25.5788,
  "destination_lng": 91.8933
}
```

#### Payload Option B: By Graph Node IDs
```json
{
  "origin_node": 1001,
  "destination_node": 1006
}
```

* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "origin_resolved_node": 1001,
    "destination_resolved_node": 1006,
    "candidate_count": 2,
    "recommended_route_id": "route-safe",
    "routes": [
      {
        "route_id": "route-safe",
        "name": "Low-Risk Alternative Route (Safest)",
        "distance_km": 30.0,
        "base_eta_minutes": 40.0,
        "risk_score": 12.0,
        "risk_level": "low",
        "recommended": true,
        "explanation": "Recommended for safety: Avoids high-risk road segments. Adds 5.0 km (+10.0 mins) to bypass severe hazard zones with a 58.6 points lower risk score.",
        "polyline": [
          [26.1833, 91.7500],
          [26.1200, 91.7100],
          [25.8500, 91.8000],
          [25.5788, 91.8933]
        ],
        "segments": [
          {
            "id": 6,
            "name": "Shillong Eastern Bypass Detour (Alternative Route)",
            "length_km": 30.0,
            "risk_score": 12.0,
            "risk_level": "low",
            "status": "accessible"
          }
        ]
      },
      {
        "route_id": "route-shortest",
        "name": "Direct Highway Route (Shortest)",
        "distance_km": 25.0,
        "base_eta_minutes": 30.0,
        "risk_score": 70.6,
        "risk_level": "high",
        "recommended": false,
        "explanation": "Direct shortest route, but NOT recommended due to HIGH disruption risk (score 70.6/100).",
        "polyline": [
          [26.1833, 91.7500],
          [26.1300, 91.8200],
          [25.9015, 91.8780],
          [25.5788, 91.8933]
        ],
        "segments": [
          {
            "id": 1,
            "name": "NH-06 Guwahati City to Jorabat Segment",
            "length_km": 16.5,
            "risk_score": 69.0,
            "risk_level": "high",
            "status": "accessible"
          },
          {
            "id": 2,
            "name": "NH-06 Jorabat to Nongpoh Hill Descent",
            "length_km": 8.5,
            "risk_score": 45.0,
            "risk_level": "medium",
            "status": "accessible"
          }
        ]
      }
    ]
  },
  "message": "Routes calculated and ranked successfully",
  "status_code": 200
}
```

---

## 6. Phase 4: Vehicle Telemetry & Condition-Aware Trip ETAs

### 6.1 Register a Vehicle
* **Method:** `POST`
* **URL:** `/api/v1/vehicles/`
* **Access:** Authenticated
* **Request Body:**
```json
{
  "registration_number": "AS-01-EC-4412",
  "vehicle_type": "truck"
}
```
* **Success Response (`201 Created`):**
```json
{
  "success": true,
  "data": {
    "id": 3,
    "registration_number": "AS-01-EC-4412",
    "vehicle_type": "truck",
    "is_active": true,
    "current_lat": null,
    "current_lng": null,
    "current_speed": 0.0,
    "last_ping_time": null
  },
  "message": "Vehicle created successfully",
  "status_code": 201
}
```

### 6.2 Ingest Live Telemetry Ping
* **Method:** `POST`
* **URL:** `/api/v1/vehicles/{id}/locations/`
* **Access:** Authenticated
* **Description:** Ingests GPS ping into historical telemetry breadcrumbs and atomically updates cached telemetry fields on the `Vehicle` record for $O(1)$ polling.
* **Request Body:**
```json
{
  "lat": 26.1450,
  "lng": 91.8100,
  "speed": 42.5,
  "heading": 135.0,
  "accuracy": 4.2
}
```
* **Success Response (`201 Created`):**
```json
{
  "success": true,
  "data": {
    "id": 104,
    "vehicle": 3,
    "lat": 26.1450,
    "lng": 91.8100,
    "speed": 42.5,
    "heading": 135.0,
    "accuracy": 4.2,
    "timestamp": "2026-09-07T14:45:00.210Z"
  },
  "message": "Location ping recorded and vehicle cache updated",
  "status_code": 201
}
```

### 6.3 Instant Vehicle Location Fetch (O(1) Polling for Live Map)
* **Method:** `GET`
* **URL:** `/api/v1/vehicles/{id}/location/latest/`
* **Access:** Authenticated
* **Description:** Instant fetch from vehicle cache without querying or scanning massive ping history tables.
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "vehicle_id": 3,
    "registration_number": "AS-01-EC-4412",
    "lat": 26.1450,
    "lng": 91.8100,
    "speed_kmh": 42.5,
    "last_updated": "2026-09-07T14:45:00.210Z"
  },
  "message": "Latest location retrieved",
  "status_code": 200
}
```

### 6.4 Create a Trip (With Initial Condition-Aware ETA)
* **Method:** `POST`
* **URL:** `/api/v1/trips/`
* **Access:** Authenticated
* **Request Body:**
```json
{
  "vehicle": 3,
  "origin_lat": 26.1833,
  "origin_lng": 91.7500,
  "destination_lat": 25.5788,
  "destination_lng": 91.8933,
  "cargo_description": "Medical & essential disaster relief supplies"
}
```
* **Success Response (`201 Created`):**
```json
{
  "success": true,
  "data": {
    "id": 8,
    "vehicle": 3,
    "vehicle_registration": "AS-01-EC-4412",
    "status": "planned",
    "origin": {
      "lat": 26.1833,
      "lng": 91.7500
    },
    "destination": {
      "lat": 25.5788,
      "lng": 91.8933
    },
    "cargo_description": "Medical & essential disaster relief supplies",
    "start_time": null,
    "end_time": null,
    "base_eta_minutes": 105.0,
    "predicted_eta_minutes": 138.0,
    "expected_delay_minutes": 33.0,
    "delay_reasons": [
      "Severe road disruption risk on NH-06 (+45% transit time)",
      "Moderate rainfall (38.0mm) causing reduced hill transit speed"
    ]
  },
  "message": "Trip created with condition-aware ETA",
  "status_code": 201
}
```

### 6.5 Trip Lifecycle Actions
#### Start Trip:
* **Method:** `POST`
* **URL:** `/api/v1/trips/{id}/start/`
* **Status transitions:** `planned` &rarr; `in_transit` (sets `start_time` to `now`).

#### Complete Trip:
* **Method:** `POST`
* **URL:** `/api/v1/trips/{id}/complete/`
* **Status transitions:** `in_transit` &rarr; `completed` (sets `end_time` to `now`).

### 6.6 Recalculate Trip ETA During Transit
* **Method:** `POST`
* **URL:** `/api/v1/trips/{id}/recalculate-eta/`
* **Access:** Authenticated
* **Description:** Dynamically updates trip ETA based on live road segment disruption risks, recent rainfall, weather warnings, and vehicle's actual telemetry speed deficit.
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "trip_id": 8,
    "base_eta_minutes": 105.0,
    "predicted_eta_minutes": 142.5,
    "expected_delay_minutes": 37.5,
    "delay_severity": "moderate",
    "top_factors": [
      "Elevated landslide risk on NH-06 corridor sector",
      "Vehicle moving 15 km/h slower than road design speed due to steep ascent"
    ]
  },
  "message": "Trip ETA recalculated successfully",
  "status_code": 200
}
```

---

## 7. Phase 5: End-to-End Pipeline Simulation

### 7.1 Simulate Full Intelligence Pipeline
* **Method:** `POST`
* **URL:** `/api/v1/routes/simulate-pipeline/`
* **Access:** Authenticated
* **Description:** Triggers the complete 6-step demo pipeline: incident submission → spatial snap → risk surge → graph rebuild → route re-ranking → ETA recalculation. Designed for hackathon judges and frontend integration testing.
* **Request Body:** _(empty — uses seeded pilot corridor data)_
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "pipeline_steps": [
      {"step": 1, "name": "Incident Submitted", "status": "ok"},
      {"step": 2, "name": "Spatial Snap", "status": "ok", "snapped_segment_id": 3},
      {"step": 3, "name": "Risk Surge", "status": "ok", "risk_level": "high", "risk_score": 82},
      {"step": 4, "name": "Graph Rebuild", "status": "ok"},
      {"step": 5, "name": "Route Re-ranked", "status": "ok", "recommended": "safe_bypass"},
      {"step": 6, "name": "ETA Recalculated", "status": "ok", "delay_minutes": 37.5}
    ]
  },
  "message": "End-to-end pipeline simulation completed successfully",
  "status_code": 200
}
```

---

## 8. Phase 8: Road & Infrastructure Alerts

### 8.1 Get Active Road Alerts
* **Method:** `GET`
* **URL:** `/api/v1/alerts/`
* **Access:** Authenticated
* **Description:** Returns a list of active road and infrastructure alerts generated dynamically from the current risk state of all road segments in the pilot corridor.
* **Query Parameters:**
  * `lat` _(optional float)_ — Filter alerts near a coordinate (latitude)
  * `lng` _(optional float)_ — Filter alerts near a coordinate (longitude)
  * `radius_m` _(optional int)_ — Radius in metres for proximity filtering (default 50000)
* **Success Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "alerts": [
      {
        "alert_id": "infra-3-high",
        "type": "infrastructure_risk",
        "severity": "high",
        "title": "High Disruption Risk — NH-06 Barapani Sector",
        "description": "Risk score 82/100. Landslide susceptibility HIGH. Recent rainfall 68mm.",
        "infrastructure_id": 3,
        "location": {"lat": 25.6588, "lng": 91.8933},
        "risk_score": 82,
        "risk_level": "high",
        "generated_at": "2026-09-13T08:21:00Z"
      }
    ],
    "total_alerts": 1
  },
  "message": "Active alerts retrieved",
  "status_code": 200
}
```

---

## 9. Enum & Choice Values Reference

### Roles
* `admin` — Full platform administrative privileges
* `field_officer` — Ground officer with photo upload and reporting rights
* `normal_user` — General user / viewer

### Incident Types (`incident_type` / `ai_issue_type`)
* `landslide`
* `flood`
* `road_damage`
* `bridge_collapse`
* `blockage`
* `other`

### Severity Levels (`severity` / `ai_severity`)
* `low`
* `medium`
* `high`
* `critical`

### Infrastructure Types (`infra_type`)
* `road`
* `bridge`
* `culvert`
* `tunnel`

### Road Classifications (`road_classification`)
* `national_highway` (Base speed: 50 km/h)
* `state_highway` (Base speed: 40 km/h)
* `major_district_road` (Base speed: 30 km/h)
* `rural_road` (Base speed: 20 km/h)

### Operational Status (`status`)
* `accessible` — Normal operations
* `compromised` — Operational with delays/cautions
* `blocked` — Totally impassable

### Risk Levels (`risk_level`)
* `low` (Risk Score: 0 – 35)
* `medium` (Risk Score: 36 – 65)
* `high` (Risk Score: 66 – 100)

### Vehicle Types (`vehicle_type`)
* `truck`
* `van`
* `drone`
* `boat`

### Trip Status (`status`)
* `planned`
* `in_transit`
* `completed`
* `cancelled`

---

## 10. Common HTTP Status Codes
* `200 OK` — Successful GET/POST operation
* `201 Created` — Resource successfully created (Incident Report, Vehicle, Trip, Ping)
* `400 Bad Request` — Validation error (Missing fields, invalid coordinate range, etc.)
* `401 Unauthorized` — Missing or expired JWT token in `Authorization: Bearer <token>`
* `403 Forbidden` — Insufficient role permissions (e.g. non-officer submitting incident)
* `404 Not Found` — Resource ID does not exist
