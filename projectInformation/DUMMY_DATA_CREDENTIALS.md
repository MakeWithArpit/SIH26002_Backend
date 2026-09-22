# SIH26002 Backend — Dummy Data Credentials & Summary

> Generated: 2026-09-22  
> Command: `python manage.py seed_dummy_data`

---

## Login Credentials

### Admin Users
| Username | Password | Role | Department |
|----------|----------|------|------------|
| admin_arpit | Password123! | Admin | PWD |
| admin_raj | Password123! | Admin | PWD |
| admin_akash | Password123! | Admin | PWD |

### Field Officers
| Username | Password | Role | Department |
|----------|----------|------|------------|
| fo_rahul | Password123! | Field Officer | PWD Assam |
| fo_priya | Password123! | Field Officer | PWD Assam |
| fo_amit | Password123! | Field Officer | PWD Meghalaya |
| fo_sonia | Password123! | Field Officer | PWD Assam |
| fo_rajesh | Password123! | Field Officer | PWD Meghalaya |
| fo_anita | Password123! | Field Officer | PWD Assam |
| fo_vikram | Password123! | Field Officer | PWD Meghalaya |
| fo_megha | Password123! | Field Officer | PWD Assam |
| fo_dipak | Password123! | Field Officer | PWD Meghalaya |

### Normal Users / Drivers
| Username | Password | Role |
|----------|----------|------|
| driver_biren | Password123! | Normal User |
| driver_gautam | Password123! | Normal User |
| driver_hiren | Password123! | Normal User |
| driver_ismail | Password123! | Normal User |
| driver_jatin | Password123! | Normal User |
| driver_kamal | Password123! | Normal User |
| driver_lalit | Password123! | Normal User |
| driver_mohan | Password123! | Normal User |
| driver_nazir | Password123! | Normal User |
| driver_ojhar | Password123! | Normal User |

(Plus 30+ more drivers: driver_pankaj through driver_satish)

---

## Data Summary

### Current Database Records

| Model | Count | Description |
|-------|-------|-------------|
| **Districts** | 38 | All NER states: Assam (20), Meghalaya (8), Arunachal (4), Nagaland (4), Manipur (4), Tripura (4), Sikkim (4) |
| **Infrastructure** | 333+ | Roads, bridges, culverts across all districts with risk scores |
| **WeatherSnapshots** | 260+ | Multiple snapshots per district (rainfall, temperature, humidity) |
| **Vehicles** | 90+ | Trucks, vans, cars, emergency vehicles |
| **LocationPings** | 270+ | Historical GPS telemetry |
| **Trips** | 30+ | Active, delayed, and completed trips |
| **IncidentReports** | 50+ | Field reports with photos, severity, AI analysis |

---

## Sample Coordinates (NER Corridor)

### Guwahati → Shillong (NH-06)
- **Guwahati (Origin)**: 26.1833°N, 91.7500°E
- **Jorabat**: 26.1030°N, 91.8650°E
- **Nongpoh**: 25.9015°N, 91.8780°E
- **Umiam Lake**: 25.6680°N, 91.9050°E
- **Shillong (Destination)**: 25.5788°N, 91.8933°E

---

## How to Use

### 1. Login to Admin Panel
```
URL: http://localhost:8000/admin/
Username: admin_arpit
Password: Password123!
```

### 2. Access API with JWT
```bash
# Get token
curl -X POST http://localhost:8000/api/v1/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin_arpit", "password": "Password123!"}'

# Use token
curl http://localhost:8000/api/v1/routes/districts/ \
  -H "Authorization: Bearer <access_token>"
```

### 3. Test Endpoints
- `POST /api/v1/accounts/login/` — Get JWT token
- `GET /api/v1/routes/districts/` — List all districts
- `GET /api/v1/routes/infrastructure/` — List roads/bridges
- `GET /api/v1/vehicles/` — List fleet vehicles
- `GET /api/v1/trips/` — List trips
- `GET /api/v1/reports/incidents/` — List incident reports
- `GET /api/v1/routes/alerts/` — Get active alerts

---

## Quick Test Scripts

### Test Authentication
```python
import requests

url = "http://localhost:8000/api/v1/accounts/login/"
data = {"username": "admin_arpit", "password": "Password123!"}
response = requests.post(url, json=data)
token = response.json()['data']['access']
print(f"Token: {token[:20]}...")
```

### Test Vehicle Tracking
```python
import requests

token = "<your_token>"
headers = {"Authorization": f"Bearer {token}"}

# Get vehicles
r = requests.get("http://localhost:8000/api/v1/vehicles/", headers=headers)
print(f"Vehicles: {len(r.json()['data'])}")

# Get latest location
vehicle_id = 1
r = requests.get(f"http://localhost:8000/api/v1/vehicles/{vehicle_id}/location/latest/", headers=headers)
print(f"Location: {r.json()['data']}")
```

---

## Notes

- All users have password: `Password123!`
- Field reports use ImageKit CDN URLs (placeholder images)
- Risk scores are randomized (0-100) with risk levels (low/medium/high)
- Weather data includes realistic rainfall (0-120mm) and temperature (18-35°C)
- Trips have various statuses: created, on_route, delayed, delivered

---

**Last Updated:** 2026-09-22