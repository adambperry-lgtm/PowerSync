import base64
import datetime
import hashlib
import hmac
import json
import struct
import time
import uuid
from typing import Any, Dict, List, Optional
import requests

from app.database import (
    KG_TO_LBS,
    get_athlete_date,
    get_athlete_timezone,
    get_athlete_weight_kg,
    get_athlete_weight_lbs,
    get_current_user_id,
    get_db_connection,
    get_setting,
    set_athlete_weight_kg,
    set_setting,
)

# Wyze API Platform Constants (aligned with wyze-sdk protocol)
WYZE_AUTH_URL = "https://auth-prod.api.wyze.com"
WYZE_API_URL = "https://api.wyzecam.com"
WYZE_SCALE_SERVICE_URL = "https://wyze-scale-service.wyzecam.com"
WYZE_PLUTO_SERVICE_URL = "https://wyze-pluto-service.wyzecam.com"

WYZE_AUTH_API_KEY = "RckMFKbsds5p6QY3COEXc2ABwNTYY0q18ziEiSEm"
WYZE_APP_ID = "9319141212m2ik"
WYZE_APP_NAME = "com.hualai"
WYZE_APP_VERSION = "2.19.14"
WYZE_APP_VER = f"{WYZE_APP_NAME}___{WYZE_APP_VERSION}"
WYZE_SIGNING_SECRET = "wyze_app_secret_key_132"
WYZE_SC = "a626948714654991afd3c0dbd7cdb901"

SV_GET_OBJECT_LIST = "c417b62d72ee44bf933054bdca183e77"
SV_REFRESH_TOKEN = "d91914dd28b7492ab9dd17f7707d35a3"

CLASSIC_SCALE_MODELS = {"JA.SC", "JA.SC2"}
PLUTO_SCALE_MODELS = {"WL_SC2", "WL_SC3", "WL_SCU", "WL_SCLET", "WL_SCLVP"}
ALL_SCALE_MODELS = CLASSIC_SCALE_MODELS | PLUTO_SCALE_MODELS

SCALE_MODEL_NAMES = {
    "JA.SC": "Wyze Scale",
    "JA.SC2": "Wyze Scale",
    "WL_SC2": "Wyze Scale S",
    "WL_SC3": "Wyze Scale X",
    "WL_SCU": "Wyze Scale Ultra",
    "WL_SCLET": "Wyze Scale BodyScan",
    "WL_SCLVP": "Wyze Scale Ultra BodyScan",
}


def _md5_hex(val: str) -> str:
    return hashlib.md5(val.encode("utf-8")).hexdigest()


def _triple_md5(password: str) -> str:
    return _md5_hex(_md5_hex(_md5_hex(password)))


def _nonce_ms() -> int:
    return int(round(time.time() * 1000))


def _request_id(nonce: int) -> str:
    return _md5_hex(_md5_hex(str(nonce)))


def _dynamic_signature(body_str: str, access_token: Optional[str] = None, secret: Optional[str] = WYZE_SIGNING_SECRET) -> str:
    tok_str = access_token or ""
    sec_str = secret or ""
    signing_key = _md5_hex(f"{tok_str}{sec_str}").encode("utf-8")
    return hmac.new(signing_key, body_str.encode("utf-8"), hashlib.md5).hexdigest()


def _generate_totp(secret: str) -> Optional[str]:
    """Pure-Python RFC 6238 TOTP generator for optional Wyze 2FA TOTP secrets."""
    try:
        clean = secret.strip().replace(" ", "").upper()
        padding = len(clean) % 8
        if padding != 0:
            clean += "=" * (8 - padding)
        key = base64.b32decode(clean, casefold=True)
        counter = int(time.time()) // 30
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
        return f"{code:06d}"
    except Exception:
        return None


def _get_phone_id(user_id: str) -> str:
    phone_id = get_setting("wyze_phone_id", None, user_id=user_id)
    if not phone_id or not isinstance(phone_id, str):
        phone_id = str(uuid.uuid4())
        set_setting("wyze_phone_id", phone_id, user_id=user_id)
    return phone_id


def login_wyze(
    email: str,
    password: str,
    key_id: str,
    api_key: str,
    totp_code: Optional[str] = None,
    totp_secret: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Authenticates with the Wyze Auth API using Email, Password, Developer Key ID, and API Key.
    Supports optional TOTP 2FA verification code or TOTP secret.
    """
    uid = user_id or get_current_user_id()
    clean_email = (email or "").strip()
    clean_password = (password or "").strip()
    clean_key_id = (key_id or "").strip()
    clean_api_key = (api_key or "").strip()

    if not clean_email or not clean_password or not clean_key_id or not clean_api_key:
        return {
            "success": False,
            "error": "Wyze Email, Password, Key ID, and API Key are all required.",
        }

    phone_id = _get_phone_id(uid)
    nonce = _nonce_ms()
    hashed_password = _triple_md5(clean_password)

    payload = {
        "email": clean_email,
        "password": hashed_password,
        "nonce": str(nonce),
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    sig2 = _dynamic_signature(body_str, access_token=None, secret=None)

    headers = {
        "Content-Type": "application/json;charset=utf-8",
        "Accept-Encoding": "gzip",
        "User-Agent": "wyze-sdk-2.1.0",
        "appid": WYZE_APP_ID,
        "appinfo": f"wyze_android_{WYZE_APP_VERSION}",
        "phoneid": phone_id,
        "access_token": "",
        "requestid": _request_id(nonce),
        "signature2": sig2,
        "x-api-key": WYZE_AUTH_API_KEY,
        "keyid": clean_key_id,
        "apikey": clean_api_key,
    }

    try:
        resp = requests.post(
            f"{WYZE_AUTH_URL}/api/user/login",
            data=body_str,
            headers=headers,
            timeout=20,
        )
        if resp.status_code >= 400:
            try:
                err_json = resp.json()
                err_msg = err_json.get("description") or err_json.get("msg") or err_json.get("message") or f"HTTP {resp.status_code}"
            except Exception:
                err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return {
                "success": False,
                "error": f"Wyze authentication failed ({err_msg}). Note: If you sign in with Apple ID, make sure you set a Wyze password via 'Forgot Password' on the Wyze login page first.",
            }

        data = resp.json()
    except Exception as e:
        return {"success": False, "error": f"Network error connecting to Wyze Auth server: {str(e)}"}

    # Check if MFA/2FA is required
    if not data.get("access_token") and data.get("mfa_options"):
        mfa_options = data.get("mfa_options") or []
        if "TotpVerificationCode" in mfa_options:
            code_to_use = (totp_code or "").strip()
            if not code_to_use and totp_secret:
                code_to_use = _generate_totp(totp_secret) or ""
            if not code_to_use:
                return {
                    "success": False,
                    "mfa_required": True,
                    "error": "Your Wyze account has 2FA enabled. Please enter your 6-digit authenticator code (or TOTP Secret Key) and click Connect again.",
                }
            totp_apps = (data.get("mfa_details") or {}).get("totp_apps") or []
            verification_id = totp_apps[0].get("app_id") if totp_apps else ""
            nonce2 = _nonce_ms()
            mfa_payload = {
                "email": clean_email,
                "password": hashed_password,
                "mfa_type": "TotpVerificationCode",
                "verification_id": verification_id,
                "verification_code": code_to_use,
                "nonce": str(nonce2),
            }
            mfa_body = json.dumps(mfa_payload, separators=(",", ":"))
            mfa_headers = dict(headers)
            mfa_headers["requestid"] = _request_id(nonce2)
            mfa_headers["signature2"] = _dynamic_signature(mfa_body, access_token=None, secret=None)
            try:
                mfa_resp = requests.post(
                    f"{WYZE_AUTH_URL}/api/user/login",
                    data=mfa_body,
                    headers=mfa_headers,
                    timeout=20,
                )
                data = mfa_resp.json()
            except Exception as e:
                return {"success": False, "error": f"Wyze 2FA verification failed: {str(e)}"}

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    wyze_user_id = data.get("user_id")

    if not access_token:
        desc = data.get("description") or data.get("msg") or data.get("error") or "Invalid credentials or missing access_token"
        return {"success": False, "error": f"Wyze login rejected: {desc}"}

    # Save credentials & tokens scoped to user_id
    set_setting("wyze_email", clean_email, user_id=uid)
    set_setting("wyze_password", clean_password, user_id=uid)
    set_setting("wyze_key_id", clean_key_id, user_id=uid)
    set_setting("wyze_api_key", clean_api_key, user_id=uid)
    if totp_secret and totp_secret.strip():
        set_setting("wyze_totp_secret", totp_secret.strip(), user_id=uid)

    tokens_obj = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "wyze_user_id": wyze_user_id,
        "email": clean_email,
        "obtained_at": time.time(),
    }
    set_setting("wyze_tokens", tokens_obj, user_id=uid)
    return {"success": True, "tokens": tokens_obj}


def refresh_wyze_token(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Refreshes the Wyze access token or re-logs in using saved credentials."""
    uid = user_id or get_current_user_id()
    tokens = get_setting("wyze_tokens", None, user_id=uid)
    phone_id = _get_phone_id(uid)

    if isinstance(tokens, dict) and tokens.get("refresh_token") and tokens.get("access_token"):
        payload = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "app_name": WYZE_APP_NAME,
            "app_ver": WYZE_APP_VER,
            "app_version": WYZE_APP_VERSION,
            "phone_id": phone_id,
            "phone_system_type": "2",
            "sc": WYZE_SC,
            "sv": SV_REFRESH_TOKEN,
            "ts": _nonce_ms(),
        }
        try:
            resp = requests.post(
                f"{WYZE_API_URL}/app/user/refresh_token",
                json=payload,
                headers={"User-Agent": "okhttp/4.7.2", "Content-Type": "application/json;charset=utf-8"},
                timeout=15,
            )
            if resp.status_code == 200:
                res_json = resp.json()
                new_data = res_json.get("data") or {}
                if new_data.get("access_token"):
                    tokens["access_token"] = new_data["access_token"]
                    if new_data.get("refresh_token"):
                        tokens["refresh_token"] = new_data["refresh_token"]
                    tokens["obtained_at"] = time.time()
                    set_setting("wyze_tokens", tokens, user_id=uid)
                    return tokens
        except Exception:
            pass

    # Fallback: Re-login if saved credentials exist
    saved_email = get_setting("wyze_email", "", user_id=uid)
    saved_password = get_setting("wyze_password", "", user_id=uid)
    saved_key_id = get_setting("wyze_key_id", "", user_id=uid)
    saved_api_key = get_setting("wyze_api_key", "", user_id=uid)
    saved_totp = get_setting("wyze_totp_secret", "", user_id=uid)

    if saved_email and saved_password and saved_key_id and saved_api_key:
        res = login_wyze(
            email=saved_email,
            password=saved_password,
            key_id=saved_key_id,
            api_key=saved_api_key,
            totp_secret=saved_totp,
            user_id=uid,
        )
        if res.get("success"):
            return res.get("tokens")

    return None


def _wyze_signed_get(base_url: str, path: str, params: Dict[str, Any], access_token: str, phone_id: str, app_id: str = WYZE_APP_ID) -> Optional[Dict[str, Any]]:
    """Executes a signed GET request to Wyze Pluto or Scale microservice."""
    nonce = _nonce_ms()
    req_params = dict(params or {})
    req_params["nonce"] = str(nonce)

    sorted_items = sorted(req_params.items(), key=lambda x: x[0])
    sorted_qs = "&".join(f"{k}={v}" for k, v in sorted_items)
    sig2 = _dynamic_signature(sorted_qs, access_token=access_token, secret=WYZE_SIGNING_SECRET)

    headers = {
        "Accept-Encoding": "gzip",
        "User-Agent": f"wyze_android_{WYZE_APP_VERSION}",
        "appid": app_id,
        "appinfo": f"wyze_android_{WYZE_APP_VERSION}",
        "phoneid": phone_id,
        "access_token": access_token,
        "requestid": _request_id(nonce),
        "signature2": sig2,
    }
    try:
        resp = requests.get(f"{base_url}{path}", params=req_params, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[PowerSync] Wyze signed GET error ({path}): {e}")
    return None


def discover_wyze_scales(access_token: str, phone_id: str) -> List[Dict[str, Any]]:
    """Queries the user's Wyze home object list and filters for Smart Scale devices."""
    payload = {
        "access_token": access_token,
        "app_name": WYZE_APP_NAME,
        "app_ver": WYZE_APP_VER,
        "app_version": WYZE_APP_VERSION,
        "phone_id": phone_id,
        "phone_system_type": "2",
        "sc": WYZE_SC,
        "sv": SV_GET_OBJECT_LIST,
        "ts": _nonce_ms(),
    }
    scales = []
    try:
        resp = requests.post(
            f"{WYZE_API_URL}/app/v2/home_page/get_object_list",
            json=payload,
            headers={"User-Agent": "okhttp/4.7.2", "Content-Type": "application/json;charset=utf-8"},
            timeout=20,
        )
        if resp.status_code == 200:
            body = resp.json()
            device_list = (body.get("data") or {}).get("device_list") or []
            for dev in device_list:
                model = str(dev.get("product_model") or "")
                ptype = str(dev.get("product_type") or "")
                nickname = str(dev.get("nickname") or "")
                if (
                    model in ALL_SCALE_MODELS
                    or "scale" in ptype.lower()
                    or "scale" in model.lower()
                    or model.startswith("WL_SC")
                    or model.startswith("JA.SC")
                ):
                    scales.append({
                        "mac": dev.get("mac") or "",
                        "product_model": model or "WL_SC2",
                        "product_type": ptype or "WyzeScale",
                        "nickname": nickname or SCALE_MODEL_NAMES.get(model, "Wyze Smart Scale"),
                        "model_label": SCALE_MODEL_NAMES.get(model, f"Wyze Scale ({model})"),
                    })
    except Exception as e:
        print(f"[PowerSync] Error listing Wyze devices: {e}")
    return scales


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except Exception:
        return None


def _normalize_wyze_record(raw: Dict[str, Any], athlete_tz: Any, default_mac: str = "", default_model: str = "") -> Optional[Dict[str, Any]]:
    """Normalizes a raw Wyze scale record (from either Pluto or Scale service) into standard kg & lbs fields."""
    if not isinstance(raw, dict):
        return None

    raw_weight = _safe_float(raw.get("weight") or raw.get("current_weight"))
    if not raw_weight or raw_weight <= 10.0:
        return None

    # Wyze scale services store weight in kg (e.g. 74.8 kg).
    # Safeguard: if a value > 205 is ever returned, check unit; standard Wyze scale range is 5-180 kg.
    unit_hint = str(raw.get("unit") or "").lower()
    if unit_hint in ("lb", "lbs"):
        weight_lbs = round(raw_weight, 1)
        weight_kg = round(raw_weight / KG_TO_LBS, 2)
    else:
        weight_kg = round(raw_weight, 2)
        weight_lbs = round(weight_kg * KG_TO_LBS, 1)

    raw_ts = raw.get("measure_ts") or raw.get("create_time") or raw.get("update_time") or int(time.time() * 1000)
    try:
        ts_int = int(float(raw_ts))
        # Normalize seconds vs milliseconds
        if ts_int < 10_000_000_000:
            ts_sec = ts_int
            ts_ms = ts_int * 1000
        else:
            ts_ms = ts_int
            ts_sec = ts_int // 1000
    except Exception:
        ts_sec = int(time.time())
        ts_ms = ts_sec * 1000

    dt_local = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc).astimezone(athlete_tz)
    date_str = dt_local.strftime("%Y-%m-%d")

    rec_id = str(raw.get("data_id") or raw.get("id") or f"wyze_{ts_ms}")
    body_fat = _safe_float(raw.get("body_fat"))
    body_water = _safe_float(raw.get("body_water"))
    muscle_raw = _safe_float(raw.get("muscle") or raw.get("skeletal_muscle"))
    bone_raw = _safe_float(raw.get("bone_mineral"))
    bmi = _safe_float(raw.get("bmi"))
    bmr = _safe_float(raw.get("bmr"))
    visceral_fat = _safe_float(raw.get("body_vfr"))
    protein_pct = _safe_float(raw.get("protein"))
    metabolic_age_raw = _safe_float(raw.get("metabolic_age"))
    metabolic_age = int(round(metabolic_age_raw)) if metabolic_age_raw else None

    lean_body_mass_kg = _safe_float(raw.get("lean_body_mass"))
    if not lean_body_mass_kg and body_fat and 2.0 < body_fat < 75.0:
        lean_body_mass_kg = round(weight_kg * (1.0 - (body_fat / 100.0)), 2)

    return {
        "id": rec_id,
        "date": date_str,
        "measure_ts": ts_ms,
        "weight_kg": weight_kg,
        "weight_lbs": weight_lbs,
        "body_fat_pct": round(body_fat, 1) if body_fat else None,
        "body_water_pct": round(body_water, 1) if body_water else None,
        "muscle_mass_kg": round(muscle_raw, 2) if muscle_raw else None,
        "lean_body_mass_kg": round(lean_body_mass_kg, 2) if lean_body_mass_kg else None,
        "bone_mass_kg": round(bone_raw, 2) if bone_raw else None,
        "bmi": round(bmi, 1) if bmi else None,
        "bmr": round(bmr, 0) if bmr else None,
        "visceral_fat": round(visceral_fat, 1) if visceral_fat else None,
        "metabolic_age": metabolic_age,
        "protein_pct": round(protein_pct, 1) if protein_pct else None,
        "device_mac": str(raw.get("mac") or raw.get("device_id") or default_mac or ""),
        "device_model": default_model or "WyzeScale",
        "raw_json": json.dumps(raw),
    }


def fetch_latest_wyze_scale_data(days: int = 90, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Connects to Wyze Scale & Pluto cloud microservices, pulls scale weigh-in records,
    saves them to SQLite `wyze_scale_records`, and updates the athlete's active weight (`kg` & `lbs`).
    """
    uid = user_id or get_current_user_id()
    tokens = get_setting("wyze_tokens", None, user_id=uid)
    if not isinstance(tokens, dict) or not tokens.get("access_token"):
        tokens = refresh_wyze_token(user_id=uid)
        if not tokens or not tokens.get("access_token"):
            return {
                "success": False,
                "auth_expired": True,
                "error": "Wyze Smart Scale is not connected or session expired. Please connect in Settings.",
            }

    # Proactively refresh if token is older than 12 hours
    obtained_at = float(tokens.get("obtained_at") or 0)
    if time.time() - obtained_at > 43200:
        refreshed = refresh_wyze_token(user_id=uid)
        if refreshed and refreshed.get("access_token"):
            tokens = refreshed

    access_token = tokens["access_token"]
    wyze_user_id = tokens.get("wyze_user_id")
    phone_id = _get_phone_id(uid)
    athlete_tz = get_athlete_timezone(uid)

    # 1. Discover scales attached to the Wyze account
    scales = discover_wyze_scales(access_token, phone_id)
    primary_scale = scales[0] if scales else {
        "mac": tokens.get("scale_mac", ""),
        "product_model": tokens.get("scale_model", "WL_SC2"),
        "nickname": tokens.get("scale_name", "Wyze Smart Scale"),
        "model_label": "Wyze Smart Scale",
    }

    if scales:
        tokens["scale_mac"] = primary_scale["mac"]
        tokens["scale_model"] = primary_scale["product_model"]
        tokens["scale_name"] = primary_scale["nickname"]
        set_setting("wyze_tokens", tokens, user_id=uid)

    now_epoch_ms = int(time.time() * 1000)
    start_epoch_ms = int((time.time() - (days * 86400)) * 1000)
    now_epoch_sec = int(time.time())
    start_epoch_sec = int(time.time() - (days * 86400))

    raw_records: List[Dict[str, Any]] = []

    # Candidate family_member_ids to query (the authenticated user_id + any family members on the scale)
    candidate_member_ids = []
    if wyze_user_id:
        candidate_member_ids.append(str(wyze_user_id))
    candidate_member_ids.append("")  # Unfiltered fallback

    for sc_dev in (scales or [primary_scale]):
        did = sc_dev.get("mac") or ""
        if did:
            for svc_url, prefix in [(WYZE_PLUTO_SERVICE_URL, "/plugin/pluto"), (WYZE_SCALE_SERVICE_URL, "/plugin/scale")]:
                fam_res = _wyze_signed_get(svc_url, f"{prefix}/get_family_member", {"device_id": did}, access_token, phone_id)
                if fam_res and isinstance(fam_res.get("data"), list):
                    for fm in fam_res["data"]:
                        fm_id = fm.get("id") or fm.get("family_member_id") or fm.get("user_id")
                        if fm_id and str(fm_id) not in candidate_member_ids:
                            candidate_member_ids.insert(0, str(fm_id))

    # 2. Query Pluto Service (Scale S, Scale X, Scale Ultra, Scale BodyScan)
    for member_id in candidate_member_ids[:4]:
        for start_v, end_v in [(start_epoch_ms, now_epoch_ms), (start_epoch_sec, now_epoch_sec)]:
            params = {
                "start_time": str(start_v),
                "end_time": str(end_v),
                "forward": "0",
            }
            if member_id:
                params["family_member_id"] = member_id
            res = _wyze_signed_get(WYZE_PLUTO_SERVICE_URL, "/plugin/pluto/get_record_range", params, access_token, phone_id)
            if res and isinstance(res.get("data"), list) and len(res["data"]) > 0:
                raw_records.extend(res["data"])
                break
        latest_params = {"family_member_id": member_id} if member_id else {}
        latest_res = _wyze_signed_get(WYZE_PLUTO_SERVICE_URL, "/plugin/pluto/get_latest_record", latest_params, access_token, phone_id)
        if latest_res and latest_res.get("data"):
            d_obj = latest_res["data"]
            if isinstance(d_obj, list):
                raw_records.extend(d_obj)
            elif isinstance(d_obj, dict):
                raw_records.append(d_obj)

    # 3. Query Classic Scale Service (Original Wyze Scale JA.SC / JA.SC2)
    for member_id in candidate_member_ids[:4]:
        for start_v, end_v in [(start_epoch_ms, now_epoch_ms), (start_epoch_sec, now_epoch_sec)]:
            params = {
                "start_time": str(start_v),
                "end_time": str(end_v),
            }
            if member_id:
                params["family_member_id"] = member_id
            res = _wyze_signed_get(WYZE_SCALE_SERVICE_URL, "/plugin/scale/get_record_range", params, access_token, phone_id)
            if res and isinstance(res.get("data"), list) and len(res["data"]) > 0:
                raw_records.extend(res["data"])
                break
        latest_params = {"family_member_id": member_id} if member_id else {}
        latest_res = _wyze_signed_get(WYZE_SCALE_SERVICE_URL, "/plugin/scale/get_latest_record", latest_params, access_token, phone_id)
        if latest_res and latest_res.get("data"):
            d_obj = latest_res["data"]
            if isinstance(d_obj, list):
                raw_records.extend(d_obj)
            elif isinstance(d_obj, dict):
                raw_records.append(d_obj)

    # Deduplicate and normalize records
    normalized_by_id: Dict[str, Dict[str, Any]] = {}
    for raw in raw_records:
        norm = _normalize_wyze_record(
            raw,
            athlete_tz=athlete_tz,
            default_mac=primary_scale.get("mac", ""),
            default_model=primary_scale.get("product_model", "WyzeScale"),
        )
        if norm:
            normalized_by_id[norm["id"]] = norm

    normalized_list = sorted(normalized_by_id.values(), key=lambda r: r["measure_ts"], reverse=True)

    if normalized_list:
        conn = get_db_connection()
        cursor = conn.cursor()
        for rec in normalized_list:
            cursor.execute(
                """
                INSERT INTO wyze_scale_records (
                    user_id, id, date, measure_ts, weight_kg, weight_lbs,
                    body_fat_pct, body_water_pct, muscle_mass_kg, lean_body_mass_kg,
                    bone_mass_kg, bmi, bmr, visceral_fat, metabolic_age, protein_pct,
                    device_mac, device_model, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, id) DO UPDATE SET
                    date = excluded.date,
                    measure_ts = excluded.measure_ts,
                    weight_kg = excluded.weight_kg,
                    weight_lbs = excluded.weight_lbs,
                    body_fat_pct = COALESCE(excluded.body_fat_pct, wyze_scale_records.body_fat_pct),
                    body_water_pct = COALESCE(excluded.body_water_pct, wyze_scale_records.body_water_pct),
                    muscle_mass_kg = COALESCE(excluded.muscle_mass_kg, wyze_scale_records.muscle_mass_kg),
                    lean_body_mass_kg = COALESCE(excluded.lean_body_mass_kg, wyze_scale_records.lean_body_mass_kg),
                    bone_mass_kg = COALESCE(excluded.bone_mass_kg, wyze_scale_records.bone_mass_kg),
                    bmi = COALESCE(excluded.bmi, wyze_scale_records.bmi),
                    bmr = COALESCE(excluded.bmr, wyze_scale_records.bmr),
                    visceral_fat = COALESCE(excluded.visceral_fat, wyze_scale_records.visceral_fat),
                    metabolic_age = COALESCE(excluded.metabolic_age, wyze_scale_records.metabolic_age),
                    protein_pct = COALESCE(excluded.protein_pct, wyze_scale_records.protein_pct),
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    uid,
                    rec["id"],
                    rec["date"],
                    rec["measure_ts"],
                    rec["weight_kg"],
                    rec["weight_lbs"],
                    rec["body_fat_pct"],
                    rec["body_water_pct"],
                    rec["muscle_mass_kg"],
                    rec["lean_body_mass_kg"],
                    rec["bone_mass_kg"],
                    rec["bmi"],
                    rec["bmr"],
                    rec["visceral_fat"],
                    rec["metabolic_age"],
                    rec["protein_pct"],
                    rec["device_mac"],
                    rec["device_model"],
                    rec["raw_json"],
                ),
            )
        conn.commit()
        conn.close()

        # Update active athlete weight (kg & lbs) from the newest scale measurement
        latest = normalized_list[0]
        set_athlete_weight_kg(latest["weight_kg"], user_id=uid)

    now_ts = time.time()
    set_setting("last_wyze_sync_timestamp", now_ts, user_id=uid)

    summary = get_wyze_scale_summary(user_id=uid)
    return {
        "success": True,
        "count": len(normalized_list),
        "scales_found": len(scales),
        "scale_name": primary_scale.get("nickname", "Wyze Smart Scale"),
        "summary": summary,
    }


def get_wyze_scale_summary(user_id: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    """
    Returns the athlete's latest Wyze Smart Scale metrics (displayed in lbs, with W/kg power reference),
    7-day and 30-day weight trends, and recent weigh-in history.
    """
    uid = user_id or get_current_user_id()
    tokens = get_setting("wyze_tokens", None, user_id=uid)
    has_creds = bool(
        get_setting("wyze_email", "", user_id=uid)
        and get_setting("wyze_password", "", user_id=uid)
        and get_setting("wyze_key_id", "", user_id=uid)
        and get_setting("wyze_api_key", "", user_id=uid)
    )
    wyze_connected = bool((isinstance(tokens, dict) and tokens.get("access_token")) or has_creds)
    ftp = int(get_setting("athlete_ftp", 250, user_id=uid) or 250)
    safe_limit = max(5, min(100, int(limit or 30)))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM wyze_scale_records
        WHERE user_id = ?
        ORDER BY measure_ts DESC
        LIMIT ?
        """,
        (uid, max(30, safe_limit)),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    weight_kg = get_athlete_weight_kg(user_id=uid)
    weight_lbs = get_athlete_weight_lbs(user_id=uid)
    ftp_w_kg = round(ftp / max(30.0, weight_kg), 2)

    if rows:
        latest_row = rows[0]
        latest_kg = round(float(latest_row["weight_kg"]), 2)
        latest_lbs = round(float(latest_row["weight_lbs"] or (latest_kg * KG_TO_LBS)), 1)
        ftp_w_kg = round(ftp / max(30.0, latest_kg), 2)

        # Compute 7-day and 30-day weight change in lbs
        latest_ts = int(latest_row["measure_ts"])
        seven_days_ago_ms = latest_ts - (7 * 86400 * 1000)
        older_7d = [r for r in rows[1:] if int(r["measure_ts"]) <= seven_days_ago_ms]
        if not older_7d and len(rows) > 1:
            older_7d = [rows[min(len(rows) - 1, 6)]]
        delta_7d_lbs = round(latest_lbs - float(older_7d[0]["weight_lbs"]), 1) if older_7d else 0.0

        older_30d = rows[-1] if len(rows) > 1 else None
        delta_30d_lbs = round(latest_lbs - float(older_30d["weight_lbs"]), 1) if older_30d else 0.0

        muscle_kg = latest_row.get("muscle_mass_kg")
        muscle_lbs = round(float(muscle_kg) * KG_TO_LBS, 1) if muscle_kg else None
        lbm_kg = latest_row.get("lean_body_mass_kg")
        lbm_lbs = round(float(lbm_kg) * KG_TO_LBS, 1) if lbm_kg else None
        bone_kg = latest_row.get("bone_mass_kg")
        bone_lbs = round(float(bone_kg) * KG_TO_LBS, 1) if bone_kg else None

        try:
            athlete_tz = get_athlete_timezone(user_id=uid)
            measured_iso = datetime.datetime.fromtimestamp(latest_ts / 1000.0, tz=datetime.timezone.utc).astimezone(athlete_tz).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            measured_iso = latest_row["date"]

        latest_obj = {
            "id": latest_row["id"],
            "date": latest_row["date"],
            "measure_ts": latest_ts,
            "measured_at_iso": measured_iso,
            "weight_lbs": latest_lbs,
            "weight_kg": latest_kg,
            "ftp_w_kg": ftp_w_kg,
            "delta_7d_lbs": delta_7d_lbs,
            "delta_30d_lbs": delta_30d_lbs,
            "body_fat_pct": latest_row.get("body_fat_pct"),
            "body_water_pct": latest_row.get("body_water_pct"),
            "muscle_mass_lbs": muscle_lbs,
            "muscle_mass_kg": muscle_kg,
            "lean_body_mass_lbs": lbm_lbs,
            "bone_mass_lbs": bone_lbs,
            "bmi": latest_row.get("bmi"),
            "bmr": latest_row.get("bmr"),
            "visceral_fat": latest_row.get("visceral_fat"),
            "metabolic_age": latest_row.get("metabolic_age"),
            "protein_pct": latest_row.get("protein_pct"),
        }

        history_items = []
        for r in rows[:safe_limit]:
            r_kg = round(float(r["weight_kg"]), 2)
            r_lbs = round(float(r["weight_lbs"] or (r_kg * KG_TO_LBS)), 1)
            history_items.append({
                "id": r["id"],
                "date": r["date"],
                "measure_ts": r["measure_ts"],
                "weight_lbs": r_lbs,
                "weight_kg": r_kg,
                "w_kg_at_ftp": round(ftp / max(30.0, r_kg), 2),
                "body_fat_pct": r.get("body_fat_pct"),
                "body_water_pct": r.get("body_water_pct"),
                "muscle_mass_lbs": round(float(r["muscle_mass_kg"]) * KG_TO_LBS, 1) if r.get("muscle_mass_kg") else None,
                "bmi": r.get("bmi"),
            })

        return {
            "connected": wyze_connected,
            "has_scale_records": True,
            "scale_name": (tokens or {}).get("scale_name", "Wyze Smart Scale") if isinstance(tokens, dict) else "Wyze Smart Scale",
            "scale_model": (tokens or {}).get("scale_model", "") if isinstance(tokens, dict) else "",
            "last_sync_date": latest_row["date"],
            "weight_lbs": latest_lbs,
            "weight_kg": latest_kg,
            "ftp_w_kg": ftp_w_kg,
            "delta_7d_lbs": delta_7d_lbs,
            "delta_30d_lbs": delta_30d_lbs,
            "body_fat_pct": latest_row.get("body_fat_pct"),
            "body_water_pct": latest_row.get("body_water_pct"),
            "muscle_mass_lbs": muscle_lbs,
            "muscle_mass_kg": muscle_kg,
            "lean_body_mass_lbs": lbm_lbs,
            "bone_mass_lbs": bone_lbs,
            "bmi": latest_row.get("bmi"),
            "bmr": latest_row.get("bmr"),
            "visceral_fat": latest_row.get("visceral_fat"),
            "metabolic_age": latest_row.get("metabolic_age"),
            "protein_pct": latest_row.get("protein_pct"),
            "latest": latest_obj,
            "history": history_items,
        }

    # Fallback when no Wyze scale records are stored yet (uses manual/configured weight in lbs & kg)
    return {
        "connected": wyze_connected,
        "has_scale_records": False,
        "scale_name": (tokens or {}).get("scale_name", "Wyze Smart Scale") if isinstance(tokens, dict) else "Wyze Smart Scale",
        "scale_model": (tokens or {}).get("scale_model", "") if isinstance(tokens, dict) else "",
        "last_sync_date": None,
        "weight_lbs": weight_lbs,
        "weight_kg": weight_kg,
        "ftp_w_kg": ftp_w_kg,
        "delta_7d_lbs": 0.0,
        "delta_30d_lbs": 0.0,
        "body_fat_pct": None,
        "body_water_pct": None,
        "muscle_mass_lbs": None,
        "muscle_mass_kg": None,
        "lean_body_mass_lbs": None,
        "bone_mass_lbs": None,
        "bmi": None,
        "bmr": None,
        "visceral_fat": None,
        "metabolic_age": None,
        "protein_pct": None,
        "latest": None,
        "history": [],
    }

