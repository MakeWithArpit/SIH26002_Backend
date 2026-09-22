# SIH26002 Backend — Complete API Reference Manual (Phases 0–12)

> **Platform:** AI-Based Smart Logistics and Accessibility Intelligence Platform  
> **Production Live URL (Render):** `https://sih26002-backend-57w9.onrender.com`  
> **Local Development URL:** `http://localhost:8000`  
> **API v1 Base URL:** `/api/v1`  
> **Swagger UI Documentation:** `https://sih26002-backend-57w9.onrender.com/api/docs/`  
> **ReDoc Documentation:** `https://sih26002-backend-57w9.onrender.com/api/redoc/`  
> **OpenAPI 3.0 Schema:** `https://sih26002-backend-57w9.onrender.com/api/schema/`  
> **Content-Type:** `application/json` (All endpoints accept & return JSON)  

---

## Table of Contents
1. [Standard API Response Envelope & Authentication](#1-standard-api-response-envelope--authentication)
2. [Phase 0 & 12: Authentication & User Role Management](#2-phase-0--12-authentication--user-role-management)
3. [Phase 1: Field Intelligence & Incident Photo Reporting](#3-phase-1-field-intelligence--incident-photo-reporting)
4. [Phase 2: Road Network Graph & Disruption Risk Intelligence](#4-phase-2-road-network-graph--disruption-risk-intelligence)
5. [Phase 3: Risk-Aware Route Optimization & Recommendations](#5-phase-3-risk-aware-route-optimization--recommendations)
6. [Phase 4 & 7: Vehicle Telemetry & Condition-Aware Trip ETAs](#6-phase-4--7-vehicle-telemetry--condition-aware-trip-etas)
7. [Phase 5: End-to-End Intelligence Pipeline Simulation](#7-phase-5-end-to-end-intelligence-pipeline-simulation)
8. [Phase 6: Live Weather Intelligence & IMD Warnings](#8-phase-6-live-weather-intelligence--imd-warnings)
9. [Phase 8: Road & Infrastructure Hazard Alerts](#9-phase-8-road--infrastructure-hazard-alerts)
10. [Phase 9: Offline Resilient Batch Synchronization](#10-phase-9-offline-resilient-batch-synchronization)
11. [Phase 10: Dynamic District Accessibility Intelligence](#11-phase-10-dynamic-district-accessibility-intelligence)
12. [Phase 11: Real-Time Operational Dashboard & Aggregations](#12-phase-11-real-time-operational-dashboard--aggregations)
13. [Phase 12: System Health & Root Status Endpoints](#13-phase-12-system-health--root-status-endpoints)
14. [Enum & Choice Values Reference](#14-enum--choice-values-reference)

---

## 1. Standard API Response Envelope & Authentication

All API endpoints return a standardized JSON envelope:

### Success Response Envelope (`HTTP 200 / 201`)
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully",
  "status_code": 200
}
```

### Error Response Envelope (`HTTP 400 / 401 / 403 / 404 / 500`)
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
Include the JWT Bearer token on all protected endpoints:
```http
Authorization: Bearer <access_token>
```

---

## 2. Phase 0 & 12: Authentication & User Role Management

### 2.1 User Login (Obtain JWT)
* **Endpoint:** `POST /api/v1/accounts/login/` (or `/api/v1/auth/login/`)
* **Access:** Public
* **Request:**
```json
{
  "username": "admin_arpit",
  "password": "Password123!"
}
```
* **Success Response (`200 OK`):**
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 2.2 Refresh Token
* **Endpoint:** `POST /api/v1/accounts/refresh/`
* **Access:** Public
* **Request:**
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```
* **Response (`200 OK`):** Returns new `access` token string.

### 2.3 User Registration
* **Endpoint:** `POST /api/v1/accounts/register/`
* **Access:** Public
* **Request:**
```json
{
  "username": "officer_jorabat",
  "email": "officer_jorabat@sih.gov.in",
  "password": "Password123!",
  "first_name": "Karan",
  "last_name": "Barman",
  "role": "field_officer",
  "phone": "+919876543210",
  "department": "PWD Assam"
}
```

### 2.4 Get Current User Profile
* **Endpoint:** `GET /api/v1/accounts/me/`
* **Access:** Authenticated
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "admin_arpit",
    "email": "admin_arpit@sih26002.gov.in",
    "first_name": "Arpit",
    "last_name": "Singh",
    "is_staff": true,
    "is_superuser": false,
    "profile": {
      "role": "admin",
      "role_display": "Admin",
      "phone": "+919876543210",
      "department": "PWD",
      "created_at": "2026-09-22T16:00:00Z",
      "updated_at": "2026-09-22T16:48:00Z"
    }
  },
  "message": null,
  "status_code": 200
}
```

### 2.5 List All Users & Roles (Admin Only)
* **Endpoint:** `GET /api/v1/accounts/users/`
* **Query Params:** `?role=admin|field_officer|normal_user`, `?search=rahul`
* **Access:** Admin only (`IsAdminRole`)
* **Response (`200 OK`):** Array of all users, their profiles, roles, and staff status.

### 2.6 Update User Role & Permissions (Admin Only)
* **Endpoint:** `PATCH /api/v1/accounts/users/<user_id>/role/`
* **Access:** Admin only
* **Request:**
```json
{
  "role": "field_officer",
  "department": "PWD Meghalaya Quick Response",
  "phone": "+919876512345",
  "is_staff": false
}
```
* **Response (`200 OK`):** Returns updated User object with updated Profile.

### 2.7 Bulk Synchronize All User Roles (Admin Only)
* **Endpoint:** `POST /api/v1/accounts/sync-roles/`
* **Access:** Admin only
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "updated_users_count": 3,
    "created_profiles_count": 0,
    "total_users": 53
  },
  "message": "Synchronized roles: 3 users updated, 0 profiles created.",
  "status_code": 200
}
```

---

## 3. Phase 1: Field Intelligence & Incident Photo Reporting

Field officers capture geotagged incident photos. The backend snaps the GPS point to the nearest road segment via PostGIS, triggers CV analysis, and boosts segment risk.

### 3.1 Submit Incident Report
* **Endpoint:** `POST /api/v1/reports/incidents/`
* **Access:** Authenticated (Field Officer / Admin)
* **Request Body:**
```json
{
  "photo_url": "https://ik.imagekit.io/sih26002/reports/landslide_nh06.jpg",
  "latitude": 26.1030,
  "longitude": 91.8650,
  "incident_type": "landslide",
  "severity": "critical",
  "description": "Massive rockfall blocking both lanes of NH-06 near Jorabat",
  "client_timestamp": "2026-09-22T10:30:00Z"
}
```
* **Response (`201 Created`):**
```json
{
  "success": true,
  "data": {
    "id": 14,
    "incident_type": "landslide",
    "severity": "critical",
    "description": "Massive rockfall blocking both lanes of NH-06 near Jorabat",
    "photo_url": "https://ik.imagekit.io/sih26002/reports/landslide_nh06.jpg",
    "latitude": 26.103,
    "longitude": 91.865,
    "snapped_road_segment": 42,
    "snapped_distance_meters": 12.4,
    "ai_analysis": {
      "detected_issue": "landslide",
      "severity": "critical",
      "confidence": 0.94,
      "blockage_estimated_pct": 100
    },
    "created_at": "2026-09-22T10:30:01Z"
  },
  "message": "Incident reported and road risk updated.",
  "status_code": 201
}
```

### 3.2 List Incident Reports
* **Endpoint:** `GET /api/v1/reports/incidents/`
* **Query Params:** `?incident_type=landslide`, `?severity=critical`, `?status=verified`
* **Access:** Authenticated

---

## 4. Phase 2: Road Network Graph & Disruption Risk Intelligence

### 4.1 List Districts
* **Endpoint:** `GET /api/v1/routes/districts/`
* **Access:** Authenticated
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Kamrup Metropolitan",
      "state": "Assam",
      "accessibility_score": 8.7,
      "connectivity_status": "normal"
    }
  ]
}
```

### 4.2 List Road Infrastructure & Spatial Proximity Search
* **Endpoint:** `GET /api/v1/routes/infrastructure/`
* **Query Params (Proximity Search):**
  - `?lat=26.1833&lng=91.7500&radius_m=5000` (Find segments within 5km radius via PostGIS spatial index)
  - `?district=1`
  - `?status=accessible|risky|blocked`
* **Access:** Authenticated

### 4.3 Assess / Recalculate Road Segment Disruption Risk
* **Endpoint:** `POST /api/v1/routes/infrastructure/<id>/assess-risk/`
* **Request (Simulation Override):**
```json
{
  "simulated_rainfall_mm": 75.0,
  "simulated_weather_warning": true,
  "simulated_condition": "damaged"
}
```
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "infrastructure_id": 42,
    "risk_score": 82.5,
    "risk_level": "high",
    "operational_status": "blocked",
    "top_factors": [
      "extreme rainfall (>50mm): +25 pts",
      "IMD red weather warning: +10 pts",
      "recent verified landslide: +20 pts"
    ]
  }
}
```

---

## 5. Phase 3: Risk-Aware Route Optimization & Recommendations

Calculates multiple candidate routes (Fastest vs Safest Alternative) using risk-penalized graph algorithms (NetworkX & Dijkstra) avoiding blocked or high-risk segments.

### 5.1 Calculate Optimized Route
* **Endpoint:** `POST /api/v1/routes/calculate/`
* **Access:** Authenticated
* **Request by Coordinates:**
```json
{
  "origin_lat": 26.1833,
  "origin_lng": 91.7500,
  "destination_lat": 25.5788,
  "destination_lng": 91.8933,
  "optimization_preference": "safest"
}
```
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "recommended_route_id": "route_safe_1",
    "candidate_routes": [
      {
        "route_id": "route_safe_1",
        "label": "Safest Alternative (Bypasses Jorabat Risk Zone)",
        "distance_km": 104.2,
        "estimated_duration_minutes": 158.0,
        "average_risk_score": 18.4,
        "max_risk_score": 32.0,
        "hazard_segments_count": 0,
        "ai_recommendation_score": 9.2,
        "path_coordinates": [
          [91.7500, 26.1833],
          [91.8100, 26.1450],
          [91.8933, 25.5788]
        ]
      },
      {
        "route_id": "route_direct_2",
        "label": "Direct NH-06 Corridor",
        "distance_km": 98.6,
        "estimated_duration_minutes": 195.0,
        "average_risk_score": 68.5,
        "max_risk_score": 85.0,
        "hazard_segments_count": 2,
        "ai_recommendation_score": 5.1
      }
    ]
  }
}
```

---

## 6. Phase 4 & 7: Vehicle Telemetry & Condition-Aware Trip ETAs

### 6.1 Register Fleet Vehicle
* **Endpoint:** `POST /api/v1/vehicles/`
* **Request:**
```json
{
  "registration_number": "AS-01-EV-4091",
  "vehicle_type": "truck",
  "driver": 3
}
```

### 6.2 Stream Location Ping (GPS Telemetry)
* **Endpoint:** `POST /api/v1/vehicles/<id>/locations/`
* **Request:**
```json
{
  "lat": 26.1450,
  "lng": 91.8100,
  "speed": 45.2,
  "heading": 140.0,
  "accuracy": 3.5,
  "battery_level": 88
}
```

### 6.3 Get Latest Vehicle Position (O(1) Cached Lookup)
* **Endpoint:** `GET /api/v1/vehicles/<id>/location/latest/`
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "vehicle_id": 1,
    "registration_number": "AS-01-EV-4091",
    "last_latitude": 26.145,
    "last_longitude": 91.81,
    "last_speed_kmh": 45.2,
    "last_ping_time": "2026-09-22T16:30:00Z"
  }
}
```

### 6.4 Create Trip with Predicted ETA
* **Endpoint:** `POST /api/v1/trips/`
* **Request:**
```json
{
  "vehicle": 1,
  "origin_lat": 26.1833,
  "origin_lng": 91.7500,
  "destination_lat": 25.5788,
  "destination_lng": 91.8933,
  "cargo_description": "Emergency Medical Relief Consignment"
}
```

### 6.5 Dynamic ETA Recalculation
* **Endpoint:** `POST /api/v1/trips/<id>/recalculate-eta/`
* **Response (`200 OK`):** Returns updated ETA accounting for real-time weather and road condition degradation.

---

## 7. Phase 5: End-to-End Intelligence Pipeline Simulation

* **Endpoint:** `POST /api/v1/routes/simulate-pipeline/`
* **Access:** Authenticated (Staff / Admin)
* **Description:** Runs the complete 6-stage intelligence pipeline end-to-end:
  1. Ingests incident report with simulated landslide photo
  2. Snaps GPS to nearest road segment via PostGIS
  3. Escalates disruption risk score on corridor
  4. Dynamically rebuilds graph edge weights
  5. Computes alternative safe route avoiding bottleneck
  6. Recalculates vehicle trip ETA

---

## 8. Phase 6: Live Weather Intelligence & IMD Warnings

### 8.1 Get District Live Weather Snapshot
* **Endpoint:** `GET /api/v1/routes/districts/<id>/weather/`
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "district_id": 1,
    "district_name": "Kamrup Metropolitan",
    "rainfall_mm": 48.5,
    "temperature_celsius": 28.2,
    "humidity_pct": 85,
    "condition": "heavy",
    "warning_level": "orange",
    "recorded_at": "2026-09-22T16:00:00Z"
  }
}
```

### 8.2 Get District 7-Day Weather Forecast
* **Endpoint:** `GET /api/v1/routes/districts/<id>/weather/forecast/`

### 8.3 Trigger Live Weather Sync
* **Endpoint:** `POST /api/v1/routes/weather/sync/`

---

## 9. Phase 8: Road & Infrastructure Hazard Alerts

### 9.1 Get Active Alerts
* **Endpoint:** `GET /api/v1/alerts/` (or `/api/v1/routes/alerts/`)
* **Query Params:** `?severity=high|critical`, `?district=1`
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": [
    {
      "id": 7,
      "alert_type": "landslide_hazard",
      "severity": "critical",
      "title": "NH-06 Blockage at Km 44",
      "message": "Heavy debris obstruction. Diverting all heavy cargo via alternate corridor.",
      "is_active": true,
      "created_at": "2026-09-22T15:20:00Z"
    }
  ]
}
```

### 9.2 Acknowledge Alert
* **Endpoint:** `POST /api/v1/routes/alerts/<id>/acknowledge/`

---

## 10. Phase 9: Offline Resilient Batch Synchronization

Allows field mobile clients to cache incident reports and GPS pings offline and sync in bulk when network is restored. Idempotent with Last-Write-Wins (LWW) resolution.

### 10.1 Batch Sync Endpoint
* **Endpoint:** `POST /api/v1/sync/batch/`
* **Access:** Authenticated
* **Request Body:**
```json
{
  "records": [
    {
      "client_id": "c6a1e351-46fd-4b07-9fa3-a9d55fc08501",
      "record_type": "incident_report",
      "client_timestamp": "2026-09-22T14:15:00Z",
      "data": {
        "photo_url": "https://ik.imagekit.io/sih26002/offline/rock_01.jpg",
        "latitude": 26.115,
        "longitude": 91.835,
        "incident_type": "road_damage",
        "severity": "high",
        "description": "Deep fissure across carriage width"
      }
    },
    {
      "client_id": "c6a1e351-46fd-4b07-9fa3-a9d55fc08502",
      "record_type": "location_ping",
      "client_timestamp": "2026-09-22T14:16:00Z",
      "data": {
        "vehicle": 1,
        "latitude": 26.114,
        "longitude": 91.836,
        "speed": 18.5,
        "battery_level": 74
      }
    }
  ]
}
```
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "total": 2,
    "created": 2,
    "skipped": 0,
    "errors": 0,
    "results": [
      {
        "client_id": "c6a1e351-46fd-4b07-9fa3-a9d55fc08501",
        "status": "created",
        "server_id": 52
      },
      {
        "client_id": "c6a1e351-46fd-4b07-9fa3-a9d55fc08502",
        "status": "created",
        "server_id": 312
      }
    ]
  },
  "message": "Batch processed: 2 created, 0 skipped, 0 errors.",
  "status_code": 200
}
```

---

## 11. Phase 10: Dynamic District Accessibility Intelligence

Replaces static accessibility with dynamic multi-factor scoring (Roads 40%, Risk 30%, Connectivity 20%, Weather 10%).

### 11.1 Get District Accessibility Breakdown
* **Endpoint:** `GET /api/v1/routes/districts/<id>/accessibility/`
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "district_id": 1,
    "district_name": "Kamrup Metropolitan",
    "state": "Assam",
    "accessibility_score": 8.15,
    "components": {
      "road_condition_score": 8.8,
      "risk_score": 7.5,
      "connectivity_score": 10.0,
      "weather_score": 6.25
    },
    "weights": {
      "road_condition": 0.4,
      "risk": 0.3,
      "connectivity": 0.2,
      "weather": 0.1
    },
    "segment_count": 45,
    "blocked_count": 0
  }
}
```

### 11.2 Trigger Full Recomputation (Staff Only)
* **Endpoint:** `POST /api/v1/routes/districts/accessibility/refresh/`

---

## 12. Phase 11: Real-Time Operational Dashboard & Aggregations

Ultra-fast, read-only aggregation APIs for frontend executive monitoring dashboards.

### 12.1 High-Level KPI Summary
* **Endpoint:** `GET /api/v1/dashboard/summary/`
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "total_districts": 38,
    "average_accessibility_score": 7.92,
    "total_infrastructure_segments": 333,
    "blocked_segments_count": 3,
    "total_vehicles": 90,
    "active_trips": 12,
    "active_alerts_count": 4,
    "recent_incidents_24h": 8
  }
}
```

### 12.2 District Readiness & Risk Rollup
* **Endpoint:** `GET /api/v1/dashboard/districts/`

### 12.3 Fleet Telemetry Overview
* **Endpoint:** `GET /api/v1/dashboard/vehicles/`

### 12.4 Active Hazard & Disruption Alerts
* **Endpoint:** `GET /api/v1/dashboard/alerts/active/`

### 12.5 Critical Bottlenecks & Damaged Assets
* **Endpoint:** `GET /api/v1/dashboard/bottlenecks/`

### 12.6 Field Intelligence Hotspots
* **Endpoint:** `GET /api/v1/dashboard/intelligence/field/`

---

## 13. Phase 12: System Health & Root Status Endpoints

### 13.1 API Root Status & Navigation Map
* **Endpoint:** `GET /`
* **Access:** Public
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "service": "SIH26002 Backend",
    "tagline": "AI-Based Smart Logistics and Accessibility Intelligence Platform",
    "version": "v1.0.0",
    "status": "operational",
    "timestamp": "2026-09-22T17:15:00Z",
    "documentation": {
      "swagger_ui": "https://sih26002-backend-57w9.onrender.com/api/docs/",
      "redoc": "https://sih26002-backend-57w9.onrender.com/api/redoc/",
      "openapi_schema": "https://sih26002-backend-57w9.onrender.com/api/schema/"
    },
    "admin": "https://sih26002-backend-57w9.onrender.com/admin/",
    "health_check": "https://sih26002-backend-57w9.onrender.com/api/v1/health/",
    "endpoints_v1": {
      "auth": "https://sih26002-backend-57w9.onrender.com/api/v1/auth/",
      "accounts": "https://sih26002-backend-57w9.onrender.com/api/v1/accounts/",
      "routes": "https://sih26002-backend-57w9.onrender.com/api/v1/routes/",
      "reports": "https://sih26002-backend-57w9.onrender.com/api/v1/reports/",
      "vehicles": "https://sih26002-backend-57w9.onrender.com/api/v1/vehicles/",
      "trips": "https://sih26002-backend-57w9.onrender.com/api/v1/trips/",
      "alerts": "https://sih26002-backend-57w9.onrender.com/api/v1/alerts/",
      "sync": "https://sih26002-backend-57w9.onrender.com/api/v1/sync/",
      "dashboard": "https://sih26002-backend-57w9.onrender.com/api/v1/dashboard/"
    }
  },
  "message": "Welcome to SIH26002 Backend API.",
  "status_code": 200
}
```

### 13.2 Database & Service Health Check
* **Endpoint:** `GET /health/` (or `/api/v1/health/`)
* **Access:** Public
* **Response (`200 OK`):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "service": "SIH26002 Backend",
    "version": "v1.0.0",
    "phase": "Phase 12 - Production Ready",
    "database": "healthy",
    "timestamp": "2026-09-22T17:15:00Z"
  },
  "message": "System is operational.",
  "status_code": 200
}
```

---

## 14. Enum & Choice Values Reference

| Context | Enum Name | Allowed Values |
|---|---|---|
| User Roles | `Role` | `admin`, `field_officer`, `normal_user` |
| Incident Types | `IncidentType` | `landslide`, `flood`, `road_damage`, `obstruction`, `other` |
| Severity Levels | `SeverityLevel` | `low`, `medium`, `high`, `critical` |
| Road Status | `OperationalStatus` | `accessible`, `risky`, `blocked` |
| Physical Condition | `PhysicalCondition` | `good`, `moderate`, `poor`, `damaged` |
| Vehicle Types | `VehicleType` | `truck`, `van`, `emergency`, `car` |
| Trip Status | `TripStatus` | `created`, `on_route`, `delayed`, `at_risk`, `delivered` |
| Connectivity | `ConnectivityStatus` | `normal`, `degraded`, `critical` |
| Weather Condition | `WeatherCondition` | `clear`, `moderate`, `heavy`, `extreme` |
| Weather Warnings | `WarningLevel` | `green`, `yellow`, `orange`, `red` |
