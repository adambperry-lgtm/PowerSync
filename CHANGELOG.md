# PowerSync Version History & Changelog

All notable changes to the PowerSync Adaptive Coach & Zwift Sync platform are documented in this file.
From version 2.2.0 forward, this changelog and the in-app version endpoint (`/api/version`) are automatically updated with every meaningful release.

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
