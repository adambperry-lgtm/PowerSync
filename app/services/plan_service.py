import datetime
import math
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple

from app.database import (
    get_athlete_date,
    get_setting,
    get_db_connection,
    save_target_plan as db_save_target_plan,
    get_active_target_plan as db_get_active_target_plan,
    get_all_target_plans as db_get_all_target_plans,
    delete_target_plan as db_delete_target_plan,
    clear_active_target_plans as db_clear_active_target_plans
)
from app.services.outdoor_coach import (
    decode_polyline,
    sample_coordinates,
    generate_svg_path,
    get_candidate_outdoor_rides
)

def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in meters."""
    R = 6371000.0 # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def parse_gpx_content(gpx_str: str, filename: str = "Uploaded Route") -> Dict[str, Any]:
    """
    Parses GPX XML string. Calculates distance, elevation gain,
    extracts trackpoints, generates SVG path for preview.
    """
    if not gpx_str:
        return {"success": False, "error": "Empty GPX content."}
    
    try:
        # Strip XML namespaces for easier traversal
        clean_xml = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', gpx_str, count=1)
        root = ET.fromstring(clean_xml)
    except Exception as e:
        return {"success": False, "error": f"Invalid GPX XML format: {str(e)}"}
    
    trkpts = root.findall(".//trkpt")
    if not trkpts:
        trkpts = root.findall(".//rtept") # route points fallback
        
    if not trkpts:
        return {"success": False, "error": "No track points (<trkpt>) found in GPX."}
    
    total_dist_m = 0.0
    total_elev_gain_m = 0.0
    coords = []
    prev_lat = None
    prev_lon = None
    prev_ele = None
    
    for pt in trkpts:
        try:
            lat = float(pt.attrib.get("lat"))
            lon = float(pt.attrib.get("lon"))
            coords.append([round(lat, 5), round(lon, 5)])
            
            ele_elem = pt.find("ele")
            ele = float(ele_elem.text) if ele_elem is not None and ele_elem.text else None
            
            if prev_lat is not None and prev_lon is not None:
                step_dist = haversine_distance_meters(prev_lat, prev_lon, lat, lon)
                total_dist_m += step_dist
                
                if ele is not None and prev_ele is not None and ele > prev_ele:
                    # Threshold small noise (< 0.5m)
                    diff = ele - prev_ele
                    if diff > 0.4:
                        total_elev_gain_m += diff
            
            prev_lat = lat
            prev_lon = lon
            if ele is not None:
                prev_ele = ele
        except Exception:
            continue
            
    if len(coords) < 2:
        return {"success": False, "error": "Insufficient valid coordinate points in GPX."}
        
    distance_miles = round(total_dist_m * 0.000621371, 1)
    elevation_gain_ft = round(total_elev_gain_m * 3.28084)
    
    # Extract route name from GPX <name> tag if available
    name_elem = root.find(".//trk/name") or root.find(".//name")
    route_name = name_elem.text.strip() if name_elem is not None and name_elem.text else filename.replace(".gpx", "")
    
    sampled = sample_coordinates(coords, max_points=140)
    svg_path, _, _ = generate_svg_path(sampled, width=380, height=170, padding=14)
    
    # Estimate ride duration and TSS
    est_duration_min = max(30, round(distance_miles / 17.0 * 60))
    est_tss = max(20, round(est_duration_min * 0.58))
    
    start_lat = coords[0][0] if coords else None
    start_lon = coords[0][1] if coords else None

    return {
        "success": True,
        "title": route_name,
        "distance_miles": distance_miles,
        "elevation_gain_ft": elevation_gain_ft,
        "estimated_duration_min": est_duration_min,
        "estimated_tss": est_tss,
        "point_count": len(coords),
        "svg_path": svg_path,
        "map_points": sampled,
        "route_source": "gpx_upload",
        "start_lat": start_lat,
        "start_lon": start_lon
    }

def parse_plan_description(text: str, default_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligently parses unstructured user input such as:
    'a 50 mile ride on Sunday'
    'planning a 40 mile ride'
    'hard 45 mile group ride with 3,000 ft climbing this Saturday'
    '30 mi easy recovery spin tomorrow'
    Extracts distance, target date, elevation, intensity, and estimates duration & TSS.
    """
    clean_text = text.strip()
    today = get_athlete_date()
    lower = clean_text.lower()
    
    # 0. Check duration in text first
    dur_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–—]?\s*(?:mins|min|minutes|minute|m\b|hours|hour|hrs|hr\b)', clean_text, re.IGNORECASE)
    parsed_duration_min = None
    if dur_match:
        dur_val = float(dur_match.group(1))
        dur_unit = dur_match.group(0).lower()
        if 'h' in dur_unit:
            parsed_duration_min = round(dur_val * 60)
        elif dur_val >= 10:
            parsed_duration_min = round(dur_val)

    # Check if this is an indoor/interval session
    is_indoor_interval = any(k in lower for k in [
        "over-under", "over under", "overunder", "interval", "trainer",
        "zwift", "sweet spot", "vo2", "threshold", "microburst", "tabata"
    ])

    # 1. Parse Distance in Miles
    dist_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–—]?\s*(?:miles|mile|mi|k|km)\b', clean_text, re.IGNORECASE)
    if dist_match:
        val = float(dist_match.group(1))
        # If user typed km, convert to miles
        unit = dist_match.group(0).lower()
        if 'k' in unit and 'm' not in unit:
            distance_miles = round(val * 0.621371, 1)
        else:
            distance_miles = round(val, 1)
    else:
        # Check standalone numbers followed by "on" or words like "50 on sunday"
        num_match = re.search(r'\b(\d{2,3})\b(?=\s*(?:on|this|next|sunday|saturday|friday|monday|tuesday|wednesday|thursday))', clean_text, re.IGNORECASE)
        if num_match:
            distance_miles = float(num_match.group(1))
        elif is_indoor_interval:
            # Indoor trainer / interval sessions do not have outdoor road distance
            distance_miles = 0.0
        elif parsed_duration_min:
            # Realistic distance based on duration (~17.5 mph endurance speed), NEVER hardcoded 40 miles!
            distance_miles = round((parsed_duration_min / 60.0) * 17.5, 1)
        else:
            distance_miles = 25.0

    # 2. Parse Target Date
    target_date = default_date
    date_label = "Upcoming Event"
    explicit_day = False
    
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    
    today_weekday = today.weekday() # 0 = Monday, 6 = Sunday
    
    # Check for relative keywords
    if "today" in lower:
        target_date = today.isoformat()
        date_label = "Today"
        explicit_day = True
    elif "tomorrow" in lower:
        target_dt = today + datetime.timedelta(days=1)
        target_date = target_dt.isoformat()
        date_label = "Tomorrow"
        explicit_day = True
    elif "this weekend" in lower or "weekend" in lower:
        days_ahead = (5 - today_weekday) % 7 # Saturday
        if days_ahead == 0 and today_weekday == 5:
            days_ahead = 7
        target_dt = today + datetime.timedelta(days=days_ahead)
        target_date = target_dt.isoformat()
        date_label = target_dt.strftime("%A, %b %-d")
        explicit_day = True
    else:
        matched_weekday = None
        for day_name, day_idx in weekdays.items():
            if re.search(rf'\b{day_name}\b', lower):
                matched_weekday = (day_name, day_idx)
                break
                
        if matched_weekday:
            name, day_idx = matched_weekday
            days_ahead = (day_idx - today_weekday) % 7
            if days_ahead == 0:
                # If today matches and user says that day, schedule for next occurrence (7 days)
                days_ahead = 7
            target_dt = today + datetime.timedelta(days=days_ahead)
            target_date = target_dt.isoformat()
            date_label = target_dt.strftime("%A, %b %-d")
            explicit_day = True
            
    if not target_date:
        if any(k in lower for k in ["replace", "today", "now", "plan to do"]):
            target_date = today.isoformat()
            date_label = "Today"
        else:
            # Fallback to next upcoming Sunday
            days_to_sunday = (6 - today_weekday) % 7
            if days_to_sunday == 0:
                days_to_sunday = 7
            target_dt = today + datetime.timedelta(days=days_to_sunday)
            target_date = target_dt.isoformat()
            date_label = target_dt.strftime("%A, %b %-d")

    # 3. Parse Elevation Gain (feet/meters)
    elev_match = re.search(r'(\d+(?:,\d+)?)\s*(?:ft|feet|\'|m|meters|meter)\b', clean_text, re.IGNORECASE)
    elevation_gain_ft = 0.0
    if elev_match:
        raw_val = float(elev_match.group(1).replace(",", ""))
        unit = elev_match.group(0).lower()
        if 'm' in unit and 'mi' not in unit:
            elevation_gain_ft = round(raw_val * 3.28084)
        else:
            elevation_gain_ft = round(raw_val)
    elif is_indoor_interval:
        elevation_gain_ft = 0.0
    else:
        # Sensible estimate based on distance (~50-60 ft per mile for typical rolling terrain)
        elevation_gain_ft = round(distance_miles * 50) if distance_miles > 0 else 0.0

    # 4. Parse Intensity & Ride Type
    intensity_type = "Endurance"
    avg_speed = 16.5
    tss_factor = 0.58

    if is_indoor_interval:
        if any(k in lower for k in ["over-under", "over under", "overunder", "threshold"]):
            intensity_type = "Threshold Over-Unders"
            tss_factor = 0.82
        elif any(k in lower for k in ["vo2", "microburst", "anaerobic"]):
            intensity_type = "VO2 Max"
            tss_factor = 0.95
        elif any(k in lower for k in ["sweet spot", "sst"]):
            intensity_type = "Sweet Spot"
            tss_factor = 0.80
        elif any(k in lower for k in ["recovery", "easy", "spin"]):
            intensity_type = "Active Recovery"
            tss_factor = 0.40
        else:
            intensity_type = "Intervals"
            tss_factor = 0.75
    elif any(k in lower for k in ["race", "gran fondo", "hammer", "hard", "fast", "sprint"]):
        intensity_type = "Hard / Race"
        avg_speed = 19.5
        tss_factor = 0.85
    elif any(k in lower for k in ["group ride", "tempo", "paceline", "spirited", "club ride"]):
        intensity_type = "Tempo / Group Ride"
        avg_speed = 18.0
        tss_factor = 0.70
    elif any(k in lower for k in ["easy", "recovery", "spin", "coffee ride", "chill"]):
        intensity_type = "Recovery"
        avg_speed = 14.5
        tss_factor = 0.38
    elif any(k in lower for k in ["climb", "climbing", "hills", "mountain"]):
        intensity_type = "Climbing Endurance"
        avg_speed = 15.0
        tss_factor = 0.75
    else:
        intensity_type = "Endurance"
        avg_speed = 16.5
        tss_factor = 0.58

    # 5. Calculate Duration & TSS
    est_duration_min = parsed_duration_min or max(30, round((distance_miles / avg_speed) * 60))
    est_tss = max(15, round(est_duration_min * tss_factor))

    # 6. Generate Friendly Title
    dist_str = f"{int(distance_miles)}" if distance_miles.is_integer() else f"{distance_miles:.1f}"
    
    if explicit_day and target_date:
        weekday_str = datetime.date.fromisoformat(target_date).strftime("%A")
        day_qualifier = f" {weekday_str}" if "today" not in lower else ""
    else:
        day_qualifier = ""
        
    if is_indoor_interval:
        dur_label = f"{est_duration_min}-Min"
        if "over-under" in lower or "over under" in lower or "overunder" in lower:
            title = f"{dur_label} Threshold Over-Unders"
        elif "sweet spot" in lower or "sst" in lower:
            title = f"{dur_label} Sweet Spot Aerobic Density"
        elif "vo2" in lower:
            title = f"{dur_label} VO2 Max High Intensity"
        elif "recovery" in lower or "easy" in lower or "spin" in lower:
            title = f"{dur_label} Cadence Flush & Spin"
        elif "threshold" in lower:
            title = f"{dur_label} Threshold Session"
        else:
            title = f"{dur_label} Structured Intervals"
    elif intensity_type == "Tempo / Group Ride":
        title = f"{dist_str}-Mile{day_qualifier} Group Ride"
    elif intensity_type == "Hard / Race":
        title = f"{dist_str}-Mile{day_qualifier} Race / Hard Pace"
    elif intensity_type == "Climbing Endurance":
        title = f"{dist_str}-Mile{day_qualifier} Hill Climb"
    else:
        title = f"{dist_str}-Mile{day_qualifier} Endurance Ride"

    return {
        "success": True,
        "title": title,
        "description": clean_text,
        "target_date": target_date,
        "date_label": date_label,
        "distance_miles": distance_miles,
        "elevation_gain_ft": elevation_gain_ft,
        "intensity_type": intensity_type,
        "estimated_duration_min": est_duration_min,
        "estimated_tss": est_tss,
        "route_source": "manual"
    }

def get_strava_route_candidates() -> List[Dict[str, Any]]:
    """
    Returns candidate routes from synced Strava activities and mock data,
    ready for 1-click selection as an upcoming target plan.
    """
    rides = get_candidate_outdoor_rides()
    candidates = []
    
    for r in rides:
        poly = r.get("summary_polyline")
        dist_m = float(r.get("distance_meters") or 0.0)
        dist_mi = round(dist_m * 0.000621371, 1)
        elev_m = float(r.get("total_elevation_gain") or 0.0)
        elev_ft = round(elev_m * 3.28084)
        moving_min = int(r.get("moving_time_sec") or 0) // 60
        suffer = int(r.get("suffer_score") or r.get("kilojoules") or 0)
        est_tss = max(30, round(moving_min * 0.65)) if suffer <= 0 else min(300, suffer)
        
        svg_path = ""
        if poly:
            coords = decode_polyline(poly)
            sampled = sample_coordinates(coords, max_points=120)
            svg_path, _, _ = generate_svg_path(sampled, width=320, height=140, padding=12)
            
        candidates.append({
            "id": str(r.get("id")),
            "title": r.get("name", "Strava Ride"),
            "distance_miles": dist_mi,
            "elevation_gain_ft": elev_ft,
            "moving_time_min": moving_min,
            "estimated_tss": est_tss,
            "summary_polyline": poly or "",
            "svg_path": svg_path,
            "date_recorded": r.get("start_date", "")[:10]
        })
        
    # Sort descending by distance
    candidates.sort(key=lambda x: x["distance_miles"], reverse=True)
    return candidates

def compute_taper_leadup_schedule(
    target_plan: Dict[str, Any],
    current_ftp: int = 250
) -> List[Dict[str, Any]]:
    """
    Computes a daily training roadmap from today up through the event day,
    showing how each day is specifically calibrated for the upcoming ride.
    """
    today = get_athlete_date()
    target_date_str = target_plan.get("target_date", "")
    try:
        target_dt = datetime.date.fromisoformat(target_date_str[:10])
    except Exception:
        target_dt = today + datetime.timedelta(days=6)
        
    days_until = (target_dt - today).days
    schedule = []
    
    # Cap timeline between 0 and 7 days
    total_steps = max(1, min(8, days_until + 1))
    
    plan_title = target_plan.get("title", "Target Event")
    plan_dist = float(target_plan.get("distance_miles") or 50.0)
    plan_tss = int(target_plan.get("estimated_tss") or 160)
    
    for offset in range(total_steps):
        day_date = today + datetime.timedelta(days=offset)
        days_remaining = (target_dt - day_date).days
        date_fmt = day_date.strftime("%a, %b %-d")
        
        if days_remaining == 0:
            # EVENT DAY
            schedule.append({
                "day_offset": offset,
                "days_remaining": 0,
                "date_formatted": date_fmt,
                "relative_label": "Today" if offset == 0 else "Event Day",
                "phase": "Event Execution",
                "title": f"🎯 {plan_title}",
                "duration_min": target_plan.get("estimated_duration_min", 180),
                "estimated_tss": plan_tss,
                "badge": "🏁 TARGET EVENT",
                "badge_color": "magenta",
                "focus": f"{plan_dist:.1f} Miles • Full Performance Execution",
                "directive": f"Execute target pacing. Consume 60–80g carbs/hr and 600ml fluids with electrolytes.",
                "is_event_day": True
            })
        elif days_remaining == 1:
            # T-1 PRIMER
            schedule.append({
                "day_offset": offset,
                "days_remaining": 1,
                "date_formatted": date_fmt,
                "relative_label": "Today" if offset == 0 else "T-1 Day",
                "phase": "Pre-Event Primer",
                "title": "⚡ Pre-Event Neuromuscular Primer",
                "duration_min": 30,
                "estimated_tss": 22,
                "badge": "⚡ T-1 Primer",
                "badge_color": "cyan",
                "focus": "Neural Activation & Glycogen Sparing",
                "directive": "30-min easy spin with 3x 30s cadence openers. Guarantees fresh glycogen and high recovery for event day.",
                "is_event_day": False
            })
        elif days_remaining == 2:
            # T-2 FLUSH
            schedule.append({
                "day_offset": offset,
                "days_remaining": 2,
                "date_formatted": date_fmt,
                "relative_label": "Today" if offset == 0 else "T-2 Days",
                "phase": "Active Taper & Flush",
                "title": "🌱 Pre-Event Active Recovery Flush",
                "duration_min": 35,
                "estimated_tss": 22,
                "badge": "🌱 T-2 Flush",
                "badge_color": "emerald",
                "focus": "Lactate Clearance & Cellular Repair",
                "directive": "Gentle Zone 1 flush (<55% FTP). Clear metabolic fatigue and prioritize sleep/hydration.",
                "is_event_day": False
            })
        elif days_remaining == 3:
            # T-3 TAPER ONSET
            schedule.append({
                "day_offset": offset,
                "days_remaining": 3,
                "date_formatted": date_fmt,
                "relative_label": "Today" if offset == 0 else "T-3 Days",
                "phase": "Taper Onset",
                "title": "🎯 Taper Onset: Controlled Tempo Touch",
                "duration_min": 45,
                "estimated_tss": 38,
                "badge": "🎯 T-3 Onset",
                "badge_color": "amber",
                "focus": "Muscular Tension & Blood Volume",
                "directive": "Short 45m session with 2x 6m controlled tempo blocks. Preserves tone while fatigue decays.",
                "is_event_day": False
            })
        else:
            # T-4+ VOLUME MANAGEMENT
            schedule.append({
                "day_offset": offset,
                "days_remaining": days_remaining,
                "date_formatted": date_fmt,
                "relative_label": "Today" if offset == 0 else f"T-{days_remaining} Days",
                "phase": "Volume Management",
                "title": "Zone 2 Steady Aerobic Foundation",
                "duration_min": 60,
                "estimated_tss": 45,
                "badge": f"🎯 T-{days_remaining} Prep",
                "badge_color": "blue",
                "focus": "Aerobic Density & Fat Oxidation",
                "directive": "Maintain aerobic efficiency while managing weekly cumulative fatigue before the weekend.",
                "is_event_day": False
            })
            
    return schedule
