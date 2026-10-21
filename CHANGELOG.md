# PowerSync Version History & Changelog

All notable changes to the PowerSync Adaptive Coach & Zwift Sync platform are documented in this file.
From version 2.2.0 forward, this changelog and the in-app version endpoint (`/api/version`) are automatically updated with every meaningful release.

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
