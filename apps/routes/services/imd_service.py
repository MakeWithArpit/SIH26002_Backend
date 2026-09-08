"""
IMD (India Meteorological Department) District-wise Warning Service.

Fetches and normalizes district-wise weather warnings from the official
IMD District Warning API for the configured Northeast India corridor districts.
Decoupled entirely from route calculation, risk engine, and road disruption intelligence.
"""
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Official IMD Warning Code Mapping
IMD_WARNING_LABELS = {
    1: "No Warning",
    2: "Heavy Rain",
    3: "Heavy Snow",
    4: "Thunderstorm & Lightning",
    5: "Hailstorm",
    6: "Dust Storm",
    7: "Dust Raising Winds",
    8: "Strong Surface Winds",
    9: "Heat Wave",
    10: "Hot Day",
    11: "Warm Night",
    12: "Cold Wave",
    13: "Cold Day",
    14: "Ground Frost",
    15: "Fog",
    16: "Very Heavy Rain",
    17: "Extremely Heavy Rain",
}

# Official IMD Color Code to UI Severity Mapping
# 1 = Red -> High, 2 = Orange -> Medium, 3 = Yellow -> Low, 4 = Green -> Low
IMD_COLOR_SEVERITY = {
    1: {"severity": "High", "label": "HIGH", "type": "high", "color_name": "Red"},
    2: {"severity": "Medium", "label": "MEDIUM", "type": "medium", "color_name": "Orange"},
    3: {"severity": "Low", "label": "LOW", "type": "low", "color_name": "Yellow"},
    4: {"severity": "Low", "label": "LOW", "type": "low", "color_name": "Green"},
}

DEFAULT_COLOR_INFO = {"severity": "Low", "label": "LOW", "type": "low", "color_name": "Green"}

# Configured Northeast Region (NER) Pilot Corridor Districts
DEFAULT_NER_DISTRICTS = {
    "east khasi hills": {"name": "East Khasi Hills", "state": "Meghalaya"},
    "ri bhoi": {"name": "Ri-Bhoi", "state": "Meghalaya"},
    "ri-bhoi": {"name": "Ri-Bhoi", "state": "Meghalaya"},
    "kamrup metropolitan": {"name": "Kamrup Metropolitan", "state": "Assam"},
    "kamrup metro": {"name": "Kamrup Metropolitan", "state": "Assam"},
    "kamrup test": {"name": "Kamrup Metropolitan", "state": "Assam"},
    "kamrup": {"name": "Kamrup Metropolitan", "state": "Assam"},
    "karbi anglong": {"name": "Karbi Anglong", "state": "Assam"},
    "morigaon": {"name": "Morigaon", "state": "Assam"},
    "nagaon": {"name": "Nagaon", "state": "Assam"},
    "dimapur": {"name": "Dimapur", "state": "Nagaland"},
    "kohima": {"name": "Kohima", "state": "Nagaland"},
    "sonitpur": {"name": "Sonitpur", "state": "Assam"},
    "cachar": {"name": "Cachar", "state": "Assam"},
    "papum pare": {"name": "Papum Pare", "state": "Arunachal Pradesh"},
    "imphal west": {"name": "Imphal West", "state": "Manipur"},
    "imphal east": {"name": "Imphal East", "state": "Manipur"},
    "aizawl": {"name": "Aizawl", "state": "Mizoram"},
}

CACHE_KEY_DATA = "imd_live_district_warnings"
CACHE_KEY_TIME = "imd_live_district_warnings_timestamp"
CACHE_KEY_STALE_DATA = "imd_stale_district_warnings"
CACHE_KEY_STALE_TIME = "imd_stale_district_warnings_timestamp"


def normalize_string(val: str) -> str:
    """Normalize district names for fuzzy matching."""
    if not val:
        return ""
    val = unicodedata.normalize("NFKD", str(val))
    val = re.sub(r"[^\w\s]", " ", val)
    val = re.sub(r"\s+", " ", val).strip().lower()
    return val


def get_warning_icon(warning_code: int) -> str:
    """Returns an intuitive emoji icon for weather warning cards."""
    if warning_code in (2, 16, 17):
        return "🌧️"
    if warning_code == 3:
        return "❄️"
    if warning_code == 4:
        return "⛈️"
    if warning_code == 5:
        return "🌨️"
    if warning_code in (6, 7, 8):
        return "💨"
    if warning_code in (9, 10, 11):
        return "☀️"
    if warning_code in (12, 13, 14):
        return "🥶"
    if warning_code == 15:
        return "🌫️"
    return "⚠️"


def parse_warning_codes(raw_val: Any) -> List[int]:
    """
    Parses warning codes from Day_N fields.
    Supports integers, floats, lists, and comma-separated strings (e.g. '2,4').
    Filters out code 1 ('No Warning') and invalid values.
    """
    if raw_val is None:
        return []
    
    if isinstance(raw_val, (int, float)):
        c = int(raw_val)
        return [c] if c > 1 else []
    
    if isinstance(raw_val, list):
        results = []
        for item in raw_val:
            try:
                c = int(str(item).strip())
                if c > 1 and c not in results:
                    results.append(c)
            except (ValueError, TypeError):
                continue
        return results

    results = []
    # Comma-separated string case
    for part in str(raw_val).replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            c = int(part)
            if c > 1 and c not in results:
                results.append(c)
    return results


class IMDWarningService:
    """
    Client service for fetching and normalizing IMD district warnings.
    """

    @classmethod
    def get_monitored_districts(cls) -> Dict[str, Dict[str, str]]:
        """
        Builds dictionary of monitored NER districts by merging database
        districts with the fallback corridor registry.
        """
        registry = dict(DEFAULT_NER_DISTRICTS)
        try:
            from apps.routes.models import District
            for d in District.objects.all():
                norm = normalize_string(d.name)
                if norm:
                    registry[norm] = {"name": d.name, "state": d.state}
        except Exception as e:
            logger.debug("Could not load District models for IMD filtering: %s", e)
        return registry

    @classmethod
    def match_district(cls, raw_district_name: str, monitored: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
        """
        Matches an IMD district name against monitored NER districts.
        """
        clean_raw = normalize_string(raw_district_name)
        if not clean_raw:
            return None

        # 1. Exact match
        if clean_raw in monitored:
            return monitored[clean_raw]

        # 2. Substring or token match
        for key, info in monitored.items():
            if key in clean_raw or clean_raw in key:
                return info

        return None

    @classmethod
    def normalize_records(cls, raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transforms raw IMD district warning records into frontend-ready alert items.
        Only generates alerts for warning codes > 1.
        Preserves original IMD codes, colors, UTC time, and issue date.
        """
        monitored = cls.get_monitored_districts()
        alerts = []

        for record in raw_records:
            if not isinstance(record, dict):
                continue

            raw_district = (
                record.get("District")
                or record.get("district")
                or record.get("district_name")
                or record.get("District_Name")
                or ""
            )

            match_info = cls.match_district(raw_district, monitored)
            if not match_info:
                # District is outside the monitored NER pilot region
                continue

            district_name = match_info["name"]
            state_name = match_info["state"]
            obj_id = str(record.get("Obj_id") or record.get("obj_id") or "")
            issue_date = str(record.get("Date") or record.get("date") or "")
            issue_time_utc = str(record.get("UTC") or record.get("utc") or "")

            # Check Day_1 through Day_5
            for day_idx in range(1, 6):
                day_key = f"Day_{day_idx}"
                color_key = f"Day{day_idx}_Color"

                raw_codes = record.get(day_key)
                if raw_codes is None:
                    raw_codes = record.get(day_key.lower()) or record.get(f"day_{day_idx}")

                warning_codes = parse_warning_codes(raw_codes)
                if not warning_codes:
                    # Code 1 (No warning) or empty
                    continue

                raw_color = record.get(color_key)
                if raw_color is None:
                    raw_color = record.get(color_key.lower()) or record.get(f"day{day_idx}_color")

                try:
                    color_code = int(raw_color) if raw_color is not None else 4
                except (ValueError, TypeError):
                    color_code = 4

                color_info = IMD_COLOR_SEVERITY.get(color_code, DEFAULT_COLOR_INFO)

                applicable_list = [
                    {
                        "warning_code": c,
                        "warning_type": IMD_WARNING_LABELS.get(c, f"Weather Warning ({c})"),
                        "icon": get_warning_icon(c),
                    }
                    for c in warning_codes
                ]

                # Generate an alert entry for each active warning code on this day
                for code in warning_codes:
                    warning_type = IMD_WARNING_LABELS.get(code, f"Weather Warning (Code {code})")
                    slug_dist = re.sub(r"[^\w]+", "-", district_name.lower()).strip("-")
                    alert_id = f"imd-{slug_dist or obj_id}-d{day_idx}-c{code}"

                    alert_item = {
                        "id": alert_id,
                        "obj_id": obj_id,
                        "district": district_name,
                        "state": state_name,
                        "location": f"{district_name}, {state_name}" if state_name else district_name,
                        "warning_type": warning_type,
                        "warning_code": code,
                        "day": f"Day {day_idx}",
                        "day_index": day_idx,
                        "issue_date": issue_date,
                        "issue_time": issue_time_utc,
                        "color_code": color_code,
                        "color_name": color_info["color_name"],
                        "severity": color_info["severity"],
                        "severity_label": color_info["label"],
                        "type": color_info["type"],
                        "icon": get_warning_icon(code),
                        "title": warning_type,
                        "message": f"{warning_type} warning issued for {district_name}. Day {day_idx} warning.",
                        "description": f"{warning_type} warning issued for the district.",
                        "source": "IMD",
                        "source_name": "India Meteorological Department",
                        "applicable_warnings": applicable_list,
                    }
                    alerts.append(alert_item)

        # Sort alerts: High severity first, then by day, then by district
        severity_priority = {"High": 0, "Medium": 1, "Low": 2}
        alerts.sort(key=lambda a: (severity_priority.get(a["severity"], 3), a["day_index"], a["district"]))
        return alerts

    @classmethod
    def fetch_warnings(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches live warning data from IMD District Warning API.
        Applies caching and returns normalized alerts or structured error response.
        """
        ttl = getattr(settings, "IMD_CACHE_TTL_SECONDS", 600)
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # 1. Return fresh cached data if available
        if not force_refresh:
            cached_data = cache.get(CACHE_KEY_DATA)
            cached_time = cache.get(CACHE_KEY_TIME)
            if cached_data is not None:
                return {
                    "success": True,
                    "alerts": cached_data,
                    "total": len(cached_data),
                    "last_updated": cached_time or now_iso,
                    "cached": False,
                    "source": "India Meteorological Department (IMD)",
                }

        # 2. Attempt authenticated request to IMD API
        url = getattr(settings, "IMD_DISTRICT_WARNING_URL", "https://api.imd.gov.in/api/v1/districtwarning")
        api_key = getattr(settings, "IMD_API_KEY", "")
        api_token = getattr(settings, "IMD_API_TOKEN", "")
        timeout = getattr(settings, "IMD_TIMEOUT_SECONDS", 10.0)

        headers = {
            "User-Agent": "SIH26-NER-Logistics/1.0",
            "Accept": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        raw_records = None
        fetch_error_msg = None
        status_code = None

        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            status_code = response.status_code
            if response.status_code == 200:
                raw_json = response.json()
                if isinstance(raw_json, list):
                    raw_records = raw_json
                elif isinstance(raw_json, dict) and "data" in raw_json and isinstance(raw_json["data"], list):
                    raw_records = raw_json["data"]
                elif isinstance(raw_json, dict):
                    raw_records = [raw_json]
            else:
                fetch_error_msg = f"IMD API returned HTTP {response.status_code}"
                logger.warning("IMD District Warning API failure (%s): %s", response.status_code, response.text[:200])
        except requests.exceptions.Timeout:
            fetch_error_msg = "IMD API request timed out."
            logger.warning("IMD API request timed out.")
        except requests.exceptions.RequestException as req_err:
            fetch_error_msg = f"IMD network error: {req_err}"
            logger.warning("IMD network connection error: %s", req_err)
        except Exception as e:
            fetch_error_msg = f"Unexpected error during IMD warning fetch: {e}"
            logger.exception("Unexpected error fetching IMD warnings: %s", e)

        # 3. Successful fetch
        if raw_records is not None:
            normalized_alerts = cls.normalize_records(raw_records)
            cache.set(CACHE_KEY_DATA, normalized_alerts, timeout=ttl)
            cache.set(CACHE_KEY_TIME, now_iso, timeout=ttl)
            # Maintain persistent stale cache for resilient fallback
            cache.set(CACHE_KEY_STALE_DATA, normalized_alerts, timeout=86400)
            cache.set(CACHE_KEY_STALE_TIME, now_iso, timeout=86400)

            return {
                "success": True,
                "alerts": normalized_alerts,
                "total": len(normalized_alerts),
                "last_updated": now_iso,
                "cached": False,
                "source": "India Meteorological Department (IMD)",
            }

        # 4. Failed fetch: Check if stale cache exists
        stale_data = cache.get(CACHE_KEY_STALE_DATA)
        stale_time = cache.get(CACHE_KEY_STALE_TIME)
        if stale_data is not None:
            return {
                "success": True,
                "alerts": stale_data,
                "total": len(stale_data),
                "last_updated": stale_time,
                "cached": True,
                "warning": "Live IMD API unavailable. Displaying cached warnings.",
                "source": "India Meteorological Department (IMD)",
            }

        # 5. No cache available -> explicit error response
        return {
            "success": False,
            "alerts": [],
            "total": 0,
            "last_updated": None,
            "cached": False,
            "source": "India Meteorological Department (IMD)",
            "error": {
                "code": "IMD_API_UNAVAILABLE",
                "message": "Unable to load live IMD alerts",
                "detail": fetch_error_msg,
                "status_code": status_code,
            },
        }
