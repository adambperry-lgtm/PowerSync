# PowerSync Version History & Changelog

All notable changes to the PowerSync Adaptive Cycling Coach & Zwift Sync platform are documented in this file.
From version 2.2.0 forward, this changelog and the in-app version endpoint (`/api/version`) are automatically updated with every meaningful release.

## [2.9.4] - 2026-11-13
### Fixed
- **Initial-Load Ride Debrief Persistence**:
  - Fixed `loadWorkout()` in `app/static/js/app.js` unconditionally setting `state.activeCoachView = "prescribed"` on initial page load, which had been overriding the automatic **Ride Debrief** view whenever a completed ride existed for today.
  - `loadWorkout()` now only switches `state.activeCoachView` to `"prescribed"` when the user explicitly requests a duration, intensity, or note adjustment.

## [2.9.3] - 2026-11-13
### Changed
- **Automatic Top-Right Ride Debrief Mode**:
  - Updated `renderAiCoachTodayCard()` in `app/static/js/app.js` so the top-right panel automatically switches from **Ride Briefing** to **Ride Debrief** once a ride has been detected for today (`isCompletedToday === true`), unless the athlete explicitly switches back to the Ride Briefing view.
  - Updated the card header (`#coachCardTitle`) dynamically between `"Ride Debrief"` and `"Ride Briefing"`, preserved the `"Full Debrief ↓"` jump link in debrief mode, and fixed Duration metric text color (`var(--text-primary)`) for crisp contrast in the light theme.

## [2.9.2] - 2026-11-13
### Fixed
- **Whole-Ride Normalized Power Target Alignment**:
  - Updated `resolve_day_prescribed_target` in `app/services/review_coach.py` via `_estimate_workout_np_and_work_pct()` to calculate the expected whole-ride Normalized Power (Coggan 30-second rolling NP) across **all** prescribed intervals (`Warmup`, `Cooldown`, `Ramp`, `SteadyState`, `Rest`, and `Repeats` blocks) instead of only averaging main work blocks.
  - Eliminates the systematic upward bias where "Power vs Target" showed a higher wattage than what an exact ERG ride actually produces once warmup, cooldown, and recovery valleys are included, while preserving the primary training zone label (e.g., `Zone 3 Tempo`, `VO2 Max`) from the work intervals.

## [2.9.1] - 2026-11-13
### Fixed
- **Exact Zwift & Intervals.icu Target Wattage Precision**:
  - Fixed 1-watt under-target drops (e.g., 200W prescribed in PowerSync appearing as 199W in Zwift) caused by Python banker's rounding (`round()`) vs. frontend `Math.round()`, Intervals.icu text-step integer `%` truncation, and stale cached `.zwo` / Intervals.icu payloads.
  - Updated `_calculate_zwo_power` in `app/services/zwift_service.py` to use half-up rounding (`math.floor(x + 0.5)`) matching `app.js` and a `+0.25W` compensation offset.
  - Updated `generate_intervals_icu_text` to emit precision-compensated 2-decimal percentages when athlete FTP is provided, and updated `push_to_intervals_icu` and `/api/workouts/download-zwo` to always regenerate `.zwo` and Intervals.icu text using the athlete's current FTP.

## [2.9.0] - 2026-11-13
### Added
- **Persistent AI Coach Conversation Memory**:
  - Added `coach_chat_messages` and `coach_conversation_memory` SQLite tables in `app/database.py`, strictly scoped by `user_id` for complete multi-user isolation.
  - Persists every athlete and AI coach message (including `proposed_action` cards, `executed_tools` pills, provider, and model metadata) across browser reloads, sessions, and devices.
  - Added automatic long-term memory distillation (`distill_conversation_memory` / `maybe_update_conversation_memory` in `app/services/coach_chat_service.py`) that summarizes older turns beyond the active 14-message context window into durable coaching notes (injuries, goals, schedule constraints, and preferences) and injects them into `build_system_prompt`.
  - Added `GET /api/chat/history`, `DELETE /api/chat/history`, and `DELETE /api/chat/memory` endpoints in `app/routers/chat.py`.
  - Updated the Coach Chat drawer (`app/static/js/app.js` and `app/static/index.html`) to automatically restore persisted conversation history on open, preserve long-term memory when clearing the visible chat transcript, and provide a `🧠` memory inspection/reset control.

## [2.8.0] - 2026-11-12
### Security & Privacy
- **Strict Multi-User Privacy & Unauthenticated Data Lockdown**:
  - Addressed critical data leakage where unauthenticated visitors or incognito sessions received private athlete data (Whoop biometrics, Strava rides, training plans, AI debriefs).
  - Enforced strict session boundaries: unauthenticated visitors (`usr_guest`) receive zero personal telemetry across all endpoints (`/api/dashboard`, `/api/workouts/*`, `/api/review/*`, `/api/power/*`, `/api/chat/*`).
  - Purged all `usr_guest` fallback queries that fell back to `usr_default` across all backend services (`review_coach`, `strava_service`, `plan_service`, `power_profile_service`, `coach_chat_service`, `forecast_service`).
  - Disabled anonymous auto-login: terminated frontend automated invocation of `/api/auth/primary-login` when visiting unauthenticated, and restricted primary login to explicitly authorized environments.

### Added
- **Unauthenticated Welcome & Sign-In Gate**:
  - Implemented modern `#unauthenticatedGate` portal displayed immediately to visitors not signed in.
  - Features clear security messaging, seamless Email sign-in, Google OAuth, and developer environment demo profile switching.
  - Automatically conceals private telemetry tiles, daily debriefs, workout prescription cards, spiderweb power envelopes, and toolbar actions until the athlete authenticates.

### Fixed
- **Cross-User Syncing & Cache Mirroring**:
  - Prevented guest sessions from duplicating Strava activities, Whoop biometrics, coach chat plans, or target training profiles into other user accounts.
  - Standardized ASGI test server host resolution (`testserver`) within production route guards.

---

## [2.7.2] - 2026-11-12
### Fixed
- **Spiderweb Active Goal & Target Planner Progress Synchronization**:
  - Eliminated the bug where the All-Time PRs spiderweb displayed `0% progress` despite the Target Changes & Goal Planner showing high completion (e.g. 96.8% readiness).
  - Resolved the mathematical flaw in `get_power_spiderweb_profile` where `all_time` set `prev_envelope` identical to `cur_envelope` (`cur_w == prev_w`), creating an artificial zero initial-to-remaining gap difference `((gap - gap) / gap = 0%)`.
  - Replaced the flawed period-delta formula with the unified continuous archetype readiness model, guaranteeing that `active_goal.progress_pct` on the spiderweb header banner perfectly matches `completion_pct` on the Target Changes & Goal Planner cards.
- **Continuous Archetype Readiness Metric**:
  - Evaluates athlete power against archetype envelope targets across all 5 durations (5s, 1m, 5m, 20m, 60m) with 2.5× weighting on phenotype signature axes and 1.0× on supporting axes.
  - Duration-specific goals evaluate current duration power directly against target wattage (`(cur_w / target_w) * 100.0`).
  - Removed artificial ceilings, allowing completed goals to properly indicate 100% achievement.
- **Active Goal Planner Badge Harmonization**:
  - Updated Target Planner phenotype cards so the active goal badge displays `🎯 Active Goal (${p.completion_pct}% Readiness • ${p.total_delta_watts}W gap)` or `🎯 Active Goal (100% Achieved)`, creating complete UI consistency.

---

## [2.7.1] - 2026-11-11
### Added
- **Canonical Coggan 7-Zone Power Ribbon**:
  - Implemented the full, standard Coggan 7-Zone Power System across the athlete dashboard and backend (`get_coggan_power_zones`):
    - **Zone 1 Active Recovery** (< 55% FTP, < 138W at 250W FTP)
    - **Zone 2 Endurance** (56–75% FTP, 140–188W)
    - **Zone 3 Tempo** (76–90% FTP, 190–225W)
    - **Zone 4 Lactate Threshold** (91–105% FTP, 228–262W)
    - **Zone 5 VO2 Max** (106–120% FTP, 265–300W)
    - **Zone 6 Anaerobic Capacity** (121–150% FTP, 302–375W)
    - **Zone 7 Neuromuscular Power** (> 150% FTP, > 375W up to Peak Sprint Power 1050W)
  - Added dedicated **Sweet Spot Sub-Zone Callout Banner** (88–94% FTP, 220–235W) properly framing Sweet Spot as the high-density aerobic bridge between upper Tempo (Z3) and lower Threshold (Z4).
  - Modernized `athlete-zones-preview-grid` with a responsive, color-coded 7-card grid with physiological focus descriptors, distinct theme border accents, and full light/dark mode support.
  - Updated the Live Workout Interface canvas legend and section breakdown classes to render all 7 Coggan zones plus Sweet Spot without truncation.

### Fixed
- **Missing Zone 3 and Threshold Power Gap (234–264W)**:
  - Eliminated the UI bug where the athlete power strip only displayed 3 zones (Z2, "Z4 Sweet Spot", and Z5), which mistakenly skipped Zone 3 Tempo entirely and created a 32-watt void between Sweet Spot (233W) and VO2 Max (265W).
- **Prescribed Ride Zone Fidelity Verification**:
  - Audited workout generation and Zwift `.zwo` export engines to confirm that all interval targets are derived directly from explicit percentages of athlete FTP ($P_{\text{target}} = \text{FTP} \times \%_{\text{target}}$) and $W'$, mathematically confirming that athlete prescribed workouts were never compromised by the incomplete 3-tile UI display.

---

## [2.7.0] - 2026-11-11
### Fixed
- **Physiological Monotonicity & Steady-State Interval Power Floor**:
  - Eliminated the backwards downward duration capping formula (`min(p_1m * 0.88, est_5m)`) that artificially degraded steady-state and ERG-mode trainer workouts lacking an all-out sprint (such as 14-minute blocks at 215W+) down to 163W at 1 minute and 143W at 5 minutes.
  - Enforced fundamental cycling physics and mathematical monotonicity ($P(5s) \ge P(30s) \ge P(1m) \ge P(5m) \ge P(20m) \ge P(60m)$): a shorter duration can never yield lower maximum power than a longer sustained duration.
  - Established empirical power floors anchored to normalized power ($NP$), average power, and interval lap telemetry: sustained efforts (e.g. 14 minutes at 215W+) now correctly propagate to all shorter durations ($5m \ge 215\text{W}$, $1m \ge 225\text{W}$, $30s \ge 235\text{W}$, $5s \ge 245\text{W}$).

---

## [2.6.9] - 2026-11-11
### Fixed
- **Ride Count Consistency in Mini-Spiderwebs**:
  - Eliminated contradictory ride counts on monthly timeline cards where the header previously reported total mixed workouts while the footer reported cycling rides (e.g. November showing "6 rides" in header and "1 rides" in footer; October showing "26 rides" and "25 rides").
  - Synchronized header and footer to display canonical cycling ride counts (`X rides · Y.Zh`), clearly distinguishing non-cycling sessions as `+N cross` without inflating the ride count.
- **Indoor Cycling Classification & Power Telemetry**:
  - Enhanced `is_cycling_sport` to properly identify indoor cycling sessions, smart trainer workouts, and virtual rides that Strava/Garmin/Wahoo categorize as generic "Workout" or "IndoorCycling".
  - Incorporated power meter telemetry validation: activities with recorded mechanical power (`average_watts > 0`, `weighted_average_watts > 0`, `kilojoules > 0`, or `device_watts: True`) that are not explicitly non-cycling (run, swim, walk, gym) are accurately classified as cycling rides.
  - Refined non-cycling keyword matching with word-boundary regex to prevent false negatives on cycling titles.
- **Interval Block Peak Power Extraction**:
  - Enhanced `calculate_activity_peak_powers` to analyze sustained interval blocks (e.g. 10–25 minute efforts such as 3x14m @ 215W+), ensuring intervals accurately populate 5m VO2 Max and 20m Threshold power envelopes.
- **Live Strava Auto-Sync on Spiderweb Access**:
  - Added auto-sync check to `get_power_spiderweb_profile` ensuring newly completed Strava/Zwift rides are ingested and analyzed immediately when opening the Power Spiderweb.

---

## [2.6.8] - 2026-11-11
### Fixed
- **Mini-Spiderweb Text Bubble Overflow & Format Redesign**:
  - Resolved horizontal border overflow where narrow card containers caused 2-column duration wattage pills to spill outside the card border.
  - Redesigned monthly timeline cards with a balanced vertical hierarchy:
    - **Hero Mini-Spiderweb Centerpiece**: Dedicated centered 105px radar canvas (`viewBox="0 0 160 110"`) featuring 5 labeled duration spokes (`5s`, `1m`, `5m`, `20m`, `60m`), concentric capacity guide rings, monthly power polygon, and interactive vertex node tooltips.
    - **Full-Width 5-Column Power Strip (`.timeline-power-strip`)**: Positioned cleanly below the radar, displaying all 5 durations in a structured grid with stacked duration labels and bold wattage values that strictly respect card boundaries.
    - **Robust Container Clipping**: Applied `overflow: hidden`, `min-width: 0`, and `box-sizing: border-box` to `.spiderweb-timeline-card` and inner cells to guarantee zero border overflow across all screen resolutions and zoom levels.

---

## [2.6.7] - 2026-11-11
### Added
- **Visual 3-Line Power Duration Curve (PDC) Progression Chart**:
  - Transformed the Power Spiderweb "Power Curve Progress Over Time" section from text numbers into an interactive, multi-series Power Duration Curve chart (`#powerCurveTimelineSvg`).
  - Renders 3 distinct physiological power curves across 5 key benchmark durations (`5s`, `1m`, `5m`, `20m`, `60m`):
    - **Current Period**: Cobalt Blue (`#0052FF`) curve with gradient area shading and prominent peak wattage callouts.
    - **Previous Period**: Slate Purple (`#8B5CF6`) dashed comparison curve showing macrocycle adaptation trajectory.
    - **All-Time PR / Target Envelope**: Speed Orange (`#FF5E00`) benchmark ceiling illustrating headroom to career bests and target envelope.
  - Native inline SVG rendering with wattage grid lines, duration labels, and full dark / Speed & Summit light theme support.
- **Monthly Mini-Spiderweb Snapshots (Compact Phenotype Radars)**:
  - Rendered native 5-axis SVG mini-radar charts inside each monthly card, normalizing peak power across durations to visually expose phenotypic shape changes over time.
  - Redesigned monthly cards pairing mini-spiderweb polygons with duration wattage pills, total cycling hours, workout counts, and cumulative TSS.
- **Interactive Timeline View Switcher**:
  - Added a dedicated view toggle bar (`.timeline-view-switcher`) allowing athletes to toggle between:
    - `📊 All`: Combined 3-line PDC curve and monthly mini-spiderwebs.
    - `📈 3-Line Curve`: Focused multi-period power duration curve comparison.
    - `🕸️ Mini-Spiderwebs`: Compact monthly phenotype radar cards.

---

## [2.6.6] - 2026-11-11
### Added
- **Rider Type Change Macrocycle Reset Confirmation**:
  - Prompt athlete confirmation before resetting the periodization macrocycle block upon rider type or target changes across the Fitness Profile Target Planner and Settings modal.
  - Granular Choice: Clicking 'OK' resets the block timeline to Week 1 (Base Phase, 8-week adaptation cycle); clicking 'Cancel' adopts the new rider type / target envelope while preserving the existing macrocycle block schedule without disruption.
  - Added `reset_block` parameter support to `POST /api/power/spiderweb/goal` and `POST /api/settings`.

---

## [2.6.5] - 2026-11-11
### Added
- **Macrocycle Block Timeline Reset on Goal Activation**:
  - Automatically resets the periodization macrocycle block timeline to Week 1 (`Base Phase`, 8-week / 56-day duration) whenever an athlete selects or updates a Rider Type or Spiderweb Goal absent a specific scheduled event.
  - Eliminated trailing block expiration where newly activated training goals inherited countdowns from prior expired blocks (e.g. 8 days remaining).
  - Added 1-click **🔄 Reset Block** action button (`#btnResetProgramBlock`) in the Long-Term Program card and `POST /api/program/reset-block` endpoint to allow manual macrocycle recalibration at any time.
  - Enhanced `update_program_goal` to automatically recalculate start and target dates for phenotype blocks.

---

## [2.6.4] - 2026-11-11
### Added
- **Unified Rider Type Target Envelope & Periodization Integration**:
  - Elevated all 6 Rider Types (`PURSUITER`, `CLIMBER`, `ROULEUR`, `PUNCHEUR`, `SPRINTER`, `ALL_ROUNDER`) to first-class goal definitions across the Long-Term Goal Setting engine and Settings modal.
  - Introduced bidirectional synchronization between the Power Spiderweb / Fitness Profile Target Planner and the Long-Term Fitness Goal & Periodization card (`#cardProgram`).
  - Added visible 5-axis target envelope chip display in the Long-Term Program card (`#programEnvelopeStrip`), surfacing target wattages across all durations (`5s`, `1m`, `5m`, `20m`, `60m`).
  - Implemented `update_program_goal` service function to seamlessly synchronize rider types, weekly load baselines, and spiderweb envelopes.

### Changed
- **Phenotype Adaptation Macrocycle Absent a Specific Event**:
  - Resolved conflict between the target planner and the macrocycle card: when no specific race/event is scheduled, the macrocycle transitions from arbitrary event taper into a structured 4-phase **Phenotype Adaptation & Specialization Macrocycle**:
    1. Base Phase (Aerobic Base & Muscular Durability)
    2. Build Phase (Threshold & Progressive Power Density)
    3. Specialty Phase (Signature Weapon Development for target Rider Type)
    4. Mastery & Benchmark Test (`4. Mastery & Test`: 5-Axis Target Envelope Testing & Breakthrough Validation).
  - When an event is scheduled (via `target_plans`), the macrocycle automatically pivots Phase 4 to `4. Taper & Fresh` with race openers and freshness priming.
  - Dynamically drives long-term Target FTP from the spiderweb 20-minute target (`max(current_ftp + 5, round(target_envelope['20m'] * 0.95))`) rather than static legacy offsets.

---

## [2.6.3] - 2026-11-11
### Fixed
- **Scientific Coggan Elite Benchmark Ceiling Calibration**:
  - Replaced legacy artificial benchmark caps (e.g. 60m capped at `0.96 * FTP` / 240W, 20m at `1.08 * FTP` / 260W) with genuine Coggan Category 1 / Elite physiological W/kg standards scaled by athlete body mass (`5s: 20.5 W/kg`, `1m: 9.6 W/kg`, `5m: 6.1 W/kg`, `20m: 5.0 W/kg`, `60m: 4.6 W/kg`).
  - Enforced dynamic physiological boundary protections: benchmark ceilings and Tier 3 targets (`calculate_spiderweb_target_changes`) now dynamically evaluate against athlete current bests and all-time PRs (`max(coggan_elite, cur_watts * 1.15, all_time_pr * 1.10)`).
  - Guaranteed monotonic progression across duration target tiers (`Current Best < Tier 1 (+5%) < Tier 2 (+10%) < Tier 3 Benchmark Ceiling`), eliminating inverted targets where Tier 3 displayed lower wattages than current bests.
  - Aligned Tier 3 duration planner cards in `app/static/js/app.js` with crisp, accessible high-contrast styling (`#7C3AED` accent pill and wattage readout).

---

## [2.6.2] - 2026-11-11
### Changed
- **Long-Term Fitness Goal & Periodization Color Palette Alignment**:
  - Aligned `.program-card` / `#cardProgram` with the modern Speed & Summit light palette (`#F4F7FA` card background, `#DCE4EE` borders, soft `rgba(17, 22, 37, 0.035)` elevation), eliminating dark navy backgrounds and high-contrast color clashes.
  - Replaced legacy dark phase badges (`color: #c4b5fd`, dark purple background) with crisp high-contrast cobalt blue accents (`background: rgba(0, 82, 255, 0.08)`, `color: #0052FF`, `border: 1px solid rgba(0, 82, 255, 0.22)`).
  - Modernized the Macrocycle Periodization timeline track with clean `#E2E8F0` tracks and a cohesive Speed & Summit gradient fill (`linear-gradient(90deg, #0052FF 0%, #00C896 60%, #FF5E00 100%)`).
  - Restyled program stat boxes (`.program-stat-box`) with clean white backgrounds (`#FFFFFF`) and dedicated `.program-stat-box-target` styling for the Target FTP metric (subtle `#FF5E00` accent border, soft orange wash, and bright Speed Orange wattage value).
  - Updated timeline phase column states and info typography for optimal contrast and readability across light theme modes.

---

## [2.6.1] - 2026-11-11
### Added
- **Cross-Training Physiological Load Analysis**:
  - Implemented `is_cycling_sport` helper classifying activities into cycling vs. cross-training disciplines (running, swimming, weight training, rowing, hiking, etc.).
  - Added dedicated cross-training strain evaluation in `calculate_activity_strain`: converts cardiovascular load (Strava Relative Effort / Suffer Score, heart rate intensity, duration) into aerobic training strain (Low XSS and Total XSS) and systemic fatigue.
  - Sparing Cycling $W'$: Cross-training activities accurately accumulate training load and fatigue without depleting cycling-specific pedal $W'$ balance or triggering false sprint/glycolytic depletion warnings.

### Fixed
- **Cycling Power Telemetry Isolation & PR Breakthrough Protection**:
  - Strictly blocked non-cycling power telemetry (e.g. Stryd/Garmin running watts, gym power meter outputs) from cycling fitness assessment and analytics.
  - Refined `calculate_activity_peak_powers()` to immediately return 0W across all durations for non-cycling activities.
  - Filtered `get_power_spiderweb_profile()` so that the 5-axis power radar envelope, monthly timeline power bars, and Coggan phenotype classification are calculated strictly from cycling activities.
  - Guaranteed that PR Breakthroughs in the Breakthroughs feed (`recent_breakthroughs`) only scan authentic cycling rides, preventing non-cycling workouts (like runs or gym sessions) from logging cycling power PRs.
  - Updated Sports Science Debrief (`build_daily_review_and_outlook_local`) so cross-training days provide holistic conditioning debriefs without comparing running or gym watts against cycling FTP.

---

## [2.6.0] - 2026-11-11
### Added
- **Unified Multi-Axis Coggan Phenotype Profiling Engine**:
  - Replaced the order-dependent `if/elif` waterfall with a scientific, multi-axis power profile classification model (`classify_athlete_phenotype`).
  - Evaluates relative energy system strengths across all 5 durations (5s sprint, 1m glycolytic, 5m VO2 Max, 20m threshold, 60m stamina) against Coggan power profiling principles, preventing premature cascade trapping (e.g. labeling an athlete as Puncheur when their true physiological strength is Pursuiter or All-Rounder).
  - Evaluates standard deviation and spread across normalized energy systems to identify true All-Rounder equilibrium vs. specialist dominance.
  - Returns continuous phenotype affinity scores and readiness percentages (0–100%) for all archetypes.

### Changed
- **Transformation Target Overload & 0W Gap Elimination**:
  - Eliminated the defect where transformation goals into existing capabilities generated a 0W gap and marked goals as 100% achieved immediately.
  - Implemented progressive adaptation overload (+5% stimulus on archetype signature axes when current fitness is already at or near baseline) so transformation goals always provide real, actionable training stimuli.
  - Updated transformation cards in the UI (`renderPlannerPhenotypeView`) to display `🎯 Current Classification (X% Match)` for the active archetype and clear progressive readiness for transformation goals.

### Fixed
- **Physiological Duration Gating & Activity Peak Power Accuracy**:
  - Refined `calculate_activity_peak_powers()` to enforce strict minimum moving times (e.g. 20m and 60m require genuine ride durations of at least 15m and 50m respectively), preventing artificial peak power generation on short rides.
  - Integrated power meter `device_watts`, `max_watts` adherence, and interval lap / segment peak extraction from activity telemetry.
  - Replaced uncalibrated all-out sprint assumptions with intensity-modulated Morton CP / $W'$ contribution.

---

## [2.5.7] - 2026-11-11
### Removed
- **Directeur Sportif Static In-Ride Pacing Bottom Sheet**:
  - Removed the simulated in-ride pacing bottom sheet (`#dsCoachingBottomSheet`, *"DIRECTEUR SPORTIVE • LIVE PACING INSIGHT"*) from the indoor workout stage. Since in-ride telemetry is not live during pre-ride planning and prescription, the static alert ("burning matches early...") was non-functional and confusing.
  - Cleaned up bottom sheet DOM elements, event listeners in `app/static/js/app.js`, and associated CSS rules from `app/static/css/style.css`.

---

## [2.5.6] - 2026-11-11
### Fixed
- **Debrief Workout Timeline Accuracy & Past Session Attribution**:
  - Corrected temporal attribution in the Sports-Science Assessment debrief so older workouts (e.g. from several days ago or last week) are never falsely described as "yesterday" or linked as immediate day-after causes of today's Whoop recovery score.
  - Enforced strict timeline directives in `call_gemini_coach_review` (`app/services/review_coach.py`), explicitly separating today's baseline recovery from past session dates (e.g. Wednesday, Nov 4 / 6 Days Ago) and forbidding "yesterday" hallucination when reviewing older sessions.
  - Implemented automated timeline post-processing to replace any hallucinated "yesterday" phrases in coach debriefs with accurate date and relative day labels.
  - Enhanced debrief activity metadata and subtitles in `app/static/js/app.js` to format friendly date displays (e.g. "Wednesday, Nov 4 (6 Days Ago)") for single and multi-session historical reviews.

---

## [2.5.5] - 2026-11-11
### Changed
- **Renamed "AI Race Briefing" to "Ride Briefing"**:
  - Updated the top telemetry directive card title (`#coachCardTitle`), tooltip and accessible labels from "AI Race Briefing" to "Ride Briefing" across the dashboard.
  - Updated pre-ride briefing banner headers in both the Indoor Structured Workout view and Outdoor Route Match preview from "AI Race Briefing" to "Ride Briefing".

---

## [2.5.4] - 2026-11-11
### Fixed
- **Telemetry Card Header Layout & Overlap Prevention**:
  - Enforced `flex-wrap: nowrap` on `.card-header-left` so card icons and titles are never severed across different lines.
  - Implemented resilient `.telemetry-grid .card-title` font sizing (`0.92rem !important`) and min-width boundaries on the title box, preventing titles like "Strava Training Load (7 Days)" from being crushed down into narrow vertical stacks.
  - Styled `.card-header-actions` to wrap cleanly to line 2 on narrow containers without overlapping or invading the title boundaries.
  - Added text-overflow protection and ellipsis clipping (`max-width: 170px`) with full-title hover tooltips for long status badges such as `Supercompensated / Fresh`.
- **AI Race Briefing Narrative Overflow & Footer Collision Fix**:
  - Replaced unconstrained `max-height: 85px` on `.telemetry-grid #coachCardNarrative` with `overflow-y: auto`, `box-sizing: border-box`, and a discrete 4px custom scrollbar. Long coach directives (such as detailed forward forecast confirmations) scroll smoothly inside the white narrative bubble without overflowing onto footer jump links or buttons.
  - Standardized `.coach-card-footer` and `#coachCardFooterSubtext` with flexible text truncation and ellipsis handling to prevent coach badges from colliding with action links.

---

## [2.5.3] - 2026-11-11
### Changed
- **Default Opening Tab Set to "Daily Training" View**:
  - Updated `initMainViewSwitcher()` in `app/static/js/app.js` so the dashboard always opens on the **Daily Training (`daily`)** tab by default on page load or refresh, rather than restoring a previously cached `analysis` tab from `localStorage` or `#analysis` URL hash.

---

## [2.5.2] - 2026-11-11
### Changed
- **Restored "PowerSync" Application Name**:
  - Changed the application brand name back to **PowerSync** across the top navigation bar, page title, PWA metadata, Coach Chat drawer, modals, version footer, and local launcher files (`PowerSync.html` and `AeroSync.html`), while retaining the "Speed & Summit" UI design system and typography.

---

## [2.5.1] - 2026-11-10
### Fixed & Improved
- **iPhone & Mobile Viewport Formatting & Responsive Layout**:
  - Fixed a duplicated CSS rule and stray closing brace inside `@media (max-width: 768px)` in `app/static/css/style.css` that prematurely closed the mobile media query and caused 3-column desktop grid rules to leak onto narrow iPhone screens.
  - Compacted the top `.navbar` on iPhone screens (`<= 600px`) into a sleek 2-row header: `.brand` and compact icon/badge `.nav-actions` on Row 1, and the full-width `Daily Training` / `Long-Term Analysis` view switcher on Row 2.
  - Configured `.telemetry-grid` (Whoop Recovery, Strava Load, AI Race Briefing) to stack cleanly as full-width cards on iPhone viewports (`<= 600px`), and updated 3-tab `.mode-tabs` (`#debriefTabGroup` and `#planSourceTabs`) to render in a balanced 3-column grid instead of wrapping an orphaned 3rd tab onto a second row.
  - Embedded the **Dynamic Coaching Bottom Sheet (`#dsCoachingBottomSheet`)** directly inside the Live Workout Interface beneath the power zone canvas so it never collides with the floating Coach Chat FAB on mobile screens, complete with animated 4-bar Cobalt-to-Orange wave indicators.
- **Mobile Coach Chat & 3-Tier Strain Light-Theme Contrast**:
  - Replaced hardcoded dark-mode `!important` mobile backgrounds in `.coach-chat-header`, `.coach-chat-input-bar`, `.pull-to-reload-content`, and `.chat-workout-action-card` with Ice Frost (`#F4F7FA`) and Pure White (`#FFFFFF`) surfaces and Midnight Carbon (`#111625`) text, and styled user chat bubbles in Electric Cobalt Blue (`#0052FF`) with crisp white text.
  - Updated 3-Tier Strain (`.strain-total-badge`, `.strain-tier-val`) and $W'$ Anaerobic Battery labels (`.battery-meter-label`) from white (`#fff`) to Midnight Carbon (`#111625`) and Electric Cobalt Blue (`#0052FF`) for full legibility on light card backgrounds.

---

## [2.5.0] - 2026-11-10
### Changed & Added
- **VeloMetrics AI Brand Identity & Value Proposition**:
  - Rebranded the application UI to **VeloMetrics AI** with the brand essence *"Data-driven training meets human passion. Your personalized AI coach for every pedal stroke."*
- **"Speed & Summit" High-Contrast Color Palette**:
  - Transitioned the dashboard to a crisp, high-tech light-first palette: **Pure White (`#FFFFFF`)** primary background, **Ice Frost (`#F4F7FA`)** card and activity containers, **Electric Cobalt Blue (`#0052FF`)** primary brand/navigation and active metrics, **Sunset Orange (`#FF5E00`)** high-energy calls-to-action and peak power alerts, **Midnight Carbon (`#111625`)** headers and key metrics, **Slate Gray (`#64748B`)** secondary labels/units, and **Mint Teal (`#00C896`)** recovery and goal completion indicators.
- **Geometric Typography & Custom Cycling Iconography**:
  - Paired **Outfit** (`Bold`/`Black` weights) for headlines and big wattage/telemetry readouts with **Inter** (`Regular`/`Medium` weights) for high-legibility body copy and dense post-ride analytics.
  - Added custom SVG iconography combining crisp, rounded line icons for navigation with solid Sunset Orange (`#FF5E00`) lightning bolt accents, cadence dials, wattage meters, elevation profiles, and an AI wave pulse icon.
- **Directeur Sportif (DS) AI UI Elements & Live Workout Interface**:
  - Added pulsing dual-tone gradient rings (`#0052FF` fading into `#FF5E00`) around live coaching insights and AI avatars.
  - Styled pre-ride AI **"Race Briefing" Cards** on an Ice Frost (`#F4F7FA`) surface with a subtle Electric Cobalt Blue (`#0052FF`) border and Sunset Orange (`#FF5E00`) highlights on Target FTP and interval wattage targets.
  - Updated live workout interval bars to transition smoothly from cool blue (Recovery/Endurance) to Sunset Orange (Sweet Spot/Threshold/VO2 Max) and added a sleek Dynamic Coaching Bottom Sheet (`"AI Coach: You're burning matches early. Ease back 15 watts on this climb to save legs for the final interval."`).

---

## [2.4.5] - 2026-11-10
### Fixed & Security Hardening
- **Settings Route Authentication Enforcement (`/api/settings`)**:
  - Placed `/api/settings` and all `/api/settings/coaching-preferences*` endpoints behind mandatory session authentication (`require_authenticated_user`), returning `HTTP 401 Unauthorized` (`WWW-Authenticate: Bearer`) to unauthenticated requests.
  - Eliminated exposure of masked API key substrings (`gemini_api_key_masked`, `google_maps_api_key_masked`, `intervals_icu_api_key_masked`) and raw OAuth client IDs (`strava_client_id`, `whoop_client_id`, `google_client_id`) from `/api/settings` and `/api/auth/google/status` responses, returning only boolean configuration flags.
  - Prevented `get_all_settings()` from populating global environment fallback secrets (`GLOBAL_ENV_KEYS`) when queried under unauthenticated guest contexts (`usr_guest`).
- **Diagnostic & Key Management Endpoint Hardening**:
  - Restricted `/api/auth/debug-headers`, `/api/auth/lock-owner`, `/api/auth/disconnect/{service}`, `/api/chat/save-key`, and `/api/chat/test-connection` to authenticated sessions and removed internal environment/mount diagnostics from `/api/auth/debug-headers`.
  - Redacted `owner_email` from `/api/auth/owner-status` for unauthenticated visitors.
  - Updated frontend settings modal and startup flow to prompt sign-in before requesting `/api/settings`.

---

## [2.4.4] - 2026-11-09
### Changed
- **Header Branding & Subtitle**:
  - Updated the navbar branding subtitle from "Adaptive Coach & Zwift Sync" to "AI Cycling Coach".

---

## [2.4.3] - 2026-11-01
### Hardened & Fixed
- **Backend Code Audit & Null Safety Remediation**:
  - Resolved `UnboundLocalError` in `apply_chat_action_endpoint` across `schedule_workout`, `schedule_upcoming_plan`, and `clear_upcoming_plan`, enabling seamless execution of all coach proposal cards in Coach Chat.
  - Hardened database and calculation services against nullable fields (`moving_time_sec`, `distance_meters`, `suffer_score`, `recovery_score`), preventing 500 crashes and `TypeError` exceptions during workout generation and sync.
  - Replaced UTC `datetime.date.today()` with timezone-aware `get_athlete_date(user_id)` in target plans and scheduled workout checks to prevent premature date rollover for athletes in US timezones.
- **Strict Multi-User Isolation in Coach Tools**:
  - Removed unauthorized fallbacks to `usr_default` across Strava activity details, high-res stream proxies, and Whoop biometric timelines, ensuring complete data privacy across authenticated athlete accounts.
  - Handled nullable arguments in `execute_coach_tool` dispatcher (`days_back`, `limit`, `days`) to guard against `None` inputs from LLM tool calls.
- **Gemini Multi-Turn API Alternation Compliance**:
  - Bundled parallel function response parts into a single user turn (`{"role": "user", "parts": fn_resp_parts}`), strictly abiding by Gemini API multi-turn alternation constraints and eliminating HTTP 400 Bad Request interruptions.
- **Frontend & UI/UX Polish**:
  - Added `requestAnimationFrame` redraw triggers for SVG spiderweb rendering, HTML5 workout graph canvas, and Leaflet outdoor map on tab switches, preventing collapsed 320px canvases.
  - Implemented `.expand()` and `.collapse()` methods on collapsible card controllers for smooth cross-pane anchor navigation.
  - Enhanced accessibility with 44x44px minimum touch targets on all modal close buttons and refined contrast for form inputs and labels in light mode.

---

## [2.4.2] - 2026-11-01
### Added & Fixed
- **Segmented Main Dashboard View Switcher**:
  - Prominent high-contrast toggle at top of the dashboard separating **Daily Training & Execution** (Whoop readiness, Strava training load, AI Coach directive, Today's Workout stage with Zwift sync & fueling, 3-Day Forward Forecast, Daily Debrief, and Recent Workouts feed) from **Long-Term Performance & Strategy** (Power Spiderweb & Fitness Profile, Macrocycle Fitness Goal & Periodization, and Athlete Power Profile & Coggan Zones).
  - Preserves view selection in `localStorage` (`powersync_main_view`) and URL hash (`#daily` vs `#analysis`).
  - Cross-tab jump links automatically switch view panes with smooth fade-in transitions.
  - Dynamically scopes the master "Expand All / Collapse All" button to expand and collapse only visible cards within the active view pane.
- **Authoritative Evening Workout Timezone Resolution**:
  - Overrides inaccurate Strava/Watopia UTC timestamps by directly converting UTC `start_date` into the athlete's configured local timezone (`America/New_York`) for all virtual/indoor rides (Zwift, TrainerRoad, etc.).
  - Workouts completed in local evening hours (9-10 PM) permanently remain on the evening date they occurred (e.g. October 27th), preventing them from rolling over into the next day (October 28th).
  - Recent Workouts feed correctly displays the true local calendar date.
- **Daily Training Slate & Debrief Harmony**:
  - The Coach Sports-Science assessment accurately debriefs yesterday's evening session against yesterday's scheduled caps (e.g. Tuesday 45m cap).
  - Today's prescribed workout stays fresh and unblocked, preventing false "Daily Target Achieved — Rest & Recovery" blocks on high-recovery mornings.

---

## [2.4.1] - 2026-11-01
### Added
- **Spiderweb Category Target Improvement Explorer**:
  - Displays what target wattage and W/kg changes are needed across each duration category (5s Sprint, 1m Anaerobic, 5m VO2 Max, 20m Threshold, 60m Stamina) across three progressive milestone tiers: Progressive (+5%), Transformative Leap (+10%), and Benchmark Ceiling (Elite).
  - Outlines physiological energy system stimulus, adaptations, and prescribed interval workouts for each category.
- **Rider Type Transformation Analysis**:
  - Detailed 5-axis gap analysis showing exact target envelope requirements to transform the athlete's phenotype into Puncheur, Rouleur, Climber, Sprinter, Pursuiter, or All-Rounder.
  - Highlights met vs pending wattage gaps with readiness completion percentages.
- **Active Spiderweb Training Goal Setting & 3rd Radar Polygon**:
  - One-click goal setting from any duration tier or rider type archetype, saved per athlete in database.
  - Renders a 3rd distinct glowing emerald dashed polygon (`#10b981`) on the Power Spiderweb radar chart with diamond vertex markers and legend indicators.
  - Live progress tracking banner displaying percentage of wattage gap closed and remaining watts to target.
- **AI Coach Integration & Gemini Tool Calling**:
  - Daily adaptive workout recommendations and sports-science debriefs incorporate the active spiderweb goal, prioritizing the appropriate energy system on green recovery days.
  - Added Gemini function calling tools `get_active_spiderweb_goal` and `set_spiderweb_goal` so athletes can inspect or set spiderweb goals dynamically in Coach Chat.

---

## [2.4.0] - 2026-11-01
### Added
- **Interactive Power Spiderweb Radar & Progress Over Time (Strava & Xert Signature Model)**:
  - **5-Axis Physiological Power Spiderweb**: Pure vanilla SVG radar chart mapping athlete power across 5 core energy system durations: 5s Sprint (Neuromuscular), 1m Anaerobic (Glycolytic), 5m VO2 Max (Maximal Aerobic Power ceiling), 20m Threshold (Lactate Equilibrium / Critical Power), and 60m Stamina (Aerobic Endurance).
  - **Dual-Period Overlay Comparison**: Directly overlays current training period (glowing cyan polygon) against baseline periods (translucent dashed violet polygon) with dynamic percentage normalization against benchmark physiology ceilings.
  - **Interactive Multi-Window Timeframe Selectors**: One-click switching between `30D vs Prior 30D`, `60D vs Prior 60D`, `90D vs Season`, and `All-Time PRs`.
  - **Rider Phenotype Classification**: Classifies athlete rider archetype (`Sprinter`, `Puncheur`, `Pursuiter`, `Rouleur`, `Climber`, `All-Rounder`), identifying primary physiological strengths and targeted growth opportunities.
  - **Duration Metrics Grid & Delta Chips**: Responsive metric cards displaying current Watts, Watts/kg, benchmark progress bar, prior period comparisons, and delta chips (`+W`, `+%`).
  - **Historical Power Progression Grid & PR Breakthroughs Feed**: Chronological monthly peak power envelope progression tracking training volume (TSS & hours) alongside an automated milestone breakthrough tracker highlighting new power PR records.
  - **Full Dashboard Integration**: Registered in collapsible tile manager with localStorage state memory and bundled into `/api/dashboard` for instant render.

---

## [2.3.3] - 2026-10-30
### Added & Fixed
- **Updated Schedule Target Fidelity in Coach Analysis**: Enhanced `review_coach.py` with `resolve_day_prescribed_target()` to evaluate completed workouts against the specific prescribed session and updated schedule (e.g. Zone 2 Aerobic Base, Active Recovery Flush, or scheduled workouts) rather than blindly assuming Sweet Spot / VO2 Max (90% FTP) whenever Whoop recovery is in the green. Pacing compliance, target zone, and target watts now accurately reflect the updated schedule, awarding `Execution Bullseye` (🎯 Target Mastered) for adhering to prescribed lower-effort work.
- **Gemini Debrief Guidance Guardrail**: Instructed Gemini LLM debrief generation to honor prescribed lower-effort rides and evaluate fidelity against that target rather than falsely diagnosing "Conservative Pacing" or headroom.
- **Automatic Strava Feed Syncing & Expanded History**: Integrated continuous background auto-sync for Strava into `loadDashboard()` and `loadDebrief()` (matching Whoop's 60s auto-refresh cadence) and on window focus/tab return. Expanded the Recent Workouts table from 5 to 15 activities and ensured real-time DOM re-rendering so freshly completed Strava workouts populate the bottom table automatically.
- **Dual-Write Guest / Default Strava Sync Isolation**: Enhanced `fetch_recent_strava_activities` and `/api/auth/sync/strava` with guest account fallback and dual-user synchronization so both sessions stay fully populated.

---

## [2.3.2] - 2026-10-30
### Added & Fixed
- **Multi-Day Weekend Chat Directives & Multi-Clause Intent Parsing**: Enhanced Coach Chat and forecast service to parse multi-day weekend directives simultaneously (e.g. "50 miles tomorrow and resting sunday"). Robust regex boundary parsing separates athlete intent from complaint clauses ("but it still has..."), staging distinct plans for both Saturday and Sunday in a single message.
- **3-Day Forecast UI Reactive Refresh & Badges**: Prioritized `💬 Coach Scheduled` badges over generic athlete notes in the 3-day forecast outlook. Automatically reloads the forecast in the DOM immediately upon chat plan confirmation and drawer close without requiring manual browser reloads.
- **T-1 Race Taper Leadup Protection**: Isolated pre-race leadup tapers so casual upcoming weekend rides or group rides do not hijack or truncate today's prescribed Friday session into a 30-minute neuromuscular primer.
- **Universal Daytime Strain Corroboration**: Unified `has_substantial_ride` across all workout endpoints (`workouts.py`, `outdoor_coach.py`, `ai_coach.py`), guaranteeing that fresh morning 0.0 strain baselines (such as 95% Whoop recovery) are never erroneously locked out into "Daily Target Achieved — Rest & Recovery" by evening workouts or uncorroborated activity records.

---

## [2.3.1] - 2026-10-29
### Added & Fixed
- **Coach Chat 3-Day Forecast Dynamic Adjustment**: Discussing upcoming rides or schedule changes in Coach Chat (e.g. 50-mile Saturday ride, tomorrow threshold over-unders, or Friday rest day) automatically adapts the 3-day forward forecast outlook cards and interval breakdowns with '💬 Coach Scheduled' badges and fatigue decay modeling.
- **Upcoming Plan Persistence**: Staged and confirmed Coach Chat plans are permanently stored in `coach_upcoming_plans` and seamlessly override future forecast day archetypes while preserving athlete weekly preferences.
- **Strava True start_date_local Prioritization**: Enhanced `resolve_strava_local_start` to prioritize Strava's true `start_date_local` and `utc_offset` over generic UTC server conversions, ensuring evening rides (9-10 PM) stay permanently anchored to the evening date they occurred.
- **Morning Training Slate Physiological Guardrail**: Prevented workouts from falsely blocking morning training when Whoop daytime strain is 0.0 with green recovery, ensuring 95% recovery slates receive their proper prescribed session.
- **Auto-Timezone Calibration**: Automatically extracts athlete timezone from synced Strava activities if unconfigured.

---

## [2.3.0] - 2026-10-29
### Added & Fixed
- **Google Gemini Function Calling & Live Tool Engine**: Enabled native tool calling (`tools=[...]`) inside the PowerSync Coach Chat. Google Gemini models dynamically invoke backend tools to inspect live Strava and Whoop metrics with zero guesswork.
- **Granular Strava Lap & Split Telemetry**: Added `get_strava_activity_details` tool to inspect workout interval laps, average/normalized watts, cadence, and 3-tier XSS strain (Low, High, Peak) for any ride (`latest`, `yesterday`, or numeric ID).
- **Peak Power Curve & Aerobic Decoupling**: Added `get_strava_activity_streams_and_power_curve` tool calculating sliding window peak wattage (5s, 15s, 1m, 5m, 20m) and heart rate aerobic decoupling (cardiac drift) from second-by-second activity streams.
- **Historical Workout Search**: Added `search_strava_activities` tool allowing natural query matching (e.g. "my sweet spot rides", "climbing workouts") across the athlete's Strava database.
- **Multi-Day Whoop Recovery Correlation**: Added `get_whoop_biometrics_timeline` tool retrieving multi-day Whoop recovery, HRV, resting heart rate, sleep performance, and strain trends.
- **Interactive UI Tool Execution Badges**: Rendered animated tool badges in the Coach Chat window showing the athlete the exact tool invoked and telemetry analyzed.

---

## [2.2.10] - 2026-10-28
### Added & Fixed
- **Zero-Dependency Database Migration**: Resolved circular import between `database.py` and `strava_service.py` during app startup, guaranteeing that SQLite migrations execute on startup and convert all historical UTC Strava activity timestamps to local time.
- **Strava Re-sync Local Start Update**: Fixed `ON CONFLICT` clause in `fetch_recent_strava_activities` to update `start_date`, ensuring re-syncing Strava records always syncs and preserves local timestamps.
- **VirtualRide Timezone Normalization**: Enhanced timestamp resolution to reliably convert Strava UTC start times for Zwift virtual rides into the athlete's local time zone (`America/New_York`), preventing evening rides from rolling over to the next morning.
- **Clean Daily Training Slate Guarantee**: Ensured yesterday evening workouts are excluded from today's completed activities, unlocking fresh prescriptions for 95% Whoop recovery.

---

## [2.2.9] - 2026-10-28
### Added & Fixed
- **Evening Workout Timezone Alignment**: Strava activities recorded during evening hours (e.g. 9:00 PM – 10:00 PM) are now mapped directly to the athlete's local calendar date using `start_date_local` and timezone conversion, preventing UTC timestamps from rolling evening workouts into the following morning.
- **Clean Daily Training Slate**: Resolved bug where yesterday evening's workout led the AI Coach to assume today's training was already completed, incorrectly locking "Today's Training" into "Daily Target Achieved — Rest & Recovery".
- **Eliminated Rolling 20-Hour Window**: Removed the legacy 20-hour window heuristic in the workout generator that conflated prior night rides with today's training session, ensuring workout prescriptions strictly reflect the current calendar day and morning Whoop recovery.
- **Automated Database Local Timestamp Migration**: Automatically updates all existing Strava activity records in SQLite to the athlete's local ISO start times upon startup.

---

## [2.2.8] - 2026-10-25
### Added & Fixed
- **Whoop Auto-Sync on Dashboard Load**: Automatically syncs and updates the athlete's latest Whoop recovery, sleep, and strain metrics in the background upon opening the dashboard and at 15-minute intervals. Eliminates the need for manual button clicks.
- **Permanent Biometric Storage & Persistence**: Biometrics from Whoop (Recovery %, Sleep Performance %, HRV, RHR, Day Strain) are stored in SQLite and retained across browser exits, tab closes, device restarts, and mobile PWA sessions until overwritten by the next sync.
- **Accurate Physiological Date & Timezone Resolution**: Correctly aligns Whoop recovery and sleep records to the athlete's local calendar day using their configured timezone and wake-up timestamps, resolving false "Yesterday" badges and perpetual re-sync prompts.
- **Single-Owner Session Persistence**: Personal deployments automatically establish persistent 30-day authenticated sessions and provide seamless biometric fallbacks for unauthenticated visits, preventing the app from reverting to guest demo mode or dropping connected integrations.
- **OAuth Session Continuity**: Whoop and Strava OAuth callbacks now issue persistent 30-day session cookies and tokens, ensuring browser redirects immediately transition into authenticated sessions.

---

## [2.2.7] - 2026-10-23
### Added
- **Collective Multi-Workout Daily Assessment**: When an athlete logs multiple rides in a single calendar day (e.g. main Sweet Spot session followed by a post-ride cooldown spin, or morning commute + evening intervals), the AI Coach assessment automatically groups and evaluates all sessions collectively rather than evaluating only the most recent cooldown spin.
- **Coggan 4th-Power Normalized Power Aggregation**: Implemented 4th-power weighting ($\left(\sum NP_i^4 t_i / \sum t_i\right)^{1/4}$) across multi-session training days to preserve the physiological intensity of the primary workout rather than dragging average power down to cooldown recovery levels.
- **Additive Training Load Summation**: Sums power-based TSS, suffer score, distance, elevation gain, and 3-tier XSS (Low, High, Peak strain) across all daily sessions for true aggregate systemic strain and accurate forward fatigue decay modeling.
- **Primary Effort Target Compliance**: Identifies primary vs secondary/cooldown sessions so compliance scoring and verdicts evaluate fidelity against the prescribed workout target zone, ensuring athletes are rewarded with high execution scores (e.g. "Execution Bullseye") rather than penalized for spinning easy to clear lactate.
- **Session Breakdown UI Badges**: Added responsive session pills directly beneath the Daily Debrief heading displaying individual workout duration, watts, and TSS for each session completed.
- **Collective LLM Coach Prompting**: Updated Google Gemini 2.5 Flash coach prompt with detailed session-by-session telemetry and strict directives to assess the day's training collectively, explicitly recognizing active recovery flushes.

---

## [2.2.6] - 2026-10-21
### Added
- **Clickable 3-Day Forecast Workout Previews**: Clicking on any forecast day card in the 3-day forward training forecast launches a high-fidelity Workout Preview Modal displaying the full session preview, projected readiness score, duration, and target strain metrics.
- **Dynamic Interval Canvas Profile**: Embeds an interactive, high-DPI interval profile canvas within the modal, color-coding progressive ramp warmups, work intervals, recovery valleys, and cooldown ramps according to physiological power zones, with 100% FTP threshold line reference and exact target watts.
- **Structured Step-by-Step Interval Breakdown**: Displays every step of the workout with interval name, duration (minutes and seconds), power target (% FTP and calculated Watts based on athlete FTP), and recommended cadence (RPM).
- **Target Date Zwift Sync & Coach Chat Integration**: Added a 1-click `🚀 Push to Zwift for This Day` button to stage upcoming rides directly to Zwift/Intervals.icu ahead of time, plus a `💬 Edit in Coach Chat` shortcut with pre-populated prompt.

---

## [2.2.5] - 2026-10-21
### Fixed
- **Mobile Settings Modal Form Grid & Date Input Alignment**: Fixed an issue on mobile devices (e.g. iPhone Safari / PWA) where the Target Event Date input and adjacent fields in the Settings modal blew out past the right boundary of the cyan card container onto the modal backdrop.
- **Responsive Layout Stacking**: Introduced `.settings-form-grid` which cleanly stacks fields to 1 column on screens $\le 768\text{px}$ and protects grid cells with `min-width: 0`, preventing WebKit intrinsic content sizing from expanding tracks past card boundaries.
- **iOS Safari Native Date Picker Polish**: Added `appearance: none`, `color-scheme: dark`, and left-aligned text styling (`::-webkit-date-and-time-value`) for seamless native input presentation.

---

## [2.2.4] - 2026-10-21
### Fixed
- **Zwift ERG Target Wattage Precision Calibration**: Fixed an issue where interval target wattages on Zwift appeared 1-2 watts lower than in the PowerSync dashboard. Zwift's C++ ERG game engine integer-truncates floating-point power ratios (e.g. `(int)(275 * 0.89) = 244W` instead of `245W`, and `round(91.5%, 2) = 0.91 -> 250W` instead of `252W`). Calibrated `.zwo` export using target-watt centering (`_calculate_zwo_power`), guaranteeing 100% exact integer watt matching between PowerSync and Zwift ERG mode across all athlete FTPs.
- **User-Scoped Intervals.icu Sync**: Added explicit `user_id` scoping in `push_to_zwift_via_intervals` to ensure the active athlete's exact FTP and API credentials are used for calendar synchronization.

---

## [2.2.3] - 2026-10-21
### Changed
- **Direct GPX Route Uploader**: Converted the workout controls bar below the profile canvas into a dedicated, clean Route Uploader (`🗺️ Upload Route (.gpx)`). Uploading a `.gpx` file immediately parses distance and elevation and applies the route pacing plan directly to the workout stage without requiring a manual regeneration click.
- **Removed Legacy 'Adapt / Plan Ride' Text Input**: Removed the legacy text box and button that triggered coarse keyword pattern matching instead of nuanced interval editing.
- **Conversational Coach Chat Alignment**: Unified all natural language interval modifications (e.g. extending surges, custom step durations, rest valley adjustments) into the Gemini AI Coach Chat (`💬 Edit in Coach Chat`), which accurately contextualizes existing intervals and provides 1-click workout updates.

---

## [2.2.2] - 2026-10-21
### Fixed
- **Automated Morning Whoop Refresh & Continuous Biometric Heartbeat**: Fixed an issue where morning Whoop recovery scores stopped auto-refreshing when opening the app. Added 15-minute recency sync tracking (`last_whoop_sync_timestamp`), unfinalized recovery auto-sync (re-syncs if morning sleep/recovery is missing or zero), and integrated automatic sync across Dashboard, Workout generation, and client boot.
- **Explicit Multi-User Whoop Token Isolation**: Fixed missing user ID scoping in `dashboard.py` and `workouts.py` to ensure connected Whoop tokens consistently resolve for the active athlete.

---

## [2.2.1] - 2026-10-20
### Fixed
- **Athlete Timezone Continuity & Evening UTC Offset Normalization**: Fixed an issue where cloud servers executing in UTC (00:00+ UTC, or after 8:00 PM EDT) flipped calendar days prematurely, causing today's sessions to be evaluated as "Yesterday" and projecting the 3-day forecast starting from Day +2 (e.g. Oct 22 instead of Oct 21).
- **Client Timezone Auto-Discovery & Context Binding**: Added automatic browser client timezone discovery via an `X-Timezone` HTTP header interceptor (`Intl.DateTimeFormat().resolvedOptions().timeZone`), bound to request lifecycle contextvars and stored in athlete settings.
- **Unified Local Timezone Utility**: Replaced all naive `datetime.date.today()` calls across all routers, services, and strain analyzers with timezone-aware `get_athlete_date()` and `get_athlete_now()`. Set `ENV TZ=America/New_York` in container definition.

---

## [2.2.0] - 2026-10-20
### Added
- **3-Day Forecast & Daily Workout Integration**: Forward 3-day forecast plans are persisted in database storage (`coach_forecast_plan`). When morning recovery matches projected assumptions, the daily workout selector confirms and prescribes the exact promised session (`⭐ Coach's Choice • Forecast Confirmed`). If recovery drops into the red, the coach adaptively explains the physiological pivot.
- **Dynamic Workout Catalog & Anti-Repetition Engine**: Replaced static sweet spot over-unders with an extensive catalog of diverse archetypes across Sweet Spot, Threshold, VO2 Max, Tempo, and Endurance Base (Sustained Blocks, Criss-Cross Surges, Pyramid Power Density, Microbursts, Over-Unders). Anti-repetition history tracking prevents identical workouts on consecutive sessions (e.g. Wednesday vs. Friday).
- **Auto-Syncing Strava & Completed Workout Protection**: Added automatic live syncing for Strava activities on dashboard and workout load. Completed daily rides now transition Today's Training into `✅ Daily Target Achieved — Rest & Recovery` and prevent scheduled workouts from overwriting completed sessions.
- **3-Tier Physiological Strain Engine (XSS & W'bal)**: Integrated Morton/Skiba Critical Power and $W'$ anaerobic battery depletion modeling, partitioning mechanical and autonomic stress into Low (Aerobic), High (Glycolytic), and Peak (Sprint) strain tiers.

### Changed
- **Mobile Layout & iPhone PWA Polish**: Redesigned the 3-Tier Strain card header to eliminate multi-line text squishing on mobile screens, cleaned up battery meter typography, and added bottom safe-area scroll clearance to prevent floating coach action buttons from obstructing debrief content.
- **True Power-Based TSS & HR Telemetry**: Fixed cardiovascular load calculation to derive true power-based Training Stress Score ($TSS = \frac{t \times NP \times IF}{FTP \times 3600} \times 100$) and populate actual average/max heart rate from Strava streams.

---

## [2.1.0] - 2026-10-16
### Added
- **Full Multi-User Database Isolation**: Scoped all settings, biometric histories, Strava activities, training plans, and forecast caches by user session ID with automatic data migration and dev-account switching.
- **Natural Language Workout Customization**: Direct chat instructions dynamically adapt workouts, recalculate TSS/XSS, and generate exportable .zwo / Intervals.icu workouts.

### Changed
- **Unified 5-Level Typography & Card Accents**: Coherent typographic hierarchy and gradient accent bars across all tiles.

---

## [2.0.0] - 2026-10-15
### Added
- **24/7 Cloud Deployment on Railway**: Docker containerized backend accessible 24/7 at powersync.up.railway.app with automated health checks.
- **Persistent Volume Storage**: SQLite fitness database backed by persistent Railway volume (`/app/data/fitness.db`), preserving biometric trends, Strava activities, and tokens across redeployments.
- **Streamlined 1-Click Connect Cards**: Replaced developer credential input fields with clean 1-click Connect & Disconnect cards for Strava and Whoop.
- **Secure Cloud Environment Secrets**: Gemini API key, Strava/Whoop client credentials, and biometrics seamlessly loaded from Railway environment variables with alias normalization.
- **Permanent High-Contrast Dark Theme**: Locked-in high-contrast carbon aesthetic optimized for indoor pain caves, OLED displays, and low-light training rooms.
- **Persistent Weekly Schedule Engine**: Custom day-by-day duration rules, progressive wattage ramp warmup/cooldown invariants, and Saturday dedicated rest directives.
- **Dynamic OAuth Domain Resolution**: Intelligent multi-environment redirect host resolution matching active browser domains.

---

## [1.5.1] - 2026-10-12
### Added
- **Clickable Interval Profile**: Click any section, ramp, or steady bar on the workout canvas to inspect its exact power targets (Watts & % FTP), duration, timeline, and zone.
- **Spotlight Highlighting**: Selected section is emphasized with a glowing border and top target indicator badge, subtly dimming other segments.
- **Section Power Inspector Card**: Detailed telemetry card showing Target Power (scaled to athlete FTP), Duration & Elapsed Timing, Target Cadence (RPM), and Zone metadata.
- **Keyboard & Step Navigation**: Step through sections using ◀ Prev / Next ▶ buttons or Left/Right arrow keys.
- **Collapsible Section Breakdown Table**: View and click through all interval blocks in a structured, sortable overview table.

---

## [1.5.0] - 2026-10-12
### Added
- **AI Coach Daily Debrief**: Evaluates completed workouts against daily Whoop recovery prescriptions and macrocycle targets with Execution Compliance Scoring (0-100%).
- **3-Day Forward Outlook**: Sports-science projection of recovery zones, workout durations, target TSS, and physiological focuses modeled on acute fatigue decay ($\tau \approx 3.0$ days).
- **Tonight's Recovery Directive**: Tailored sleep targets (factoring sleep debt), glycogen replenishment guidelines, and hydration protocols for autonomic restoration.
- **Interactive GPS Route Map**: Embedded high-contrast dark route map with Leaflet tiles, glowing course polyline, and start/finish flags for outdoor rides.
- **Instant Alternative Route Switching**: Zero-latency instantaneous switching between alternative outdoor routes with live course map rendering.

---

## [1.4.0] - 2026-10-12
### Added
- **Outdoor Ride Recommender**: Analyzes your Strava outdoor ride history and suggests prior routes matching your current Whoop recovery and target time.
- **On-the-Bike Execution Plan**: Power ceiling on climbs (% FTP), cadence focus, and terrain management tailored to your daily readiness.
- **Dual-Load Modeling**: Factors trailing 7-day Whoop strain average and peak strain days ($\ge 14.0$) alongside Strava cycling volume.
- **Mode Switcher**: Seamlessly toggle between Indoor Structured Workouts (Zwift/Apple TV) and Outdoor Route Matches.
- **Direct Strava Link**: 1-click route launcher to inspect GPS tracks, elevation profiles, and segments on Strava.

---

## [1.3.1] - 2026-10-11
### Added
- **All 3 Whoop Rings**: Real-time Recovery, Day Strain (0-21.0), and Sleep Performance (%) rings.
- **Dynamic Zone Reactive Styling**: Green, Yellow, and Red zones with signature Whoop cyan and purple accents.
- **Secondary Biometrics**: Real-time HRV rMSSD, Resting Heart Rate, and sleep duration integration.

---

## [1.3.0] - 2026-10-11
### Added
- **Alternative Workouts Generator**: Generates 3 daily options (Coach's Choice, Low-Strain Base, 35m Express).
- **Interactive Workout Switcher**: 1-click option switching updating intervals, profile chart, and Zwift export.
- **Long-Term Periodization Program**: Tracks Base/Build/Peak/Taper phases and event countdown.
- **Weekly TSS Compliance & Target FTP**: Tracks progress against Strava actual training load and target watts.
- **Custom Goal Configuration**: Set target dates, FTP goals, and weekly TSS in Settings modal.

---

## [1.2.4] - 2026-10-11
### Added
- Upgraded Whoop to active v2 endpoints (`/v2/recovery`, `/v2/activity/sleep`, `/v2/cycle`).
- Added high-entropy CSRF state protection for Whoop OAuth.
- Added dedicated 'Sync Whoop' manual trigger to dashboard.
- Live recovery, sleep, and strain integration.

---

## [1.2.0] - 2026-10-11
### Added
- Custom PowerSync biometric lightning app icon and favicon.
- Strava OAuth handshake and activity history synchronization.
- Enabled outbound socket support for real-time cloud data polling.

---

## [1.1.0] - 2026-10-11
### Added
- 1-click cloud sync to Zwift via free Intervals.icu bridge.
- Native `.zwo` XML file generator with power interval steps.
- Real-time interactive Canvas interval profile graph with power zone colors.

---

## [1.0.0] - 2026-10-11
### Added
- Anti-Xert high-signal, low-clutter responsive dashboard.
- Adaptive Coggan sports-science engine & Gemini AI prompt generator.
- SQLite local data layer.
