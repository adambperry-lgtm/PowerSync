import math
from typing import Dict, Any, List, Optional

def generate_fueling_plan(
    duration_min: int = 60,
    distance_miles: Optional[float] = None,
    avg_power_watts: Optional[int] = None,
    ftp: int = 250,
    intensity_type: str = "Endurance",
    ride_title: str = "Training Ride",
    athlete_weight_kg: float = 70.0,
    temp_f: int = 74,
    humidity_pct: int = 50,
    is_outdoor: bool = True,
    recovery_score: int = 50,
    trailing_strain_avg: float = 11.0,
    yesterday_tss: int = 0
) -> Dict[str, Any]:
    """
    Generates a personalized, sports-science backed fueling and hydration strategy
    accounting for:
    - Ride duration, distance, intensity & power expenditure
    - Outdoor ambient weather (temperature, humidity, heat index)
    - Whoop physiological recovery score & acute/chronic trailing training stress
    """
    dur_min = max(20, int(duration_min))
    dur_hours = dur_min / 60.0
    
    # Estimate distance if not provided
    if not distance_miles or distance_miles <= 0:
        est_speed = 17.5
        if "race" in intensity_type.lower() or "hard" in intensity_type.lower():
            est_speed = 20.0
        elif "recovery" in intensity_type.lower():
            est_speed = 15.0
        distance_miles = round(est_speed * dur_hours, 1)

    # Estimate average watts and Intensity Factor
    if not avg_power_watts or avg_power_watts <= 0:
        if "race" in intensity_type.lower() or "hard" in intensity_type.lower():
            pct_ftp = 0.88
        elif "tempo" in intensity_type.lower() or "group" in intensity_type.lower():
            pct_ftp = 0.78
        elif "recovery" in intensity_type.lower():
            pct_ftp = 0.52
        else:
            pct_ftp = 0.65
        avg_power_watts = round(ftp * pct_ftp)
    else:
        pct_ftp = avg_power_watts / float(ftp)

    # 1. Caloric Expenditure Modeling
    # kJ ≈ Watts * sec / 1000; kcal ≈ kJ * 1.05 (factoring gross mechanical efficiency ~21-23%)
    total_kj = round(avg_power_watts * (dur_min * 60) / 1000)
    # Cold weather thermoregulation increases burn by ~6%
    cold_adjustment = 1.06 if temp_f < 50 else 1.0
    total_kcal = round(total_kj * 1.05 * cold_adjustment)
    kcal_per_hour = round(total_kcal / dur_hours) if dur_hours > 0 else 0

    # 2. Baseline Carbohydrate Requirements (Jeukendrup / ACSM sports nutrition model)
    if dur_min < 45:
        base_carbs_per_hour = 0
        carb_strategy = "Hydration Only (Glycogen reserves sufficient)"
        carb_ratio = "N/A"
    elif dur_min <= 75:
        base_carbs_per_hour = 35 if pct_ftp < 0.75 else 45
        carb_strategy = "Single-Source Carbs (Maltodextrin / Glucose)"
        carb_ratio = "1:0 (Glucose / Maltodextrin)"
    elif dur_min <= 135:
        base_carbs_per_hour = 50 if pct_ftp < 0.75 else 60
        carb_strategy = "Moderate Glycogen Sparing"
        carb_ratio = "2:1 Glucose-to-Fructose"
    elif dur_min <= 210: # ~2.25 - 3.5 hrs (e.g. 40-55 mile ride)
        base_carbs_per_hour = 65 if pct_ftp < 0.75 else 75
        carb_strategy = "High Oxidation Dual-Source Carbs"
        carb_ratio = "1:0.8 to 2:1 Glucose-to-Fructose"
    else: # > 3.5 hrs (epic fondo / 60+ miles)
        base_carbs_per_hour = 80 if pct_ftp < 0.75 else 90
        carb_strategy = "Maximum Gut-Oxidation Saturation"
        carb_ratio = "1:0.8 Maltodextrin-to-Fructose"

    # 3. Whoop Recovery & Trailing Fatigue Stress Adjustments
    recovery_context_notes = []
    carb_boost = 0
    is_fatigue_compromised = (recovery_score < 40 or yesterday_tss >= 80 or trailing_strain_avg >= 13.5)

    if is_fatigue_compromised and dur_min >= 45:
        # Increase exogenous carb intake to protect depleted muscle/liver glycogen
        carb_boost = 12
        recovery_context_notes.append(
            f"Recovery Compromise ({recovery_score}% Whoop recovery, yesterday {yesterday_tss} TSS): "
            f"Starting glycogen is depleted. Intake boosted by +{carb_boost}g/hr carbs to spare muscle tissue."
        )
    elif recovery_score >= 67:
        recovery_context_notes.append(
            f"High Physiological Readiness ({recovery_score}% Whoop recovery): "
            f"Endogenous glycogen stores are primed for optimal fuel utilization."
        )

    target_carbs_per_hour = min(100, base_carbs_per_hour + carb_boost)
    total_carbs_on_bike = round(target_carbs_per_hour * dur_hours)

    # 4. Weather & Environmental Hydration Adjustments
    # Baseline sweat rate: 500-650 ml/hr
    base_fluid_ml_hr = 500 if pct_ftp < 0.65 else (650 if pct_ftp < 0.80 else 750)
    base_sodium_mg_hr = 500 if pct_ftp < 0.70 else 650
    weather_context_notes = []

    if is_outdoor:
        if temp_f >= 85:
            fluid_multiplier = 1.35
            sodium_multiplier = 1.45
            weather_context_notes.append(
                f"Hot Conditions ({temp_f}°F, {humidity_pct}% humidity): "
                f"Elevated sweat rate increases fluid needs to ~{int(base_fluid_ml_hr * fluid_multiplier)} ml/hr and sodium to ~{int(base_sodium_mg_hr * sodium_multiplier)} mg/hr. "
                f"Pre-cool bottles with ice to blunt core temperature rise."
            )
        elif temp_f >= 75 and humidity_pct >= 55:
            fluid_multiplier = 1.20
            sodium_multiplier = 1.25
            weather_context_notes.append(
                f"Warm & Humid ({temp_f}°F, {humidity_pct}% humidity): "
                f"Reduced evaporative cooling requires proactive hydration every 10–12 minutes."
            )
        elif temp_f < 52:
            fluid_multiplier = 0.85
            sodium_multiplier = 0.90
            weather_context_notes.append(
                f"Cool Weather ({temp_f}°F): Thirst sensation will be blunted. "
                f"Drink on a structured timer even without feeling thirsty."
            )
        else:
            fluid_multiplier = 1.0
            sodium_multiplier = 1.0
            weather_context_notes.append(f"Ideal Riding Conditions ({temp_f}°F, {humidity_pct}% humidity): Standard hydration rate.")
    else:
        # Indoor riding: fan airflow factor
        fluid_multiplier = 1.15
        sodium_multiplier = 1.15
        weather_context_notes.append("Indoor Trainer Session: Limited wind-chill increases sweat rate. Ensure high-velocity fan is running.")

    fluid_ml_per_hour = round(base_fluid_ml_hr * fluid_multiplier)
    sodium_mg_per_hour = round(base_sodium_mg_hr * sodium_multiplier)
    total_fluid_liters = round((fluid_ml_per_hour * dur_hours) / 1000.0, 1)
    total_sodium_mg = round(sodium_mg_per_hour * dur_hours)

    # 5. Pre-Ride Fueling & Priming
    pre_carb_factor = 2.0 if is_fatigue_compromised or dur_min >= 120 else 1.5
    pre_carb_target_g = round(athlete_weight_kg * pre_carb_factor)
    pre_meal_timing = "2.5 – 3.0 hours before rollout"
    pre_meal_suggestions = [
        f"Aim for ~{pre_carb_target_g}g easily digestible carbohydrates with low fiber (<3g) and low fat to prevent GI sluggishness.",
        "Meal options: Large bowl of oatmeal with banana, maple syrup, and berries; or 2 toasted bagels with jam and a small protein side.",
        f"Pre-hydration: Drink 500 ml water with 400–500 mg sodium electrolytes 2 hours before rollout to hyperhydrate plasma volume."
    ]
    pre_rollout_snack = (
        "15–20 min before rollout: 1 energy gel (22–25g carbs) or 4 chews with 150ml water to elevate circulating blood glucose as you start."
        if dur_min >= 60 else "No pre-ride snack required for sessions under 60 minutes."
    )

    # 6. Hour-by-Hour On-the-Bike Feeding Timeline
    hourly_schedule = []
    num_hours = math.ceil(dur_hours)
    
    for h in range(1, num_hours + 1):
        is_final_hour = (h == num_hours)
        hour_fraction = 1.0 if not is_final_hour else (dur_hours - (h - 1))
        hour_carbs = round(target_carbs_per_hour * hour_fraction)
        
        if dur_min < 45:
            hourly_schedule.append({
                "hour": h,
                "label": f"0–{dur_min} min",
                "carbs_g": 0,
                "fluid_ml": round(fluid_ml_per_hour * hour_fraction),
                "sodium_mg": round(sodium_mg_per_hour * hour_fraction),
                "fuel_items": [
                    {"time": "Every 15 min", "item": "Sip plain water or light electrolyte drink", "carbs": 0}
                ],
                "coach_note": "No exogenous carbs needed. Muscle glycogen is fully adequate for short sessions."
            })
            break

        items = []
        if h == 1:
            items.append({"time": "Min 0–30", "item": "Drink mix (35g carbs in bottle)", "carbs": 35})
            if target_carbs_per_hour >= 50:
                items.append({"time": "Min 45", "item": "1 Energy Gel or 4 Chews", "carbs": target_carbs_per_hour - 35})
            note = "Start fueling early at minute 15–20. The gut absorbs carbs most efficiently before core temperature and dehydration rise."
        elif h == 2:
            items.append({"time": "Min 15", "item": "Solid bite (Stroopwafel or Rice Cake)", "carbs": 25})
            items.append({"time": "Min 40", "item": "1 Energy Gel + electrolyte sip", "carbs": 30})
            if target_carbs_per_hour >= 70:
                items.append({"time": "Throughout", "item": "Sip high-carb drink mix in second bottle", "carbs": target_carbs_per_hour - 55})
            note = "Steady carbohydrate flow prevents the catastrophic liver glycogen depletion that causes mid-ride bonking."
        elif h == 3:
            items.append({"time": "Min 20", "item": "1 Energy Gel with caffeine (25–50mg)", "carbs": 25})
            items.append({"time": "Min 45", "item": "Energy Chews (3–4 pieces) + water", "carbs": 25})
            if target_carbs_per_hour >= 65:
                items.append({"time": "Throughout", "item": "High-electrolyte carb drink mix", "carbs": target_carbs_per_hour - 50})
            note = "Caffeine stimulates central nervous system alertness and mobilizes free fatty acids during late-ride fatigue."
        else: # Hour 4+
            items.append({"time": "Min 20", "item": "1 Liquid hydrogel / isotonic gel", "carbs": 30})
            items.append({"time": "Min 45", "item": "Chews or carb drink sip", "carbs": max(20, target_carbs_per_hour - 30)})
            note = "Rely primarily on liquid and hydrogel fuel now. Blood flow to the GI tract decreases as cardiac drift increases."

        hourly_schedule.append({
            "hour": h,
            "label": f"Hour {h} ({int((h-1)*60)}–{int(min(dur_min, h*60))} min)",
            "carbs_g": hour_carbs,
            "fluid_ml": round(fluid_ml_per_hour * hour_fraction),
            "sodium_mg": round(sodium_mg_per_hour * hour_fraction),
            "fuel_items": items,
            "coach_note": note
        })

    # 7. Post-Ride Recovery Protocol
    recovery_carbs_g = round(athlete_weight_kg * (0.9 if dur_min < 75 else 1.2))
    recovery_protein_g = round(athlete_weight_kg * 0.35) # ~25-30g
    recovery_guidelines = [
        f"Within 30–45 minutes (glycogen synthase window): Consume {recovery_carbs_g}g carbohydrates + {recovery_protein_g}g lean protein (optimal 3:1 to 4:1 ratio).",
        "Recommended recovery meal: Protein smoothie (whey/plant) with 1 large banana, 50g oats, berries, and pinch of sea salt; or chicken breast with white rice.",
        f"Rehydration: Drink {round(total_fluid_liters * 0.65, 1)}L fluid with electrolytes over the next 2–3 hours to replenish plasma volume."
    ]

    # 8. Jersey Pocket Packing Checklist
    bottles_needed = max(1, math.ceil(total_fluid_liters / 0.75))
    gels_needed = max(1, math.ceil(total_carbs_on_bike * 0.45 / 25.0)) if total_carbs_on_bike > 0 else 0
    chews_or_solids = math.ceil(total_carbs_on_bike * 0.35 / 30.0) if dur_min >= 90 else 0
    drink_mix_servings = min(bottles_needed, max(1, math.ceil(total_carbs_on_bike * 0.35 / 40.0))) if total_carbs_on_bike > 0 else 0

    checklist = [
        {"item": f"{bottles_needed}x 750ml Cycling Water Bottles", "detail": f"1 with electrolyte carb mix, 1 with pure water", "icon": "🍼"},
        {"item": f"{gels_needed}x Energy Gels (~25g carbs ea)", "detail": "Include 1 with caffeine for the second half of the ride", "icon": "⚡"},
    ]
    if chews_or_solids > 0:
        checklist.append({"item": f"{chews_or_solids}x Solid Fuel Pack (Chews / Stroopwafel)", "detail": "Easy to digest on flat or gentle gradient sections", "icon": "🧇"})
    if drink_mix_servings > 0:
        checklist.append({"item": f"{drink_mix_servings}x Scoop High-Carb Drink Mix", "detail": "Dissolved in main bottle before rolling out", "icon": "🧪"})
    if sodium_mg_per_hour >= 650 or temp_f >= 80:
        checklist.append({"item": "2x Electrolyte Salt Capsules", "detail": "Carried in pocket to prevent cramping in warm/humid weather", "icon": "🧂"})

    return {
        "success": True,
        "ride_title": ride_title,
        "duration_minutes": dur_min,
        "distance_miles": distance_miles,
        "avg_power_watts": avg_power_watts,
        "intensity_type": intensity_type,
        "environmental_factors": {
            "temp_f": temp_f,
            "humidity_pct": humidity_pct,
            "is_outdoor": is_outdoor,
            "notes": weather_context_notes
        },
        "environmental_summary": {
            "temp_f": temp_f,
            "humidity_pct": humidity_pct,
            "is_outdoor": is_outdoor,
            "headline": f"{temp_f}°F, {humidity_pct}% Humidity" if is_outdoor else "Indoor Trainer Session",
            "summary_text": weather_context_notes[0] if weather_context_notes else "Standard Conditions"
        },
        "recovery_factors": {
            "recovery_score": recovery_score,
            "trailing_strain_avg": trailing_strain_avg,
            "yesterday_tss": yesterday_tss,
            "is_fatigue_compromised": is_fatigue_compromised,
            "notes": recovery_context_notes
        },
        "recovery_summary": {
            "recovery_score": recovery_score,
            "recovery_zone": "red" if recovery_score < 40 else ("yellow" if recovery_score < 67 else "green"),
            "trailing_strain_avg": trailing_strain_avg,
            "yesterday_tss": yesterday_tss,
            "carb_boost_g": carb_boost,
            "is_fatigue_compromised": is_fatigue_compromised,
            "headline": f"Glycogen Sparing (+{carb_boost}g/h Carbs)" if carb_boost > 0 else (f"Optimal Glycogen Readiness ({recovery_score}%)" if recovery_score >= 67 else f"Balanced Readiness ({recovery_score}%)"),
            "summary_text": recovery_context_notes[0] if recovery_context_notes else "Standard Physiological Readiness"
        },
        "energy_expenditure": {
            "total_kcal": total_kcal,
            "total_kj": total_kj,
            "kcal_per_hour": kcal_per_hour
        },
        "target_rates": {
            "carbs_per_hour_g": target_carbs_per_hour,
            "total_carbs_g": total_carbs_on_bike,
            "fluid_ml_per_hour": fluid_ml_per_hour,
            "total_fluid_liters": total_fluid_liters,
            "sodium_mg_per_hour": sodium_mg_per_hour,
            "total_sodium_mg": total_sodium_mg,
            "carb_strategy": carb_strategy,
            "carb_ratio": carb_ratio
        },
        "pre_ride": {
            "timing": pre_meal_timing,
            "target_carbs_g": pre_carb_target_g,
            "guidelines": pre_meal_suggestions,
            "rollout_snack": pre_rollout_snack
        },
        "hourly_timeline": hourly_schedule,
        "post_ride": {
            "target_carbs_g": recovery_carbs_g,
            "target_protein_g": recovery_protein_g,
            "guidelines": recovery_guidelines
        },
        "packing_checklist": checklist
    }
