# PowerSync ⚡ — AI Fitness Dashboard & Zwift Bridge

An intelligent, low-cognitive-load endurance dashboard that connects **Whoop** (daily recovery, HRV, sleep, strain) with **Strava** (historical activities, training load, power) and prescribes adaptive workouts sent directly to **Zwift** (optimized for **Apple TV**).

---

## 🎯 Why PowerSync vs. Xert?

Platforms like **Xert** are notoriously data-intensive: athletes are confronted with complex proprietary metrics (Maximal Power Available / MPA, High Intensity Energy / HIE, Focus Duration, Strain score dials) that require constant mental translation and cause "data fatigue."

**PowerSync adopts the opposite philosophy — High Signal, Low Clutter:**
* **Plain-English Coaching Rationale**: Explains *why* today's workout is prescribed based on your autonomic readiness (Whoop) and accumulated muscular fatigue (Strava).
* **Clear Readiness Gauges**: At-a-glance Whoop Recovery % (Green / Yellow / Red), HRV baseline shift, and sleep score.
* **1-Click Zwift Push (Apple TV Compatible)**: Eliminates file transfer headaches.
* **Adaptive Customization**: Adjust duration (30m to 90m) or intensity (-10% to +10%) on the fly, or give a note like *"Legs feel stiff"* to automatically scale the intervals.

---

## 📺 How It Syncs to Zwift on Apple TV

Because Apple TV does not have a user-accessible file system to drop `.zwo` workout files into, Zwift partners with cloud calendar platforms. The industry standard bridge is **Intervals.icu** (completely free):

```
+----------------+      1-Click      +-------------------+      Auto-Sync     +-------------------+
|   PowerSync    | ----------------> |   Intervals.icu   | -----------------> |  Zwift on         |
|  (Local App)   |   Schedules for   |     Calendar      |   Appears under    |  Apple TV         |
|                |       Today       |                   |  "Custom Workouts" |                   |
+----------------+                   +-------------------+                    +-------------------+
```

### 1-Time Setup (Takes ~2 Minutes):
1. Create a free account at [Intervals.icu](https://intervals.icu) if you don't already have one.
2. In Zwift: Go to **Settings -> Connections -> Intervals.icu** and click **Connect**.
3. In Intervals.icu: Go to **Settings -> Developer Settings** and copy your **Athlete ID** and **API Key**.
4. In PowerSync: Open **⚙️ Settings**, paste your Athlete ID & API Key, and click **Save Changes**.

Whenever you click **"🚀 Send to Zwift (Apple TV)"** in PowerSync, today's workout will automatically appear on your Apple TV home screen when you launch Zwift!

*(Note: PowerSync also provides a direct **"💾 Download .zwo"** button if you ever run Zwift on a Mac/PC or want to archive workouts).*

---

## 🚀 Quick Start (Running Locally)

### 1. Launch the Server
From this directory:
```bash
./run.sh
```
Or manually:
```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 2. Open the Dashboard
Open your browser to:
👉 **`http://localhost:8000`**

The dashboard starts in **Demo / Preview Mode** out-of-the-box, allowing you to test:
* Whoop recovery gauges and biometric dials
* Strava workload analytics and activity tables
* AI workout prescription and the interactive canvas interval visualizer
* Zwift `.zwo` downloads and Intervals.icu push

---

## 🔑 Connecting Your Real Accounts

Click **⚙️ Settings** in the top right of the dashboard:

### 1. Whoop Developer API
* Register a free application at the [Whoop Developer Portal](https://developer.whoop.com).
* Set the Redirect URI to `http://localhost:8000/api/auth/whoop/callback`.
* Enter your Client ID & Secret in PowerSync Settings, then click **Connect Whoop via OAuth**.

### 2. Strava API
* Register an app at [Strava Developers](https://www.strava.com/settings/api).
* Set the Authorization Callback Domain to `localhost`.
* Enter your Client ID & Secret in PowerSync Settings, then click **Connect Strava via OAuth**.

### 3. Google Gemini AI (Optional)
* Get an API key from Google AI Studio.
* Paste it into the Gemini API Key field. 
*(If omitted, PowerSync automatically uses its built-in sports-science adaptive algorithm).*

---

## 📁 Project Architecture

```
fitness-dashboard/
├── app/
│   ├── main.py              # FastAPI application & route mounting
│   ├── database.py          # SQLite persistence for metrics, settings, workouts
│   ├── services/
│   │   ├── ai_coach.py      # Gemini AI prompt engine & local adaptive logic
│   │   ├── zwift_service.py # .zwo XML builder & Intervals.icu Apple TV sync
│   │   ├── whoop_service.py # Whoop OAuth and recovery data fetcher
│   │   ├── strava_service.py# Strava OAuth and activity stream fetcher
│   │   └── mock_data.py     # Realistic demo telemetry provider
│   ├── routers/
│   │   ├── dashboard.py     # Aggregated stats endpoint
│   │   ├── workouts.py      # AI generation, interval adjusting, Zwift push
│   │   ├── settings.py      # Config management
│   │   └── auth.py          # OAuth redirect & callback flows
│   └── static/
│       ├── index.html       # Single-page athletic dark UI
│       ├── css/style.css    # Clean modern responsive styling
│       └── js/app.js        # Canvas workout visualizer & dashboard reactivity
├── data/                    # SQLite database storage (fitness.db)
├── run.sh                   # One-click startup script
└── requirements.txt         # Python dependencies
```
