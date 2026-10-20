# PowerSync Repository Guidelines & Agent Instructions

This document provides operational rules and instructions for all AI agents working on the PowerSync codebase.

---

## 1. Version History & Changelog Maintenance (MANDATORY)

Whenever **meaningful updates** (new features, architectural enhancements, bug fixes, or UI improvements) are implemented in this repository, the agent **MUST automatically**:

1. **Update `CHANGELOG.md`**:
   - Follow [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning (SemVer)](https://semver.org/).
   - Document changes under `Added`, `Changed`, `Fixed`, or `Removed`.
   - Update or bump the version number and release date accordingly.

2. **Update the In-App Version API (`app/main.py`)**:
   - In the `@app.get("/api/version")` route (`version_info()` function), update:
     - `version`: e.g. `"2.2.0"`
     - `release_name`: descriptive theme of the release
     - `build_date`: `YYYY-MM-DD`
     - Prepend the new version item to the `changelog` list so the in-app "Version History & Changelog" modal (`#modalChangelog`) stays in sync with `CHANGELOG.md`.

---

## 2. Multi-User Isolation & Session Awareness

- All endpoints in `app/routers/` must resolve `user_id` via `get_current_user_id(request)`.
- All database queries, caches, and storage (`fitness.db`) must be scoped strictly by `user_id`. Never share in-memory state or caches globally across users.

---

## 3. Physiological Science & Workout Generation

- Power calculations must adhere to standard Coggan/Skiba principles ($NP$, $IF$, $TSS = \frac{t \times NP \times IF}{FTP \times 3600} \times 100$).
- 3-Tier strain tracking partitions mechanical work into Low (Aerobic), High (Glycolytic), and Peak (Sprint) strain based on athlete FTP and $W'$.
- Workout generation must respect user recovery, weekly day-by-day duration rules, dedicated rest days, and catalog anti-repetition tracking.
- Daily workout suggestions must align with forward forecasts stored in `coach_forecast_plan` when recovery assumptions hold true.
