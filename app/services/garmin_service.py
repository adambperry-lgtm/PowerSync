import ast
import datetime
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import requests

from app.database import get_current_user_id, get_db_connection, get_setting, set_setting
from app.services.outdoor_coach import decode_polyline
from app.services.strava_service import STRAVA_API_BASE, refresh_strava_token

# In-memory transient MFA state keyed by user_id (never shared across users)
_GARMIN_MFA_STATES: Dict[str, Any] = {}

SPORT_TO_GARMIN_ACTIVITY_TYPE = {
    "Ride": 10,              # Road Cycling
    "OutdoorRide": 10,
    "GravelRide": 145,       # Gravel / Unpaved Cycling
    "MountainBikeRide": 11,  # Mountain Biking
    "EBikeRide": 10,
}


def get_garmin_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    email = str(get_setting("garmin_email", "", user_id=uid) or "")
    has_pw = bool(get_setting("garmin_password", "", user_id=uid))
    tokens = str(get_setting("garmin_tokens", "", user_id=uid) or "")
    mfa_pending = uid in _GARMIN_MFA_STATES
    connected = bool(tokens or (email and has_pw))
    return {
        "connected": connected,
        "has_tokens": bool(tokens),
        "email": email,
        "mfa_pending": mfa_pending,
    }


def disconnect_garmin(user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    set_setting("garmin_tokens", "", user_id=uid)
    set_setting("garmin_password", "", user_id=uid)
    _GARMIN_MFA_STATES.pop(uid, None)
    return {"success": True, "connected": False}


def _get_garmin_client(user_id: Optional[str] = None):
    """
    Returns an authenticated garminconnect.Garmin client for `user_id`,
    preferring saved session tokens and falling back to stored credentials.
    """
    from garminconnect import Garmin

    uid = user_id or get_current_user_id()
    email = str(get_setting("garmin_email", "", user_id=uid) or "").strip()
    password = str(get_setting("garmin_password", "", user_id=uid) or "")
    saved_tokens = str(get_setting("garmin_tokens", "", user_id=uid) or "").strip()

    if saved_tokens:
        try:
            client = Garmin(email=email or None, password=password or None)
            client.login(tokenstore=saved_tokens)
            # Refresh persisted token dump in case DI token was refreshed
            try:
                refreshed = client.client.dumps()
                if refreshed and refreshed != saved_tokens:
                    set_setting("garmin_tokens", refreshed, user_id=uid)
            except Exception:
                pass
            return client
        except Exception:
            # Saved tokens expired or invalid; fall through to credential login if available
            pass

    if not email or not password:
        raise RuntimeError("Garmin Connect is not configured. Please connect your Garmin account in Settings (⚙️).")

    client = Garmin(email=email, password=password, return_on_mfa=True)
    mfa_status, client_state = client.login()
    if mfa_status == "needs_mfa":
        _GARMIN_MFA_STATES[uid] = {"client": client, "state": client_state}
        raise RuntimeError("GARMIN_MFA_REQUIRED")

    try:
        dumped = client.client.dumps()
        if dumped:
            set_setting("garmin_tokens", dumped, user_id=uid)
    except Exception:
        pass
    return client


def connect_garmin(
    email: Optional[str] = None,
    password: Optional[str] = None,
    mfa_code: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Authenticates with Garmin Connect and stores session tokens scoped by `user_id`.
    Supports 2-step MFA completion when `mfa_code` is provided.
    """
    from garminconnect import Garmin

    uid = user_id or get_current_user_id()

    if mfa_code and mfa_code.strip():
        pending = _GARMIN_MFA_STATES.get(uid)
        if not pending:
            return {"success": False, "error": "No pending Garmin MFA challenge. Please click Connect Garmin again."}
        try:
            client = pending["client"]
            client.resume_login(pending["state"], mfa_code.strip())
            _GARMIN_MFA_STATES.pop(uid, None)
            dumped = client.client.dumps()
            if dumped:
                set_setting("garmin_tokens", dumped, user_id=uid)
            return {
                "success": True,
                "connected": True,
                "email": str(get_setting("garmin_email", "", user_id=uid) or ""),
                "message": "Garmin Connect linked successfully!",
            }
        except Exception as e:
            return {"success": False, "error": f"Garmin MFA verification failed: {str(e)}"}

    clean_email = (email or get_setting("garmin_email", "", user_id=uid) or "").strip()
    clean_pw = password if (password and "•" not in password and "\u2022" not in password) else str(get_setting("garmin_password", "", user_id=uid) or "")

    if not clean_email or not clean_pw:
        return {"success": False, "error": "Garmin Connect email and password are required."}

    set_setting("garmin_email", clean_email, user_id=uid)
    set_setting("garmin_password", clean_pw, user_id=uid)

    try:
        client = Garmin(email=clean_email, password=clean_pw, return_on_mfa=True)
        mfa_status, client_state = client.login()
        if mfa_status == "needs_mfa":
            _GARMIN_MFA_STATES[uid] = {"client": client, "state": client_state}
            return {
                "success": False,
                "mfa_required": True,
                "error": "Garmin Connect requires a 2FA verification code. Enter the code sent to your email/authenticator and click Verify.",
            }

        dumped = client.client.dumps()
        if dumped:
            set_setting("garmin_tokens", dumped, user_id=uid)
        _GARMIN_MFA_STATES.pop(uid, None)
        return {
            "success": True,
            "connected": True,
            "email": clean_email,
            "message": f"Connected to Garmin Connect as {clean_email}!",
        }
    except Exception as e:
        return {"success": False, "error": f"Garmin Connect login failed: {str(e)}"}


def generate_gpx_from_points(
    name: str,
    coords: List[List[float]],
    elevations: Optional[List[float]] = None,
    sport_type: str = "Ride",
) -> str:
    """
    Builds a clean GPX 1.1 XML string from [[lat, lng], ...] and optional elevation meters.
    """
    gpx = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "PowerSync",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )
    meta = ET.SubElement(gpx, "metadata")
    ET.SubElement(meta, "name").text = name or "PowerSync Route"
    ET.SubElement(meta, "time").text = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = name or "PowerSync Route"
    ET.SubElement(trk, "type").text = sport_type or "cycling"
    trkseg = ET.SubElement(trk, "trkseg")

    has_ele = elevations is not None and len(elevations) == len(coords)
    for idx, pt in enumerate(coords):
        if not pt or len(pt) < 2:
            continue
        lat, lon = float(pt[0]), float(pt[1])
        trkpt = ET.SubElement(trkseg, "trkpt", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"})
        if has_ele and elevations[idx] is not None:
            ET.SubElement(trkpt, "ele").text = f"{float(elevations[idx]):.1f}"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(gpx, encoding="unicode")


def _fetch_strava_latlng_altitude(activity_id: str, user_id: str) -> Dict[str, Any]:
    """Fetches high-resolution GPS latlng and altitude streams from Strava if connected."""
    tokens = get_setting("strava_tokens", {}, user_id=user_id)
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not access_token or not str(activity_id).isdigit():
        return {}

    url = f"{STRAVA_API_BASE}/activities/{activity_id}/streams?keys=latlng,altitude&key_by_type=true"
    try:
        res = requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if res.status_code == 401:
            new_tok = refresh_strava_token(user_id=user_id)
            if new_tok:
                res = requests.get(url, headers={"Authorization": f"Bearer {new_tok}"}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                return {
                    "latlng": data.get("latlng", {}).get("data", []),
                    "altitude": data.get("altitude", {}).get("data", []),
                }
    except Exception:
        pass
    return {}


def fetch_activity_gpx_data(activity_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolves a prior outdoor ride from `strava_activities` and builds a GPX 1.1 payload,
    upgrading to high-res Strava GPS/altitude streams when available.
    """
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, name, sport_type, distance_meters, total_elevation_gain, raw_json
        FROM strava_activities
        WHERE user_id = ? AND id = ?
        """,
        (uid, str(activity_id)),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": "Outdoor ride not found in your synced history."}

    ride = dict(row)
    name = ride.get("name") or "PowerSync Route"
    sport_type = ride.get("sport_type") or "Ride"

    # 1. Try high-res Strava streams first
    stream_data = _fetch_strava_latlng_altitude(str(activity_id), uid)
    coords = stream_data.get("latlng") or []
    elevations = stream_data.get("altitude") or None

    # 2. Fall back to stored summary_polyline in raw_json
    if not coords:
        raw = ride.get("raw_json")
        poly = ""
        if raw:
            raw_d = None
            try:
                raw_d = json.loads(raw)
            except Exception:
                try:
                    raw_d = ast.literal_eval(raw)
                except Exception:
                    raw_d = None
            if isinstance(raw_d, dict):
                poly = raw_d.get("map", {}).get("summary_polyline") or ""
        coords = decode_polyline(poly)
        elevations = None

    if not coords or len(coords) < 2:
        return {"success": False, "error": "This ride does not contain GPS route coordinates."}

    gpx_xml = generate_gpx_from_points(name=name, coords=coords, elevations=elevations, sport_type=sport_type)
    return {
        "success": True,
        "id": str(activity_id),
        "name": name,
        "sport_type": sport_type,
        "point_count": len(coords),
        "high_res": bool(stream_data.get("latlng")),
        "gpx_xml": gpx_xml,
    }


def push_course_to_garmin(
    course_name: str,
    gpx_xml: str,
    sport_type: str = "Ride",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Imports a GPX route into Garmin Connect and saves it as a Course in the user's
    Garmin Connect Courses library so it syncs directly to their Garmin Edge/Forerunner.
    """
    uid = user_id or get_current_user_id()
    if not gpx_xml or "<trkpt" not in gpx_xml:
        return {"success": False, "error": "Invalid or empty GPX route data."}

    try:
        client = _get_garmin_client(user_id=uid)
    except RuntimeError as auth_err:
        msg = str(auth_err)
        if msg == "GARMIN_MFA_REQUIRED":
            return {
                "success": False,
                "mfa_required": True,
                "error": "Garmin Connect requires 2FA verification. Open Settings (⚙️) → Garmin Connect to enter your verification code.",
            }
        return {"success": False, "error": msg}
    except Exception as e:
        return {"success": False, "error": f"Garmin authentication failed: {str(e)}"}

    safe_filename = re.sub(r"[^A-Za-z0-9_-]+", "_", course_name or "PowerSync_Route").strip("_") or "PowerSync_Route"
    filename = f"{safe_filename}.gpx"

    try:
        # Step 1: Import GPX into Garmin Connect course parser
        files = {"file": (filename, gpx_xml.encode("utf-8"), "application/gpx+xml")}
        imported = client.client.post(
            "connectapi",
            "/course-service/course/import",
            files=files,
            api=True,
        )
        if not isinstance(imported, dict):
            return {"success": False, "error": "Garmin Connect returned an unexpected response during GPX import."}

        activity_type_pk = SPORT_TO_GARMIN_ACTIVITY_TYPE.get(sport_type, 10)
        geo_points = imported.get("geoPoints") or []
        if not geo_points:
            return {"success": False, "error": "Garmin Connect could not parse GPS points from this route."}

        course_payload = {
            "courseName": (course_name or imported.get("courseName") or "PowerSync Route")[:100],
            "activityTypePk": activity_type_pk,
            "coordinateSystem": imported.get("coordinateSystem") or "WGS84",
            "distanceMeter": imported.get("distanceMeter"),
            "elevationGainMeter": imported.get("elevationGainMeter"),
            "elevationLossMeter": imported.get("elevationLossMeter"),
            "geoPoints": geo_points,
            "boundingBox": imported.get("boundingBox"),
            "sourceTypeId": 3,
            "rulePK": 2,  # Private course
            "openStreetMap": False,
            "hasTurnDetection": imported.get("hasTurnDetection", True),
            "courseLines": imported.get("courseLines") or [],
        }

        # Step 2: Persist course to Garmin Connect Courses
        created = client.client.post(
            "connectapi",
            "/course-service/course",
            json=course_payload,
            api=True,
        )
        course_id = created.get("courseId") if isinstance(created, dict) else None
        course_url = f"https://connect.garmin.com/modern/course/{course_id}" if course_id else "https://connect.garmin.com/modern/courses"

        return {
            "success": True,
            "course_id": course_id,
            "course_url": course_url,
            "message": f"Sent '{course_payload['courseName']}' to Garmin Connect Courses! Sync your Garmin device to ride it.",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to push route to Garmin Connect: {str(e)}"}
