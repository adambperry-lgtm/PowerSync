import sqlite3
import json
import os
from typing import Dict, Any, Optional, List

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fitness.db")

def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Whoop daily metrics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS whoop_metrics (
        date TEXT PRIMARY KEY,
        recovery_score INTEGER,
        hrv_rmssd REAL,
        resting_heart_rate INTEGER,
        sleep_performance INTEGER,
        sleep_duration_hours REAL,
        day_strain REAL,
        raw_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Strava activities table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS strava_activities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        sport_type TEXT NOT NULL,
        start_date TEXT NOT NULL,
        elapsed_time_sec INTEGER,
        moving_time_sec INTEGER,
        distance_meters REAL,
        total_elevation_gain REAL,
        average_watts REAL,
        weighted_average_watts REAL,
        average_heartrate REAL,
        max_heartrate REAL,
        suffer_score REAL,
        kilojoules REAL,
        raw_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Workouts generated / prescribed
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workouts (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        focus_area TEXT,
        duration_minutes INTEGER NOT NULL,
        estimated_tss INTEGER,
        intervals_json TEXT NOT NULL,
        zwo_content TEXT,
        intervals_icu_text TEXT,
        ai_rationale TEXT,
        status TEXT DEFAULT 'suggested',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Target / upcoming plans table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS target_plans (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        target_date TEXT NOT NULL,
        description TEXT,
        distance_miles REAL,
        elevation_gain_ft REAL,
        estimated_duration_min INTEGER,
        estimated_tss INTEGER,
        intensity_type TEXT DEFAULT 'Endurance',
        route_source TEXT DEFAULT 'manual',
        strava_id TEXT,
        summary_polyline TEXT,
        svg_path TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def get_setting(key: str, default: Any = None) -> Any:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row["value"] is not None and str(row["value"]).strip() != "":
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    
    # Cloud / Environment fallback (e.g. Render, Railway, Fly.io, Heroku)
    env_val = os.environ.get(key.upper())
    if env_val is None:
        env_val = os.environ.get(key)
    if env_val is not None:
        try:
            return json.loads(env_val)
        except Exception:
            return env_val

    return default

def set_setting(key: str, value: Any):
    conn = get_db_connection()
    cursor = conn.cursor()
    serialized = json.dumps(value) if not isinstance(value, str) else value
    cursor.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, serialized))
    conn.commit()
    conn.close()

def get_all_settings() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except Exception:
            result[r["key"]] = r["value"]
    return result

def save_target_plan(plan: Dict[str, Any]) -> str:
    """Inserts or updates a target upcoming plan. Marks it active."""
    import uuid
    conn = get_db_connection()
    cursor = conn.cursor()
    
    plan_id = str(plan.get("id") or f"plan_{uuid.uuid4().hex[:10]}")
    
    # If this plan is active, optionally deactivate previous active plans
    if plan.get("is_active", 1):
        cursor.execute("UPDATE target_plans SET is_active = 0")
        
    cursor.execute("""
        INSERT INTO target_plans (
            id, title, target_date, description, distance_miles,
            elevation_gain_ft, estimated_duration_min, estimated_tss,
            intensity_type, route_source, strava_id, summary_polyline,
            svg_path, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            target_date = excluded.target_date,
            description = excluded.description,
            distance_miles = excluded.distance_miles,
            elevation_gain_ft = excluded.elevation_gain_ft,
            estimated_duration_min = excluded.estimated_duration_min,
            estimated_tss = excluded.estimated_tss,
            intensity_type = excluded.intensity_type,
            route_source = excluded.route_source,
            strava_id = excluded.strava_id,
            summary_polyline = excluded.summary_polyline,
            svg_path = excluded.svg_path,
            is_active = excluded.is_active
    """, (
        plan_id,
        plan.get("title", "Upcoming Target Ride"),
        plan.get("target_date", ""),
        plan.get("description", ""),
        float(plan.get("distance_miles") or 0.0),
        float(plan.get("elevation_gain_ft") or 0.0),
        int(plan.get("estimated_duration_min") or 0),
        int(plan.get("estimated_tss") or 0),
        plan.get("intensity_type", "Endurance"),
        plan.get("route_source", "manual"),
        str(plan.get("strava_id") or ""),
        plan.get("summary_polyline", ""),
        plan.get("svg_path", ""),
        int(plan.get("is_active", 1))
    ))
    conn.commit()
    conn.close()
    return plan_id

def get_active_target_plan() -> Optional[Dict[str, Any]]:
    """Returns the most immediate active target plan, or None."""
    import datetime
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM target_plans 
        WHERE is_active = 1
        ORDER BY target_date ASC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
        
    p = dict(row)
    try:
        target_dt = datetime.date.fromisoformat(p["target_date"][:10])
        today = datetime.date.today()
        p["days_until"] = (target_dt - today).days
        p["is_past"] = p["days_until"] < 0
    except Exception:
        p["days_until"] = None
        p["is_past"] = False
        
    return p

def get_all_target_plans() -> List[Dict[str, Any]]:
    """Returns all target plans."""
    import datetime
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM target_plans ORDER BY target_date DESC")
    rows = cursor.fetchall()
    conn.close()
    
    today = datetime.date.today()
    results = []
    for r in rows:
        p = dict(r)
        try:
            target_dt = datetime.date.fromisoformat(p["target_date"][:10])
            p["days_until"] = (target_dt - today).days
            p["is_past"] = p["days_until"] < 0
        except Exception:
            p["days_until"] = None
            p["is_past"] = False
        results.append(p)
    return results

def delete_target_plan(plan_id: str) -> bool:
    """Deletes a target plan by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM target_plans WHERE id = ?", (plan_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def clear_active_target_plans() -> bool:
    """Deactivates all active target plans."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE target_plans SET is_active = 0 WHERE is_active = 1")
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

def save_scheduled_workout(workout: Dict[str, Any], date_str: str) -> str:
    """Saves or updates a scheduled workout for a specific date in SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    w_id = str(workout.get("id") or f"workout_scheduled_{date_str.replace('-', '')}")
    intervals_json = json.dumps(workout.get("intervals") or [])
    
    cursor.execute("""
        INSERT INTO workouts (
            id, date, title, description, focus_area, duration_minutes,
            estimated_tss, intervals_json, zwo_content, intervals_icu_text,
            ai_rationale, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            date = excluded.date,
            title = excluded.title,
            description = excluded.description,
            focus_area = excluded.focus_area,
            duration_minutes = excluded.duration_minutes,
            estimated_tss = excluded.estimated_tss,
            intervals_json = excluded.intervals_json,
            zwo_content = excluded.zwo_content,
            intervals_icu_text = excluded.intervals_icu_text,
            ai_rationale = excluded.ai_rationale,
            status = excluded.status
    """, (
        w_id,
        date_str,
        workout.get("title", "Scheduled Workout"),
        workout.get("description", ""),
        workout.get("focus_area", "Adaptive"),
        int(workout.get("duration_minutes") or 45),
        int(workout.get("estimated_tss") or 50),
        intervals_json,
        workout.get("zwo_content", ""),
        workout.get("intervals_icu_text", ""),
        workout.get("ai_rationale", ""),
        workout.get("status", "scheduled")
    ))
    conn.commit()
    conn.close()
    return w_id

def get_scheduled_workout_for_date(date_str: str) -> Optional[Dict[str, Any]]:
    """Returns scheduled workout for date_str if one exists."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM workouts
        WHERE date = ? AND status IN ('scheduled', 'prescribed')
        ORDER BY created_at DESC
        LIMIT 1
    """, (date_str,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    w = dict(row)
    try:
        w["intervals"] = json.loads(w["intervals_json"])
    except Exception:
        w["intervals"] = []
    w["badge"] = "💬 Coach Scheduled"
    w["badge_color"] = "cyan"
    w["option_type"] = "coach_scheduled"
    return w

def get_upcoming_scheduled_workouts(from_date: str) -> List[Dict[str, Any]]:
    """Returns all scheduled workouts from from_date onwards."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM workouts
        WHERE date >= ? AND status IN ('scheduled', 'prescribed')
        ORDER BY date ASC
    """, (from_date,))
    rows = cursor.fetchall()
    conn.close()
    res = []
    for r in rows:
        w = dict(r)
        try:
            w["intervals"] = json.loads(w["intervals_json"])
        except Exception:
            w["intervals"] = []
        w["badge"] = "💬 Coach Scheduled"
        w["badge_color"] = "cyan"
        res.append(w)
    return res

# Initialize on module load
init_db()
