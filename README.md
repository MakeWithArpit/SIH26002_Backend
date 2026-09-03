# SIH26002 — AI-Based Smart Logistics & Accessibility Intelligence Platform

Backend engine for the North Eastern Region (NER) Smart Logistics and Accessibility Intelligence Platform (Smart India Hackathon 2026).

---

## 📌 Project Overview

The North Eastern Region of India faces severe logistics and accessibility bottlenecks due to hilly terrain, severe monsoons, and recurring disruptions (landslides, flash floods, bridge washouts, and road collapses). Delivering critical supplies—such as emergency medicines, food, and construction materials—to remote districts often suffers from unpredictable delays and zero real-time operational visibility.

This project delivers an integrated, AI-driven backend platform that converts raw field intelligence, weather data, and road conditions into proactive routing and disruption management.

---

## 🚀 Core Capabilities

1. **Field Intelligence & Photo Analysis (Vision AI)**
   - Accepts geo-tagged field reports and ground photos from Field Officers.
   - Automatically detects and classifies road disruptions (flooding, landslides, structural damage) and severity.

2. **Infrastructure Disruption Risk Prediction**
   - Continuously evaluates road and bridge vulnerability using weather data, historical trends, and real-time field reports.
   - Generates dynamic risk scores and disruption probabilities per transit corridor.

3. **Risk-Aware Route Optimization & Ranking**
   - Generates candidate transport routes between origins and destinations.
   - Evaluates alternative corridors using safety, road condition, accessibility scores, and live risk metrics to recommend optimal routes.

4. **Dynamic ETA & Delay Estimation**
   - Ingests GPS tracking pings from driver mobile applications.
   - Predicts accurate arrival times and flags delivery delays proactively.

5. **Automated Alerts & Multilingual Notifications**
   - Dispatches actionable operational alerts for blocked passages, critical risks, and delayed supply convoys.

6. **Offline Synchronization**
   - Built-in batch sync ensuring field officers and drivers can capture reports and location pings even in zero-connectivity remote zones.

---

## 🛠️ Tech Stack

- **Backend:** Python, Django, Django REST Framework
- **Spatial Database:** PostgreSQL with PostGIS extension (GeoDjango)
- **Intelligence Layer:** In-process AI/ML models (Random Forest, Computer Vision wrappers)
- **Task Queue & Cache:** Celery, Celery Beat, Redis
- **Authentication:** JWT (SimpleJWT) with Role-Based Access Control (Admin, Field Officer, Normal User)
- **API Spec:** OpenAPI 3.0 via `drf-spectacular`
