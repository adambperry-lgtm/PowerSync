import math
from typing import Dict, Any, List, Optional
from app.database import get_athlete_weight_kg

def generate_fueling_plan(
    duration_min: int = 60,
    distance_miles: Optional[float] = None,
    avg_power_watts: Optional[int] = None,
    ftp: int = 250,
    intensity_type: str = "Endurance",
    ride_title: str = "Training Ride",
    athlete_weight_kg: Optional[float] = None,
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
    if athlete_weight_kg is None or athlete_weight_kg <= 0:
        athlete_weight_kg = get_athlete_weight_kg()
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
    total_drink_mix_g = 0
    total_gels_count = 0
    caffeine_gels_count = 0
    total_gels_g = 0
    total_solids_count = 0
    total_solids_g = 0

    if dur_min < 45:
        hourly_schedule.append({
            "hour": 1,
            "label": f"Hour 1 (0–{dur_min} min)",
            "carbs_g": 0,
            "fluid_ml": round(fluid_ml_per_hour * dur_hours),
            "sodium_mg": round(sodium_mg_per_hour * dur_hours),
            "fuel_items": [
                {"time": f"Min 0–{dur_min}", "item": "Sip plain water or light electrolyte drink", "carbs": 0}
            ],
            "coach_note": "No exogenous carbs needed. Muscle glycogen is fully adequate for short sessions."
        })
    else:
        # Build hour windows; fold a tiny tail (<= 15 min past an hour mark) into the previous hour
        # so we never show a 3-minute "Hour 2 (60-63 min)" block.
        windows = []
        full_hours = dur_min // 60
        rem_min = dur_min % 60
        if full_hours == 0:
            windows.append((0, dur_min))
        else:
            for idx in range(full_hours):
                s_min = idx * 60
                e_min = (idx + 1) * 60
                if idx == full_hours - 1 and 0 < rem_min <= 15:
                    e_min = dur_min
                windows.append((s_min, e_min))
            if rem_min > 15:
                windows.append((full_hours * 60, dur_min))

        # Reconcile per-window rounding so hourly carbs sum exactly to total_carbs_on_bike
        window_carbs_list = [
            round(target_carbs_per_hour * ((e_min - s_min) / 60.0))
            for (s_min, e_min) in windows
        ]
        if total_carbs_on_bike > 0 and window_carbs_list:
            carb_diff = total_carbs_on_bike - sum(window_carbs_list)
            window_carbs_list[-1] = max(0, window_carbs_list[-1] + carb_diff)

        for h, ((start_min, end_min), hour_carbs) in enumerate(zip(windows, window_carbs_list), start=1):
            window_min = end_min - start_min
            hour_fraction = window_min / 60.0
            items = []

            if h == 1:
                if hour_carbs == 0:
                    items.append({"time": f"Min 0–{end_min}", "item": "Sip plain water or light electrolyte drink", "carbs": 0})
                elif hour_carbs <= 45:
                    items.append({"time": f"Min 0–{end_min}", "item": f"Sip carb drink mix steadily ({hour_carbs}g carbs in bottle)", "carbs": hour_carbs})
                    total_drink_mix_g += hour_carbs
                elif hour_carbs < 70:
                    gel_g = 25
                    bottle_g = hour_carbs - gel_g
                    items.append({"time": f"Min 0–{end_min}", "item": f"Sip carb drink mix steadily ({bottle_g}g carbs in bottle)", "carbs": bottle_g})
                    items.append({"time": "Min 40", "item": "1 Energy Gel or 4 Chews", "carbs": gel_g})
                    total_drink_mix_g += bottle_g
                    total_gels_count += 1
                    total_gels_g += gel_g
                else:
                    gel1_g = 25
                    gel2_g = 25
                    bottle_g = hour_carbs - (gel1_g + gel2_g)
                    items.append({"time": f"Min 0–{end_min}", "item": f"Sip carb drink mix steadily ({bottle_g}g carbs in bottle)", "carbs": bottle_g})
                    items.append({"time": "Min 25", "item": "1 Energy Gel or 4 Chews", "carbs": gel1_g})
                    items.append({"time": "Min 45", "item": "1 Energy Gel or Energy Chews", "carbs": gel2_g})
                    total_drink_mix_g += bottle_g
                    total_gels_count += 2
                    total_gels_g += gel1_g + gel2_g
                note = "Start fueling early at minute 15–20. The gut absorbs carbs most efficiently before core temperature and dehydration rise."
            else:
                if window_min <= 35:
                    t_mark = start_min + min(15, max(5, window_min // 2))
                    if hour_carbs == 0:
                        items.append({"time": f"Min {start_min}–{end_min}", "item": "Sip plain water or light electrolyte drink", "carbs": 0})
                    elif hour_carbs < 18:
                        items.append({"time": f"Min {start_min}–{end_min}", "item": "Sip carb drink mix in bottle", "carbs": hour_carbs})
                        total_drink_mix_g += hour_carbs
                    elif hour_carbs <= 35:
                        items.append({"time": f"Min {t_mark}", "item": "1 Energy Gel or 3–4 Chews", "carbs": hour_carbs})
                        total_gels_count += 1
                        total_gels_g += hour_carbs
                    else:
                        gel_g = 25
                        bottle_g = hour_carbs - gel_g
                        items.append({"time": f"Min {t_mark}", "item": "1 Energy Gel or 4 Chews", "carbs": gel_g})
                        items.append({"time": f"Min {start_min}–{end_min}", "item": "Sip carb drink mix in bottle", "carbs": bottle_g})
                        total_gels_count += 1
                        total_gels_g += gel_g
                        total_drink_mix_g += bottle_g
                else:
                    if hour_carbs == 0:
                        items.append({"time": f"Min {start_min}–{end_min}", "item": "Sip plain water or light electrolyte drink", "carbs": 0})
                    elif hour_carbs >= 70:
                        first_g = 25
                        second_g = 25
                        bottle_g = hour_carbs - (first_g + second_g)
                        if h == 2:
                            items.append({"time": f"Min {start_min + 15}", "item": "Solid bite (Stroopwafel or Rice Cake)", "carbs": first_g})
                            total_solids_count += 1
                            total_solids_g += first_g
                        else:
                            items.append({"time": f"Min {start_min + 15}", "item": "1 Energy Gel with caffeine (25–50mg)", "carbs": first_g})
                            total_gels_count += 1
                            caffeine_gels_count += 1
                            total_gels_g += first_g
                        items.append({"time": f"Min {start_min + 40}", "item": "1 Energy Gel or Energy Chews", "carbs": second_g})
                        items.append({"time": f"Min {start_min}–{end_min}", "item": "Sip high-carb drink mix in bottle", "carbs": bottle_g})
                        total_gels_count += 1
                        total_gels_g += second_g
                        total_drink_mix_g += bottle_g
                    elif hour_carbs >= 40:
                        first_g = round(hour_carbs * 0.45)
                        second_g = hour_carbs - first_g
                        if h == 2:
                            items.append({"time": f"Min {start_min + 15}", "item": "Solid bite (Stroopwafel or Rice Cake)", "carbs": first_g})
                            total_solids_count += 1
                            total_solids_g += first_g
                        else:
                            items.append({"time": f"Min {start_min + 15}", "item": "1 Energy Gel with caffeine (25–50mg)", "carbs": first_g})
                            total_gels_count += 1
                            caffeine_gels_count += 1
                            total_gels_g += first_g
                        items.append({"time": f"Min {start_min + 40}", "item": "1 Energy Gel + water/electrolyte sip", "carbs": second_g})
                        total_gels_count += 1
                        total_gels_g += second_g
                    else:
                        items.append({"time": f"Min {start_min + 20}", "item": "1 Energy Gel or 4 Chews", "carbs": hour_carbs})
                        total_gels_count += 1
                        total_gels_g += hour_carbs

                if h == 2:
                    note = "Steady carbohydrate flow prevents liver glycogen depletion and late-ride fade."
                elif h == 3:
                    note = "Caffeine stimulates central nervous system alertness and mobilizes free fatty acids during late-ride fatigue."
                else:
                    note = "Rely primarily on liquid and hydrogel fuel now. Blood flow to the GI tract decreases as cardiac drift increases."

            hourly_schedule.append({
                "hour": h,
                "label": f"Hour {h} ({start_min}–{end_min} min)",
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

    # 8. Jersey Pocket Packing Checklist (derived 1:1 from hourly_schedule & fluid targets)
    total_fluid_ml = round(fluid_ml_per_hour * dur_hours)
    bottles_needed = max(1, math.ceil(total_fluid_ml / 750.0))
    bottle_label = "1x 750ml Cycling Water Bottle" if bottles_needed == 1 else f"{bottles_needed}x 750ml Cycling Water Bottles"

    carb_bottles = 0
    if total_drink_mix_g > 0:
        carb_bottles = min(bottles_needed, max(1, math.ceil(total_drink_mix_g / 50.0)))
        plain_bottles = bottles_needed - carb_bottles
        if bottles_needed == 1:
            bottle_detail = f"~{total_fluid_liters}L fluid target — dissolve your {total_drink_mix_g}g carb mix & ~{total_sodium_mg}mg sodium inside"
        elif plain_bottles == 0:
            bottle_detail = f"All {bottles_needed} bottles with carb & electrolyte mix (~{total_fluid_liters}L total)"
        else:
            bottle_detail = f"{carb_bottles} with carb mix, {plain_bottles} with water/electrolytes (~{total_fluid_liters}L total)"
    elif total_carbs_on_bike == 0:
        bottle_detail = f"Plain water or light electrolyte mix (~{total_sodium_mg}mg sodium, 0g carbs)"
    else:
        bottle_detail = f"Water with electrolytes (~{total_fluid_liters}L total, ~{total_sodium_mg}mg sodium)"

    checklist = [
        {"item": bottle_label, "detail": bottle_detail, "icon": "🍼", "carbs_g": 0},
    ]

    if total_drink_mix_g > 0:
        if bottles_needed == 1:
            mix_detail = (
                f"Dissolve into bottle before rolling out (covers full {total_carbs_on_bike}g carb target)"
                if total_drink_mix_g == total_carbs_on_bike
                else "Dissolve into bottle before rolling out"
            )
        elif carb_bottles == 1:
            mix_detail = "Dissolve into 1 bottle before rolling out"
        else:
            per_bottle_g = round(total_drink_mix_g / carb_bottles)
            mix_detail = f"Split across {carb_bottles} bottles (~{per_bottle_g}g carbs each) before rolling out"
        checklist.append({
            "item": f"Carb Drink Mix ({total_drink_mix_g}g carbs)",
            "detail": mix_detail,
            "icon": "🧪",
            "carbs_g": total_drink_mix_g,
        })

    if total_gels_count > 0:
        if total_gels_count == 1:
            gel_label = f"1x Energy Gel or Chews ({total_gels_g}g carbs)"
            gel_detail = (
                "Choose a caffeinated gel (25–50mg) for late-ride focus"
                if caffeine_gels_count > 0
                else "Carry in jersey pocket for mid-ride fuel"
            )
        else:
            avg_gel_g = round(total_gels_g / total_gels_count)
            gel_label = f"{total_gels_count}x Energy Gels ({total_gels_g}g carbs total)"
            if caffeine_gels_count > 0:
                caf_txt = "1 with caffeine" if caffeine_gels_count == 1 else f"{caffeine_gels_count} with caffeine"
                gel_detail = f"~{avg_gel_g}g carbs each; include {caf_txt} for Hour 3+"
            else:
                gel_detail = f"~{avg_gel_g}g carbs each; carry in jersey pocket"
        checklist.append({"item": gel_label, "detail": gel_detail, "icon": "⚡", "carbs_g": total_gels_g})

    if total_solids_count > 0:
        if total_solids_count == 1:
            solid_label = f"1x Solid Fuel ({total_solids_g}g carbs)"
            solid_detail = "Stroopwafel or rice cake for Hour 2 on flat/gentle sections"
        else:
            solid_label = f"{total_solids_count}x Solid Fuel Packs ({total_solids_g}g carbs total)"
            solid_detail = "Stroopwafels or rice cakes for steady mid-ride fueling"
        checklist.append({"item": solid_label, "detail": solid_detail, "icon": "🧇", "carbs_g": total_solids_g})

    if is_outdoor and ((temp_f >= 82 and humidity_pct >= 60) or temp_f >= 88):
        checklist.append({
            "item": "2x Electrolyte Salt Capsules",
            "detail": "Carried in pocket to prevent cramping in very hot/humid weather",
            "icon": "🧂",
            "carbs_g": 0,
        })

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
