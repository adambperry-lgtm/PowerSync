import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
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
        "version": "1.5.1",
        "release_name": "Clickable Workout Profile & Power Target Inspector",
        "build_date": "2026-10-12",
        "services": {
            "whoop": "v2 REST API",
            "strava": "v3 REST API",
            "zwift": "Intervals.icu Cloud Bridge + .zwo",
            "ai_coach": "Gemini 2.5 Flash / Periodization Engine"
        },
        "changelog": [
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
