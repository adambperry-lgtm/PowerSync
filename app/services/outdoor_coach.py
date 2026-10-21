import datetime
import math
import json
import ast
from typing import Dict, Any, List, Optional
from app.database import get_db_connection, get_setting, get_current_user_id, get_athlete_date
from app.services.mock_data import get_mock_strava_activities

def decode_polyline(polyline_str: str) -> List[List[float]]:
    """Decodes Google / Strava encoded polyline string into [[lat, lng], ...]."""
    if not polyline_str:
        return []
    index, lat, lng = 0, 0, 0
    coordinates = []
    changes = {'latitude': 0, 'longitude': 0}
    try:
        while index < len(polyline_str):
            for unit in ['latitude', 'longitude']: 
                shift, result = 0, 0
                while True:
                    byte = ord(polyline_str[index]) - 63
                    index += 1
                    result |= (byte & 0x1f) << shift
                    shift += 5
                    if not byte >= 0x20:
                        break
                if (result & 1):
                    changes[unit] = ~(result >> 1)
                else:
                    changes[unit] = (result >> 1)
            lat += changes['latitude']
            lng += changes['longitude']
            coordinates.append([round(lat / 100000.0, 5), round(lng / 100000.0, 5)])
    except Exception:
        pass
    return coordinates

def sample_coordinates(coords: List[List[float]], max_points: int = 120) -> List[List[float]]:
    """Samples down coordinate array for fast client rendering."""
    if not coords or len(coords) <= max_points:
        return coords
    step = len(coords) / float(max_points - 1)
    sampled = [coords[int(i * step)] for i in range(max_points - 1)]
    sampled.append(coords[-1])
    return sampled

def generate_svg_path(coords: List[List[float]], width: int = 400, height: int = 180, padding: int = 16):
    """
    Normalizes GPS coordinates into an SVG path string preserving aspect ratio.
    Returns (path_str, start_xy, end_xy).
    """
    if not coords or len(coords) < 2:
        return '', None, None
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    
    mid_lat = (min_lat + max_lat) / 2.0
    lat_span = max(0.0001, (max_lat - min_lat) * math.cos(math.radians(mid_lat)))
    lng_span = max(0.0001, (max_lng - min_lng))
    
    draw_w = width - 2 * padding
    draw_h = height - 2 * padding
    
    scale = min(draw_w / lng_span, draw_h / lat_span)
    
    x_offset = padding + (draw_w - (lng_span * scale)) / 2.0
    y_offset = padding + (draw_h - (lat_span * scale)) / 2.0
    
    path_cmds = []
    start_pt = None
    end_pt = None
    for i, (lat, lng) in enumerate(coords):
        x = round(x_offset + (lng - min_lng) * scale, 1)
        y = round(y_offset + (max_lat - lat) * math.cos(math.radians(mid_lat)) * scale, 1)
        cmd = 'M' if i == 0 else 'L'
        path_cmds.append(f'{cmd}{x},{y}')
        if i == 0:
            start_pt = [x, y]
        if i == len(coords) - 1:
            end_pt = [x, y]
            
    return ' '.join(path_cmds), start_pt, end_pt

def get_candidate_outdoor_rides() -> List[Dict[str, Any]]:
    """
    Retrieves outdoor rides from SQLite database (or falls back to mock data).
    Filters out virtual rides, commutes, very short errand rides (< 20 min).
    """
    strava_tokens = get_setting("strava_tokens", None)
    rides: List[Dict[str, Any]] = []

    if strava_tokens:
        uid = get_current_user_id()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, name, sport_type, start_date, moving_time_sec, distance_meters,
                   total_elevation_gain, average_watts, weighted_average_watts,
                   average_heartrate, max_heartrate, suffer_score, kilojoules, raw_json
            FROM strava_activities
            WHERE user_id = ?
              AND (sport_type = 'Ride' OR sport_type != 'VirtualRide')
              AND moving_time_sec >= 1200
            ORDER BY start_date DESC
            LIMIT 40
        """, (uid,))
        rows = c.fetchall()
        conn.close()
        for r in rows:
            r_dict = dict(r)
            raw = r_dict.pop("raw_json", None)
            poly = None
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
                    poly = raw_d.get("map", {}).get("summary_polyline")
            r_dict["summary_polyline"] = poly
            rides.append(r_dict)

    if not rides:
        # Fall back to mock activities that qualify as outdoor rides
        all_mock = get_mock_strava_activities()
        rides = [
            a for a in all_mock 
            if a.get("sport_type") in ("Ride", "OutdoorRide") or "Zwift" not in a.get("name", "")
        ]

    # Further filter out rides that are clearly just cool-downs or errands
    filtered = []
    for r in rides:
        name_lower = r.get("name", "").lower()
        if any(ign in name_lower for ign in ["doordash", "errand", "commute", "cool down"]) and r.get("moving_time_sec", 0) < 1800:
            continue
        filtered.append(r)

    return filtered

def format_relative_date(date_str: str) -> str:
    """Formats an ISO date string into a friendly string like 'Oct 2, 2026 (10 days ago)'."""
    if not date_str:
        return ""
    try:
        clean = date_str[:10]
        dt = datetime.date.fromisoformat(clean)
        today = get_athlete_date()
        delta = (today - dt).days
        formatted = dt.strftime("%b %-d, %Y")
        if delta == 0:
            return f"{formatted} (Today)"
        elif delta == 1:
            return f"{formatted} (Yesterday)"
        elif delta < 30:
            return f"{formatted} ({delta} days ago)"
        else:
            return f"{formatted} ({delta // 30}mo ago)"
    except Exception:
        return date_str[:10]

def build_outdoor_ride_recommendation(
    recovery_score: int,
    hrv_rmssd: float,
    sleep_score: int,
    recent_volume_hours: float,
    recent_high_intensity: bool,
    today_strain: float = 0.0,
    trailing_7d_strain_avg: float = 0.0,
    trailing_7d_high_strain_count: int = 0,
    recent_weighted_strain: float = 0.0,
    yesterday_strain: float = 0.0,
    total_tss: int = 0,
    acute_weighted_tss: int = 0,
    yesterday_tss: int = 0,
    load_profile: str = "Evenly Distributed",
    strain_profile: str = "Evenly Distributed",
    target_duration_min: int = 60,
    ftp: int = 250,
    user_note: str = "",
    today_activities: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Analyzes athlete's Strava outdoor ride history and selects the best matching
    prior ride as an actionable template for today's training.
    """
    candidates = get_candidate_outdoor_rides()

    import re
    note_clean = (user_note or "").strip().lower()
    if note_clean:
        dur_min_match = re.search(r'\b(\d{2,3})\s*(?:m|min|mins|minute|minutes)\b', note_clean)
        dur_hr_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b', note_clean)
        if dur_min_match:
            parsed_d = int(dur_min_match.group(1))
            if 20 <= parsed_d <= 300:
                target_duration_min = parsed_d
        elif dur_hr_match:
            parsed_d = round(float(dur_hr_match.group(1)) * 60)
            if 20 <= parsed_d <= 300:
                target_duration_min = parsed_d

    # Determine desired physiological stimulus today
    today_acts = today_activities or []
    today_moving_min = sum(a.get("moving_time_sec", 0) for a in today_acts) // 60
    has_substantial_ride = today_moving_min >= 30 or len(today_acts) > 0
    high_strain_reached = today_strain >= 13.5 or (today_strain >= 11.5 and recovery_score <= 55)

    is_recovery_needed = (
        (has_substantial_ride or high_strain_reached) and not bool(note_clean)
    ) or recovery_score < 34

    effective_strain = recent_weighted_strain if recent_weighted_strain > 0 else trailing_7d_strain_avg
    effective_tss = acute_weighted_tss if acute_weighted_tss > 0 else total_tss

    # Recency-weighted fatigue triggers:
    # A) Recent Fatigue Surge (e.g. yesterday 200 TSS or >= 14.2 strain)
    is_recent_fatigue_surge = (
        yesterday_tss >= 80 or
        yesterday_strain >= 14.2 or
        (acute_weighted_tss >= 340 and yesterday_tss >= 50) or
        (effective_strain >= 12.0 and yesterday_strain >= 13.0) or
        load_profile == "Recent Surge (Yesterday Heavy)"
    )

    # B) Front-Loaded Supercompensated (e.g. 200 TSS was 7 days ago, yesterday was 0-30 TSS / rest)
    is_front_loaded_fresh = (
        yesterday_tss < 35 and
        yesterday_strain < 8.5 and
        (total_tss >= 160 or recent_volume_hours >= 4.0) and
        (load_profile == "Front-Loaded (Supercompensated/Fresh)" or (total_tss > 0 and acute_weighted_tss <= total_tss * 0.90))
    )

    is_yellow = (34 <= recovery_score <= 66)
    is_high_combined_load = (
        is_recent_fatigue_surge or
        (not is_front_loaded_fresh and (
            recent_volume_hours > 7.0 or
            effective_tss >= 350 or
            effective_strain >= 11.5 or
            trailing_7d_high_strain_count >= 3 or
            (recent_volume_hours >= 5.5 and effective_strain >= 10.0)
        ))
    )

    is_yesterday_surge = yesterday_tss >= 90 or yesterday_strain >= 15.0 or load_profile == "Recent Surge (Yesterday Heavy)"

    if note_clean and any(k in note_clean for k in ["recovery", "easy", "flush", "spin", "flat", "zone 1", "z1", "light"]):
        target_zone = "Active Recovery"
        target_pct_ftp = 52
        target_suffer_max = 35
        zone_badge = "Active Recovery Flush"
    elif note_clean and any(k in note_clean for k in ["zone 2", "z2", "endurance", "base", "steady", "aerobic"]):
        target_zone = "Zone 2 Aerobic Base"
        target_pct_ftp = 66
        target_suffer_max = 60
        zone_badge = "Zone 2 Aerobic Base"
    elif note_clean and any(k in note_clean for k in ["tempo", "zone 3", "z3", "rolling"]):
        target_zone = "Tempo / Muscular Endurance"
        target_pct_ftp = 80
        target_suffer_max = 80
        zone_badge = "Tempo Rolling Route"
    elif note_clean and any(k in note_clean for k in ["climb", "climbing", "hill", "hills", "punchy", "hard", "threshold", "sweet spot", "sst", "vo2"]):
        target_zone = "High Aerobic / Punchy Climbing"
        target_pct_ftp = 88
        target_suffer_max = 110
        zone_badge = "High Aerobic / Punchy"
    elif is_recovery_needed:
        target_zone = "Active Recovery"
        target_pct_ftp = 50
        target_suffer_max = 30
        zone_badge = "Active Recovery Flush"
    elif is_yellow and is_high_combined_load:
        target_zone = "Zone 2 Aerobic Base"
        target_pct_ftp = 66
        target_suffer_max = 55
        zone_badge = "Zone 2 Aerobic Base"
    elif is_yellow and not is_high_combined_load:
        target_zone = "Tempo / Muscular Endurance"
        target_pct_ftp = 80
        target_suffer_max = 75
        zone_badge = "Tempo Rolling Route"
    elif recovery_score > 66 and (is_yesterday_surge or effective_strain >= 14.0 or trailing_7d_high_strain_count >= 4):
        target_zone = "Sweet Spot / Controlled Elevation"
        target_pct_ftp = 88
        target_suffer_max = 85
        zone_badge = "Sweet Spot Rolling"
    else:
        # Green recovery with capacity for harder terrain
        target_zone = "High Aerobic / Punchy Climbing"
        target_pct_ftp = 88
        target_suffer_max = 100
        zone_badge = "High Aerobic / Punchy"

    # Score and annotate each candidate ride
    scored_rides = []
    for ride in candidates:
        r_sec = ride.get("moving_time_sec", 0)
        r_min = r_sec // 60
        r_dist_km = round(ride.get("distance_meters", 0) / 1000.0, 1)
        r_elev_m = int(ride.get("total_elevation_gain", 0))
        r_watts = ride.get("average_watts") or ride.get("weighted_average_watts") or 0.0
        r_pct_ftp = round((r_watts / max(1, ftp)) * 100) if r_watts > 0 else 70
        r_suffer = ride.get("suffer_score") or 0

        # Elevation climbing density (m per km)
        climbing_ratio = r_elev_m / max(1.0, r_dist_km)

        # 1. Duration match penalty (relative to target_duration_min)
        dur_diff = abs(r_min - target_duration_min)
        dur_score = max(0, 100 - (dur_diff * 1.5))

        # 2. Intensity match score
        pct_diff = abs(r_pct_ftp - target_pct_ftp)
        intensity_score = max(0, 100 - (pct_diff * 2.0))

        # Suffer cap penalty if athlete is fatigued
        if is_recovery_needed and r_suffer > 30:
            intensity_score -= 35
        elif is_yellow and is_high_combined_load and r_suffer > 65:
            intensity_score -= 25

        # 3. Terrain appropriateness
        terrain_score = 80
        if target_zone == "Active Recovery":
            if climbing_ratio > 12.0:
                terrain_score -= 30
        elif target_zone == "Zone 2 Aerobic Base":
            if climbing_ratio <= 14.0:
                terrain_score += 15
        elif target_zone in ("High Aerobic / Punchy Climbing", "Sweet Spot / Controlled Elevation"):
            if r_elev_m >= 350:
                terrain_score += 15

        # Total fit score (0-100)
        total_score = (dur_score * 0.45) + (intensity_score * 0.35) + (terrain_score * 0.20)
        total_score = min(99, max(40, round(total_score)))

        # Map decoding & SVG generation
        poly = ride.get("summary_polyline") or ""
        pts = decode_polyline(poly)
        sampled_pts = sample_coordinates(pts, 120)
        svg_d, start_xy, end_xy = generate_svg_path(pts, 460, 210, padding=18)
        header_svg, h_start_xy, h_end_xy = generate_svg_path(pts, 160, 80, padding=8)
        thumb_svg, _, _ = generate_svg_path(pts, 110, 48, padding=4)
        bounds = None
        if pts:
            lats = [p[0] for p in pts]
            lngs = [p[1] for p in pts]
            bounds = [[min(lats), min(lngs)], [max(lats), max(lngs)]]

        # Geometry classification
        is_loop = False
        orientation_label = "Point-to-Point"
        if pts and len(pts) >= 2:
            start_lat, start_lng = pts[0]
            end_lat, end_lng = pts[-1]
            dist_start_end = math.sqrt(((start_lat - end_lat) * 111.0)**2 + ((start_lng - end_lng) * 85.0)**2)
            if dist_start_end < 0.8:
                is_loop = True
                orientation_label = "Loop Course (Starts & finishes at same spot)"
            elif dist_start_end < 2.0:
                orientation_label = "Out-and-Back Route"
            else:
                orientation_label = "Point-to-Point Route"

        ride_annotated = {
            "id": str(ride.get("id")),
            "name": ride.get("name", "Outdoor Ride"),
            "sport_type": ride.get("sport_type", "Ride"),
            "start_date": ride.get("start_date", ""),
            "date_relative": format_relative_date(ride.get("start_date", "")),
            "moving_time_min": r_min,
            "moving_time_formatted": f"{r_min // 60}h {r_min % 60}m" if r_min >= 60 else f"{r_min}m",
            "distance_km": r_dist_km,
            "distance_miles": round(r_dist_km * 0.621371, 1),
            "elevation_gain_m": r_elev_m,
            "elevation_gain_ft": int(r_elev_m * 3.28084),
            "climbing_ratio_m_per_km": round(climbing_ratio, 1),
            "average_watts": int(r_watts) if r_watts else None,
            "pct_ftp": r_pct_ftp if r_watts else None,
            "suffer_score": int(r_suffer) if r_suffer else None,
            "match_score": total_score,
            "strava_url": f"https://www.strava.com/activities/{ride.get('id')}",
            "summary_polyline": poly,
            "map_points": sampled_pts,
            "svg_path": svg_d,
            "header_svg": header_svg,
            "thumbnail_svg": thumb_svg,
            "start_xy": start_xy,
            "end_xy": end_xy,
            "is_loop": is_loop,
            "orientation_label": orientation_label,
            "start_latlng": pts[0] if pts else None,
            "end_latlng": pts[-1] if pts else None,
            "bounds": bounds
        }
        scored_rides.append(ride_annotated)

    # Sort descending by match score
    scored_rides.sort(key=lambda x: x["match_score"], reverse=True)

    if not scored_rides:
        # Fallback if no outdoor rides found
        dummy_poly = "ginwFry|dMVHvZmBfMyAz@pAVLpBiERuAq@sE{DoG{AoFOaAEmEi@oKi@cCw@w@}D}@qHgCwFeFyDoIo@uCUoJ{@}DiBoC~@eFKcAaA}CJ]lDjBzDxHbH`HfJpK|DrHbNlPvL~PzSdOlBzBbApBlEhP`AdChSj\\`PtXpRlY|GxOlKrT`HhJ~CrFrDxHhCpIxJlWjAhB~GdEnGtEtA^dAGpB_A~JgH@c@cBoK@sBj@wCnB_Eh@m@dBg@t@BpDpBhAO`Bs@bAAxAx@rBzCr@ZlESf@i@AkBk@mCgC}EyCeBsB}FiCuAoL{@oD}AyA_Bs@uB{@uGg@yB}@mAwEcDgAwBo@yDj@qB@mAoCkT}BuMy@iCoEiImFqN}BeD{BwAwCu@{GqCmKoCIi@HoOKw@gOwTuGyISyCYg@k@Q{@XWnAHj@~@jBNfDS~EHdBzAlJfBfEV|AGp@e@`AqE`CmAnBUlENzA\\jAtBhBjAV`AIj@[~@yA~@{DJoCQeDaBwEa@uB_BkDsAyHU{CPeEMsE|@qANo@Aq@]eAD_@hBaH`Aw@xAFjEzETzDN|@`AzAZtAb@p@hA^xFZpDzA`Dp@fAr@fBhDzA~@jGlAfAKv@WBd@_AbDArA~@xBxDbG|BpHxAlUjE`QnCjNiDrBWAyAwHe@_B{E_JwFgO_C_DcCuAiMkEiJkC?uPQiAaCwCuHkL_J}LOmCc@w@g@Q{@^SnAP~@t@vAPzDQpCDpCvAjJf@bB~@dB\\pBGn@e@z@qE`CaAvAYrAEnDd@~Bf@t@pAx@rAZ~@InAoAf@gA`@mBPgC?sBUwBoAmDe@eCaBsDaBkKFeGOqEXq@d@KhEjFjMvRnCdDPfAGjOLj@ZVnJbChMpE|B`B~A|B`G|O`EhHhA|DlB|KnCbT@z@k@xAEn@h@hDb@nAv@dApE~Cp@|@p@dCv@vGj@dB`BhBpCvAhB`@tIb@nClAh@z@fAxDdDxBzBbE|@~D@l@Uh@kEd@q@MyBaDsBkAs@FsCdAu@KgDkBuCh@g@j@sBhEi@dDBhBtArJMfAsLvHyARkAUkHcFeFuCwAyAkJyU}CqK_BqDiFmJyHcKqL{V_@Oy@`AHfBpBpFf@dCTlEMpCUr@gCrD]hBSpDq@dBoHrKaBv@eAK[k@iCqKoAkC{CuCkY_SqH{JqCwE{DyNiAcCiMeOaB`BmEZwF`ByEfDaCz@qXfBQ_GqBsISiCyCax@"
        d_pts = decode_polyline(dummy_poly)
        d_svg, d_sxy, d_exy = generate_svg_path(d_pts, 460, 210, padding=18)
        d_hdr, _, _ = generate_svg_path(d_pts, 160, 80, padding=8)
        d_thumb, _, _ = generate_svg_path(d_pts, 110, 48, padding=4)
        dummy_best = {
            "id": "outdoor_example",
            "name": "Rolling Endurance Loop",
            "sport_type": "Ride",
            "start_date": get_athlete_date().isoformat(),
            "date_relative": "Example Route",
            "moving_time_min": 60,
            "moving_time_formatted": "1h 00m",
            "distance_km": 28.5,
            "distance_miles": 17.7,
            "elevation_gain_m": 320,
            "elevation_gain_ft": 1050,
            "average_watts": int(ftp * 0.66),
            "pct_ftp": 66,
            "suffer_score": 40,
            "match_score": 92,
            "strava_url": "https://www.strava.com",
            "summary_polyline": dummy_poly,
            "map_points": sample_coordinates(d_pts, 120),
            "svg_path": d_svg,
            "header_svg": d_hdr,
            "thumbnail_svg": d_thumb,
            "start_xy": d_sxy,
            "end_xy": d_exy,
            "is_loop": True,
            "orientation_label": "Loop Course (Starts & finishes at same spot)",
            "start_latlng": d_pts[0] if d_pts else None,
            "end_latlng": d_pts[-1] if d_pts else None
        }
        scored_rides = [dummy_best]

    primary_match = scored_rides[0]
    alternatives = scored_rides[1:4]

    # Generate tailored Plain-English AI Coaching Rationale & On-the-Bike Tips
    ai_rationale = generate_outdoor_coaching_rationale(
        primary_match=primary_match,
        target_zone=target_zone,
        recovery_score=recovery_score,
        hrv_rmssd=hrv_rmssd,
        recent_volume_hours=recent_volume_hours,
        trailing_7d_strain_avg=trailing_7d_strain_avg,
        trailing_7d_high_strain_count=trailing_7d_high_strain_count,
        target_duration_min=target_duration_min,
        ftp=ftp,
        is_recovery_needed=is_recovery_needed,
        recent_weighted_strain=recent_weighted_strain,
        yesterday_strain=yesterday_strain,
        total_tss=total_tss,
        acute_weighted_tss=acute_weighted_tss,
        yesterday_tss=yesterday_tss,
        load_profile=load_profile,
        strain_profile=strain_profile,
        is_recent_fatigue_surge=is_recent_fatigue_surge,
        is_front_loaded_fresh=is_front_loaded_fresh,
        user_note=user_note
    )

    coaching_tips = generate_outdoor_execution_tips(
        primary_match=primary_match,
        target_zone=target_zone,
        ftp=ftp
    )

    primary_match["badge"] = f"⭐ {primary_match['match_score']}% Match"
    primary_match["badge_color"] = "cyan"
    primary_match["target_zone"] = target_zone
    primary_match["zone_badge"] = zone_badge
    primary_match["ai_rationale"] = ai_rationale
    primary_match["coaching_tips"] = coaching_tips

    for idx, alt in enumerate(alternatives):
        alt["badge"] = f"Option {idx + 2} · {alt['match_score']}%"
        alt["badge_color"] = "emerald" if alt["moving_time_min"] < primary_match["moving_time_min"] else "purple"
        alt["zone_badge"] = target_zone

    return {
        "primary": primary_match,
        "alternatives": alternatives,
        "all_options": [primary_match] + alternatives,
        "all_routes": scored_rides[:10],
        "target_zone": target_zone,
        "telemetry": {
            "recovery_score": recovery_score,
            "today_strain": today_strain,
            "trailing_7d_strain_avg": trailing_7d_strain_avg,
            "recent_weighted_strain": recent_weighted_strain,
            "yesterday_strain": yesterday_strain,
            "strain_profile": strain_profile,
            "trailing_7d_high_strain_count": trailing_7d_high_strain_count,
            "recent_volume_hours": recent_volume_hours,
            "total_tss": total_tss,
            "acute_weighted_tss": acute_weighted_tss,
            "yesterday_tss": yesterday_tss,
            "load_profile": load_profile,
            "target_duration_min": target_duration_min
        }
    }

def generate_outdoor_coaching_rationale(
    primary_match: Dict[str, Any],
    target_zone: str,
    recovery_score: int,
    hrv_rmssd: float,
    recent_volume_hours: float,
    trailing_7d_strain_avg: float,
    trailing_7d_high_strain_count: int,
    target_duration_min: int,
    ftp: int,
    is_recovery_needed: bool,
    recent_weighted_strain: float = 0.0,
    yesterday_strain: float = 0.0,
    total_tss: int = 0,
    acute_weighted_tss: int = 0,
    yesterday_tss: int = 0,
    load_profile: str = "Evenly Distributed",
    strain_profile: str = "Evenly Distributed",
    is_recent_fatigue_surge: bool = False,
    is_front_loaded_fresh: bool = False,
    user_note: str = ""
) -> str:
    name = primary_match.get("name", "prior ride")
    date_str = primary_match.get("date_relative", "")
    dur_str = primary_match.get("moving_time_formatted", "")
    dist_km = primary_match.get("distance_km", 0)
    elev_m = primary_match.get("elevation_gain_m", 0)
    w = primary_match.get("average_watts", 0)

    note_prefix = f"Adapted to your instruction ('{user_note.strip()}'): " if (user_note and user_note.strip()) else ""

    if is_recovery_needed:
        return note_prefix + (
            f"Your Whoop recovery is low ({recovery_score}%) with accumulated strain. "
            f"Instead of a hard route, your historical ride '{name}' ({dur_str}, {dist_km} km) from {date_str} "
            f"is the ideal reference for an active flush. Keep climbing power strictly below {int(ftp * 0.55)}W "
            f"and prioritize smooth pedaling on flats to clear metabolic fatigue."
        )

    if is_recent_fatigue_surge and target_zone == "Zone 2 Aerobic Base":
        return note_prefix + (
            f"Whoop recovery is moderate at {recovery_score}%. While your 7-day volume totals {recent_volume_hours:.1f} hrs ({total_tss} TSS), "
            f"your fatigue is acutely concentrated in the last 24 hours (yesterday logged {yesterday_tss} TSS and {yesterday_strain:.1f} Whoop strain, "
            f"producing an acute weighted load of {acute_weighted_tss} TSS). Because acute muscular fatigue takes 3–5 days to clear, "
            f"your prior '{name}' from {date_str} ({dur_str}, {dist_km} km, {elev_m}m elevation) provides the ideal steady Zone 2 aerobic template "
            f"without pushing your cardiovascular or muscular system into sympathetic exhaustion."
        )

    if is_front_loaded_fresh and target_zone == "Tempo / Muscular Endurance":
        return note_prefix + (
            f"Whoop recovery is stable at {recovery_score}%. While your 7-day load totals {recent_volume_hours:.1f} hrs ({total_tss} TSS), "
            f"your heavy training was front-loaded earlier in the cycle. With yesterday being an easy recovery day ({yesterday_strain:.1f} strain, {yesterday_tss} TSS), "
            f"acute residual fatigue has decayed (acute weighted load: {acute_weighted_tss} TSS). Your body has supercompensated, "
            f"making your prior '{name}' from {date_str} ({dur_str}, {dist_km} km, {w}W avg) an excellent tempo endurance route today."
        )

    if target_zone == "Zone 2 Aerobic Base":
        return note_prefix + (
            f"Whoop recovery is moderate at {recovery_score}%. Combined with {recent_volume_hours:.1f} Strava hours "
            f"and a recency-weighted Whoop strain of {recent_weighted_strain:.1f} ({trailing_7d_high_strain_count} peak days ≥14.0), "
            f"your body needs steady aerobic base building rather than high cardiac cost. "
            f"Your prior '{name}' from {date_str} ({dur_str}, {dist_km} km, {elev_m}m elevation, {w}W avg) is a fantastic real-world template. "
            f"The rolling profile allows continuous aerobic endurance without pushing your heart rate into excessive sympathetic stress."
        )

    if target_zone == "Tempo / Muscular Endurance":
        return note_prefix + (
            f"With stable Whoop recovery ({recovery_score}%) and moderate trailing strain ({recent_weighted_strain:.1f}), "
            f"you have the reserves for a brisk outdoor session. Your prior '{name}' from {date_str} "
            f"({dur_str}, {dist_km} km, {w}W avg) is recommended. Ride the flats in steady Zone 2/3 and hold a controlled "
            f"tempo cadence on the gentle rises."
        )

    if target_zone == "Sweet Spot / Controlled Elevation":
        return note_prefix + (
            f"Good morning recovery ({recovery_score}%), but yesterday's heavy effort ({yesterday_tss} TSS, {yesterday_strain:.1f} strain) "
            f"still requires intelligent load management. Your prior '{name}' from {date_str} ({dur_str}, {dist_km} km, {elev_m}m elevation) "
            f"allows controlled Sweet Spot climbing (~{int(ftp * 0.88)}W) without the extreme anaerobic spikes of high-mountain efforts."
        )

    return note_prefix + (
        f"Strong Whoop readiness today ({recovery_score}% Recovery, {hrv_rmssd:.0f} ms HRV). "
        f"Your prior '{name}' from {date_str} ({dur_str}, {dist_km} km, {elev_m}m elevation) provides the ideal outdoor stimulus. "
        f"Push the punchy climbs at Sweet Spot / Threshold (~{int(ftp * 0.88)}–{int(ftp * 0.95)}W) and maintain cadence over the crests."
    )

def generate_outdoor_execution_tips(
    primary_match: Dict[str, Any],
    target_zone: str,
    ftp: int
) -> List[Dict[str, str]]:
    elev_m = primary_match.get("elevation_gain_m", 0)
    climbing_ratio = primary_match.get("climbing_ratio_m_per_km", 0)

    tips = []

    if target_zone == "Zone 2 Aerobic Base":
        z2_top = int(ftp * 0.72)
        tips.append({
            "title": f"Climbing Ceiling: < {z2_top}W",
            "desc": f"On the {elev_m}m of elevation, shift early and cap power at {z2_top}W to prevent crossing the aerobic threshold."
        })
        tips.append({
            "title": "Cadence Focus: 88–94 RPM",
            "desc": "Keep legs light on flatter stretches to maximize aerobic capillary engagement without muscle soreness."
        })
        tips.append({
            "title": "Hydration Target",
            "desc": "Aim for 1 bottle per 60 minutes with electrolytes to sustain Whoop recovery for tomorrow."
        })
    elif target_zone == "Active Recovery":
        z1_cap = int(ftp * 0.55)
        tips.append({
            "title": f"Power Ceiling: < {z1_cap}W",
            "desc": f"Strict Zone 1 flush. If the gradient steepens, gear down to stay below {z1_cap}W."
        })
        tips.append({
            "title": "Cadence: 90+ RPM",
            "desc": "Spin freely with minimal pedal torque to facilitate lymphatic flow."
        })
    else:
        tips.append({
            "title": f"Climb Target: {int(ftp * 0.85)}–{int(ftp * 0.95)}W",
            "desc": f"Attack rollers with controlled punchy efforts, settling quickly back into Zone 2 over each summit."
        })
        tips.append({
            "title": "Aero Posture on Flats",
            "desc": "Practice tucking in the hoods on open sections to build speed efficiency."
        })

    return tips
