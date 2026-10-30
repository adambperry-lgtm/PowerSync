import os
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
from app.routers import dashboard, workouts, settings, auth, review, plans, chat

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

@app.get("/api/version")
def version_info():
    return {
        "version": "2.3.1",
        "release_name": "Coach Chat 3-Day Forecast Dynamic Adjustment & Evening Workout Timezone Resolution",
        "build_date": "2026-10-29",
        "services": {
            "whoop": "v2 REST API",
            "strava": "v3 REST API",
            "zwift": "Intervals.icu Cloud Bridge",
            "ai_coach":"Google Gemini 3 Flash / 3.8 Flash (Tool Calling)",
            "cloud": "Railway 24/7 + Persistent Volume"
        },
        "changelog": [
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
