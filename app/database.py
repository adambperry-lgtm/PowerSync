import sqlite3
import json
import os
import datetime
import secrets
import uuid
from typing import Dict, Any, Optional, List
from contextvars import ContextVar

DEFAULT_USER_ID = "usr_default"
CURRENT_USER_ID: ContextVar[str] = ContextVar("CURRENT_USER_ID", default=DEFAULT_USER_ID)

def get_current_user_id() -> str:
    """Returns the current active user ID from contextvars, or the default user."""
    return CURRENT_USER_ID.get()

def set_current_user_context(user_id: str):
    """Sets the active user ID context for the current request lifecycle."""
    return CURRENT_USER_ID.set(user_id)

def reset_current_user_context(token):
    """Resets the contextvar token back to its previous state."""
    CURRENT_USER_ID.reset(token)

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
    conn = sqlite3.connect(active_path)
    conn.row_factory = sqlite3.Row
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
    if key in GLOBAL_ENV_KEYS or uid == DEFAULT_USER_ID:
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

    # 3. Check if usr_default has not been claimed by a Google account yet -> Claim it directly!
    cursor.execute("SELECT * FROM users WHERE id = 'usr_default' AND (google_id IS NULL OR google_id = '')")
    default_row = cursor.fetchone()
    if default_row:
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

    # 4. If usr_default was already claimed, create a new user and copy default history
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, google_id, last_login)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, clean_email, name, picture or "", google_id))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())
    conn.close()

    # Automatically copy default athlete settings and history to guarantee zero data loss
    claim_or_copy_default_data_to_user(user_id)
    return user

def create_or_get_dev_user(email: str, name: str, picture: Optional[str] = None) -> Dict[str, Any]:
    """Helper for dev/testing authentication with automatic default data preservation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    clean_email = email.strip().lower()
    cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET name = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?", (name, row["id"]))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (row["id"],))
        user = dict(cursor.fetchone())
        conn.close()
        return user

    # Check if usr_default is unclaimed and can be adopted
    cursor.execute("SELECT * FROM users WHERE id = 'usr_default' AND (google_id IS NULL OR google_id = '') AND (email = 'athlete@powersync.local' OR email = 'default@powersync.local')")
    default_row = cursor.fetchone()
    if default_row:
        cursor.execute("UPDATE users SET email = ?, name = ?, picture = COALESCE(?, picture), last_login = CURRENT_TIMESTAMP WHERE id = 'usr_default'", (clean_email, name, picture or ""))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = 'usr_default'")
        user = dict(cursor.fetchone())
        conn.close()
        return user

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    cursor.execute("""
        INSERT INTO users (id, email, name, picture, last_login)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, clean_email, name, picture or ""))
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cursor.fetchone())
    conn.close()
    return user

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

def get_default_or_guest_user() -> Dict[str, Any]:
    """Returns the default primary athlete profile."""
    u = get_user_by_id(DEFAULT_USER_ID)
    if u:
        return u
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
    return user

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
