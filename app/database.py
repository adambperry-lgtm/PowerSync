import sqlite3
import json
import os
import datetime
import secrets
import uuid
import zoneinfo
from typing import Dict, Any, Optional, List
from contextvars import ContextVar

DEFAULT_USER_ID = "usr_default"
GUEST_USER_ID = "usr_guest"
DEFAULT_TIMEZONE = "America/New_York"
CURRENT_USER_ID: ContextVar[str] = ContextVar("CURRENT_USER_ID", default=DEFAULT_USER_ID)
CURRENT_USER_TIMEZONE: ContextVar[str] = ContextVar("CURRENT_USER_TIMEZONE", default=DEFAULT_TIMEZONE)

def get_current_user_id() -> str:
    """Returns the current active user ID from contextvars, or the default user."""
    return CURRENT_USER_ID.get()

def set_current_user_context(user_id: str):
    """Sets the active user ID context for the current request lifecycle."""
    return CURRENT_USER_ID.set(user_id)

def reset_current_user_context(token):
    """Resets the contextvar token back to its previous state."""
    CURRENT_USER_ID.reset(token)

def set_current_timezone_context(tz_name: str):
    """Sets the active user timezone context for the current request lifecycle."""
    return CURRENT_USER_TIMEZONE.set(tz_name)

def reset_current_timezone_context(token):
    """Resets the timezone contextvar token back to its previous state."""
    CURRENT_USER_TIMEZONE.reset(token)

def get_athlete_timezone_name(user_id: Optional[str] = None) -> str:
    """Resolves the active athlete IANA timezone name."""
    ctx_tz = CURRENT_USER_TIMEZONE.get()
    if ctx_tz and ctx_tz != DEFAULT_TIMEZONE:
        return ctx_tz

    uid = user_id or get_current_user_id()
    try:
        saved_tz = get_setting("athlete_timezone", default=None, user_id=uid)
        if saved_tz and isinstance(saved_tz, str) and saved_tz.strip():
            return saved_tz.strip()
    except Exception:
        pass

    env_tz = os.environ.get("TZ") or os.environ.get("ATHLETE_TIMEZONE")
    if env_tz and env_tz.strip():
        return env_tz.strip()

    return ctx_tz or DEFAULT_TIMEZONE

def get_athlete_timezone(user_id: Optional[str] = None) -> zoneinfo.ZoneInfo:
    """Returns ZoneInfo object for athlete, falling back safely to America/New_York."""
    tz_name = get_athlete_timezone_name(user_id)
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)

def get_athlete_now(user_id: Optional[str] = None) -> datetime.datetime:
    """Returns the current timezone-aware datetime for the athlete."""
    return datetime.datetime.now(get_athlete_timezone(user_id))

def get_athlete_date(user_id: Optional[str] = None) -> datetime.date:
    """Returns the current calendar date in the athlete's local timezone."""
    return get_athlete_now(user_id).date()

def get_db_path() -> str:
    # 1. Explicit DATABASE_PATH override
    if os.environ.get("DATABASE_PATH") and os.environ["DATABASE_PATH"].strip():
        return os.environ["DATABASE_PATH"].strip()

    # 2. Check Railway Volume mount path (both raw and stripped)
    railway_vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_vol:
        if os.path.isdir(railway_vol):
            return os.path.join(railway_vol, "fitness.db")
        if os.path.isdir(railway_vol.strip()):
            return os.path.join(railway_vol.strip(), "fitness.db")

    # 3. Check /app/data (Docker standard)
    if os.path.isdir("/app/data"):
        return "/app/data/fitness.db"

    # 4. Default local repository data folder
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fitness.db")

DB_PATH = get_db_path()

def ensure_db_migrated():
    """Guarantees that an existing database with athlete data is preserved on the persistent volume."""
    target = get_db_path()
    target_has_data = os.path.exists(target) and os.path.getsize(target) > 0
    if target_has_data:
        return

    # Look for candidate existing databases that have data
    candidates = [
        "/app/data/fitness.db",
        os.path.join(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""), "fitness.db") if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") else "",
        os.path.join(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip(), "fitness.db") if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") else "",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fitness.db")
    ]
    import shutil
    for cand in candidates:
        if cand and cand != target and os.path.exists(cand) and os.path.getsize(cand) > 0:
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(cand, target)
                print(f"[PowerSync] Migrated existing database ({os.path.getsize(cand)} bytes) from {cand} to persistent volume at {target}")
                break
            except Exception as e:
                print(f"[PowerSync] Could not copy {cand} to {target}: {e}")

def get_db_connection() -> sqlite3.Connection:
    ensure_db_migrated()
    active_path = get_db_path()
    db_dir = os.path.dirname(active_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(active_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn

def _migrate_table_to_multiuser(cursor, table_name: str, create_v2_sql: str, copy_columns: str):
    """Safely adds user_id column and updates primary key without data loss."""
    try:
        cols = [r["name"] for r in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
        if not cols:
            # Table does not exist yet; standard init will create it
            return
        if "user_id" not in cols:
            v2_table = f"{table_name}_v2"
            cursor.execute(create_v2_sql)
            cursor.execute(f"INSERT OR IGNORE INTO {v2_table} (user_id, {copy_columns}) SELECT '{DEFAULT_USER_ID}', {copy_columns} FROM {table_name}")
            cursor.execute(f"DROP TABLE {table_name}")
            cursor.execute(f"ALTER TABLE {v2_table} RENAME TO {table_name}")
            print(f"[PowerSync] Successfully migrated {table_name} to multi-user isolated schema.")
    except Exception as e:
        print(f"[PowerSync] Warning: Table migration error on {table_name}: {e}")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users account table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        picture TEXT,
        google_id TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. OAuth temporary states table (for CSRF protection and multi-user callback routing)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        user_id TEXT,
        provider TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Check and migrate settings
    _migrate_table_to_multiuser(
        cursor,
        table_name="settings",
        create_v2_sql="""
        CREATE TABLE IF NOT EXISTS settings_v2 (
            user_id TEXT NOT NULL DEFAULT 'usr_default',
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        """,
        copy_columns="key, value"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT NOT NULL DEFAULT 'usr_default',
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (user_id, key)
    );
    """)

    # Check and migrate whoop_metrics
    _migrate_table_to_multiuser(
        cursor,
        table_name="whoop_metrics",
        create_v2_sql="""
        CREATE TABLE IF NOT EXISTS whoop_metrics_v2 (
            user_id TEXT NOT NULL DEFAULT 'usr_default',
            date TEXT NOT NULL,
            recovery_score INTEGER,
            hrv_rmssd REAL,
            resting_heart_rate INTEGER,
            sleep_performance INTEGER,
            sleep_duration_hours REAL,
            day_strain REAL,
            raw_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, date)
        );
        """,
        copy_columns="date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain, raw_json, updated_at"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS whoop_metrics (
        user_id TEXT NOT NULL DEFAULT 'usr_default',
        date TEXT NOT NULL,
        recovery_score INTEGER,
        hrv_rmssd REAL,
        resting_heart_rate INTEGER,
        sleep_performance INTEGER,
        sleep_duration_hours REAL,
        day_strain REAL,
        raw_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, date)
    );
    """)

    # Check and migrate strava_activities
    _migrate_table_to_multiuser(
        cursor,
        table_name="strava_activities",
        create_v2_sql="""
        CREATE TABLE IF NOT EXISTS strava_activities_v2 (
            user_id TEXT NOT NULL DEFAULT 'usr_default',
            id TEXT NOT NULL,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, id)
        );
        """,
        copy_columns="id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec, distance_meters, total_elevation_gain, average_watts, weighted_average_watts, average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json, created_at"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS strava_activities (
        user_id TEXT NOT NULL DEFAULT 'usr_default',
        id TEXT NOT NULL,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, id)
    );
    """)

    # Check and migrate workouts
    _migrate_table_to_multiuser(
        cursor,
        table_name="workouts",
        create_v2_sql="""
        CREATE TABLE IF NOT EXISTS workouts_v2 (
            user_id TEXT NOT NULL DEFAULT 'usr_default',
            id TEXT NOT NULL,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, id)
        );
        """,
        copy_columns="id, date, title, description, focus_area, duration_minutes, estimated_tss, intervals_json, zwo_content, intervals_icu_text, ai_rationale, status, created_at"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workouts (
        user_id TEXT NOT NULL DEFAULT 'usr_default',
        id TEXT NOT NULL,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, id)
    );
    """)

    # Check and migrate target_plans
    _migrate_table_to_multiuser(
        cursor,
        table_name="target_plans",
        create_v2_sql="""
        CREATE TABLE IF NOT EXISTS target_plans_v2 (
            user_id TEXT NOT NULL DEFAULT 'usr_default',
            id TEXT NOT NULL,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, id)
        );
        """,
        copy_columns="id, title, target_date, description, distance_miles, elevation_gain_ft, estimated_duration_min, estimated_tss, intensity_type, route_source, strava_id, summary_polyline, svg_path, is_active, created_at"
    )
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS target_plans (
        user_id TEXT NOT NULL DEFAULT 'usr_default',
        id TEXT NOT NULL,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, id)
    );
    """)

    # Ensure default user exists so legacy single-user data is preserved
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, email, name, picture)
        VALUES ('usr_default', 'athlete@powersync.local', 'Primary Athlete', '')
    """)

    # Ensure isolated guest user exists for unauthenticated browsing
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, email, name, picture)
        VALUES ('usr_guest', 'guest@powersync.local', 'Guest Athlete', '')
    """)

    # Auto-repair: If usr_default was accidentally renamed to Coach Alex in earlier dev switching,
    # restore its identity back to Primary Athlete so the owner's credentials remain clean.
    cursor.execute("""
        UPDATE users
        SET email = 'athlete@powersync.local', name = 'Primary Athlete'
        WHERE id = 'usr_default' AND (google_id IS NULL OR google_id = '') AND email LIKE '%@powersync.app'
    """)

    conn.commit()
    conn.close()

ENV_FALLBACK_ALIASES = {
    "athlete_ftp": ["ATHLETE_FTP", "FTP"],
    "athlete_max_hr": ["ATHLETE_MAX_HR", "MAX_HR"],
    "intervals_icu_api_key": ["INTERVALS_ICU_API_KEY", "INTERVALS_API_KEY"],
    "intervals_athlete_id": ["INTERVALS_ATHLETE_ID", "INTERVALS_ID"],
    "strava_client_id": ["STRAVA_CLIENT_ID"],
    "strava_client_secret": ["STRAVA_CLIENT_SECRET"],
    "whoop_client_id": ["WHOOP_CLIENT_ID"],
    "whoop_client_secret": ["WHOOP_CLIENT_SECRET"],
    "gemini_api_key": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "google_maps_api_key": ["GOOGLE_MAPS_API_KEY", "MAPS_API_KEY"],
    "google_client_id": ["GOOGLE_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"],
    "google_client_secret": ["GOOGLE_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"],
    "strava_tokens": ["STRAVA_TOKENS"],
    "whoop_tokens": ["WHOOP_TOKENS"],
}

# App-wide global environment keys that can be shared across all users
GLOBAL_ENV_KEYS = {
    "strava_client_id", "strava_client_secret",
    "whoop_client_id", "whoop_client_secret",
    "gemini_api_key", "google_maps_api_key",
    "google_client_id", "google_client_secret"
}

def get_env_fallback(key: str) -> Optional[Any]:
    candidates = ENV_FALLBACK_ALIASES.get(key, [key.upper(), key])
    for cand in candidates:
        val = os.environ.get(cand)
        if val is not None and str(val).strip():
            val = str(val).strip()
            try:
                return json.loads(val)
            except Exception:
                return val
    return None

def get_setting(key: str, default: Any = None, user_id: Optional[str] = None) -> Any:
    uid = user_id or get_current_user_id()

    # Guest user isolation & defaults
    if uid == GUEST_USER_ID:
        if key == "demo_mode":
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (uid, key))
            row = cursor.fetchone()
            conn.close()
            if row and row["value"]:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return True
        # For sensitive personal credentials, guests NEVER inherit usr_default's credentials
        if key in ("intervals_icu_api_key", "intervals_athlete_id", "strava_tokens", "whoop_tokens"):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (uid, key))
            row = cursor.fetchone()
            conn.close()
            if row and row["value"]:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return default

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (uid, key))
    row = cursor.fetchone()
    conn.close()
    if row and row["value"] is not None and str(row["value"]).strip() != "":
        val = row["value"]
        if isinstance(val, str):
            val = val.strip()
        try:
            parsed = json.loads(val)
            if parsed is not None:
                return parsed
            # Explicit null stored in database (e.g. disconnected)
            return default
        except Exception:
            return val
    
    # Global environment fallback: only for app credentials or for default athlete account
    if key in GLOBAL_ENV_KEYS:
        # Check if saved under usr_default if current user is not usr_default
        if uid != DEFAULT_USER_ID:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (DEFAULT_USER_ID, key))
            def_row = cursor.fetchone()
            conn.close()
            if def_row and def_row["value"] and str(def_row["value"]).strip() != "":
                try:
                    return json.loads(def_row["value"])
                except Exception:
                    return def_row["value"]
        env_val = get_env_fallback(key)
        if env_val is not None:
            return env_val

    if uid == DEFAULT_USER_ID:
        env_val = get_env_fallback(key)
        if env_val is not None:
            return env_val

    return default

def set_setting(key: str, value: Any, user_id: Optional[str] = None):
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    serialized = json.dumps(value) if not isinstance(value, str) else value
    cursor.execute("""
        INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
    """, (uid, key, serialized))
    conn.commit()
    conn.close()

def get_all_settings(user_id: Optional[str] = None) -> Dict[str, Any]:
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE user_id = ?", (uid,))
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except Exception:
            result[r["key"]] = r["value"]

    # Fallback to environment variables for global credentials
    for k in GLOBAL_ENV_KEYS:
        if k not in result or result[k] is None or (isinstance(result[k], str) and not result[k].strip()):
            env_val = get_env_fallback(k)
            if env_val is not None:
                result[k] = env_val

    # For default user, also inherit other non-secret env defaults
    if uid == DEFAULT_USER_ID:
        for k in ENV_FALLBACK_ALIASES.keys():
            if k not in result or result[k] is None or (isinstance(result[k], str) and not result[k].strip()):
                env_val = get_env_fallback(k)
                if env_val is not None:
                    result[k] = env_val

    return result

# ==========================================
# User Account & Session Management
# ==========================================

def create_or_get_google_user(email: str, name: str, picture: Optional[str] = None, google_id: Optional[str] = None) -> Dict[str, Any]:
    """Finds or creates a user account authenticated via Google."""
    clean_email = email.strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Lookup by google_id
    if google_id:
        cursor.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE users SET name = ?, picture = COALESCE(?, picture), last_login = CURRENT_TIMESTAMP WHERE id = ?", (name, picture, row["id"]))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE id = ?", (row["id"],))
            user = dict(cursor.fetchone())
            conn.close()
            return user

    # 2. Lookup by email
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET name = ?, picture = COALESCE(?, picture), google_id = COALESCE(?, google_id), last_login = CURRENT_TIMESTAMP WHERE id = ?", (name, picture, google_id, row["id"]))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (row["id"],))
        user = dict(cursor.fetchone())
        conn.close()
        return user

    # 3. Check if usr_default has not been claimed by a Google account yet -> Claim it directly IF owner matches or unclaimed
    locked_owner = get_primary_owner_email()
    cursor.execute("SELECT * FROM users WHERE id = 'usr_default' AND (google_id IS NULL OR google_id = '')")
    default_row = cursor.fetchone()
    can_claim_default = False
    if default_row:
        if not locked_owner:
            can_claim_default = True
            set_primary_owner_email(clean_email)
        elif locked_owner == clean_email:
            can_claim_default = True

    if can_claim_default:
        cursor.execute("""
            UPDATE users
            SET email = ?, name = ?, picture = COALESCE(?, picture), google_id = ?, last_login = CURRENT_TIMESTAMP
            WHERE id = 'usr_default'
        """, (clean_email, name, picture or "", google_id))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = 'usr_default'")
        user = dict(cursor.fetchone())
        conn.close()
        return user

    # 4. If usr_default was already claimed or locked to the owner, create a clean isolated user profile
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, google_id, last_login)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, clean_email, name, picture or "", google_id))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())
    conn.close()
    return user

DEV_USER_PROFILES: Dict[str, Dict[str, Any]] = {
    "coach.alex@powersync.app": {
        "id": "usr_coach_alex",
        "name": "Coach Alex",
        "email": "coach.alex@powersync.app",
        "settings": {
            "athlete_ftp": 315,
            "athlete_max_hr": 194,
            "athlete_w_prime_kj": 25.0,
            "athlete_peak_power_watts": 1250,
            "program_goal": "FTP_BUILD",
            "program_target_ftp": 335,
            "program_target_date": "2026-08-15",
            "program_weekly_tss_target": 480,
            "demo_mode": False,
            "coaching_preferences": {
                "directives": [
                    "Warmup: 45% -> 75% FTP ramp, Cooldown: 65% -> 40% FTP ramp",
                    "Indoor intervals on Tuesday/Thursday, outdoor endurance on weekends",
                    "Focus on anaerobic capacity and power above threshold"
                ]
            }
        },
        "whoop": {
            "recovery_score": 88,
            "hrv_rmssd": 84.2,
            "resting_heart_rate": 42,
            "sleep_performance": 94,
            "sleep_duration_hours": 8.5,
            "day_strain": 7.4
        },
        "plan": {
            "id": "plan_coach_alex",
            "title": "Leadville 100 MTB Prep",
            "target_date": "2026-08-15",
            "description": "High-altitude mountain bike endurance preparation focusing on threshold repeatability and sustained climbing.",
            "distance_miles": 100.0,
            "elevation_gain_ft": 12000.0,
            "estimated_duration_min": 420,
            "estimated_tss": 460,
            "intensity_type": "Threshold",
            "is_active": 1
        },
        "activities": [
            {
                "id": "alex_act_1",
                "name": "High-Altitude VO2 Max Climbing Repeats",
                "sport_type": "Ride",
                "days_ago": 1,
                "moving_time_sec": 4800,
                "distance_meters": 38500,
                "total_elevation_gain": 850,
                "average_watts": 285,
                "weighted_average_watts": 320,
                "average_heartrate": 164,
                "max_heartrate": 188,
                "suffer_score": 92,
                "kilojoules": 1368
            },
            {
                "id": "alex_act_2",
                "name": "Sweet Spot Threshold Progression",
                "sport_type": "VirtualRide",
                "days_ago": 2,
                "moving_time_sec": 4200,
                "distance_meters": 36000,
                "total_elevation_gain": 320,
                "average_watts": 275,
                "weighted_average_watts": 298,
                "average_heartrate": 156,
                "max_heartrate": 178,
                "suffer_score": 78,
                "kilojoules": 1155
            },
            {
                "id": "alex_act_3",
                "name": "Sub-Threshold Canyon Tempo",
                "sport_type": "Ride",
                "days_ago": 4,
                "moving_time_sec": 7200,
                "distance_meters": 64000,
                "total_elevation_gain": 1200,
                "average_watts": 250,
                "weighted_average_watts": 270,
                "average_heartrate": 148,
                "max_heartrate": 170,
                "suffer_score": 115,
                "kilojoules": 1800
            }
        ]
    },
    "rider.jordan@powersync.app": {
        "id": "usr_rider_jordan",
        "name": "Rider Jordan",
        "email": "rider.jordan@powersync.app",
        "settings": {
            "athlete_ftp": 210,
            "athlete_max_hr": 174,
            "athlete_w_prime_kj": 16.0,
            "athlete_peak_power_watts": 850,
            "program_goal": "GRAN_FONDO",
            "program_target_ftp": 230,
            "program_target_date": "2026-10-04",
            "program_weekly_tss_target": 260,
            "demo_mode": False,
            "coaching_preferences": {
                "directives": [
                    "Strictly cap heart rate under Zone 3 on recovery days",
                    "Prefers high cadence 90-95 RPM spinning",
                    "Saturday dedicated gravel endurance roll"
                ]
            }
        },
        "whoop": {
            "recovery_score": 38,
            "hrv_rmssd": 41.5,
            "resting_heart_rate": 58,
            "sleep_performance": 68,
            "sleep_duration_hours": 6.2,
            "day_strain": 15.8
        },
        "plan": {
            "id": "plan_rider_jordan",
            "title": "Belgian Waffle Ride 100k",
            "target_date": "2026-10-04",
            "description": "Challenging mixed-surface dirt and gravel endurance ride with punchy sectors.",
            "distance_miles": 65.0,
            "elevation_gain_ft": 4500.0,
            "estimated_duration_min": 240,
            "estimated_tss": 250,
            "intensity_type": "Endurance",
            "is_active": 1
        },
        "activities": [
            {
                "id": "jordan_act_1",
                "name": "Heavy Trail Day (High Fatigue)",
                "sport_type": "Ride",
                "days_ago": 1,
                "moving_time_sec": 5400,
                "distance_meters": 32000,
                "total_elevation_gain": 650,
                "average_watts": 170,
                "weighted_average_watts": 192,
                "average_heartrate": 152,
                "max_heartrate": 168,
                "suffer_score": 88,
                "kilojoules": 918
            },
            {
                "id": "jordan_act_2",
                "name": "Easy Coffee & Bakery Spin",
                "sport_type": "Ride",
                "days_ago": 3,
                "moving_time_sec": 3000,
                "distance_meters": 18000,
                "total_elevation_gain": 110,
                "average_watts": 140,
                "weighted_average_watts": 148,
                "average_heartrate": 122,
                "max_heartrate": 138,
                "suffer_score": 24,
                "kilojoules": 420
            },
            {
                "id": "jordan_act_3",
                "name": "Canal Gravel Endurance",
                "sport_type": "Ride",
                "days_ago": 5,
                "moving_time_sec": 4800,
                "distance_meters": 34000,
                "total_elevation_gain": 180,
                "average_watts": 155,
                "weighted_average_watts": 165,
                "average_heartrate": 130,
                "max_heartrate": 145,
                "suffer_score": 42,
                "kilojoules": 744
            }
        ]
    }
}

def seed_dev_user_profile(user_id: str, profile: Dict[str, Any]):
    """Seeds distinct athlete biometrics, settings, activities, and goals for a dev athlete."""
    clean_email = (profile.get("email") or f"{user_id}@powersync.app").strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    # Clean up any legacy row that had this email under a random UUID to avoid UNIQUE constraint violation
    c.execute("DELETE FROM users WHERE email = ? AND id != ?", (clean_email, user_id))
    c.execute("""
        INSERT INTO users (id, email, name, picture, last_login)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET email = excluded.email, name = excluded.name, last_login = CURRENT_TIMESTAMP
    """, (user_id, clean_email, profile["name"], profile.get("picture", "")))
    conn.commit()
    conn.close()

    # Settings
    for k, v in profile.get("settings", {}).items():
        set_setting(k, v, user_id=user_id)

    # Whoop metrics: seed today + 6 trailing days
    today = get_athlete_date()
    whoop = profile.get("whoop", {})
    base_rec = whoop.get("recovery_score", 75)
    base_hrv = whoop.get("hrv_rmssd", 55.0)
    base_rhr = whoop.get("resting_heart_rate", 50)
    base_sleep = whoop.get("sleep_performance", 85)
    base_sleep_hrs = whoop.get("sleep_duration_hours", 7.5)
    base_strain = whoop.get("day_strain", 10.0)

    conn = get_db_connection()
    c = conn.cursor()
    for d in range(7):
        d_date = (today - datetime.timedelta(days=d)).isoformat()
        jitter = (d % 3) * 2 - 2
        d_rec = max(20, min(99, base_rec + jitter))
        d_strain = max(4.0, min(20.0, base_strain - jitter * 0.8))
        c.execute("""
            INSERT INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                recovery_score = excluded.recovery_score,
                hrv_rmssd = excluded.hrv_rmssd,
                resting_heart_rate = excluded.resting_heart_rate,
                sleep_performance = excluded.sleep_performance,
                sleep_duration_hours = excluded.sleep_duration_hours,
                day_strain = excluded.day_strain
        """, (user_id, d_date, d_rec, base_hrv, base_rhr, base_sleep, base_sleep_hrs, d_strain))

    # Strava activities
    for act in profile.get("activities", []):
        act_date = (today - datetime.timedelta(days=act.get("days_ago", 1))).strftime("%Y-%m-%dT08:00:00Z")
        c.execute("""
            INSERT INTO strava_activities (
                user_id, id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec,
                distance_meters, total_elevation_gain, average_watts, weighted_average_watts,
                average_heartrate, max_heartrate, suffer_score, kilojoules
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, id) DO UPDATE SET
                start_date = excluded.start_date,
                name = excluded.name,
                average_watts = excluded.average_watts,
                weighted_average_watts = excluded.weighted_average_watts,
                suffer_score = excluded.suffer_score,
                kilojoules = excluded.kilojoules
        """, (
            user_id, act["id"], act["name"], act["sport_type"], act_date,
            act["moving_time_sec"] + 300, act["moving_time_sec"],
            act["distance_meters"], act["total_elevation_gain"],
            act["average_watts"], act["weighted_average_watts"],
            act["average_heartrate"], act["max_heartrate"],
            act["suffer_score"], act["kilojoules"]
        ))

    # Target plan
    plan = profile.get("plan")
    if plan:
        c.execute("""
            INSERT INTO target_plans (
                user_id, id, title, target_date, description, distance_miles, elevation_gain_ft,
                estimated_duration_min, estimated_tss, intensity_type, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, id) DO UPDATE SET title = excluded.title, target_date = excluded.target_date
        """, (
            user_id, plan["id"], plan["title"], plan["target_date"], plan["description"],
            plan["distance_miles"], plan["elevation_gain_ft"], plan["estimated_duration_min"],
            plan["estimated_tss"], plan["intensity_type"], plan["is_active"]
        ))

    conn.commit()
    conn.close()

def get_primary_owner_email() -> Optional[str]:
    """Returns the locked primary owner email address, if one has been established."""
    env_owner = os.environ.get("OWNER_EMAIL") or os.environ.get("PRIMARY_ATHLETE_EMAIL")
    if env_owner and env_owner.strip():
        return env_owner.strip().lower()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE user_id = 'usr_default' AND key = 'primary_owner_email'")
    row = c.fetchone()
    conn.close()
    if row and row["value"]:
        val = str(row["value"]).strip().lower()
        if "@" in val:
            return val
    return None

def set_primary_owner_email(email: str):
    """Permanently locks the primary athlete account to this specific email address."""
    clean = email.strip().lower()
    set_setting("primary_owner_email", clean, user_id="usr_default")

def create_or_get_email_user(email: str, name: Optional[str] = None, picture: Optional[str] = None, claim_primary: bool = False) -> Dict[str, Any]:
    """
    Finds or creates an isolated athlete account authenticated via email.
    If the primary owner email is locked, ONLY that specific email can access usr_default.
    Anyone else is strictly routed to their own private isolated athlete database.
    """
    clean_email = email.strip().lower()
    auto_name = name.strip() if name and name.strip() else clean_email.split("@")[0].replace(".", " ").title()

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Built-in test athletes: Coach Alex & Rider Jordan with distinct data
    if clean_email in DEV_USER_PROFILES:
        conn.close()
        prof = DEV_USER_PROFILES[clean_email]
        user_id = prof["id"]
        seed_dev_user_profile(user_id, prof)
        user = get_user_by_id(user_id)
        if user:
            return user

    # 2. Check primary owner locking
    locked_owner = get_primary_owner_email()
    cursor.execute("SELECT * FROM users WHERE id = 'usr_default'")
    default_row = cursor.fetchone()

    is_matching_owner = bool(locked_owner and clean_email == locked_owner)
    is_default_row_email = bool(default_row and default_row["email"] == clean_email)

    can_access_primary = False
    if is_matching_owner or is_default_row_email:
        can_access_primary = True
    elif not locked_owner and claim_primary:
        # First-time claim permanently locks primary ownership to this email!
        can_access_primary = True
        set_primary_owner_email(clean_email)

    if can_access_primary:
        # Remove any non-default row with this email to avoid UNIQUE constraint
        cursor.execute("DELETE FROM users WHERE email = ? AND id != 'usr_default'", (clean_email,))
        cursor.execute("""
            UPDATE users SET email = ?, name = ?, last_login = CURRENT_TIMESTAMP
            WHERE id = 'usr_default'
        """, (clean_email, auto_name))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = 'usr_default'")
        user = dict(cursor.fetchone())
        conn.close()
        return user

    # 3. Lookup existing user by email
    cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET name = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?", (auto_name, row["id"]))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (row["id"],))
        user = dict(cursor.fetchone())
        conn.close()
        return user

    # 4. Create new isolated athlete user
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, last_login)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, clean_email, auto_name, picture or ""))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())
    conn.close()
    return user

def create_or_get_dev_user(email: str, name: str, picture: Optional[str] = None) -> Dict[str, Any]:
    """Helper for dev/testing authentication with complete data isolation."""
    return create_or_get_email_user(email=email, name=name, picture=picture, claim_primary=False)

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_guest_user() -> Dict[str, Any]:
    """Returns the unauthenticated guest athlete profile with demo-mode isolation."""
    u = get_user_by_id(GUEST_USER_ID)
    if u:
        user_dict = dict(u)
        user_dict["is_guest"] = True
        return user_dict
    return {
        "id": GUEST_USER_ID,
        "email": "guest@powersync.local",
        "name": "Guest Athlete",
        "picture": "",
        "google_id": None,
        "is_guest": True,
        "created_at": None
    }

def get_default_athlete_user() -> Dict[str, Any]:
    """Returns the default primary athlete profile holding all historical data."""
    u = get_user_by_id(DEFAULT_USER_ID)
    if u:
        user_dict = dict(u)
        user_dict["is_guest"] = False
        return user_dict
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, email, name, picture)
        VALUES ('usr_default', 'athlete@powersync.local', 'Primary Athlete', '')
    """)
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = 'usr_default'")
    user = dict(cursor.fetchone())
    conn.close()
    user["is_guest"] = False
    return user

def get_default_or_guest_user() -> Dict[str, Any]:
    """Backward compatibility alias for primary athlete."""
    return get_default_athlete_user()

def create_session(user_id: str, days_valid: int = 30) -> str:
    """Generates a secure cryptographically random session token for user_id."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=days_valid)).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires_at))
    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return token

def get_user_by_session(token: str) -> Optional[Dict[str, Any]]:
    """Resolves active user by session token, verifying expiration."""
    if not token or not token.strip():
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.email, u.name, u.picture, u.google_id, u.created_at, u.last_login, s.expires_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    """, (token.strip(),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    now_iso = datetime.datetime.utcnow().isoformat()
    if row["expires_at"] < now_iso:
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token.strip(),))
        conn.commit()
        conn.close()
        return None

    conn.close()
    return dict(row)

def delete_session(token: str) -> bool:
    """Revokes session token."""
    if not token:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token.strip(),))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def save_oauth_state(state: str, user_id: Optional[str], provider: str):
    """Saves high-entropy OAuth state for callback routing and CSRF defense."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO oauth_states (state, user_id, provider) VALUES (?, ?, ?)", (state, user_id, provider))
    conn.commit()
    conn.close()

def verify_and_consume_oauth_state(state: str, provider: str) -> Optional[str]:
    """Verifies state exists for provider and deletes it. Returns attached user_id or None."""
    if not state:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM oauth_states WHERE state = ? AND provider = ?", (state, provider))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    user_id = row["user_id"]
    cursor.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    conn.commit()
    conn.close()
    return user_id

# ==========================================
# User-Isolated Target Plans
# ==========================================

def save_target_plan(plan: Dict[str, Any], user_id: Optional[str] = None) -> str:
    """Inserts or updates a target upcoming plan. Marks it active for this user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    plan_id = str(plan.get("id") or f"plan_{uuid.uuid4().hex[:10]}")
    
    # If this plan is active, deactivate previous active plans for this user
    if plan.get("is_active", 1):
        cursor.execute("UPDATE target_plans SET is_active = 0 WHERE user_id = ?", (uid,))
        
    cursor.execute("""
        INSERT INTO target_plans (
            user_id, id, title, target_date, description, distance_miles,
            elevation_gain_ft, estimated_duration_min, estimated_tss,
            intensity_type, route_source, strava_id, summary_polyline,
            svg_path, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, id) DO UPDATE SET
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
        uid,
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

def get_active_target_plan(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns the most immediate active target plan for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM target_plans 
        WHERE user_id = ? AND is_active = 1
        ORDER BY target_date ASC
        LIMIT 1
    """, (uid,))
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

def get_all_target_plans(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all target plans for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM target_plans WHERE user_id = ? ORDER BY target_date DESC", (uid,))
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

def delete_target_plan(plan_id: str, user_id: Optional[str] = None) -> bool:
    """Deletes a target plan by ID for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM target_plans WHERE user_id = ? AND id = ?", (uid, plan_id))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def clear_active_target_plans(user_id: Optional[str] = None) -> bool:
    """Deactivates all active target plans for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE target_plans SET is_active = 0 WHERE user_id = ? AND is_active = 1", (uid,))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

# ==========================================
# User-Isolated Scheduled Workouts
# ==========================================

def save_scheduled_workout(workout: Dict[str, Any], date_str: str, user_id: Optional[str] = None) -> str:
    """Saves or updates a scheduled workout for a specific date in SQLite."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    w_id = str(workout.get("id") or f"workout_scheduled_{date_str.replace('-', '')}")
    intervals_json = json.dumps(workout.get("intervals") or [])
    
    cursor.execute("""
        INSERT INTO workouts (
            user_id, id, date, title, description, focus_area, duration_minutes,
            estimated_tss, intervals_json, zwo_content, intervals_icu_text,
            ai_rationale, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, id) DO UPDATE SET
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
        uid,
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

def get_scheduled_workout_for_date(date_str: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns scheduled workout for date_str if one exists for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM workouts
        WHERE user_id = ? AND date = ? AND status IN ('scheduled', 'prescribed')
        ORDER BY created_at DESC
        LIMIT 1
    """, (uid, date_str))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    w = dict(row)
    try:
        w["intervals"] = json.loads(w["intervals_json"])
    except Exception:
        w["intervals"] = []
    import datetime
    today_iso = datetime.date.today().isoformat()
    if date_str == today_iso:
        w["badge"] = "⭐ Coach's Choice"
        w["badge_color"] = "emerald"
    else:
        w["badge"] = "💬 Coach Scheduled"
        w["badge_color"] = "cyan"
    w["option_type"] = "coach_scheduled"
    return w

def get_upcoming_scheduled_workouts(from_date: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all scheduled workouts from from_date onwards for the active user."""
    uid = user_id or get_current_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM workouts
        WHERE user_id = ? AND date >= ? AND status IN ('scheduled', 'prescribed')
        ORDER BY date ASC
    """, (uid, from_date))
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

def claim_or_copy_default_data_to_user(target_user_id: str) -> Dict[str, Any]:
    """
    Copies all settings, directives, biometrics, activities, workouts, and plans
    from the default athlete profile (usr_default) to target_user_id.
    """
    if not target_user_id or target_user_id == DEFAULT_USER_ID:
        return {"success": True, "message": "Already using default athlete profile."}
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Copy settings where key does not exist yet for target_user_id
    cursor.execute("""
        INSERT OR IGNORE INTO settings (user_id, key, value)
        SELECT ?, key, value FROM settings WHERE user_id = 'usr_default'
    """, (target_user_id,))

    # 2. Copy whoop metrics
    cursor.execute("""
        INSERT OR IGNORE INTO whoop_metrics (user_id, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain, raw_json, updated_at)
        SELECT ?, date, recovery_score, hrv_rmssd, resting_heart_rate, sleep_performance, sleep_duration_hours, day_strain, raw_json, updated_at
        FROM whoop_metrics WHERE user_id = 'usr_default'
    """, (target_user_id,))

    # 3. Copy strava activities
    cursor.execute("""
        INSERT OR IGNORE INTO strava_activities (user_id, id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec, distance_meters, total_elevation_gain, average_watts, weighted_average_watts, average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json, created_at)
        SELECT ?, id, name, sport_type, start_date, elapsed_time_sec, moving_time_sec, distance_meters, total_elevation_gain, average_watts, weighted_average_watts, average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json, created_at
        FROM strava_activities WHERE user_id = 'usr_default'
    """, (target_user_id,))

    # 4. Copy workouts
    cursor.execute("""
        INSERT OR IGNORE INTO workouts (user_id, id, date, title, description, focus_area, duration_minutes, estimated_tss, intervals_json, zwo_content, intervals_icu_text, ai_rationale, status, created_at)
        SELECT ?, id, date, title, description, focus_area, duration_minutes, estimated_tss, intervals_json, zwo_content, intervals_icu_text, ai_rationale, status, created_at
        FROM workouts WHERE user_id = 'usr_default'
    """, (target_user_id,))

    # 5. Copy target plans
    cursor.execute("""
        INSERT OR IGNORE INTO target_plans (user_id, id, title, target_date, description, distance_miles, elevation_gain_ft, estimated_duration_min, estimated_tss, intensity_type, route_source, strava_id, summary_polyline, svg_path, is_active, created_at)
        SELECT ?, id, title, target_date, description, distance_miles, elevation_gain_ft, estimated_duration_min, estimated_tss, intensity_type, route_source, strava_id, summary_polyline, svg_path, is_active, created_at
        FROM target_plans WHERE user_id = 'usr_default'
    """, (target_user_id,))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Successfully imported all settings, coaching directives, and history from default athlete."}

# Initialize on module load
init_db()
for _email, _prof in DEV_USER_PROFILES.items():
    seed_dev_user_profile(_prof["id"], _prof)

