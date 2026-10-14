import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import datetime
import copy
from typing import Dict, Any, List, Optional

def _format_intervals_dur(sec: int) -> str:
    sec = int(sec)
    if sec % 60 == 0:
        return f"{sec // 60}m"
    elif sec < 60:
        return f"{sec}s"
    else:
        m = sec // 60
        s = sec % 60
        return f"{m}m{s}s"

def calc_intervals_duration_sec(intervals: List[Dict[str, Any]]) -> int:
    """Calculates total duration in seconds across all workout interval steps."""
    total = 0
    for item in intervals:
        seg_type = str(item.get("type", "SteadyState")).lower()
        if seg_type in ["repeats", "intervalblock", "intervals"]:
            repeat = int(item.get("repeat", 1))
            on_dur = int(item.get("on_duration_sec", 0))
            off_dur = int(item.get("off_duration_sec", 0))
            total += repeat * (on_dur + off_dur)
        else:
            total += int(item.get("duration_sec", 0))
    return total

def reconcile_workout_intervals(intervals: List[Dict[str, Any]], target_duration_min: int, ftp: int = 250) -> List[Dict[str, Any]]:
    """
    Guarantees that the sum of all interval steps equals target_duration_min * 60 seconds EXACTLY.
    Intervals.icu and Zwift calculate workout duration solely by summing individual step durations.
    """
    if not intervals or target_duration_min <= 0:
        return intervals

    reconciled = [copy.deepcopy(item) for item in intervals]
    target_sec = int(target_duration_min * 60)
    current_sec = calc_intervals_duration_sec(reconciled)
    delta = target_sec - current_sec

    if delta == 0:
        return reconciled

    warmup_item = next((i for i in reconciled if str(i.get("type", "")).lower() == "warmup"), None)
    cooldown_item = next((i for i in reversed(reconciled) if str(i.get("type", "")).lower() == "cooldown"), None)
    repeats_item = next((i for i in reconciled if str(i.get("type", "")).lower() in ["repeats", "intervalblock", "intervals"]), None)

    # 1. If Repeats exist and delta is a clean multiple of the repeat cycle
    if repeats_item:
        rep = int(repeats_item.get("repeat", 1))
        on_d = int(repeats_item.get("on_duration_sec", 0))
        off_d = int(repeats_item.get("off_duration_sec", 0))
        cycle = on_d + off_d
        if cycle > 0:
            if delta > 0 and delta >= cycle:
                add_reps = delta // cycle
                repeats_item["repeat"] = rep + add_reps
                name = repeats_item.get("name", "")
                if f"{rep}x" in name:
                    repeats_item["name"] = name.replace(f"{rep}x", f"{rep + add_reps}x")
                delta -= add_reps * cycle
            elif delta < 0 and abs(delta) >= cycle and rep > (abs(delta) // cycle):
                sub_reps = abs(delta) // cycle
                repeats_item["repeat"] = rep - sub_reps
                name = repeats_item.get("name", "")
                if f"{rep}x" in name:
                    repeats_item["name"] = name.replace(f"{rep}x", f"{rep - sub_reps}x")
                delta += sub_reps * cycle

    if delta > 0:
        # Check if an existing SteadyState endurance bridge or base segment exists
        steady_bridge = next((
            i for i in reconciled
            if str(i.get("type", "")).lower() == "steadystate"
            and any(k in str(i.get("name", "")).lower() for k in ["bridge", "base", "endurance", "steady", "cruise", "tempo"])
        ), None)

        if steady_bridge:
            steady_bridge["duration_sec"] = int(steady_bridge.get("duration_sec", 0)) + delta
            delta = 0
        elif delta <= 360:
            # Adjustment: distribute between Warmup and Cooldown ramps
            if warmup_item and cooldown_item:
                w_add = (delta + 1) // 2
                c_add = delta - w_add
                warmup_item["duration_sec"] = int(warmup_item.get("duration_sec", 420)) + w_add
                cooldown_item["duration_sec"] = int(cooldown_item.get("duration_sec", 300)) + c_add
                delta = 0
            elif warmup_item:
                warmup_item["duration_sec"] = int(warmup_item.get("duration_sec", 420)) + delta
                delta = 0
            elif cooldown_item:
                cooldown_item["duration_sec"] = int(cooldown_item.get("duration_sec", 300)) + delta
                delta = 0
        else:
            # Significant delta (> 6 min): if repeats exist, add an extra repeat block and adjust ramps
            if repeats_item:
                on_d = int(repeats_item.get("on_duration_sec", 120))
                off_d = int(repeats_item.get("off_duration_sec", 60))
                cycle = on_d + off_d
                if cycle > 0:
                    add_reps = max(1, delta // cycle)
                    repeats_item["repeat"] = int(repeats_item.get("repeat", 1)) + add_reps
                    name = repeats_item.get("name", "")
                    if "x" in name:
                        import re
                        repeats_item["name"] = re.sub(r'^\d+x', f"{repeats_item['repeat']}x", name)
                    delta -= add_reps * cycle

            # Absorb any remaining delta into progressive warmup and cooldown ramps
            if delta > 0:
                if warmup_item and cooldown_item:
                    w_add = (delta + 1) // 2
                    c_add = delta - w_add
                    warmup_item["duration_sec"] = int(warmup_item.get("duration_sec", 420)) + w_add
                    cooldown_item["duration_sec"] = int(cooldown_item.get("duration_sec", 300)) + c_add
                    delta = 0
                elif warmup_item:
                    warmup_item["duration_sec"] = int(warmup_item.get("duration_sec", 420)) + delta
                    delta = 0
                elif cooldown_item:
                    cooldown_item["duration_sec"] = int(cooldown_item.get("duration_sec", 300)) + delta
                    delta = 0

    elif delta < 0:
        needed_cut = abs(delta)
        # 1. First cut from existing steady bridges or steady state intervals if long enough
        for item in reconciled:
            if str(item.get("type", "")).lower() == "steadystate" and int(item.get("duration_sec", 0)) > 180 and needed_cut > 0:
                dur = int(item["duration_sec"])
                can_cut = min(dur - 120, needed_cut)
                item["duration_sec"] = dur - can_cut
                needed_cut -= can_cut

        # 2. Next cut from Warmup (keep at least 300s)
        if needed_cut > 0 and warmup_item:
            w_dur = int(warmup_item.get("duration_sec", 600))
            if w_dur > 300:
                can_cut = min(w_dur - 300, needed_cut)
                warmup_item["duration_sec"] = w_dur - can_cut
                needed_cut -= can_cut

        # 3. Next cut from Cooldown (keep at least 180s)
        if needed_cut > 0 and cooldown_item:
            c_dur = int(cooldown_item.get("duration_sec", 300))
            if c_dur > 180:
                can_cut = min(c_dur - 180, needed_cut)
                cooldown_item["duration_sec"] = c_dur - can_cut
                needed_cut -= can_cut

        # 4. Final safety cut from any non-repeat segment
        if needed_cut > 0:
            for item in reconciled:
                if str(item.get("type", "")).lower() not in ["repeats", "intervalblock", "intervals"]:
                    dur = int(item.get("duration_sec", 0))
                    if dur > 60:
                        can_cut = min(dur - 60, needed_cut)
                        item["duration_sec"] = dur - can_cut
                        needed_cut -= can_cut
                        if needed_cut <= 0:
                            break

    # Final exact check
    final_total = calc_intervals_duration_sec(reconciled)
    diff = target_sec - final_total
    if diff != 0:
        if cooldown_item:
            cooldown_item["duration_sec"] = max(60, int(cooldown_item.get("duration_sec", 300)) + diff)
        elif warmup_item:
            warmup_item["duration_sec"] = max(60, int(warmup_item.get("duration_sec", 600)) + diff)

    return reconciled

def generate_zwo_xml(workout_data: Dict[str, Any], athlete_ftp: int = 250) -> str:
    """
    Generates a Zwift .zwo XML file string from structured workout intervals.
    """
    if "duration_minutes" in workout_data and workout_data["duration_minutes"]:
        workout_data["intervals"] = reconcile_workout_intervals(
            workout_data.get("intervals", []),
            int(workout_data["duration_minutes"]),
            athlete_ftp
        )
    workout_file = ET.Element("workout_file")
    
    author = ET.SubElement(workout_file, "author")
    author.text = "AI Adaptive Coach"
    
    name = ET.SubElement(workout_file, "name")
    name.text = workout_data.get("title", "AI Prescribed Workout")
    
    description = ET.SubElement(workout_file, "description")
    description.text = workout_data.get("description", "Generated based on Whoop recovery and Strava training load.")
    
    sport_type = ET.SubElement(workout_file, "sportType")
    sport_type.text = "bike"
    
    tags = ET.SubElement(workout_file, "tags")
    for t in workout_data.get("tags", ["AI Coach", workout_data.get("focus_area", "Adaptive")]):
        tag = ET.SubElement(tags, "tag")
        tag.set("name", str(t))
        
    workout = ET.SubElement(workout_file, "workout")
    
    intervals = workout_data.get("intervals", [])
    for item in intervals:
        seg_type = item.get("type", "SteadyState").lower()
        duration = int(item.get("duration_sec", 300))
        
        if seg_type == "warmup":
            p_low = round(float(item.get("power_low_pct", 50)) / 100.0, 2)
            p_high = round(float(item.get("power_high_pct", 75)) / 100.0, 2)
            elem = ET.SubElement(workout, "Warmup", {
                "Duration": str(duration),
                "PowerLow": str(p_low),
                "PowerHigh": str(p_high)
            })
            if "cadence" in item and item["cadence"]:
                elem.set("Cadence", str(item["cadence"]))
                
        elif seg_type == "cooldown":
            p_low = round(float(item.get("power_low_pct", 75)) / 100.0, 2)
            p_high = round(float(item.get("power_high_pct", 45)) / 100.0, 2)
            elem = ET.SubElement(workout, "Cooldown", {
                "Duration": str(duration),
                "PowerLow": str(p_low),
                "PowerHigh": str(p_high)
            })
            if "cadence" in item and item["cadence"]:
                elem.set("Cadence", str(item["cadence"]))
                
        elif seg_type in ["repeats", "intervalblock", "intervals"]:
            repeat = int(item.get("repeat", 3))
            on_dur = int(item.get("on_duration_sec", 180))
            off_dur = int(item.get("off_duration_sec", 120))
            on_p = round(float(item.get("on_power_pct", 95)) / 100.0, 2)
            off_p = round(float(item.get("off_power_pct", 55)) / 100.0, 2)
            elem = ET.SubElement(workout, "IntervalsT", {
                "Repeat": str(repeat),
                "OnDuration": str(on_dur),
                "OffDuration": str(off_dur),
                "OnPower": str(on_p),
                "OffPower": str(off_p)
            })
            if "cadence" in item and item["cadence"]:
                elem.set("Cadence", str(item["cadence"]))
            if "cadence_rest" in item and item["cadence_rest"]:
                elem.set("CadenceRest", str(item["cadence_rest"]))
                
        elif seg_type == "ramp":
            p_low = round(float(item.get("power_low_pct", 60)) / 100.0, 2)
            p_high = round(float(item.get("power_high_pct", 90)) / 100.0, 2)
            elem = ET.SubElement(workout, "Ramp", {
                "Duration": str(duration),
                "PowerLow": str(p_low),
                "PowerHigh": str(p_high)
            })
            if "cadence" in item and item["cadence"]:
                elem.set("Cadence", str(item["cadence"]))
                
        else: # steadystate / recovery
            power = round(float(item.get("power_pct", 65)) / 100.0, 2)
            elem = ET.SubElement(workout, "SteadyState", {
                "Duration": str(duration),
                "Power": str(power)
            })
            if "cadence" in item and item["cadence"]:
                elem.set("Cadence", str(item["cadence"]))
                
        if "text_event" in item and item["text_event"]:
            msg = ET.SubElement(elem, "textevent", {
                "timeoffset": "10",
                "message": item["text_event"]
            })

    rough_xml = ET.tostring(workout_file, 'utf-8')
    reparsed = minidom.parseString(rough_xml)
def generate_intervals_icu_text(workout_data: Dict[str, Any]) -> str:
    """
    Generates plain-text workout definition compatible with Intervals.icu.
    Intervals.icu automatically converts this into Zwift workouts when synced.
    """
    if "duration_minutes" in workout_data and workout_data["duration_minutes"]:
        workout_data["intervals"] = reconcile_workout_intervals(
            workout_data.get("intervals", []),
            int(workout_data["duration_minutes"])
        )
    lines = [f"{workout_data.get('title', 'AI Workout')}"]
    lines.append(f"{workout_data.get('ai_rationale', '')}\n")
    
    for item in workout_data.get("intervals", []):
        seg_type = item.get("type", "SteadyState").lower()
        if seg_type == "warmup":
            dur_str = _format_intervals_dur(item.get("duration_sec", 600))
            p_low = item.get("power_low_pct", 50)
            p_high = item.get("power_high_pct", 75)
            cad = f" {item['cadence']}rpm" if item.get("cadence") else ""
            lines.append(f"Warmup\n- {dur_str} {p_low}-{p_high}%{cad}\n")
        elif seg_type == "cooldown":
            dur_str = _format_intervals_dur(item.get("duration_sec", 300))
            p_low = item.get("power_low_pct", 75)
            p_high = item.get("power_high_pct", 45)
            cad = f" {item['cadence']}rpm" if item.get("cadence") else ""
            lines.append(f"Cooldown\n- {dur_str} {p_low}-{p_high}%{cad}\n")
        elif seg_type in ["repeats", "intervalblock", "intervals"]:
            repeat = int(item.get("repeat", 3))
            on_dur_str = _format_intervals_dur(item.get("on_duration_sec", 180))
            off_dur_str = _format_intervals_dur(item.get("off_duration_sec", 120))
            on_p = item.get("on_power_pct", 95)
            off_p = item.get("off_power_pct", 55)
            cad = f" {item['cadence']}rpm" if item.get("cadence") else ""
            cad_rest = f" {item['cadence_rest']}rpm" if item.get("cadence_rest") else ""
            
            lines.append(f"Main Set {repeat}x")
            lines.append(f"- {on_dur_str} {on_p}%{cad}")
            lines.append(f"- {off_dur_str} {off_p}%{cad_rest}\n")
        else:
            dur_str = _format_intervals_dur(item.get("duration_sec", 300))
            p = item.get("power_pct", 65)
            cad = f" {item['cadence']}rpm" if item.get("cadence") else ""
            name = item.get("name", "Steady")
            lines.append(f"- {dur_str} {p}%{cad} {name}")
            
    return "\n".join(lines)

def push_to_intervals_icu(athlete_id: str, api_key: str, workout_data: Dict[str, Any], target_date: Optional[str] = None, ftp: int = 250) -> Dict[str, Any]:
    """
    Pushes workout directly to Intervals.icu calendar for target_date (and tomorrow for timezone safety).
    Uses the bulk upsert endpoint providing both native .zwo XML and parsed interval step syntax.
    """
    if not athlete_id or not api_key:
        return {"success": False, "error": "Intervals.icu Athlete ID and API Key required."}
    if "•" in api_key or "\u2022" in api_key:
        return {"success": False, "error": "Intervals.icu API Key contains placeholder mask characters. Please re-enter your valid API Key in Settings."}
        
    today = datetime.date.today()
    if not target_date:
        target_date = today.isoformat()
    
    try:
        req_date = datetime.date.fromisoformat(target_date)
    except Exception:
        req_date = today

    tomorrow_str = (req_date + datetime.timedelta(days=1)).isoformat()
    
    # Guarantee intervals are reconciled to match duration_minutes
    if "duration_minutes" in workout_data and workout_data["duration_minutes"]:
        workout_data["intervals"] = reconcile_workout_intervals(
            workout_data.get("intervals", []),
            int(workout_data["duration_minutes"]),
            ftp
        )
        workout_data["zwo_content"] = generate_zwo_xml(workout_data, ftp)
        workout_data["intervals_icu_text"] = generate_intervals_icu_text(workout_data)

    # Generate native ZWO and Intervals syntax
    zwo_content = workout_data.get("zwo_content") or generate_zwo_xml(workout_data, ftp)
    workout_text = workout_data.get("intervals_icu_text") or generate_intervals_icu_text(workout_data)
    workout_title = workout_data.get('title', 'Adaptive Workout')
    clean_filename = f"PowerSync_{workout_title.replace(' ', '_')}.zwo"
    
    # Look for existing workout event on req_date to update in place
    existing_id = None
    extra_same_day_ids = []
    try:
        cur_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={req_date.isoformat()}&newest={req_date.isoformat()}"
        cur_res = requests.get(cur_url, auth=("API_KEY", api_key), timeout=5)
        if cur_res.status_code == 200:
            for ev in cur_res.json():
                ev_name = ev.get("name", "")
                if ev.get("category") == "WORKOUT" and (ev_name.startswith("PowerSync:") or ev_name.startswith("AeroSync:")):
                    if existing_id is None:
                        existing_id = ev.get("id")
                    else:
                        extra_same_day_ids.append(ev.get("id"))
    except Exception as check_err:
        print("Notice: could not query existing target date event:", check_err)

    event_payload = {
        "category": "WORKOUT",
        "start_date_local": f"{req_date.isoformat()}T08:00:00",
        "name": f"PowerSync: {workout_title}",
        "type": "Ride",
        "filename": clean_filename,
        "file_contents": zwo_content,
        "description": workout_text
    }

    try:
        if existing_id:
            # Update existing event in place
            url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/{existing_id}"
            response = requests.put(
                url,
                auth=("API_KEY", api_key),
                json=event_payload,
                headers={"Content-Type": "application/json"},
                timeout=12
            )
            event_res_id = existing_id
        else:
            # Create single new event
            url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events"
            response = requests.post(
                url,
                auth=("API_KEY", api_key),
                json=event_payload,
                headers={"Content-Type": "application/json"},
                timeout=12
            )
            event_res_id = response.json().get("id") if response.status_code in [200, 201] else None

        if response.status_code in [200, 201]:
            # Delete any extra duplicate events on the same target date
            for extra_id in extra_same_day_ids:
                try:
                    requests.delete(f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/{extra_id}", auth=("API_KEY", api_key), timeout=5)
                except Exception:
                    pass

            # Clean up any lingering duplicate event from next day if created previously
            try:
                next_day_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={tomorrow_str}&newest={tomorrow_str}"
                n_res = requests.get(next_day_url, auth=("API_KEY", api_key), timeout=5)
                if n_res.status_code == 200:
                    for ev in n_res.json():
                        ev_name = ev.get("name", "")
                        if ev_name.startswith("PowerSync:") or ev_name.startswith("AeroSync:"):
                            dup_id = ev.get("id")
                            requests.delete(f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/{dup_id}", auth=("API_KEY", api_key), timeout=5)
            except Exception as clean_err:
                print("Notice: could not clean lingering next-day duplicate event:", clean_err)

            return {
                "success": True,
                "message": f"Workout scheduled on Intervals.icu for {req_date.isoformat()}! It will appear on Zwift when launched.",
                "event_ids": [event_res_id] if event_res_id else [],
                "date": req_date.isoformat()
            }
        else:
            return {
                "success": False,
                "error": f"Intervals.icu API returned HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {"success": False, "error": f"Failed to connect to Intervals.icu: {str(e)}"}
