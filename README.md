# SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform

> **Smart India Hackathon (SIH)**  
> **Backend Engine for North Eastern Region (NER) Multi-State Corridors**  
> **Live Production Deployment (Render):** [https://sih26002-backend-57w9.onrender.com](https://sih26002-backend-57w9.onrender.com)  
> **Interactive Swagger Documentation:** [https://sih26002-backend-57w9.onrender.com/api/docs/](https://sih26002-backend-57w9.onrender.com/api/docs/)  
> **Status:** **100% Completed (Phases 0–12 Production Ready)**  

---

## 📌 Project Overview

The North Eastern Region of India faces severe logistics and accessibility bottlenecks due to hilly terrain, severe monsoons, and recurring disruptions (landslides, flash floods, bridge washouts, and road collapses). Delivering critical supplies—such as emergency medicines, food, and construction materials—to remote districts often suffers from unpredictable delays and zero real-time operational visibility.

This project delivers an integrated, AI-driven backend platform that converts raw field intelligence, live weather data, and road conditions into proactive routing, dynamic risk scoring, and real-time disruption management.

---

## 🚀 Core Capabilities

1. **Field Intelligence & Photo Analysis (Vision AI)**
   - Accepts geo-tagged field reports and ground photos from Field Officers.
   - Snaps coordinates to the nearest road segment via PostGIS (`ST_DWithin`).
   - Automatically detects and classifies road disruptions (flooding, landslides, structural damage) and severity.

2. **Infrastructure Disruption Risk Prediction**
   - Continuously evaluates road and bridge vulnerability using multi-factor scoring (rainfall, landslide susceptibility, IMD warnings, damage).
   - Generates dynamic risk scores (0–100) and disruption probabilities per transit corridor.

3. **Risk-Aware Route Optimization & Ranking**
   - Generates candidate transport routes between origins and destinations using NetworkX graph pathfinding.
   - Evaluates alternative corridors using safety, road condition, accessibility scores, and live risk metrics to recommend optimal routes.

4. **Dynamic ETA & Delay Estimation**
   - Ingests GPS tracking pings from driver mobile applications.
   - Predicts condition-aware arrival times and flags delivery delays proactively.

5. **Automated Alerts & Operational Intelligence**
   - Dispatches actionable operational alerts for blocked passages, critical risks, and delayed supply convoys.

6. **Offline Resilient Synchronization**
   - Built-in idempotent batch sync (`POST /api/v1/sync/batch/`) ensuring field officers and drivers can capture reports and location pings in zero-connectivity remote zones.

7. **Dynamic Accessibility Intelligence**
   - Multi-factor district accessibility scoring (Roads 40%, Risk 30%, Connectivity 20%, Weather 10%).

8. **Executive Dashboard Aggregation Engine**
   - Ultra-fast read-only aggregation APIs for real-time monitoring of districts, fleet telemetry, active alerts, and bottlenecks.

9. **Automated Role Management & Production Hardening**
   - Built-in auto-sync for user roles (Admin, Field Officer, Normal User).
   - Inlined role editor inside Django Admin.
   - Real database health probes (`/health/`) and OpenAPI 3.0 docs.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.12, Django 5.x, Django REST Framework 3.15+
- **Spatial Database:** PostgreSQL 16 with PostGIS 3.4 extension (GeoDjango)
- **Graph & Algorithms:** NetworkX 3.x, OSMnx 1.9+, Dijkstra pathfinding
- **Task Queue & Cache:** Celery, Celery Beat, Redis 7
- **Authentication:** JWT (SimpleJWT) with Role-Based Access Control (Admin, Field Officer, Normal User)
- **API Spec & Docs:** OpenAPI 3.0 via `drf-spectacular` (Swagger UI & ReDoc)
- **Deployment:** Docker, Gunicorn, Render.com

---

## 🔑 Demo Credentials

| Role | Username | Password | Access Level |
|---|---|---|---|
| **Admin** | `admin_arpit` | `Password123!` | Full System, Django Admin (`/admin/`), User Management |
| **Field Officer** | `fo_rahul` | `Password123!` | Incident Submissions, Offline Batch Sync |
| **Driver / User** | `driver_biren` | `Password123!` | Telemetry Streaming, Trips, Route Queries |

---

## 📚 Documentation Links

- [Complete API Documentation (Phases 0–12)](file:///d:/Anti/SIH26002_Backend/projectInformation/FRONTEND_API_DOCUMENTATION.md)
- [Comprehensive Backend Progress Report](file:///d:/Anti/SIH26002_Backend/projectInformation/BACKEND_PROGRESS_REPORT.md)
- [Architecture Design Document](file:///d:/Anti/SIH26002_Backend/projectInformation/architecture.md)
- [Phased Implementation Guide](file:///d:/Anti/SIH26002_Backend/projectInformation/phases.md)
- [Dummy Data & Credentials Guide](file:///d:/Anti/SIH26002_Backend/projectInformation/DUMMY_DATA_CREDENTIALS.md)

---

## ⚡ Quick Start (Docker)

```bash
# Clone the repository
git clone https://github.com/MakeWithArpit/SIH26002_Backend.git
cd SIH26002_Backend

# Start containers
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate

# Seed dummy data
docker compose exec web python manage.py seed_dummy_data

# Synchronize user roles
docker compose exec web python manage.py assign_user_roles

# Run test suite
docker compose exec web python manage.py test --keepdb apps.accounts.test_phase12_roles
```
