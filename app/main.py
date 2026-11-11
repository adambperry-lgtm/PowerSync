import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import (
    init_db, get_user_by_session, get_guest_user, get_default_athlete_user,
    set_current_user_context, reset_current_user_context,
    set_current_timezone_context, reset_current_timezone_context
)
from app.routers import dashboard, workouts, settings, auth, review, plans, chat, power

app = FastAPI(
    title="PowerSync - AI Fitness Dashboard",
    description="Adaptive fitness dashboard integrating Whoop recovery, Strava load, and Zwift / Apple TV sync."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.middleware("http")
async def user_session_middleware(request, call_next):
    """
    Multi-User Context Middleware.
    Resolves session token from powersync_session cookie or Bearer header,
    sets request.state.user, and binds CURRENT_USER_ID for complete data isolation.
    Unauthenticated visitors are safely bound to an isolated guest context.
    """
    candidate_tokens = []
    if "authorization" in request.headers:
        auth_val = request.headers["authorization"]
        if auth_val.startswith("Bearer "):
            bt = auth_val[7:].strip()
            if bt:
                candidate_tokens.append(bt)

    cookie_tok = request.cookies.get("powersync_session")
    if cookie_tok and cookie_tok not in candidate_tokens:
        candidate_tokens.append(cookie_tok)

    query_tok = request.query_params.get("token")
    if query_tok and query_tok not in candidate_tokens:
        candidate_tokens.append(query_tok)

    user = None
    for tok in candidate_tokens:
        user = get_user_by_session(tok)
        if user:
            break

    if not user:
        user = get_guest_user()

    request.state.user = user
    ctx_token = set_current_user_context(user["id"])

    req_tz = request.headers.get("x-timezone") or request.query_params.get("timezone")
    tz_token = set_current_timezone_context(req_tz.strip()) if (req_tz and req_tz.strip()) else None

    try:
        response = await call_next(request)
    finally:
        if tz_token:
            reset_current_timezone_context(tz_token)
        reset_current_user_context(ctx_token)

    return response

# Initialize DB tables
init_db()

@app.on_event("startup")
def startup_gemini_status():
    from app.services.coach_chat_service import get_gemini_api_key
    key = get_gemini_api_key()
    print(f"=== PowerSync AI Coach initialized. Gemini Key present: {bool(key)} ===")

# Include Routers
app.include_router(dashboard.router)
app.include_router(workouts.router)
app.include_router(settings.router)
app.include_router(auth.router)
app.include_router(review.router)
app.include_router(plans.router)
app.include_router(chat.router)
app.include_router(power.router)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "PowerSync API is running. UI index.html not yet found."}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "PowerSync"}

@app.post("/api/program/reset-block")
def reset_program_block_api(payload: Optional[dict] = None):
    from app.routers.power import reset_program_block_endpoint
    return reset_program_block_endpoint(payload)

@app.get("/api/version")
def version_info():
    return {
        "version": "2.7.0",
        "release_name": "Physiological Monotonicity & Interval Sustained Power Calibration",
        "build_date": "2026-11-11",
        "services": {
            "whoop": "v2 REST API",
            "strava": "v3 REST API",
            "zwift": "Intervals.icu Cloud Bridge",
            "ai_coach":"Google Gemini 3 Flash / 3.8 Flash (Tool Calling)",
            "cloud": "Railway 24/7 + Persistent Volume"
        },
        "changelog": [
            {
                "version": "v2.7.0",
                "date": "2026-11-11",
                "title": "Physiological Monotonicity & Interval Sustained Power Calibration",
                "items": [
                    "Physiological Monotonicity: Enforced P(5s) >= P(30s) >= P(1m) >= P(5m) >= P(20m) >= P(60m) so shorter durations can never have lower power than longer durations.",
                    "Sustained Interval Floors: Eliminated downward sprint-decay capping that artificially degraded steady trainer workouts (e.g. 14m @ 215W+) down to 143W at 5m and 163W at 1m.",
                    "Telemetry-Driven Durations: Anchored 5m, 1m, and sprint intervals to normalized power (NP), average power, and lap telemetry for accurate anaerobic and VO2 representation."
                ]
            },
            {
                "version": "v2.6.9",
                "date": "2026-11-11",
                "title": "Cycling Activity Detection Telemetry & Consistent Ride Counts",
                "items": [
                    "Ride Count Consistency: Synchronized monthly card header and footer ride counts, accurately attributing non-cycling sessions as cross-training (+N cross) without inflating ride tallies.",
                    "Power Telemetry & Indoor Recognition: Enhanced is_cycling_sport to detect smart trainer intervals, indoor rides, and power meter telemetry (watts/kilojoules) regardless of generic 'Workout' tagging.",
                    "Interval Block Peak Extraction: Updated peak power calculations to analyze sustained 10-25m interval blocks (e.g. 3x14m @ 215W+) for accurate 5m and 20m curve modeling.",
                    "Live Strava Auto-Sync: Automatically syncs recent Strava activities when accessing the Power Spiderweb to guarantee same-day rides appear immediately."
                ]
            },
            {
                "version": "v2.6.8",
                "date": "2026-11-11",
                "title": "Refined Mini-Spiderweb Hero Radars & 5-Column Power Strip",
                "items": [
                    "Hero Mini-Spiderweb Centerpiece: Enlarged 105px radar canvas with 5 clearly labeled duration vertices (5s, 1m, 5m, 20m, 60m), concentric rings, and interactive tooltips.",
                    "Full-Width 5-Column Power Strip: Replaced cramped side-by-side pills with a structured 5-column metric strip that perfectly aligns with card boundaries and never overflows.",
                    "Zero Border Clipping: Applied overflow: hidden and box-sizing: border-box across timeline cards and power cells for flawless rendering across all screen sizes."
                ]
            },
            {
                "version": "v2.6.7",
                "date": "2026-11-11",
                "title": "Visual Power Curve Progression & Monthly Mini-Spiderwebs",
                "items": [
                    "3-Line Power Duration Curve: Interactive SVG chart comparing Current Period (Cobalt Blue), Previous Period (Slate Purple dashed), and All-Time PR / Target Envelope (Speed Orange) across 5s, 1m, 5m, 20m, and 60m.",
                    "Monthly Mini-Spiderwebs: Native 5-axis mini-radar charts embedded in monthly progression cards to visualize phenotype evolution and duration balance over time.",
                    "Interactive Timeline View Switcher: 3-way toggle between All, 3-Line Curve, and Mini-Spiderwebs with responsive theme styling."
                ]
            },
            {
                "version": "v2.6.6",
                "date": "2026-11-11",
                "title": "Rider Type Change Macrocycle Reset Confirmation",
                "items": [
                    "User Confirmation on Goal Change: Prompts athlete confirmation before resetting the macrocycle block timeline when selecting or changing rider types or targets.",
                    "Athlete Agency: Clicking OK resets the block to Week 1 (56 days, Base Phase); clicking Cancel updates the target phenotype and envelope while keeping the existing macrocycle schedule intact.",
                    "Dual-Planner & Settings Integration: Confirmation flows seamlessly through both the Fitness Profile Target Planner and the Settings modal."
                ]
            },
            {
                "version": "v2.6.5",
                "date": "2026-11-11",
                "title": "Macrocycle Block Timeline Reset on Goal Activation",
                "items": [
                    "Automatic Block Reset: Selecting a new Rider Type or Spiderweb Goal absent a scheduled race now automatically resets the periodization macrocycle to Week 1 (8-week adaptation block).",
                    "Eliminated Trailing Block Expiration: Prevents new training goals from inheriting an old block's countdown (e.g. 8 days remaining in block), resetting days remaining to 56 days in Base Phase.",
                    "1-Click 'Reset Block' Action: Added #btnResetProgramBlock to the Long-Term Program card and POST /api/program/reset-block endpoint for instant manual block calibration.",
                    "Settings Goal Synchronization: update_program_goal now automatically recalibrates start and target dates for new phenotype blocks."
                ]
            },
            {
                "version": "v2.6.4",
                "date": "2026-11-11",
                "title": "Unified Rider Type Target Envelope & Periodization Macrocycle",
                "items": [
                    "First-Class Rider Types: Pursuiter, Climber, Rouleur, Puncheur, Sprinter, and All-Rounder are now first-class goals across Settings and the Long-Term Program card.",
                    "Spiderweb Drives Long-Term Envelope: The 5-axis target envelope directly defines the athlete's target power profile and Target FTP absent a specific event.",
                    "Phenotype Adaptation Periodization: Without a scheduled race, the macrocycle follows a 4-phase adaptation progression culminating in Phase 4: Mastery & Benchmark Test rather than an artificial race taper.",
                    "Visible Target Envelope Chips: Added #programEnvelopeStrip displaying the 5-axis target wattages (5s, 1m, 5m, 20m, 60m) directly within the Long-Term Goal card."
                ]
            },
            {
                "version": "v2.6.3",
                "date": "2026-11-11",
                "title": "Coggan Elite Physiological Benchmarks & Ceiling Calibration",
                "items": [
                    "Scientific Elite Benchmarks: Calibrated duration benchmarks against Coggan Category 1 / Elite power-to-weight (W/kg) standards and athlete body weight (5s: 20.5, 1m: 9.6, 5m: 6.1, 20m: 5.0, 60m: 4.6 W/kg).",
                    "Dynamic Ceiling Protection: Guaranteed that benchmark ceilings dynamically scale to exceed athlete current bests and all-time PRs (max(coggan_elite, cur_watts * 1.15, all_time_pr * 1.10)).",
                    "Monotonic Duration Tiers: Tier 3 Benchmark Ceiling targets are mathematically guaranteed to sit above Tier 1 (+5%), Tier 2 (+10%), and current bests, preventing inverted targets.",
                    "High-Contrast Light Theme Accents: Updated Tier 3 duration planner cards to crisp #7C3AED accent pills and readable typography."
                ]
            },
            {
                "version": "v2.6.2",
                "date": "2026-11-11",
                "title": "Long-Term Fitness Goal & Periodization Color Palette Alignment",
                "items": [
                    "Card & Elevation Harmony: Aligned .program-card with Speed & Summit palette (#F4F7FA card background, #DCE4EE borders, soft elevation), eliminating dark navy backgrounds and contrast clashes.",
                    "Macrocycle Timeline: Modernized periodization track with #E2E8F0 rail and Speed & Summit gradient (#0052FF -> #00C896 -> #FF5E00).",
                    "Crisp Badges & Typography: Phase badges updated to cobalt blue (#0052FF on light blue pill) and active timeline column highlighting.",
                    "Target FTP Callout: Dedicated .program-stat-box-target styling with high-contrast Speed Orange (#FF5E00) metric value and subtle accent borders."
                ]
            },
            {
                "version": "v2.6.1",
                "date": "2026-11-11",
                "title": "Cross-Training Isolation & Cycling Power Telemetry Integrity",
                "items": [
                    "Cycling Power Isolation: Strictly quarantined cycling power duration models, peak power calculation, 5-axis radar spiderwebs, and PR breakthroughs from non-cycling activities (running, swimming, weight training, rowing, hiking).",
                    "PR Breakthroughs Integrity: PR breakthroughs in the breakthroughs feed now scan authentic cycling rides exclusively, preventing non-cycling workouts from claiming cycling power PR breakthroughs.",
                    "Cross-Training Fitness & Fatigue: Enhanced calculate_activity_strain to convert non-cycling cardiovascular training stress (Strava Suffer Score / Relative Effort, heart rate intensity, duration) into systemic aerobic strain (Low XSS and Total XSS) and acute fatigue without depleting cycling pedal W' balance.",
                    "Holistic Sports Science Debriefs: Debrief engine now natively identifies cross-training days, presenting conditioning summaries without comparing running or gym watts against cycling FTP."
                ]
            },
            {
                "version": "v2.6.0",
                "date": "2026-11-11",
                "title": "Power Spiderweb & Multi-Axis Coggan Phenotype Profiling Engine",
                "items": [
                    "Unified Multi-Axis Coggan Phenotype Profiling: Replaced the order-dependent if/elif waterfall with a scientific, multi-axis power profile classification model (classify_athlete_phenotype). Evaluates relative energy system strengths across all 5 durations (5s sprint, 1m glycolytic, 5m VO2 Max, 20m threshold, 60m stamina) to classify phenotypes (All-Rounder, Pursuiter, Puncheur, Rouleur, Climber, Sprinter) without cascade pre-emption.",
                    "Continuous Phenotype Readiness & Affinity Scoring: Computes smooth, weighted readiness percentages (0–100%) and multi-axis affinity scores, ending conflicting 100% qualifications across disparate archetypes.",
                    "Transformation Goal Progression & 0W Gap Elimination: Signature axes for target phenotypes now challenge athletes with a progressive +5% adaptation overload when baseline requirements are already met, ensuring transformation targets always provide positive, actionable wattage goals instead of instant 0W completion.",
                    "Physiological Duration Gating & Activity Peak Power Accuracy: Refined calculate_activity_peak_powers to enforce strict minimum moving times (e.g. 20m and 60m require genuine ride durations), honor power meter max_watts telemetry, extract lap/segment interval peaks, and calibrate anaerobic W' contribution to ride intensity.",
                    "Planner UI Status & Card Polish: Updated rider archetype cards to show '🎯 Current Classification (X% Match)' for the active phenotype and clear progressive readiness for transformation goals."
                ]
            },
            {
                "version": "v2.5.7",
                "date": "2026-11-11",
                "title": "Removed Static Live In-Ride Pacing Bottom Sheet",
                "items": [
                    "Directeur Sportif Live Pacing Removal: Removed the static simulated in-ride pacing bottom sheet ('DIRECTEUR SPORTIVE • LIVE PACING INSIGHT') from the workout interface since in-ride telemetry is not live during pre-ride workout planning.",
                    "Cleaned DOM & Styles: Removed the bottom sheet markup, event listeners, and unused CSS rules across mobile and desktop styles."
                ]
            },
            {
                "version": "v2.5.6",
                "date": "2026-11-11",
                "title": "Debrief Workout Timeline Accuracy & Past Session Attribution",
                "items": [
                    "Debrief Workout Timeline Accuracy: Corrected temporal attribution in the Sports-Science Assessment debrief so older workouts (e.g. from several days ago or last week) are never falsely described as 'yesterday' or linked as immediate day-after causes of today's Whoop recovery score.",
                    "Gemini Coach Prompt Engineering: Enforced strict timeline directives in call_gemini_coach_review, explicitly separating today's baseline recovery from past session dates (e.g., Wednesday, Nov 4 / 6 Days Ago) and forbidding 'yesterday' hallucination when reviewing older sessions.",
                    "Defense-in-Depth Sanitization: Implemented automated timeline post-processing to replace any hallucinated 'yesterday' phrases in coach debriefs with accurate date and relative day labels.",
                    "UI Debrief Headers & Subtitles: Enhanced debrief activity metadata and subtitles to format friendly date displays (e.g., 'Wednesday, Nov 4 (6 Days Ago)') for single and multi-session historical reviews."
                ]
            },
            {
                "version": "v2.5.5",
                "date": "2026-11-11",
                "title": "Renamed AI Race Briefing to Ride Briefing",
                "items": [
                    "Ride Briefing Terminology: Updated card title, collapse header, and directive banners across top telemetry cards, indoor structured stages, and outdoor route previews from 'AI Race Briefing' to 'Ride Briefing' for a more natural daily training experience."
                ]
            },
            {
                "version": "v2.5.4",
                "date": "2026-11-11",
                "title": "Card Header Layout & Text Bubble Collision Fixes",
                "items": [
                    "Telemetry Grid Header Layout & Wrapping: Fixed card-header flex wrapping and prevented title wrapping under icons by enforcing nowrap in card-header-left and setting a resilient minimum width on header titles. Sub-status badges and collapse controls now wrap cleanly without overlapping card titles.",
                    "AI Coach Narrative Overflow & Scrollbar: Added overflow-y: auto and box-sizing to #coachCardNarrative with a sleek thin scrollbar, ensuring long briefing texts (e.g., forecast confirmation explanations) never spill over or collide with footer jump links.",
                    "Ellipsis Protection & Title Tooltips: Added text-overflow: ellipsis and full title hover tooltips for formStatusBadge and coachCardFooterSubtext to safeguard against multi-line text running across adjacent controls."
                ]
            },
            {
                "version": "v2.5.3",
                "date": "2026-11-11",
                "title": "Default Opening Tab Set to Daily Training View",
                "items": [
                    "Default Daily View on Startup: Configured initMainViewSwitcher() so PowerSync always opens on the Daily Training ('daily') tab by default when launching or refreshing the app."
                ]
            },
            {
                "version": "v2.5.2",
                "date": "2026-11-11",
                "title": "Restored 'PowerSync' Brand Name on Speed & Summit UI",
                "items": [
                    "PowerSync Brand Restoration: Changed the application name back to PowerSync across the navigation bar, browser title, iOS PWA title, Coach Chat drawer, modals, footer, and launcher pages while preserving the Speed & Summit design system."
                ]
            },
            {
                "version": "v2.5.1",
                "date": "2026-11-10",
                "title": "iPhone & Mobile Viewport Formatting & Light-Theme Contrast Fixes",
                "items": [
                    "Mobile Media Query & Telemetry Grid Fix: Fixed a stray closing brace in @media (max-width: 768px) and ensured Whoop, Strava, and AI Race Briefing cards stack cleanly at 100% width on iPhone screens.",
                    "Sleek 2-Row iPhone Navbar & 3-Column Mode Tabs: Compacted mobile navbar actions onto Row 1 with the Daily/Analysis switcher on Row 2, and formatted 3-tab switchers (#debriefTabGroup, #planSourceTabs) into a balanced 3-column layout.",
                    "Live Workout Dynamic Coaching Bottom Sheet: Positioned the Directeur Sportive live pacing bottom sheet directly inside the Live Workout Interface with animated 4-bar wave indicators and mobile-friendly actions.",
                    "Mobile Coach Chat & 3-Tier Strain Contrast: Replaced dark-mode mobile overrides in the Coach Chat drawer, pull-to-reload pill, and 3-Tier Strain / W' Battery readouts with high-contrast Ice Frost (#F4F7FA), Electric Cobalt Blue (#0052FF), and Midnight Carbon (#111625) styles."
                ]
            },
            {
                "version": "v2.5.0",
                "date": "2026-11-10",
                "title": "VeloMetrics AI — 'Speed & Summit' Design System & UI Rebranding",
                "items": [
                    "Brand Identity Rebrand to VeloMetrics AI: Updated application branding, header logo, modals, and footer with the value proposition 'Data-driven training meets human passion. Your personalized AI coach for every pedal stroke.'",
                    "'Speed & Summit' High-Contrast Palette: Applied Pure White (#FFFFFF) primary background, Ice Frost (#F4F7FA) card containers, Electric Cobalt Blue (#0052FF) primary brand/navigation metrics, Sunset Orange (#FF5E00) high-energy CTAs and peak power alerts, Midnight Carbon (#111625) primary typography, Slate Gray (#64748B) labels, and Mint Teal (#00C896) recovery indicators.",
                    "Geometric Typography & Custom Iconography: Paired Outfit (Bold/Black weights) for headlines and big wattage metrics with Inter (Regular/Medium) for body copy, alongside custom rounded line icons, filled Sunset Orange lightning bolts, cadence dials, elevation profiles, and glowing AI wave pulses.",
                    "Directeur Sportif (DS) AI UI Elements: Introduced pulsing dual-tone gradient rings (#0052FF to #FF5E00) around AI insights, Ice Frost AI 'Race Briefing' cards with Sunset Orange FTP/Zone 4 highlights, smooth Blue-to-Orange workout power zone bars, and a sleek live coaching bottom sheet."
                ]
            },
            {
                "version": "v2.4.5",
                "date": "2026-11-10",
                "title": "Settings Authentication & Credential Hardening",
                "items": [
                    "Authenticated /api/settings Guard: Placed /api/settings and all coaching preference sub-routes behind mandatory session authentication (HTTP 401 Unauthorized for unauthenticated requests).",
                    "Zero-Credential Response Payload: Removed masked API key strings and raw OAuth client IDs from /api/settings and /api/auth/google/status responses, exposing only boolean status indicators.",
                    "Endpoint Security Hardening: Restricted /api/auth/debug-headers, /api/auth/lock-owner, /api/auth/disconnect, /api/chat/save-key, and /api/chat/test-connection to signed-in sessions."
                ]
            },
            {
                "version": "v2.4.4",
                "date": "2026-11-09",
                "title": "Header Branding Subtitle Update",
                "items": [
                    "Updated navbar branding subtitle from 'Adaptive Coach & Zwift Sync' to 'AI Cycling Coach'."
                ]
            },
            {
                "version": "v2.4.3",
                "date": "2026-11-01",
                "title": "Comprehensive Code Audit, Multi-User Isolation & UI Hardening",
                "items": [
                    "Coach Chat UnboundLocalError Remediation: Lifted uid and ftp definitions to top of apply_chat_action_endpoint, ensuring seamless execution across schedule_workout, schedule_upcoming_plan, clear_upcoming_plan, and apply_today_workout.",
                    "Strict Multi-User Isolation in Coach Tools: Removed default user fallbacks across Strava activity details, API proxies, and Whoop timeline tools, guaranteeing authenticated athletes never leak or view another user's biometric telemetry or ride data.",
                    "Gemini Parallel Tool Call Turn Bundling: Bundled all parallel tool function response parts into a single user turn, strictly satisfying Gemini API multi-turn alternation requirements and preventing HTTP 400 errors.",
                    "Comprehensive Null-Safety Hardening: Added fallback defaults for nullable moving_time_sec, distance_meters, suffer_score, and recovery_score fields across workouts, preferences, outdoor coach, and dashboard routers.",
                    "Canvas & Outdoor Map View Switcher Redraw: Bound drawWorkoutGraph, outdoorMap.invalidateSize, and spiderweb SVG rendering to requestAnimationFrame triggers during tab transitions, preventing canvas collapsing.",
                    "Touch Target & Modal Accessibility: Enlarged modal close buttons to 44x44px minimum touch targets and refined light-mode contrast across inputs, dropdowns, and form labels."
                ]
            },
            {
                "version": "v2.4.2",
                "date": "2026-11-01",
                "title": "Dual Dashboard View Switcher & Evening Workout Timezone Alignment",
                "items": [
                    "Segmented Dashboard View Switcher: High-contrast toggle at top of dashboard separating Daily Training & Execution (Whoop, Strava, Coach Directive, Workout Stage, 3-Day Forecast, Debrief, Recent Workouts) from Long-Term Performance & Strategy (Power Spiderweb, Macrocycle Program, Coggan Zones).",
                    "View State & Hash Persistence: Preserves active view in localStorage and URL hash (#daily vs #analysis) with automatic tab switching on cross-pane anchor clicks.",
                    "View-Scoped Master Collapse/Expand: Dynamically scopes the master expand/collapse button to control tiles only within the active view pane.",
                    "Authoritative Evening Workout Timezone Resolution: Prioritizes athlete's configured timezone over inaccurate Strava/Watopia UTC timestamps for virtual/indoor rides, preventing 9-10 PM workouts from rolling into the next day.",
                    "Daily Training Slate & Debrief Harmony: Ensures evening workouts appear with their true local calendar date, properly referenced in yesterday's debrief while keeping today's prescription fresh and unblocked."
                ]
            },
            {
                "version": "v2.4.1",
                "date": "2026-11-01",
                "title": "Category Target Changes Explorer & Spiderweb Training Goal Setting",
                "items": [
                    "Duration Category Target Explorer: Interactive target progression engine analyzing what wattage changes (+W, +%, +W/kg) are required across 5s, 1m, 5m, 20m, and 60m durations to achieve Progressive (+5%), Transformative (+10%), or Elite Benchmark Ceiling leaps.",
                    "Rider Type Transformation Analysis: Precise multi-axis gap analysis mapping exact power envelope requirements needed to transform into target phenotypes (Puncheur, Rouleur, Climber, Sprinter, Pursuiter, All-Rounder) with readiness completion percentages.",
                    "Active Spiderweb Training Goal Setting: Athletes can set active training goals from any duration milestone or rider archetype via UI or Coach Chat. Persisted per athlete in database.",
                    "3rd Radar Target Overlay Polygon: Visualizes active training goal directly on the spiderweb radar as a glowing emerald dashed polygon (#10b981) with diamond vertex targets and progress tracking.",
                    "AI Coach Adaptation & Tool Calling: AI coach incorporates active spiderweb goals into daily session prescriptions and sports-science debriefs, and exposes Gemini function calling tools (get_active_spiderweb_goal, set_spiderweb_goal) in Coach Chat."
                ]
            },
            {
                "version": "v2.4.0",
                "date": "2026-11-01",
                "title": "Interactive Power Spiderweb Radar & Progress Over Time (Strava & Xert Signature Model)",
                "items": [
                    "5-Axis Physiological Power Spiderweb: Implemented interactive radar spiderweb comparing athlete power outputs across 5 core energy system durations: 5s Sprint (Neuromuscular), 1m Anaerobic (Glycolytic), 5m VO2 Max (Aerobic Ceiling), 20m Threshold (Lactate Equilibrium), and 60m Stamina (Aerobic Endurance).",
                    "Dual-Period Overlay Polygons: Visualizes current period (glowing cyan polygon) overlaid directly against baseline comparative periods (translucent dashed violet polygon) with dynamic percentage scaling against benchmark physiology ceilings.",
                    "Multi-Window Timeframe Analysis: Interactive timeframe tabs supporting 30D vs Prior 30D, 60D vs Prior 60D, 90D vs Season, and All-Time PR envelopes.",
                    "Rider Phenotype Classification: Analyzes envelope distribution to categorize athlete phenotype (Sprinter, Puncheur, Pursuiter, Rouleur, Climber, All-Rounder) highlighting primary strengths and targeted physiological growth opportunities.",
                    "Duration Metrics Grid & Progression Timeline: Displays live power deltas (+W, +%, W/kg) for each duration alongside chronological monthly peak power progressions and historical power PR breakthroughs feed."
                ]
            },
            {
                "version": "v2.3.3",
                "date": "2026-10-30",
                "title": "Prescribed Schedule Target Fidelity in Coach Analysis & Live Strava List Auto-Sync",
                "items": [
                    "Updated Schedule Target Fidelity: Enhanced review coach with resolve_day_prescribed_target() to evaluate completed workouts against the specific prescribed session (e.g. Zone 2 Aerobic Base, Active Recovery Flush, or scheduled intervals) rather than defaulting to Sweet Spot whenever Whoop recovery is high.",
                    "Execution Bullseye for Lower-Effort Adherence: Athletes adhering precisely to lower-effort rides or endurance targets receive 'Target Mastered' / 'Execution Bullseye' verdicts without false 'Conservative Pacing' warnings.",
                    "Live Strava Feed Auto-Sync: Added automatic background syncing for Strava on 60s cadence and on tab focus, auto-populating the Recent Workouts table at the bottom of the dashboard without manual button clicks.",
                    "Expanded Recent Workouts Feed: Increased recent Strava activity history from 5 to 15 items in the dashboard response."
                ]
            },
            {
                "version": "v2.3.2",
                "date": "2026-10-30",
                "title": "Multi-Day Weekend Forecast Sync, Instant UI Refresh & Training Slate Safeguard",
                "items": [
                    "Multi-Day Weekend Directives: Coach Chat and forecast service simultaneously extract multi-clause weekend plans (e.g. '50 miles tomorrow and resting sunday'), correctly splitting athlete intent from complaint clauses and staging distinct workouts for both days.",
                    "3-Day Forecast UI Reactive Refresh: Instantly updates the 3-day forecast in the DOM as soon as plans are discussed or confirmed, prioritizing '💬 Coach Scheduled' badges over generic athlete notes.",
                    "Slate Protection Against Taper Hijacking: Casual weekend rides no longer truncate or overwrite today's Friday prescribed session into a 30-minute pre-event neuromuscular primer.",
                    "Universal Strain Corroboration: Unified daytime cardiovascular strain checking across all workout endpoints to guarantee fresh 0.0 strain morning baselines receive their prescribed workouts without false rest day locks."
                ]
            },
            {
                "version": "v2.3.1",
                "date": "2026-10-29",
                "title": "Coach Chat 3-Day Forecast Dynamic Adjustment & Evening Workout Timezone Resolution",
                "items": [
                    "Dynamic 3-Day Forecast Chat Adjustment: Discussing upcoming rides or schedule changes in Coach Chat (e.g. 50-mile Saturday group ride, tomorrow threshold over-unders, or Friday rest day) automatically adapts the 3-day forward forecast outlook cards and interval breakdowns with '💬 Coach Scheduled' badges and fatigue decay modeling.",
                    "Upcoming Plan Persistence: Staged and confirmed Coach Chat plans are permanently stored in coach_upcoming_plans and seamlessly override future forecast day archetypes while preserving athlete weekly preferences.",
                    "Strava True start_date_local Prioritization: Enhanced resolve_strava_local_start to prioritize Strava's true start_date_local and utc_offset over generic UTC server conversions, ensuring evening rides (9-10 PM) stay permanently anchored to the evening date they occurred.",
                    "Morning Training Slate Physiological Guardrail: Prevented workouts from falsely blocking morning training when Whoop daytime strain is 0.0 with green recovery, ensuring 95% recovery slates receive their proper prescribed session.",
                    "Auto-Timezone Calibration: Automatically extracts athlete timezone from synced Strava activities if unconfigured."
                ]
            },
            {
                "version": "v2.3.0",
                "date": "2026-10-29",
                "title": "Google Gemini Function Calling & Live Strava/Whoop Tool Engine",
                "items": [
                    "Gemini Tool Calling Loop: Integrated native function declarations with Google Gemini (gemini-3-flash-preview / gemini-3.8-flash) enabling the AI Coach to dynamically execute tools to query real Strava telemetry on demand.",
                    "Granular Strava Lap & Split Telemetry: Added get_strava_activity_details tool to retrieve detailed lap breakdowns, work vs rest intervals, cadence, and 3-tier XSS strain for any ride ('latest', 'yesterday', or specific ID).",
                    "Power Curve & Aerobic Decoupling: Added get_strava_activity_streams_and_power_curve tool calculating peak power sliding windows (5s, 1m, 5m, 20m) and heart rate cardiac drift percentage.",
                    "Activity Search & Whoop Correlation: Added search_strava_activities and get_whoop_biometrics_timeline tools enabling historical workout comparison and physiological recovery correlation.",
                    "Interactive Chat Tool Badges: Visualized tool execution chips in the Coach Chat modal showing the athlete exactly what telemetry the coach analyzed."
                ]
            },
            {
                "version": "v2.2.10",
                "date": "2026-10-28",
                "title": "Evening Workout Timezone Migration & Training Slate Unification",
                "items": [
                    "Zero-Dependency Database Migration: Decoupled timestamp migration from the Strava service to ensure all legacy UTC-stored Strava rides in SQLite are reliably migrated to the athlete's local ISO time on startup without circular import blocks.",
                    "Strava Resync Local Start Preservation: Updated conflict resolution during Strava re-syncs to update start_date with local timestamps, ensuring Zwift evening sessions stay properly anchored to the night they occurred.",
                    "Robust VirtualRide Timezone Handling: Enhanced resolve_strava_local_start to accurately transform UTC timestamps for virtual indoor rides (which lack physical GPS coordinates) directly into the athlete's local time zone (America/New_York).",
                    "Clean Morning Training Slate: Guaranteed that yesterday evening rides do not populate today's completed workouts, unlocking fresh tailored workouts based on 95% Whoop recovery."
                ]
            },
            {
                "version": "v2.2.9",
                "date": "2026-10-28",
                "title": "Evening Workout Timezone Alignment & Clean Daily Slate",
                "items": [
                    "Local Start Time Resolution: Strava activities recorded in evening hours (e.g. 9-10 PM) are accurately mapped to the athlete's local calendar date rather than rolling over into the next day via UTC timestamps.",
                    "Clean Morning Training Slate: Resolved issue where yesterday evening's ride caused the AI Coach to mistakenly assume today's workout was already completed, wrongly prescribing 'Daily Target Achieved — Rest & Recovery'.",
                    "Eliminated Rolling Window Heuristics: Removed legacy 20-hour window logic in workout generator that conflated prior night rides with today's training session, aligning workout prescription directly with the athlete's local calendar day and fresh Whoop recovery.",
                    "Automated Historical Strava Migration: Added automatic database migration converting existing UTC-stored Strava timestamps to athlete local time on startup."
                ]
            },
            {
                "version": "v2.2.8",
                "date": "2026-10-25",
                "title": "Automatic Whoop Biometric Sync & Session Persistence",
                "items": [
                    "Whoop Auto-Sync on Dashboard Load: Automatically checks and fetches the athlete's latest Whoop metrics in the background upon opening the app and at 15-minute intervals.",
                    "Persistent Biometric Storage: Synced Whoop biometrics (Recovery %, Sleep %, HRV, RHR, Strain) are permanently stored in SQLite and retained across browser exits, tab closes, and mobile PWA sessions until overwritten by the next sync.",
                    "Accurate Physiological Date Resolution: Whoop recovery records are correctly aligned to the athlete's wake-up calendar day in their local timezone, eliminating false 'Yesterday' labels and unnecessary re-sync prompts.",
                    "Zero-Data-Loss Session Bridge: Personal single-owner instances automatically establish persistent sessions and provide seamless credential/biometric fallbacks so unauthenticated visits never revert to empty mock data."
                ]
            },
            {
                "version": "v2.2.7",
                "date": "2026-10-23",
                "title": "Multi-Workout Collective Daily Assessment & Coggan Power Integration",
                "items": [
                    "Collective Multi-Workout Debrief: AI Coach now aggregates all sessions completed on a single day (e.g. main ride + cooldown spin) collectively instead of assessing only the most recent spin.",
                    "Coggan 4th-Power NP Aggregation: Combined daily normalized power is calculated via 4th-power weighting to preserve primary workout intensity rather than dragging averages down to cooldown levels.",
                    "Primary Effort Target Fidelity: Pacing compliance scores evaluate the primary workout's target zone alignment, crediting the athlete for hitting targets while acknowledging cooldowns as active recovery / lactate clearing.",
                    "Session Breakdown Badges: Daily Debrief header surfaces individual session pills detailing duration, power, and TSS for every ride completed."
                ]
            },
            {
                "version": "v2.2.6",
                "date": "2026-10-21",
                "title": "Forecasted Workout Preview & Interactive Interval Breakdown",
                "items": [
                    "Clickable 3-Day Forecast Cards: Athletes can now click on any day card in the 3-day forward training forecast to launch an interactive, high-fidelity Workout Preview Modal.",
                    "Full-Color Canvas Profile & Wattage Telemetry: Dynamically visualizes the forecasted session's interval sequence, progressive ramp warmup, work intervals, recovery spin valleys, and cooldown, scaled to athlete FTP with 100% FTP threshold reference line.",
                    "Structured Step-by-Step Interval Breakdown: Detailed list displaying every interval repetition, target power (% FTP & exact Watts), target cadence (RPM), and duration.",
                    "1-Click Target Day Zwift Sync & Coach Chat: Direct 'Push to Zwift for This Day' button enables staging future rides directly to Apple TV / Zwift, plus 1-click 'Edit in Coach Chat' alignment."
                ]
            },
            {
                "version": "v2.2.5",
                "date": "2026-10-21",
                "title": "Mobile Settings Form Layout & Date Input Alignment",
                "items": [
                    "Resolved Settings Input Overflow & Misalignment: Fixed an issue where the Target Event Date input and adjacent form fields blew out past the right boundary of the cyan card container onto the modal backdrop on mobile screens.",
                    "Mobile-Responsive Modal Form Grid: Implemented dedicated .settings-form-grid with full-width stacking on mobile screens (<= 768px) and min-width: 0 protection on grid cells to eliminate horizontal clipping.",
                    "Native iOS Date Input Styling: Applied appearance: none, color-scheme: dark, and left-aligned date formatting (::-webkit-date-and-time-value) for seamless native rendering on iOS Safari and PWA."
                ]
            },
            {
                "version": "v2.2.4",
                "date": "2026-10-21",
                "title": "Zwift ERG Target Wattage Precision Calibration",
                "items": [
                    "Eliminated 1-2 Watt Truncation Drop: Fixed an issue where Zwift's C++ ERG game engine integer-truncated floating-point power ratios from .zwo files, causing targets in Zwift to appear 1-2W lower than in PowerSync.",
                    "Exact-Watt Centering Calibration: Calibrated .zwo power ratio export with high-precision centering ((target_watts + 0.15) / ftp) to guarantee 100% exact integer watt matching across all athlete FTPs.",
                    "User-Scoped Sync Lookups: Scoped Intervals.icu credentials and athlete FTP directly to user session in push endpoint."
                ]
            },
            {
                "version": "v2.2.3",
                "date": "2026-10-21",
                "title": "Dedicated Route Uploader & Conversational Coach Chat Alignment",
                "items": [
                    "Removed Legacy Adapt/Plan Ride Text Box: Eliminated the confusing text input and button that previously reran keyword-matching heuristics instead of targeted interval edits.",
                    "Direct GPX Route Uploader: Converted the workout controls into a streamlined 1-click GPX route uploader (🗺️ Upload Route (.gpx)) that immediately loads route elevation, distance, and pacing targets.",
                    "Conversational Coach Chat Alignment: Unified all custom interval tweaks and workout modifications into the Gemini AI Coach Chat with direct 1-click workout application."
                ]
            },
            {
                "version": "v2.2.2",
                "date": "2026-10-21",
                "title": "Automated Morning Whoop Sync & Continuous Biometric Heartbeat",
                "items": [
                    "Automated Morning Whoop Refresh: Morning recovery, sleep performance, and day strain auto-refresh seamlessly upon opening the app or pulling to reload.",
                    "15-Minute Recency Sync: Added timestamp staleness tracking to continuously poll live Whoop metrics without requiring manual button taps.",
                    "Unfinalized Recovery Auto-Fetch: If today's recovery was recorded prior to morning wake-up scoring, PowerSync automatically fetches final scored recovery.",
                    "Multi-User Token Resolution: Scoped all Whoop credential lookups directly to the active athlete session."
                ]
            },
            {
                "version": "v2.2.1",
                "date": "2026-10-20",
                "title": "Athlete Timezone Continuity & Evening UTC Offset Normalization",
                "items": [
                    "Athlete Timezone Continuity: Fixed premature calendar rollover on UTC cloud servers (00:00+ UTC / 8:00 PM+ EDT) so evening workouts are correctly evaluated as Today rather than Yesterday.",
                    "3-Day Forward Outlook Alignment: Synced forecast generator to local athlete time so Tomorrow consistently points to the immediate next calendar day (Day +1).",
                    "Client Timezone Auto-Discovery: Intercepts browser IANA timezone (X-Timezone header) and binds request context to athlete's local clock."
                ]
            },
            {
                "version": "v2.2.0",
                "date": "2026-10-20",
                "title": "3-Day Forecast Integration, Anti-Repetition Engine & Real-Time Sync Resilience",
                "items": [
                    "3-Day Forecast & Daily Workout Integration: Forward 3-day forecast plans are persisted in database storage. When morning recovery matches projected assumptions, the daily workout selector confirms and prescribes the exact promised session (⭐ Coach's Choice • Forecast Confirmed). If recovery drops into the red, the coach adaptively explains the physiological pivot.",
                    "Dynamic Workout Catalog & Anti-Repetition Engine: Replaced static sweet spot over-unders with an extensive catalog of diverse archetypes across Sweet Spot, Threshold, VO2 Max, Tempo, and Endurance Base (Sustained Blocks, Criss-Cross Surges, Pyramid Power Density, Microbursts, Over-Unders). Anti-repetition history tracking prevents identical workouts on consecutive sessions (e.g. Wednesday vs. Friday).",
                    "Auto-Syncing Strava & Completed Workout Protection: Added automatic live syncing for Strava activities on dashboard and workout load. Completed daily rides now transition Today's Training into 'Daily Target Achieved — Rest & Recovery' and prevent scheduled workouts from overwriting completed sessions.",
                    "3-Tier Physiological Strain Engine (XSS & W'bal): Integrated Morton/Skiba Critical Power and W' anaerobic battery depletion modeling, partitioning mechanical and autonomic stress into Low (Aerobic), High (Glycolytic), and Peak (Sprint) strain tiers.",
                    "Mobile Layout & iPhone PWA Polish: Redesigned the 3-Tier Strain card header to eliminate multi-line text squishing on mobile screens, cleaned up battery meter typography, and added bottom safe-area scroll clearance to prevent floating coach action buttons from obstructing debrief content.",
                    "True Power-Based TSS & HR Telemetry: Fixed cardiovascular load calculation to derive true power-based Training Stress Score (TSS = (sec * NP * IF) / (FTP * 3600) * 100) and populate actual average/max heart rate from Strava streams."
                ]
            },
            {
                "version": "v2.1.0",
                "date": "2026-10-16",
                "title": "Multi-User Security Isolation, Unified Typography & Google OAuth",
                "items": [
                    "Full Multi-User Database Isolation: Scoped all settings, biometric histories, Strava activities, training plans, and forecast caches by user session ID with automatic data migration and dev-account switching.",
                    "5-Level Typography & Card Accents: Coherent typographic hierarchy and gradient accent bars across all tiles.",
                    "Natural Language Workout Customization: Direct chat instructions dynamically adapt workouts, recalculate TSS/XSS, and generate exportable .zwo / Intervals.icu workouts."
                ]
            },
            {
                "version": "v2.0.0",
                "date": "2026-10-15",
                "title": "Cloud 24/7 Architecture, 1-Click Integrations & Permanent Dark Mode",
                "items": [
                    "24/7 Cloud Deployment on Railway: Docker containerized backend accessible 24/7 at powersync.up.railway.app with automated health checks",
                    "Persistent Volume Storage: SQLite fitness database backed by persistent Railway volume (/app/data/fitness.db), preserving biometric trends, Strava activities, and tokens across redeployments",
                    "Streamlined 1-Click Connect Cards: Replaced developer credential input fields with clean 1-click Connect & Disconnect cards for Strava and Whoop",
                    "Secure Cloud Environment Secrets: Gemini API key, Strava/Whoop client credentials, and biometrics seamlessly loaded from Railway environment variables with alias normalization",
                    "Permanent High-Contrast Dark Theme: Locked-in high-contrast carbon aesthetic optimized for indoor pain caves, OLED displays, and low-light training rooms",
                    "Persistent Weekly Schedule Engine: Custom day-by-day duration rules, progressive wattage ramp warmup/cooldown invariants, and Saturday dedicated rest directives",
                    "Dynamic OAuth Domain Resolution: Intelligent multi-environment redirect host resolution matching active browser domains"
                ]
            },
            {
                "version": "v1.5.1",
                "date": "2026-10-12",
                "title": "Interactive Clickable Profile Graph & Section Power Inspector",
                "items": [
                    "Clickable Interval Profile: Click any section, ramp, or steady bar on the workout canvas to inspect its exact power targets (Watts & % FTP), duration, timeline, and zone",
                    "Spotlight Highlighting: Selected section is emphasized with a glowing border and top target indicator badge, subtly dimming other segments",
                    "Section Power Inspector Card: Detailed telemetry card showing Target Power (scaled to athlete FTP), Duration & Elapsed Timing, Target Cadence (RPM), and Zone metadata",
                    "Keyboard & Step Navigation: Step through sections using ◀ Prev / Next ▶ buttons or Left/Right arrow keys",
                    "Collapsible Section Breakdown Table: View and click through all interval blocks in a structured, sortable overview table"
                ]
            },
            {
                "version": "v1.5.0",
                "date": "2026-10-12",
                "title": "AI Coach Daily Debrief, 3-Day Outlook & GPS Course Maps",
                "items": [
                    "AI Coach Daily Debrief: Evaluates completed workouts against daily Whoop recovery prescriptions and macrocycle targets with Execution Compliance Scoring (0-100%)",
                    "3-Day Forward Outlook: Sports-science projection of recovery zones, workout durations, target TSS, and physiological focuses modeled on acute fatigue decay (tau ~ 3.0 days)",
                    "Tonight's Recovery Directive: Tailored sleep targets (factoring sleep debt), glycogen replenishment guidelines, and hydration protocols for autonomic restoration",
                    "Interactive GPS Route Map: Embedded high-contrast dark route map with Leaflet tiles, glowing course polyline, and start/finish flags for outdoor rides",
                    "Instant Alternative Route Switching: Zero-latency instantaneous switching between alternative outdoor routes with live course map rendering"
                ]
            },
            {
                "version": "v1.4.0",
                "date": "2026-10-12",
                "title": "Outdoor Ride Recommendations & Dual-Load Trailing Strain",
                "items": [
                    "Outdoor Ride Recommender: Analyzes your Strava outdoor ride history and suggests prior routes matching your current Whoop recovery and target time",
                    "On-the-Bike Execution Plan: Power ceiling on climbs (% FTP), cadence focus, and terrain management tailored to your daily readiness",
                    "Dual-Load Modeling: Factors trailing 7-day Whoop strain average and peak strain days (>=14.0) alongside Strava cycling volume",
                    "Mode Switcher: Seamlessly toggle between Indoor Structured Workouts (Zwift/Apple TV) and Outdoor Route Matches",
                    "Direct Strava Link: 1-click route launcher to inspect GPS tracks, elevation profiles, and segments on Strava"
                ]
            },
            {
                "version": "v1.3.1",
                "date": "2026-10-11",
                "title": "Whoop 3-Rings Biometric Display",
                "items": [
                    "All 3 Whoop Rings: Real-time Recovery, Day Strain (0-21.0), and Sleep Performance (%) rings",
                    "Dynamic Zone Reactive Styling: Green, Yellow, and Red zones with signature Whoop cyan and purple accents",
                    "Secondary Biometrics: Real-time HRV rMSSD, Resting Heart Rate, and sleep duration integration"
                ]
            },
            {
                "version": "v1.3.0",
                "date": "2026-10-11",
                "title": "Alternative Workouts & Long-Term Fitness Goals",
                "items": [
                    "Alternative Workouts Generator: Generates 3 daily options (Coach's Choice, Low-Strain Base, 35m Express)",
                    "Interactive Workout Switcher: 1-click option switching updating intervals, profile chart, and Zwift export",
                    "Long-Term Periodization Program: Xert alternative tracking Base/Build/Peak/Taper phases and countdown",
                    "Weekly TSS Compliance & Target FTP: Tracks progress against Strava actual training load and target watts",
                    "Custom Goal Configuration: Set target dates, FTP goals, and weekly TSS in Settings modal"
                ]
            },
            {
                "version": "v1.2.4",
                "date": "2026-10-11",
                "title": "Whoop v2 Sync & Real Biometric Pipeline",
                "items": [
                    "Upgraded Whoop to active v2 endpoints (/v2/recovery, /v2/activity/sleep, /v2/cycle)",
                    "Added high-entropy CSRF state protection for Whoop OAuth",
                    "Added dedicated 'Sync Whoop' manual trigger to dashboard",
                    "Live recovery (50% Yellow), sleep (83%), and strain (15.0) integration"
                ]
            },
            {
                "version": "v1.2.0",
                "date": "2026-10-11",
                "title": "Brand Identity & Strava Integration",
                "items": [
                    "Added custom PowerSync biometric lightning app icon and favicon",
                    "Strava OAuth handshake and activity history synchronization",
                    "Enabled outbound socket support for real-time cloud data polling"
                ]
            },
            {
                "version": "v1.1.0",
                "date": "2026-10-11",
                "title": "Apple TV Zwift Engine",
                "items": [
                    "Engineered 1-click cloud sync to Zwift via free Intervals.icu bridge",
                    "Native .zwo XML file generator with power interval steps",
                    "Real-time interactive Canvas interval profile graph with power zone colors"
                ]
            },
            {
                "version": "v1.0.0",
                "date": "2026-10-11",
                "title": "Initial Architecture",
                "items": [
                    "Anti-Xert high-signal, low-clutter responsive dashboard",
                    "Adaptive Coggan sports-science engine & Gemini AI prompt generator",
                    "SQLite local data layer"
                ]
            }
        ]
    }
