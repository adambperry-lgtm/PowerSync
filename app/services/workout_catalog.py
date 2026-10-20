"""
Workout Archetype Catalog & Anti-Repetition Engine
Provides diverse, periodized workout structures across physiological training zones
while strictly respecting athlete invariants (progressive wattage ramps, weekday duration caps).
"""

import math
from typing import Dict, Any, List, Optional, Tuple
from app.database import get_db_connection, get_current_user_id, get_active_target_plan

# ==============================================================================
# 1. INTERVAL BUILDER HELPERS (All enforce progressive wattage ramps)
# ==============================================================================

def make_progressive_warmup(duration_sec: int = 420) -> Dict[str, Any]:
    """Generates a progressive warmup wattage ramp (45% -> 75% FTP). Never flat."""
    return {
        "type": "Warmup",
        "duration_sec": max(300, duration_sec),
        "power_low_pct": 45,
        "power_high_pct": 75,
        "cadence": 88,
        "name": "Progressive Warmup Ramp"
    }

def make_progressive_cooldown(duration_sec: int = 300) -> Dict[str, Any]:
    """Generates a progressive cooldown wattage ramp (65% -> 40% FTP). Never flat."""
    return {
        "type": "Cooldown",
        "duration_sec": max(240, duration_sec),
        "power_low_pct": 65,
        "power_high_pct": 40,
        "cadence": 82,
        "name": "Progressive Cooldown Ramp"
    }


# ==============================================================================
# 2. SWEET SPOT ARCHETYPES (88% - 94% FTP)
# ==============================================================================

def build_sweet_spot_sustained(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Sustained Sweet Spot Blocks (steady 88-91% FTP)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 480
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)

    if duration_min <= 45:
        # 2 blocks of sustained Sweet Spot
        recovery_dur = 180
        block_dur = max(300, (avail - recovery_dur) // 2)
        intervals = [
            make_progressive_warmup(w_dur),
            {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 89, "cadence": 90, "name": f"Sweet Spot Block 1 ({block_dur // 60}m @ 89%)"},
            {"type": "SteadyState", "duration_sec": recovery_dur, "power_pct": 55, "cadence": 85, "name": "Aerobic Recovery Valley"},
            {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 91, "cadence": 92, "name": f"Sweet Spot Block 2 ({block_dur // 60}m @ 91%)"},
            make_progressive_cooldown(c_dur)
        ]
    else:
        # 3 blocks of sustained Sweet Spot
        recovery_dur = 180
        block_dur = max(360, (avail - (recovery_dur * 2)) // 3)
        intervals = [
            make_progressive_warmup(w_dur),
            {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 88, "cadence": 90, "name": f"Sweet Spot Block 1 ({block_dur // 60}m @ 88%)"},
            {"type": "SteadyState", "duration_sec": recovery_dur, "power_pct": 55, "cadence": 85, "name": "Aerobic Recovery Valley"},
            {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 90, "cadence": 92, "name": f"Sweet Spot Block 2 ({block_dur // 60}m @ 90%)"},
            {"type": "SteadyState", "duration_sec": recovery_dur, "power_pct": 55, "cadence": 85, "name": "Aerobic Recovery Valley"},
            {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 92, "cadence": 94, "name": f"Sweet Spot Block 3 ({block_dur // 60}m @ 92%)"},
            make_progressive_cooldown(c_dur)
        ]

    return {
        "archetype_id": "sst_sustained",
        "title": f"{duration_min}-Min Sweet Spot Sustained Blocks",
        "focus_area": "Sweet Spot Aerobic Density",
        "estimated_tss": int(duration_min * 0.78),
        "ai_rationale": (
            f"Focuses on sustained aerobic density at 89–91% FTP to expand mitochondrial density and glycogen efficiency. "
            f"Unlike over-unders, these steady blocks build raw muscular stamina and mental composure under continuous sub-threshold tension."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_sweet_spot_criss_cross(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Criss-Cross Surges: 88% FTP baseline with 30s surges at 105% FTP to practice clearing lactate."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)

    reps = max(3, avail // 150)
    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 30,
            "off_duration_sec": 120,
            "on_power_pct": 105,
            "off_power_pct": 88,
            "cadence": 98,
            "cadence_rest": 90,
            "name": f"{reps}x Criss-Cross Surges (30s @ 105% / 2m @ 88%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "sst_criss_cross",
        "title": f"{duration_min}-Min Sweet Spot Criss-Cross Surges",
        "focus_area": "Lactate Shuttling & Surges",
        "estimated_tss": int(duration_min * 0.81),
        "ai_rationale": (
            f"Employs dynamic criss-cross intervals: 30-second surges at 105% FTP punch above threshold, followed by 2 minutes at 88% Sweet Spot. "
            f"This forces your oxidative fibers to buffer and consume lactate while still operating at high sub-threshold power."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_sweet_spot_ladder(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Stepped Sweet Spot Ladder: Ascending steps through the sweet spot zone (86% -> 90% -> 94%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 480
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)

    step_dur = max(180, (avail - 180) // 6)
    intervals = [
        make_progressive_warmup(w_dur),
        # Ladder 1
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 86, "cadence": 90, "name": "Step 1: Low Sweet Spot (86%)"},
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 90, "cadence": 92, "name": "Step 2: Mid Sweet Spot (90%)"},
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 94, "cadence": 94, "name": "Step 3: High Sweet Spot (94%)"},
        {"type": "SteadyState", "duration_sec": 180, "power_pct": 55, "cadence": 85, "name": "Recovery Spin"},
        # Ladder 2
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 86, "cadence": 90, "name": "Step 1: Low Sweet Spot (86%)"},
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 90, "cadence": 92, "name": "Step 2: Mid Sweet Spot (90%)"},
        {"type": "SteadyState", "duration_sec": step_dur, "power_pct": 94, "cadence": 94, "name": "Step 3: High Sweet Spot (94%)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "sst_ladder",
        "title": f"{duration_min}-Min Stepped Sweet Spot Ladder",
        "focus_area": "Ascending Aerobic Tension",
        "estimated_tss": int(duration_min * 0.79),
        "ai_rationale": (
            f"Step-loaded intervals gradually increasing tension from 86% up to 94% FTP. "
            f"Progressive step loading teaches controlled pacing, progressive motor unit recruitment, and mental focus as fatigue accumulates."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_sweet_spot_over_under(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Classic Sweet Spot Over-Unders (2m @ 95% / 2m @ 88%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    primer_dur = 180
    spin_dur = 120
    fixed_dur = w_dur + c_dur + primer_dur + spin_dur
    main_dur = max(480, dur_sec - fixed_dur)
    reps = max(2, main_dur // 240)

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": primer_dur, "power_pct": 88, "cadence": 92, "name": "Sweet Spot Primer"},
        {"type": "SteadyState", "duration_sec": spin_dur, "power_pct": 55, "cadence": 85, "name": "Valley Spin"},
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 120,
            "off_duration_sec": 120,
            "on_power_pct": 95,
            "off_power_pct": 88,
            "cadence": 92,
            "cadence_rest": 88,
            "name": f"{reps}x Sweet Spot Over-Unders (2m @ 95% / 2m @ 88%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "sst_over_under",
        "title": f"{duration_min}-Min Sweet Spot Over-Unders",
        "focus_area": "Sweet Spot Over-Unders",
        "estimated_tss": int(duration_min * 0.82),
        "ai_rationale": (
            f"Alternating between 95% FTP (Over) and 88% FTP (Under) to train your muscles to process metabolites at high aerobic throughput. "
            f"The continuous tension maintains maximum aerobic density with rapid recovery clearance."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_sweet_spot_pyramid(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Pyramid Sweet Spot Intervals (88% -> 92% -> 95% -> 92% -> 88%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    unit = max(120, avail // 7)

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": unit, "power_pct": 88, "cadence": 90, "name": "Pyramid Base (88%)"},
        {"type": "SteadyState", "duration_sec": unit, "power_pct": 92, "cadence": 92, "name": "Pyramid Climb (92%)"},
        {"type": "SteadyState", "duration_sec": unit, "power_pct": 95, "cadence": 94, "name": "Pyramid Peak (95%)"},
        {"type": "SteadyState", "duration_sec": unit, "power_pct": 92, "cadence": 92, "name": "Pyramid Descent (92%)"},
        {"type": "SteadyState", "duration_sec": unit, "power_pct": 88, "cadence": 90, "name": "Pyramid Finish (88%)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "sst_pyramid",
        "title": f"{duration_min}-Min Sweet Spot Pyramid",
        "focus_area": "Pyramid Power Density",
        "estimated_tss": int(duration_min * 0.80),
        "ai_rationale": (
            f"Ascending to a 95% peak and descending back to 88% Sweet Spot. "
            f"The variable duration and progressive intensity shifts challenge your cardiac output and break interval monotony."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }


# ==============================================================================
# 3. TEMPO ARCHETYPES (76% - 85% FTP)
# ==============================================================================

def build_tempo_cadence_ladders(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Tempo Cadence Ladders: Alternating cadences (90 / 96 RPM) at 78-82% FTP."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min < 45 else 480
    c_dur = 240 if duration_min < 45 else 300
    val_sec = 180 if duration_min < 45 else 240
    fixed_sec = w_dur + val_sec + c_dur
    work_sec = max(180, (dur_sec - fixed_sec) // 2)

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": work_sec, "power_pct": 80, "cadence": 90, "name": "Tempo Block 1 (90 RPM)"},
        {"type": "SteadyState", "duration_sec": val_sec, "power_pct": 55, "cadence": 85, "name": "Recovery Valley"},
        {"type": "SteadyState", "duration_sec": work_sec, "power_pct": 82, "cadence": 96, "name": "Tempo Block 2 (96 RPM)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "tempo_cadence_ladders",
        "title": f"{duration_min}-Min Tempo Cadence Ladders",
        "focus_area": "Tempo & Cadence Efficiency",
        "estimated_tss": int(duration_min * 0.68),
        "ai_rationale": (
            f"Targets Zone 3 tempo (80–82% FTP) with dual cadence objectives (90 RPM ground work and 96 RPM spin efficiency). "
            f"Trains neuromuscular versatility and smooth pedaling biomechanics while staying comfortably below threshold."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_tempo_surges(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Tempo Aerobic Cruise with Micro-Surges (80% FTP base with 15s 100+ RPM spin-ups)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min < 45 else 420
    c_dur = 240 if duration_min < 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    reps = max(4, avail // 180)

    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 15,
            "off_duration_sec": 165,
            "on_power_pct": 105,
            "off_power_pct": 80,
            "cadence": 105,
            "cadence_rest": 90,
            "name": f"{reps}x Tempo Surges (15s @ 105% 105 RPM / 2m45s @ 80%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "tempo_surges",
        "title": f"{duration_min}-Min Tempo Cruise & Spin-Ups",
        "focus_area": "Neuromuscular Cadence & Tempo",
        "estimated_tss": int(duration_min * 0.70),
        "ai_rationale": (
            f"Steady 80% FTP tempo base punctuated by 15-second high-cadence surges (105 RPM) every 3 minutes. "
            f"Recruits fast-twitch motor units without elevating heart rate into heavy glycolytic debt."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_tempo_torque(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Low-Cadence Muscular Torque (70-75 RPM tempo blocks to build climbing torque)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min < 45 else 480
    c_dur = 240 if duration_min < 45 else 300
    val_sec = 180
    avail = dur_sec - (w_dur + c_dur + val_sec)
    block_dur = max(240, avail // 2)

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 80, "cadence": 72, "name": "Torque Block 1 (72 RPM Low Cadence)"},
        {"type": "SteadyState", "duration_sec": val_sec, "power_pct": 55, "cadence": 92, "name": "High-Cadence Flush (92 RPM)"},
        {"type": "SteadyState", "duration_sec": block_dur, "power_pct": 82, "cadence": 74, "name": "Torque Block 2 (74 RPM Low Cadence)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "tempo_torque",
        "title": f"{duration_min}-Min Muscular Torque & Climbing Tempo",
        "focus_area": "Muscular Torque & Climbing Stamina",
        "estimated_tss": int(duration_min * 0.69),
        "ai_rationale": (
            f"Controlled low-cadence tempo intervals (72–74 RPM) designed to build force production and tendon resilience for sustained outdoor climbs. "
            f"Builds functional climbing torque while protecting recovery reserves."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_tempo_sustained_cruise(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Sustained Aerobic Tempo Cruise (continuous 78-82% FTP)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min < 45 else 420
    c_dur = 240 if duration_min < 45 else 300
    main_dur = dur_sec - (w_dur + c_dur)

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": main_dur, "power_pct": 80, "cadence": 92, "name": "Zone 3 Aerobic Cruise (80% FTP)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "tempo_cruise",
        "title": f"{duration_min}-Min Steady Aerobic Tempo Cruise",
        "focus_area": "Aerobic Efficiency & Tempo",
        "estimated_tss": int(duration_min * 0.67),
        "ai_rationale": (
            f"Unbroken Zone 3 tempo cruise (80% FTP) flanked by progressive wattage ramps. "
            f"Develops steady-state pacing, fat-carbohydrate crossover efficiency, and endurance resilience."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }


# ==============================================================================
# 4. VO2 MAX ARCHETYPES (105% - 120% FTP)
# ==============================================================================

def build_vo2_microbursts_40_20(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """40/20 High-Aerobic Microbursts (40s @ 120% / 20s @ 50%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 480
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    reps = max(4, avail // 60)

    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 40,
            "off_duration_sec": 20,
            "on_power_pct": 120,
            "off_power_pct": 50,
            "cadence": 100,
            "cadence_rest": 85,
            "name": f"{reps}x 40/20 VO2 Microbursts (40s @ 120% / 20s @ 50%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "vo2_40_20",
        "title": f"{duration_min}-Min 40/20 VO2 Max Microbursts",
        "focus_area": "VO2 Max & Anaerobic Capacity",
        "estimated_tss": int(duration_min * 0.90),
        "ai_rationale": (
            f"High-frequency 40/20 microbursts (40s @ 120% FTP with 20s recovery). "
            f"Short rest intervals keep respiration and cardiac output at VO2 max while allowing rapid partial phosphocreatine replenishment."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_vo2_repeats_3min(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Classic 3-Min VO2 Max Repeats (3m @ 115% / 3m @ 50%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    reps = max(2, avail // 360)

    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 180,
            "off_duration_sec": 180,
            "on_power_pct": 115,
            "off_power_pct": 50,
            "cadence": 98,
            "cadence_rest": 85,
            "name": f"{reps}x 3-Min VO2 Max Blocks (3m @ 115% / 3m @ 50%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "vo2_3min_repeats",
        "title": f"{duration_min}-Min VO2 Max 3-Min Repeats",
        "focus_area": "Aerobic Capacity Ceiling",
        "estimated_tss": int(duration_min * 0.88),
        "ai_rationale": (
            f"Long-duration 3-minute repeats at 115% FTP. These blocks push maximum stroke volume and expand pulmonary oxygen uptake, "
            f"elevating your aerobic ceiling."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_vo2_30_30(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """30/30 High-Intensity Turnover (30s @ 125% / 30s @ 50%)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    reps = max(5, avail // 60)

    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": reps,
            "on_duration_sec": 30,
            "off_duration_sec": 30,
            "on_power_pct": 125,
            "off_power_pct": 50,
            "cadence": 102,
            "cadence_rest": 85,
            "name": f"{reps}x 30/30 VO2 Surges (30s @ 125% / 30s @ 50%)"
        },
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "vo2_30_30",
        "title": f"{duration_min}-Min 30/30 High-Intensity Turnover",
        "focus_area": "High-End Aerobic Turnover",
        "estimated_tss": int(duration_min * 0.89),
        "ai_rationale": (
            f"Punchy 30/30 intervals at 125% FTP. Develops punchiness and anaerobic battery recycling with rapid cadence turnover."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }


# ==============================================================================
# 5. ZONE 2 ENDURANCE ARCHETYPES (Alternative 2 & Base Days)
# ==============================================================================

def build_endurance_steady(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Zone 2 Steady Aerobic Foundation (65% FTP)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 480
    c_dur = 240 if duration_min <= 45 else 300
    main_dur = max(600, dur_sec - (w_dur + c_dur))

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": main_dur, "power_pct": 65, "cadence": 90, "name": "Zone 2 Aerobic Base (65% FTP)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "endurance_steady",
        "title": f"{duration_min}-Min Steady Aerobic Foundation",
        "focus_area": "Zone 2 Aerobic Base",
        "estimated_tss": int(duration_min * 0.52),
        "ai_rationale": (
            f"Steady Zone 2 aerobic foundation (65% FTP). Builds capillary beds and stimulates mitochondrial biogenesis "
            f"without generating sympathetic fatigue."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_endurance_cadence_flush(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Zone 2 Cadence Flushes (alternating 86 RPM and 96 RPM at 65% FTP)."""
    dur_sec = duration_min * 60
    w_dur = 360 if duration_min <= 45 else 420
    c_dur = 240 if duration_min <= 45 else 300
    avail = dur_sec - (w_dur + c_dur)
    half = avail // 2

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": half, "power_pct": 65, "cadence": 86, "name": "Z2 Smooth Base (86 RPM)"},
        {"type": "SteadyState", "duration_sec": half, "power_pct": 66, "cadence": 96, "name": "Z2 Cadence Spin (96 RPM)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "endurance_cadence_flush",
        "title": f"{duration_min}-Min Zone 2 Cadence Flushes",
        "focus_area": "Aerobic Cadence Variation",
        "estimated_tss": int(duration_min * 0.53),
        "ai_rationale": (
            f"Zone 2 aerobic conditioning with alternating cadence segments (86 RPM muscular spin and 96 RPM aerobic spin). "
            f"Enhances neuromuscular coordination under light cardiovascular load."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }

def build_endurance_progressive_build(duration_min: int, ftp: int, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """Progressive Aerobic Build (55% -> 65% -> 72% FTP)."""
    dur_sec = duration_min * 60
    w_dur = 300
    c_dur = 240
    avail = dur_sec - (w_dur + c_dur)
    third = avail // 3

    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": third, "power_pct": 58, "cadence": 88, "name": "Z1/Z2 Easy Flow (58%)"},
        {"type": "SteadyState", "duration_sec": third, "power_pct": 65, "cadence": 90, "name": "Z2 Core Base (65%)"},
        {"type": "SteadyState", "duration_sec": third, "power_pct": 72, "cadence": 92, "name": "Z2 Upper Aerobic (72%)"},
        make_progressive_cooldown(c_dur)
    ]

    return {
        "archetype_id": "endurance_progressive_build",
        "title": f"{duration_min}-Min Progressive Aerobic Build",
        "focus_area": "Progressive Aerobic Conditioning",
        "estimated_tss": int(duration_min * 0.55),
        "ai_rationale": (
            f"Gentle progressive build through the aerobic spectrum (58% -> 65% -> 72% FTP). "
            f"Gradually activates working muscle fibers and promotes lipid oxidation."
            + (f" {plan_ctx}" if plan_ctx else "")
        ),
        "intervals": intervals
    }


# ==============================================================================
# 6. TIME-CRUNCHED EXPRESS ARCHETYPES (35-min options)
# ==============================================================================

def build_express_microbursts(duration_min: int = 35, ftp: int = 250, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """35-Min Microburst & Cadence Flush (8x 30s @ 110% / 90s @ 55% + aerobic bridge)."""
    dur = 35
    w_dur = 360 # 6m
    c_dur = 300 # 5m
    # 8 reps * 120s = 960s (16m)
    # Bridge = 2100 - (360 + 960 + 300) = 480s (8m)
    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": 8,
            "on_duration_sec": 30,
            "off_duration_sec": 90,
            "on_power_pct": 110,
            "off_power_pct": 55,
            "cadence": 102,
            "cadence_rest": 85,
            "name": "8x 30s High Cadence Bursts (110%)"
        },
        {"type": "SteadyState", "duration_sec": 480, "power_pct": 68, "cadence": 90, "name": "Aerobic Bridge (68%)"},
        make_progressive_cooldown(c_dur)
    ]
    return {
        "archetype_id": "express_microbursts",
        "title": "35-Min Microburst & Cadence Flush",
        "focus_area": "Time-Crunched High Efficiency",
        "duration_minutes": dur,
        "estimated_tss": 36,
        "ai_rationale": "Short on time? 30-second cadence surges stimulate motor unit recruitment and cardiovascular turnover in half the time.",
        "intervals": intervals
    }

def build_express_40_20(duration_min: int = 35, ftp: int = 250, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """35-Min 40/20 Aerobic Shock (2 sets of 40/20)."""
    dur = 35
    w_dur = 360 # 6m
    c_dur = 300 # 5m
    # Total = 2100s. Remainder = 2100 - 660 = 1440s (24m).
    # Set 1: 8 reps * 60s = 480s (8m)
    # Mid-valley: 480s (8m)
    # Set 2: 8 reps * 60s = 480s (8m)
    intervals = [
        make_progressive_warmup(w_dur),
        {
            "type": "Repeats",
            "repeat": 8,
            "on_duration_sec": 40,
            "off_duration_sec": 20,
            "on_power_pct": 115,
            "off_power_pct": 50,
            "cadence": 98,
            "cadence_rest": 85,
            "name": "Set 1: 8x 40/20 Surges (115%)"
        },
        {"type": "SteadyState", "duration_sec": 480, "power_pct": 55, "cadence": 88, "name": "Mid-Session Valley Flush"},
        {
            "type": "Repeats",
            "repeat": 8,
            "on_duration_sec": 40,
            "off_duration_sec": 20,
            "on_power_pct": 115,
            "off_power_pct": 50,
            "cadence": 98,
            "cadence_rest": 85,
            "name": "Set 2: 8x 40/20 Surges (115%)"
        },
        make_progressive_cooldown(c_dur)
    ]
    return {
        "archetype_id": "express_40_20",
        "title": "35-Min 40/20 Aerobic Shock",
        "focus_area": "High-Efficiency Aerobic Capacity",
        "duration_minutes": dur,
        "estimated_tss": 38,
        "ai_rationale": "Two sets of 40/20 surges maximize aerobic cardiac output and oxygen consumption within an efficient 35-minute block.",
        "intervals": intervals
    }

def build_express_tempo_primer(duration_min: int = 35, ftp: int = 250, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """35-Min Tempo & Cadence Primer (two tempo blocks with alternating cadence)."""
    dur = 35
    w_dur = 360 # 6m
    c_dur = 300 # 5m
    # Remainder = 2100 - 660 = 1440s (24m).
    # Block 1: 600s (10m), Valley: 240s (4m), Block 2: 600s (10m)
    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": 600, "power_pct": 80, "cadence": 90, "name": "Tempo Block 1 (90 RPM)"},
        {"type": "SteadyState", "duration_sec": 240, "power_pct": 55, "cadence": 85, "name": "Spin Valley"},
        {"type": "SteadyState", "duration_sec": 600, "power_pct": 82, "cadence": 96, "name": "Tempo Block 2 (96 RPM)"},
        make_progressive_cooldown(c_dur)
    ]
    return {
        "archetype_id": "express_tempo_primer",
        "title": "35-Min Tempo & Cadence Primer",
        "focus_area": "Time-Crunched Muscular Endurance",
        "duration_minutes": dur,
        "estimated_tss": 35,
        "ai_rationale": "Focused 35-minute tempo workout targeting aerobic muscular endurance without fatigue spillover.",
        "intervals": intervals
    }

def build_express_stepped_punch(duration_min: int = 35, ftp: int = 250, plan_ctx: Optional[str] = None) -> Dict[str, Any]:
    """35-Min Stepped Threshold Punch (ascending 88% -> 92% -> 96% -> 100%)."""
    dur = 35
    w_dur = 360 # 6m
    c_dur = 300 # 5m
    # Remainder = 2100 - 660 = 1440s (24m) -> 4 steps of 360s (6m each)
    step = 360
    intervals = [
        make_progressive_warmup(w_dur),
        {"type": "SteadyState", "duration_sec": step, "power_pct": 88, "cadence": 90, "name": "Step 1: Low Sweet Spot (88%)"},
        {"type": "SteadyState", "duration_sec": step, "power_pct": 92, "cadence": 92, "name": "Step 2: High Sweet Spot (92%)"},
        {"type": "SteadyState", "duration_sec": step, "power_pct": 96, "cadence": 94, "name": "Step 3: Sub-Threshold (96%)"},
        {"type": "SteadyState", "duration_sec": step, "power_pct": 100, "cadence": 96, "name": "Step 4: Threshold Peak (100%)"},
        make_progressive_cooldown(c_dur)
    ]
    return {
        "archetype_id": "express_stepped_punch",
        "title": "35-Min Stepped Threshold Punch",
        "focus_area": "Threshold Stepped Pacing",
        "duration_minutes": dur,
        "estimated_tss": 37,
        "ai_rationale": "A 35-minute ascending stepped ladder from 88% to 100% FTP. Sharpens threshold pacing in minimal time.",
        "intervals": intervals
    }


# ==============================================================================
# 7. ARCHETYPE REGISTRY & ROTATION ENGINE
# ==============================================================================

ZONE_ARCHETYPES = {
    "sweet_spot": [
        build_sweet_spot_sustained,
        build_sweet_spot_criss_cross,
        build_sweet_spot_ladder,
        build_sweet_spot_over_under,
        build_sweet_spot_pyramid
    ],
    "tempo": [
        build_tempo_cadence_ladders,
        build_tempo_surges,
        build_tempo_torque,
        build_tempo_sustained_cruise
    ],
    "vo2_max": [
        build_vo2_microbursts_40_20,
        build_vo2_repeats_3min,
        build_vo2_30_30
    ],
    "endurance_base": [
        build_endurance_steady,
        build_endurance_cadence_flush,
        build_endurance_progressive_build
    ],
    "express": [
        build_express_microbursts,
        build_express_40_20,
        build_express_tempo_primer,
        build_express_stepped_punch
    ]
}

def get_recent_workout_history(user_id: Optional[str] = None, limit: int = 5) -> List[str]:
    """
    Retrieves recent titles and normalized keywords from workouts and strava_activities
    to detect recently used archetypes and prevent repetitive prescriptions.
    """
    uid = user_id or get_current_user_id()
    recent_names = []
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 1. Check workouts table
        c.execute("SELECT title FROM workouts WHERE user_id = ? ORDER BY date DESC LIMIT ?", (uid, limit))
        for row in c.fetchall():
            if row[0]:
                recent_names.append(row[0].lower())

        # 2. Check strava_activities table
        c.execute("SELECT name FROM strava_activities WHERE user_id = ? ORDER BY start_date DESC LIMIT ?", (uid, limit))
        for row in c.fetchall():
            if row[0]:
                recent_names.append(row[0].lower())

        conn.close()
    except Exception:
        pass

    return recent_names

def select_diverse_archetype(
    zone: str,
    duration_min: int,
    ftp: int = 250,
    plan_ctx: Optional[str] = None,
    user_id: Optional[str] = None,
    forced_archetype_id: Optional[str] = None,
    extra_history: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Selects an archetype within the specified physiological zone that has NOT
    been completed or prescribed recently, preventing repetitive workouts.
    """
    builders = ZONE_ARCHETYPES.get(zone, ZONE_ARCHETYPES["sweet_spot"])
    db_history = get_recent_workout_history(user_id, limit=6)
    recent_history = (list(extra_history) if extra_history else []) + db_history

    # If an explicit archetype was requested
    if forced_archetype_id:
        for b in builders:
            candidate = b(duration_min, ftp, plan_ctx)
            if candidate["archetype_id"] == forced_archetype_id:
                candidate["duration_minutes"] = duration_min
                return candidate

    # Score each candidate: lower score = less recently seen
    zone_prefixes = ["sst_", "tempo_", "vo2_", "endurance_", "express_"]
    scored_candidates = []
    for idx, b in enumerate(builders):
        candidate = b(duration_min, ftp, plan_ctx)
        arch_id = candidate["archetype_id"]
        title_lower = candidate["title"].lower()

        # Clean distinctive archetype keywords (strip zone prefix)
        clean_arch_key = arch_id
        for pfx in zone_prefixes:
            if clean_arch_key.startswith(pfx):
                clean_arch_key = clean_arch_key[len(pfx):]
                break
        distinctive_keywords = [kw for kw in clean_arch_key.split("_") if len(kw) >= 3]

        # Check recency in history
        recency_penalty = 0
        for h_idx, past_title in enumerate(recent_history):
            past_lower = past_title.lower()
            # 1. Exact title containment
            if title_lower in past_lower or clean_arch_key in past_lower:
                recency_penalty += (len(recent_history) - h_idx) * 50
            else:
                # 2. Distinctive keyword containment (e.g. "ladder", "torque", "criss", "surge", "cruise")
                match_count = sum(1 for kw in distinctive_keywords if kw in past_lower)
                if match_count >= 1:
                    recency_penalty += (len(recent_history) - h_idx) * 25 * match_count

        scored_candidates.append((recency_penalty, idx, candidate))

    # Sort by lowest recency penalty (least recently used)
    scored_candidates.sort(key=lambda x: (x[0], x[1]))
    selected = scored_candidates[0][2]
    selected["duration_minutes"] = duration_min
    return selected
