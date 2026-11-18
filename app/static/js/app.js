// Standalone web app detection (PWA on iOS / Android)
const clientTz = (typeof Intl !== "undefined" && Intl.DateTimeFormat) ? Intl.DateTimeFormat().resolvedOptions().timeZone : "America/New_York";

if (typeof window !== "undefined") {
  if ((window.navigator && window.navigator.standalone) || (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches)) {
    document.documentElement.classList.add("is-standalone-app");
  }

  // Intercept fetch to automatically attach Authorization header and athlete X-Timezone
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    let [resource, config] = args;
    const token = localStorage.getItem("powersync_token");
    if (typeof resource === "string" && (resource.startsWith("/api") || resource.startsWith("/"))) {
      config = config || {};
      config.headers = config.headers || {};
      if (config.headers instanceof Headers) {
        if (token && !config.headers.has("Authorization")) {
          config.headers.set("Authorization", `Bearer ${token}`);
        }
        if (clientTz && !config.headers.has("X-Timezone")) {
          config.headers.set("X-Timezone", clientTz);
        }
      } else if (Array.isArray(config.headers)) {
        if (token && !config.headers.some(([k]) => k.toLowerCase() === "authorization")) {
          config.headers.push(["Authorization", `Bearer ${token}`]);
        }
        if (clientTz && !config.headers.some(([k]) => k.toLowerCase() === "x-timezone")) {
          config.headers.push(["X-Timezone", clientTz]);
        }
      } else {
        if (token && !config.headers["Authorization"] && !config.headers["authorization"]) {
          config.headers["Authorization"] = `Bearer ${token}`;
        }
        if (clientTz && !config.headers["X-Timezone"] && !config.headers["x-timezone"]) {
          config.headers["X-Timezone"] = clientTz;
        }
      }
    }
    return originalFetch(resource, config);
  };
}

let state = {
  ftp: 250,
  maxHr: 185,
  trainingMode: "indoor", // 'indoor' | 'outdoor'
  currentDuration: 60,
  currentIntensity: 0,
  currentWorkout: null,
  workoutOptions: [],
  activeOptionId: "workout_primary",
  selectedIntervalIndex: null, // Interactive interval inspector
  currentOutdoorRide: null,
  outdoorOptions: [],
  activeOutdoorId: null,
  outdoorDuration: 60,
  program: null,
  dashboard: null
};

// DOM References
const gaugeValCircle = document.getElementById("gaugeValCircle");
const gaugeRecoveryNum = document.getElementById("gaugeRecoveryNum");
const valHrv = document.getElementById("valHrv");
const valRhr = document.getElementById("valRhr");
const valSleep = document.getElementById("valSleep");
const valStrain = document.getElementById("valStrain");
const valWeeklyHours = document.getElementById("valWeeklyHours");
const valWeeklyDist = document.getElementById("valWeeklyDist");
const valWeeklyElev = document.getElementById("valWeeklyElev");
const valWeeklyTss = document.getElementById("valWeeklyTss");
const formStatusBadge = document.getElementById("formStatusBadge");
const formDesc = document.getElementById("formDesc");
const valFtpDisplay = document.getElementById("valFtpDisplay");
const valMaxHrDisplay = document.getElementById("valMaxHrDisplay");
const rangeZ1 = document.getElementById("rangeZ1");
const rangeZ2 = document.getElementById("rangeZ2");
const rangeZ3 = document.getElementById("rangeZ3");
const rangeSweetSpot = document.getElementById("rangeSweetSpot");
const rangeZ4 = document.getElementById("rangeZ4");
const rangeZ5 = document.getElementById("rangeZ5");
const rangeVO2 = document.getElementById("rangeVO2");
const rangeZ6 = document.getElementById("rangeZ6");
const rangeZ7 = document.getElementById("rangeZ7");
const recentActivitiesBody = document.getElementById("recentActivitiesBody");

// Mode Switcher DOM
const tabModeIndoor = document.getElementById("tabModeIndoor");
const tabModeOutdoor = document.getElementById("tabModeOutdoor");
const modeSubtext = document.getElementById("modeSubtext");
const indoorContainer = document.getElementById("indoorContainer");
const outdoorContainer = document.getElementById("outdoorContainer");

// Indoor Workout DOM
const workoutTitle = document.getElementById("workoutTitle");
const workoutFocus = document.getElementById("workoutFocus");
const workoutDurationBadge = document.getElementById("workoutDurationBadge");
const workoutTssBadge = document.getElementById("workoutTssBadge");
const workoutRationale = document.getElementById("workoutRationale");
const intervalCanvas = document.getElementById("intervalCanvas");
const inputUserNote = null;
const btnRegenerateWorkout = null;
const btnPushZwift = document.getElementById("btnPushZwift");
const durPillGroup = document.getElementById("durPillGroup");
const intensityPillGroup = document.getElementById("intensityPillGroup");
const workoutOptionsGrid = document.getElementById("workoutOptionsGrid");
const intervalTooltip = document.getElementById("intervalTooltip");
const intervalInspector = document.getElementById("intervalInspector");
const btnToggleSectionTable = document.getElementById("btnToggleSectionTable");
const sectionTableContainer = document.getElementById("sectionTableContainer");
const sectionTableBody = document.getElementById("sectionTableBody");
const inspTotalSectionsCount = document.getElementById("inspTotalSectionsCount");

// Outdoor Ride Recommendation DOM
const outdoorTitle = document.getElementById("outdoorTitle");
const outdoorZoneBadge = document.getElementById("outdoorZoneBadge");
const outdoorDurationBadge = document.getElementById("outdoorDurationBadge");
const outdoorDistBadge = document.getElementById("outdoorDistBadge");
const outdoorElevBadge = document.getElementById("outdoorElevBadge");
const outdoorRationale = document.getElementById("outdoorRationale");
const outdoorStatTime = document.getElementById("outdoorStatTime");
const outdoorStatDate = document.getElementById("outdoorStatDate");
const outdoorStatDist = document.getElementById("outdoorStatDist");
const outdoorStatMiles = document.getElementById("outdoorStatMiles");
const outdoorStatElev = document.getElementById("outdoorStatElev");
const outdoorStatGradient = document.getElementById("outdoorStatGradient");
const outdoorStatWatts = document.getElementById("outdoorStatWatts");
const outdoorStatPctFtp = document.getElementById("outdoorStatPctFtp");
const outdoorStatSuffer = document.getElementById("outdoorStatSuffer");
const outdoorStatMatch = document.getElementById("outdoorStatMatch");
const outdoorTipsGrid = document.getElementById("outdoorTipsGrid");
const outdoorDurPillGroup = document.getElementById("outdoorDurPillGroup");
const inputOutdoorUserNote = document.getElementById("inputOutdoorUserNote");
const btnRegenerateOutdoor = document.getElementById("btnRegenerateOutdoor");
const btnRematchOutdoor = document.getElementById("btnRematchOutdoor");
const btnOpenStrava = document.getElementById("btnOpenStrava");
const outdoorOptionsGrid = document.getElementById("outdoorOptionsGrid");

// Program DOM
const btnAdjustGoal = document.getElementById("btnAdjustGoal");
const programGoalTitle = document.getElementById("programGoalTitle");
const programPhaseBadge = document.getElementById("programPhaseBadge");
const programGoalDesc = document.getElementById("programGoalDesc");
const macrocycleFillBar = document.getElementById("macrocycleFillBar");
const programWeekInfo = document.getElementById("programWeekInfo");
const programDaysInfo = document.getElementById("programDaysInfo");
const programFtpDelta = document.getElementById("programFtpDelta");
const programTargetFtpVal = document.getElementById("programTargetFtpVal");
const programCurrentFtpVal = document.getElementById("programCurrentFtpVal");
const programCompliancePct = document.getElementById("programCompliancePct");
const programWeeklyTssActual = document.getElementById("programWeeklyTssActual");
const programWeeklyTssTarget = document.getElementById("programWeeklyTssTarget");
const programWeeklyXssActual = document.getElementById("programWeeklyXssActual");
const programWeeklyXssTarget = document.getElementById("programWeeklyXssTarget");
const programXssCompliancePct = document.getElementById("programXssCompliancePct");
const programFocusDurationBadge = document.getElementById("programFocusDurationBadge");
const programTssMeterFill = document.getElementById("programTssMeterFill");
const programPhaseFocus = document.getElementById("programPhaseFocus");
const programPhaseDetail = document.getElementById("programPhaseDetail");

// Settings Modal DOM
const settingsModal = document.getElementById("settingsModal");
const btnOpenSettings = document.getElementById("btnOpenSettings");
const btnCloseSettings = document.getElementById("btnCloseSettings");
const btnCancelSettings = document.getElementById("btnCancelSettings");
const btnSaveSettings = document.getElementById("btnSaveSettings");
const bannerToast = document.getElementById("bannerToast");

// Helper: Show Toast
function showToast(message, duration = 4000) {
  bannerToast.textContent = message;
  bannerToast.style.display = "block";
  setTimeout(() => {
    bannerToast.style.display = "none";
  }, duration);
}

// 1. Fetch Dashboard Data
async function loadDashboard() {
  const isAuthUser = Boolean(currentAthleteUser && !currentAthleteUser.is_guest);
  if (!isAuthUser) {
    applyAuthVisibility(false);
    return;
  }
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.authenticated === false || (data.user && data.user.is_guest)) {
      applyAuthVisibility(false);
      return;
    }
    applyAuthVisibility(true);
    state.dashboard = data;
    state.whoop = data.whoop;
    state.strava = data.strava;
    state.wyzeScale = data.wyze_scale || null;
    state.dayConfig = data.day_config;
    state.coachingPreferences = data.coaching_preferences;
    state.ftp = data.athlete.ftp || 250;
    state.maxHr = data.athlete.max_hr || 185;
    state.athleteWPrime = data.athlete.w_prime_kj !== undefined ? data.athlete.w_prime_kj : 20.0;
    state.athletePeakPower = data.athlete.peak_power_watts !== undefined ? data.athlete.peak_power_watts : 1050;
    state.weightKg = data.athlete.weight_kg || 70.0;
    state.weightLbs = data.athlete.weight_lbs || Number((state.weightKg * 2.20462262185).toFixed(1));
    state.ftpWkg = data.athlete.ftp_w_kg || Number((state.ftp / Math.max(30, state.weightKg)).toFixed(2));
    state.trailingStrain = data.whoop ? (data.whoop.trailing_7d_strain_avg || data.whoop.day_strain) : null;

    if (data.program) {
      renderProgram(data.program);
    }
    renderWhoop(data.whoop);
    renderStrava(data.strava);
    renderAthleteProfile();
    state.ftpTestReadiness = data.ftp_test_readiness || null;
    if (typeof renderFtpTestReadiness === "function") {
      renderFtpTestReadiness(state.ftpTestReadiness);
    }
    renderIntegrations(data.integrations);
    renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
    if (data.power_spiderweb) {
      renderPowerSpiderweb(data.power_spiderweb);
    } else {
      loadPowerSpiderweb("30d");
    }
    loadDebrief();
    updateCoachChatTelemetryChips();

    // Auto-sync Whoop if connected and today's metrics are missing or >60s elapsed
    if (data.integrations && data.integrations.whoop && data.integrations.whoop.connected) {
      const needsSync = !data.whoop || !data.whoop.is_today || (Date.now() - (state.lastWhoopAutoSyncTime || 0)) > 60000;
      if (needsSync && !state.isAutoSyncingWhoop) {
        state.isAutoSyncingWhoop = true;
        state.lastWhoopAutoSyncTime = Date.now();
        fetch("/api/auth/sync/whoop", { method: "POST" })
          .then(r => r.ok ? r.json() : null)
          .then(syncData => {
            state.isAutoSyncingWhoop = false;
            if (syncData && syncData.success) {
              return fetch("/api/dashboard").then(r => r.json());
            }
          })
          .then(freshData => {
            if (freshData && freshData.whoop) {
              state.whoop = freshData.whoop;
              renderWhoop(freshData.whoop);
              updateCoachChatTelemetryChips();
            }
          })
          .catch(syncErr => {
            state.isAutoSyncingWhoop = false;
            console.warn("Background Whoop sync error:", syncErr);
          });
      }
    }

    // Auto-sync Strava if connected and >60s elapsed
    if (data.integrations && data.integrations.strava && data.integrations.strava.connected) {
      const needsStravaSync = (Date.now() - (state.lastStravaAutoSyncTime || 0)) > 60000;
      if (needsStravaSync && !state.isAutoSyncingStrava) {
        state.isAutoSyncingStrava = true;
        state.lastStravaAutoSyncTime = Date.now();
        fetch("/api/auth/sync/strava", { method: "POST" })
          .then(r => r.ok ? r.json() : null)
          .then(syncData => {
            state.isAutoSyncingStrava = false;
            if (syncData && syncData.success && syncData.count > 0) {
              return fetch("/api/dashboard").then(r => r.json());
            }
          })
          .then(freshData => {
            if (freshData && freshData.strava) {
              state.strava = freshData.strava;
              renderStrava(freshData.strava);
              if (typeof loadDebrief === "function") {
                loadDebrief();
              }
            }
          })
          .catch(syncErr => {
            state.isAutoSyncingStrava = false;
            console.warn("Background Strava sync error:", syncErr);
          });
      }
    }
  } catch (err) {
    console.error("Failed to load dashboard:", err);
  }
}

// Render Whoop 3-Rings Biometrics (Tri-Ring & Concentric)
function renderWhoop(whoop) {
  if (!whoop) return;
  state.whoop = whoop;
  updateCoachChatTelemetryChips();
  const score = Math.round(Number(whoop.recovery_score) || 0);
  const strain = Number(whoop.day_strain) || 0;
  const sleep = Math.round(Number(whoop.sleep_performance) || 0);
  const sleepHours = Number(whoop.sleep_duration_hours) || 0;

  // Dynamic Zone Color for Recovery
  let recColor = "#10b981"; // green
  let zoneText = "Green Zone (Prime)";
  if (score < 34) {
    recColor = "#f43f5e"; // red
    zoneText = "Red Zone (Fatigued)";
  } else if (score <= 66) {
    recColor = "#f59e0b"; // yellow
    zoneText = "Yellow Zone (Moderate)";
  }

  // 1. Tri-Ring Elements (r=38, circumference = 2 * PI * 38 = 238.76)
  const cTri = 238.76;
  
  // Recovery Ring
  const recOffset = cTri - (score / 100) * cTri;
  const gaugeValCircle = document.getElementById("gaugeValCircle");
  if (gaugeValCircle) {
    gaugeValCircle.style.strokeDasharray = cTri;
    gaugeValCircle.style.strokeDashoffset = recOffset;
    gaugeValCircle.style.stroke = recColor;
  }
  const gaugeRecoveryNum = document.getElementById("gaugeRecoveryNum");
  if (gaugeRecoveryNum) {
    gaugeRecoveryNum.textContent = `${score}%`;
    gaugeRecoveryNum.style.color = recColor;
  }
  const ringTitleRec = document.getElementById("ringTitleRecovery");
  if (ringTitleRec) ringTitleRec.style.color = recColor;
  const ringDetailRec = document.getElementById("ringDetailRecovery");
  if (ringDetailRec) ringDetailRec.textContent = zoneText.split(" ")[0] + " Zone";

  // Strain Ring (0 to 21.0 scale)
  const strainOffset = cTri - Math.min(1.0, strain / 21.0) * cTri;
  const gaugeStrainCircle = document.getElementById("gaugeStrainCircle");
  if (gaugeStrainCircle) {
    gaugeStrainCircle.style.strokeDasharray = cTri;
    gaugeStrainCircle.style.strokeDashoffset = strainOffset;
  }
  const gaugeStrainNum = document.getElementById("gaugeStrainNum");
  if (gaugeStrainNum) {
    gaugeStrainNum.textContent = strain.toFixed(1);
  }
  const ringDetailStrain = document.getElementById("ringDetailStrain");
  if (ringDetailStrain) {
    if (whoop.trailing_7d_strain_avg) {
      ringDetailStrain.textContent = `7D Avg: ${Number(whoop.trailing_7d_strain_avg).toFixed(1)}`;
    } else {
      ringDetailStrain.textContent = `/ 21.0 Max`;
    }
  }

  // Sleep Ring (0 to 100%)
  const sleepOffset = cTri - (sleep / 100) * cTri;
  const gaugeSleepCircle = document.getElementById("gaugeSleepCircle");
  if (gaugeSleepCircle) {
    gaugeSleepCircle.style.strokeDasharray = cTri;
    gaugeSleepCircle.style.strokeDashoffset = sleepOffset;
  }
  const gaugeSleepNum = document.getElementById("gaugeSleepNum");
  if (gaugeSleepNum) {
    gaugeSleepNum.textContent = `${sleep}%`;
  }
  const ringDetailSleep = document.getElementById("ringDetailSleep");
  if (ringDetailSleep) {
    ringDetailSleep.textContent = sleepHours > 0 ? `${sleepHours.toFixed(1)} hrs` : `${sleep}% score`;
  }

  // 2. Sub-strip Telemetry
  const hrvNum = Number(whoop.hrv_rmssd);
  const hrvStr = !isNaN(hrvNum) && hrvNum > 0 ? `${hrvNum.toFixed(1)} ms` : "--";
  if (valHrv) valHrv.innerHTML = `${hrvStr} <span style="color:${recColor};font-size:0.75rem;">(${whoop.trends?.hrv_vs_baseline || 'Live'})</span>`;
  if (valRhr) valRhr.textContent = `${whoop.resting_heart_rate || '--'} bpm`;
  if (valSleep) valSleep.textContent = `${sleep}% (${sleepHours.toFixed(1)} hrs)`;
  if (valStrain) valStrain.textContent = `${strain.toFixed(1)} / 21`;

  const valYesterdayStrain = document.getElementById("valYesterdayStrain");
  if (valYesterdayStrain) {
    if (whoop.yesterday_strain !== undefined && whoop.yesterday_strain !== null) {
      valYesterdayStrain.textContent = `${Number(whoop.yesterday_strain).toFixed(1)}`;
    } else {
      valYesterdayStrain.textContent = "--";
    }
  }

  const valTrailingStrain = document.getElementById("valTrailingStrain");
  if (valTrailingStrain) {
    const weighted = whoop.recent_weighted_strain ? Number(whoop.recent_weighted_strain).toFixed(1) : (whoop.trailing_7d_strain_avg ? Number(whoop.trailing_7d_strain_avg).toFixed(1) : "--");
    const avg = whoop.trailing_7d_strain_avg ? Number(whoop.trailing_7d_strain_avg).toFixed(1) : "--";
    valTrailingStrain.innerHTML = `${weighted} <span style="font-size:0.7rem;color:var(--text-secondary);font-weight:500;" title="7-Day Unweighted Average: ${avg}">(${avg} avg)</span>`;
  }

  // Update Collapsed Whoop Summary Chips
  const collapsedWhoopRec = document.getElementById("collapsedWhoopRecovery");
  if (collapsedWhoopRec) {
    collapsedWhoopRec.textContent = `Recovery: ${score}%`;
    collapsedWhoopRec.style.color = recColor;
  }
  const collapsedWhoopStrain = document.getElementById("collapsedWhoopStrain");
  if (collapsedWhoopStrain) {
    collapsedWhoopStrain.textContent = `Strain: ${strain.toFixed(1)}`;
  }
  const collapsedWhoopSleep = document.getElementById("collapsedWhoopSleep");
  if (collapsedWhoopSleep) {
    collapsedWhoopSleep.textContent = `Sleep: ${sleep}%`;
  }
  const collapsedWhoopHrv = document.getElementById("collapsedWhoopHrv");
  if (collapsedWhoopHrv) {
    collapsedWhoopHrv.textContent = `HRV: ${hrvStr}`;
  }

  const whoopDateBadge = document.getElementById("whoopDateBadge");
  if (whoopDateBadge) {
    if (whoop.auth_expired) {
      whoopDateBadge.textContent = "⚠️ Reconnect Whoop";
      whoopDateBadge.style.background = "rgba(244, 63, 94, 0.2)";
      whoopDateBadge.style.color = "#f43f5e";
      whoopDateBadge.style.cursor = "pointer";
      whoopDateBadge.onclick = openSettingsModal;
    } else if (whoop.is_today) {
      whoopDateBadge.textContent = "Today";
      whoopDateBadge.style.background = "rgba(16, 185, 129, 0.15)";
      whoopDateBadge.style.color = "#10b981";
      whoopDateBadge.onclick = null;
      whoopDateBadge.title = "Synced Today with Whoop.";
    } else if (whoop.date) {
      whoopDateBadge.textContent = `${whoop.date} (Synced)`;
      whoopDateBadge.style.background = "rgba(16, 185, 129, 0.15)";
      whoopDateBadge.style.color = "#10b981";
      whoopDateBadge.title = "Displaying latest synced Whoop biometrics.";
      whoopDateBadge.onclick = null;
    }
  }
}

// Render Strava Workload
function renderStrava(strava) {
  if (!strava) return;
  const ws = strava.weekly_stats || {};
  valWeeklyHours.textContent = `${ws.total_hours || 0} hrs`;
  const totalMi = ws.total_distance_miles || (ws.total_distance_km ? (ws.total_distance_km * 0.621371).toFixed(1) : "0.0");
  valWeeklyDist.textContent = `${totalMi} mi`;
  const totalFt = ws.total_elevation_ft || (ws.total_elevation_m ? Math.round(ws.total_elevation_m * 3.28084) : 0);
  valWeeklyElev.textContent = `${totalFt.toLocaleString()} ft`;
  if (ws.total_xss) {
    valWeeklyTss.innerHTML = `${ws.total_tss || 0} <span style="font-size:0.75rem;color:#a78bfa;font-weight:600;">(~${ws.total_xss} XSS)</span>`;
  } else {
    valWeeklyTss.textContent = `${ws.total_tss || 0}`;
  }

  const valAcuteTss = document.getElementById("valAcuteTss");
  if (valAcuteTss) {
    valAcuteTss.textContent = `${ws.acute_weighted_tss || ws.total_tss || 0}`;
  }
  const valYesterdayTss = document.getElementById("valYesterdayTss");
  if (valYesterdayTss) {
    valYesterdayTss.textContent = `${ws.yesterday_tss || 0}`;
  }
  const valLoadProfileBadge = document.getElementById("valLoadProfileBadge");
  if (valLoadProfileBadge && ws.load_profile) {
    valLoadProfileBadge.textContent = ws.load_profile;
    if (ws.load_profile.includes("Surge")) {
      valLoadProfileBadge.style.color = "var(--accent-amber)";
    } else if (ws.load_profile.includes("Front-Loaded")) {
      valLoadProfileBadge.style.color = "var(--accent-green)";
    } else {
      valLoadProfileBadge.style.color = "var(--accent-cyan)";
    }
  }

  if (ws.form_status) {
    formStatusBadge.textContent = ws.form_status;
    formStatusBadge.title = ws.form_status;
  }
  if (ws.form_description) {
    formDesc.textContent = ws.form_description;
  }

  // Update Collapsed Strava Summary Chips
  const collapsedStravaHours = document.getElementById("collapsedStravaHours");
  if (collapsedStravaHours) collapsedStravaHours.textContent = `${ws.total_hours || 0} hrs`;
  const collapsedStravaDist = document.getElementById("collapsedStravaDist");
  if (collapsedStravaDist) collapsedStravaDist.textContent = `${totalMi} mi`;
  const collapsedStravaTss = document.getElementById("collapsedStravaTss");
  if (collapsedStravaTss) collapsedStravaTss.textContent = `${ws.total_tss || 0} TSS`;
  const collapsedStravaForm = document.getElementById("collapsedStravaForm");
  if (collapsedStravaForm && ws.form_status) collapsedStravaForm.textContent = ws.form_status;

  // Populate Activities Table
  const acts = strava.recent_activities || [];
  if (acts.length === 0) {
    recentActivitiesBody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);">No recent activities found.</td></tr>`;
    return;
  }

  recentActivitiesBody.innerHTML = acts.map(a => {
    const durMin = Math.round((a.moving_time_sec || 0) / 60);
    const durStr = durMin >= 60 ? `${Math.floor(durMin / 60)}h ${durMin % 60}m` : `${durMin}m`;
    const distMiles = a.distance_miles ? a.distance_miles.toFixed(1) : ((a.distance_meters || 0) * 0.000621371).toFixed(1);
    const dateStr = a.start_date ? a.start_date.substring(0, 10) : "";
    const xssVal = a.total_xss !== undefined ? Math.round(a.total_xss) : Math.round(a.suffer_score || 0);
    const tssVal = Math.round(a.suffer_score || 0);
    const lowXss = a.low_xss !== undefined ? Math.round(a.low_xss) : Math.round(xssVal * 0.8);
    const highXss = a.high_xss !== undefined ? Math.round(a.high_xss) : Math.round(xssVal * 0.2);
    const focusDuration = a.focus_duration || (a.sport_type === 'Ride' ? 'Endurance / Century (>1h Focus)' : 'Cardio');
    
    return `
      <tr>
        <td style="color:var(--text-muted);white-space:nowrap;">${dateStr}</td>
        <td style="font-weight:600;">${a.name}</td>
        <td><span class="badge-status" style="font-size:0.7rem;padding:0.15rem 0.4rem;">${a.sport_type}</span></td>
        <td style="white-space:nowrap;">${durStr}</td>
        <td style="white-space:nowrap;">${distMiles} mi</td>
        <td style="font-weight:600;color:var(--accent-cyan);white-space:nowrap;">${Math.round(a.weighted_average_watts || a.average_watts || 0)} W</td>
        <td style="white-space:nowrap;">${Math.round(a.average_heartrate || 0)} bpm</td>
        <td>
          <div style="display:flex;flex-direction:column;gap:2px;">
            <div style="display:flex;align-items:center;gap:4px;white-space:nowrap;">
              <span style="color:#a78bfa;font-weight:700;">⚡ ${xssVal} XSS</span>
              <span style="font-size:0.75rem;color:var(--text-muted);font-weight:500;">(~${tssVal} TSS)</span>
            </div>
            <div style="font-size:0.7rem;color:var(--text-secondary);white-space:nowrap;">
              <span style="color:#10b981;">${lowXss}L</span> • <span style="color:#f59e0b;">${highXss}H</span>
            </div>
          </div>
        </td>
        <td>
          <span class="badge-status" style="font-size:0.7rem;padding:0.15rem 0.4rem;background:rgba(6,182,212,0.12);color:#06b6d4;border-color:rgba(6,182,212,0.25);white-space:nowrap;">
            ${focusDuration}
          </span>
        </td>
      </tr>
    `;
  }).join("");

  // Update collapsed summary for recent workouts
  if (acts.length > 0) {
    const latest = acts[0];
    const latestDurMin = Math.round((latest.moving_time_sec || 0) / 60);
    const latestDurStr = latestDurMin >= 60 ? `${Math.floor(latestDurMin / 60)}h ${latestDurMin % 60}m` : `${latestDurMin}m`;
    const latestTss = Math.round(latest.suffer_score || latest.total_xss || 0);

    const collapsedRecentTitle = document.getElementById("collapsedRecentTitle");
    if (collapsedRecentTitle) collapsedRecentTitle.textContent = latest.name || "Latest Workout";
    const collapsedRecentSport = document.getElementById("collapsedRecentSport");
    if (collapsedRecentSport) collapsedRecentSport.textContent = latest.sport_type || "Ride";
    const collapsedRecentDur = document.getElementById("collapsedRecentDur");
    if (collapsedRecentDur) collapsedRecentDur.textContent = latestDurStr;
    const collapsedRecentTss = document.getElementById("collapsedRecentTss");
    if (collapsedRecentTss) collapsedRecentTss.textContent = `${latestTss} TSS`;
  }
}

// Render Athlete Profile
function renderAthleteProfile() {
  valFtpDisplay.innerHTML = `${state.ftp} <span style="font-size:1.1rem;color:var(--text-secondary);font-weight:600;">W</span>`;
  valMaxHrDisplay.innerHTML = `${state.maxHr} <span style="font-size:0.9rem;color:var(--text-muted);">BPM</span>`;

  const ftp = state.ftp || 250;
  const peak = state.athletePeakPower || 1050;
  const weightKg = state.weightKg || 70.0;
  const weightLbs = state.weightLbs || Number((weightKg * 2.20462262185).toFixed(1));
  const ftpWkg = (ftp / Math.max(30, weightKg)).toFixed(2);

  const valFtpWkgSub = document.getElementById("valFtpWkgSub");
  if (valFtpWkgSub) {
    valFtpWkgSub.textContent = `${ftpWkg} W/kg`;
  }

  const valWeightLbsEl = document.getElementById("valWeightLbsDisplay");
  if (valWeightLbsEl) {
    valWeightLbsEl.innerHTML = `${Number(weightLbs).toFixed(1)} <span style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">lbs</span>`;
  }

  const lblWeightTitle = document.getElementById("lblWeightMetricTitle");
  const valWeightSubEl = document.getElementById("valWeightSubDisplay");
  const latestWyze = state.wyzeScale && state.wyzeScale.latest ? state.wyzeScale.latest : null;
  if (lblWeightTitle) {
    lblWeightTitle.textContent = (state.wyzeScale && state.wyzeScale.connected) || latestWyze
      ? "BODY WEIGHT (WYZE)"
      : "BODY WEIGHT (LBS)";
  }
  if (valWeightSubEl) {
    const subParts = [];
    if (latestWyze && latestWyze.body_fat_pct !== null && latestWyze.body_fat_pct !== undefined) {
      subParts.push(`${Number(latestWyze.body_fat_pct).toFixed(1)}% BF`);
    }
    if (latestWyze && latestWyze.muscle_mass_lbs !== null && latestWyze.muscle_mass_lbs !== undefined) {
      subParts.push(`${Number(latestWyze.muscle_mass_lbs).toFixed(1)} lb muscle`);
    }
    if (subParts.length === 0) {
      subParts.push(`Power ref: ${Number(weightKg).toFixed(1)} kg`);
    }
    valWeightSubEl.textContent = subParts.join(" • ");
  }

  const valWPrimeEl = document.getElementById("valWPrimeDisplay");
  if (valWPrimeEl) {
    valWPrimeEl.innerHTML = `${state.athleteWPrime !== undefined ? state.athleteWPrime : 20.0} <span style="font-size:1rem;color:var(--text-secondary);font-weight:600;">kJ</span>`;
  }
  const valPeakPowerEl = document.getElementById("valPeakPowerDisplay");
  if (valPeakPowerEl) {
    valPeakPowerEl.innerHTML = `${state.athletePeakPower !== undefined ? state.athletePeakPower : 1050} <span style="font-size:1rem;color:var(--text-secondary);font-weight:600;">W</span>`;
  }

  const elZ1 = document.getElementById("rangeZ1");
  if (elZ1) elZ1.textContent = `< ${Math.round(ftp * 0.55)} W`;

  const elZ2 = document.getElementById("rangeZ2");
  if (elZ2) elZ2.textContent = `${Math.round(ftp * 0.56)} – ${Math.round(ftp * 0.75)} W`;

  const elZ3 = document.getElementById("rangeZ3");
  if (elZ3) elZ3.textContent = `${Math.round(ftp * 0.76)} – ${Math.round(ftp * 0.90)} W`;

  const elSS = document.getElementById("rangeSweetSpot");
  if (elSS) elSS.textContent = `${Math.round(ftp * 0.88)} – ${Math.round(ftp * 0.94)} W`;

  const elZ4 = document.getElementById("rangeZ4");
  if (elZ4) elZ4.textContent = `${Math.round(ftp * 0.91)} – ${Math.round(ftp * 1.05)} W`;

  const elZ5 = document.getElementById("rangeZ5") || document.getElementById("rangeVO2");
  if (elZ5) elZ5.textContent = `${Math.round(ftp * 1.06)} – ${Math.round(ftp * 1.20)} W`;

  const elZ6 = document.getElementById("rangeZ6");
  if (elZ6) elZ6.textContent = `${Math.round(ftp * 1.21)} – ${Math.round(ftp * 1.50)} W`;

  const elZ7 = document.getElementById("rangeZ7");
  if (elZ7) elZ7.textContent = `> ${Math.round(ftp * 1.50)} W (${peak} W)`;

  // Update collapsed summary for athlete profile
  const collapsedFtp = document.getElementById("collapsedAthleteFtp");
  if (collapsedFtp) collapsedFtp.textContent = `FTP: ${state.ftp}W (${ftpWkg} W/kg)`;
  const collapsedWeight = document.getElementById("collapsedAthleteWeight");
  if (collapsedWeight) collapsedWeight.textContent = `Weight: ${Number(weightLbs).toFixed(1)} lbs`;
  const collapsedWPrime = document.getElementById("collapsedAthleteWPrime");
  if (collapsedWPrime) collapsedWPrime.textContent = `W': ${state.athleteWPrime !== undefined ? state.athleteWPrime : 20.0} kJ`;
  const collapsedMaxHr = document.getElementById("collapsedAthleteMaxHr");
  if (collapsedMaxHr) collapsedMaxHr.textContent = `Max HR: ${state.maxHr} bpm`;
}

function renderFtpTestReadiness(r) {
  const panel = document.getElementById("ftpTestAdvisorPanel");
  const dailyBanner = document.getElementById("dailyFtpTestBanner");
  if (!r) {
    if (panel) panel.style.display = "none";
    if (dailyBanner) dailyBanner.style.display = "none";
    return;
  }
  if (panel) panel.style.display = "block";

  const statusBadge = document.getElementById("ftpTestStatusBadge");
  const scoreChip = document.getElementById("ftpTestScoreChip");
  const headlineEl = document.getElementById("ftpTestHeadline");
  const rationaleEl = document.getElementById("ftpTestRationale");
  const bestWindowEl = document.getElementById("ftpTestBestWindow");
  const protoEl = document.getElementById("ftpTestProtocolLabel");
  const eftpEl = document.getElementById("ftpTestEftpSignal");
  const lastTestEl = document.getElementById("ftpTestLastTested");
  const pillarsGrid = document.getElementById("ftpTestPillarsGrid");

  const statusColors = {
    PRIME_NOW: { bg: "rgba(0,200,150,0.14)", color: "#00A87E", border: "rgba(0,200,150,0.4)" },
    SOON: { bg: "rgba(0,82,255,0.12)", color: "#0052FF", border: "rgba(0,82,255,0.35)" },
    HOLD: { bg: "rgba(245,158,11,0.14)", color: "#D97706", border: "rgba(245,158,11,0.4)" },
    DEFER_EVENT: { bg: "rgba(100,116,139,0.14)", color: "#475569", border: "rgba(100,116,139,0.35)" },
    DEFER_RECENT: { bg: "rgba(16,185,129,0.12)", color: "#059669", border: "rgba(16,185,129,0.35)" }
  };
  const sc = statusColors[r.status] || statusColors.HOLD;
  if (statusBadge) {
    statusBadge.textContent = r.status_label || r.status;
    statusBadge.style.background = sc.bg;
    statusBadge.style.color = sc.color;
    statusBadge.style.borderColor = sc.border;
  }
  if (scoreChip) scoreChip.textContent = `${r.readiness_score ?? "--"}/100`;
  if (headlineEl) headlineEl.textContent = r.headline || "";
  if (rationaleEl) rationaleEl.textContent = r.rationale || "";
  if (bestWindowEl) bestWindowEl.textContent = r.recommended_window_label || "--";
  if (protoEl) protoEl.textContent = r.recommended_protocol_label || "--";
  if (eftpEl) {
    eftpEl.textContent = r.has_breakthrough
      ? `~${r.estimated_ftp}W (+${r.eftp_delta_watts}W)`
      : `${r.current_ftp}W (Aligned)`;
    eftpEl.style.color = r.has_breakthrough ? "#FF5E00" : "inherit";
  }
  if (lastTestEl) {
    lastTestEl.textContent = r.days_since_last_test !== null && r.days_since_last_test !== undefined
      ? `${r.days_since_last_test}d ago`
      : "Not recorded";
  }

  if (pillarsGrid && r.pillars) {
    const pMeta = [
      { key: "block_timing", label: "Block Timing" },
      { key: "progress_signal", label: "Progress / eFTP" },
      { key: "physiological_readiness", label: "Whoop Readiness" },
      { key: "fatigue_clearance", label: "Fatigue Clearance" }
    ];
    pillarsGrid.innerHTML = pMeta.map(m => {
      const p = r.pillars[m.key] || { score: 0, max: 25, note: "" };
      const pct = Math.min(100, Math.round((p.score / Math.max(1, p.max)) * 100));
      const barColor = pct >= 75 ? "#00C896" : (pct >= 50 ? "#0052FF" : "#F59E0B");
      return `
        <div title="${(p.note || "").replace(/"/g, "&quot;")}" style="background:#fff;border:1px solid var(--border-color);border-radius:8px;padding:0.45rem 0.6rem;">
          <div style="display:flex;justify-content:space-between;font-size:0.7rem;font-weight:700;color:var(--text-secondary);margin-bottom:0.25rem;">
            <span>${m.label}</span>
            <span style="color:${barColor};">${p.score}/${p.max}</span>
          </div>
          <div style="height:5px;border-radius:999px;background:rgba(17,22,37,0.08);overflow:hidden;">
            <div style="height:100%;width:${pct}%;background:${barColor};border-radius:999px;"></div>
          </div>
        </div>
      `;
    }).join("");
  }

  // Daily Prime FTP Test Banner
  if (dailyBanner) {
    if (r.status === "PRIME_NOW") {
      dailyBanner.style.display = "flex";
      const dHead = document.getElementById("dailyFtpTestHeadline");
      const dSub = document.getElementById("dailyFtpTestSub");
      if (dHead) dHead.textContent = r.headline || "Prime Window: Ready for an FTP Test Today";
      if (dSub) dSub.textContent = `Score ${r.readiness_score}/100 • Recommended: ${r.recommended_protocol_label}`;
    } else {
      dailyBanner.style.display = "none";
    }
  }
}

async function launchRecommendedFtpTest() {
  const r = state.ftpTestReadiness;
  const proto = r && r.recommended_protocol === "ramp_test" ? "ramp test" : "ftp test";
  const dur = (r && r.recommended_duration_min) ? r.recommended_duration_min : (proto === "ramp test" ? 38 : 55);
  const tabDaily = document.getElementById("tabMainViewDaily");
  if (tabDaily) tabDaily.click();
  if (typeof loadWorkout === "function") {
    await loadWorkout(dur, 0, proto);
  }
}

async function recordFtpTestResultFlow() {
  const currentFtp = state.ftp || 250;
  const r = state.ftpTestReadiness;
  const suggested = (r && r.has_breakthrough && r.estimated_ftp > currentFtp) ? r.estimated_ftp : currentFtp;
  const raw = window.prompt(`Enter your new tested FTP in Watts (current: ${currentFtp}W):`, String(suggested));
  if (raw === null) return;
  const parsed = parseInt(raw.trim(), 10);
  if (isNaN(parsed) || parsed < 80 || parsed > 600) {
    alert("Please enter a valid FTP between 80 and 600 Watts.");
    return;
  }
  try {
    const res = await fetch("/api/power/ftp-test-record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        new_ftp: parsed,
        protocol: (r && r.recommended_protocol) || "20m_coggan"
      })
    });
    const data = await res.json();
    if (data.success) {
      state.ftp = parsed;
      state.ftpTestReadiness = data.readiness || null;
      renderAthleteProfile();
      renderFtpTestReadiness(state.ftpTestReadiness);
      if (data.program) renderProgram(data.program);
      if (typeof loadPowerSpiderweb === "function") loadPowerSpiderweb("30d");
    } else {
      alert(data.detail || "Failed to record FTP test result.");
    }
  } catch (err) {
    console.error("Failed to record FTP test:", err);
    alert("Error saving FTP test result.");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btnAdv = document.getElementById("btnAdvisorLoadFtpTest");
  if (btnAdv) btnAdv.addEventListener("click", launchRecommendedFtpTest);
  const btnDaily = document.getElementById("btnDailyLoadFtpTest");
  if (btnDaily) btnDaily.addEventListener("click", launchRecommendedFtpTest);
  const btnRec = document.getElementById("btnRecordFtpTestResult");
  if (btnRec) btnRec.addEventListener("click", recordFtpTestResultFlow);
});

// Utility: cleanly extract text from any insights string that may contain raw JSON
function cleanCoachInsightsText(text) {
  if (!text || typeof text !== "string") return "";
  let str = text.trim();
  if (str.startsWith("{") || str.includes('"insights"')) {
    try {
      const parsed = JSON.parse(str);
      if (parsed.insights && typeof parsed.insights === "string") {
        return parsed.insights.trim();
      }
    } catch (_) {
      const m = str.match(/"insights"\s*:\s*"((?:[^"\\]|\\.)*)/i);
      if (m && m[1] && m[1].length > 15) {
        return m[1].replace(/\\"/g, '"').replace(/\\n/g, '\n').trim();
      }
    }
    return "";
  }
  return str;
}

// Compute Target Watts for a Workout
function computeWorkoutTargetWatts(w, ftp) {
  if (!w) return "--";
  if (w.duration_minutes === 0 || w.option_type === "rest") return "0 W";
  if (w.target_power && w.target_power > 0) return `${Math.round(w.target_power)} W`;
  const f = ftp || state.ftp || 250;
  if (w.intervals && Array.isArray(w.intervals) && w.intervals.length > 0) {
    const workInt = w.intervals.find(i => {
      const t = (i.type || i.name || "").toLowerCase();
      return !t.includes("warmup") && !t.includes("cooldown");
    }) || w.intervals[1] || w.intervals[0];
    if (workInt) {
      const pct = workInt.power_pct || workInt.on_power_pct || workInt.power_high_pct || workInt.power_low_pct;
      if (pct) return `${Math.round(f * pct / 100)} W`;
    }
  }
  const focus = (w.focus_area || w.intensity_type || "").toLowerCase();
  if (focus.includes("sweet spot")) return `${Math.round(f * 0.90)} W`;
  if (focus.includes("threshold")) return `${Math.round(f * 1.0)} W`;
  if (focus.includes("tempo")) return `${Math.round(f * 0.82)} W`;
  if (focus.includes("vo2")) return `${Math.round(f * 1.15)} W`;
  if (focus.includes("anaerobic")) return `${Math.round(f * 1.25)} W`;
  return `${Math.round(f * 0.68)} W`;
}

// Render Top-Right AI Coach Directive Panel (Completed vs Scheduled)
function renderAiCoachTodayCard(debriefData, workoutData) {
  const cardTitle = document.getElementById("coachCardTitle");
  const badge = document.getElementById("coachCardStatusBadge");
  const preHeading = document.getElementById("coachCardPreHeading");
  const title = document.getElementById("coachCardSessionTitle");
  const lbl1 = document.getElementById("coachCardLbl1");
  const val1 = document.getElementById("coachCardVal1");
  const lbl2 = document.getElementById("coachCardLbl2");
  const val2 = document.getElementById("coachCardVal2");
  const lbl3 = document.getElementById("coachCardLbl3");
  const val3 = document.getElementById("coachCardVal3");
  const lbl4 = document.getElementById("coachCardLbl4");
  const val4 = document.getElementById("coachCardVal4");
  const narrative = document.getElementById("coachCardNarrative");
  const subtext = document.getElementById("coachCardFooterSubtext");
  const jumpLink = document.getElementById("coachCardJumpLink");

  if (!title) return;
  if (badge) badge.style.display = "none";

  const assessment = (debriefData && debriefData.today_assessment) || (state.dailyDebrief && state.dailyDebrief.today_assessment) || {};
  const isCompletedToday = Boolean(assessment.is_today && assessment.title && assessment.title !== "Rest / Off-Bike Day");

  const w = workoutData || state.currentWorkout || {};
  const hasActivePrescription = Boolean(
    w && (
      w.coach_prescribed ||
      w.pushed_to_zwift ||
      w.synced_to_zwift ||
      w.id === "workout_coach_prescribed" ||
      w.option_type === "coach_chat" ||
      w.is_user_adapted ||
      w.id === "workout_custom_replaced" ||
      (w.title && w.title !== "Rest Day or Easy Spin")
    )
  );

  // Default to Ride Debrief once a ride has occurred today, unless the user explicitly switches to the prescribed briefing
  const showPrescribed = (state.activeCoachView === "prescribed") || (!isCompletedToday);

  if (!showPrescribed && isCompletedToday) {
    // State 1: Ride Debrief (Workout Completed Today)
    if (cardTitle) cardTitle.textContent = "Ride Debrief";
    if (preHeading) {
      preHeading.innerHTML = hasActivePrescription
        ? '<span style="color:var(--text-muted);font-weight:700;">DIRECTEUR SPORTIVE • POST-RIDE DEBRIEF</span> · <a href="#" id="linkSwitchToPrescribed" style="color:var(--accent-cyan);text-decoration:none;font-weight:600;font-size:0.75rem;">Switch to Ride Briefing 🚀</a>'
        : 'DIRECTEUR SPORTIVE • POST-RIDE DEBRIEF';
    }
    title.textContent = assessment.title;

    if (lbl1) lbl1.textContent = "Duration";
    if (val1) {
      val1.textContent = assessment.moving_time_formatted || `${assessment.moving_time_min || 0}m`;
      val1.style.color = "var(--text-primary)";
    }

    if (lbl2) lbl2.textContent = "Avg Power";
    if (val2) {
      val2.textContent = assessment.weighted_watts ? `${assessment.weighted_watts} W` : "--";
      val2.style.color = "var(--accent-cyan)";
    }

    if (lbl3) lbl3.textContent = "Avg HR";
    if (val3) {
      val3.textContent = assessment.avg_hr ? `${assessment.avg_hr} bpm` : "--";
      val3.style.color = "#f59e0b";
    }

    if (lbl4) lbl4.textContent = assessment.total_xss ? "Total Strain" : "Verdict";
    if (val4) {
      if (assessment.total_xss) {
        val4.textContent = `${assessment.total_xss} XSS`;
        val4.style.color = "#c084fc";
      } else {
        val4.textContent = assessment.compliance_score ? `${assessment.compliance_score}% Fidelity` : (assessment.verdict || "Bullseye 🎯");
        val4.style.color = "#10b981";
      }
    }

    if (narrative) {
      const raw = assessment.ai_coach_insights || assessment.assessment_text || "";
      const cleaned = cleanCoachInsightsText(raw);
      narrative.textContent = cleaned || "Controlled session completed today matching prescribed recovery targets.";
    }

    if (subtext) {
      subtext.textContent = assessment.verdict ? `${assessment.verdict} 🎯` : "Execution Bullseye 🎯";
      subtext.style.color = "#10b981";
    }

    if (jumpLink) {
      jumpLink.href = "#cardCoachDebrief";
      jumpLink.innerHTML = "Full Debrief ↓";
      jumpLink.onclick = (e) => {
        e.preventDefault();
        const debriefEl = document.getElementById("cardCoachDebrief");
        if (debriefEl) debriefEl.scrollIntoView({ behavior: "smooth", block: "start" });
      };
    }

    const linkSwitch = document.getElementById("linkSwitchToPrescribed");
    if (linkSwitch) {
      linkSwitch.onclick = (e) => {
        e.preventDefault();
        state.activeCoachView = "prescribed";
        renderAiCoachTodayCard(debriefData, workoutData);
      };
    }
  } else {
    // State 2: Ride Briefing (Active Coach Directive / Prescribed Session)
    if (cardTitle) cardTitle.textContent = "Ride Briefing";
    const whoopRec = (state.whoop && state.whoop.recovery_score) || (state.dashboard && state.dashboard.whoop && state.dashboard.whoop.recovery_score) || 50;
    const isRest = (w.duration_minutes === 0 || w.option_type === "rest");
    const isZwiftSynced = Boolean(w.pushed_to_zwift || w.synced_to_zwift);

    if (preHeading) {
      if (isZwiftSynced) {
        preHeading.innerHTML = '<span style="color:#10b981;font-weight:700;">ACTIVE DIRECTIVE</span> · <span style="color:var(--accent-cyan);font-weight:700;">SENT TO ZWIFT 🚀</span>' +
          (isCompletedToday ? ' · <a href="#" id="linkSwitchToCompleted" style="color:var(--text-muted);text-decoration:underline;font-size:0.75rem;margin-left:0.25rem;">Ride Debrief ↗</a>' : '');
      } else if (hasActivePrescription && (w.coach_prescribed || w.option_type === "coach_chat")) {
        preHeading.innerHTML = '<span style="color:var(--accent-cyan);font-weight:700;">ACTIVE COACH DIRECTIVE</span> · <span style="color:#c084fc;font-weight:700;">CHAT REVISED 💬</span>' +
          (isCompletedToday ? ' · <a href="#" id="linkSwitchToCompleted" style="color:var(--text-muted);text-decoration:underline;font-size:0.75rem;margin-left:0.25rem;">Ride Debrief ↗</a>' : '');
      } else if (hasActivePrescription && w.is_user_adapted) {
        preHeading.innerHTML = '<span style="color:var(--accent-cyan);font-weight:700;">ACTIVE COACH DIRECTIVE</span> · <span style="color:#f59e0b;font-weight:700;">CUSTOM ADAPTED ⚡</span>' +
          (isCompletedToday ? ' · <a href="#" id="linkSwitchToCompleted" style="color:var(--text-muted);text-decoration:underline;font-size:0.75rem;margin-left:0.25rem;">Ride Debrief ↗</a>' : '');
      } else if (isRest) {
        preHeading.textContent = "TODAY'S REST DAY DIRECTIVE";
      } else {
        preHeading.innerHTML = 'DIRECTEUR SPORTIVE • PRE-RIDE RACE BRIEFING' +
          (isCompletedToday ? ' · <a href="#" id="linkSwitchToCompleted" style="color:var(--text-muted);text-decoration:underline;font-size:0.75rem;margin-left:0.25rem;">Ride Debrief ↗</a>' : '');
      }
    }

    title.textContent = w.title || (isRest ? "Rest Day or Easy Spin" : "Zone 2 Aerobic Base Flush");

    if (lbl1) lbl1.textContent = "Duration";
    if (val1) {
      val1.textContent = `${w.duration_minutes !== undefined ? w.duration_minutes : 60}m`;
      val1.style.color = "var(--text-primary)";
    }

    if (lbl2) lbl2.textContent = "Target Watts";
    if (val2) {
      val2.textContent = computeWorkoutTargetWatts(w, state.ftp || 250);
      val2.style.color = isRest ? "#10b981" : "var(--accent-cyan)";
    }

    if (lbl3) lbl3.textContent = "Target Zone";
    if (val3) {
      val3.textContent = w.focus_area || w.target_zone || (isRest ? "Rest & Recovery" : "Zone 2");
      val3.style.color = isRest ? "#10b981" : "#38bdf8";
    }

    if (lbl4) lbl4.textContent = (w.total_xss !== undefined && w.total_xss > 0) ? "Target Strain" : "Est. TSS";
    if (val4) {
      if (isRest) {
        val4.textContent = "0 TSS";
        val4.style.color = "var(--text-muted)";
      } else if (w.total_xss !== undefined && w.total_xss > 0) {
        val4.textContent = `${w.total_xss} XSS`;
        val4.style.color = "#c084fc";
      } else {
        val4.textContent = w.tss ? `~${w.tss}` : (w.estimated_tss ? `~${w.estimated_tss}` : "~50");
        val4.style.color = "var(--accent-amber)";
      }
    }

    if (narrative) {
      narrative.textContent = w.ai_rationale || w.description || (isRest
        ? `Per your forward directive, today is recommended as a full rest day or gentle active recovery spin.`
        : `Whoop recovery sits at ${whoopRec}%. Keep power strictly within aerobic boundaries to protect recovery and build aerobic fitness.`);
    }

    if (subtext) {
      if (isZwiftSynced) {
        subtext.innerHTML = '<span style="color:#10b981;font-weight:600;">✓ Synced to Zwift 🚀</span>';
      } else if (w.badge) {
        subtext.textContent = w.badge;
        subtext.title = w.badge;
        subtext.style.color = isRest ? "#10b981" : "var(--accent-cyan)";
      } else {
        subtext.textContent = `Whoop: ${whoopRec}% Recovery`;
        subtext.style.color = whoopRec >= 67 ? "#10b981" : (whoopRec < 40 ? "#f43f5e" : "#f59e0b");
      }
    }

    if (jumpLink) {
      if (isCompletedToday) {
        jumpLink.href = "#";
        jumpLink.innerHTML = "View Ride Debrief ↗";
        jumpLink.onclick = (e) => {
          e.preventDefault();
          state.activeCoachView = "completed";
          renderAiCoachTodayCard(debriefData, workoutData);
        };
      } else {
        jumpLink.href = "#workoutStageSection";
        jumpLink.innerHTML = "Jump to Plan ↓";
        jumpLink.onclick = (e) => {
          e.preventDefault();
          const stageEl = document.getElementById("workoutStageSection") || document.getElementById("indoorContainer");
          if (stageEl) {
            if (typeof isWorkoutStageCollapsed === "function" && isWorkoutStageCollapsed()) {
              setWorkoutStageCollapsed(false);
            }
            stageEl.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        };
      }
    }

    const linkSwitchComp = document.getElementById("linkSwitchToCompleted");
    if (linkSwitchComp) {
      linkSwitchComp.onclick = (e) => {
        e.preventDefault();
        state.activeCoachView = "completed";
        renderAiCoachTodayCard(debriefData, workoutData);
      };
    }
  }

  // Update Collapsed Coach Directive Summary Chips
  const collapsedCoachSession = document.getElementById("collapsedCoachSession");
  if (collapsedCoachSession) {
    collapsedCoachSession.textContent = showPrescribed
      ? (w.title || "Today's Session")
      : (assessment.title || "Today's Session");
  }
  const collapsedCoachVerdict = document.getElementById("collapsedCoachVerdict");
  if (collapsedCoachVerdict && val4) {
    collapsedCoachVerdict.textContent = (showPrescribed && (w.pushed_to_zwift || w.synced_to_zwift))
      ? "On Zwift 🚀"
      : val4.textContent;
  }
  const collapsedCoachDur = document.getElementById("collapsedCoachDur");
  if (collapsedCoachDur && val1) {
    collapsedCoachDur.textContent = val1.textContent;
  }
}

// Render Integration Status Badges
function renderIntegrations(integrations) {
  if (!integrations) return;
  const whoopText = document.getElementById("whoopStatusText");
  const stravaText = document.getElementById("stravaStatusText");
  const zwiftText = document.getElementById("zwiftStatusText");
  const banner = document.getElementById("demoModeBanner");

  const isDemo = state.dashboard?.demo_mode;
  if (banner) {
    banner.style.display = isDemo ? "flex" : "none";
  }

  const whoopBadge = document.getElementById("badgeWhoop");
  const whoopDot = whoopBadge ? whoopBadge.querySelector(".dot") : null;
  if (integrations.whoop?.auth_expired) {
    whoopText.textContent = "Session Expired";
    if (whoopDot) whoopDot.className = "dot red";
  } else if (integrations.whoop?.connected) {
    whoopText.textContent = "Connected";
    if (whoopDot) whoopDot.className = "dot green";
  } else {
    whoopText.textContent = isDemo ? "Demo Mode" : "Not connected";
    if (whoopDot) whoopDot.className = isDemo ? "dot amber" : "dot gray";
  }

  const stravaBadge = document.getElementById("badgeStrava");
  const stravaDot = stravaBadge ? stravaBadge.querySelector(".dot") : null;
  if (integrations.strava?.connected) {
    stravaText.textContent = "Connected";
    if (stravaDot) {
      stravaDot.className = "dot green";
      stravaDot.style.background = "#10b981";
      stravaDot.style.boxShadow = "0 0 8px #10b981";
    }
  } else {
    stravaText.textContent = isDemo ? "Demo Mode" : "Not connected";
    if (stravaDot) {
      stravaDot.className = isDemo ? "dot amber" : "dot gray";
      stravaDot.style.background = isDemo ? "var(--accent-amber)" : "#94a3b8";
      stravaDot.style.boxShadow = "none";
    }
  }

  const zwiftBadge = document.getElementById("badgeZwift");
  const zwiftDot = zwiftBadge ? (document.getElementById("zwiftNavDot") || zwiftBadge.querySelector(".dot")) : null;
  const isZwiftConnected = Boolean(integrations.intervals_icu?.configured);
  if (isZwiftConnected) {
    zwiftText.textContent = "Connected";
    if (zwiftDot) {
      zwiftDot.className = "dot green";
      zwiftDot.style.background = "#10b981";
      zwiftDot.style.boxShadow = "0 0 8px #10b981";
    }
  } else {
    zwiftText.textContent = isDemo ? "Demo Mode" : "Not connected";
    if (zwiftDot) {
      zwiftDot.className = isDemo ? "dot amber" : "dot gray";
      zwiftDot.style.background = isDemo ? "var(--accent-amber)" : "#94a3b8";
      zwiftDot.style.boxShadow = "none";
    }
  }

  const geminiText = document.getElementById("geminiNavStatusText");
  const geminiDot = document.getElementById("geminiNavDot");
  if (geminiText) {
    const isGeminiConfigured = Boolean(integrations.gemini?.configured);
    if (isGeminiConfigured) {
      geminiText.textContent = "Connected";
      if (geminiDot) {
        geminiDot.className = "dot green";
        geminiDot.style.background = "#10b981";
        geminiDot.style.boxShadow = "0 0 8px #10b981";
      }
    } else {
      geminiText.textContent = isDemo ? "Demo AI" : "Not connected";
      if (geminiDot) {
        geminiDot.className = isDemo ? "dot amber" : "dot gray";
        geminiDot.style.background = isDemo ? "var(--accent-amber)" : "#94a3b8";
        geminiDot.style.boxShadow = "none";
      }
    }
  }

  const wyzeText = document.getElementById("wyzeStatusText");
  const wyzeDot = document.getElementById("wyzeNavDot");
  if (wyzeText) {
    const isWyzeConnected = Boolean(integrations.wyze?.connected);
    const isWyzeExpired = Boolean(integrations.wyze?.auth_expired);
    if (isWyzeExpired) {
      wyzeText.textContent = "Auth Expired";
      if (wyzeDot) {
        wyzeDot.className = "dot red";
        wyzeDot.style.background = "#f43f5e";
        wyzeDot.style.boxShadow = "0 0 8px rgba(244,63,94,0.6)";
      }
    } else if (isWyzeConnected) {
      const latestW = state.wyzeScale && state.wyzeScale.latest ? state.wyzeScale.latest : null;
      wyzeText.textContent = latestW && latestW.weight_lbs ? `${Number(latestW.weight_lbs).toFixed(1)} lbs` : "Connected";
      if (wyzeDot) {
        wyzeDot.className = "dot green";
        wyzeDot.style.background = "#10b981";
        wyzeDot.style.boxShadow = "0 0 8px #10b981";
      }
    } else {
      wyzeText.textContent = "Not connected";
      if (wyzeDot) {
        wyzeDot.className = "dot gray";
        wyzeDot.style.background = "#94a3b8";
        wyzeDot.style.boxShadow = "none";
      }
    }
  }

  // Update Connections Dropdown Summary (pill indicator & count badge)
  const summaryDot = document.getElementById("connectionsSummaryDot");
  const countBadge = document.getElementById("connectionsCountBadge");
  const btnDropdown = document.getElementById("btnConnectionsDropdown");

  let connectedCount = 0;
  const totalServices = 5;
  const hasExpired = Boolean(integrations.whoop?.auth_expired || integrations.wyze?.auth_expired);

  if (integrations.whoop?.connected && !integrations.whoop?.auth_expired) {
    connectedCount++;
  }
  if (integrations.strava?.connected) {
    connectedCount++;
  }
  if (integrations.wyze?.connected && !integrations.wyze?.auth_expired) {
    connectedCount++;
  }
  if (Boolean(integrations.intervals_icu?.configured)) {
    connectedCount++;
  }
  if (Boolean(integrations.gemini?.configured) || (!isDemo && state.dashboard?.has_gemini)) {
    connectedCount++;
  }

  if (countBadge) {
    countBadge.textContent = `${connectedCount}/${totalServices}`;
  }

  if (btnDropdown) {
    btnDropdown.title = `Connected Services: ${connectedCount} of ${totalServices} active`;
  }

  if (summaryDot) {
    if (hasExpired) {
      summaryDot.className = "dot red";
      summaryDot.style.background = "var(--accent-rose, #f43f5e)";
      summaryDot.style.boxShadow = "0 0 8px rgba(244, 63, 94, 0.6)";
    } else if (connectedCount >= 3) {
      summaryDot.className = "dot green";
      summaryDot.style.background = "var(--accent-emerald, #10b981)";
      summaryDot.style.boxShadow = "0 0 8px var(--accent-emerald, #10b981)";
    } else if (connectedCount > 0 || isDemo) {
      summaryDot.className = "dot amber";
      summaryDot.style.background = "var(--accent-amber, #f59e0b)";
      summaryDot.style.boxShadow = "0 0 8px rgba(245, 158, 11, 0.5)";
    } else {
      summaryDot.className = "dot gray";
      summaryDot.style.background = "#94a3b8";
      summaryDot.style.boxShadow = "none";
    }
  }
}

// Render Long-Term Fitness Goal & Periodization
function renderProgram(p) {
  if (!p) return;
  state.program = p;

  if (programGoalTitle) programGoalTitle.textContent = p.goal_title || "Training Program";
  if (programPhaseBadge) programPhaseBadge.textContent = p.phase || "Build Phase";
  if (programGoalDesc) programGoalDesc.textContent = p.goal_description || "";

  const programSpiderwebBadge = document.getElementById("programSpiderwebBadge");
  if (programSpiderwebBadge) {
    if (p.active_spiderweb_goal && p.active_spiderweb_goal.target_badge) {
      programSpiderwebBadge.style.display = "inline-flex";
      programSpiderwebBadge.textContent = `🎯 ${p.active_spiderweb_goal.target_badge}`;
    } else {
      programSpiderwebBadge.style.display = "none";
    }
  }

  const plannerSyncBadge = document.getElementById("plannerMacrocycleSyncBadge");
  if (plannerSyncBadge) {
    plannerSyncBadge.textContent = `🔄 Synced: ${p.phase || "Build Phase"} • Target FTP ${p.target_ftp || 265}W (${p.weekly_xss_target || p.weekly_tss_target || 360} XSS/wk)`;
  }

  // Macrocycle column labels (Event taper vs Phenotype mastery absent event)
  const phaseColTaper = document.getElementById("phaseColTaper");
  if (phaseColTaper) phaseColTaper.textContent = p.phase_4_label || (p.has_specific_event ? "4. Taper & Fresh" : "4. Mastery & Test");
  const phaseColPeak = document.getElementById("phaseColPeak");
  if (phaseColPeak) phaseColPeak.textContent = p.has_specific_event ? "3. Peak (VO2)" : "3. Specialty";

  // Highlight active column in macrocycle
  const phaseStr = (p.phase || "").toLowerCase();
  const cols = ["phaseColBase", "phaseColBuild", "phaseColPeak", "phaseColTaper"];
  cols.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("active");
  });
  if (phaseStr.includes("base")) document.getElementById("phaseColBase")?.classList.add("active");
  else if (phaseStr.includes("build")) document.getElementById("phaseColBuild")?.classList.add("active");
  else if (phaseStr.includes("specialty") || phaseStr.includes("peak")) document.getElementById("phaseColPeak")?.classList.add("active");
  else if (phaseStr.includes("taper") || phaseStr.includes("mastery") || phaseStr.includes("test")) document.getElementById("phaseColTaper")?.classList.add("active");

  if (macrocycleFillBar) macrocycleFillBar.style.width = `${Math.min(100, Math.max(5, p.progress_pct || 0))}%`;
  if (programWeekInfo) programWeekInfo.textContent = `Week ${p.current_week || 1} of ${p.total_weeks || 8} • ${p.phase}`;
  if (programDaysInfo) programDaysInfo.textContent = p.has_specific_event ? `${p.days_remaining || 0} Days to Event` : `${p.days_remaining || 0} Days Remaining in Block`;

  if (programFtpDelta) {
    const delta = p.ftp_delta || 0;
    programFtpDelta.textContent = `${delta >= 0 ? '+' : ''}${delta}W`;
  }
  if (programTargetFtpVal) programTargetFtpVal.textContent = p.target_ftp || 265;
  if (programCurrentFtpVal) programCurrentFtpVal.textContent = `${p.current_ftp || state.ftp}W`;

  if (programCompliancePct) programCompliancePct.textContent = `${p.weekly_compliance_pct || 0}%`;
  if (programWeeklyTssActual) programWeeklyTssActual.textContent = p.weekly_tss_actual || 0;
  if (programWeeklyTssTarget) programWeeklyTssTarget.textContent = p.weekly_tss_target || 360;
  if (programWeeklyXssActual) programWeeklyXssActual.textContent = p.weekly_xss_actual !== undefined ? p.weekly_xss_actual : (p.weekly_tss_actual || 0);
  if (programWeeklyXssTarget) programWeeklyXssTarget.textContent = p.weekly_xss_target || p.weekly_tss_target || 360;
  if (programXssCompliancePct) programXssCompliancePct.textContent = `${p.weekly_xss_compliance_pct !== undefined ? p.weekly_xss_compliance_pct : (p.weekly_compliance_pct || 0)}%`;
  if (programFocusDurationBadge) programFocusDurationBadge.textContent = p.target_focus_duration || "Sweet Spot (45:00 Focus)";
  if (programTssMeterFill) {
    const pct = Math.min(100, p.weekly_compliance_pct || 0);
    programTssMeterFill.style.width = `${pct}%`;
    programTssMeterFill.style.backgroundColor = pct >= 80 ? "var(--accent-emerald)" : (pct >= 50 ? "var(--accent-amber)" : "var(--accent-cyan)");
  }

  if (programPhaseFocus) programPhaseFocus.textContent = p.phase_focus || "";
  if (programPhaseDetail) programPhaseDetail.textContent = p.phase_desc || "";

  // Render Target Power Envelope chips strip
  const envChipsEl = document.getElementById("programEnvelopeChips");
  if (envChipsEl) {
    const env = p.target_envelope || {};
    const durKeys = ["5s", "1m", "5m", "20m", "60m"];
    const validDurs = durKeys.filter(k => env[k] !== undefined);
    if (validDurs.length > 0) {
      envChipsEl.innerHTML = validDurs.map(k => `
        <span class="tag" style="background:rgba(0,82,255,0.08);color:#0052FF;border:1px solid rgba(0,82,255,0.22);font-weight:700;font-size:0.75rem;">
          ${k}: ${env[k]}W
        </span>
      `).join("");
    } else {
      envChipsEl.innerHTML = `<span style="font-size:0.75rem;color:var(--text-muted);">Syncing from 5-axis profile...</span>`;
    }
  }

  // Update collapsed summary for program card
  const collapsedPhase = document.getElementById("collapsedProgramPhase");
  if (collapsedPhase) collapsedPhase.textContent = p.phase || "Build Phase";
  const collapsedWeek = document.getElementById("collapsedProgramWeek");
  if (collapsedWeek) collapsedWeek.textContent = `Week ${p.current_week || 1} of ${p.total_weeks || 8}`;
  const collapsedCompliance = document.getElementById("collapsedProgramCompliance");
  if (collapsedCompliance) collapsedCompliance.textContent = `${p.weekly_compliance_pct || 0}% Compliance`;
  const collapsedFtpDelta = document.getElementById("collapsedProgramFtpDelta");
  if (collapsedFtpDelta) {
    const delta = p.ftp_delta || 0;
    collapsedFtpDelta.textContent = `${delta >= 0 ? '+' : ''}${delta}W FTP Target`;
  }
}

function formatCarbPreview(opt) {
  if (!opt) return "Hydration Only";
  if (opt.duration_minutes === 0 || opt.option_type === "rest") return "Hydrate & Rest";
  if (typeof opt.carbs_per_hour_g === "number") {
    return opt.carbs_per_hour_g <= 0 ? "Hydration Only" : `~${opt.carbs_per_hour_g}g/h`;
  }
  const durMin = Math.max(
    20,
    Math.round(
      opt.duration_minutes ??
      opt.moving_time_min ??
      (opt.moving_time_sec ? opt.moving_time_sec / 60 : 60)
    )
  );
  const intensity = String(opt.focus_area || opt.target_zone || opt.zone || "").toLowerCase();
  const ftp = Number(state.ftp || 250);
  let pctFtp = 0.65;
  if (opt.average_watts && opt.average_watts > 0 && ftp > 0) {
    pctFtp = opt.average_watts / ftp;
  } else if (intensity.includes("race") || intensity.includes("hard") || intensity.includes("vo2") || intensity.includes("threshold") || intensity.includes("anaerobic")) {
    pctFtp = 0.88;
  } else if (intensity.includes("tempo") || intensity.includes("group") || intensity.includes("sweet")) {
    pctFtp = 0.78;
  } else if (intensity.includes("recovery")) {
    pctFtp = 0.52;
  }
  if (durMin < 45) return "Hydration Only";
  if (durMin <= 75) return pctFtp < 0.75 ? "~35g/h" : "~45g/h";
  if (durMin <= 135) return pctFtp < 0.75 ? "~50g/h" : "~60g/h";
  if (durMin <= 210) return pctFtp < 0.75 ? "~65g/h" : "~75g/h";
  return pctFtp < 0.75 ? "~80g/h" : "~90g/h";
}

// Render Alternative Workouts Selection Cards
function renderWorkoutOptions(options, activeId) {
  if (!workoutOptionsGrid || !options || options.length === 0) return;

  workoutOptionsGrid.innerHTML = options.map(opt => {
    const isActive = opt.id === activeId;
    const badgeColor = opt.badge_color === "emerald" ? "var(--accent-emerald)" : 
                       (opt.badge_color === "amber" ? "var(--accent-amber)" : "var(--accent-cyan)");
    const carbPreview = formatCarbPreview(opt);
    const strainPreview = (opt.total_xss !== undefined && opt.total_xss > 0)
      ? `<span style="color:#c084fc;font-weight:600;" title="3-Tier Strain: ${opt.low_xss || 0} Low • ${opt.high_xss || 0} High • ${opt.peak_xss || 0} Peak">⚡ ${opt.total_xss} XSS</span>`
      : `<span>⚡ ~${opt.estimated_tss} TSS</span>`;
    return `
      <div class="workout-option-card ${isActive ? 'active' : ''}" data-opt-id="${opt.id}">
        <div class="workout-option-badge" style="color:${badgeColor};">
          ${opt.badge || 'Workout Option'}
        </div>
        <div class="workout-option-title">${opt.title}</div>
        <div class="workout-option-meta">
          <span>⏱️ ${opt.duration_minutes}m</span>
          ${strainPreview}
          <span>🎯 ${opt.focus_area}</span>
          <span style="color:#10b981;font-weight:600;">🥪 ${carbPreview}</span>
        </div>
      </div>
    `;
  }).join("");

  workoutOptionsGrid.querySelectorAll(".workout-option-card").forEach(card => {
    card.addEventListener("click", () => {
      const optId = card.dataset.optId;
      if (optId && optId !== state.activeOptionId) {
        selectWorkoutOption(optId);
      }
    });
  });
}

// Sync duration pills with active workout duration
function syncDurationPills(duration) {
  if (!durPillGroup) return;
  let found = false;
  durPillGroup.querySelectorAll(".btn-pill").forEach(b => {
    const d = parseInt(b.dataset.dur, 10);
    if (d === duration) {
      b.classList.add("active");
      found = true;
    } else {
      b.classList.remove("active");
    }
  });
  let customPill = durPillGroup.querySelector(".custom-dur-pill");
  if (!found && duration > 0) {
    if (!customPill) {
      customPill = document.createElement("button");
      customPill.className = "btn-pill custom-dur-pill";
      durPillGroup.appendChild(customPill);
    }
    customPill.dataset.dur = duration;
    customPill.textContent = `${duration}m`;
    customPill.classList.add("active");
  } else if (customPill && found) {
    customPill.remove();
  }
}

// Select Workout Option Switcher
async function selectWorkoutOption(optionId) {
  // 1. Instant optimistic local UI update
  const localMatch = (state.workoutOptions || []).find(o => o.id === optionId);
  if (localMatch) {
    state.currentWorkout = localMatch;
    state.activeOptionId = localMatch.id;
    state.currentDuration = localMatch.duration_minutes;
    state.selectedIntervalIndex = null;
    state.activeCoachView = "prescribed";
    syncDurationPills(state.currentDuration);
    renderWorkout(state.currentWorkout);
    renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
    renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);

    const fuelingPanel = document.getElementById("fuelingPlanPanel");
    if (fuelingPanel && fuelingPanel.style.display !== "none") {
      if (typeof positionFuelingPanel === "function") positionFuelingPanel("indoor");
      loadFuelingPlanForRide(localMatch, false);
    }
  }

  try {
    const res = await fetch("/api/workouts/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ option_id: optionId })
    });
    const data = await res.json();
    if (data.success && data.active_workout) {
      state.currentWorkout = data.active_workout;
      state.activeOptionId = data.active_workout.id;
      state.currentDuration = data.active_workout.duration_minutes;
      state.activeCoachView = "prescribed";
      syncDurationPills(state.currentDuration);
      renderWorkout(state.currentWorkout);
      renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
      renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
      showToast(`Selected: ${state.currentWorkout.title}`);
      if (data.fueling_plan) {
        currentFuelingPlan = data.fueling_plan;
        const fuelingPanel = document.getElementById("fuelingPlanPanel");
        if (fuelingPanel && fuelingPanel.style.display !== "none") {
          renderFuelingPlan(data.fueling_plan);
        }
      }
    }
  } catch (err) {
    console.error("Failed to select option:", err);
  }
}

// Switch Mode: Indoor vs Outdoor
function setTrainingMode(mode) {
  state.trainingMode = mode;
  const fuelingPanel = document.getElementById("fuelingPlanPanel");
  if (typeof positionFuelingPanel === "function") positionFuelingPanel(mode);

  if (mode === "outdoor") {
    if (tabModeIndoor) tabModeIndoor.className = "mode-tab";
    if (tabModeOutdoor) tabModeOutdoor.className = "mode-tab active active-outdoor";
    if (indoorContainer) indoorContainer.style.display = "none";
    if (outdoorContainer) outdoorContainer.style.display = "block";
    if (modeSubtext) modeSubtext.textContent = "🌲 Strava GPS History & Elevation Profile Match";
    const stageHeaderSubtitle = document.getElementById("stageHeaderSubtitle");
    if (stageHeaderSubtitle) stageHeaderSubtitle.textContent = "AI match of your best prior Strava route for today's recovery";

    if (fuelingPanel && fuelingPanel.style.display !== "none") {
      if (state.currentOutdoorRide) {
        loadFuelingPlanForRide(state.currentOutdoorRide, true);
      }
    }

    if (!state.currentOutdoorRide) {
      loadOutdoorRecommendation(state.outdoorDuration);
    } else {
      setTimeout(() => {
        if (state.currentOutdoorRide) {
          renderOutdoorMap(state.currentOutdoorRide);
        } else if (outdoorMap) {
          outdoorMap.invalidateSize(true);
        }
      }, 120);
    }
  } else {
    if (tabModeIndoor) tabModeIndoor.className = "mode-tab active";
    if (tabModeOutdoor) tabModeOutdoor.className = "mode-tab";
    if (indoorContainer) indoorContainer.style.display = "block";
    if (outdoorContainer) outdoorContainer.style.display = "none";
    if (modeSubtext) modeSubtext.textContent = "⚡ Indoor ERG & Zwift Cloud Bridge";
    const stageHeaderSubtitle = document.getElementById("stageHeaderSubtitle");
    if (stageHeaderSubtitle) stageHeaderSubtitle.textContent = "Intervals scaled to Whoop recovery with 1-click Zwift export";

    if (fuelingPanel && fuelingPanel.style.display !== "none") {
      if (state.currentWorkout) {
        loadFuelingPlanForRide(state.currentWorkout, false);
      }
    }
  }
  if (typeof updateFuelingButtonStates === "function") {
    updateFuelingButtonStates();
  }
}

// Fetch Outdoor Route Recommendation
async function loadOutdoorRecommendation(duration = 60, userNote = "") {
  try {
    if (outdoorRationale) {
      outdoorRationale.innerHTML = "<em>Analyzing your Strava outdoor ride history and matching today's recovery...</em>";
    }
    const res = await fetch("/api/workouts/outdoor-recommendation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_min: duration,
        user_note: userNote
      })
    });
    const data = await res.json();
    if (data.success && data.active_ride) {
      state.currentOutdoorRide = data.active_ride;
      state.outdoorOptions = data.options || [data.active_ride];
      state.activeOutdoorId = data.active_ride.id;
      renderOutdoorRide(state.currentOutdoorRide);
      renderOutdoorOptions(state.outdoorOptions, state.activeOutdoorId);
      if (data.fueling_plan) {
        currentFuelingPlan = data.fueling_plan;
        const fuelingPanel = document.getElementById("fuelingPlanPanel");
        if (fuelingPanel && fuelingPanel.style.display !== "none" && state.trainingMode === "outdoor") {
          renderFuelingPlan(data.fueling_plan);
        }
      }
    }
  } catch (err) {
    console.error("Failed to load outdoor recommendation:", err);
    if (outdoorRationale) {
      outdoorRationale.textContent = "Error loading outdoor recommendation.";
    }
  }
}



// Render Mini Header Course Preview
function renderHeaderMiniMap(ride, svgElem) {
  if (!svgElem || !ride) return;
  const path = ride.header_svg || ride.thumbnail_svg || ride.svg_path;
  if (!path) {
    svgElem.innerHTML = '';
    return;
  }
  svgElem.innerHTML = `
    <defs>
      <linearGradient id="headerMapGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#10b981" />
        <stop offset="50%" stop-color="#fc5200" />
        <stop offset="100%" stop-color="#06b6d4" />
      </linearGradient>
    </defs>
    <path d="${path}" stroke="rgba(252, 82, 0, 0.35)" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
    <path d="${path}" stroke="url(#headerMapGrad)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
  `;
}

// Render High-Contrast GPS Route Silhouette
function renderSvgRouteMap(ride, svgElem) {
  if (!svgElem || !ride || !ride.svg_path) return;
  
  const startX = ride.start_xy ? ride.start_xy[0] : 0;
  const startY = ride.start_xy ? ride.start_xy[1] : 0;
  const endX = ride.end_xy ? ride.end_xy[0] : 0;
  const endY = ride.end_xy ? ride.end_xy[1] : 0;
  const isLoop = ride.is_loop !== false;

  svgElem.innerHTML = `
    <defs>
      <pattern id="gpsGrid" width="40" height="40" patternUnits="userSpaceOnUse">
        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255, 255, 255, 0.04)" stroke-width="1" />
      </pattern>
      <linearGradient id="routeNeonGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#10b981" />
        <stop offset="35%" stop-color="#fc5200" />
        <stop offset="70%" stop-color="#f59e0b" />
        <stop offset="100%" stop-color="#06b6d4" />
      </linearGradient>
      <filter id="routeGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <!-- Radar Grid Background -->
    <rect width="100%" height="100%" fill="url(#gpsGrid)" />
    
    <!-- Compass Rose -->
    <g transform="translate(425, 28)" opacity="0.6">
      <circle cx="0" cy="0" r="13" fill="rgba(0,0,0,0.5)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
      <path d="M 0 -10 L 3 -1 L -3 -1 Z" fill="#fc5200" />
      <path d="M 0 10 L 3 1 L -3 1 Z" fill="rgba(255,255,255,0.3)" />
      <text x="0" y="-12" text-anchor="middle" font-size="7.5" fill="#fc5200" font-weight="800">N</text>
    </g>

    <!-- Ambient Shadow & Luminous Core -->
    <path d="${ride.svg_path}" stroke="rgba(252, 82, 0, 0.3)" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round" />
    <path d="${ride.svg_path}" stroke="url(#routeNeonGrad)" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#routeGlow)" />

    <!-- Start Pin -->
    ${ride.start_xy ? `
      <circle cx="${startX}" cy="${startY}" r="10" fill="rgba(16, 185, 129, 0.25)" />
      <circle cx="${startX}" cy="${startY}" r="5.5" fill="#10b981" stroke="#ffffff" stroke-width="2" />
      <text x="${Math.min(380, Math.max(35, startX + 11))}" y="${Math.min(195, Math.max(20, startY + 4))}" 
            fill="#10b981" font-size="10" font-weight="700" letter-spacing="0.05em">START</text>
    ` : ''}

    <!-- Finish Pin (if not loop) -->
    ${ride.end_xy && !isLoop ? `
      <circle cx="${endX}" cy="${endY}" r="10" fill="rgba(6, 182, 212, 0.25)" />
      <circle cx="${endX}" cy="${endY}" r="5.5" fill="#06b6d4" stroke="#ffffff" stroke-width="2" />
      <text x="${Math.min(380, Math.max(35, endX + 11))}" y="${Math.min(195, Math.max(20, endY + 4))}" 
            fill="#06b6d4" font-size="10" font-weight="700" letter-spacing="0.05em">FINISH</text>
    ` : ''}
  `;
}

// Google Encoded Polyline Decoder
function decodePolyline(encoded) {
  if (!encoded || typeof encoded !== "string") return [];
  const points = [];
  let index = 0, len = encoded.length;
  let lat = 0, lng = 0;
  try {
    while (index < len) {
      let b, shift = 0, result = 0;
      do {
        b = encoded.charCodeAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
      lat += dlat;
      shift = 0;
      result = 0;
      do {
        b = encoded.charCodeAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
      lng += dlng;
      points.push([Number((lat / 1e5).toFixed(5)), Number((lng / 1e5).toFixed(5))]);
    }
  } catch (err) {
    console.warn("Polyline decode error:", err);
  }
  return points;
}

// Leaflet Map state & Base Tile Providers
let outdoorMap = null;
let outdoorPolylineLayer = null;
let outdoorStartMarker = null;
let outdoorEndMarker = null;
let outdoorCurrentTileLayer = null;
let savedMapBase = localStorage.getItem("preferred_map_base");
if (!savedMapBase || !["google_roads", "google_hybrid", "google_terrain"].includes(savedMapBase)) {
  savedMapBase = "google_roads";
  localStorage.setItem("preferred_map_base", "google_roads");
}
let outdoorBaseLayerName = savedMapBase;
let outdoorMapMode = "leaflet"; // "leaflet" (overlaid on real map by default) or "silhouette"

function getTileLayerConfig(layerName, googleApiKey = "") {
  const gKeyParam = googleApiKey ? `&key=${googleApiKey}` : "";
  switch (layerName) {
    case "google_hybrid":
      return {
        url: `https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}${gKeyParam}`,
        options: {
          maxZoom: 20,
          subdomains: "0123",
          attribution: "&copy; Google Maps"
        }
      };
    case "google_terrain":
      return {
        url: `https://mt{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}${gKeyParam}`,
        options: {
          maxZoom: 20,
          subdomains: "0123",
          attribution: "&copy; Google Maps"
        }
      };
    case "google_roads":
    default:
      return {
        url: `https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}${gKeyParam}`,
        options: {
          maxZoom: 20,
          subdomains: "0123",
          attribution: "&copy; Google Maps"
        }
      };
  }
}

function applyBaseTileLayer(layerName) {
  if (!outdoorMap) return;
  if (!["google_roads", "google_hybrid", "google_terrain"].includes(layerName)) {
    layerName = "google_roads";
  }
  if (outdoorCurrentTileLayer) {
    outdoorMap.removeLayer(outdoorCurrentTileLayer);
  }
  const googleKey = (state && state.googleMapsApiKey) || "";
  const cfg = getTileLayerConfig(layerName, googleKey);
  outdoorCurrentTileLayer = L.tileLayer(cfg.url, cfg.options).addTo(outdoorMap);
  outdoorBaseLayerName = layerName;
  localStorage.setItem("preferred_map_base", layerName);
  const selectElem = document.getElementById("selectMapBaseLayer");
  if (selectElem && selectElem.value !== layerName) {
    selectElem.value = layerName;
  }
}

// Render Leaflet Map (when toggled or active)
function initOrUpdateLeafletMap(ride) {
  if (!ride) return;
  let pts = ride.map_points || [];
  if ((!pts || pts.length < 2) && ride.summary_polyline) {
    pts = decodePolyline(ride.summary_polyline);
  }
  if (!pts || pts.length < 2) {
    console.warn("No map points available for ride:", ride.name);
    return;
  }
  if (typeof L === "undefined" || typeof L.map !== "function") {
    console.warn("Leaflet library not ready");
    return;
  }

  const mapContainer = document.getElementById("outdoorLeafletMap");
  if (!mapContainer) return;

  try {
    const initialCenter = pts[0] || [40.7115, -74.3724];

    if (!outdoorMap) {
      outdoorMap = L.map("outdoorLeafletMap", {
        center: initialCenter,
        zoom: 13,
        zoomControl: true,
        attributionControl: false,
        dragging: true,
        scrollWheelZoom: true,
        touchZoom: true
      });

      applyBaseTileLayer(outdoorBaseLayerName);
    }

    if (outdoorPolylineLayer) {
      outdoorMap.removeLayer(outdoorPolylineLayer);
      outdoorPolylineLayer = null;
    }
    if (outdoorStartMarker) {
      outdoorMap.removeLayer(outdoorStartMarker);
      outdoorStartMarker = null;
    }
    if (outdoorEndMarker) {
      outdoorMap.removeLayer(outdoorEndMarker);
      outdoorEndMarker = null;
    }

    // High-visibility dual stroke: glowing border + vivid Strava orange path
    const isDarkLayer = outdoorBaseLayerName === "dark";
    const haloColor = isDarkLayer ? "rgba(252, 82, 0, 0.45)" : "rgba(255, 255, 255, 0.95)";

    const glowLine = L.polyline(pts, {
      color: haloColor,
      weight: 7,
      opacity: 0.9,
      lineCap: "round",
      lineJoin: "round"
    });

    const mainLine = L.polyline(pts, {
      color: "#fc5200",
      weight: 4.5,
      opacity: 1.0,
      lineCap: "round",
      lineJoin: "round"
    });

    outdoorPolylineLayer = L.featureGroup([glowLine, mainLine]).addTo(outdoorMap);

    outdoorStartMarker = L.circleMarker(pts[0], {
      radius: 7.5,
      fillColor: "#10b981",
      color: "#ffffff",
      weight: 2.5,
      fillOpacity: 1
    }).bindPopup("<b>🟢 Start Location</b>").addTo(outdoorMap);

    outdoorEndMarker = L.circleMarker(pts[pts.length - 1], {
      radius: 7.5,
      fillColor: "#06b6d4",
      color: "#ffffff",
      weight: 2.5,
      fillOpacity: 1
    }).bindPopup("<b>🏁 Finish Location</b>").addTo(outdoorMap);

    const bounds = L.latLngBounds(pts);

    const applyBounds = () => {
      if (!outdoorMap || !bounds.isValid()) return;
      outdoorMap.invalidateSize(true);
      const cW = outdoorMap.getContainer().clientWidth;
      const cH = outdoorMap.getContainer().clientHeight;
      if (cW > 0 && cH > 0) {
        outdoorMap.fitBounds(bounds, {
          padding: [28, 28],
          maxZoom: 16,
          animate: false
        });
      }
    };

    applyBounds();

    // Schedule re-fits to guarantee alignment after DOM transition and tile rendering
    setTimeout(applyBounds, 120);
    setTimeout(applyBounds, 350);

    // Update external Google Maps navigation link
    const btnGoogle = document.getElementById("btnExternalGoogleMaps");
    if (btnGoogle && pts[0]) {
      const sLat = pts[0][0];
      const sLng = pts[0][1];
      const eLat = pts[pts.length - 1][0];
      const eLng = pts[pts.length - 1][1];
      btnGoogle.href = `https://www.google.com/maps/dir/?api=1&origin=${sLat},${sLng}&destination=${eLat},${eLng}&travelmode=bicycling`;
    }

  } catch (e) {
    console.warn("Leaflet error:", e);
  }
}

// Render Outdoor Ride Map Card
function renderOutdoorMap(ride) {
  const leafletDiv = document.getElementById("outdoorLeafletMap");
  const svgWrap = document.getElementById("outdoorMapSvgWrap");
  const svgElem = document.getElementById("outdoorMapSvg");
  const badgeMapDist = document.getElementById("badgeMapDist");
  const outdoorMapSubtext = document.getElementById("outdoorMapSubtext");
  const outdoorMapHeading = document.getElementById("outdoorMapHeading");
  const outdoorMapElevationProfile = document.getElementById("outdoorMapElevationProfile");
  const btnMapModeSilhouette = document.getElementById("btnMapModeSilhouette");
  const btnMapModeLeaflet = document.getElementById("btnMapModeLeaflet");

  if (!ride) return;

  const rDistMi = ride.distance_miles || (ride.distance_km ? parseFloat((ride.distance_km * 0.621371).toFixed(1)) : 0.0);
  const rElevFt = ride.elevation_gain_ft || (ride.elevation_gain_m ? Math.round(ride.elevation_gain_m * 3.28084) : 0);
  const rGradFtMi = rDistMi > 0 ? Math.round(rElevFt / rDistMi) : 0;

  if (badgeMapDist) {
    badgeMapDist.textContent = `${rDistMi} mi · ${rElevFt.toLocaleString()} ft elev`;
  }
  if (outdoorMapSubtext && ride.name) {
    outdoorMapSubtext.textContent = ride.name;
  }
  if (outdoorMapHeading) {
    outdoorMapHeading.textContent = `🧭 Course Orientation: ${ride.orientation_label || 'Closed Loop'}`;
  }
  if (outdoorMapElevationProfile) {
    outdoorMapElevationProfile.textContent = `⛰️ Gradient: ${rGradFtMi} ft/mi · Gain: ${rElevFt.toLocaleString()} ft`;
  }

  // Draw the high-contrast SVG silhouette for fallback/preview
  renderSvgRouteMap(ride, svgElem);

  // Set active mode
  if (outdoorMapMode === "leaflet") {
    if (svgWrap) svgWrap.style.display = "none";
    if (leafletDiv) leafletDiv.style.display = "block";
    if (btnMapModeSilhouette) btnMapModeSilhouette.classList.remove("active");
    if (btnMapModeLeaflet) btnMapModeLeaflet.classList.add("active");
    initOrUpdateLeafletMap(ride);
  } else {
    if (svgWrap) svgWrap.style.display = "flex";
    if (leafletDiv) leafletDiv.style.display = "none";
    if (btnMapModeSilhouette) btnMapModeSilhouette.classList.add("active");
    if (btnMapModeLeaflet) btnMapModeLeaflet.classList.remove("active");
  }
}

// Toggle Map Mode & Layer Switcher listeners
const btnMapModeSilhouette = document.getElementById("btnMapModeSilhouette");
const btnMapModeLeaflet = document.getElementById("btnMapModeLeaflet");
const selectMapBaseLayer = document.getElementById("selectMapBaseLayer");

if (btnMapModeSilhouette) {
  btnMapModeSilhouette.addEventListener("click", () => {
    outdoorMapMode = "silhouette";
    if (state.currentOutdoorRide) renderOutdoorMap(state.currentOutdoorRide);
  });
}
if (btnMapModeLeaflet) {
  btnMapModeLeaflet.addEventListener("click", () => {
    outdoorMapMode = "leaflet";
    if (state.currentOutdoorRide) renderOutdoorMap(state.currentOutdoorRide);
  });
}
if (selectMapBaseLayer) {
  selectMapBaseLayer.value = outdoorBaseLayerName;
  selectMapBaseLayer.addEventListener("change", (e) => {
    applyBaseTileLayer(e.target.value);
  });
}

// Center Route button click listener
const btnRecenterRoute = document.getElementById("btnRecenterRoute");
if (btnRecenterRoute) {
  btnRecenterRoute.addEventListener("click", () => {
    if (outdoorMap && outdoorPolylineLayer) {
      outdoorMap.invalidateSize(true);
      outdoorMap.fitBounds(outdoorPolylineLayer.getBounds(), { padding: [28, 28], maxZoom: 16 });
    } else if (state.currentOutdoorRide) {
      initOrUpdateLeafletMap(state.currentOutdoorRide);
    }
  });
}

// Header Mini Map Card click scrolls to full map
const outdoorHeaderThumbCard = document.getElementById("outdoorHeaderThumbCard");
if (outdoorHeaderThumbCard) {
  outdoorHeaderThumbCard.addEventListener("click", () => {
    const mapCard = document.getElementById("outdoorMapCard");
    if (mapCard) {
      mapCard.scrollIntoView({ behavior: "smooth", block: "center" });
      mapCard.style.borderColor = "#fc5200";
      setTimeout(() => {
        mapCard.style.borderColor = "";
      }, 1500);
    }
  });
}

// Render Outdoor Ride Details
function renderOutdoorRide(r) {
  if (!r) return;
  const rDistMi = r.distance_miles || (r.distance_km ? parseFloat((r.distance_km * 0.621371).toFixed(1)) : 0.0);
  const rElevFt = r.elevation_gain_ft || (r.elevation_gain_m ? Math.round(r.elevation_gain_m * 3.28084) : 0);
  const rGradFtMi = rDistMi > 0 ? Math.round(rElevFt / rDistMi) : 0;

  if (outdoorTitle) outdoorTitle.textContent = r.name || "Outdoor Ride";
  if (outdoorZoneBadge) outdoorZoneBadge.textContent = r.zone_badge || r.target_zone || "Aerobic Base";
  if (outdoorDurationBadge) outdoorDurationBadge.textContent = r.moving_time_formatted || `${r.moving_time_min}m`;
  if (outdoorDistBadge) outdoorDistBadge.textContent = `${rDistMi} mi`;
  if (outdoorElevBadge) outdoorElevBadge.textContent = `${rElevFt.toLocaleString()} ft Elev`;
  if (outdoorRationale) {
    outdoorRationale.textContent = r.ai_rationale || `Matched '${r.name || "Outdoor Ride"}' (${rDistMi} mi, ${rElevFt.toLocaleString()} ft elev) to today's ${r.zone_badge || r.target_zone || "training"} target.`;
  }
  
  // Update collapsed stage header tags for outdoor mode
  const colTitle = document.getElementById("collapsedWorkoutTitle");
  const colFocus = document.getElementById("collapsedWorkoutFocus");
  const colDur = document.getElementById("collapsedWorkoutDur");
  const colTss = document.getElementById("collapsedWorkoutTss");
  const colXss = document.getElementById("collapsedWorkoutXss");
  if (colTitle) colTitle.textContent = r.name || "Outdoor Ride";
  if (colFocus) colFocus.textContent = r.zone_badge || r.target_zone || "Aerobic Base";
  if (colDur) colDur.textContent = r.moving_time_formatted || `${r.moving_time_min}m`;
  if (colTss) colTss.textContent = `${rDistMi} mi`;
  if (colXss) colXss.style.display = "none";
  
  if (btnOpenStrava) {
    btnOpenStrava.href = r.strava_url || "https://www.strava.com";
  }

  // Header Hero Mini Map Preview
  const headerThumbSvg = document.getElementById("outdoorHeaderThumbSvg");
  if (headerThumbSvg) {
    renderHeaderMiniMap(r, headerThumbSvg);
  }

  // Telemetry boxes
  if (outdoorStatTime) outdoorStatTime.textContent = r.moving_time_formatted || `${r.moving_time_min}m`;
  if (outdoorStatDate) outdoorStatDate.textContent = `Ridden ${r.date_relative || 'previously'}`;
  if (outdoorStatDist) outdoorStatDist.textContent = `${rDistMi} mi`;
  if (outdoorStatMiles) outdoorStatMiles.textContent = `${rDistMi} miles`;
  if (outdoorStatElev) outdoorStatElev.textContent = `${rElevFt.toLocaleString()} ft`;
  if (outdoorStatGradient) outdoorStatGradient.textContent = `${rGradFtMi} ft/mi gradient`;
  if (outdoorStatWatts) outdoorStatWatts.textContent = r.average_watts ? `${r.average_watts} W` : "--";
  if (outdoorStatPctFtp) outdoorStatPctFtp.textContent = r.pct_ftp ? `${r.pct_ftp}% FTP` : "Paced";
  if (outdoorStatSuffer) outdoorStatSuffer.textContent = (r.suffer_score !== null && r.suffer_score !== undefined) ? r.suffer_score : "--";
  if (outdoorStatMatch) outdoorStatMatch.textContent = `${r.match_score || 85}%`;

  // Draw Course Map Preview
  renderOutdoorMap(r);

  // Coaching tips
  if (outdoorTipsGrid) {
    const tips = r.coaching_tips || [];
    if (tips.length > 0) {
      outdoorTipsGrid.innerHTML = tips.map(t => `
        <div class="outdoor-tip-card">
          <div class="outdoor-tip-heading">💡 ${t.title}</div>
          <div class="outdoor-tip-desc">${t.desc}</div>
        </div>
      `).join("");
    } else {
      outdoorTipsGrid.innerHTML = `
        <div class="outdoor-tip-card">
          <div class="outdoor-tip-heading">💡 Aerobic Pacing</div>
          <div class="outdoor-tip-desc">Keep climbs controlled in Zone 2 to support Whoop recovery.</div>
        </div>
      `;
    }
  }
}

// Render Outdoor Options Cards
function renderOutdoorOptions(options, activeId) {
  if (!outdoorOptionsGrid || !options || options.length === 0) return;

  outdoorOptionsGrid.innerHTML = options.map(opt => {
    const isActive = String(opt.id) === String(activeId);
    const thumbHtml = opt.thumbnail_svg ? `
      <div class="outdoor-option-thumb-wrap">
        <svg class="outdoor-option-thumb-svg" viewBox="0 0 110 48" preserveAspectRatio="xMidYMid meet">
          <path d="${opt.thumbnail_svg}" stroke="${isActive ? '#fc5200' : 'rgba(255,255,255,0.45)'}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
    ` : '';
    const carbPreview = formatCarbPreview(opt);
    const optDistMi = opt.distance_miles || (opt.distance_km ? parseFloat((opt.distance_km * 0.621371).toFixed(1)) : 0.0);
    const optElevFt = opt.elevation_gain_ft || (opt.elevation_gain_m ? Math.round(opt.elevation_gain_m * 3.28084) : 0);

    return `
      <div class="workout-option-card ${isActive ? 'active' : ''}" data-ride-id="${opt.id}" onclick="selectOutdoorOption('${opt.id}')" style="cursor:pointer;">
        <div class="workout-option-badge" style="color:#fc5200;">
          ${opt.badge || 'Route Option'}
        </div>
        <div class="workout-option-title">${opt.name}</div>
        ${thumbHtml}
        <div class="workout-option-meta">
          <span>⏱️ ${opt.moving_time_formatted}</span>
          <span>🚴 ${optDistMi} mi</span>
          <span>⛰️ ${optElevFt.toLocaleString()} ft</span>
          ${opt.average_watts ? `<span>⚡ ${opt.average_watts}W</span>` : ''}
          <span style="color:#10b981;font-weight:600;">🥪 ${carbPreview}</span>
        </div>
      </div>
    `;
  }).join("");

  outdoorOptionsGrid.querySelectorAll(".workout-option-card").forEach(card => {
    card.onclick = (e) => {
      e.preventDefault();
      const rideId = card.getAttribute("data-ride-id");
      if (rideId) {
        selectOutdoorOption(rideId);
      }
    };
  });
}

// Select Alternative Outdoor Option
async function selectOutdoorOption(rideId) {
  if (!rideId) return;
  const cleanId = String(rideId).trim();

  // 1. Immediately switch locally from state.outdoorOptions so the user gets instant feedback
  const localMatch = (state.outdoorOptions || []).find(o => String(o.id).trim() === cleanId);
  if (localMatch) {
    state.currentOutdoorRide = localMatch;
    state.activeOutdoorId = String(localMatch.id);
    renderOutdoorRide(localMatch);
    renderOutdoorOptions(state.outdoorOptions, state.activeOutdoorId);
    showToast(`Selected Route: ${localMatch.name}`);

    const fuelingPanel = document.getElementById("fuelingPlanPanel");
    if (fuelingPanel && fuelingPanel.style.display !== "none") {
      if (typeof positionFuelingPanel === "function") positionFuelingPanel("outdoor");
      loadFuelingPlanForRide(localMatch, true);
    }
  }

  // 2. Sync to server in background
  try {
    const res = await fetch("/api/workouts/select-outdoor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ride_id: cleanId })
    });
    const data = await res.json();
    if (data.success && data.active_ride) {
      state.currentOutdoorRide = data.active_ride;
      state.activeOutdoorId = String(data.active_ride.id);
      renderOutdoorRide(state.currentOutdoorRide);
      renderOutdoorOptions(state.outdoorOptions, state.activeOutdoorId);
      if (data.fueling_plan) {
        currentFuelingPlan = data.fueling_plan;
        const fuelingPanel = document.getElementById("fuelingPlanPanel");
        if (fuelingPanel && fuelingPanel.style.display !== "none") {
          renderFuelingPlan(data.fueling_plan);
        }
      }
    }
  } catch (err) {
    console.warn("Background outdoor select sync:", err);
  }
}

// Attach globally to window
window.selectOutdoorOption = selectOutdoorOption;

// 2. Fetch or Generate Workout
async function loadWorkout(duration = null, intensity = 0, userNote = "") {
  try {
    workoutRationale.innerHTML = "<em>Analyzing Whoop recovery and generating tailored intervals...</em>";
    const tempF = fuelingTempSlider ? parseInt(fuelingTempSlider.value, 10) : 74;
    const humPct = fuelingHumiditySlider ? parseInt(fuelingHumiditySlider.value, 10) : 50;

    let payload = {
      duration_min: duration,
      intensity_adjust: intensity,
      user_note: userNote,
      temp_f: tempF,
      humidity_pct: humPct,
      selected_option_id: state.activeOptionId
    };

    if (state.attachedRoute && state.attachedRoute.gpx_content) {
      payload.gpx_content = state.attachedRoute.gpx_content;
      payload.gpx_filename = state.attachedRoute.filename;
    }

    const res = await fetch("/api/workouts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const prevOptionId = state.activeOptionId;
    state.workoutOptions = data.options || [data.active_workout];
    const hasUserNote = Boolean(userNote && userNote.trim());
    
    const activeTargetId = (data.active_workout && data.active_workout.id) || state.activeOptionId || prevOptionId || "workout_primary";
    const matchingOption = state.workoutOptions.find(o => o.id === activeTargetId);
    
    if (matchingOption) {
      state.currentWorkout = matchingOption;
      state.activeOptionId = matchingOption.id;
      if (duration !== null || intensity !== 0 || hasUserNote) {
        state.activeCoachView = "prescribed";
      }
      if (typeof setWorkoutStageCollapsed === "function" && state.workoutStageCollapsed) {
        setWorkoutStageCollapsed(false);
      }
    } else {
      state.currentWorkout = data.active_workout || data;
      state.activeOptionId = (data.active_workout && data.active_workout.id) || "workout_primary";
    }
    state.currentDuration = (state.currentWorkout.duration_minutes !== undefined) ? state.currentWorkout.duration_minutes : duration;
    syncDurationPills(state.currentDuration);
    renderWorkout(state.currentWorkout);
    renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
    renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);

    if (data.is_custom_replaced && data.fueling_plan) {
      currentFuelingPlan = data.fueling_plan;
      renderFuelingPlan(data.fueling_plan);
      const fuelingPanel = document.getElementById("fuelingPlanPanel");
      if (fuelingPanel) fuelingPanel.style.display = "block";
      showToast(`✨ Plan active: ${state.currentWorkout.title}! Fueling strategy loaded.`);
    } else if (data.is_user_adapted || hasUserNote) {
      if (data.fueling_plan) {
        currentFuelingPlan = data.fueling_plan;
        const fuelingPanel = document.getElementById("fuelingPlanPanel");
        if (fuelingPanel && fuelingPanel.style.display !== "none") {
          renderFuelingPlan(data.fueling_plan);
        }
      }
      showToast(`✨ Workout adapted: ${state.currentWorkout.title} (${state.currentWorkout.duration_minutes}m)`);
    }
  } catch (err) {
    console.error("Failed to generate workout:", err);
    workoutRationale.textContent = "Error generating workout. Check server logs.";
  }
}

// Helpers for Power Targets & Zones (Canonical Coggan 7-Zone Power System)
function getPowerZone(pct) {
  if (pct < 55) {
    return { name: "Zone 1 Active Recovery (< 55%)", short: "Z1 Recovery", color: "#64748b", zoneNum: 1 };
  } else if (pct <= 75) {
    return { name: "Zone 2 Endurance (56–75%)", short: "Z2 Base", color: "#0052FF", zoneNum: 2 };
  } else if (pct <= 90) {
    if (pct >= 88) {
      return { name: "Zone 3 Tempo / Sweet Spot (88–90%)", short: "Sweet Spot", color: "#10B981", zoneNum: 3, isSweetSpot: true };
    }
    return { name: "Zone 3 Tempo (76–90%)", short: "Z3 Tempo", color: "#10B981", zoneNum: 3 };
  } else if (pct <= 105) {
    if (pct <= 94) {
      return { name: "Zone 4 Threshold / Sweet Spot (91–94%)", short: "Z4 Sweet Spot", color: "#F59E0B", zoneNum: 4, isSweetSpot: true };
    }
    return { name: "Zone 4 Lactate Threshold (91–105%)", short: "Z4 Threshold", color: "#F59E0B", zoneNum: 4 };
  } else if (pct <= 120) {
    return { name: "Zone 5 VO2 Max (106–120%)", short: "Z5 VO2 Max", color: "#FF5E00", zoneNum: 5 };
  } else if (pct <= 150) {
    return { name: "Zone 6 Anaerobic Capacity (121–150%)", short: "Z6 Anaerobic", color: "#8B5CF6", zoneNum: 6 };
  } else {
    return { name: "Zone 7 Neuromuscular Power (> 150%)", short: "Z7 Sprint", color: "#EC4899", zoneNum: 7 };
  }
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function formatDuration(seconds) {
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  return `${seconds}s`;
}

let canvasSegments = [];

// Render Workout Data & Draw Canvas
function renderWorkout(w) {
  if (!w) return;
  workoutTitle.textContent = w.title || "Prescribed Workout";
  workoutFocus.textContent = w.focus_area || "Adaptive";
  workoutDurationBadge.textContent = `${w.duration_minutes} MIN`;
  workoutTssBadge.textContent = `~${w.estimated_tss} TSS`;

  const activeEyebrow = document.getElementById("workoutActiveEyebrow");
  if (activeEyebrow) {
    if (w.title && (w.title.includes("Daily Target Achieved") || w.badge && w.badge.includes("Strain Met"))) {
      activeEyebrow.textContent = "✅ DAILY TARGET COMPLETED • REST & RECOVERY";
      activeEyebrow.style.color = "#10b981";
    } else if (w.pushed_to_zwift || w.synced_to_zwift) {
      activeEyebrow.textContent = "🚀 SENT TO ZWIFT • COACH'S CHOICE";
      activeEyebrow.style.color = "";
    } else if (w.badge && w.badge.includes("Coach's Choice")) {
      activeEyebrow.textContent = "⭐ ACTIVE PRESCRIPTION • COACH'S CHOICE";
      activeEyebrow.style.color = "";
    } else if (w.badge) {
      activeEyebrow.textContent = `${w.badge.toUpperCase()} • ACTIVE PRESCRIPTION`;
      activeEyebrow.style.color = "";
    } else {
      activeEyebrow.textContent = "⭐ ACTIVE PRESCRIPTION • COACH'S CHOICE";
      activeEyebrow.style.color = "";
    }
  }

  const xssBadge = document.getElementById("workoutXssBadge");
  const strainBreakdownBadge = document.getElementById("workoutStrainBreakdownBadge");
  if (xssBadge) {
    if (w.total_xss !== undefined && w.total_xss > 0) {
      xssBadge.textContent = `${w.total_xss} XSS`;
      xssBadge.title = `3-Tier Strain: ${w.low_xss || 0} Low • ${w.high_xss || 0} High • ${w.peak_xss || 0} Peak`;
      xssBadge.style.display = "inline-flex";
    } else {
      xssBadge.style.display = "none";
    }
  }
  if (strainBreakdownBadge) {
    if (w.low_xss !== undefined && (w.total_xss || 0) > 0) {
      strainBreakdownBadge.textContent = `${w.low_xss} Low • ${w.high_xss} High • ${w.peak_xss} Peak`;
      strainBreakdownBadge.style.display = "inline-flex";
    } else {
      strainBreakdownBadge.style.display = "none";
    }
  }

  // Update collapsed stage header tags
  const colTitle = document.getElementById("collapsedWorkoutTitle");
  const colFocus = document.getElementById("collapsedWorkoutFocus");
  const colDur = document.getElementById("collapsedWorkoutDur");
  const colTss = document.getElementById("collapsedWorkoutTss");
  const colXss = document.getElementById("collapsedWorkoutXss");
  if (colTitle) colTitle.textContent = w.title || "Prescribed Workout";
  if (colFocus) colFocus.textContent = w.focus_area || "Adaptive";
  if (colDur) colDur.textContent = `${w.duration_minutes} MIN`;
  if (colTss) colTss.textContent = `~${w.estimated_tss} TSS`;
  if (colXss) {
    if (w.total_xss !== undefined && w.total_xss > 0) {
      colXss.textContent = `${w.total_xss} XSS`;
      colXss.style.display = "inline-flex";
    } else {
      colXss.style.display = "none";
    }
  }

  workoutRationale.textContent = w.ai_rationale || w.description || "";

  // Show course map preview if route silhouette SVG exists
  const thumbCard = document.getElementById("workoutHeaderThumbCard");
  const thumbSvg = document.getElementById("workoutHeaderThumbSvg");
  if (thumbCard && thumbSvg) {
    if (w.svg_path) {
      thumbSvg.innerHTML = `<path d="${w.svg_path}" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`;
      thumbCard.style.display = "flex";
    } else {
      thumbCard.style.display = "none";
    }
  }

  syncDurationPills(w.duration_minutes);
  drawWorkoutGraph(w);
}

// Draw Interactive Interval Profile to Canvas
function drawWorkoutGraph(workout) {
  const canvas = intervalCanvas;
  if (!canvas) return;

  // Handle high-DPI retina displays
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const displayWidth = Math.max(Math.round(rect.width), 320);
  const displayHeight = Math.max(Math.round(rect.height), 160);
  canvas.width = displayWidth * dpr;
  canvas.height = displayHeight * dpr;

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const w = displayWidth;
  const h = displayHeight;

  ctx.clearRect(0, 0, w, h);

  // Flatten intervals (expanding repeats)
  const flattened = [];
  const intervals = (workout && workout.intervals) || [];

  for (const item of intervals) {
    const t = (item.type || "").toLowerCase();
    if (t === "repeats" || t === "intervalblock" || t === "intervals") {
      const reps = item.repeat || 1;
      for (let r = 0; r < reps; r++) {
        flattened.push({
          duration_sec: item.on_duration_sec,
          power_pct: item.on_power_pct,
          cadence: item.cadence || 92,
          name: `${item.name || "Interval"} (Rep ${r + 1}/${reps} Work)`,
          section_type: "Work",
          rep_num: r + 1,
          total_reps: reps
        });
        flattened.push({
          duration_sec: item.off_duration_sec,
          power_pct: item.off_power_pct,
          cadence: item.cadence_rest || 85,
          name: `${item.name || "Interval"} (Rep ${r + 1}/${reps} Recovery)`,
          section_type: "Rest",
          rep_num: r + 1,
          total_reps: reps
        });
      }
    } else if (t === "warmup") {
      flattened.push({
        duration_sec: item.duration_sec,
        power_low_pct: item.power_low_pct || 50,
        power_high_pct: item.power_high_pct || 75,
        cadence: item.cadence || 90,
        type: "ramp",
        name: item.name || "Progressive Warmup",
        section_type: "Warmup"
      });
    } else if (t === "cooldown") {
      flattened.push({
        duration_sec: item.duration_sec,
        power_low_pct: item.power_low_pct || 75,
        power_high_pct: item.power_high_pct || 45,
        cadence: item.cadence || 85,
        type: "ramp",
        name: item.name || "Cooling Spin-Down",
        section_type: "Cooldown"
      });
    } else {
      flattened.push({
        duration_sec: item.duration_sec,
        power_pct: item.power_pct || 65,
        cadence: item.cadence || 90,
        name: item.name || "Steady Endurance",
        section_type: "Steady"
      });
    }
  }

  const totalDuration = flattened.reduce((sum, item) => sum + (item.duration_sec || 0), 0) || 3600;
  const maxPowerPct = 125; // Scale ceiling

  // Build canvasSegments with calculated target watts, timing, and zones
  let cumulativeSec = 0;
  canvasSegments = flattened.map((seg, idx) => {
    const start_sec = cumulativeSec;
    const end_sec = start_sec + seg.duration_sec;
    cumulativeSec = end_sec;

    let zone, power_watts, low_watts, high_watts;
    if (seg.type === "ramp") {
      low_watts = Math.round(state.ftp * (seg.power_low_pct / 100));
      high_watts = Math.round(state.ftp * (seg.power_high_pct / 100));
      const avgPct = Math.round((seg.power_low_pct + seg.power_high_pct) / 2);
      zone = getPowerZone(avgPct);
    } else {
      power_watts = Math.round(state.ftp * (seg.power_pct / 100));
      zone = getPowerZone(seg.power_pct);
    }

    return {
      ...seg,
      index: idx,
      start_sec,
      end_sec,
      zone,
      power_watts,
      low_watts,
      high_watts,
      startX: 0,
      width: 0,
      endX: 0,
      y: 0,
      height: 0,
      topY: 0
    };
  });

  // Clamp selectedIntervalIndex if out of bounds
  if (state.selectedIntervalIndex !== null && state.selectedIntervalIndex >= canvasSegments.length) {
    state.selectedIntervalIndex = null;
  }

  const hasSelection = state.selectedIntervalIndex !== null && state.selectedIntervalIndex >= 0 && state.selectedIntervalIndex < canvasSegments.length;

  // Draw FTP target reference line (100% FTP)
  const isLightMode = true;
  const ftpLineY = h - (100 / maxPowerPct) * (h - 20) - 10;
  ctx.strokeStyle = isLightMode ? "rgba(17, 22, 37, 0.22)" : "rgba(255, 255, 255, 0.15)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(0, ftpLineY);
  ctx.lineTo(w, ftpLineY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Draw 100% FTP text
  ctx.fillStyle = isLightMode ? "rgba(17, 22, 37, 0.65)" : "rgba(255, 255, 255, 0.4)";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText(`100% FTP (${state.ftp}W)`, 6, ftpLineY - 4);

  if (canvasSegments.length === 0) {
    ctx.fillStyle = "#00C896";
    ctx.font = "bold 13px Outfit, Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("🛋️ Rest Day Directive • No Intervals Scheduled (Active Recovery / Off the Bike)", w / 2, h / 2 - 8);
    ctx.fillStyle = "#64748B";
    ctx.font = "12px Inter, sans-serif";
    ctx.fillText("Select '20-Min Active Recovery Flush' or 'Optional 45m Base' above if you wish to ride.", w / 2, h / 2 + 14);
    ctx.textAlign = "left";
    return;
  }

  let currentX = 0;

  for (let i = 0; i < canvasSegments.length; i++) {
    const seg = canvasSegments[i];
    const segWidth = (seg.duration_sec / totalDuration) * w;
    seg.startX = currentX;
    seg.width = segWidth;
    seg.endX = currentX + segWidth;

    const isSelected = hasSelection && state.selectedIntervalIndex === i;

    // Apply spotlight dimming to non-selected segments when an item is selected
    if (hasSelection && !isSelected) {
      ctx.globalAlpha = 0.35;
    } else {
      ctx.globalAlpha = 1.0;
    }

    if (seg.type === "ramp") {
      const yLow = h - (seg.power_low_pct / maxPowerPct) * (h - 20) - 10;
      const yHigh = h - (seg.power_high_pct / maxPowerPct) * (h - 20) - 10;
      seg.yLow = yLow;
      seg.yHigh = yHigh;
      seg.topY = Math.min(yLow, yHigh);

      ctx.beginPath();
      ctx.moveTo(currentX, h - 10);
      ctx.lineTo(currentX, yLow);
      ctx.lineTo(currentX + segWidth, yHigh);
      ctx.lineTo(currentX + segWidth, h - 10);
      ctx.closePath();

      const grad = ctx.createLinearGradient(currentX, Math.min(yLow, yHigh), currentX, h - 10);
      grad.addColorStop(0, seg.zone.color + "b3");
      grad.addColorStop(1, seg.zone.color + "1a");
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.strokeStyle = seg.zone.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(currentX, yLow);
      ctx.lineTo(currentX + segWidth, yHigh);
      ctx.stroke();

    } else {
      const p = seg.power_pct || 60;
      const barHeight = (p / maxPowerPct) * (h - 20);
      const y = h - barHeight - 10;
      seg.y = y;
      seg.height = barHeight;
      seg.topY = y;

      const col = seg.zone.color;
      ctx.fillStyle = col + "cc";
      ctx.fillRect(currentX + 0.5, y, Math.max(1, segWidth - 1), barHeight);

      // Top highlight border
      ctx.fillStyle = col;
      ctx.fillRect(currentX + 0.5, y, Math.max(1, segWidth - 1), 3);
    }

    currentX += segWidth;
  }

  ctx.globalAlpha = 1.0;

  // Draw glowing selection outline & top target badge for selected segment
  if (hasSelection) {
    const selSeg = canvasSegments[state.selectedIntervalIndex];
    ctx.save();
    ctx.shadowColor = selSeg.zone.color;
    ctx.shadowBlur = 14;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2.5;

    if (selSeg.type === "ramp") {
      ctx.beginPath();
      ctx.moveTo(selSeg.startX, h - 10);
      ctx.lineTo(selSeg.startX, selSeg.yLow);
      ctx.lineTo(selSeg.endX, selSeg.yHigh);
      ctx.lineTo(selSeg.endX, h - 10);
      ctx.closePath();
      ctx.stroke();
    } else {
      ctx.strokeRect(selSeg.startX + 0.5, selSeg.y, Math.max(2, selSeg.width - 1), selSeg.height);
    }
    ctx.restore();

    // Top indicator pill above selected segment
    const midX = Math.max(35, Math.min(w - 35, selSeg.startX + selSeg.width / 2));
    const label = selSeg.type === "ramp" ? `${selSeg.low_watts}→${selSeg.high_watts}W` : `${selSeg.power_watts}W`;

    ctx.save();
    ctx.font = "bold 10px sans-serif";
    const textWidth = ctx.measureText(label).width;
    const badgeW = textWidth + 14;
    const badgeH = 18;
    const badgeY = Math.max(4, selSeg.topY - badgeH - 6);
    const badgeX = Math.max(4, Math.min(w - badgeW - 4, midX - badgeW / 2));

    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = selSeg.zone.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4);
    } else {
      ctx.rect(badgeX, badgeY, badgeW, badgeH);
    }
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, badgeX + badgeW / 2, badgeY + badgeH / 2);
    ctx.restore();
  }

  // Update DOM Inspector & Table
  renderIntervalInspector();
  renderIntervalTable();
}

// Render Interval Inspector Panel
function renderIntervalInspector() {
  if (!intervalInspector) return;

  if (state.selectedIntervalIndex === null || !canvasSegments[state.selectedIntervalIndex]) {
    intervalInspector.innerHTML = `
      <div class="inspector-prompt">
        <span class="inspector-prompt-icon">👆</span>
        <div>
          <strong>Click any section in the profile graph above</strong> to inspect its power target (${state.ftp}W FTP), % FTP, duration, cadence, and training zone.
        </div>
      </div>
    `;
    return;
  }

  const seg = canvasSegments[state.selectedIntervalIndex];
  const total = canvasSegments.length;

  intervalInspector.innerHTML = `
    <div class="inspector-card">
      <div class="inspector-top">
        <div class="inspector-title-group">
          <span class="inspector-badge" style="background:${seg.zone.color}22;color:${seg.zone.color};border:1px solid ${seg.zone.color}55;">
            ${seg.zone.short}
          </span>
          <h3 class="inspector-title">${seg.name}</h3>
          <span class="inspector-timing">${formatTime(seg.start_sec)} – ${formatTime(seg.end_sec)} (${formatDuration(seg.duration_sec)})</span>
        </div>
        <div class="inspector-nav">
          <button class="btn btn-secondary" id="btnPrevSection" style="padding:0.25rem 0.55rem;font-size:0.75rem;" title="Previous section">◀ Prev</button>
          <span style="font-size:0.75rem;color:var(--text-muted);font-weight:600;min-width:32px;text-align:center;">${seg.index + 1} / ${total}</span>
          <button class="btn btn-secondary" id="btnNextSection" style="padding:0.25rem 0.55rem;font-size:0.75rem;" title="Next section">Next ▶</button>
          <button class="btn btn-secondary" id="btnCloseInspector" style="padding:0.25rem 0.5rem;font-size:0.75rem;" title="Deselect section">✕</button>
        </div>
      </div>

      <div class="inspector-metrics-grid">
        <div class="inspector-metric-card highlight">
          <div class="metric-label">TARGET POWER</div>
          <div class="metric-val" style="color:${seg.zone.color};">
            ${seg.type === 'ramp' ? `${seg.low_watts} → ${seg.high_watts}` : seg.power_watts} <span class="unit">W</span>
          </div>
          <div class="metric-sub">
            ${seg.type === 'ramp' ? `${seg.power_low_pct}% → ${seg.power_high_pct}% FTP (Progressive Ramp)` : `${seg.power_pct}% of FTP (${state.ftp}W Baseline)`}
          </div>
        </div>

        <div class="inspector-metric-card">
          <div class="metric-label">DURATION & TIMING</div>
          <div class="metric-val">${formatDuration(seg.duration_sec)}</div>
          <div class="metric-sub">${seg.duration_sec}s · From ${formatTime(seg.start_sec)} to ${formatTime(seg.end_sec)}</div>
        </div>

        <div class="inspector-metric-card">
          <div class="metric-label">TARGET CADENCE</div>
          <div class="metric-val">${seg.cadence || 90} <span class="unit">RPM</span></div>
          <div class="metric-sub">${(seg.cadence || 90) >= 100 ? 'High-Velocity Turnover' : ((seg.cadence || 90) <= 80 ? 'Low-Cadence Force' : 'Smooth Aerobic Cadence')}</div>
        </div>

        <div class="inspector-metric-card">
          <div class="metric-label">TRAINING ZONE</div>
          <div class="metric-val" style="color:${seg.zone.color};">${seg.zone.short}</div>
          <div class="metric-sub">${seg.zone.name}</div>
        </div>
      </div>
    </div>
  `;

  const btnPrev = document.getElementById("btnPrevSection");
  if (btnPrev) {
    btnPrev.onclick = () => selectIntervalSegment(Math.max(0, state.selectedIntervalIndex - 1));
  }
  const btnNext = document.getElementById("btnNextSection");
  if (btnNext) {
    btnNext.onclick = () => selectIntervalSegment(Math.min(total - 1, state.selectedIntervalIndex + 1));
  }
  const btnClose = document.getElementById("btnCloseInspector");
  if (btnClose) {
    btnClose.onclick = () => deselectIntervalSegment();
  }
}

// Select / Deselect Section Helpers
function selectIntervalSegment(index) {
  if (!canvasSegments || canvasSegments.length === 0) return;
  const clamped = Math.max(0, Math.min(canvasSegments.length - 1, index));
  state.selectedIntervalIndex = clamped;
  if (state.currentWorkout) {
    drawWorkoutGraph(state.currentWorkout);
  }
  const targetRow = sectionTableBody ? sectionTableBody.querySelector(`tr[data-idx="${clamped}"]`) : null;
  if (targetRow && sectionTableContainer && sectionTableContainer.style.display !== "none") {
    targetRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function deselectIntervalSegment() {
  state.selectedIntervalIndex = null;
  if (state.currentWorkout) {
    drawWorkoutGraph(state.currentWorkout);
  }
}

// Render Collapsible Interval Breakdown Table
function renderIntervalTable() {
  if (inspTotalSectionsCount) {
    inspTotalSectionsCount.textContent = canvasSegments.length;
  }
  if (!sectionTableBody) return;

  if (canvasSegments.length === 0) {
    sectionTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No intervals in current workout.</td></tr>`;
    return;
  }

  sectionTableBody.innerHTML = canvasSegments.map((seg, idx) => {
    const isActive = state.selectedIntervalIndex === idx;
    const powerStr = seg.type === "ramp" ? `${seg.low_watts} – ${seg.high_watts} W` : `${seg.power_watts} W`;
    const pctStr = seg.type === "ramp" ? `${seg.power_low_pct}% – ${seg.power_high_pct}%` : `${seg.power_pct}%`;
    return `
      <tr class="${isActive ? 'active-row' : ''}" data-idx="${idx}">
        <td style="color:var(--text-muted);font-weight:600;">${idx + 1}</td>
        <td style="font-weight:600;color:#f8fafc;">${seg.name}</td>
        <td style="color:var(--text-muted);">${formatTime(seg.start_sec)} – ${formatTime(seg.end_sec)}</td>
        <td>${formatDuration(seg.duration_sec)}</td>
        <td style="font-weight:700;color:${seg.zone.color};">${powerStr}</td>
        <td style="color:${seg.zone.color};font-weight:600;">${pctStr}</td>
        <td>${seg.cadence || 90} rpm</td>
        <td>
          <span class="badge-status" style="font-size:0.7rem;padding:0.15rem 0.45rem;color:${seg.zone.color};border-color:${seg.zone.color}66;background:${seg.zone.color}15;">
            ${seg.zone.short}
          </span>
        </td>
      </tr>
    `;
  }).join("");

  sectionTableBody.querySelectorAll("tr").forEach(tr => {
    tr.addEventListener("click", () => {
      const idx = parseInt(tr.dataset.idx, 10);
      if (!isNaN(idx)) {
        selectIntervalSegment(idx);
      }
    });
  });
}

// Attach Canvas Mouse & Touch Interactions
if (intervalCanvas) {
  intervalCanvas.addEventListener("mousemove", (e) => {
    if (!canvasSegments || canvasSegments.length === 0) return;
    const rect = intervalCanvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;

    const seg = canvasSegments.find(s => mouseX >= s.startX && mouseX <= s.endX);
    if (seg) {
      intervalCanvas.style.cursor = "pointer";
      if (intervalTooltip) {
        const powerText = seg.type === "ramp" ? `${seg.low_watts}–${seg.high_watts}W (${seg.power_low_pct}%–${seg.power_high_pct}%)` : `${seg.power_watts}W (${seg.power_pct}% FTP)`;
        intervalTooltip.innerHTML = `
          <div style="font-weight:700;margin-bottom:2px;color:#f8fafc;">${seg.name}</div>
          <div style="color:${seg.zone.color};font-weight:700;font-size:0.85rem;">⚡ ${powerText}</div>
          <div style="color:var(--text-muted);font-size:0.72rem;margin-top:2px;">⏱️ ${formatDuration(seg.duration_sec)} · ${seg.zone.short}${seg.cadence ? ` · ${seg.cadence} RPM` : ''}</div>
          <div style="font-size:0.68rem;color:#38bdf8;margin-top:2px;">(Click to view section)</div>
        `;
        intervalTooltip.style.display = "block";
        const tooltipX = Math.min(Math.max(60, mouseX), rect.width - 60);
        const tooltipY = Math.max(25, seg.topY - 8);
        intervalTooltip.style.left = `${tooltipX}px`;
        intervalTooltip.style.top = `${tooltipY}px`;
      }
    } else {
      intervalCanvas.style.cursor = "default";
      if (intervalTooltip) intervalTooltip.style.display = "none";
    }
  });

  intervalCanvas.addEventListener("mouseleave", () => {
    if (intervalTooltip) intervalTooltip.style.display = "none";
  });

  intervalCanvas.addEventListener("click", (e) => {
    if (!canvasSegments || canvasSegments.length === 0) return;
    const rect = intervalCanvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;

    const seg = canvasSegments.find(s => mouseX >= s.startX && mouseX <= s.endX);
    if (seg) {
      selectIntervalSegment(seg.index);
    }
  });

  // Touch device support
  intervalCanvas.addEventListener("touchstart", (e) => {
    if (!canvasSegments || canvasSegments.length === 0 || !e.touches || !e.touches[0]) return;
    const rect = intervalCanvas.getBoundingClientRect();
    const mouseX = e.touches[0].clientX - rect.left;
    const seg = canvasSegments.find(s => mouseX >= s.startX && mouseX <= s.endX);
    if (seg) {
      selectIntervalSegment(seg.index);
    }
  }, { passive: true });
}

// Collapsible Table Toggle Button Listener
if (btnToggleSectionTable) {
  btnToggleSectionTable.addEventListener("click", () => {
    if (!sectionTableContainer) return;
    const isHidden = sectionTableContainer.style.display === "none";
    sectionTableContainer.style.display = isHidden ? "block" : "none";
    btnToggleSectionTable.textContent = isHidden ?
      `📋 Hide Section Breakdown (${canvasSegments.length})` :
      `📋 View Section Breakdown (${canvasSegments.length})`;
    if (isHidden && state.selectedIntervalIndex !== null) {
      const activeRow = sectionTableBody ? sectionTableBody.querySelector(`tr[data-idx="${state.selectedIntervalIndex}"]`) : null;
      if (activeRow) activeRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

// Global Keyboard Navigation (Left / Right Arrows & Escape)
window.addEventListener("keydown", (e) => {
  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
  if (state.selectedIntervalIndex === null || !canvasSegments || canvasSegments.length === 0) return;

  if (e.key === "ArrowLeft") {
    e.preventDefault();
    selectIntervalSegment(Math.max(0, state.selectedIntervalIndex - 1));
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    selectIntervalSegment(Math.min(canvasSegments.length - 1, state.selectedIntervalIndex + 1));
  } else if (e.key === "Escape") {
    deselectIntervalSegment();
  }
});

// Window Resize Redraw
let resizeDebounce = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeDebounce);
  resizeDebounce = setTimeout(() => {
    if (state.currentWorkout) {
      drawWorkoutGraph(state.currentWorkout);
    }
  }, 100);
});

// 3. Event Listeners & Interactions

// Duration Pills
durPillGroup.addEventListener("click", (e) => {
  const pill = e.target.closest(".btn-pill");
  if (pill && durPillGroup.contains(pill)) {
    const dur = parseInt(pill.dataset.dur, 10);
    if (!Number.isNaN(dur)) {
      state.currentDuration = dur;
      state.selectedIntervalIndex = null;
      syncDurationPills(dur);
      loadWorkout(state.currentDuration, state.currentIntensity);
    }
  }
});

// Intensity Pills
intensityPillGroup.addEventListener("click", (e) => {
  const pill = e.target.closest(".btn-pill");
  if (pill && intensityPillGroup.contains(pill)) {
    intensityPillGroup.querySelectorAll(".btn-pill").forEach(b => b.classList.remove("active"));
    pill.classList.add("active");
    state.currentIntensity = parseInt(pill.dataset.intensity, 10);
    loadWorkout(state.currentDuration, state.currentIntensity);
  }
});

// Mode Switcher Listeners
if (tabModeIndoor) {
  tabModeIndoor.addEventListener("click", () => setTrainingMode("indoor"));
}
if (tabModeOutdoor) {
  tabModeOutdoor.addEventListener("click", () => setTrainingMode("outdoor"));
}

// Outdoor Duration Pills
if (outdoorDurPillGroup) {
  outdoorDurPillGroup.addEventListener("click", (e) => {
    const pill = e.target.closest(".btn-pill");
    if (pill && outdoorDurPillGroup.contains(pill)) {
      outdoorDurPillGroup.querySelectorAll(".btn-pill").forEach(b => b.classList.remove("active"));
      pill.classList.add("active");
      state.outdoorDuration = parseInt(pill.dataset.dur, 10);
      loadOutdoorRecommendation(state.outdoorDuration, inputOutdoorUserNote ? inputOutdoorUserNote.value.trim() : "");
    }
  });
}

// Outdoor Rematch / Regenerate Buttons
if (btnRegenerateOutdoor) {
  btnRegenerateOutdoor.addEventListener("click", async () => {
    const origText = btnRegenerateOutdoor.textContent;
    btnRegenerateOutdoor.textContent = "⏳ Matching...";
    btnRegenerateOutdoor.disabled = true;
    try {
      const noteVal = inputOutdoorUserNote ? inputOutdoorUserNote.value.trim() : "";
      await loadOutdoorRecommendation(state.outdoorDuration, noteVal);
      if (typeof setWorkoutStageCollapsed === "function" && state.workoutStageCollapsed) {
        setWorkoutStageCollapsed(false);
      }
      if (state.currentOutdoorRide) {
        showToast(`✨ Outdoor route matched: ${state.currentOutdoorRide.name}`);
      }
    } finally {
      btnRegenerateOutdoor.textContent = origText;
      btnRegenerateOutdoor.disabled = false;
    }
  });
}
if (btnRematchOutdoor) {
  btnRematchOutdoor.addEventListener("click", async () => {
    const origText = btnRematchOutdoor.textContent;
    btnRematchOutdoor.textContent = "⏳ Matching...";
    btnRematchOutdoor.disabled = true;
    try {
      const noteVal = inputOutdoorUserNote ? inputOutdoorUserNote.value.trim() : "";
      await loadOutdoorRecommendation(state.outdoorDuration, noteVal);
      if (state.currentOutdoorRide) {
        showToast(`✨ Outdoor route matched: ${state.currentOutdoorRide.name}`);
      }
    } finally {
      btnRematchOutdoor.textContent = origText;
      btnRematchOutdoor.disabled = false;
    }
  });
}
if (inputOutdoorUserNote && btnRegenerateOutdoor) {
  inputOutdoorUserNote.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      btnRegenerateOutdoor.click();
    }
  });
}



// Send to Zwift (Apple TV via Intervals.icu)
btnPushZwift.addEventListener("click", async () => {
  btnPushZwift.textContent = "⏳ Sending to Zwift...";
  btnPushZwift.disabled = true;

  try {
    const res = await fetch("/api/workouts/push-intervals-icu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const result = await res.json();

    if (result.success) {
      if (state.currentWorkout) {
        state.currentWorkout.pushed_to_zwift = true;
        state.currentWorkout.synced_to_zwift = true;
        state.currentWorkout.badge = "🚀 Sent to Zwift";
      }
      if (result.options && result.options.length > 0) {
        state.workoutOptions = result.options;
      } else if (state.workoutOptions && state.workoutOptions.length > 0) {
        const primOpt = state.workoutOptions.find(o => o.id === state.activeOptionId) || state.workoutOptions[0];
        if (primOpt) {
          primOpt.pushed_to_zwift = true;
          primOpt.synced_to_zwift = true;
          primOpt.badge = "🚀 Sent to Zwift";
        }
      }
      state.activeCoachView = "prescribed";
      showToast("🚀 Workout scheduled! Open Zwift — today's workout is ready on your home screen!");
      renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
      if (typeof renderWorkout === "function" && state.currentWorkout) {
        renderWorkout(state.currentWorkout);
      }
      if (typeof renderWorkoutOptions === "function" && state.workoutOptions) {
        renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
      }
    } else {
      showToast(`⚠️ ${result.error || 'Could not sync to Zwift.'}`);
      const errStr = (result.error || '').toLowerCase();
      if (errStr.includes("credential") || errStr.includes("re-entered") || errStr.includes("settings") || errStr.includes("api key")) {
        openSettingsModal();
      }
    }
  } catch (err) {
    showToast("⚠️ Network error syncing to Zwift.");
  } finally {
    btnPushZwift.textContent = "🚀 Send to Zwift";
    btnPushZwift.disabled = false;
  }
});

// Sync Strava manually
document.getElementById("btnSyncStrava").addEventListener("click", async () => {
  const btn = document.getElementById("btnSyncStrava");
  btn.textContent = "Syncing...";
  btn.disabled = true;
  try {
    const res = await fetch("/api/auth/sync/strava", { method: "POST" });
    let data;
    try {
      data = await res.json();
    } catch (_) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }
    await loadDashboard();
    await loadWorkout(state.currentDuration, state.currentIntensity, "");
    await loadDebrief();
    if (data.success && data.count > 0) {
      showToast(`✅ Synced ${data.count} Strava activities!`);
    } else if (data.success && data.count === 0) {
      showToast("ℹ️ Strava is up to date (no new activities).");
    } else if (data.auth_expired) {
      showToast("⚠️ Strava token expired. Please re-authorize or check Client Secret in Settings.");
    } else {
      showToast(`⚠️ Strava sync: ${data.error || "Unable to sync"}`);
    }
  } catch (err) {
    showToast("⚠️ Strava sync failed: " + (err.message || "Network error"));
  } finally {
    btn.textContent = "Sync Now";
    btn.disabled = false;
  }
});

// Sync All-Time Strava History (paginated background backfill)
const btnSyncStravaFull = document.getElementById("btnSyncStravaFull");
if (btnSyncStravaFull) {
  let stravaFullPollTimer = null;
  const pollStravaFullStatus = async () => {
    try {
      const sRes = await fetch("/api/auth/sync/strava/status");
      const sData = await sRes.json();
      if (sData.in_progress) {
        btnSyncStravaFull.textContent = `🔄 Syncing (${sData.activities_synced || 0})...`;
        btnSyncStravaFull.disabled = true;
        stravaFullPollTimer = setTimeout(pollStravaFullStatus, 1500);
        return;
      }
      btnSyncStravaFull.textContent = "🔄 Sync All-Time";
      btnSyncStravaFull.disabled = false;
      if (sData.error) {
        showToast(`⚠️ Strava all-time sync: ${sData.error}`);
      } else {
        showToast(`✅ All-time Strava sync complete (${sData.total_stored_activities || 0} total activities)!`);
      }
      if (typeof loadPowerSpiderweb === "function") {
        await loadPowerSpiderweb(typeof currentSpiderwebTimeframe !== "undefined" ? currentSpiderwebTimeframe : "30d");
      }
      if (typeof loadDashboard === "function") {
        await loadDashboard();
      }
    } catch (_) {
      btnSyncStravaFull.textContent = "🔄 Sync All-Time";
      btnSyncStravaFull.disabled = false;
    }
  };

  btnSyncStravaFull.addEventListener("click", async () => {
    if (stravaFullPollTimer) clearTimeout(stravaFullPollTimer);
    btnSyncStravaFull.textContent = "🔄 Starting...";
    btnSyncStravaFull.disabled = true;
    try {
      const res = await fetch("/api/auth/sync/strava/full", { method: "POST" });
      const data = await res.json();
      if (!data.success) {
        showToast(`⚠️ ${data.error || "Unable to start all-time Strava sync"}`);
        btnSyncStravaFull.textContent = "🔄 Sync All-Time";
        btnSyncStravaFull.disabled = false;
        return;
      }
      showToast("🔄 Syncing all-time Strava history in background...");
      stravaFullPollTimer = setTimeout(pollStravaFullStatus, 1200);
    } catch (err) {
      showToast("⚠️ Failed to start all-time sync: " + (err.message || "Network error"));
      btnSyncStravaFull.textContent = "🔄 Sync All-Time";
      btnSyncStravaFull.disabled = false;
    }
  });
}

// Sync Whoop manually
const btnSyncWhoop = document.getElementById("btnSyncWhoop");
if (btnSyncWhoop) {
  btnSyncWhoop.addEventListener("click", async () => {
    btnSyncWhoop.textContent = "Syncing...";
    btnSyncWhoop.disabled = true;
    try {
      const res = await fetch("/api/auth/sync/whoop", { method: "POST" });
      let data;
      try {
        data = await res.json();
      } catch (_) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      if (data.success && data.metrics) {
        showToast(`✅ Whoop Synced! Recovery: ${data.metrics.recovery_score}%, Sleep: ${data.metrics.sleep_performance}%`);
        await loadDashboard();
        await loadWorkout(state.currentDuration, state.currentIntensity);
        await loadDebrief();
      } else if (data.auth_expired) {
        showToast("⚠️ Whoop session expired. Please re-authorize in Settings.");
        openSettingsModal();
      } else {
        showToast(`⚠️ Whoop sync: ${data.error || 'Check Whoop connection'}`);
      }
    } catch (err) {
      showToast("⚠️ Whoop sync network error: " + (err.message || "Failed"));
    } finally {
      btnSyncWhoop.textContent = "🔄 Sync Whoop";
      btnSyncWhoop.disabled = false;
    }
  });
}
// ========================================================
// PowerSync — "Speed & Summit" High-Contrast Light Theme
// ========================================================
const currentThemeMode = "light";

function applyTheme(mode = "light", persist = false) {
  document.documentElement.setAttribute("data-theme", "light");
  document.documentElement.setAttribute("data-theme-mode", "light");
  try {
    localStorage.setItem("powersync_theme_mode", "light");
  } catch (_) {}
}

function initThemeSystem() {
  applyTheme("light", false);
}

// Coaching Directives & Persistent Preferences UI
function renderCoachingDirectives(directives) {
  const listEl = document.getElementById("preferencesDirectivesList");
  if (!listEl) return;
  listEl.innerHTML = "";
  if (!directives || directives.length === 0) {
    listEl.innerHTML = `<div style="font-size:0.75rem;color:var(--text-muted);font-style:italic;">No custom directives added yet. Add one below or tell your coach in chat!</div>`;
    return;
  }
  directives.forEach((d, idx) => {
    const item = document.createElement("div");
    item.style.cssText = "display:flex;justify-content:space-between;align-items:center;background:#F4F7FA;border:1px solid #DCE4EE;padding:0.35rem 0.55rem;border-radius:6px;font-size:0.75rem;color:#111625;gap:0.5rem;";
    
    const textSpan = document.createElement("span");
    textSpan.style.cssText = "flex:1;line-height:1.35;";
    textSpan.textContent = `• ${d}`;
    
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.innerHTML = "✕";
    delBtn.title = "Delete directive";
    delBtn.style.cssText = "background:none;border:none;color:#ef4444;font-size:0.8rem;cursor:pointer;padding:0 0.3rem;line-height:1;";
    delBtn.addEventListener("click", async () => {
      try {
        const res = await fetch(`/api/settings/coaching-preferences/directives/${idx}`, { method: "DELETE" });
        const resData = await res.json();
        if (resData.success) {
          showToast("🗑️ Directive removed");
          renderCoachingDirectives(resData.directives);
        }
      } catch (e) {
        console.error("Failed to delete directive:", e);
      }
    });

    item.appendChild(textSpan);
    item.appendChild(delBtn);
    listEl.appendChild(item);
  });
}

async function loadAndRenderCoachingPreferences() {
  try {
    const res = await fetch("/api/settings/coaching-preferences");
    const data = await res.json();
    if (data.success && data.preferences) {
      state.coachingPreferences = data.preferences;
      renderCoachingDirectives(data.preferences.directives || []);
    }
  } catch (err) {
    console.warn("Failed to load coaching preferences:", err);
  }
}

// Settings Modal Handlers
function openSettingsModal() {
  if (!currentAthleteUser || currentAthleteUser.is_guest) {
    showToast("🔒 Please sign in to access Settings");
    openAuthModal();
    return;
  }
  loadAndRenderCoachingPreferences();
  fetch("/api/settings")
    .then(async r => {
      if (!r.ok) {
        if (r.status === 401) {
          showToast("🔒 Please sign in to access Settings");
          openAuthModal();
        }
        return null;
      }
      return r.json();
    })
    .then(s => {
      if (!s) return;
      document.getElementById("settingIntervalsAthleteId").value = s.intervals_athlete_id || "";
      const intervalsKeyInput = document.getElementById("settingIntervalsApiKey");
      if (intervalsKeyInput) {
        intervalsKeyInput.value = "";
        intervalsKeyInput.placeholder = s.intervals_icu_api_key_set ? "•••••••••••• (Saved on server — leave blank to keep)" : "Enter Intervals.icu API Key";
      }

      const googleClientIdInput = document.getElementById("settingGoogleClientId");
      if (googleClientIdInput) {
        googleClientIdInput.value = "";
        googleClientIdInput.placeholder = s.google_client_id_set ? "•••••••••••• (Saved on server — leave blank to keep)" : "Enter Google OAuth Client ID";
      }
      const googleSecretInput = document.getElementById("settingGoogleClientSecret");
      if (googleSecretInput) {
        googleSecretInput.value = "";
        googleSecretInput.placeholder = s.google_client_secret_set ? "•••••••••••• (Saved on server — leave blank to keep)" : "Enter Google Client Secret";
      }

      const ownerInput = document.getElementById("settingPrimaryOwnerEmail");
      const ownerPill = document.getElementById("ownerLockStatusPill");
      if (ownerInput) ownerInput.value = s.primary_owner_email || "";
      if (ownerPill) {
        if (s.primary_owner_email || s.primary_owner_locked) {
          ownerPill.textContent = "Lock Active";
          ownerPill.style.background = "rgba(16,185,129,0.15)";
          ownerPill.style.color = "#10b981";
        } else {
          ownerPill.textContent = "Unset (Open)";
          ownerPill.style.background = "rgba(234,179,8,0.15)";
          ownerPill.style.color = "#fde047";
        }
      }

      document.getElementById("settingFtp").value = s.athlete_ftp || 250;
      document.getElementById("settingMaxHr").value = s.athlete_max_hr || 185;
      const weightLbsInput = document.getElementById("settingAthleteWeightLbs");
      if (weightLbsInput) {
        const wLbs = s.athlete_weight_lbs !== undefined ? s.athlete_weight_lbs : Number(((s.athlete_weight_kg || 70.0) * 2.20462262185).toFixed(1));
        weightLbsInput.value = Number(wLbs).toFixed(1);
      }
      updateSettingsLiveWkgBadge();
      const wPrimeInput = document.getElementById("settingAthleteWPrime");
      if (wPrimeInput) wPrimeInput.value = s.athlete_w_prime_kj !== undefined ? s.athlete_w_prime_kj : 20.0;
      const peakPowerInput = document.getElementById("settingAthletePeakPower");
      if (peakPowerInput) peakPowerInput.value = s.athlete_peak_power_watts !== undefined ? s.athlete_peak_power_watts : 1050;
      
      const prefMapLayerEl = document.getElementById("settingPreferredMapLayer");
      if (prefMapLayerEl) {
        prefMapLayerEl.value = (s.preferred_map_layer && ["google_roads", "google_hybrid", "google_terrain"].includes(s.preferred_map_layer)) ? s.preferred_map_layer : (outdoorBaseLayerName || "google_roads");
      }

      document.getElementById("settingDemoMode").checked = s.demo_mode;
      
      const progGoalEl = document.getElementById("settingProgramGoal");
      if (progGoalEl) {
        const currentGoal = (s.program_goal || "ALL_ROUNDER").toUpperCase();
        progGoalEl.value = currentGoal;
        if (!progGoalEl.value && progGoalEl.options.length > 0) {
          progGoalEl.selectedIndex = 0;
        }
      }
      const progTargetFtpEl = document.getElementById("settingProgramTargetFtp");
      if (progTargetFtpEl) progTargetFtpEl.value = s.program_target_ftp || 265;
      const progTargetDateEl = document.getElementById("settingProgramTargetDate");
      if (progTargetDateEl) progTargetDateEl.value = s.program_target_date || "";
      const progWeeklyTssEl = document.getElementById("settingProgramWeeklyTss");
      if (progWeeklyTssEl) progWeeklyTssEl.value = s.program_weekly_tss_target || 360;
      const progWeeklyXssEl = document.getElementById("settingProgramWeeklyXss");
      if (progWeeklyXssEl) progWeeklyXssEl.value = s.program_weekly_xss_target || s.program_weekly_tss_target || 360;

      // Strava Connection & Buttons
      const stravaStat = document.getElementById("stravaConnStatus");
      const btnConnectStrava = document.getElementById("btnConnectStravaOAuth");
      const btnDisconnectStrava = document.getElementById("btnDisconnectStrava");
      if (stravaStat) {
        stravaStat.textContent = s.strava_connected ? "Connected ✅" : "Not connected";
        stravaStat.style.color = s.strava_connected ? "#10b981" : "#94a3b8";
      }
      if (btnConnectStrava) {
        btnConnectStrava.textContent = s.strava_connected ? "🔄 Reconnect Strava" : "🔗 Connect Strava";
      }
      if (btnDisconnectStrava) {
        btnDisconnectStrava.style.display = s.strava_connected ? "inline-block" : "none";
      }

      // Whoop Connection & Buttons
      const whoopStat = document.getElementById("whoopConnStatus");
      const btnConnectWhoop = document.getElementById("btnConnectWhoopOAuth");
      const btnDisconnectWhoop = document.getElementById("btnDisconnectWhoop");
      if (whoopStat) {
        whoopStat.textContent = s.whoop_connected ? "Connected ✅" : "Not connected";
        whoopStat.style.color = s.whoop_connected ? "#10b981" : "#94a3b8";
      }
      if (btnConnectWhoop) {
        btnConnectWhoop.textContent = s.whoop_connected ? "🔄 Reconnect Whoop" : "🔗 Connect Whoop";
      }
      if (btnDisconnectWhoop) {
        btnDisconnectWhoop.style.display = s.whoop_connected ? "inline-block" : "none";
      }

      // Wyze Smart Scale Connection & Fields
      renderWyzeSettingsSummary(s);

      // Intervals.icu / Zwift Connection Status
      const intervalsStat = document.getElementById("intervalsConnStatus");
      if (intervalsStat) {
        const isIntervalsConfigured = Boolean(s.intervals_athlete_id && s.intervals_icu_api_key_set);
        intervalsStat.textContent = isIntervalsConfigured ? "Connected ✅" : "Not configured";
        intervalsStat.style.color = isIntervalsConfigured ? "#10b981" : "#94a3b8";
      }

      // Gemini AI Engine Status
      const isGeminiSet = Boolean(s.gemini_api_key_set);
      updateGeminiConnectedIndicators(isGeminiSet);
      checkCoachGeminiStatus();

      settingsModal.classList.add("open");
    });
}

function updateSettingsLiveWkgBadge() {
  const badge = document.getElementById("settingLiveWkgBadge");
  if (!badge) return;
  const ftpVal = parseFloat(document.getElementById("settingFtp")?.value) || state.ftp || 250;
  const lbsVal = parseFloat(document.getElementById("settingAthleteWeightLbs")?.value) || state.weightLbs || 154.3;
  const kgVal = Math.max(30.0, lbsVal / 2.20462262185);
  const wkg = (ftpVal / kgVal).toFixed(2);
  badge.textContent = `${wkg} W/kg`;
}

function renderWyzeSettingsSummary(s) {
  const wyzeEmailEl = document.getElementById("settingWyzeEmail");
  const wyzePassEl = document.getElementById("settingWyzePassword");
  const wyzeKeyIdEl = document.getElementById("settingWyzeKeyId");
  const wyzeApiKeyEl = document.getElementById("settingWyzeApiKey");
  const wyzeTotpEl = document.getElementById("settingWyzeTotp");
  const wyzeStat = document.getElementById("wyzeConnStatus");
  const btnConnectWyze = document.getElementById("btnConnectWyze");
  const btnSyncWyze = document.getElementById("btnSyncWyzeScale");
  const btnDisconnectWyze = document.getElementById("btnDisconnectWyze");
  const summaryBox = document.getElementById("wyzeScaleSummaryBox");
  const feedbackEl = document.getElementById("wyzeConnectFeedback");

  if (feedbackEl) feedbackEl.style.display = "none";
  if (wyzeEmailEl && s.wyze_email !== undefined) wyzeEmailEl.value = s.wyze_email || "";
  if (wyzeKeyIdEl && s.wyze_key_id !== undefined) wyzeKeyIdEl.value = s.wyze_key_id || "";
  if (wyzePassEl) {
    wyzePassEl.value = "";
    wyzePassEl.placeholder = s.wyze_password_set ? "•••••••••••• (Saved on server — leave blank to keep)" : "Wyze password";
  }
  if (wyzeApiKeyEl) {
    wyzeApiKeyEl.value = "";
    wyzeApiKeyEl.placeholder = s.wyze_api_key_set ? "•••••••••••• (Saved on server — leave blank to keep)" : "Wyze API Key";
  }
  if (wyzeTotpEl) {
    wyzeTotpEl.value = "";
    wyzeTotpEl.placeholder = s.wyze_totp_secret_set ? "•••••••••••• (TOTP Secret saved — or enter 6-digit code)" : "6-digit code (or base32 TOTP secret for automatic 2FA)";
  }

  const isConnected = Boolean(s.wyze_connected || (s.wyze_summary && s.wyze_summary.connected));
  if (wyzeStat) {
    wyzeStat.textContent = isConnected ? "Connected ✅" : "Not connected";
    wyzeStat.style.color = isConnected ? "#10b981" : "#94a3b8";
  }
  if (btnConnectWyze) {
    btnConnectWyze.textContent = isConnected ? "🔑 Update & Re-Sync Wyze" : "🔗 Connect & Sync Wyze Scale";
  }
  if (btnSyncWyze) {
    btnSyncWyze.style.display = isConnected ? "inline-block" : "none";
  }
  if (btnDisconnectWyze) {
    btnDisconnectWyze.style.display = isConnected ? "inline-block" : "none";
  }

  const latest = s.wyze_summary && s.wyze_summary.latest ? s.wyze_summary.latest : null;
  if (summaryBox) {
    if (latest && latest.weight_lbs) {
      summaryBox.style.display = "block";
      const ftpVal = parseFloat(document.getElementById("settingFtp")?.value) || s.athlete_ftp || state.ftp || 250;
      const kgVal = latest.weight_kg || (latest.weight_lbs / 2.20462262185);
      const wkg = (ftpVal / Math.max(30.0, kgVal)).toFixed(2);
      const wText = document.getElementById("wyzeLatestWeightText");
      const wkgText = document.getElementById("wyzeLatestWkgText");
      const compText = document.getElementById("wyzeLatestCompText");
      const dateText = document.getElementById("wyzeLatestDateText");
      if (wText) wText.textContent = `⚖️ ${Number(latest.weight_lbs).toFixed(1)} lbs`;
      if (wkgText) wkgText.textContent = `⚡ ${wkg} W/kg`;
      if (compText) {
        const compParts = [];
        if (latest.body_fat_pct !== null && latest.body_fat_pct !== undefined) compParts.push(`${Number(latest.body_fat_pct).toFixed(1)}% Body Fat`);
        if (latest.muscle_mass_lbs !== null && latest.muscle_mass_lbs !== undefined) compParts.push(`${Number(latest.muscle_mass_lbs).toFixed(1)} lbs Muscle`);
        if (latest.body_water_pct !== null && latest.body_water_pct !== undefined) compParts.push(`${Number(latest.body_water_pct).toFixed(1)}% Water`);
        compText.textContent = compParts.length ? `(${compParts.join(" · ")})` : "";
      }
      if (dateText) {
        const iso = latest.measured_at_iso ? latest.measured_at_iso.replace("T", " ").substring(0, 16) : "Synced";
        dateText.textContent = `Last weigh-in: ${iso}`;
      }
    } else {
      summaryBox.style.display = "none";
    }
  }
}

function closeSettingsModal() {
  settingsModal.classList.remove("open");
}

btnOpenSettings.addEventListener("click", openSettingsModal);
if (btnAdjustGoal) btnAdjustGoal.addEventListener("click", openSettingsModal);
document.getElementById("btnEditFtp").addEventListener("click", openSettingsModal);
btnCloseSettings.addEventListener("click", closeSettingsModal);
btnCancelSettings.addEventListener("click", closeSettingsModal);

const settingWeightLbsEl = document.getElementById("settingAthleteWeightLbs");
if (settingWeightLbsEl) {
  settingWeightLbsEl.addEventListener("input", updateSettingsLiveWkgBadge);
}

// Coaching Preferences Directives Add & Reset Event Listeners
const btnAddDirective = document.getElementById("btnAddDirective");
const inputNewDirective = document.getElementById("inputNewDirective");
if (btnAddDirective && inputNewDirective) {
  btnAddDirective.addEventListener("click", async () => {
    const text = inputNewDirective.value.trim();
    if (!text) return;
    try {
      const res = await fetch("/api/settings/coaching-preferences/directives", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directive: text })
      });
      const data = await res.json();
      if (data.success) {
        inputNewDirective.value = "";
        showToast("🎯 New coaching directive saved!");
        renderCoachingDirectives(data.directives);
      }
    } catch (err) {
      console.error("Failed to add directive:", err);
    }
  });

  inputNewDirective.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      btnAddDirective.click();
    }
  });
}

const btnResetCoachingPreferences = document.getElementById("btnResetCoachingPreferences");
if (btnResetCoachingPreferences) {
  btnResetCoachingPreferences.addEventListener("click", async () => {
    if (!confirm("Reset all coaching schedule rules and directives to default athlete settings?")) return;
    try {
      const res = await fetch("/api/settings/coaching-preferences/reset", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        showToast("↺ Coaching preferences reset to defaults");
        if (data.preferences) {
          renderCoachingDirectives(data.preferences.directives || []);
        }
      }
    } catch (err) {
      console.error("Failed to reset preferences:", err);
    }
  });
}

// Clickable badges & banner
const btnBannerOpenConnect = document.getElementById("btnBannerOpenConnect");
if (btnBannerOpenConnect) btnBannerOpenConnect.addEventListener("click", openSettingsModal);
document.getElementById("badgeWhoop").addEventListener("click", openSettingsModal);
document.getElementById("badgeStrava").addEventListener("click", openSettingsModal);
const badgeWyzeNav = document.getElementById("badgeWyze");
if (badgeWyzeNav) badgeWyzeNav.addEventListener("click", openSettingsModal);
document.getElementById("badgeZwift").addEventListener("click", openSettingsModal);
const badgeGeminiNav = document.getElementById("badgeGemini");
if (badgeGeminiNav) badgeGeminiNav.addEventListener("click", openSettingsModal);
const badgeCardGeminiEl = document.getElementById("badgeCardGeminiStatus");
if (badgeCardGeminiEl) {
  badgeCardGeminiEl.style.cursor = "pointer";
  badgeCardGeminiEl.addEventListener("click", openSettingsModal);
}
const footerPillGeminiEl = document.getElementById("footerPillGemini");
if (footerPillGeminiEl) {
  footerPillGeminiEl.style.cursor = "pointer";
  footerPillGeminiEl.addEventListener("click", openSettingsModal);
}

// Connected Services Dropdown Toggle & Accessibility
function initConnectionsDropdown() {
  const wrapper = document.getElementById("connectionsDropdownWrapper");
  const btn = document.getElementById("btnConnectionsDropdown");
  const menu = document.getElementById("connectionsDropdownMenu");
  const btnManage = document.getElementById("btnDropdownManage");

  if (!wrapper || !btn || !menu) return;

  function setDropdownOpen(isOpen) {
    wrapper.classList.toggle("is-open", isOpen);
    btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  // Prevent multiple bindings
  if (wrapper._connectionsDropdownInit) return;
  wrapper._connectionsDropdownInit = true;

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const currentlyOpen = wrapper.classList.contains("is-open");
    setDropdownOpen(!currentlyOpen);
  });

  if (btnManage) {
    btnManage.addEventListener("click", (e) => {
      e.stopPropagation();
      setDropdownOpen(false);
      if (typeof openSettingsModal === "function") openSettingsModal();
    });
  }

  // Close when clicking outside
  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) {
      setDropdownOpen(false);
    }
  });

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && wrapper.classList.contains("is-open")) {
      setDropdownOpen(false);
      btn.focus();
    }
  });

  // Clicking an item in the dropdown closes dropdown
  const items = menu.querySelectorAll(".connections-dropdown-item");
  items.forEach(item => {
    item.addEventListener("click", () => {
      setDropdownOpen(false);
    });
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setDropdownOpen(false);
        item.click();
      }
    });
  });
}
initConnectionsDropdown();

// Direct OAuth connect buttons & Disconnect listeners
const stravaOAuthBtn = document.getElementById("btnConnectStravaOAuth");
if (stravaOAuthBtn) {
  stravaOAuthBtn.addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Redirecting to Strava...");
    const tok = localStorage.getItem("powersync_token");
    window.location.href = tok ? `/api/auth/strava/login?token=${encodeURIComponent(tok)}` : "/api/auth/strava/login";
  });
}

const btnDisconnectStrava = document.getElementById("btnDisconnectStrava");
if (btnDisconnectStrava) {
  btnDisconnectStrava.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to disconnect Strava?")) return;
    try {
      await fetch("/api/auth/disconnect/strava", { method: "POST" });
      showToast("Strava disconnected");
      openSettingsModal();
      loadDashboard();
    } catch (err) {
      showToast("Error disconnecting Strava");
    }
  });
}

const whoopOAuthBtn = document.getElementById("btnConnectWhoopOAuth");
if (whoopOAuthBtn) {
  whoopOAuthBtn.addEventListener("click", (e) => {
    e.preventDefault();
    showToast("Redirecting to Whoop...");
    const tok = localStorage.getItem("powersync_token");
    window.location.href = tok ? `/api/auth/whoop/login?token=${encodeURIComponent(tok)}` : "/api/auth/whoop/login";
  });
}

const btnDisconnectWhoop = document.getElementById("btnDisconnectWhoop");
if (btnDisconnectWhoop) {
  btnDisconnectWhoop.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to disconnect Whoop?")) return;
    try {
      await fetch("/api/auth/disconnect/whoop", { method: "POST" });
      showToast("Whoop disconnected");
      openSettingsModal();
      loadDashboard();
    } catch (err) {
      showToast("Error disconnecting Whoop");
    }
  });
}

// Wyze Smart Scale Connect, Sync & Disconnect Listeners
const btnConnectWyze = document.getElementById("btnConnectWyze");
if (btnConnectWyze) {
  btnConnectWyze.addEventListener("click", async () => {
    const email = document.getElementById("settingWyzeEmail")?.value.trim() || "";
    const password = document.getElementById("settingWyzePassword")?.value.trim() || "";
    const keyId = document.getElementById("settingWyzeKeyId")?.value.trim() || "";
    const apiKey = document.getElementById("settingWyzeApiKey")?.value.trim() || "";
    const totpRaw = document.getElementById("settingWyzeTotp")?.value.trim() || "";
    const feedbackEl = document.getElementById("wyzeConnectFeedback");

    const isSixDigitCode = /^\d{6}$/.test(totpRaw);
    const payload = {
      email: email || undefined,
      password: (password && !password.includes("•")) ? password : undefined,
      key_id: keyId || undefined,
      api_key: (apiKey && !apiKey.includes("•")) ? apiKey : undefined,
      totp_code: isSixDigitCode ? totpRaw : undefined,
      totp_secret: (!isSixDigitCode && totpRaw && !totpRaw.includes("•")) ? totpRaw : undefined
    };

    const origText = btnConnectWyze.textContent;
    btnConnectWyze.textContent = "⏳ Connecting to Wyze...";
    btnConnectWyze.disabled = true;
    if (feedbackEl) {
      feedbackEl.style.display = "block";
      feedbackEl.style.color = "var(--text-secondary)";
      feedbackEl.style.borderColor = "var(--border-color)";
      feedbackEl.textContent = "Authenticating with Wyze Cloud API and discovering Smart Scale records...";
    }

    try {
      const res = await fetch("/api/auth/wyze/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        const latest = data.summary && data.summary.latest ? data.summary.latest : (data.sync && data.sync.latest ? data.sync.latest : null);
        if (latest && latest.weight_lbs) {
          const wInput = document.getElementById("settingAthleteWeightLbs");
          if (wInput) wInput.value = Number(latest.weight_lbs).toFixed(1);
          updateSettingsLiveWkgBadge();
        }
        renderWyzeSettingsSummary({
          wyze_email: email,
          wyze_key_id: keyId,
          wyze_password_set: true,
          wyze_api_key_set: true,
          wyze_connected: true,
          wyze_summary: data.summary
        });
        if (feedbackEl) {
          feedbackEl.style.display = "block";
          feedbackEl.style.color = "#00C896";
          feedbackEl.style.borderColor = "rgba(0,200,150,0.4)";
          feedbackEl.textContent = `✅ ${data.message || "Connected and synced Wyze Smart Scale!"}`;
        }
        showToast(`⚖️ ${data.message || "Wyze Smart Scale connected!"}`);
        await loadDashboard();
        if (typeof loadPowerSpiderweb === "function") {
          await loadPowerSpiderweb(typeof currentSpiderwebTimeframe !== "undefined" ? currentSpiderwebTimeframe : "30d");
        }
      } else {
        if (feedbackEl) {
          feedbackEl.style.display = "block";
          feedbackEl.style.color = "#ef4444";
          feedbackEl.style.borderColor = "rgba(239,68,68,0.4)";
          feedbackEl.textContent = `⚠️ ${data.error || "Failed to connect to Wyze."}`;
        }
        showToast(`⚠️ ${data.error || "Wyze connection failed"}`);
      }
    } catch (err) {
      if (feedbackEl) {
        feedbackEl.style.display = "block";
        feedbackEl.style.color = "#ef4444";
        feedbackEl.textContent = `⚠️ Network error: ${err.message || "Could not reach server"}`;
      }
      showToast("⚠️ Network error connecting to Wyze");
    } finally {
      btnConnectWyze.textContent = origText;
      btnConnectWyze.disabled = false;
    }
  });
}

const btnSyncWyzeScale = document.getElementById("btnSyncWyzeScale");
if (btnSyncWyzeScale) {
  btnSyncWyzeScale.addEventListener("click", async () => {
    const feedbackEl = document.getElementById("wyzeConnectFeedback");
    const origText = btnSyncWyzeScale.textContent;
    btnSyncWyzeScale.textContent = "⏳ Syncing...";
    btnSyncWyzeScale.disabled = true;
    try {
      const res = await fetch("/api/auth/sync/wyze", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        const latest = data.latest || (data.summary && data.summary.latest);
        if (latest && latest.weight_lbs) {
          const wInput = document.getElementById("settingAthleteWeightLbs");
          if (wInput) wInput.value = Number(latest.weight_lbs).toFixed(1);
          updateSettingsLiveWkgBadge();
        }
        renderWyzeSettingsSummary({
          wyze_email: document.getElementById("settingWyzeEmail")?.value || "",
          wyze_key_id: document.getElementById("settingWyzeKeyId")?.value || "",
          wyze_password_set: true,
          wyze_api_key_set: true,
          wyze_connected: true,
          wyze_summary: data.summary
        });
        if (feedbackEl) {
          feedbackEl.style.display = "block";
          feedbackEl.style.color = "#00C896";
          feedbackEl.style.borderColor = "rgba(0,200,150,0.4)";
          feedbackEl.textContent = `✅ ${data.message || "Wyze Scale synced!"}`;
        }
        showToast(`⚖️ ${data.message || "Wyze Scale synced!"}`);
        await loadDashboard();
        if (typeof loadPowerSpiderweb === "function") {
          await loadPowerSpiderweb(typeof currentSpiderwebTimeframe !== "undefined" ? currentSpiderwebTimeframe : "30d");
        }
      } else {
        if (feedbackEl) {
          feedbackEl.style.display = "block";
          feedbackEl.style.color = "#ef4444";
          feedbackEl.textContent = `⚠️ ${data.error || "Unable to sync Wyze Scale."}`;
        }
        showToast(`⚠️ ${data.error || "Wyze sync failed"}`);
      }
    } catch (err) {
      showToast("⚠️ Wyze sync network error");
    } finally {
      btnSyncWyzeScale.textContent = origText;
      btnSyncWyzeScale.disabled = false;
    }
  });
}

const btnDisconnectWyze = document.getElementById("btnDisconnectWyze");
if (btnDisconnectWyze) {
  btnDisconnectWyze.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to disconnect your Wyze Smart Scale?")) return;
    try {
      await fetch("/api/auth/disconnect/wyze", { method: "POST" });
      showToast("Wyze Smart Scale disconnected");
      openSettingsModal();
      loadDashboard();
    } catch (err) {
      showToast("Error disconnecting Wyze Smart Scale");
    }
  });
}

btnSaveSettings.addEventListener("click", async () => {
  const intervalsApiKeyVal = document.getElementById("settingIntervalsApiKey") ? document.getElementById("settingIntervalsApiKey").value.trim() : "";
  const preferredMapLayerVal = document.getElementById("settingPreferredMapLayer") ? document.getElementById("settingPreferredMapLayer").value : "google_roads";
  const weightLbsVal = parseFloat(document.getElementById("settingAthleteWeightLbs")?.value);

  const payload = {
    theme_mode: currentThemeMode,
    intervals_athlete_id: document.getElementById("settingIntervalsAthleteId") ? document.getElementById("settingIntervalsAthleteId").value.trim() : "",
    athlete_ftp: parseInt(document.getElementById("settingFtp")?.value, 10) || 250,
    athlete_max_hr: parseInt(document.getElementById("settingMaxHr")?.value, 10) || 185,
    athlete_w_prime_kj: parseFloat(document.getElementById("settingAthleteWPrime")?.value) || 20.0,
    athlete_peak_power_watts: parseInt(document.getElementById("settingAthletePeakPower")?.value, 10) || 1050,
    demo_mode: document.getElementById("settingDemoMode") ? document.getElementById("settingDemoMode").checked : false,
    program_goal: document.getElementById("settingProgramGoal")?.value || "FTP_BUILD",
    program_target_ftp: parseInt(document.getElementById("settingProgramTargetFtp")?.value, 10) || 265,
    program_target_date: document.getElementById("settingProgramTargetDate")?.value || "",
    program_weekly_tss_target: parseInt(document.getElementById("settingProgramWeeklyTss")?.value, 10) || 360,
    program_weekly_xss_target: parseInt(document.getElementById("settingProgramWeeklyXss")?.value, 10) || parseInt(document.getElementById("settingProgramWeeklyTss")?.value, 10) || 360,
    preferred_map_layer: preferredMapLayerVal
  };

  if (!isNaN(weightLbsVal) && weightLbsVal > 50) {
    payload.athlete_weight_lbs = Number(weightLbsVal.toFixed(1));
  }

  const wyzeEmailVal = document.getElementById("settingWyzeEmail")?.value.trim();
  if (wyzeEmailVal !== undefined) payload.wyze_email = wyzeEmailVal;
  const wyzeKeyIdVal = document.getElementById("settingWyzeKeyId")?.value.trim();
  if (wyzeKeyIdVal !== undefined) payload.wyze_key_id = wyzeKeyIdVal;
  const wyzePassVal = document.getElementById("settingWyzePassword")?.value.trim();
  if (wyzePassVal && !wyzePassVal.includes("•")) payload.wyze_password = wyzePassVal;
  const wyzeApiKeyVal = document.getElementById("settingWyzeApiKey")?.value.trim();
  if (wyzeApiKeyVal && !wyzeApiKeyVal.includes("•")) payload.wyze_api_key = wyzeApiKeyVal;
  const wyzeTotpVal = document.getElementById("settingWyzeTotp")?.value.trim();
  if (wyzeTotpVal && !wyzeTotpVal.includes("•") && !/^\d{6}$/.test(wyzeTotpVal)) {
    payload.wyze_totp_secret = wyzeTotpVal;
  }

  const oldGoal = (state.program?.goal_id || "").toUpperCase();
  const newGoal = (payload.program_goal || "").toUpperCase();
  let resetBlock = false;
  if (newGoal && oldGoal && newGoal !== oldGoal) {
    const goalSelect = document.getElementById("settingProgramGoal");
    const goalName = (goalSelect && goalSelect.selectedOptions && goalSelect.selectedOptions[0]) ? goalSelect.selectedOptions[0].text : newGoal;
    resetBlock = confirm(
      `You changed your rider type / long-term goal to ${goalName}.\n\nWould you like to reset your macrocycle block to Week 1 (8-week adaptation cycle)?\n\n• Click OK to reset the block to Week 1 (Base Phase)\n• Click Cancel to maintain your current block timeline`
    );
  }
  payload.reset_block = resetBlock;

  if (intervalsApiKeyVal && !intervalsApiKeyVal.includes("•")) {
    payload.intervals_icu_api_key = intervalsApiKeyVal;
  }

  const googleClientIdVal = document.getElementById("settingGoogleClientId")?.value.trim();
  if (googleClientIdVal && !googleClientIdVal.includes("•")) {
    payload.google_client_id = googleClientIdVal;
  }
  const googleSecretVal = document.getElementById("settingGoogleClientSecret")?.value.trim();
  if (googleSecretVal && !googleSecretVal.includes("•")) {
    payload.google_client_secret = googleSecretVal;
  }

  const primaryOwnerEmailVal = document.getElementById("settingPrimaryOwnerEmail")?.value.trim();
  if (primaryOwnerEmailVal) {
    payload.primary_owner_email = primaryOwnerEmailVal.toLowerCase();
  }

  try {
    const saveRes = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!saveRes.ok) {
      if (saveRes.status === 401) {
        showToast("🔒 Please sign in to save settings.");
        closeSettingsModal();
        openAuthModal();
        return;
      }
      throw new Error(`HTTP ${saveRes.status}`);
    }
    closeSettingsModal();
    if (payload.preferred_map_layer) {
      applyBaseTileLayer(payload.preferred_map_layer);
    }
    showToast("✅ Settings saved!");
    hasSyncedInitialPlannerMode = false;
    await checkCoachGeminiStatus();
    await loadDashboard();
    await loadWorkout(state.currentDuration, state.currentIntensity);
    await loadDebrief();
    await loadPowerSpiderweb(currentSpiderwebTimeframe);
  } catch (err) {
    showToast("⚠️ Failed to save settings.");
  }
});

// Program Goal & Target FTP Dynamic Auto-Update (Xert Alternative)
const settingProgramGoalEl = document.getElementById("settingProgramGoal");
const settingProgramTargetFtpEl = document.getElementById("settingProgramTargetFtp");
const settingProgramWeeklyTssEl = document.getElementById("settingProgramWeeklyTss");
const settingProgramWeeklyXssEl = document.getElementById("settingProgramWeeklyXss");
const settingFtpEl = document.getElementById("settingFtp");

const PROGRAM_GOAL_ARCHETYPES = {
  "PURSUITER": { gain: 12, tss: 360, xss: 360 },
  "CLIMBER": { gain: 15, tss: 380, xss: 380 },
  "ROULEUR": { gain: 15, tss: 400, xss: 400 },
  "PUNCHEUR": { gain: 12, tss: 350, xss: 350 },
  "SPRINTER": { gain: 8, tss: 320, xss: 320 },
  "ALL_ROUNDER": { gain: 12, tss: 380, xss: 380 },
  "FTP_BUILD": { gain: 15, tss: 360, xss: 360 },
  "GRAN_FONDO": { gain: 10, tss: 420, xss: 420 },
  "VO2_CRIT": { gain: 12, tss: 340, xss: 340 },
  "HEALTH_LONGEVITY": { gain: 5, tss: 260, xss: 260 }
};

function updateTargetFtpFromProgramGoal(flash = true) {
  if (!settingProgramGoalEl || !settingProgramTargetFtpEl) return;
  const goalKey = settingProgramGoalEl.value || "FTP_BUILD";
  const archetype = PROGRAM_GOAL_ARCHETYPES[goalKey] || { gain: 15, tss: 360, xss: 360 };
  const currentFtp = parseInt(settingFtpEl?.value, 10) || state.athlete?.ftp || 250;
  const newTargetFtp = currentFtp + archetype.gain;

  settingProgramTargetFtpEl.value = newTargetFtp;
  settingProgramTargetFtpEl.placeholder = newTargetFtp;

  if (settingProgramWeeklyTssEl) {
    settingProgramWeeklyTssEl.value = archetype.tss;
    settingProgramWeeklyTssEl.placeholder = archetype.tss;
  }
  if (settingProgramWeeklyXssEl) {
    settingProgramWeeklyXssEl.value = archetype.xss;
    settingProgramWeeklyXssEl.placeholder = archetype.xss;
  }

  if (flash) {
    settingProgramTargetFtpEl.style.transition = "border-color 0.25s ease, box-shadow 0.25s ease";
    settingProgramTargetFtpEl.style.borderColor = "var(--accent-cyan)";
    settingProgramTargetFtpEl.style.boxShadow = "0 0 10px rgba(6, 182, 212, 0.4)";
    setTimeout(() => {
      settingProgramTargetFtpEl.style.borderColor = "";
      settingProgramTargetFtpEl.style.boxShadow = "";
    }, 600);
  }
}

if (settingProgramGoalEl) {
  settingProgramGoalEl.addEventListener("change", () => {
    updateTargetFtpFromProgramGoal(true);
  });
}

if (settingFtpEl) {
  settingFtpEl.addEventListener("input", () => {
    updateTargetFtpFromProgramGoal(false);
    updateSettingsLiveWkgBadge();
  });
}

// Test Gemini API Key Button in Settings
const btnTestGemini = document.getElementById("btnTestGeminiKey");
if (btnTestGemini) {
  btnTestGemini.addEventListener("click", async () => {
    const keyInput = document.getElementById("settingGeminiKey");
    const keyVal = keyInput ? keyInput.value.trim() : "";
    const feedback = document.getElementById("geminiTestFeedback");
    btnTestGemini.disabled = true;
    btnTestGemini.textContent = "Testing...";
    if (feedback) {
      feedback.style.display = "block";
      feedback.style.color = "var(--text-muted)";
      feedback.textContent = "Pinging Google Gemini API...";
    }

    try {
      const res = await fetch("/api/chat/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: keyVal })
      });
      const data = await res.json();
      if (data.success) {
        if (feedback) {
          feedback.style.color = "#10b981";
          feedback.textContent = `✓ ${data.message}`;
        }
        updateGeminiConnectedIndicators(true, data.model);
        showToast(`✨ Connected to Google Gemini (${data.model})!`);
      } else {
        if (feedback) {
          feedback.style.color = "#ef4444";
          feedback.textContent = `⚠️ ${data.message}`;
        }
        updateGeminiConnectedIndicators(false);
        showToast(`⚠️ ${data.message}`);
      }
    } catch (err) {
      if (feedback) {
        feedback.style.color = "#ef4444";
        feedback.textContent = `⚠️ Network error: ${err.message}`;
      }
    } finally {
      btnTestGemini.disabled = false;
      btnTestGemini.textContent = "⚡ Test Connection";
    }
  });
}

// W' Anaerobic Work Capacity Estimator Helper in Settings
const btnToggleWpHelper = document.getElementById("btnToggleWPrimeHelper");
const btnCloseWpHelper = document.getElementById("btnCloseWPrimeHelper");
const wpHelperBox = document.getElementById("wPrimeEstimatorBox");

if (btnToggleWpHelper && wpHelperBox) {
  btnToggleWpHelper.addEventListener("click", () => {
    const isHidden = wpHelperBox.style.display === "none";
    wpHelperBox.style.display = isHidden ? "block" : "none";
    if (isHidden) {
      const ftpVal = parseFloat(document.getElementById("settingFtp")?.value) || 250;
      const watts1 = document.getElementById("calcWpWatts1");
      const watts2 = document.getElementById("calcWpWatts2");
      if (watts1 && !watts1.value) watts1.value = Math.round(ftpVal * 1.36); // e.g. ~340W for 250W FTP
      if (watts2 && !watts2.value) watts2.value = Math.round(ftpVal * 1.08); // e.g. ~270W for 250W FTP
    }
  });
}

if (btnCloseWpHelper && wpHelperBox) {
  btnCloseWpHelper.addEventListener("click", () => {
    wpHelperBox.style.display = "none";
  });
}

// Option A: 2-Point Math Model
const btnCalcWp = document.getElementById("btnCalculateWPrime");
if (btnCalcWp) {
  btnCalcWp.addEventListener("click", () => {
    const t1 = parseFloat(document.getElementById("calcWpDur1")?.value);
    const p1 = parseFloat(document.getElementById("calcWpWatts1")?.value);
    const t2 = parseFloat(document.getElementById("calcWpDur2")?.value);
    const p2 = parseFloat(document.getElementById("calcWpWatts2")?.value);
    const resBox = document.getElementById("calcWpResult");

    if (!t1 || !p1 || !t2 || !p2 || t1 <= 0 || t2 <= 0 || p1 <= 0 || p2 <= 0) {
      if (resBox) {
        resBox.style.display = "block";
        resBox.style.color = "#ef4444";
        resBox.style.borderColor = "rgba(239,68,68,0.3)";
        resBox.textContent = "⚠️ Please enter valid duration (>0 sec) and power (>0 W) for both efforts.";
      }
      return;
    }

    if (t2 <= t1 || p1 <= p2) {
      if (resBox) {
        resBox.style.display = "block";
        resBox.style.color = "#ef4444";
        resBox.style.borderColor = "rgba(239,68,68,0.3)";
        resBox.textContent = "⚠️ Effort 1 must be shorter duration and higher power than Effort 2 (e.g. 180s @ 340W and 600s @ 270W).";
      }
      return;
    }

    // Work1 = p1 * t1, Work2 = p2 * t2
    // CP = (Work2 - Work1) / (t2 - t1)
    // W' = (Work1 - CP * t1) / 1000 (kJ)
    const work1 = p1 * t1;
    const work2 = p2 * t2;
    const cp = (work2 - work1) / (t2 - t1);
    const wpKj = (work1 - (cp * t1)) / 1000.0;

    if (wpKj < 5.0 || wpKj > 50.0 || cp < 100) {
      if (resBox) {
        resBox.style.display = "block";
        resBox.style.color = "#f59e0b";
        resBox.style.borderColor = "rgba(245,158,11,0.3)";
        resBox.textContent = `⚠️ Estimated W': ${wpKj.toFixed(1)} kJ (CP: ${Math.round(cp)}W). This is outside typical human range (10–35 kJ). Check your test numbers.`;
      }
    } else {
      if (resBox) {
        resBox.style.display = "block";
        resBox.style.color = "#10b981";
        resBox.style.borderColor = "rgba(16,185,129,0.3)";
        resBox.innerHTML = `✓ Estimated W': <strong>${wpKj.toFixed(1)} kJ</strong> • Modeled Critical Power: <strong>${Math.round(cp)}W</strong>. Populated into settings!`;
      }
    }

    const inputWp = document.getElementById("settingAthleteWPrime");
    if (inputWp && wpKj > 0) {
      inputWp.value = Math.max(5.0, Math.min(50.0, wpKj)).toFixed(1);
    }
  });
}

// Option B: Presets by rider type
document.querySelectorAll(".btn-wp-preset").forEach(btn => {
  btn.addEventListener("click", () => {
    const val = parseFloat(btn.dataset.wp);
    const inputWp = document.getElementById("settingAthleteWPrime");
    if (inputWp && val) {
      inputWp.value = val.toFixed(1);
      const resBox = document.getElementById("calcWpResult");
      if (resBox) {
        resBox.style.display = "block";
        resBox.style.color = "#10b981";
        resBox.style.borderColor = "rgba(16,185,129,0.3)";
        resBox.innerHTML = `✓ Set W' to <strong>${val.toFixed(1)} kJ</strong> (${btn.textContent.trim()}).`;
      }
    }
  });
});

// Version & Changelog Modal Logic
const changelogModal = document.getElementById("changelogModal");
const btnOpenChangelog = document.getElementById("btnOpenChangelog");
const btnCloseChangelog = document.getElementById("btnCloseChangelog");
const changelogList = document.getElementById("changelogList");
const footerVersionBadge = document.getElementById("footerVersionBadge");

let isVersionLoading = false;
let versionDataLoaded = false;

async function loadVersionInfo(force = false) {
  if (versionDataLoaded && !force && changelogList && changelogList.querySelector(".changelog-entry")) {
    return;
  }
  if (isVersionLoading) return;

  if (changelogList && (!changelogList.querySelector(".changelog-entry") || force)) {
    changelogList.innerHTML = `
      <div style="text-align:center;padding:2.5rem 1rem;color:var(--text-muted);display:flex;flex-direction:column;align-items:center;gap:0.75rem;">
        <div style="width:26px;height:26px;border:3px solid rgba(6,182,212,0.2);border-top-color:var(--accent-cyan,#06b6d4);border-radius:50%;animation:pullSpinnerRotate 0.8s linear infinite;"></div>
        <span style="font-size:0.875rem;">Loading release notes & changelog...</span>
      </div>
    `;
  }

  isVersionLoading = true;
  try {
    const res = await fetch(`/api/version?_t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (footerVersionBadge && data.version) {
      footerVersionBadge.textContent = `v${data.version}`;
    }
    if (changelogList && Array.isArray(data.changelog) && data.changelog.length > 0) {
      changelogList.innerHTML = data.changelog.map(entry => `
        <div class="changelog-entry">
          <div class="changelog-header">
            <span class="changelog-ver">${entry.version || ""}</span>
            <span class="changelog-date">${entry.date || ""}</span>
          </div>
          <div class="changelog-title">${entry.title || ""}</div>
          <ul class="changelog-items">
            ${(entry.items || []).map(item => `<li>${item}</li>`).join("")}
          </ul>
        </div>
      `).join("");
      versionDataLoaded = true;
    } else if (changelogList) {
      changelogList.innerHTML = `
        <div style="text-align:center;padding:2.5rem 1rem;color:var(--text-muted);">
          No release notes available at this time.
        </div>
      `;
    }
  } catch (err) {
    console.error("Failed to load version info:", err);
    if (changelogList && (!changelogList.querySelector(".changelog-entry") || force)) {
      changelogList.innerHTML = `
        <div style="text-align:center;padding:2.5rem 1rem;color:var(--text-muted);display:flex;flex-direction:column;align-items:center;gap:0.75rem;">
          <span style="color:#ef4444;font-size:0.875rem;">⚠️ Unable to load release notes right now.</span>
          <button type="button" class="btn btn-sm btn-secondary" id="btnRetryChangelog" style="font-size:0.8rem;padding:0.35rem 0.85rem;cursor:pointer;">
            Retry
          </button>
        </div>
      `;
      const btnRetry = document.getElementById("btnRetryChangelog");
      if (btnRetry) {
        btnRetry.addEventListener("click", () => loadVersionInfo(true));
      }
    }
  } finally {
    isVersionLoading = false;
  }
}

function openChangelogModal() {
  if (!changelogModal) return;
  changelogModal.classList.add("open", "active");
  loadVersionInfo();
}

function closeChangelogModal() {
  if (!changelogModal) return;
  changelogModal.classList.remove("open", "active");
}

window.openChangelogModal = openChangelogModal;
window.closeChangelogModal = closeChangelogModal;
window.loadVersionInfo = loadVersionInfo;

if (btnOpenChangelog) {
  btnOpenChangelog.addEventListener("click", (e) => {
    e.preventDefault();
    openChangelogModal();
  });
}
if (footerVersionBadge) {
  footerVersionBadge.style.cursor = "pointer";
  footerVersionBadge.title = "Click to view Release Notes";
  footerVersionBadge.addEventListener("click", (e) => {
    e.preventDefault();
    openChangelogModal();
  });
}
if (btnCloseChangelog) {
  btnCloseChangelog.addEventListener("click", (e) => {
    e.preventDefault();
    closeChangelogModal();
  });
}

// Close modals when clicking backdrop or pressing ESC
if (changelogModal) {
  changelogModal.addEventListener("click", (e) => {
    if (e.target === changelogModal) closeChangelogModal();
  });
}
if (settingsModal) {
  settingsModal.addEventListener("click", (e) => {
    if (e.target === settingsModal) closeSettingsModal();
  });
}
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeChangelogModal();
    closeSettingsModal();
  }
});

// -------------------------------------------------------------
// AI COACH DAILY DEBRIEF & MULTI-DAY OUTLOOK
// -------------------------------------------------------------
const tabDebriefToday = document.getElementById("tabDebriefToday");
const tabDebriefOutlook = document.getElementById("tabDebriefOutlook");
const tabDebriefRecovery = document.getElementById("tabDebriefRecovery");
const debriefTabAssessment = document.getElementById("debriefTabAssessment");
const debriefTabOutlook = document.getElementById("debriefTabOutlook");
const debriefTabProtocol = document.getElementById("debriefTabProtocol");
const btnRefreshDebrief = document.getElementById("btnRefreshDebrief");

function switchDebriefTab(tabName) {
  const tabs = [
    { btn: tabDebriefToday, panel: debriefTabAssessment, name: "assessment" },
    { btn: tabDebriefOutlook, panel: debriefTabOutlook, name: "outlook" },
    { btn: tabDebriefRecovery, panel: debriefTabProtocol, name: "protocol" }
  ];
  tabs.forEach(t => {
    if (!t.btn || !t.panel) return;
    if (t.name === tabName) {
      t.btn.classList.add("active");
      t.panel.style.display = "block";
    } else {
      t.btn.classList.remove("active");
      t.panel.style.display = "none";
    }
  });
}

if (tabDebriefToday) {
  tabDebriefToday.addEventListener("click", () => switchDebriefTab("assessment"));
}
if (tabDebriefOutlook) {
  tabDebriefOutlook.addEventListener("click", () => switchDebriefTab("outlook"));
}
if (tabDebriefRecovery) {
  tabDebriefRecovery.addEventListener("click", () => switchDebriefTab("protocol"));
}

async function loadDebrief() {
  try {
    const res = await fetch("/api/review/daily-debrief");
    if (!res.ok) throw new Error("Debrief fetch failed");
    const data = await res.json();
    state.dailyDebrief = data;
    renderDebrief(data);
    renderAiCoachTodayCard(data, state.currentWorkout);
    if (data.strava && typeof renderStrava === "function") {
      state.strava = data.strava;
      renderStrava(data.strava);
    }
  } catch (err) {
    console.error("Failed to load daily debrief:", err);
  }
}

function renderDebrief(data) {
  if (!data) return;
  const assessment = data.today_assessment || {};
  const outlook = data.outlook_days || [];
  const protocol = data.recovery_protocol || {};
  const macro = data.macrocycle_context || {};

  // 1. Session Assessment
  const debriefActivityMeta = document.getElementById("debriefActivityMeta");
  const debriefActivityTitle = document.getElementById("debriefActivityTitle");
  const debriefVerdictBadge = document.getElementById("debriefVerdictBadge");
  const debriefMetricScore = document.getElementById("debriefMetricScore");
  const debriefMetricVerdict = document.getElementById("debriefMetricVerdict");
  const debriefMetricWatts = document.getElementById("debriefMetricWatts");
  const debriefMetricTargetWatts = document.getElementById("debriefMetricTargetWatts");
  const debriefMetricTime = document.getElementById("debriefMetricTime");
  const debriefMetricDist = document.getElementById("debriefMetricDist");
  const debriefMetricTss = document.getElementById("debriefMetricTss");
  const debriefMetricHr = document.getElementById("debriefMetricHr");
  const debriefAssessmentText = document.getElementById("debriefAssessmentText");

  const isMultiSession = assessment.sessions && assessment.sessions.length > 1;

  if (debriefActivityMeta) {
    if (isMultiSession) {
      const sessCount = `${assessment.sessions.length} SESSIONS`;
      if (assessment.is_today) {
        debriefActivityMeta.textContent = `COLLECTIVE EVALUATION OF ${sessCount} TODAY`;
      } else if (assessment.is_yesterday) {
        debriefActivityMeta.textContent = `COLLECTIVE EVALUATION OF ${sessCount} YESTERDAY (${assessment.date || "OCT 11"})`;
      } else {
        debriefActivityMeta.textContent = `COLLECTIVE EVALUATION OF ${sessCount} (${assessment.date_display || assessment.date || "PREVIOUS"})`;
      }
    } else {
      if (assessment.is_today) {
        debriefActivityMeta.textContent = "EVALUATION OF COMPLETED SESSION TODAY";
      } else if (assessment.is_yesterday) {
        debriefActivityMeta.textContent = `EVALUATION OF YESTERDAY'S SESSION (${assessment.date || "OCT 11"})`;
      } else {
        debriefActivityMeta.textContent = `EVALUATION OF RECENT SESSION (${assessment.date_display || assessment.date || "PREVIOUS"})`;
      }
    }
  }

  const tabDebriefToday = document.getElementById("tabDebriefToday");
  if (tabDebriefToday) {
    if (isMultiSession) {
      tabDebriefToday.innerHTML = assessment.is_today
        ? "🎯 Today's Sessions"
        : (assessment.is_yesterday ? "🎯 Yesterday's Sessions" : "🎯 Recent Sessions");
    } else {
      tabDebriefToday.innerHTML = assessment.is_today
        ? "🎯 Today's Debrief"
        : (assessment.is_yesterday ? "🎯 Yesterday's Debrief" : "🎯 Recent Debrief");
    }
  }

  const debriefSubtitle = document.getElementById("debriefSubtitle");
  if (debriefSubtitle) {
    if (isMultiSession) {
      if (assessment.is_today) {
        debriefSubtitle.textContent = `Collectively assessing all ${assessment.sessions.length} sessions completed today`;
      } else if (assessment.is_yesterday) {
        debriefSubtitle.textContent = `Collectively assessing all ${assessment.sessions.length} sessions completed yesterday (${assessment.date})`;
      } else {
        const dLabel = assessment.date_display ? `${assessment.date_display} (${assessment.relative_day_label || assessment.date})` : (assessment.relative_day_label || assessment.date || "this day");
        debriefSubtitle.textContent = `Collectively assessing all ${assessment.sessions.length} sessions completed on ${dLabel}`;
      }
    } else if (assessment.is_today) {
      debriefSubtitle.textContent = "Assessing today's session against prescriptions, goals, and recovery";
    } else if (assessment.is_yesterday) {
      debriefSubtitle.textContent = `Assessing yesterday's session (${assessment.date}) and how it shaped today's recovery`;
    } else {
      const dLabel = assessment.date_display ? `${assessment.date_display} (${assessment.relative_day_label || assessment.date})` : (assessment.relative_day_label || assessment.date || "previous session");
      debriefSubtitle.textContent = `Assessing previous session from ${dLabel} against prescriptions and goals`;
    }
  }

  if (debriefActivityTitle) {
    debriefActivityTitle.textContent = assessment.title || "Rest / Recovery Day";
  }

  const debriefSessionsBreakdown = document.getElementById("debriefSessionsBreakdown");
  if (debriefSessionsBreakdown) {
    if (isMultiSession) {
      debriefSessionsBreakdown.style.display = "flex";
      debriefSessionsBreakdown.innerHTML = assessment.sessions.map((s) => {
        const isPrimary = s.is_primary;
        const badgeBg = isPrimary ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.12)";
        const borderCol = isPrimary ? "rgba(16, 185, 129, 0.4)" : "rgba(56, 189, 248, 0.3)";
        const icon = isPrimary ? "⚡" : "🌀";
        const role = isPrimary ? "Primary Workout" : "Cooldown / Flush";
        return `<span style="font-size:0.75rem;padding:0.25rem 0.55rem;border-radius:6px;background:${badgeBg};border:1px solid ${borderCol};color:#f1f5f9;display:inline-flex;align-items:center;gap:0.35rem;">` +
          `<span>${icon} <strong>${s.name}</strong> <span style="color:var(--text-muted);">(${role})</span></span>` +
          `<span style="color:var(--text-muted);margin-left:0.2rem;">• ${s.moving_time_formatted} • ${s.weighted_watts}W • ${s.tss} TSS</span>` +
        `</span>`;
      }).join("");
    } else {
      debriefSessionsBreakdown.style.display = "none";
      debriefSessionsBreakdown.innerHTML = "";
    }
  }
  if (debriefVerdictBadge) {
    debriefVerdictBadge.textContent = assessment.verdict_badge || "🎯 Target Mastered";
    if (assessment.verdict_color === "amber") {
      debriefVerdictBadge.style.color = "#f59e0b";
      debriefVerdictBadge.style.borderColor = "rgba(245, 158, 11, 0.3)";
    } else if (assessment.verdict_color === "cyan") {
      debriefVerdictBadge.style.color = "#06b6d4";
      debriefVerdictBadge.style.borderColor = "rgba(6, 182, 212, 0.3)";
    } else {
      debriefVerdictBadge.style.color = "#10b981";
      debriefVerdictBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
    }
  }

  if (debriefMetricScore) debriefMetricScore.textContent = `${assessment.compliance_score || 95}%`;
  if (debriefMetricVerdict) debriefMetricVerdict.textContent = assessment.verdict || "Target Fidelity";
  
  if (debriefMetricWatts) {
    debriefMetricWatts.textContent = assessment.weighted_watts ? `${assessment.weighted_watts}W` : "0W";
  }
  if (debriefMetricTargetWatts) {
    debriefMetricTargetWatts.textContent = `Target: ${assessment.target_watts || 0}W (${assessment.target_zone || ""})`;
  }
  if (debriefMetricTime) debriefMetricTime.textContent = assessment.moving_time_formatted || "0m";
  const debriefDistMi = assessment.distance_miles || (assessment.distance_km ? (assessment.distance_km * 0.621371).toFixed(1) : 0);
  if (debriefMetricDist) debriefMetricDist.textContent = `${debriefDistMi} mi logged`;
  const cardLoadTss = (assessment.calculated_tss !== undefined && assessment.calculated_tss !== null) ? assessment.calculated_tss : (assessment.suffer_score || 0);
  if (debriefMetricTss) debriefMetricTss.textContent = `${cardLoadTss} TSS`;
  if (debriefMetricHr) {
    debriefMetricHr.textContent = (assessment.avg_hr && assessment.avg_hr > 0) ? `${assessment.avg_hr} bpm avg` : "-- bpm avg";
  }

  // Update collapsed summary for debrief card
  const collapsedDebriefVerdict = document.getElementById("collapsedDebriefVerdict");
  if (collapsedDebriefVerdict) collapsedDebriefVerdict.textContent = assessment.verdict_badge || "🎯 Compliant";
  const collapsedDebriefScore = document.getElementById("collapsedDebriefScore");
  if (collapsedDebriefScore) collapsedDebriefScore.textContent = `Score: ${assessment.compliance_score || 95}%`;
  const collapsedDebriefTss = document.getElementById("collapsedDebriefTss");
  if (collapsedDebriefTss) collapsedDebriefTss.textContent = `${cardLoadTss} TSS`;

  if (debriefAssessmentText) {
    const rawDebrief = assessment.ai_coach_insights || assessment.assessment_text || "";
    const cleanDebrief = cleanCoachInsightsText(rawDebrief);
    debriefAssessmentText.textContent = cleanDebrief || assessment.assessment_text || "";
  }

  // 3-Tier Physiological Strain & W'bal Battery
  const debriefFocusDurationBadge = document.getElementById("debriefFocusDurationBadge");
  const debriefTotalXssVal = document.getElementById("debriefTotalXssVal");
  const debriefLowXssVal = document.getElementById("debriefLowXssVal");
  const debriefHighXssVal = document.getElementById("debriefHighXssVal");
  const debriefPeakXssVal = document.getElementById("debriefPeakXssVal");
  const debriefBatteryLabel = document.getElementById("debriefBatteryLabel");
  const debriefBatteryFill = document.getElementById("debriefBatteryFill");

  if (debriefFocusDurationBadge) {
    debriefFocusDurationBadge.textContent = assessment.focus_duration || "Endurance / Century (>1h Focus)";
  }
  if (debriefTotalXssVal) {
    debriefTotalXssVal.textContent = assessment.total_xss !== undefined ? assessment.total_xss : (assessment.suffer_score || 0);
  }
  if (debriefLowXssVal) {
    debriefLowXssVal.innerHTML = `${assessment.low_strain_xss !== undefined ? assessment.low_strain_xss : 0} <span style="font-size:0.75rem;color:var(--text-muted);">XSS</span>`;
  }
  if (debriefHighXssVal) {
    debriefHighXssVal.innerHTML = `${assessment.high_strain_xss !== undefined ? assessment.high_strain_xss : 0} <span style="font-size:0.75rem;color:var(--text-muted);">XSS</span>`;
  }
  if (debriefPeakXssVal) {
    debriefPeakXssVal.innerHTML = `${assessment.peak_strain_xss !== undefined ? assessment.peak_strain_xss : 0} <span style="font-size:0.75rem;color:var(--text-muted);">XSS</span>`;
  }
  if (debriefBatteryLabel && debriefBatteryFill) {
    const minWBalPct = assessment.min_w_bal_pct !== undefined ? assessment.min_w_bal_pct : 100;
    const depletedPct = assessment.battery_depleted_pct !== undefined ? assessment.battery_depleted_pct : Math.round(100 - minWBalPct);
    debriefBatteryLabel.textContent = `${minWBalPct}% Remaining (${depletedPct}% Depleted)`;
    debriefBatteryFill.style.width = `${Math.max(5, Math.min(100, minWBalPct))}%`;
    if (minWBalPct >= 70) {
      debriefBatteryFill.style.background = "linear-gradient(90deg, #10b981, #06b6d4)";
    } else if (minWBalPct >= 40) {
      debriefBatteryFill.style.background = "linear-gradient(90deg, #f59e0b, #eab308)";
    } else {
      debriefBatteryFill.style.background = "linear-gradient(90deg, #f43f5e, #ef4444)";
    }
  }

  // 2. 3-Day Outlook
  const outlookWeeklyTargetTss = document.getElementById("outlookWeeklyTargetTss");
  if (outlookWeeklyTargetTss && macro.weekly_tss_target) {
    const xssTgt = macro.weekly_xss_target || macro.weekly_tss_target;
    outlookWeeklyTargetTss.textContent = `${macro.weekly_tss_target} TSS (~${xssTgt} XSS)`;
  }

  const outlookCardsGrid = document.getElementById("outlookCardsGrid");
  if (outlookCardsGrid && Array.isArray(outlook)) {
    state.cachedOutlook = outlook;
    outlookCardsGrid.innerHTML = outlook.map((item, idx) => {
      let zoneColor = "#10b981";
      let zoneBg = "rgba(16, 185, 129, 0.1)";
      if (item.projected_zone === "yellow") {
        zoneColor = "#f59e0b";
        zoneBg = "rgba(245, 158, 11, 0.1)";
      } else if (item.projected_zone === "red") {
        zoneColor = "#f43f5e";
        zoneBg = "rgba(244, 63, 94, 0.1)";
      }

      const durTag = `<span class="tag tag-dur">${item.duration_min || 0} MIN</span>`;
      const xssTag = (item.estimated_xss !== undefined && item.estimated_xss > 0)
        ? `<span class="tag" style="background:rgba(139,92,246,0.15);color:#a78bfa;border:1px solid rgba(139,92,246,0.3);font-weight:600;">⚡ ~${item.estimated_xss} XSS</span>`
        : '';
      const tssTag = (item.estimated_tss > 0)
        ? `<span class="tag tag-tss">~${item.estimated_tss} TSS</span>`
        : `<span class="tag tag-tss" style="color:var(--text-muted);">0 TSS</span>`;
      const focusDurationTag = (item.focus_duration && item.duration_min > 0)
        ? `<span class="tag" style="background:rgba(6,182,212,0.12);color:#06b6d4;border:1px solid rgba(6,182,212,0.25);">🎯 ${item.focus_duration}</span>`
        : '';

      const scheduledBadge = item.is_coach_scheduled
        ? `<span class="badge-status" style="color:var(--accent-cyan);border-color:rgba(6,182,212,0.4);background:rgba(6,182,212,0.12);font-size:0.75rem;padding:0.15rem 0.5rem;">💬 Coach Scheduled</span>`
        : (item.is_athlete_adjusted
          ? `<span class="badge-status" style="color:#a78bfa;border-color:rgba(167,139,250,0.4);background:rgba(167,139,250,0.12);font-size:0.75rem;padding:0.15rem 0.5rem;">✍️ Athlete Note</span>`
          : (item.is_directive_rest
            ? `<span class="badge-status" style="color:#10b981;border-color:rgba(16,185,129,0.4);background:rgba(16,185,129,0.12);font-size:0.75rem;padding:0.15rem 0.5rem;">📋 Schedule Directive</span>`
            : ''));
      const cardStyle = item.is_coach_scheduled
        ? 'style="border-color:rgba(6,182,212,0.45);background:rgba(6,182,212,0.03);box-shadow:0 0 15px rgba(6,182,212,0.06);"'
        : (item.is_athlete_adjusted
          ? 'style="border-color:rgba(167,139,250,0.45);background:rgba(167,139,250,0.03);box-shadow:0 0 15px rgba(167,139,250,0.06);"'
          : (item.is_directive_rest
            ? 'style="border-color:rgba(16,185,129,0.45);background:rgba(16,185,129,0.03);box-shadow:0 0 15px rgba(16,185,129,0.06);"'
            : ''));
      const titleStyle = item.is_coach_scheduled
        ? 'style="color:var(--accent-cyan);font-weight:700;"'
        : (item.is_athlete_adjusted
          ? 'style="color:#a78bfa;font-weight:700;"'
          : (item.is_directive_rest
            ? 'style="color:#10b981;font-weight:700;"'
            : ''));
      const zwiftTag = item.is_coach_scheduled
        ? `<span class="tag" style="background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);font-weight:600;">🚀 Zwift Synced</span>`
        : '';

      return `
        <div class="outlook-card" data-forecast-idx="${idx}" ${cardStyle} role="button" tabindex="0" title="Click to preview workout & intervals for ${item.date_relative}">
          <div class="outlook-card-header">
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.4rem;">
              <span class="outlook-card-date">${item.date_relative} • ${item.date_formatted}</span>
              ${scheduledBadge}
            </div>
            <span class="badge-status" style="color:${zoneColor};border-color:${zoneColor}40;background:${zoneBg};font-size:0.75rem;padding:0.15rem 0.5rem;">
              ⚡ ~${item.projected_recovery}% ${item.projected_zone ? item.projected_zone.toUpperCase() : ''}
            </span>
          </div>
          <div class="outlook-card-title" ${titleStyle}>${item.title}</div>
          <div class="outlook-tags">
            ${durTag}
            ${xssTag}
            ${tssTag}
            ${focusDurationTag}
            <span class="tag tag-focus">${item.focus}</span>
            ${zwiftTag}
          </div>
          <div class="outlook-card-desc">${item.description}</div>
          <div class="outlook-preview-hint">
            <span>🔍 Preview workout &amp; intervals</span>
            <span style="font-size:0.85rem;">&rarr;</span>
          </div>
        </div>
      `;
    }).join("");

    outlookCardsGrid.querySelectorAll(".outlook-card").forEach(card => {
      card.addEventListener("click", () => {
        const idx = parseInt(card.getAttribute("data-forecast-idx"), 10);
        if (!isNaN(idx) && state.cachedOutlook && state.cachedOutlook[idx]) {
          openForecastModal(state.cachedOutlook[idx]);
        }
      });
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          card.click();
        }
      });
    });
  }

  // 3. Recovery Protocol
  const protocolSleepVal = document.getElementById("protocolSleepVal");
  const protocolSleepDesc = document.getElementById("protocolSleepDesc");
  const protocolNutritionTitle = document.getElementById("protocolNutritionTitle");
  const protocolNutritionDesc = document.getElementById("protocolNutritionDesc");
  const protocolHydrationDesc = document.getElementById("protocolHydrationDesc");

  if (protocolSleepVal && protocol.sleep_target_hours) {
    protocolSleepVal.textContent = `${protocol.sleep_target_hours} hrs`;
  }
  if (protocolSleepDesc && protocol.sleep_target_text) {
    protocolSleepDesc.textContent = protocol.sleep_target_text;
  }
  if (protocolNutritionTitle && protocol.nutrition_headline) {
    protocolNutritionTitle.textContent = protocol.nutrition_headline;
  }
  if (protocolNutritionDesc && protocol.nutrition_advice) {
    protocolNutritionDesc.textContent = protocol.nutrition_advice;
  }
  if (protocolHydrationDesc && protocol.hydration_target) {
    protocolHydrationDesc.textContent = protocol.hydration_target;
  }
  const inputDebriefUserNote = document.getElementById("inputDebriefUserNote");
  if (inputDebriefUserNote && data.athlete_note && !inputDebriefUserNote.value) {
    inputDebriefUserNote.value = data.athlete_note;
  }
  renderAiCoachTodayCard(data, state.currentWorkout);
}

const inputDebriefUserNote = document.getElementById("inputDebriefUserNote");
const btnAnalyzeDebrief = document.getElementById("btnAnalyzeDebrief");
const badgeDebriefNav = document.getElementById("badgeDebriefNav");

if (badgeDebriefNav) {
  badgeDebriefNav.addEventListener("click", () => {
    const debriefCard = document.getElementById("cardCoachDebrief");
    if (debriefCard) {
      debriefCard.scrollIntoView({ behavior: "smooth", block: "start" });
      debriefCard.style.borderColor = "var(--accent-cyan)";
      setTimeout(() => { debriefCard.style.borderColor = ""; }, 1800);
    }
  });
}

async function triggerDebriefAnalysis(note = "") {
  if (btnAnalyzeDebrief) {
    btnAnalyzeDebrief.disabled = true;
    btnAnalyzeDebrief.textContent = "⏳ Analyzing Session...";
  }
  if (btnRefreshDebrief) {
    btnRefreshDebrief.disabled = true;
    btnRefreshDebrief.textContent = "⏳ Analyzing...";
  }
  try {
    const res = await fetch("/api/review/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_note: note })
    });
    if (!res.ok) throw new Error("Debrief regenerate failed");
    const data = await res.json();
    state.dailyDebrief = data;
    state.activeCoachView = "completed";
    renderDebrief(data);
    if (note) {
      const tabDebriefOutlook = document.getElementById("tabDebriefOutlook");
      if (tabDebriefOutlook) {
        tabDebriefOutlook.click();
      }
    }
    showToast("🧠 AI coach debrief & 3-day forecast updated!");
  } catch (err) {
    console.error("Failed to analyze debrief:", err);
    showToast("⚠️ Could not update debrief.");
  } finally {
    if (btnAnalyzeDebrief) {
      btnAnalyzeDebrief.disabled = false;
      btnAnalyzeDebrief.textContent = "🧠 Assess & Update Forecast";
    }
    if (btnRefreshDebrief) {
      btnRefreshDebrief.disabled = false;
      btnRefreshDebrief.textContent = "🔄 Refresh";
    }
  }
}

if (btnAnalyzeDebrief) {
  btnAnalyzeDebrief.addEventListener("click", () => {
    const note = inputDebriefUserNote ? inputDebriefUserNote.value.trim() : "";
    triggerDebriefAnalysis(note);
  });
}

if (inputDebriefUserNote) {
  inputDebriefUserNote.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const note = inputDebriefUserNote.value.trim();
      triggerDebriefAnalysis(note);
    }
  });
}

// ============================================================================
// FORECAST WORKOUT PREVIEW MODAL
// ============================================================================
const modalForecastPreview = document.getElementById("modalForecastPreview");
const btnCloseForecastModal = document.getElementById("btnCloseForecastModal");
const btnCancelForecastModal = document.getElementById("btnCancelForecastModal");

if (btnCloseForecastModal) {
  btnCloseForecastModal.addEventListener("click", () => {
    if (modalForecastPreview) modalForecastPreview.classList.remove("open", "active");
  });
}
if (btnCancelForecastModal) {
  btnCancelForecastModal.addEventListener("click", () => {
    if (modalForecastPreview) modalForecastPreview.classList.remove("open", "active");
  });
}
if (modalForecastPreview) {
  modalForecastPreview.addEventListener("click", (e) => {
    if (e.target === modalForecastPreview) {
      modalForecastPreview.classList.remove("open", "active");
    }
  });
}

function openForecastModal(item) {
  if (!item) return;
  const modal = document.getElementById("modalForecastPreview");
  if (!modal) return;

  const titleEl = document.getElementById("forecastModalTitle");
  const subEl = document.getElementById("forecastModalSubtitle");
  const nameEl = document.getElementById("forecastModalWorkoutName");
  const badgeEl = document.getElementById("forecastModalBadgeType");
  const focusTagEl = document.getElementById("forecastModalFocusTag");
  const recPillEl = document.getElementById("forecastModalRecoveryPill");
  const recSubEl = document.getElementById("forecastModalRecoverySub");

  if (titleEl) titleEl.textContent = `Forecast Preview: ${item.date_relative || 'Upcoming Ride'}`;
  if (subEl) subEl.textContent = `${item.date_relative || ''} • ${item.date_formatted || ''}`;
  if (nameEl) nameEl.textContent = item.title || "Scheduled Ride";
  
  if (focusTagEl) {
    focusTagEl.textContent = item.focus || "Structured Workout";
  }

  if (badgeEl) {
    if (item.is_athlete_adjusted) {
      badgeEl.textContent = "✍️ Athlete Note";
      badgeEl.style.color = "#a78bfa";
      badgeEl.style.borderColor = "rgba(167,139,250,0.4)";
      badgeEl.style.background = "rgba(167,139,250,0.12)";
    } else if (item.is_directive_rest) {
      badgeEl.textContent = "📋 Schedule Directive";
      badgeEl.style.color = "#10b981";
      badgeEl.style.borderColor = "rgba(16,185,129,0.4)";
      badgeEl.style.background = "rgba(16,185,129,0.12)";
    } else if (item.is_coach_scheduled) {
      badgeEl.textContent = "💬 Coach Scheduled";
      badgeEl.style.color = "var(--accent-cyan)";
      badgeEl.style.borderColor = "rgba(6,182,212,0.4)";
      badgeEl.style.background = "rgba(6,182,212,0.12)";
    } else {
      badgeEl.textContent = "⭐ Coach Forecast";
      badgeEl.style.color = "var(--accent-cyan)";
      badgeEl.style.borderColor = "rgba(6,182,212,0.3)";
      badgeEl.style.background = "rgba(6,182,212,0.08)";
    }
  }

  // Recovery & Zone
  let zoneColor = "#10b981";
  let zoneBg = "rgba(16, 185, 129, 0.15)";
  const z = (item.projected_zone || "").toLowerCase();
  if (z === "yellow") {
    zoneColor = "#f59e0b";
    zoneBg = "rgba(245, 158, 11, 0.15)";
  } else if (z === "red") {
    zoneColor = "#f43f5e";
    zoneBg = "rgba(244, 63, 94, 0.15)";
  }

  if (recPillEl) {
    recPillEl.textContent = `⚡ ~${item.projected_recovery}% ${(item.projected_zone || '').toUpperCase()}`;
    recPillEl.style.color = zoneColor;
    recPillEl.style.borderColor = `${zoneColor}50`;
    recPillEl.style.background = zoneBg;
  }
  if (recSubEl) {
    recSubEl.textContent = `Projected Readiness for ${item.date_relative || 'Day'}`;
  }

  // Quick Metrics
  const durEl = document.getElementById("forecastModalDur");
  const xssEl = document.getElementById("forecastModalXss");
  const tssEl = document.getElementById("forecastModalTss");
  const focusDurEl = document.getElementById("forecastModalFocusDur");
  const graphDurEl = document.getElementById("forecastModalGraphDuration");
  const ftpLineLbl = document.getElementById("forecastModalFtpLineLbl");

  if (durEl) durEl.textContent = `${item.duration_min || 0} min`;
  if (xssEl) xssEl.textContent = item.estimated_xss ? `~${item.estimated_xss} XSS` : `${item.estimated_tss || 0} TSS`;
  if (tssEl) tssEl.textContent = `${item.estimated_tss || 0} TSS`;
  if (focusDurEl) focusDurEl.textContent = item.focus_duration || "Endurance Base";
  if (graphDurEl) graphDurEl.textContent = `• ${item.duration_min || 0}:00 Total`;
  if (ftpLineLbl) ftpLineLbl.textContent = `-- 100% FTP (${state.ftp || 250}W)`;

  // Coach Rationale
  const rationaleEl = document.getElementById("forecastModalRationale");
  if (rationaleEl) {
    rationaleEl.textContent = item.ai_rationale || item.description || "Adaptive workout prescribed to build aerobic fitness and match weekly periodization.";
  }

  // Open the Modal first so canvas has dimensions in DOM
  modal.classList.add("open", "active");

  // Render Canvas with requestAnimationFrame to ensure accurate canvas width
  requestAnimationFrame(() => {
    drawForecastCanvas(item);
  });

  // Render Step-by-Step Intervals Table
  renderForecastSteps(item);

  // Zwift Button Setup
  const btnPushZwift = document.getElementById("btnForecastPushZwift");
  if (btnPushZwift) {
    const isRest = (item.duration_min === 0) || item.is_directive_rest || (item.title && item.title.toLowerCase().includes("rest"));
    if (isRest) {
      btnPushZwift.style.display = "none";
    } else {
      btnPushZwift.style.display = "inline-flex";
      btnPushZwift.onclick = async () => {
        btnPushZwift.textContent = "⏳ Sending to Zwift...";
        btnPushZwift.disabled = true;
        try {
          const payload = {
            target_date: item.target_date || item.date_iso,
            workout: {
              title: item.title,
              duration_minutes: item.duration_min,
              estimated_tss: item.estimated_tss,
              focus_area: item.focus,
              description: item.description,
              intervals: item.intervals || []
            }
          };
          const res = await fetch("/api/workouts/push-intervals-icu", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          const result = await res.json();
          if (result.success) {
            btnPushZwift.textContent = "✅ Synced to Zwift!";
            showToast(`🚀 "${item.title}" successfully synced to Zwift for ${item.date_formatted}!`);
            setTimeout(() => {
              btnPushZwift.textContent = "🚀 Push to Zwift for This Day";
              btnPushZwift.disabled = false;
            }, 3000);
          } else {
            showToast(result.error || "Failed to push to Zwift.");
            btnPushZwift.textContent = "🚀 Push to Zwift for This Day";
            btnPushZwift.disabled = false;
          }
        } catch (err) {
          showToast("⚠️ Network error syncing to Zwift.");
          btnPushZwift.textContent = "🚀 Push to Zwift for This Day";
          btnPushZwift.disabled = false;
        }
      };
    }
  }

  // Discuss in Coach Chat Button Setup
  const btnDiscuss = document.getElementById("btnForecastDiscussCoach");
  if (btnDiscuss) {
    btnDiscuss.onclick = () => {
      modal.classList.remove("open", "active");
      const coachDrawer = document.getElementById("coachChatDrawer");
      const backdrop = document.getElementById("coachChatBackdrop");
      if (coachDrawer) coachDrawer.classList.add("open");
      if (backdrop) backdrop.classList.add("open");
      const input = document.getElementById("inputCoachMessage");
      if (input) {
        input.value = `Can you explain the plan for ${item.date_relative}'s ${item.title} (${item.duration_min}m)? What should my target pacing and nutrition strategy be?`;
        input.focus();
      }
    };
  }
}

function drawForecastCanvas(item) {
  const canvas = document.getElementById("forecastIntervalCanvas");
  if (!canvas) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const displayWidth = Math.max(Math.round(rect.width), 300);
  const displayHeight = Math.max(Math.round(rect.height), 150);
  canvas.width = displayWidth * dpr;
  canvas.height = displayHeight * dpr;

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const w = displayWidth;
  const h = displayHeight;

  ctx.clearRect(0, 0, w, h);

  const rawIntervals = (item && item.intervals) || [];
  const flattened = [];

  for (const seg of rawIntervals) {
    const t = (seg.type || "").toLowerCase();
    if (t === "repeats" || t === "intervalblock" || t === "intervals") {
      const reps = seg.repeat || 1;
      for (let r = 0; r < reps; r++) {
        flattened.push({
          duration_sec: seg.on_duration_sec,
          power_pct: seg.on_power_pct,
          cadence: seg.cadence || 92,
          name: `${seg.name || "Work"} (Rep ${r + 1}/${reps})`,
          type: "interval"
        });
        flattened.push({
          duration_sec: seg.off_duration_sec,
          power_pct: seg.off_power_pct,
          cadence: seg.cadence_rest || 85,
          name: "Rest Valley",
          type: "rest"
        });
      }
    } else if (t === "warmup") {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_low_pct: seg.power_low_pct || 45,
        power_high_pct: seg.power_high_pct || 75,
        cadence: seg.cadence || 88,
        type: "ramp",
        name: seg.name || "Warmup Ramp"
      });
    } else if (t === "cooldown") {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_low_pct: seg.power_low_pct || 65,
        power_high_pct: seg.power_high_pct || 40,
        cadence: seg.cadence || 82,
        type: "ramp",
        name: seg.name || "Cooldown Ramp"
      });
    } else {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_pct: seg.power_pct || 65,
        cadence: seg.cadence || 90,
        type: "steady",
        name: seg.name || "Steady"
      });
    }
  }

  if (flattened.length === 0) {
    ctx.fillStyle = "rgba(0, 200, 150, 0.08)";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#00C896";
    ctx.font = "bold 13px Outfit, Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("🛋️ Rest Day Directive • Rest & Recovery", w / 2, h / 2 - 8);
    ctx.fillStyle = "#64748B";
    ctx.font = "11px Inter, sans-serif";
    ctx.fillText("Off-the-bike recovery or gentle flush spin (<55% FTP) to support supercompensation.", w / 2, h / 2 + 14);
    ctx.textAlign = "left";
    return;
  }

  const totalSec = flattened.reduce((sum, s) => sum + (s.duration_sec || 0), 0) || 2700;
  const maxPowerPct = 125;
  const bottomPadding = 12;
  const topPadding = 18;
  const chartHeight = h - bottomPadding - topPadding;
  const athleteFtp = state.ftp || 250;

  // Draw 100% FTP line
  const ftpY = h - bottomPadding - (100 / maxPowerPct) * chartHeight;
  ctx.strokeStyle = "rgba(17, 22, 37, 0.22)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(0, ftpY);
  ctx.lineTo(w, ftpY);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "rgba(17, 22, 37, 0.65)";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText(`100% FTP (${athleteFtp}W)`, 6, ftpY - 4);

  let currentX = 0;
  for (let i = 0; i < flattened.length; i++) {
    const seg = flattened[i];
    const segW = (seg.duration_sec / totalSec) * w;

    if (seg.type === "ramp") {
      const avgPct = (seg.power_low_pct + seg.power_high_pct) / 2;
      const zone = getPowerZone(avgPct);
      const startH = (seg.power_low_pct / maxPowerPct) * chartHeight;
      const endH = (seg.power_high_pct / maxPowerPct) * chartHeight;

      const yStart = h - bottomPadding - startH;
      const yEnd = h - bottomPadding - endH;

      ctx.beginPath();
      ctx.moveTo(currentX, h - bottomPadding);
      ctx.lineTo(currentX, yStart);
      ctx.lineTo(currentX + segW, yEnd);
      ctx.lineTo(currentX + segW, h - bottomPadding);
      ctx.closePath();

      const grad = ctx.createLinearGradient(0, Math.min(yStart, yEnd), 0, h - bottomPadding);
      grad.addColorStop(0, zone.color);
      grad.addColorStop(1, `${zone.color}35`);
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.strokeStyle = zone.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    } else {
      const pct = seg.power_pct || 65;
      const zone = getPowerZone(pct);
      const segH = Math.min((pct / maxPowerPct) * chartHeight, chartHeight + 10);
      const y = h - bottomPadding - segH;

      const grad = ctx.createLinearGradient(0, y, 0, h - bottomPadding);
      grad.addColorStop(0, zone.color);
      grad.addColorStop(1, `${zone.color}35`);
      ctx.fillStyle = grad;
      ctx.fillRect(currentX, y, segW, segH);

      ctx.strokeStyle = zone.color;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(currentX, y, segW, segH);

      if (segW > 38) {
        ctx.fillStyle = "#FFFFFF";
        ctx.font = "bold 10px Outfit, Inter, sans-serif";
        ctx.textAlign = "center";
        const watts = Math.round(athleteFtp * (pct / 100));
        ctx.fillText(`${watts}W`, currentX + segW / 2, y + 14);
        ctx.textAlign = "left";
      }
    }

    currentX += segW;
  }
}

function renderForecastSteps(item) {
  const container = document.getElementById("forecastStepsList");
  const countBadge = document.getElementById("forecastStepsCountBadge");
  if (!container) return;

  const rawIntervals = (item && item.intervals) || [];
  if (rawIntervals.length === 0) {
    if (countBadge) countBadge.textContent = "Rest Day";
    container.innerHTML = `
      <div style="font-size:0.78rem;color:var(--text-muted);padding:0.75rem;text-align:center;">
        🛋️ No structured intervals scheduled for this day (Rest / Recovery).
      </div>
    `;
    return;
  }

  const flattened = [];
  for (const seg of rawIntervals) {
    const t = (seg.type || "").toLowerCase();
    if (t === "repeats" || t === "intervalblock" || t === "intervals") {
      const reps = seg.repeat || 1;
      for (let r = 0; r < reps; r++) {
        flattened.push({
          duration_sec: seg.on_duration_sec,
          power_pct: seg.on_power_pct,
          cadence: seg.cadence || 92,
          name: `${seg.name || "Work Interval"} (Rep ${r + 1}/${reps})`,
          is_ramp: false
        });
        flattened.push({
          duration_sec: seg.off_duration_sec,
          power_pct: seg.off_power_pct,
          cadence: seg.cadence_rest || 85,
          name: "Rest Valley",
          is_ramp: false
        });
      }
    } else if (t === "warmup") {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_low_pct: seg.power_low_pct || 45,
        power_high_pct: seg.power_high_pct || 75,
        cadence: seg.cadence || 88,
        name: seg.name || "Progressive Warmup Ramp",
        is_ramp: true
      });
    } else if (t === "cooldown") {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_low_pct: seg.power_low_pct || 65,
        power_high_pct: seg.power_high_pct || 40,
        cadence: seg.cadence || 82,
        name: seg.name || "Progressive Cooldown Ramp",
        is_ramp: true
      });
    } else {
      flattened.push({
        duration_sec: seg.duration_sec,
        power_pct: seg.power_pct || 65,
        cadence: seg.cadence || 90,
        name: seg.name || "Steady Endurance",
        is_ramp: false
      });
    }
  }

  if (countBadge) {
    countBadge.textContent = `${flattened.length} Steps • ${item.duration_min || 0}m`;
  }

  const athleteFtp = state.ftp || 250;
  container.innerHTML = flattened.map((step, idx) => {
    let zoneClass = "zone-z2";
    let powerDisplay = "";
    const avgPct = step.is_ramp ? Math.round((step.power_low_pct + step.power_high_pct) / 2) : step.power_pct;
    const zone = getPowerZone(avgPct);

    if (avgPct < 55) zoneClass = "zone-z1";
    else if (avgPct <= 75) zoneClass = "zone-z2";
    else if (avgPct <= 90) zoneClass = (avgPct >= 88) ? "zone-ss" : "zone-z3";
    else if (avgPct <= 105) zoneClass = (avgPct <= 94) ? "zone-ss" : "zone-z4";
    else if (avgPct <= 120) zoneClass = "zone-z5";
    else if (avgPct <= 150) zoneClass = "zone-z6";
    else zoneClass = "zone-z7";

    if (step.is_ramp) {
      const lowW = Math.round(athleteFtp * (step.power_low_pct / 100));
      const highW = Math.round(athleteFtp * (step.power_high_pct / 100));
      powerDisplay = `${lowW}W &rarr; ${highW}W (${step.power_low_pct}% &rarr; ${step.power_high_pct}%)`;
    } else {
      const watts = Math.round(athleteFtp * (step.power_pct / 100));
      powerDisplay = `<b>${watts}W</b> (${step.power_pct}% FTP)`;
    }

    const durMins = formatTime(step.duration_sec);

    return `
      <div class="forecast-step-row ${zoneClass}">
        <div style="display:flex;align-items:center;gap:0.45rem;min-width:0;flex:1;">
          <span style="font-size:0.68rem;color:var(--text-muted);font-weight:700;min-width:18px;">#${idx + 1}</span>
          <div style="min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            <div style="font-weight:600;color:#111625;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${step.name}</div>
            <div style="font-size:0.68rem;color:${zone.color};font-weight:600;">${zone.short} • ⏱️ ${durMins}</div>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          <div style="font-size:0.75rem;color:#111625;">${powerDisplay}</div>
          <div style="font-size:0.68rem;color:var(--text-muted);">${step.cadence || 90} RPM</div>
        </div>
      </div>
    `;
  }).join("");
}

// ============================================================================
// UPCOMING TARGET PLANS & TAPER SCHEDULER
// ============================================================================
let activeTargetPlan = null;

async function loadUpcomingPlan() {
  try {
    const res = await fetch("/api/plans/active");
    const data = await res.json();
    renderUpcomingPlan(data);
  } catch (err) {
    console.error("Failed to load upcoming target plan:", err);
  }
}

function renderUpcomingPlan(data) {
  const card = document.getElementById("cardUpcomingPlan");
  const activeView = document.getElementById("upcomingActiveView");
  const emptyView = document.getElementById("upcomingEmptyView");
  if (!card || !activeView) return;

  if (data && data.has_active_plan && data.plan) {
    activeTargetPlan = data.plan;
    card.style.display = "block";
    activeView.style.display = "block";
    if (emptyView) emptyView.style.display = "none";

    const p = data.plan;
    const daysUntil = p.days_until !== null && p.days_until !== undefined ? p.days_until : 0;
    const cdBadge = document.getElementById("upcomingCountdownBadge");
    const phaseBadge = document.getElementById("upcomingPhaseBadge");
    const titleElem = document.getElementById("upcomingPlanTitle");
    const descElem = document.getElementById("upcomingPlanDesc");

    if (cdBadge) {
      if (daysUntil === 0) {
        cdBadge.textContent = "🏁 Event Day Today!";
        cdBadge.style.color = "#ec4899";
        cdBadge.style.borderColor = "rgba(236,72,153,0.5)";
      } else {
        cdBadge.textContent = `🎯 T-${daysUntil} Days Remaining • ${p.target_date}`;
        cdBadge.style.color = "#fbbf24";
        cdBadge.style.borderColor = "rgba(245,158,11,0.4)";
      }
    }

    if (phaseBadge) {
      if (daysUntil === 0) phaseBadge.textContent = "Execution Phase";
      else if (daysUntil === 1) phaseBadge.textContent = "Neuromuscular Primer Phase";
      else if (daysUntil === 2) phaseBadge.textContent = "Active Flush Phase";
      else if (daysUntil === 3) phaseBadge.textContent = "Taper Onset Phase";
      else phaseBadge.textContent = "Volume Management Protocol";
    }

    if (titleElem) titleElem.textContent = p.title;
    if (descElem) descElem.textContent = p.description || `${p.distance_miles} mile planned session.`;

    const distElem = document.getElementById("upcomingMetaDist");
    const elevElem = document.getElementById("upcomingMetaElev");
    const durElem = document.getElementById("upcomingMetaDur");
    const tssElem = document.getElementById("upcomingMetaTss");
    const intElem = document.getElementById("upcomingMetaIntensity");

    if (distElem) distElem.textContent = `${p.distance_miles || 0} mi`;
    if (elevElem) elevElem.textContent = `${p.elevation_gain_ft ? Number(p.elevation_gain_ft).toLocaleString() : 0} ft`;
    if (durElem) {
      const durM = p.estimated_duration_min || 0;
      durElem.textContent = durM >= 60 ? `~${Math.floor(durM / 60)}h ${durM % 60}m` : `~${durM}m`;
    }
    if (tssElem) tssElem.textContent = `~${p.estimated_tss || 0} TSS`;
    if (intElem) intElem.textContent = p.intensity_type || "Endurance";

    // Update collapsed summary for upcoming plan
    const collapsedUpcomingDist = document.getElementById("collapsedUpcomingDist");
    if (collapsedUpcomingDist) collapsedUpcomingDist.textContent = `${p.distance_miles || 0} mi`;
    const collapsedUpcomingDur = document.getElementById("collapsedUpcomingDur");
    if (collapsedUpcomingDur) {
      const durM = p.estimated_duration_min || 0;
      collapsedUpcomingDur.textContent = durM >= 60 ? `~${Math.floor(durM / 60)}h ${durM % 60}m` : `~${durM}m`;
    }
    const collapsedUpcomingTss = document.getElementById("collapsedUpcomingTss");
    if (collapsedUpcomingTss) collapsedUpcomingTss.textContent = `~${p.estimated_tss || 0} TSS`;
    const collapsedUpcomingIntensity = document.getElementById("collapsedUpcomingIntensity");
    if (collapsedUpcomingIntensity) collapsedUpcomingIntensity.textContent = p.intensity_type || "Endurance";

    // Map SVG preview
    const mapWrap = document.getElementById("upcomingRouteMapWrap");
    const mapSvg = document.getElementById("upcomingRouteSvg");
    if (mapWrap && mapSvg) {
      if (p.svg_path) {
        mapSvg.innerHTML = `<path d="${p.svg_path}" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`;
        mapWrap.style.display = "block";
      } else {
        mapWrap.style.display = "none";
      }
    }

    // Render roadmap schedule
    const taperGrid = document.getElementById("upcomingTaperGrid");
    if (taperGrid && data.schedule) {
      taperGrid.innerHTML = data.schedule.map(step => {
        const isToday = step.day_offset === 0;
        const isEvent = step.is_event_day;
        const cls = isEvent ? "taper-step-card event-day" : (isToday ? "taper-step-card active-today" : "taper-step-card");
        return `
          <div class="${cls}">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
              <span style="font-size:0.75rem;font-weight:700;color:${isEvent ? '#ec4899' : (isToday ? 'var(--accent-cyan)' : 'var(--text-muted)')};">${step.date_formatted}</span>
              <span style="font-size:0.7rem;font-weight:700;color:${step.badge_color === 'magenta' ? '#ec4899' : (step.badge_color === 'cyan' ? '#06b6d4' : '#10b981')};">${step.relative_label}</span>
            </div>
            <div style="font-size:0.82rem;font-weight:700;color:var(--text-primary);margin-bottom:0.15rem;">${step.title}</div>
            <div style="font-size:0.72rem;color:var(--text-muted);">${step.duration_min}m • ~${step.estimated_tss} TSS</div>
            <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:0.25rem;line-height:1.35;">${step.directive}</div>
          </div>
        `;
      }).join("");
    }
  } else {
    activeTargetPlan = null;
    activeView.style.display = "none";
    if (emptyView) emptyView.style.display = "none";
    card.style.display = "none";
  }
}

// Plan Builder Modal Handlers
const modalUpcomingPlan = document.getElementById("modalUpcomingPlan");
const btnOpenPlanBuilder = document.getElementById("btnOpenPlanBuilder");
const btnClosePlanModal = document.getElementById("btnClosePlanModal");
const btnCancelPlanModal = document.getElementById("btnCancelPlanModal");
const btnEditUpcomingPlan = document.getElementById("btnEditUpcomingPlan");
const btnClearUpcomingPlan = document.getElementById("btnClearUpcomingPlan");
const btnAutoParsePlan = document.getElementById("btnAutoParsePlan");
const inputPlanDescribe = document.getElementById("inputPlanDescribe");
const btnQuickSetPlan = document.getElementById("btnQuickSetPlan");
const inputQuickPlanText = document.getElementById("inputQuickPlanText");
const btnSubmitUpcomingPlan = document.getElementById("btnSubmitUpcomingPlan");

if (btnOpenPlanBuilder) {
  btnOpenPlanBuilder.addEventListener("click", (e) => {
    e.stopPropagation();
    if (modalUpcomingPlan) {
      modalUpcomingPlan.classList.add("open");
      modalUpcomingPlan.classList.add("active");
    }
    loadStravaCandidatesIntoSelect();
  });
}
if (btnEditUpcomingPlan) {
  btnEditUpcomingPlan.addEventListener("click", () => {
    if (modalUpcomingPlan) {
      modalUpcomingPlan.classList.add("open");
      modalUpcomingPlan.classList.add("active");
    }
    if (activeTargetPlan) {
      if (inputPlanDescribe) inputPlanDescribe.value = activeTargetPlan.description || "";
      const distInp = document.getElementById("inputPlanDistance");
      const elevInp = document.getElementById("inputPlanElevation");
      const dateInp = document.getElementById("inputPlanDate");
      const intInp = document.getElementById("selectPlanIntensity");
      if (distInp) distInp.value = activeTargetPlan.distance_miles || "";
      if (elevInp) elevInp.value = activeTargetPlan.elevation_gain_ft || "";
      if (dateInp) dateInp.value = activeTargetPlan.target_date || "";
      if (intInp) intInp.value = activeTargetPlan.intensity_type || "Endurance";
    }
    loadStravaCandidatesIntoSelect();
  });
}
if (btnClosePlanModal) btnClosePlanModal.addEventListener("click", () => {
  if (modalUpcomingPlan) {
    modalUpcomingPlan.classList.remove("open");
    modalUpcomingPlan.classList.remove("active");
  }
});
if (btnCancelPlanModal) btnCancelPlanModal.addEventListener("click", () => {
  if (modalUpcomingPlan) {
    modalUpcomingPlan.classList.remove("open");
    modalUpcomingPlan.classList.remove("active");
  }
});
if (modalUpcomingPlan) {
  modalUpcomingPlan.addEventListener("click", (e) => {
    if (e.target === modalUpcomingPlan) {
      modalUpcomingPlan.classList.remove("open");
      modalUpcomingPlan.classList.remove("active");
    }
  });
}

// Source tabs in Plan Modal
const planSourceTabs = document.getElementById("planSourceTabs");
if (planSourceTabs) {
  planSourceTabs.querySelectorAll(".mode-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      planSourceTabs.querySelectorAll(".mode-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const src = tab.dataset.source;
      const pManual = document.getElementById("planSourceManual");
      const pStrava = document.getElementById("planSourceStrava");
      const pGpx = document.getElementById("planSourceGpx");
      if (pManual) pManual.style.display = src === "manual" ? "block" : "none";
      if (pStrava) pStrava.style.display = src === "strava" ? "block" : "none";
      if (pGpx) pGpx.style.display = src === "gpx" ? "block" : "none";
    });
  });
}

// Auto Parse Description
if (btnAutoParsePlan && inputPlanDescribe) {
  btnAutoParsePlan.addEventListener("click", async () => {
    const text = inputPlanDescribe.value.trim();
    if (!text) return;
    try {
      btnAutoParsePlan.textContent = "⏳ Parsing...";
      const res = await fetch("/api/plans/parse-description", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const data = await res.json();
      btnAutoParsePlan.textContent = "✨ Auto-Parse";
      if (data.success) {
        const distInp = document.getElementById("inputPlanDistance");
        const elevInp = document.getElementById("inputPlanElevation");
        const dateInp = document.getElementById("inputPlanDate");
        const intInp = document.getElementById("selectPlanIntensity");
        if (distInp) distInp.value = data.distance_miles;
        if (elevInp) elevInp.value = data.elevation_gain_ft;
        if (dateInp) dateInp.value = data.target_date;
        if (intInp) intInp.value = data.intensity_type;
        showToast(`Parsed: ${data.distance_miles} mi on ${data.target_date}`);
      }
    } catch (e) {
      btnAutoParsePlan.textContent = "✨ Auto-Parse";
      console.error(e);
    }
  });
}

// Quick Set Plan Bar
if (btnQuickSetPlan && inputQuickPlanText) {
  btnQuickSetPlan.addEventListener("click", async () => {
    const text = inputQuickPlanText.value.trim();
    if (!text) return;
    try {
      btnQuickSetPlan.textContent = "⏳ Setting...";
      const parseRes = await fetch("/api/plans/parse-description", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const parsed = await parseRes.json();
      if (parsed.success) {
        const saveRes = await fetch("/api/plans", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed)
        });
        const saved = await saveRes.json();
        btnQuickSetPlan.textContent = "⚡ Set Plan & Adapt Days";
        if (saved.success) {
          showToast(`🎯 Plan active: ${saved.plan.title}`);
          renderUpcomingPlan(saved);
          await loadWorkout(60, 0, "");
          await loadDebrief();
        }
      }
    } catch (e) {
      btnQuickSetPlan.textContent = "⚡ Set Plan & Adapt Days";
      console.error(e);
    }
  });
}

// Clear Plan
if (btnClearUpcomingPlan) {
  btnClearUpcomingPlan.addEventListener("click", async () => {
    if (!confirm("Clear upcoming target plan and revert to standard progression?")) return;
    try {
      const res = await fetch("/api/plans/clear", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        showToast("Training plan cleared. Deload & recovery active.");
        if (data.active_workout || data.workout) {
          const activeW = data.active_workout || data.workout;
          state.currentWorkout = activeW;
          state.activeOptionId = activeW.id;
          state.currentDuration = activeW.duration_minutes;
          if (data.options) state.workoutOptions = data.options;
          syncDurationPills(state.currentDuration);
          renderWorkout(state.currentWorkout);
          renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
          renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
        }
        if (data.program) {
          state.program = data.program;
          if (typeof renderProgram === "function") {
            renderProgram(state.program);
          }
        }
        await loadUpcomingPlan();
        await loadDebrief();
        await loadDashboard();
        await loadWorkout();
      }
    } catch (e) {
      console.error(e);
    }
  });
}

// Submit Plan Modal
if (btnSubmitUpcomingPlan) {
  btnSubmitUpcomingPlan.addEventListener("click", async () => {
    const distInp = document.getElementById("inputPlanDistance");
    const elevInp = document.getElementById("inputPlanElevation");
    const dateInp = document.getElementById("inputPlanDate");
    const intInp = document.getElementById("selectPlanIntensity");
    const desc = inputPlanDescribe ? inputPlanDescribe.value.trim() : "";

    const dist = parseFloat(distInp ? distInp.value : 50) || 50;
    const elev = parseFloat(elevInp ? elevInp.value : 2500) || 2500;
    const targetDate = (dateInp && dateInp.value) ? dateInp.value : new Date(Date.now() + 6*86400000).toISOString().split('T')[0];
    const intensity = intInp ? intInp.value : "Endurance";

    const payload = {
      title: `${Math.round(dist)}-Mile Target Ride`,
      description: desc || `${dist} mile planned ride`,
      distance_miles: dist,
      elevation_gain_ft: elev,
      target_date: targetDate,
      intensity_type: intensity,
      route_source: "manual"
    };

    // Check if Strava route was selected
    const selStrava = document.getElementById("selectStravaRouteCandidate");
    if (selStrava && selStrava.value && selStrava.selectedOptions[0]) {
      const opt = selStrava.selectedOptions[0];
      payload.title = opt.dataset.title || payload.title;
      payload.summary_polyline = opt.dataset.polyline || "";
      payload.svg_path = opt.dataset.svg || "";
      payload.strava_id = selStrava.value;
      payload.route_source = "strava_activity";
    }

    try {
      const res = await fetch("/api/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        if (modalUpcomingPlan) {
          modalUpcomingPlan.classList.remove("open");
          modalUpcomingPlan.classList.remove("active");
        }
        showToast(`🎯 Plan saved: ${data.plan.title}`);
        renderUpcomingPlan(data);
        await loadWorkout(60, 0, "");
        await loadDebrief();
      }
    } catch (e) {
      console.error(e);
    }
  });
}

// Strava Candidates in Select
async function loadStravaCandidatesIntoSelect() {
  const sel = document.getElementById("selectStravaRouteCandidate");
  if (!sel || sel.children.length > 1) return;
  try {
    const res = await fetch("/api/plans/strava-candidates");
    const data = await res.json();
    if (data.success && data.candidates) {
      sel.innerHTML = '<option value="">-- Choose a Strava Route --</option>' + data.candidates.map(c => `
        <option value="${c.id}" data-title="${c.title}" data-dist="${c.distance_miles}" data-elev="${c.elevation_gain_ft}" data-polyline="${c.summary_polyline}" data-svg="${c.svg_path}">
          ${c.title} (${c.distance_miles} mi • ${c.elevation_gain_ft} ft)
        </option>
      `).join("");

      sel.addEventListener("change", () => {
        const opt = sel.selectedOptions[0];
        if (opt && opt.value) {
          const distInp = document.getElementById("inputPlanDistance");
          const elevInp = document.getElementById("inputPlanElevation");
          if (distInp) distInp.value = opt.dataset.dist;
          if (elevInp) elevInp.value = opt.dataset.elev;
        }
      });
    }
  } catch (e) {
    console.error(e);
  }
}

// GPX File Upload for Plan Builder
const inputPlanGpxFile = document.getElementById("inputPlanGpxFile");
if (inputPlanGpxFile) {
  inputPlanGpxFile.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (evt) => {
      const gpxText = evt.target.result;
      try {
        const res = await fetch("/api/plans/upload-gpx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gpx_content: gpxText, filename: file.name })
        });
        const data = await res.json();
        if (data.success) {
          const distInp = document.getElementById("inputPlanDistance");
          const elevInp = document.getElementById("inputPlanElevation");
          const fn = document.getElementById("planGpxFilename");
          if (distInp) distInp.value = data.distance_miles;
          if (elevInp) elevInp.value = data.elevation_gain_ft;
          if (fn) fn.textContent = `✓ ${data.title} (${data.distance_miles} mi, ${data.elevation_gain_ft} ft)`;
          showToast(`GPX parsed: ${data.distance_miles} mi`);
        }
      } catch (err) {
        console.error(err);
      }
    };
    reader.readAsText(file);
  });
}

// ============================================================================
// FUELING & NUTRITION PLAN CONTROLLERS
// ============================================================================
let currentFuelingPlan = null;

function positionFuelingPanel(mode = null) {
  const panel = document.getElementById("fuelingPlanPanel");
  if (!panel) return;
  const targetMode = mode || state.trainingMode || "indoor";
  const container = targetMode === "outdoor" ? document.getElementById("outdoorContainer") : document.getElementById("indoorContainer");
  if (!container) return;
  const header = container.querySelector(".workout-header");
  if (header) {
    header.insertAdjacentElement("afterend", panel);
  }
}
window.positionFuelingPanel = positionFuelingPanel;

function loadFuelingPlanForRide(ride, isOutdoor = false) {
  if (!ride) {
    loadFuelingPlan();
    return;
  }
  const durMin = Math.round((ride.moving_time_sec || (ride.moving_time_min ? ride.moving_time_min * 60 : 0) || (ride.duration_minutes ? ride.duration_minutes * 60 : 3600)) / 60);
  const distMi = ride.distance_miles || (ride.distance_km ? parseFloat((ride.distance_km * 0.621371).toFixed(1)) : 0.0);
  const avgW = ride.average_watts || Math.round(state.ftp * 0.68);
  const title = ride.title || ride.name || "Selected Ride";
  const intensity = ride.focus_area || ride.target_zone || (isOutdoor ? "Zone 2 Base" : "Endurance");

  loadFuelingPlan({
    duration_min: durMin,
    distance_miles: distMi,
    avg_power_watts: avgW,
    ride_title: title,
    intensity_type: intensity,
    is_outdoor: isOutdoor
  });
}

async function loadFuelingPlan(customParams = null) {
  try {
    const tempSlider = document.getElementById("fuelingTempSlider");
    const humSlider = document.getElementById("fuelingHumiditySlider");
    const outCheck = document.getElementById("fuelingOutdoorCheck");

    const temp_f = tempSlider ? parseInt(tempSlider.value, 10) : 74;
    const humidity_pct = humSlider ? parseInt(humSlider.value, 10) : 50;

    // Determine outdoor status
    let effectiveIsOutdoor;
    if (outCheck) {
      if (customParams && typeof customParams.is_outdoor === "boolean") {
        effectiveIsOutdoor = customParams.is_outdoor;
        outCheck.checked = effectiveIsOutdoor;
      } else {
        effectiveIsOutdoor = outCheck.checked;
      }
    } else {
      effectiveIsOutdoor = (customParams && typeof customParams.is_outdoor === "boolean")
        ? customParams.is_outdoor
        : (state.trainingMode === "outdoor");
    }

    if (!customParams) {
      if (state.trainingMode === "outdoor" && state.currentOutdoorRide) {
        const r = state.currentOutdoorRide;
        const durMin = Math.round((r.moving_time_sec || (r.moving_time_min ? r.moving_time_min * 60 : 0) || 3600) / 60);
        const distMi = r.distance_miles || (r.distance_km ? parseFloat((r.distance_km * 0.621371).toFixed(1)) : 0.0);
        customParams = {
          duration_min: durMin,
          distance_miles: distMi,
          avg_power_watts: r.average_watts || Math.round(state.ftp * 0.68),
          ride_title: r.name || "Selected Outdoor Route",
          intensity_type: r.target_zone || "Zone 2 Base",
          is_outdoor: true
        };
        effectiveIsOutdoor = true;
        if (outCheck) outCheck.checked = true;
      } else if (state.currentWorkout) {
        const w = state.currentWorkout;
        const isCustOut = (w.option_type === "custom" && w.route_source !== "manual");
        customParams = {
          duration_min: w.duration_minutes || 60,
          distance_miles: w.distance_miles || 0,
          avg_power_watts: Math.round(state.ftp * 0.68),
          ride_title: w.title || "Selected Workout",
          intensity_type: w.focus_area || "Endurance",
          is_outdoor: isCustOut ? true : effectiveIsOutdoor
        };
      }
    }

    let res;
    if (customParams) {
      res = await fetch("/api/workouts/fueling-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...customParams, temp_f, humidity_pct, is_outdoor: effectiveIsOutdoor })
      });
    } else {
      res = await fetch(`/api/workouts/fueling-plan?temp_f=${temp_f}&humidity_pct=${humidity_pct}&is_outdoor=${effectiveIsOutdoor}`);
    }
    const data = await res.json();
    currentFuelingPlan = data;
    renderFuelingPlan(data);
  } catch (err) {
    console.error("Failed to load fueling plan:", err);
  }
}

function renderFuelingPlan(data) {
  if (!data || !data.success) return;

  const panel = document.getElementById("fuelingPlanPanel");
  if (panel) panel.style.display = "block";
  updateFuelingButtonStates();

  const titleElem = document.getElementById("fuelingRideTitle");
  if (titleElem) titleElem.textContent = `Fueling Strategy: ${data.ride_title} (${data.distance_miles} mi, ${data.duration_minutes}m)`;

  const carbsPerHr = document.getElementById("fuelingCarbsPerHour");
  const totalCarbs = document.getElementById("fuelingTotalCarbs");
  const totalCals = document.getElementById("fuelingTotalCals");
  const carbRatio = document.getElementById("fuelingCarbRatio");
  const fluidPerHr = document.getElementById("fuelingFluidPerHour");
  const totalFluid = document.getElementById("fuelingTotalFluid");
  const sodiumPerHr = document.getElementById("fuelingSodiumPerHour");
  const totalSodium = document.getElementById("fuelingTotalSodium");

  if (carbsPerHr) carbsPerHr.innerHTML = `${data.target_rates.carbs_per_hour_g} <span style="font-size:0.8rem;">g/h</span>`;
  if (totalCarbs) totalCarbs.innerHTML = `${data.target_rates.total_carbs_g} <span style="font-size:0.8rem;">g</span>`;
  if (totalCals) totalCals.textContent = `~${data.energy_expenditure.total_kcal} kcal burn`;
  if (carbRatio) carbRatio.textContent = data.target_rates.carb_ratio;
  if (fluidPerHr) fluidPerHr.innerHTML = `${data.target_rates.fluid_ml_per_hour} <span style="font-size:0.8rem;">ml/h</span>`;
  if (totalFluid) totalFluid.textContent = `~${data.target_rates.total_fluid_liters} L total`;
  if (sodiumPerHr) sodiumPerHr.innerHTML = `${data.target_rates.sodium_mg_per_hour} <span style="font-size:0.8rem;">mg/h</span>`;
  if (totalSodium) totalSodium.textContent = `~${data.target_rates.total_sodium_mg} mg total`;

  const weatherBadge = document.getElementById("fuelingWeatherBadge");
  if (weatherBadge) {
    if (data.environmental_summary && data.environmental_summary.summary_text) {
      weatherBadge.textContent = data.environmental_summary.summary_text;
    } else if (data.environmental_factors && data.environmental_factors.notes) {
      weatherBadge.textContent = data.environmental_factors.notes[0] || "Standard Climate Strategy";
    }
  }

  // Recovery & Trailing Stress Impact Bar
  if (data.recovery_summary) {
    const recSummary = data.recovery_summary;
    const recBar = document.getElementById("fuelingRecoveryImpactBar");
    const recTitle = document.getElementById("fuelingRecoveryTitle");
    const recDesc = document.getElementById("fuelingRecoveryDesc");
    const badgeScore = document.getElementById("fuelingBadgeRecScore");
    const badgeStrain = document.getElementById("fuelingBadgeStrain");
    const badgeTss = document.getElementById("fuelingBadgeYesterdayTss");
    const recIcon = document.getElementById("fuelingRecoveryIcon");

    if (recBar) recBar.style.display = "flex";
    if (recTitle) recTitle.textContent = recSummary.headline;
    if (recDesc) recDesc.textContent = recSummary.summary_text;
    if (recIcon) recIcon.textContent = recSummary.is_fatigue_compromised ? "⚡" : (recSummary.recovery_zone === "green" ? "🟢" : "🧬");

    if (badgeScore) {
      badgeScore.textContent = `Whoop: ${recSummary.recovery_score}%`;
      badgeScore.style.borderColor = recSummary.recovery_zone === "green" ? "rgba(16,185,129,0.4)" : (recSummary.recovery_zone === "red" ? "rgba(244,63,94,0.4)" : "rgba(245,158,11,0.4)");
      badgeScore.style.color = recSummary.recovery_zone === "green" ? "#10b981" : (recSummary.recovery_zone === "red" ? "#f43f5e" : "#f59e0b");
    }
    if (badgeStrain) {
      const trStr = (recSummary.trailing_strain_avg != null) ? Number(recSummary.trailing_strain_avg).toFixed(1) : "11.0";
      badgeStrain.textContent = `7D Strain: ${trStr}`;
      badgeStrain.style.color = (Number(recSummary.trailing_strain_avg || 0) >= 13.5) ? "#f59e0b" : "var(--text-secondary)";
    }
    if (badgeTss) {
      badgeTss.textContent = `Yesterday: ${recSummary.yesterday_tss} TSS`;
      badgeTss.style.color = recSummary.yesterday_tss >= 80 ? "#f59e0b" : "var(--text-secondary)";
    }
  }

  // Pre-ride
  const preCarbTarget = document.getElementById("fuelingPreCarbTarget");
  const preGuidelines = document.getElementById("fuelingPreGuidelines");
  const rolloutSnack = document.getElementById("fuelingRolloutSnack");

  if (preCarbTarget && data.pre_ride) preCarbTarget.textContent = `Target: ~${data.pre_ride.target_carbs_g}g Carbohydrates (${data.pre_ride.timing})`;
  if (preGuidelines && data.pre_ride && data.pre_ride.guidelines) {
    preGuidelines.innerHTML = data.pre_ride.guidelines.map(g => `<li>${g}</li>`).join("");
  }
  if (rolloutSnack && data.pre_ride) rolloutSnack.textContent = data.pre_ride.rollout_snack;

  // Post-ride
  const recTarget = document.getElementById("fuelingRecoveryTarget");
  const recGuidelines = document.getElementById("fuelingRecoveryGuidelines");
  if (recTarget && data.post_ride) recTarget.textContent = `Target: ~${data.post_ride.target_carbs_g}g Carbs + ${data.post_ride.target_protein_g}g Protein`;
  if (recGuidelines && data.post_ride && data.post_ride.guidelines) {
    recGuidelines.innerHTML = data.post_ride.guidelines.map(g => `<li>${g}</li>`).join("");
  }

  // Hourly grid
  const hourlyGrid = document.getElementById("fuelingHourlyGrid");
  if (hourlyGrid && data.hourly_timeline) {
    hourlyGrid.innerHTML = data.hourly_timeline.map(h => {
      const itemsHtml = h.fuel_items.map(it => `
        <div class="fuel-item-pill">
          <span>${it.time}: <b>${it.item}</b></span>
          <span style="color:#10b981;font-weight:700;">+${it.carbs}g</span>
        </div>
      `).join("");
      return `
        <div class="fueling-hour-card">
          <div class="fueling-hour-header">
            <span style="font-size:0.82rem;font-weight:800;color:#10b981;">${h.label}</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">${h.carbs_g}g carbs • ${h.fluid_ml}ml fluid</span>
          </div>
          ${itemsHtml}
          <div style="font-size:0.72rem;color:var(--text-secondary);margin-top:0.4rem;line-height:1.35;border-top:1px solid rgba(255,255,255,0.05);padding-top:0.35rem;">
            💡 ${h.coach_note}
          </div>
        </div>
      `;
    }).join("");
  }

  // Checklist
  const checkGrid = document.getElementById("fuelingChecklistGrid");
  if (checkGrid && data.packing_checklist) {
    checkGrid.innerHTML = data.packing_checklist.map(item => `
      <div class="checklist-item-row">
        <span style="font-size:1.1rem;">${item.icon}</span>
        <div style="flex:1;">
          <div style="font-weight:700;color:var(--text-primary);">${item.item}</div>
          <div style="font-size:0.72rem;color:var(--text-muted);">${item.detail}</div>
        </div>
        <input type="checkbox" style="cursor:pointer;width:16px;height:16px;" />
      </div>
    `).join("");
  }
}

// Fueling Plan Controls & Weather Adjustments
const btnToggleFuelingPlan = document.getElementById("btnToggleFuelingPlan");
const btnToggleOutdoorFueling = document.getElementById("btnToggleOutdoorFueling");
const btnCloseFuelingPanel = document.getElementById("btnCloseFuelingPanel");
const fuelingTempSlider = document.getElementById("fuelingTempSlider");
const fuelingHumiditySlider = document.getElementById("fuelingHumiditySlider");
const fuelingTempLabel = document.getElementById("fuelingTempLabel");
const fuelingHumidityLabel = document.getElementById("fuelingHumidityLabel");
const fuelingOutdoorCheck = document.getElementById("fuelingOutdoorCheck");
const btnViewPlanFueling = document.getElementById("btnViewPlanFueling");

function updateFuelingButtonStates() {
  const panel = document.getElementById("fuelingPlanPanel");
  const isOpen = panel && panel.style.display === "block";

  if (btnToggleFuelingPlan) {
    if (isOpen && state.trainingMode !== "outdoor") {
      btnToggleFuelingPlan.classList.add("active");
      btnToggleFuelingPlan.innerHTML = "✕ Close Fueling Plan";
    } else {
      btnToggleFuelingPlan.classList.remove("active");
      btnToggleFuelingPlan.innerHTML = "🥪 Fueling Plan";
    }
  }

  if (btnToggleOutdoorFueling) {
    if (isOpen && state.trainingMode === "outdoor") {
      btnToggleOutdoorFueling.classList.add("active");
      btnToggleOutdoorFueling.innerHTML = "✕ Close Fueling Plan";
    } else {
      btnToggleOutdoorFueling.classList.remove("active");
      btnToggleOutdoorFueling.innerHTML = "🥪 Fueling Plan";
    }
  }
}
window.updateFuelingButtonStates = updateFuelingButtonStates;

if (btnToggleFuelingPlan) {
  btnToggleFuelingPlan.addEventListener("click", () => {
    const panel = document.getElementById("fuelingPlanPanel");
    if (!panel) return;
    positionFuelingPanel("indoor");
    const isHidden = (panel.style.display === "none" || !panel.style.display);
    if (isHidden) {
      panel.style.display = "block";
      updateFuelingButtonStates();
      if (currentFuelingPlan) {
        renderFuelingPlan(currentFuelingPlan);
      }
      loadFuelingPlanForRide(state.currentWorkout, false);
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      panel.style.display = "none";
      updateFuelingButtonStates();
    }
  });
}

if (btnToggleOutdoorFueling) {
  btnToggleOutdoorFueling.addEventListener("click", () => {
    const panel = document.getElementById("fuelingPlanPanel");
    if (!panel) return;
    positionFuelingPanel("outdoor");
    const isHidden = (panel.style.display === "none" || !panel.style.display);
    if (isHidden) {
      panel.style.display = "block";
      updateFuelingButtonStates();
      if (currentFuelingPlan) {
        renderFuelingPlan(currentFuelingPlan);
      }
      loadFuelingPlanForRide(state.currentOutdoorRide, true);
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      panel.style.display = "none";
      updateFuelingButtonStates();
    }
  });
}

if (btnCloseFuelingPanel) {
  btnCloseFuelingPanel.addEventListener("click", () => {
    const panel = document.getElementById("fuelingPlanPanel");
    if (panel) panel.style.display = "none";
    updateFuelingButtonStates();
  });
}

function reloadFuelingForActiveRide() {
  const isOutdoor = fuelingOutdoorCheck ? fuelingOutdoorCheck.checked : (state.trainingMode === "outdoor");
  if (state.trainingMode === "outdoor" && state.currentOutdoorRide) {
    loadFuelingPlanForRide(state.currentOutdoorRide, isOutdoor);
  } else if (state.currentWorkout) {
    loadFuelingPlanForRide(state.currentWorkout, isOutdoor);
  } else {
    loadFuelingPlan({ is_outdoor: isOutdoor });
  }
}

if (fuelingTempSlider) {
  fuelingTempSlider.addEventListener("input", (e) => {
    if (fuelingTempLabel) fuelingTempLabel.textContent = `${e.target.value}°F`;
    reloadFuelingForActiveRide();
  });
}
if (fuelingHumiditySlider) {
  fuelingHumiditySlider.addEventListener("input", (e) => {
    if (fuelingHumidityLabel) fuelingHumidityLabel.textContent = `${e.target.value}%`;
    reloadFuelingForActiveRide();
  });
}
if (fuelingOutdoorCheck) {
  fuelingOutdoorCheck.addEventListener("change", () => reloadFuelingForActiveRide());
}

// Weather detection via browser geolocation & Open-Meteo
async function fetchCurrentLocalWeather(onSuccess) {
  if (!navigator.geolocation) {
    showToast("⚠️ Geolocation is not supported in this browser.");
    return;
  }
  showToast("📍 Fetching live local weather...");
  navigator.geolocation.getCurrentPosition(async (pos) => {
    try {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m&temperature_unit=fahrenheit`);
      const wdata = await res.json();
      if (wdata && wdata.current) {
        const temp = Math.round(wdata.current.temperature_2m);
        const hum = Math.round(wdata.current.relative_humidity_2m);
        
        const fTemp = document.getElementById("fuelingTempSlider");
        const fHum = document.getElementById("fuelingHumiditySlider");
        const fTempLbl = document.getElementById("fuelingTempLabel");
        const fHumLbl = document.getElementById("fuelingHumidityLabel");
        if (fTemp) fTemp.value = temp;
        if (fHum) fHum.value = hum;
        if (fTempLbl) fTempLbl.textContent = `${temp}°F`;
        if (fHumLbl) fHumLbl.textContent = `${hum}%`;

        const cTemp = document.getElementById("sliderCustomTemp");
        const cHum = document.getElementById("sliderCustomHumidity");
        const cTempLbl = document.getElementById("lblCustomTemp");
        const cHumLbl = document.getElementById("lblCustomHumidity");
        if (cTemp) cTemp.value = temp;
        if (cHum) cHum.value = hum;
        if (cTempLbl) cTempLbl.textContent = `${temp}°F`;
        if (cHumLbl) cHumLbl.textContent = `${hum}%`;

        showToast(`📍 Live weather applied: ${temp}°F, ${hum}% humidity`);
        if (onSuccess) onSuccess(temp, hum);
      }
    } catch (e) {
      console.warn("Weather fetch error:", e);
      showToast("⚠️ Could not fetch live weather. Using manual sliders.");
    }
  }, (err) => {
    console.warn("Geolocation permission error:", err);
    showToast("📍 Geolocation unavailable. Using manual sliders.");
  });
}

const btnFetchLocalWeather = document.getElementById("btnFetchLocalWeather");
if (btnFetchLocalWeather) {
  btnFetchLocalWeather.addEventListener("click", () => fetchCurrentLocalWeather(() => loadFuelingPlan()));
}

const btnFetchModalWeather = document.getElementById("btnFetchModalWeather");
if (btnFetchModalWeather) {
  btnFetchModalWeather.addEventListener("click", () => fetchCurrentLocalWeather());
}

// Inline GPX route upload in workout controls
const inputInlineGpxUpload = document.getElementById("inputInlineGpxUpload");
const chipAttachedRoute = document.getElementById("chipAttachedRoute");
const lblAttachedRouteName = document.getElementById("lblAttachedRouteName");
const btnRemoveAttachedRoute = document.getElementById("btnRemoveAttachedRoute");

if (inputInlineGpxUpload) {
  inputInlineGpxUpload.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = async (evt) => {
        try {
          showToast(`⏳ Parsing GPX route: ${file.name}...`);
          const res = await fetch("/api/plans/upload-gpx", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gpx_content: evt.target.result, filename: file.name })
          });
          const data = await res.json();
          if (data.success) {
            state.attachedRoute = {
              gpx_content: evt.target.result,
              filename: file.name,
              title: data.title,
              distance_miles: data.distance_miles,
              elevation_gain_ft: data.elevation_gain_ft,
              duration_min: data.estimated_duration_min,
              svg_path: data.svg_path
            };
            if (chipAttachedRoute) chipAttachedRoute.style.display = "inline-flex";
            if (lblAttachedRouteName) lblAttachedRouteName.textContent = `${data.title} (${data.distance_miles} mi, ${data.elevation_gain_ft} ft)`;
            
            showToast(`🗺️ Applying route plan: ${data.title}...`);
            await loadWorkout(null, state.currentIntensity);
            showToast(`✅ Route loaded: ${data.title} (${data.distance_miles} mi, ${data.elevation_gain_ft} ft elev)`);
          } else {
            showToast(`⚠️ Could not parse GPX: ${data.error || "Invalid file"}`);
          }
        } catch (err) {
          console.error(err);
          showToast("⚠️ Error reading GPX file.");
        }
      };
      reader.readAsText(file);
    }
  });
}

if (btnRemoveAttachedRoute) {
  btnRemoveAttachedRoute.addEventListener("click", async () => {
    state.attachedRoute = null;
    if (chipAttachedRoute) chipAttachedRoute.style.display = "none";
    if (inputInlineGpxUpload) inputInlineGpxUpload.value = "";
    showToast("Route unlinked. Restoring prescribed workout...");
    await loadWorkout(state.currentDuration, state.currentIntensity);
  });
}

if (btnViewPlanFueling) {
  btnViewPlanFueling.addEventListener("click", () => {
    positionFuelingPanel(state.trainingMode);
    const panel = document.getElementById("fuelingPlanPanel");
    if (panel) {
      panel.style.display = "block";
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (activeTargetPlan) {
      loadFuelingPlan({
        duration_min: activeTargetPlan.estimated_duration_min || 180,
        distance_miles: activeTargetPlan.distance_miles || 50,
        ride_title: activeTargetPlan.title,
        intensity_type: activeTargetPlan.intensity_type || "Endurance",
        is_outdoor: true
      });
    } else {
      loadFuelingPlan();
    }
  });
}

// ============================================================================
// REPLACE WITH CUSTOM RIDE & FUELING MODAL
// ============================================================================
const modalReplaceRide = document.getElementById("modalReplaceRide");
const btnOpenReplaceRideModal = document.getElementById("btnOpenReplaceRideModal");
const btnCloseReplaceRide = document.getElementById("btnCloseReplaceRide");
const btnCancelReplaceRide = document.getElementById("btnCancelReplaceRide");
const btnSubmitReplaceRide = document.getElementById("btnSubmitReplaceRide");
const sliderCustomTemp = document.getElementById("sliderCustomTemp");
const sliderCustomHumidity = document.getElementById("sliderCustomHumidity");
const lblCustomTemp = document.getElementById("lblCustomTemp");
const lblCustomHumidity = document.getElementById("lblCustomHumidity");

if (btnOpenReplaceRideModal) {
  btnOpenReplaceRideModal.addEventListener("click", () => {
    if (modalReplaceRide) {
      modalReplaceRide.classList.add("open");
      modalReplaceRide.classList.add("active");
      const whoopPill = document.getElementById("modalReplaceBadgeWhoop");
      const strainPill = document.getElementById("modalReplaceBadgeStrain");
      const tssPill = document.getElementById("modalReplaceBadgeTss");
      const recScore = (state.whoop && state.whoop.recovery_score) || (state.whoopMetrics && state.whoopMetrics.recovery_score) || 50;
      if (whoopPill) {
        whoopPill.textContent = `Whoop: ${recScore}%`;
        whoopPill.style.color = recScore >= 67 ? "#10b981" : (recScore < 40 ? "#f43f5e" : "#f59e0b");
      }
      if (strainPill) strainPill.textContent = `7D Strain: ${(state.trailingStrain || 11.4).toFixed(1)}`;
      if (tssPill) tssPill.textContent = `Yesterday: ${state.yesterdayTss || 0} TSS`;
    }
  });
}
if (btnCloseReplaceRide) btnCloseReplaceRide.addEventListener("click", () => {
  if (modalReplaceRide) {
    modalReplaceRide.classList.remove("open");
    modalReplaceRide.classList.remove("active");
  }
});
if (btnCancelReplaceRide) btnCancelReplaceRide.addEventListener("click", () => {
  if (modalReplaceRide) {
    modalReplaceRide.classList.remove("open");
    modalReplaceRide.classList.remove("active");
  }
});
if (modalReplaceRide) {
  modalReplaceRide.addEventListener("click", (e) => {
    if (e.target === modalReplaceRide) {
      modalReplaceRide.classList.remove("open");
      modalReplaceRide.classList.remove("active");
    }
  });
}

const inputCustomRideDescribe = document.getElementById("inputCustomRideDescribe");
if (inputCustomRideDescribe) {
  inputCustomRideDescribe.addEventListener("input", (e) => {
    const val = e.target.value;
    const distMatch = val.match(/(\d+(?:\.\d+)?)\s*(?:miles?|mi|km|k)\b/i);
    const distInp = document.getElementById("inputCustomRideDist");
    if (distMatch && distInp && (!distInp.value || distInp.value === "40")) {
      distInp.value = parseFloat(distMatch[1]);
    }
    const elevMatch = val.match(/(\d+(?:,\d+)?)\s*(?:ft|feet|m|meters)\b/i);
    const elevInp = document.getElementById("inputCustomRideElev");
    if (elevMatch && elevInp && (!elevInp.value || elevInp.value === "2200")) {
      elevInp.value = parseInt(elevMatch[1].replace(/,/g, ''), 10);
    }
  });
}

if (sliderCustomTemp) {
  sliderCustomTemp.addEventListener("input", (e) => {
    if (lblCustomTemp) lblCustomTemp.textContent = `${e.target.value}°F`;
  });
}
if (sliderCustomHumidity) {
  sliderCustomHumidity.addEventListener("input", (e) => {
    if (lblCustomHumidity) lblCustomHumidity.textContent = `${e.target.value}%`;
  });
}

// Submit Replace Ride
if (btnSubmitReplaceRide) {
  btnSubmitReplaceRide.addEventListener("click", async () => {
    const descInp = document.getElementById("inputCustomRideDescribe");
    const distInp = document.getElementById("inputCustomRideDist");
    const durInp = document.getElementById("inputCustomRideDur");
    const elevInp = document.getElementById("inputCustomRideElev");
    const gpxInp = document.getElementById("inputCustomRideGpx");

    const desc = descInp ? descInp.value.trim() : "";
    const dist = parseFloat(distInp ? distInp.value : 0) || 0;
    const dur = parseInt(durInp ? durInp.value : 0, 10) || 0;
    const elev = parseFloat(elevInp ? elevInp.value : 0) || 0;
    const tempF = sliderCustomTemp ? parseInt(sliderCustomTemp.value, 10) : 78;
    const humPct = sliderCustomHumidity ? parseInt(sliderCustomHumidity.value, 10) : 60;

    let payload = {
      description: desc,
      distance_miles: dist,
      duration_min: dur,
      elevation_gain_ft: elev,
      temp_f: tempF,
      humidity_pct: humPct,
      is_outdoor: true
    };

    btnSubmitReplaceRide.textContent = "⏳ Calculating...";

    // Handle GPX file if attached
    if (gpxInp && gpxInp.files && gpxInp.files[0]) {
      const file = gpxInp.files[0];
      const reader = new FileReader();
      reader.onload = async (evt) => {
        try {
          const gpxRes = await fetch("/api/plans/upload-gpx", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gpx_content: evt.target.result, filename: file.name })
          });
          const gpxData = await gpxRes.json();
          if (gpxData.success) {
            payload.distance_miles = gpxData.distance_miles;
            payload.elevation_gain_ft = gpxData.elevation_gain_ft;
            payload.duration_min = gpxData.estimated_duration_min;
            payload.title = gpxData.title;
            payload.svg_path = gpxData.svg_path;
            payload.route_source = "gpx_upload";
          }
          await executeReplaceRide(payload);
        } catch (e) {
          console.error(e);
          await executeReplaceRide(payload);
        }
      };
      reader.readAsText(file);
    } else {
      await executeReplaceRide(payload);
    }
  });
}

async function executeReplaceRide(payload) {
  try {
    const res = await fetch("/api/workouts/replace-custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    btnSubmitReplaceRide.textContent = "🥪 Replace Ride & Generate Fueling Plan";

    if (data.success && data.active_workout) {
      if (modalReplaceRide) {
        modalReplaceRide.classList.remove("open");
        modalReplaceRide.classList.remove("active");
      }
      state.currentWorkout = data.active_workout;
      state.activeOptionId = data.active_workout.id;
      state.currentDuration = data.active_workout.duration_minutes;

      if (!state.workoutOptions.some(o => o.id === data.active_workout.id)) {
        state.workoutOptions = [data.active_workout, ...state.workoutOptions];
      } else {
        const idx = state.workoutOptions.findIndex(o => o.id === data.active_workout.id);
        state.workoutOptions[idx] = data.active_workout;
      }

      renderWorkout(state.currentWorkout);
      renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
      renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
      if (data.fueling_plan) {
        currentFuelingPlan = data.fueling_plan;
        positionFuelingPanel("indoor");
        renderFuelingPlan(data.fueling_plan);
        const panel = document.getElementById("fuelingPlanPanel");
        if (panel) {
          panel.style.display = "block";
          updateFuelingButtonStates();
          panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
      showToast(`✨ Replaced ride: ${data.active_workout.title}! Fueling plan loaded.`);
    }
  } catch (err) {
    btnSubmitReplaceRide.textContent = "🥪 Replace Ride & Generate Fueling Plan";
    console.error(err);
  }
}

// ============================================================================
// INTERACTIVE AI COACH CHATBOT (GEMINI & SPORTS-SCIENCE TELEMETRY)
// ============================================================================
const btnOpenCoachChat = document.getElementById("btnOpenCoachChat");
const btnFloatingCoachChat = document.getElementById("btnFloatingCoachChat");
const coachChatDrawer = document.getElementById("coachChatDrawer");
const coachChatBackdrop = document.getElementById("coachChatBackdrop");
const btnCloseCoachChat = document.getElementById("btnCloseCoachChat");
const btnClearChatHistory = document.getElementById("btnClearChatHistory");
const btnCoachMemory = document.getElementById("btnCoachMemory");
const coachChatMessages = document.getElementById("coachChatMessages");
const formCoachChat = document.getElementById("formCoachChat");
const inputCoachMessage = document.getElementById("inputCoachMessage");
const btnSendCoachMessage = document.getElementById("btnSendCoachMessage");
const coachQuickPrompts = document.getElementById("coachQuickPrompts");

let coachChatHistory = [];
let coachChatHistoryLoaded = false;
let coachConversationMemory = null;
let isCoachChatLoading = false;

function updateGeminiConnectedIndicators(isConfigured, modelName) {
  const modelSuffix = modelName ? ` (${modelName})` : "";

  // 1. Drawer Header Badge
  const badgeCoach = document.getElementById("badgeCoachGeminiStatus");
  const txtCoach = document.getElementById("txtCoachGeminiStatus");
  if (badgeCoach && txtCoach) {
    if (isConfigured) {
      badgeCoach.className = "badge-status badge-gemini connected";
      badgeCoach.style.background = "rgba(16,185,129,0.15)";
      badgeCoach.style.borderColor = "rgba(16,185,129,0.35)";
      badgeCoach.style.color = "#10b981";
      txtCoach.textContent = "Connected";
      badgeCoach.title = `Google Gemini Active${modelSuffix}`;
      badgeCoach.style.display = "inline-flex";
    } else {
      badgeCoach.className = "badge-status badge-gemini disconnected";
      badgeCoach.style.background = "rgba(148,163,184,0.1)";
      badgeCoach.style.borderColor = "rgba(148,163,184,0.25)";
      badgeCoach.style.color = "#94a3b8";
      txtCoach.textContent = "Built-in Rules";
      badgeCoach.title = "Using built-in sports-science rules";
      badgeCoach.style.display = "inline-flex";
    }
  }

  // 2. Main Dashboard Coach Card Header Badge
  const badgeCard = document.getElementById("badgeCardGeminiStatus");
  const txtCard = document.getElementById("txtCardGeminiStatus");
  if (badgeCard && txtCard) {
    if (isConfigured) {
      badgeCard.className = "badge-status badge-gemini connected";
      badgeCard.style.background = "rgba(16,185,129,0.15)";
      badgeCard.style.borderColor = "rgba(16,185,129,0.35)";
      badgeCard.style.color = "#10b981";
      txtCard.textContent = "Connected";
      badgeCard.title = `Google Gemini Sports-Science AI Active${modelSuffix}`;
      badgeCard.style.display = "inline-flex";
    } else {
      badgeCard.className = "badge-status badge-gemini disconnected";
      badgeCard.style.background = "rgba(148,163,184,0.1)";
      badgeCard.style.borderColor = "rgba(148,163,184,0.25)";
      badgeCard.style.color = "#94a3b8";
      txtCard.textContent = "Built-in Rules";
      badgeCard.title = "Google Gemini AI Not Configured (Using built-in rules)";
      badgeCard.style.display = "inline-flex";
    }
  }

  // 3. Settings Modal Status Badge
  const geminiStat = document.getElementById("geminiConnStatus");
  const txtGeminiStat = document.getElementById("txtGeminiConnStatus");
  if (geminiStat && txtGeminiStat) {
    if (isConfigured) {
      geminiStat.className = "badge-status badge-gemini connected";
      geminiStat.style.background = "rgba(16,185,129,0.15)";
      geminiStat.style.borderColor = "rgba(16,185,129,0.35)";
      geminiStat.style.color = "#10b981";
      txtGeminiStat.textContent = `Connected${modelSuffix}`;
      geminiStat.style.display = "inline-flex";
    } else {
      geminiStat.className = "badge-status badge-gemini disconnected";
      geminiStat.style.background = "rgba(148,163,184,0.1)";
      geminiStat.style.borderColor = "rgba(148,163,184,0.25)";
      geminiStat.style.color = "#94a3b8";
      txtGeminiStat.textContent = "Not connected";
      geminiStat.style.display = "inline-flex";
    }
  }

  // 4. Version Footer Status Pill
  const footerDot = document.getElementById("footerDotGemini");
  const footerText = document.getElementById("footerTextGemini");
  if (footerDot && footerText) {
    if (isConfigured) {
      footerDot.className = "dot green";
      footerDot.style.background = "#10b981";
      footerDot.style.boxShadow = "0 0 6px #10b981";
      footerText.textContent = `Gemini Connected${modelSuffix}`;
    } else {
      footerDot.className = "dot";
      footerDot.style.background = "#94a3b8";
      footerDot.style.boxShadow = "none";
      footerText.textContent = "AI Engine (Offline)";
    }
  }

  // 5. Top Navbar Status Badge
  const geminiNavDot = document.getElementById("geminiNavDot");
  const geminiNavText = document.getElementById("geminiNavStatusText");
  if (geminiNavText) {
    if (isConfigured) {
      geminiNavText.textContent = "Connected";
      if (geminiNavDot) {
        geminiNavDot.className = "dot green";
        geminiNavDot.style.background = "#10b981";
        geminiNavDot.style.boxShadow = "0 0 8px #10b981";
      }
    } else {
      geminiNavText.textContent = "Not connected";
      if (geminiNavDot) {
        geminiNavDot.className = "dot gray";
        geminiNavDot.style.background = "#94a3b8";
        geminiNavDot.style.boxShadow = "none";
      }
    }
  }
}

async function checkCoachGeminiStatus() {
  try {
    const res = await fetch("/api/chat/status");
    if (res.ok) {
      const data = await res.json();
      updateGeminiConnectedIndicators(data.gemini_configured, data.gemini_model);

      if (data.recovery_score != null) {
        state.chatRecovery = Number(data.recovery_score);
        updateCoachChatTelemetryChips();
      }

      const subtitle = document.getElementById("coachChatSubtitle");
      if (subtitle) {
        if (data.gemini_configured) {
          subtitle.textContent = "Google Gemini • Live Telemetry";
          subtitle.title = `Model: ${data.gemini_model || "Gemini Flash"} • Real-time telemetry connected`;
          subtitle.style.color = "var(--accent-cyan)";
        } else {
          subtitle.textContent = "Sports-Science Telemetry • Built-in Rules";
          subtitle.title = "Add Google Gemini API key in Settings for AI coaching";
          subtitle.style.color = "var(--text-muted)";
        }
      }
    }
  } catch (e) {
    console.warn("Could not check coach status:", e);
  }
}

function adjustCoachInputHeight() {
  if (!inputCoachMessage) return;
  inputCoachMessage.style.height = "auto";
  const scrollH = inputCoachMessage.scrollHeight;
  const targetH = Math.min(Math.max(scrollH + 4, 44), 140);
  inputCoachMessage.style.height = targetH + "px";
  inputCoachMessage.style.overflowY = scrollH > 136 ? "auto" : "hidden";
}

function updateCoachMemoryIndicator(memory) {
  coachConversationMemory = memory || null;
  if (!btnCoachMemory) return;
  const hasSummary = Boolean(memory && memory.summary && memory.summary.trim());
  const hasFacts = Boolean(memory && Array.isArray(memory.key_facts) && memory.key_facts.length > 0);
  if (hasSummary || hasFacts) {
    btnCoachMemory.style.display = "flex";
    const factCount = hasFacts ? memory.key_facts.length : 0;
    btnCoachMemory.title = `Coach Long-Term Memory Active (${factCount} remembered notes) — Click to view or reset`;
  } else {
    btnCoachMemory.style.display = "none";
  }
}

async function loadCoachChatHistory(force = false) {
  if (coachChatHistoryLoaded && !force) return;
  try {
    const res = await fetch("/api/chat/history?limit=60");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.success) return;

    coachChatHistoryLoaded = true;
    updateCoachMemoryIndicator(data.memory);

    if (Array.isArray(data.messages) && data.messages.length > 0 && coachChatMessages) {
      // Preserve initial welcome message if present, then append persisted history
      const firstGreeting = coachChatMessages.querySelector(".chat-msg-coach");
      const greetingHtml = firstGreeting ? firstGreeting.outerHTML : "";
      coachChatMessages.innerHTML = greetingHtml;
      coachChatHistory = [];

      for (const msg of data.messages) {
        const uiRole = msg.role === "user" ? "user" : "coach";
        const msgText = msg.text || msg.content || "";
        appendCoachChatMessage(
          uiRole,
          msgText,
          msg.proposed_action || null,
          msg.executed_tools || null
        );
        coachChatHistory.push({
          role: msg.role === "user" ? "user" : "model",
          text: msgText
        });
      }
      scrollCoachChatToBottom();
    }
  } catch (e) {
    console.warn("Could not load persisted coach chat history:", e);
  }
}

function openCoachChat() {
  const drawer = document.getElementById("coachChatDrawer");
  const backdrop = document.getElementById("coachChatBackdrop");
  if (!drawer) {
    console.error("Coach chat drawer element not found");
    return;
  }
  drawer.classList.add("open");
  if (backdrop) backdrop.classList.add("open");

  updateCoachChatTelemetryChips();
  checkCoachGeminiStatus();
  loadCoachChatHistory();

  const inp = document.getElementById("inputCoachMessage");
  if (inp) {
    adjustCoachInputHeight();
    setTimeout(() => {
      try { inp.focus(); } catch (e) {}
    }, 250);
  }
  scrollCoachChatToBottom();
}

function closeCoachChat() {
  const drawer = document.getElementById("coachChatDrawer");
  const backdrop = document.getElementById("coachChatBackdrop");
  if (drawer) drawer.classList.remove("open");
  if (backdrop) backdrop.classList.remove("open");
  if (document.activeElement && drawer && drawer.contains(document.activeElement)) {
    try { document.activeElement.blur(); } catch (e) {}
  }
  if (typeof loadDebrief === "function") {
    loadDebrief();
  }
}

window.openCoachChat = openCoachChat;
window.closeCoachChat = closeCoachChat;

function updateCoachChatTelemetryChips() {
  try {
    const chipRec = document.getElementById("chatChipRecovery");
    const chipFtp = document.getElementById("chatChipFtp");
    const chipWPrime = document.getElementById("chatChipWPrime");
    const chipStrain = document.getElementById("chatChipStrain");
    const chipWorkout = document.getElementById("chatChipWorkout");

    const whoopData = state.whoop || (state.dashboard && state.dashboard.whoop) || state.whoopMetrics;
    const rec = (whoopData && whoopData.recovery_score != null)
      ? Math.round(Number(whoopData.recovery_score))
      : (state.chatRecovery != null ? Math.round(Number(state.chatRecovery)) : 72);

    const ftp = state.ftp || (state.dashboard && state.dashboard.athlete && state.dashboard.athlete.ftp) || 250;
    const wPrime = state.athleteWPrime !== undefined
      ? state.athleteWPrime
      : ((state.dashboard && state.dashboard.athlete && state.dashboard.athlete.w_prime_kj) ?? 20.0);

    const rawStrain = (whoopData && whoopData.trailing_7d_strain_avg != null)
      ? Number(whoopData.trailing_7d_strain_avg)
      : ((whoopData && whoopData.day_strain != null)
          ? Number(whoopData.day_strain)
          : (state.trailingStrain != null ? Number(state.trailingStrain) : 10.6));
    const strain = isNaN(rawStrain) ? "10.6" : rawStrain.toFixed(1);

    const workoutTitle = (state.currentWorkout && state.currentWorkout.title)
      || (state.todayPrescribed && state.todayPrescribed.title)
      || (state.dashboard && state.dashboard.today_prescribed && state.dashboard.today_prescribed.title)
      || "Sweet Spot Aerobic";

    if (chipRec) {
      chipRec.textContent = `🧬 Whoop: ${rec}%`;
      if (rec > 66) {
        chipRec.style.background = "rgba(16, 185, 129, 0.15)";
        chipRec.style.borderColor = "rgba(16, 185, 129, 0.4)";
        chipRec.style.color = "#10b981";
      } else if (rec >= 34) {
        chipRec.style.background = "rgba(245, 158, 11, 0.15)";
        chipRec.style.borderColor = "rgba(245, 158, 11, 0.4)";
        chipRec.style.color = "#f59e0b";
      } else {
        chipRec.style.background = "rgba(244, 63, 94, 0.15)";
        chipRec.style.borderColor = "rgba(244, 63, 94, 0.4)";
        chipRec.style.color = "#f43f5e";
      }
    }
    if (chipFtp) chipFtp.textContent = `⚡ FTP: ${ftp}W`;
    if (chipWPrime) chipWPrime.textContent = `🔋 W': ${wPrime}kJ`;
    if (chipStrain) chipStrain.textContent = `🔥 7D Strain: ${strain}`;
    if (chipWorkout) chipWorkout.textContent = `🎯 Today: ${workoutTitle}`;
  } catch (err) {
    console.warn("Could not update coach telemetry chips:", err);
  }
}

function scrollCoachChatToBottom() {
  if (coachChatMessages) {
    coachChatMessages.scrollTop = coachChatMessages.scrollHeight;
    requestAnimationFrame(() => {
      if (coachChatMessages) {
        coachChatMessages.scrollTop = coachChatMessages.scrollHeight;
      }
    });
    setTimeout(() => {
      if (coachChatMessages) {
        coachChatMessages.scrollTop = coachChatMessages.scrollHeight;
      }
    }, 60);
  }
}

function formatCoachMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h3>$1</h3>')
    .replace(/^# (.*$)/gim, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/^- (.*$)/gim, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gims, '<ul>$1</ul>')
    .replace(/\n\n+/g, '</p><p>');

  html = `<p>${html}</p>`;
  html = html.replace(/<p><(h3|blockquote|ul)>/g, '<$1>');
  html = html.replace(/<\/(h3|blockquote|ul)><\/p>/g, '</$1>');
  return html;
}

function appendCoachChatMessage(role, text, actionData = null, executedTools = null) {
  if (!coachChatMessages) return;
  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg chat-msg-${role === "user" ? "user" : "coach"}`;

  const avatar = document.createElement("div");
  avatar.className = "chat-msg-avatar";
  avatar.textContent = role === "user" ? "🚴" : "🧠";

  const content = document.createElement("div");
  content.className = "chat-msg-content";

  if (role === "user") {
    content.textContent = text;
  } else {
    let toolsHtml = "";
    if (executedTools && Array.isArray(executedTools) && executedTools.length > 0) {
      toolsHtml = `
        <div class="chat-tools-container" style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.75rem;">
          ${executedTools.map(t => {
            const summary = t.summary || 'Inspected Strava telemetry';
            return `
              <div class="chat-tool-pill" title="Gemini Function Call: ${t.name || 'tool'}">
                <span class="chat-tool-icon">⚡</span>
                <span class="chat-tool-label">${summary}</span>
              </div>
            `;
          }).join("")}
        </div>
      `;
    }
    content.innerHTML = toolsHtml + formatCoachMarkdown(text);
  }

  // Render Action Proposal Card if present
  if (actionData && role === "coach") {
    const isToday = actionData.action_type === "apply_today_workout";
    const isScheduleWorkout = actionData.action_type === "schedule_workout";
    const isClear = actionData.action_type === "clear_upcoming_plan";
    const isUpcomingPlan = actionData.action_type === "schedule_upcoming_plan";
    const actionCard = document.createElement("div");
    actionCard.className = "chat-workout-action-card";

    let badgeLabel = "";
    let btnLabel = "";
    if (isToday) {
      badgeLabel = "⚡ Proposed For Today";
      btnLabel = "⚡ Apply as Today's Workout";
    } else if (isScheduleWorkout) {
      const d = actionData.target_date || "Tomorrow";
      badgeLabel = `📅 Scheduled for ${d}`;
      btnLabel = "🚀 Sync to Zwift Calendar";
    } else if (isClear) {
      badgeLabel = "🗑️ Plan Cleared";
      btnLabel = actionData.already_applied ? "✓ Plan Cleared! 🗑️" : "🗑️ Confirm Clear Plan";
    } else {
      badgeLabel = `🏆 Target Event (${actionData.target_date || 'Upcoming'})`;
      btnLabel = "🏆 Set as Target Event & Activate Taper";
    }

    const isIndoor = actionData.is_indoor || !actionData.distance_miles || actionData.distance_miles === 0;
    const durStr = actionData.duration_minutes ? `${actionData.duration_minutes}m` : (actionData.distance_miles ? `${actionData.distance_miles} mi` : "");
    const tssStr = actionData.estimated_tss ? `~${actionData.estimated_tss} TSS` : "";
    const distStr = (!isIndoor && actionData.distance_miles && actionData.distance_miles > 0) ? `${actionData.distance_miles} mi` : "";
    const elevStr = (!isIndoor && actionData.elevation_gain_ft && actionData.elevation_gain_ft > 0) ? `${actionData.elevation_gain_ft} ft` : "";
    const focusStr = actionData.focus_area || actionData.intensity_type || (isClear ? "Clear Plan" : "Custom");

    actionCard.innerHTML = `
      <div class="chat-action-header">
        <span class="chat-action-badge">${badgeLabel}</span>
        <span class="chat-action-focus">${focusStr}</span>
      </div>
      <div class="chat-action-title">${actionData.title || (isClear ? 'Cancel Upcoming Plan' : 'Custom Session')}</div>
      <div class="chat-action-meta">
        ${durStr ? `<span>⏱️ ${durStr}</span>` : ''}
        ${distStr ? `<span>📍 ${distStr}</span>` : ''}
        ${elevStr ? `<span>⛰️ ${elevStr}</span>` : ''}
        ${tssStr ? `<span>⚡ ${tssStr}</span>` : ''}
        <span>🎯 ${focusStr}</span>
      </div>
      <button class="btn btn-primary btn-chat-apply-action" type="button">
        ${btnLabel}
      </button>
    `;

    const applyBtn = actionCard.querySelector(".btn-chat-apply-action");
    if (actionData.already_applied && isClear) {
      applyBtn.classList.remove("btn-primary");
      applyBtn.classList.add("btn-applied");
      applyBtn.disabled = true;
    }

    applyBtn.addEventListener("click", async () => {
      applyBtn.disabled = true;
      applyBtn.textContent = "⏳ Applying...";
      try {
        const res = await fetch("/api/chat/apply-action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_type: actionData.action_type,
            action_data: actionData
          })
        });
        const resData = await res.json();
        if (resData.success) {
          if (isToday) {
            applyBtn.textContent = "✓ Active on Today's Dashboard! 🚀";
          } else if (isScheduleWorkout) {
            applyBtn.textContent = "✓ Scheduled & Synced to Zwift! 🚀";
          } else if (isClear) {
            applyBtn.textContent = "✓ Plan Cleared! 🗑️";
          } else {
            applyBtn.textContent = "✓ Scheduled in Training Plan! 📅";
          }
          applyBtn.classList.remove("btn-primary");
          applyBtn.classList.add("btn-applied");
          showToast(resData.message || `Activated ${actionData.title || 'Plan'}`);

          state.activeCoachView = "prescribed";
          const todayIso = new Date().toISOString().slice(0, 10);
          const isForToday = isToday || (isScheduleWorkout && (resData.is_for_today || resData.target_date === todayIso || actionData.target_date === todayIso));

          if (isClear) {
            if (resData.active_workout || resData.workout) {
              const activeW = resData.active_workout || resData.workout;
              state.currentWorkout = activeW;
              state.activeOptionId = activeW.id;
              state.currentDuration = activeW.duration_minutes;
              if (resData.options) state.workoutOptions = resData.options;
              syncDurationPills(state.currentDuration);
              renderWorkout(state.currentWorkout);
              renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
              renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
            }
            if (resData.program) {
              state.program = resData.program;
              if (typeof renderProgram === "function") {
                renderProgram(state.program);
              }
            }
            if (typeof loadUpcomingPlan === "function") {
              await loadUpcomingPlan();
            }
            if (typeof loadDebrief === "function") {
              await loadDebrief();
            }
            if (typeof loadDashboard === "function") {
              await loadDashboard();
            }
            if (typeof loadWorkout === "function") {
              await loadWorkout();
            }
          } else if (isForToday && (resData.active_workout || resData.workout)) {
            const activeW = resData.active_workout || resData.workout;
            if (resData.synced_to_zwift) {
              activeW.pushed_to_zwift = true;
              activeW.synced_to_zwift = true;
              activeW.badge = "🚀 Sent to Zwift";
            }
            if (typeof setWorkoutStageCollapsed === "function") {
              setWorkoutStageCollapsed(false);
            }
            state.currentWorkout = activeW;
            state.activeOptionId = activeW.id;
            state.currentDuration = activeW.duration_minutes;
            if (resData.options) state.workoutOptions = resData.options;
            syncDurationPills(state.currentDuration);
            renderWorkout(state.currentWorkout);
            renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
            renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
            if (resData.fueling_plan) {
              currentFuelingPlan = resData.fueling_plan;
              const fuelingPanel = document.getElementById("fuelingPlanPanel");
              if (fuelingPanel && fuelingPanel.style.display !== "none") {
                renderFuelingPlan(resData.fueling_plan);
              }
            }
          } else if (isScheduleWorkout) {
            // Scheduled for tomorrow / Zwift calendar — refresh 3-day forecast immediately!
            state.scheduledZwiftWorkout = resData.workout;
            if (typeof loadDebrief === "function") {
              await loadDebrief();
            }
            renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
          } else {
            if (typeof loadUpcomingPlan === "function") {
              await loadUpcomingPlan();
            }
            if (typeof loadDebrief === "function") {
              await loadDebrief();
            }
          }
        } else {
          applyBtn.disabled = false;
          applyBtn.textContent = "⚠️ Failed to Apply — Tap to Retry";
        }
      } catch (err) {
        console.error("Failed to apply chat action:", err);
        applyBtn.disabled = false;
        applyBtn.textContent = "⚠️ Error — Tap to Retry";
      }
    });

    content.appendChild(actionCard);
  }

  msgDiv.appendChild(avatar);
  msgDiv.appendChild(content);
  coachChatMessages.appendChild(msgDiv);
  scrollCoachChatToBottom();
}

function showCoachTypingIndicator() {
  if (!coachChatMessages) return null;
  const typingDiv = document.createElement("div");
  typingDiv.className = "chat-msg chat-msg-coach chat-msg-typing";
  typingDiv.id = "coachTypingIndicator";

  const avatar = document.createElement("div");
  avatar.className = "chat-msg-avatar";
  avatar.textContent = "🧠";

  const content = document.createElement("div");
  content.className = "chat-msg-content";
  content.innerHTML = `
    <div class="chat-typing-wrapper" style="display:inline-flex;align-items:center;gap:0.6rem;white-space:nowrap;">
      <div class="chat-typing-dots" style="display:inline-flex;align-items:center;gap:4px;">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
      <span class="chat-typing-label" style="display:inline-block;white-space:nowrap;font-size:0.78rem;font-weight:500;">Analyzing telemetry...</span>
    </div>
  `;

  typingDiv.appendChild(avatar);
  typingDiv.appendChild(content);
  coachChatMessages.appendChild(typingDiv);
  scrollCoachChatToBottom();
  return typingDiv;
}

function removeCoachTypingIndicator() {
  const indicator = document.getElementById("coachTypingIndicator");
  if (indicator) indicator.remove();
}

async function sendCoachMessage(text) {
  if (!text || !text.trim() || isCoachChatLoading) return;
  const cleanMsg = text.trim();
  isCoachChatLoading = true;

  appendCoachChatMessage("user", cleanMsg);
  coachChatHistory.push({ role: "user", text: cleanMsg });

  if (inputCoachMessage) {
    inputCoachMessage.value = "";
    adjustCoachInputHeight();
  }
  if (btnSendCoachMessage) btnSendCoachMessage.disabled = true;

  showCoachTypingIndicator();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: cleanMsg,
        history: coachChatHistory.slice(-10)
      })
    });

    const data = await res.json();
    removeCoachTypingIndicator();

    if (data.success && data.reply) {
      appendCoachChatMessage("coach", data.reply, data.proposed_action, data.executed_tools);
      coachChatHistory.push({ role: "model", text: data.reply });

      if (data.cleared_plan || (data.proposed_action && data.proposed_action.action_type === "clear_upcoming_plan")) {
        if (data.active_workout || data.workout) {
          const activeW = data.active_workout || data.workout;
          state.currentWorkout = activeW;
          state.activeOptionId = activeW.id;
          state.currentDuration = activeW.duration_minutes;
          if (data.options) state.workoutOptions = data.options;
          syncDurationPills(state.currentDuration);
          renderWorkout(state.currentWorkout);
          renderWorkoutOptions(state.workoutOptions, state.activeOptionId);
          renderAiCoachTodayCard(state.dailyDebrief, state.currentWorkout);
        }
        if (data.program) {
          state.program = data.program;
          if (typeof renderProgram === "function") {
            renderProgram(state.program);
          }
        }
        const cardUpcoming = document.getElementById("cardUpcomingPlan");
        if (cardUpcoming) cardUpcoming.style.display = "none";

        if (typeof loadUpcomingPlan === "function") await loadUpcomingPlan();
        if (typeof loadDebrief === "function") await loadDebrief();
        if (typeof loadDashboard === "function") await loadDashboard();
        if (typeof loadWorkout === "function") await loadWorkout();
      } else if (data.scheduled_plans || data.proposed_action) {
        if (typeof loadDebrief === "function") {
          loadDebrief();
        }
      }

      if (Array.isArray(data.executed_tools) && data.executed_tools.some(t => t.name === "customize_and_save_workout" || t.name === "send_workout_to_zwift")) {
        if (typeof loadWorkoutArchive === "function") loadWorkoutArchive();
        if (typeof loadWorkout === "function") loadWorkout();
        if (typeof loadDebrief === "function") loadDebrief();
      }

      const subtitle = document.getElementById("coachChatSubtitle");
      if (subtitle) {
        if (data.provider === "gemini") {
          subtitle.textContent = "Google Gemini • Strava & Whoop Tools";
          subtitle.title = `Model: ${data.model || "Gemini 3 Flash"} • Live Strava & Whoop function calling enabled`;
          subtitle.style.color = "var(--accent-cyan)";
        } else {
          subtitle.textContent = "Sports-Science Telemetry • Built-in Rules";
          subtitle.title = "Built-in sports science rules active";
          subtitle.style.color = "var(--text-muted)";
        }
      }
    } else {
      appendCoachChatMessage("coach", "⚠️ I encountered an issue analyzing your telemetry. Please try again.");
    }
  } catch (err) {
    removeCoachTypingIndicator();
    console.error("Coach chat error:", err);
    appendCoachChatMessage("coach", "⚠️ Connection error contacting coach engine. Please verify the PowerSync server is running.");
  } finally {
    isCoachChatLoading = false;
    if (btnSendCoachMessage) btnSendCoachMessage.disabled = false;
    if (inputCoachMessage) inputCoachMessage.focus();
  }
}

const btnCoachCardChat = document.getElementById("btnCoachCardChat");

if (btnOpenCoachChat) {
  btnOpenCoachChat.addEventListener("click", openCoachChat);
}
if (btnFloatingCoachChat) {
  btnFloatingCoachChat.addEventListener("click", openCoachChat);
}
if (btnCoachCardChat) {
  btnCoachCardChat.addEventListener("click", openCoachChat);
}

if (btnCloseCoachChat) {
  btnCloseCoachChat.addEventListener("click", (e) => {
    e.preventDefault();
    closeCoachChat();
  });
  btnCloseCoachChat.addEventListener("touchend", (e) => {
    e.preventDefault();
    closeCoachChat();
  }, { passive: false });
}

if (coachChatBackdrop) {
  coachChatBackdrop.addEventListener("click", (e) => {
    e.preventDefault();
    closeCoachChat();
  });
  coachChatBackdrop.addEventListener("touchend", (e) => {
    e.preventDefault();
    closeCoachChat();
  }, { passive: false });
}

// Global fallback delegator for any chat button (open or close)
document.addEventListener("click", (e) => {
  if (e.target.closest("#btnCloseCoachChat, [data-close-coach-chat]")) {
    e.preventDefault();
    closeCoachChat();
    return;
  }
  const trigger = e.target.closest("#btnOpenCoachChat, #btnFloatingCoachChat, #btnCoachCardChat, [data-open-coach-chat]");
  if (trigger) {
    e.preventDefault();
    openCoachChat();
  }
});

document.addEventListener("touchend", (e) => {
  if (e.target.closest("#btnCloseCoachChat, [data-close-coach-chat]")) {
    e.preventDefault();
    closeCoachChat();
  }
}, { passive: false });

if (btnClearChatHistory) {
  btnClearChatHistory.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/chat/history", { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        updateCoachMemoryIndicator(data.memory);
      }
    } catch (e) {
      console.warn("Could not clear persisted chat history:", e);
    }
    coachChatHistory = [];
    coachChatHistoryLoaded = true;
    if (coachChatMessages) {
      coachChatMessages.innerHTML = `
        <div class="chat-msg chat-msg-coach">
          <div class="chat-msg-avatar">🧠</div>
          <div class="chat-msg-content">
            <p><strong>Chat history reset.</strong></p>
            <p>I'm ready with your fresh live Whoop &amp; Strava metrics. Ask me anything, or tell me about an upcoming ride/event to adapt your training schedule!</p>
          </div>
        </div>
      `;
    }
    showToast("🧹 Chat history cleared (long-term coaching memory preserved).");
  });
}

if (btnCoachMemory) {
  btnCoachMemory.addEventListener("click", async () => {
    const mem = coachConversationMemory;
    if (!mem) return;
    const summaryText = mem.summary ? `Summary: ${mem.summary}\n\n` : "";
    const factsText = (mem.key_facts && mem.key_facts.length > 0)
      ? `Remembered Notes:\n• ${mem.key_facts.join("\n• ")}\n\n`
      : "";
    const shouldClear = window.confirm(
      `PowerSync Coach Long-Term Memory:\n\n${summaryText}${factsText}Press OK to reset this long-term memory, or Cancel to keep it.`
    );
    if (shouldClear) {
      try {
        const res = await fetch("/api/chat/memory", { method: "DELETE" });
        if (res.ok) {
          updateCoachMemoryIndicator(null);
          showToast("🧠 Long-term coach memory reset.");
        }
      } catch (e) {
        console.warn("Could not reset coach memory:", e);
      }
    }
  });
}

if (formCoachChat) {
  formCoachChat.addEventListener("submit", (e) => {
    e.preventDefault();
    if (inputCoachMessage) {
      sendCoachMessage(inputCoachMessage.value);
    }
  });
}

if (inputCoachMessage) {
  inputCoachMessage.addEventListener("input", adjustCoachInputHeight);
  inputCoachMessage.addEventListener("focus", adjustCoachInputHeight);

  inputCoachMessage.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendCoachMessage(inputCoachMessage.value);
    }
  });
}

if (coachQuickPrompts) {
  coachQuickPrompts.querySelectorAll(".quick-prompt-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const prompt = pill.dataset.prompt;
      if (prompt) {
        sendCoachMessage(prompt);
      }
    });
  });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && coachChatDrawer && coachChatDrawer.classList.contains("open")) {
    closeCoachChat();
  }
});

// ============================================================================
// Pull Down to Reload Feature (PWA / Mobile Standalone Mode)
// ============================================================================
function initPullToReload() {
  const indicator = document.getElementById("pullToReloadIndicator");
  const label = document.getElementById("pullToReloadLabel");
  if (!indicator || !label) return;
  const arrowIcon = indicator.querySelector(".pull-arrow-icon");

  let startY = 0;
  let startX = 0;
  let currentY = 0;
  let isTracking = false;
  let isPulling = false;
  let isRefreshing = false;
  let hasVibrated = false;

  const PULL_THRESHOLD = 60; // px downward pull to trigger reload
  const MAX_PULL = 85;      // maximum visual movement

  function isModalOrDrawerOpen() {
    const activeModal = document.querySelector(".modal-overlay.open, .modal-overlay.active");
    const chatDrawer = document.getElementById("coachChatDrawer") || document.getElementById("chatSlider");
    return Boolean(activeModal || (chatDrawer && chatDrawer.classList.contains("open")));
  }

  function hasScrolledAncestor(el) {
    let node = el && el.nodeType === 1 ? el : (el ? el.parentElement : null);
    while (node && node !== document.body && node !== document.documentElement) {
      if (node.scrollTop > 0) return true;
      const style = window.getComputedStyle(node);
      const overflowY = style ? style.overflowY : "";
      if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight + 4) {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function getScrollTop() {
    return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
  }

  function handleStart(y, x, target) {
    if (isRefreshing) return false;
    // Allow anywhere on screen as long as page is at the top
    if (getScrollTop() > 5) return false;
    if (isModalOrDrawerOpen()) return false;
    if (target && target.closest && target.closest("input, textarea, select, #coachChatDrawer, .modal-dialog, #outdoorLeafletMap, .leaflet-container")) return false;
    if (hasScrolledAncestor(target)) return false;

    startY = y;
    startX = x;
    currentY = startY;
    isTracking = true;
    isPulling = false;
    hasVibrated = false;
    return true;
  }

  function handleMove(y, x, cancelable, preventDefaultFn) {
    if (!isTracking || isRefreshing) return;
    currentY = y;
    const diffY = currentY - startY;
    const diffX = x - startX;

    // Scrolling up or sideways
    if (diffY <= 0) {
      if (isPulling) resetIndicator(false);
      return;
    }

    // Ignore horizontal swipes (e.g. tabs or sliders)
    if (Math.abs(diffX) > Math.abs(diffY) && !isPulling) {
      isTracking = false;
      return;
    }

    // Ensure we haven't scrolled down
    if (getScrollTop() > 5) {
      if (isPulling) resetIndicator(false);
      return;
    }

    // Threshold to engage pull behavior (6px deadzone)
    if (diffY < 6) return;

    isPulling = true;
    if (cancelable && preventDefaultFn) {
      preventDefaultFn();
    }

    // Smooth physics curve
    const pullDist = Math.min(MAX_PULL, Math.pow(diffY - 6, 0.88) * 1.3);

    indicator.classList.add("touching");
    const translateY = Math.min(60, pullDist);
    const opacity = Math.min(1, Math.max(0.1, pullDist / 18));
    indicator.style.transform = `translate(-50%, ${translateY}px) scale(1)`;
    indicator.style.opacity = opacity.toString();

    const progress = Math.min(1, pullDist / PULL_THRESHOLD);
    if (arrowIcon) {
      arrowIcon.style.transform = `rotate(${progress * 180}deg)`;
    }

    if (pullDist >= PULL_THRESHOLD) {
      indicator.classList.add("ready");
      label.textContent = "Release to reload";
      if (!hasVibrated) {
        hasVibrated = true;
        if (navigator.vibrate) {
          try { navigator.vibrate(12); } catch (_) {}
        }
      }
    } else {
      indicator.classList.remove("ready");
      label.textContent = "Pull to reload";
      hasVibrated = false;
    }
  }

  function handleEnd() {
    if (!isTracking) return;
    isTracking = false;

    if (!isPulling) return;
    isPulling = false;

    const diffY = Math.max(0, currentY - startY);
    const pullDist = Math.min(MAX_PULL, Math.pow(Math.max(0, diffY - 6), 0.88) * 1.3);

    indicator.classList.remove("touching");

    if (pullDist >= PULL_THRESHOLD) {
      // Trigger Reload!
      isRefreshing = true;
      indicator.classList.remove("ready");
      indicator.classList.add("refreshing");
      label.textContent = "Reloading PowerSync...";
      indicator.style.transform = "translate(-50%, 50px) scale(1)";
      indicator.style.opacity = "1";

      if (navigator.vibrate) {
        try { navigator.vibrate([15, 30, 15]); } catch (_) {}
      }

      setTimeout(() => {
        try {
          const url = new URL(window.location.href);
          url.searchParams.set("reload", Date.now().toString());
          window.location.replace(url.toString());
        } catch (_) {
          window.location.reload();
        }
      }, 350);
    } else {
      resetIndicator(true);
    }
  }

  function resetIndicator(animate) {
    if (isRefreshing) return;
    indicator.classList.remove("touching", "ready");
    indicator.style.transform = "translate(-50%, -35px) scale(0.85)";
    indicator.style.opacity = "0";
    label.textContent = "Pull to reload";
    if (arrowIcon) arrowIcon.style.transform = "rotate(0deg)";
    hasVibrated = false;
  }

  // Touch Events (iOS & Android)
  document.addEventListener("touchstart", (e) => {
    if (e.touches.length === 1) {
      handleStart(e.touches[0].clientY, e.touches[0].clientX, e.target);
    }
  }, { passive: false });

  document.addEventListener("touchmove", (e) => {
    if (e.touches.length === 1) {
      handleMove(
        e.touches[0].clientY,
        e.touches[0].clientX,
        e.cancelable,
        () => {
          if (e.cancelable) e.preventDefault();
        }
      );
    }
  }, { passive: false });

  document.addEventListener("touchend", () => {
    handleEnd();
  }, { passive: true });

  document.addEventListener("touchcancel", () => {
    isTracking = false;
    isPulling = false;
    resetIndicator(true);
  }, { passive: true });

  // Mouse Drag Support (Desktop testing)
  let isMouseDown = false;
  document.addEventListener("mousedown", (e) => {
    if (handleStart(e.clientY, e.clientX, e.target)) {
      isMouseDown = true;
    }
  });

  document.addEventListener("mousemove", (e) => {
    if (!isMouseDown) return;
    handleMove(e.clientY, e.clientX, true, () => {
      if (e.cancelable) e.preventDefault();
    });
  });

  document.addEventListener("mouseup", () => {
    if (isMouseDown) {
      isMouseDown = false;
      handleEnd();
    }
  });
}

// ========================================================
// Collapsible Adaptive Prescription Tile
// ========================================================
const workoutStageSection = document.getElementById("workoutStageSection");
const workoutStageHeader = document.getElementById("workoutStageHeader");
const btnToggleWorkoutStage = document.getElementById("btnToggleWorkoutStage");
const workoutStageToggleIcon = document.getElementById("workoutStageToggleIcon");
const workoutStageToggleText = document.getElementById("workoutStageToggleText");

function isWorkoutStageCollapsed() {
  const stage = workoutStageSection || document.getElementById("workoutStageSection");
  return stage ? stage.classList.contains("collapsed") : false;
}

function setWorkoutStageCollapsed(collapsed, triggerRedraw = true, updateMaster = true) {
  const stage = workoutStageSection || document.getElementById("workoutStageSection");
  if (!stage) return;

  const toggleIcon = workoutStageToggleIcon || document.getElementById("workoutStageToggleIcon");
  const toggleText = workoutStageToggleText || document.getElementById("workoutStageToggleText");
  const header = workoutStageHeader || document.getElementById("workoutStageHeader");

  if (collapsed) {
    stage.classList.add("collapsed");
    if (toggleIcon) toggleIcon.textContent = "▼";
    if (toggleText) toggleText.textContent = "Expand";
    if (header) header.setAttribute("aria-expanded", "false");
    document.querySelectorAll(".btn-collapse-inline").forEach(btn => {
      btn.textContent = "▼ Expand Tile";
    });
    try {
      localStorage.setItem("adaptivePrescriptionCollapsed", "true");
    } catch (_) {}
  } else {
    stage.classList.remove("collapsed");
    if (toggleIcon) toggleIcon.textContent = "▲";
    if (toggleText) toggleText.textContent = "Collapse";
    if (header) header.setAttribute("aria-expanded", "true");
    document.querySelectorAll(".btn-collapse-inline").forEach(btn => {
      btn.textContent = "▲ Collapse Tile";
    });
    try {
      localStorage.setItem("adaptivePrescriptionCollapsed", "false");
    } catch (_) {}

    if (triggerRedraw) {
      requestAnimationFrame(() => {
        if (state.currentWorkout && typeof drawWorkoutGraph === "function") {
          drawWorkoutGraph(state.currentWorkout);
        }
        if (typeof outdoorMap !== "undefined" && outdoorMap && typeof outdoorMap.invalidateSize === "function") {
          outdoorMap.invalidateSize(true);
        }
      });
    }
  }

  if (updateMaster) {
    syncMasterToggleState();
  }
}

function toggleWorkoutStage() {
  setWorkoutStageCollapsed(!isWorkoutStageCollapsed());
}

function initWorkoutStageCollapsible() {
  const toggleBtn = btnToggleWorkoutStage || document.getElementById("btnToggleWorkoutStage");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleWorkoutStage();
    });
  }

  const header = workoutStageHeader || document.getElementById("workoutStageHeader");
  if (header) {
    header.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      toggleWorkoutStage();
    });

    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleWorkoutStage();
      }
    });
  }

  document.addEventListener("click", (e) => {
    const inlineBtn = e.target.closest(".btn-collapse-inline");
    if (inlineBtn) {
      e.preventDefault();
      toggleWorkoutStage();
    }
  });

  // Restore saved collapse preference
  try {
    const saved = localStorage.getItem("adaptivePrescriptionCollapsed");
    if (saved === "true") {
      setWorkoutStageCollapsed(true, false, false);
    }
  } catch (_) {}
}

// ========================================================
// Generic Collapsible Tile Controller & Master Tile Manager
// ========================================================
function setupCollapsibleTile({
  cardId,
  headerId,
  toggleBtnId,
  toggleIconId,
  toggleTextId,
  storageKey,
  onExpand = null
}) {
  const card = document.getElementById(cardId);
  const header = document.getElementById(headerId);
  const toggleBtn = document.getElementById(toggleBtnId);
  const toggleIcon = document.getElementById(toggleIconId);
  const toggleText = document.getElementById(toggleTextId);

  if (!card) return null;

  function isCollapsed() {
    return card.classList.contains("collapsed");
  }

  function setCollapsed(collapsed, triggerExpandCallback = true, updateMaster = true) {
    if (collapsed) {
      card.classList.add("collapsed");
      if (toggleIcon) toggleIcon.textContent = "▼";
      if (toggleText) toggleText.textContent = "Expand";
      if (header) header.setAttribute("aria-expanded", "false");
      try {
        localStorage.setItem(storageKey, "true");
      } catch (_) {}
    } else {
      card.classList.remove("collapsed");
      if (toggleIcon) toggleIcon.textContent = "▲";
      if (toggleText) toggleText.textContent = "Collapse";
      if (header) header.setAttribute("aria-expanded", "true");
      try {
        localStorage.setItem(storageKey, "false");
      } catch (_) {}
      if (triggerExpandCallback && typeof onExpand === "function") {
        requestAnimationFrame(() => {
          onExpand();
        });
      }
    }

    if (updateMaster) {
      syncMasterToggleState();
    }
  }

  function toggle() {
    setCollapsed(!isCollapsed());
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle();
    });
  }

  if (header) {
    header.addEventListener("click", (e) => {
      if (e.target.closest("button, a, input, select, textarea, .mode-tab, .mode-tabs")) return;
      toggle();
    });

    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        if (e.target.closest("button, a, input, select, textarea, .mode-tab, .mode-tabs")) return;
        e.preventDefault();
        toggle();
      }
    });
  }

  // Restore saved collapse preference
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === "true") {
      setCollapsed(true, false, false);
    }
  } catch (_) {}

  return {
    isCollapsed,
    setCollapsed,
    toggle,
    expand: () => setCollapsed(false),
    collapse: () => setCollapsed(true)
  };
}

// --- Power Spiderweb Tracker & Progress Over Time (Strava & Xert Model) ---

function escapeSpiderwebHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

let currentSpiderwebTimeframe = "30d";
let currentSpiderwebData = null;

async function loadPowerSpiderweb(timeframe = "30d") {
  currentSpiderwebTimeframe = timeframe;
  try {
    const res = await fetch(`/api/power/spiderweb?timeframe=${encodeURIComponent(timeframe)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentSpiderwebData = data;
    renderPowerSpiderweb(data);
  } catch (err) {
    console.warn("Failed to load power spiderweb data:", err);
  }
}

function setupPowerSpiderwebTabs() {
  const group = document.getElementById("spiderwebTimeframeGroup");
  if (!group) return;
  const tabs = group.querySelectorAll(".mode-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", (e) => {
      e.stopPropagation();
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const tf = tab.getAttribute("data-timeframe") || "30d";
      loadPowerSpiderweb(tf);
    });
  });

  setupSpiderwebPlannerNav();
}

function renderPowerSpiderweb(data) {
  if (!data || !data.axes) return;
  currentSpiderwebData = data;

  // Legend labels
  const curLbl = document.getElementById("spiderwebLegendCurrentLabel");
  const prevLbl = document.getElementById("spiderwebLegendPreviousLabel");
  if (curLbl) curLbl.textContent = `${data.current_label || 'Current Period'} (Current)`;
  if (prevLbl) prevLbl.textContent = `${data.previous_label || 'Baseline Period'} (Baseline)`;

  // Active Spiderweb Goal Banner
  const goalBanner = document.getElementById("spiderwebGoalBanner");
  const goalBadge = document.getElementById("spiderwebGoalBadge");
  const goalTitle = document.getElementById("spiderwebGoalTitle");
  const goalProgLbl = document.getElementById("spiderwebGoalProgressLabel");
  const goalRemLbl = document.getElementById("spiderwebGoalRemainingLabel");
  const goalBar = document.getElementById("spiderwebGoalProgressBar");
  const goalChips = document.getElementById("spiderwebGoalChips");
  const legendGoalItem = document.getElementById("spiderwebLegendGoalItem");
  const legendGoalLbl = document.getElementById("spiderwebLegendGoalLabel");

  if (data.has_active_goal && data.active_goal) {
    const g = data.active_goal;
    if (goalBanner) goalBanner.style.display = "flex";
    if (goalBadge) goalBadge.textContent = g.target_badge || "🎯 Active Goal";
    if (goalTitle) goalTitle.textContent = g.target_title;
    if (goalProgLbl) goalProgLbl.textContent = `Goal Progress: ${g.progress_pct || 0}% achieved`;
    if (goalBar) goalBar.style.width = `${Math.min(100, Math.max(5, g.progress_pct || 0))}%`;
    if (goalRemLbl) {
      if (g.is_achieved) {
        goalRemLbl.textContent = "🏆 Target Unlocked!";
        goalRemLbl.style.color = "#10b981";
      } else {
        goalRemLbl.textContent = `${g.remaining_total_watts || 0}W total gap remaining`;
        goalRemLbl.style.color = "#f59e0b";
      }
    }
    if (goalChips && data.axes) {
      goalChips.innerHTML = data.axes.map(ax => {
        if (!ax.target_watts) return "";
        const isMet = ax.goal_met;
        const cls = isMet ? "met" : "gap";
        const icon = isMet ? "✓" : "▲";
        const remText = isMet ? "Met" : `-${ax.goal_remaining_watts}W`;
        return `<span class="spiderweb-goal-chip ${cls}">${ax.icon} ${ax.name}: ${ax.target_watts}W (${icon} ${remText})</span>`;
      }).join("");
    }
    if (legendGoalItem) {
      legendGoalItem.style.display = "inline-flex";
      if (legendGoalLbl) legendGoalLbl.textContent = `Goal: ${g.target_title}`;
    }
  } else {
    if (goalBanner) goalBanner.style.display = "none";
    if (legendGoalItem) legendGoalItem.style.display = "none";
  }

  // Phenotype badge & card
  const badgeEl = document.getElementById("spiderwebPhenotypeBadge");
  const titleEl = document.getElementById("spiderwebPhenotypeTitle");
  const descEl = document.getElementById("spiderwebPhenotypeDesc");
  const strengthEl = document.getElementById("spiderwebStrengthVal");
  const growthEl = document.getElementById("spiderwebGrowthVal");
  const iconEl = document.getElementById("spiderwebPhenotypeIcon");

  if (data.phenotype) {
    if (badgeEl) badgeEl.textContent = data.phenotype.badge || data.phenotype.title;
    if (titleEl) titleEl.textContent = data.phenotype.title;
    if (descEl) descEl.textContent = data.phenotype.description;
    if (strengthEl) strengthEl.textContent = data.phenotype.primary_strength;
    if (growthEl) growthEl.textContent = data.phenotype.growth_focus;
    if (iconEl) {
      const icons = {
        "Sprinter": "⚡",
        "Puncheur": "🚀",
        "Pursuiter": "⏱️",
        "Rouleur": "🛡️",
        "Climber": "🏔️",
        "All-Rounder": "🎯"
      };
      iconEl.textContent = icons[data.phenotype.title] || "🎯";
    }
  }

  // Collapsed summary chips
  const c5s = document.getElementById("collapsedSpiderweb5s");
  const c5m = document.getElementById("collapsedSpiderweb5m");
  const c20m = document.getElementById("collapsedSpiderweb20m");

  const s5 = data.axes.find(a => a.key === "5s");
  const s5m = data.axes.find(a => a.key === "5m");
  const s20m = data.axes.find(a => a.key === "20m");
  const isAllTime = data.timeframe === "all_time";

  const formatCollapsedChip = (label, axis) => {
    if (isAllTime) {
      const prW = axis.all_time_pr_watts || axis.previous_watts || axis.current_watts;
      const delta = axis.delta_watts || 0;
      return delta < 0
        ? `${label}: ${prW}W PR (${delta}W cur)`
        : `${label}: ${prW}W PR`;
    }
    const sign = axis.delta_watts > 0 ? "+" : "";
    return `${label}: ${axis.current_watts}W (${sign}${axis.delta_watts}W)`;
  };

  if (c5s && s5) c5s.textContent = formatCollapsedChip("5s", s5);
  if (c5m && s5m) c5m.textContent = formatCollapsedChip("5m", s5m);
  if (c20m && s20m) c20m.textContent = formatCollapsedChip("20m", s20m);

  // Draw SVG Radar with active goal polygon
  renderSpiderwebSvg(data.axes, data.active_goal);

  // Duration metrics grid
  renderSpiderwebDurationsGrid(data.axes);

  // 3-Line Power Duration Curve Chart (Current, Previous, All-Time / Target)
  renderPowerCurveTimelineChart(data.axes, data.active_goal);

  // Historical Timeline (with Mini-Spiderwebs)
  renderSpiderwebTimeline(data.progression_timeline, data.axes);

  // Breakthrough PRs
  renderSpiderwebBreakthroughs(data.recent_breakthroughs);

  // Auto-load target analysis planner data
  loadSpiderwebTargetAnalysis();
}

function renderSpiderwebSvg(axes, activeGoal) {
  const svg = document.getElementById("spiderwebSvg");
  if (!svg || !axes || axes.length === 0) return;

  const cx = 300;
  const cy = 232;
  const r = 142;
  const n = axes.length;

  const defsHtml = `
    <defs>
      <radialGradient id="radarCurrentGradient" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#0052FF" stop-opacity="0.32" />
        <stop offset="100%" stop-color="#0052FF" stop-opacity="0.10" />
      </radialGradient>
      <radialGradient id="radarPreviousGradient" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#FF5E00" stop-opacity="0.22" />
        <stop offset="100%" stop-color="#FF5E00" stop-opacity="0.06" />
      </radialGradient>
      <radialGradient id="radarGoalGradient" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#00C896" stop-opacity="0.26" />
        <stop offset="100%" stop-color="#00C896" stop-opacity="0.08" />
      </radialGradient>
      <filter id="radarGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="2.5" result="blur" />
        <feComposite in="SourceGraphic" in2="blur" operator="over" />
      </filter>
    </defs>
  `;

  let content = defsHtml;

  // Concentric pentagon rings
  const levels = [0.2, 0.4, 0.6, 0.8, 1.0];
  levels.forEach((lvl, idx) => {
    const isOuter = idx === levels.length - 1;
    const pts = [];
    for (let i = 0; i < n; i++) {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
      const px = cx + (r * lvl) * Math.cos(angle);
      const py = cy + (r * lvl) * Math.sin(angle);
      pts.push(`${px.toFixed(1)},${py.toFixed(1)}`);
    }
    const strokeColor = isOuter ? "rgba(100, 116, 139, 0.45)" : "rgba(100, 116, 139, 0.22)";
    const strokeW = isOuter ? "1.5" : "1";
    const dash = isOuter ? "none" : "3 3";
    content += `<polygon points="${pts.join(" ")}" fill="none" stroke="${strokeColor}" stroke-width="${strokeW}" stroke-dasharray="${dash}" />`;

    // Percentage tick label along top axis
    if (idx > 0 && idx < levels.length - 1) {
      const labelY = cy - (r * lvl);
      content += `<text x="${cx + 5}" y="${(labelY + 13).toFixed(1)}" fill="#64748B" font-size="11" font-weight="600" font-family="Inter, monospace">${Math.round(lvl * 100)}%</text>`;
    }
  });

  // Radial spoke lines
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const sx = cx + r * Math.cos(angle);
    const sy = cy + r * Math.sin(angle);
    content += `<line x1="${cx}" y1="${cy}" x2="${sx.toFixed(1)}" y2="${sy.toFixed(1)}" stroke="rgba(100, 116, 139, 0.25)" stroke-width="1" />`;
  }

  // Baseline polygon
  const prevPts = [];
  const prevCircles = [];
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const pct = Math.max(15, Math.min(100, axes[i].previous_radar_pct || 20)) / 100;
    const px = cx + (r * pct) * Math.cos(angle);
    const py = cy + (r * pct) * Math.sin(angle);
    prevPts.push(`${px.toFixed(1)},${py.toFixed(1)}`);
    prevCircles.push({ x: px, y: py, axis: axes[i] });
  }
  content += `<polygon points="${prevPts.join(" ")}" fill="url(#radarPreviousGradient)" stroke="#FF5E00" stroke-width="2.2" stroke-dasharray="4 3" opacity="0.92" />`;
  prevCircles.forEach(pt => {
    content += `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="4.5" fill="#FF5E00" stroke="#FFFFFF" stroke-width="1.5"><title>Baseline: ${pt.axis.previous_watts || '--'}W</title></circle>`;
  });

  // Active Goal Polygon (if active goal set)
  const hasGoal = !!(activeGoal && axes.some(a => a.target_radar_pct !== null && a.target_radar_pct !== undefined));
  if (hasGoal) {
    const goalPts = [];
    const goalDiamonds = [];
    for (let i = 0; i < n; i++) {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
      const pct = Math.max(15, Math.min(100, axes[i].target_radar_pct || axes[i].current_radar_pct || 20)) / 100;
      const gx = cx + (r * pct) * Math.cos(angle);
      const gy = cy + (r * pct) * Math.sin(angle);
      goalPts.push(`${gx.toFixed(1)},${gy.toFixed(1)}`);
      goalDiamonds.push({ x: gx, y: gy, axis: axes[i] });
    }
    content += `<polygon points="${goalPts.join(" ")}" fill="url(#radarGoalGradient)" stroke="#00C896" stroke-width="2.5" stroke-dasharray="6 3" opacity="0.95" />`;
    goalDiamonds.forEach(pt => {
      content += `
        <polygon points="${(pt.x).toFixed(1)},${(pt.y - 5.5).toFixed(1)} ${(pt.x + 5.5).toFixed(1)},${(pt.y).toFixed(1)} ${(pt.x).toFixed(1)},${(pt.y + 5.5).toFixed(1)} ${(pt.x - 5.5).toFixed(1)},${(pt.y).toFixed(1)}" fill="#00C896" stroke="#FFFFFF" stroke-width="1.5">
          <title>Goal Target: ${escapeSpiderwebHtml(pt.axis.name)} @ ${pt.axis.target_watts || '--'}W (${pt.axis.target_w_kg || '--'} W/kg)</title>
        </polygon>
      `;
    });
  }

  // Current period polygon
  const curPts = [];
  const curCircles = [];
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const pct = Math.max(15, Math.min(100, axes[i].current_radar_pct || 20)) / 100;
    const px = cx + (r * pct) * Math.cos(angle);
    const py = cy + (r * pct) * Math.sin(angle);
    curPts.push(`${px.toFixed(1)},${py.toFixed(1)}`);
    curCircles.push({ x: px, y: py, axis: axes[i] });
  }
  content += `<polygon points="${curPts.join(" ")}" fill="url(#radarCurrentGradient)" stroke="#0052FF" stroke-width="2.75" filter="url(#radarGlow)" />`;
  curCircles.forEach(pt => {
    content += `<circle class="spiderweb-svg-vertex-hit" data-axis-key="${escapeSpiderwebHtml(pt.axis.key)}" cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="6" fill="#0052FF" stroke="#FFFFFF" stroke-width="2"><title>${escapeSpiderwebHtml(pt.axis.name)}: ${pt.axis.current_watts}W (${pt.axis.current_w_kg} W/kg) — Click for details</title></circle>`;
  });

  // Outer axis labels
  for (let i = 0; i < n; i++) {
    const ax = axes[i];
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const labelDist = r + 18;
    let lx = cx + labelDist * Math.cos(angle);
    let ly = cy + labelDist * Math.sin(angle);

    let textAnchor = "middle";
    let hitX = lx - 68;
    if (Math.abs(Math.cos(angle)) > 0.3) {
      if (Math.cos(angle) > 0) {
        textAnchor = "start";
        lx += 6;
        hitX = lx - 6;
      } else {
        textAnchor = "end";
        lx -= 6;
        hitX = lx - 134;
      }
      if (Math.sin(angle) < 0) {
        ly -= 12;
      }
    } else {
      if (Math.sin(angle) < 0) {
        ly -= 36;
      } else {
        ly += 14;
      }
      hitX = lx - 70;
    }

    const deltaSign = ax.delta_watts > 0 ? "+" : "";
    const deltaColor = ax.delta_watts > 0 ? "#00C896" : ax.delta_watts < 0 ? "#EF4444" : "#64748B";

    let goalLine = "";
    if (hasGoal && ax.target_watts) {
      if (ax.goal_met) {
        goalLine = `<text x="${lx.toFixed(1)}" y="${(ly + 48).toFixed(1)}" text-anchor="${textAnchor}" fill="#00C896" font-size="11" font-weight="700">🎯 ${ax.target_watts}W (✓ Met)</text>`;
      } else {
        goalLine = `<text x="${lx.toFixed(1)}" y="${(ly + 48).toFixed(1)}" text-anchor="${textAnchor}" fill="#FF5E00" font-size="11" font-weight="700">🎯 ${ax.target_watts}W (-${ax.goal_remaining_watts}W)</text>`;
      }
    }

    const hitHeight = (hasGoal && ax.target_watts) ? 68 : 52;
    content += `
      <g class="spiderweb-svg-axis-label" data-axis-key="${escapeSpiderwebHtml(ax.key)}" role="button" tabindex="0" aria-label="Inspect ${escapeSpiderwebHtml(ax.name || ax.label)} details" style="pointer-events:all;">
        <rect x="${hitX.toFixed(1)}" y="${(ly - 15).toFixed(1)}" width="140" height="${hitHeight}" rx="6" fill="transparent" pointer-events="all" />
        <text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${textAnchor}" fill="#111625" font-size="14" font-weight="800" font-family="Outfit, Inter, sans-serif">
          ${ax.icon} ${escapeSpiderwebHtml(ax.label)}
        </text>
        <text x="${lx.toFixed(1)}" y="${(ly + 17).toFixed(1)}" text-anchor="${textAnchor}" fill="#0052FF" font-size="14" font-weight="800" font-family="Outfit, Inter, sans-serif">
          ${ax.current_watts}W <tspan fill="#64748B" font-size="12" font-weight="600" font-family="Inter, sans-serif">· ${ax.current_w_kg ? ax.current_w_kg.toFixed(1) : '--'} W/kg</tspan>
        </text>
        <text x="${lx.toFixed(1)}" y="${(ly + 32).toFixed(1)}" text-anchor="${textAnchor}" fill="${deltaColor}" font-size="11.5" font-weight="700">
          ${deltaSign}${ax.delta_watts}W (${deltaSign}${ax.delta_pct ? ax.delta_pct.toFixed(1) : '0.0'}%)
        </text>
        ${goalLine}
      </g>
    `;
  }

  svg.innerHTML = content;

  svg.querySelectorAll("[data-axis-key]").forEach(el => {
    const key = el.getAttribute("data-axis-key");
    el.addEventListener("click", () => openSpiderwebAxisModal(key));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openSpiderwebAxisModal(key);
      }
    });
  });
}

function openSpiderwebAxisModal(axisKey) {
  if (typeof currentSpiderwebData === "undefined" || !currentSpiderwebData || !Array.isArray(currentSpiderwebData.axes)) return;
  const ax = currentSpiderwebData.axes.find(a => a.key === axisKey);
  const modal = document.getElementById("spiderwebAxisModal");
  if (!ax || !modal) return;

  const iconEl = document.getElementById("spiderwebAxisModalIcon");
  const titleEl = document.getElementById("spiderwebAxisModalTitle");
  const sysEl = document.getElementById("spiderwebAxisModalSystem");
  const bodyEl = document.getElementById("spiderwebAxisModalBody");

  if (iconEl) iconEl.textContent = ax.icon || "⚡";
  if (titleEl) titleEl.textContent = ax.name || ax.label || axisKey;
  if (sysEl) sysEl.textContent = ax.energy_system || "Power Duration Axis";

  const deltaSign = ax.delta_watts > 0 ? "▲ +" : ax.delta_watts < 0 ? "▼ " : "";
  const deltaColor = ax.delta_watts > 0 ? "#00C896" : ax.delta_watts < 0 ? "#EF4444" : "#64748B";
  const barPct = Math.min(100, Math.max(8, ax.current_radar_pct || 20));
  const pheno = currentSpiderwebData.phenotype || {};

  const goalHtml = ax.target_watts
    ? `<div class="spiderweb-axis-stat-box" style="grid-column:1 / -1;border-color:${ax.goal_met ? 'rgba(0,200,150,0.45)' : 'rgba(255,94,0,0.45)'};">
         <span class="spiderweb-axis-stat-lbl">Active Goal Target</span>
         <span class="spiderweb-axis-stat-val" style="color:${ax.goal_met ? '#00C896' : '#FF5E00'};">
           🎯 ${ax.target_watts}W ${ax.target_w_kg ? `(${ax.target_w_kg.toFixed(2)} W/kg)` : ''}
         </span>
         <span class="spiderweb-axis-stat-sub">
           ${ax.goal_met ? '✓ Target Achieved!' : `${ax.goal_remaining_watts}W remaining to reach target`}
         </span>
       </div>`
    : "";

  if (bodyEl) {
    bodyEl.innerHTML = `
      <div class="spiderweb-axis-stat-grid">
        <div class="spiderweb-axis-stat-box">
          <span class="spiderweb-axis-stat-lbl">Current Period</span>
          <span class="spiderweb-axis-stat-val" style="color:#0052FF;">${ax.current_watts}W</span>
          <span class="spiderweb-axis-stat-sub">${ax.current_w_kg ? ax.current_w_kg.toFixed(2) : '--'} W/kg</span>
        </div>
        <div class="spiderweb-axis-stat-box">
          <span class="spiderweb-axis-stat-lbl">Period Change</span>
          <span class="spiderweb-axis-stat-val" style="color:${deltaColor};">${deltaSign}${ax.delta_watts}W</span>
          <span class="spiderweb-axis-stat-sub">${ax.delta_pct > 0 ? '+' : ''}${ax.delta_pct ? ax.delta_pct.toFixed(1) : '0.0'}% vs prior</span>
        </div>
        <div class="spiderweb-axis-stat-box">
          <span class="spiderweb-axis-stat-lbl">Comparison / Prior</span>
          <span class="spiderweb-axis-stat-val">${ax.previous_watts || '--'}W</span>
          <span class="spiderweb-axis-stat-sub">${ax.previous_w_kg ? ax.previous_w_kg.toFixed(2) + ' W/kg' : '--'}</span>
        </div>
        <div class="spiderweb-axis-stat-box">
          <span class="spiderweb-axis-stat-lbl">Synced All-Time PR</span>
          <span class="spiderweb-axis-stat-val" style="color:#FF5E00;">${ax.all_time_pr_watts || ax.current_watts}W</span>
          <span class="spiderweb-axis-stat-sub">Benchmark ceiling: ${ax.benchmark_watts || '--'}W</span>
        </div>
        ${goalHtml}
      </div>
      <div>
        <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:var(--text-muted);margin-bottom:0.35rem;">
          <span>Benchmark Ceiling Progress</span>
          <span style="font-weight:700;color:var(--text-primary);">${(ax.current_radar_pct || 0).toFixed(0)}%</span>
        </div>
        <div class="duration-progress-bar-bg">
          <div class="duration-progress-bar-fill" style="width:${barPct}%;"></div>
        </div>
      </div>
      ${pheno.title ? `
        <div style="background:rgba(0,82,255,0.05);border:1px solid rgba(0,82,255,0.2);border-radius:10px;padding:0.75rem 0.9rem;font-size:0.8rem;color:var(--text-secondary);">
          <div style="font-weight:700;color:var(--text-primary);margin-bottom:0.2rem;">${pheno.icon || '🎯'} Rider Phenotype: ${escapeSpiderwebHtml(pheno.title)}</div>
          <div>${escapeSpiderwebHtml(pheno.description || '')}</div>
        </div>
      ` : ''}
    `;
  }

  modal.classList.add("open");
}

(function initSpiderwebAxisModal() {
  const modal = document.getElementById("spiderwebAxisModal");
  const closeBtn = document.getElementById("btnCloseSpiderwebAxisModal");
  if (closeBtn && modal) {
    closeBtn.addEventListener("click", () => modal.classList.remove("open"));
  }
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.remove("open");
    });
  }
})();

function renderSpiderwebDurationsGrid(axes) {
  const container = document.getElementById("spiderwebDurationsGrid");
  if (!container || !axes) return;

  container.innerHTML = axes.map(ax => {
    const deltaClass = ax.delta_watts > 0 ? "positive" : ax.delta_watts < 0 ? "negative" : "neutral";
    const deltaSign = ax.delta_watts > 0 ? "▲ +" : ax.delta_watts < 0 ? "▼ " : "";
    const barPct = Math.min(100, Math.max(12, ax.current_radar_pct || 20));

    return `
      <div class="spiderweb-duration-card">
        <div class="duration-card-header">
          <div style="display:flex;align-items:center;gap:0.4rem;">
            <span class="duration-icon">${ax.icon}</span>
            <span class="duration-title">${escapeSpiderwebHtml(ax.name || ax.label)}</span>
          </div>
          <span class="duration-system-tag">${escapeSpiderwebHtml(ax.energy_system || '')}</span>
        </div>
        <div class="duration-card-values">
          <div class="duration-primary-val">
            <span class="duration-watts">${ax.current_watts}W</span>
            <span class="duration-wkg">${ax.current_w_kg ? ax.current_w_kg.toFixed(2) : '--'} W/kg</span>
          </div>
          <div class="duration-delta-chip ${deltaClass}">
            ${deltaSign}${ax.delta_watts}W (${ax.delta_pct > 0 ? '+' : ''}${ax.delta_pct ? ax.delta_pct.toFixed(1) : '0.0'}%)
          </div>
        </div>
        <div class="duration-card-sub">
          <span>Prior: ${ax.previous_watts || '--'}W (${ax.previous_w_kg ? ax.previous_w_kg.toFixed(2) + ' W/kg' : '--'})</span>
          <span class="duration-pr-badge">All-Time PR: ${ax.all_time_pr_watts}W</span>
        </div>
        <div class="duration-progress-bar-bg" title="${(ax.current_radar_pct || 0).toFixed(0)}% benchmark ceiling">
          <div class="duration-progress-bar-fill" style="width:${barPct}%;"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderPowerCurveTimelineChart(axes, activeGoal) {
  const svg = document.getElementById("powerCurveTimelineSvg");
  if (!svg || !axes || axes.length === 0) return;

  const w = 540;
  const h = 185;
  const padLeft = 46;
  const padRight = 32;
  const padTop = 22;
  const padBottom = 32;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  const orderKeys = ["5s", "1m", "5m", "20m", "60m"];
  const sortedAxes = orderKeys.map(k => axes.find(a => a.key === k) || { key: k, current_watts: 0, previous_watts: 0, all_time_pr_watts: 0, target_watts: 0, name: k });

  const curWatts = sortedAxes.map(a => a.current_watts || 0);
  const prevWatts = sortedAxes.map(a => a.previous_watts || Math.round(a.current_watts * 0.95) || 0);
  const targetEnvelope = activeGoal?.target_envelope || {};
  const peakWatts = sortedAxes.map(a => targetEnvelope[a.key] || a.target_watts || a.all_time_pr_watts || a.current_watts || 0);

  const allVals = [...curWatts, ...prevWatts, ...peakWatts].filter(v => v > 0);
  const maxW = allVals.length > 0 ? Math.max(...allVals) * 1.12 : 1000;
  const minW = allVals.length > 0 ? Math.max(0, Math.min(...allVals) * 0.75) : 100;
  const valRange = Math.max(10, maxW - minW);

  const getX = (idx) => padLeft + (idx * (chartW / (sortedAxes.length - 1)));
  const getY = (val) => padTop + chartH * (1 - (Math.max(minW, val) - minW) / valRange);

  const curPts = curWatts.map((val, idx) => ({ x: getX(idx), y: getY(val), val, name: sortedAxes[idx].name }));
  const prevPts = prevWatts.map((val, idx) => ({ x: getX(idx), y: getY(val), val, name: sortedAxes[idx].name }));
  const peakPts = peakWatts.map((val, idx) => ({ x: getX(idx), y: getY(val), val, name: sortedAxes[idx].name }));

  const getSmoothPath = (pts) => {
    if (pts.length === 0) return "";
    let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i === 0 ? 0 : i - 1];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2 < pts.length ? i + 2 : i + 1];
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    return d;
  };

  const curPath = getSmoothPath(curPts);
  const prevPath = getSmoothPath(prevPts);
  const peakPath = getSmoothPath(peakPts);

  const bottomY = padTop + chartH;
  const curArea = `${curPath} L ${curPts[curPts.length - 1].x.toFixed(1)},${bottomY} L ${curPts[0].x.toFixed(1)},${bottomY} Z`;

  // Grid lines
  const gridLevels = [0.25, 0.5, 0.75, 1.0];
  let gridHtml = "";
  gridLevels.forEach(lvl => {
    const wVal = Math.round(minW + lvl * valRange);
    const yPos = getY(wVal);
    gridHtml += `
      <line x1="${padLeft}" y1="${yPos.toFixed(1)}" x2="${padLeft + chartW}" y2="${yPos.toFixed(1)}" stroke="rgba(148,163,184,0.18)" stroke-width="1" stroke-dasharray="3 3" />
      <text x="${padLeft - 6}" y="${(yPos + 3).toFixed(1)}" fill="#64748B" font-size="9" text-anchor="end" font-family="monospace">${wVal}W</text>
    `;
  });

  // X Axis Labels
  const durLabels = ["5s", "1m", "5m", "20m", "60m"];
  let xLabelsHtml = "";
  durLabels.forEach((label, idx) => {
    const xPos = getX(idx);
    const axisName = sortedAxes[idx].name || "";
    xLabelsHtml += `
      <line x1="${xPos.toFixed(1)}" y1="${padTop}" x2="${xPos.toFixed(1)}" y2="${bottomY}" stroke="rgba(148,163,184,0.12)" stroke-width="1" />
      <text x="${xPos.toFixed(1)}" y="${bottomY + 14}" fill="var(--text-primary)" font-size="10" font-weight="700" text-anchor="middle">${label}</text>
      <text x="${xPos.toFixed(1)}" y="${bottomY + 25}" fill="var(--text-muted)" font-size="8" text-anchor="middle">${axisName.replace(/\s*\(.*\)/, '')}</text>
    `;
  });

  // Circles & labels
  const peakCircles = peakPts.map(pt => `
    <circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="3.5" fill="#FF5E00" stroke="#FFFFFF" stroke-width="1.5" />
    <text x="${pt.x.toFixed(1)}" y="${(pt.y - 7).toFixed(1)}" fill="#FF5E00" font-size="9" font-weight="700" text-anchor="middle">${pt.val}W</text>
  `).join("");

  const prevCircles = prevPts.map(pt => `
    <circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="3" fill="#8B5CF6" opacity="0.8" />
  `).join("");

  const curCircles = curPts.map((pt) => `
    <circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="4.5" fill="#0052FF" stroke="#FFFFFF" stroke-width="2" />
    <text x="${pt.x.toFixed(1)}" y="${(pt.y + 16).toFixed(1)}" fill="#0052FF" font-size="10" font-weight="800" text-anchor="middle">${pt.val}W</text>
  `).join("");

  svg.innerHTML = `
    <defs>
      <linearGradient id="curveCurGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#0052FF" stop-opacity="0.25" />
        <stop offset="100%" stop-color="#0052FF" stop-opacity="0.02" />
      </linearGradient>
    </defs>
    ${gridHtml}
    ${xLabelsHtml}
    <path d="${curArea}" fill="url(#curveCurGrad)" />
    <!-- Line 2: Previous Period -->
    <path d="${prevPath}" fill="none" stroke="#8B5CF6" stroke-width="2" stroke-dasharray="4 3" opacity="0.85" />
    ${prevCircles}
    <!-- Line 3: All-Time PR / Target -->
    <path d="${peakPath}" fill="none" stroke="#FF5E00" stroke-width="2.2" opacity="0.9" />
    ${peakCircles}
    <!-- Line 1: Current Period -->
    <path d="${curPath}" fill="none" stroke="#0052FF" stroke-width="2.8" />
    ${curCircles}
  `;
}

function generateMiniSpiderwebSvg(item, bmMap) {
  const cx = 80;
  const cy = 54;
  const r = 34;
  const keys = ["5s", "1m", "5m", "20m", "60m"];
  const n = keys.length;

  const outerPts = [];
  const midPts = [];
  const innerPts = [];
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    outerPts.push(`${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`);
    midPts.push(`${(cx + (r * 0.6) * Math.cos(angle)).toFixed(1)},${(cy + (r * 0.6) * Math.sin(angle)).toFixed(1)}`);
    innerPts.push(`${(cx + (r * 0.3) * Math.cos(angle)).toFixed(1)},${(cy + (r * 0.3) * Math.sin(angle)).toFixed(1)}`);
  }

  const polyPts = [];
  const polyNodes = [];
  for (let i = 0; i < n; i++) {
    const k = keys[i];
    const val = item[`peak_${k}`] || 0;
    const bm = (bmMap && bmMap[k]) ? bmMap[k] : 1000;
    const pct = Math.min(1.0, Math.max(0.18, val / (bm || 1)));
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const px = cx + (r * pct) * Math.cos(angle);
    const py = cy + (r * pct) * Math.sin(angle);
    polyPts.push(`${px.toFixed(1)},${py.toFixed(1)}`);
    polyNodes.push({ x: px, y: py, val, key: k });
  }

  let spokes = "";
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI / n);
    const sx = cx + r * Math.cos(angle);
    const sy = cy + r * Math.sin(angle);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${sx.toFixed(1)}" y2="${sy.toFixed(1)}" stroke="rgba(148,163,184,0.2)" stroke-width="0.8" />`;
  }

  const labelConfigs = [
    { key: "5s", x: cx, y: 11, anchor: "middle" },
    { key: "1m", x: 120, y: 45, anchor: "start" },
    { key: "5m", x: 106, y: 95, anchor: "start" },
    { key: "20m", x: 54, y: 95, anchor: "end" },
    { key: "60m", x: 40, y: 45, anchor: "end" }
  ];

  let labelsHtml = "";
  labelConfigs.forEach(cfg => {
    labelsHtml += `<text x="${cfg.x}" y="${cfg.y}" text-anchor="${cfg.anchor}" fill="var(--text-muted)" font-size="8.5" font-weight="700" font-family="Outfit, Inter, sans-serif">${cfg.key}</text>`;
  });

  const nodeCircles = polyNodes.map(node => `
    <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="2.5" fill="#0052FF" stroke="#FFFFFF" stroke-width="1">
      <title>${node.key}: ${node.val ? node.val + 'W' : '--'}</title>
    </circle>
  `).join("");

  return `
    <svg viewBox="0 0 160 110" style="width:100%;height:100%;max-height:105px;display:block;overflow:visible;">
      <polygon points="${outerPts.join(" ")}" fill="rgba(15,23,42,0.12)" stroke="rgba(148,163,184,0.28)" stroke-width="0.9" />
      <polygon points="${midPts.join(" ")}" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="0.8" stroke-dasharray="2 2" />
      <polygon points="${innerPts.join(" ")}" fill="none" stroke="rgba(148,163,184,0.12)" stroke-width="0.7" />
      ${spokes}
      ${labelsHtml}
      <polygon points="${polyPts.join(" ")}" fill="rgba(0, 82, 255, 0.22)" stroke="#0052FF" stroke-width="1.8" />
      ${nodeCircles}
    </svg>
  `;
}

function initTimelineViewSwitcher() {
  const btnAll = document.getElementById("btnTimelineToggleAll");
  const btnCurve = document.getElementById("btnTimelineToggleCurve");
  const btnRadar = document.getElementById("btnTimelineToggleRadar");
  const curveWrap = document.getElementById("timelineCurveChartWrap");
  const gridWrap = document.getElementById("spiderwebTimelineGrid");

  const setView = (mode) => {
    [btnAll, btnCurve, btnRadar].forEach(b => b?.classList.remove("active"));
    if (mode === "all") {
      btnAll?.classList.add("active");
      if (curveWrap) curveWrap.style.display = "block";
      if (gridWrap) gridWrap.style.display = "grid";
    } else if (mode === "curve") {
      btnCurve?.classList.add("active");
      if (curveWrap) curveWrap.style.display = "block";
      if (gridWrap) gridWrap.style.display = "none";
    } else if (mode === "radar") {
      btnRadar?.classList.add("active");
      if (curveWrap) curveWrap.style.display = "none";
      if (gridWrap) gridWrap.style.display = "grid";
    }
  };

  btnAll?.addEventListener("click", () => setView("all"));
  btnCurve?.addEventListener("click", () => setView("curve"));
  btnRadar?.addEventListener("click", () => setView("radar"));
}

let hasInitTimelineSwitcher = false;

function renderSpiderwebTimeline(timeline, axes) {
  const container = document.getElementById("spiderwebTimelineGrid");
  if (!container) return;

  if (!hasInitTimelineSwitcher) {
    initTimelineViewSwitcher();
    hasInitTimelineSwitcher = true;
  }

  if (!timeline || timeline.length === 0) {
    container.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:var(--text-muted);padding:1rem;">No monthly progression data recorded yet.</div>`;
    return;
  }

  const bmMap = {};
  (axes || []).forEach(a => {
    bmMap[a.key] = a.benchmark_ceiling_watts || a.all_time_pr_watts || 1000;
  });

  container.innerHTML = timeline.map(item => {
    const miniSvg = generateMiniSpiderwebSvg(item, bmMap);
    const rideCount = item.cycling_count !== undefined ? item.cycling_count : (item.workout_count || 0);
    const hours = item.cycling_hours || item.total_hours || 0;
    const crossCount = item.cross_training_count || 0;
    const crossBadge = crossCount > 0 ? ` · +${crossCount} cross` : '';
    const rideText = `${rideCount} ${rideCount === 1 ? 'ride' : 'rides'}`;

    return `
      <div class="spiderweb-timeline-card">
        <div class="timeline-card-header">
          <span class="timeline-month">${escapeSpiderwebHtml(item.label)}</span>
          <span class="timeline-count-badge" title="${rideText} (${hours}h)${crossCount > 0 ? ' plus ' + crossCount + ' cross-training sessions' : ''}">
            ${rideText} · ${hours}h${crossBadge}
          </span>
        </div>
        <div class="timeline-mini-radar-container" title="Monthly 5-Axis Phenotype Radar (${escapeSpiderwebHtml(item.label)})">
          ${miniSvg}
        </div>
        <div class="timeline-power-strip">
          <div class="timeline-power-cell">
            <span class="cell-label">5s</span>
            <span class="cell-val">${item.peak_5s ? item.peak_5s + 'W' : '--'}</span>
          </div>
          <div class="timeline-power-cell">
            <span class="cell-label">1m</span>
            <span class="cell-val">${item.peak_1m ? item.peak_1m + 'W' : '--'}</span>
          </div>
          <div class="timeline-power-cell">
            <span class="cell-label">5m</span>
            <span class="cell-val">${item.peak_5m ? item.peak_5m + 'W' : '--'}</span>
          </div>
          <div class="timeline-power-cell">
            <span class="cell-label">20m</span>
            <span class="cell-val">${item.peak_20m ? item.peak_20m + 'W' : '--'}</span>
          </div>
          <div class="timeline-power-cell">
            <span class="cell-label">60m</span>
            <span class="cell-val">${item.peak_60m ? item.peak_60m + 'W' : '--'}</span>
          </div>
        </div>
        <div class="timeline-card-footer">
          <span>Work: <strong style="color:var(--accent-cyan);">${item.total_tss || 0} TSS</strong></span>
          <span>${rideText}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderSpiderwebBreakthroughs(breakthroughs) {
  const container = document.getElementById("spiderwebBreakthroughsList");
  if (!container) return;

  if (!breakthroughs || breakthroughs.length === 0) {
    container.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:1rem;font-size:0.85rem;">Complete more high-intensity intervals to log power PR breakthroughs!</div>`;
    return;
  }

  container.innerHTML = breakthroughs.map(b => `
    <div class="spiderweb-breakthrough-item">
      <span class="breakthrough-badge">${escapeSpiderwebHtml(b.badge)}</span>
      <span class="breakthrough-info">
        <strong>${escapeSpiderwebHtml(b.duration)}</strong> on <em>${escapeSpiderwebHtml(b.activity_name)}</em>
      </span>
      <span class="breakthrough-date">${escapeSpiderwebHtml(b.date)}</span>
    </div>
  `).join("");
}

// --- Interactive Spiderweb Target Changes Explorer & Goal Planner ---

let currentPlannerMode = "duration"; // "duration" or "phenotype"
let currentPlannerDurationKey = "20m";
let currentTargetAnalysisData = null;
let isPlannerNavBound = false;

let hasSyncedInitialPlannerMode = false;

async function loadSpiderwebTargetAnalysis(syncToActiveGoal = false) {
  try {
    const res = await fetch(`/api/power/spiderweb/target-analysis?timeframe=${encodeURIComponent(currentSpiderwebTimeframe || "30d")}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    currentTargetAnalysisData = await res.json();

    const activeGoal = currentTargetAnalysisData.active_goal;
    if ((syncToActiveGoal || !hasSyncedInitialPlannerMode) && activeGoal) {
      hasSyncedInitialPlannerMode = true;
      const btnDur = document.getElementById("btnPlannerTabDuration");
      const btnPheno = document.getElementById("btnPlannerTabPhenotype");
      const durView = document.getElementById("plannerDurationView");
      const phenoView = document.getElementById("plannerPhenotypeView");

      if (activeGoal.goal_type === "phenotype") {
        currentPlannerMode = "phenotype";
        btnPheno?.classList.add("active");
        btnDur?.classList.remove("active");
        if (durView) durView.style.display = "none";
        if (phenoView) phenoView.style.display = "block";
      } else if (activeGoal.goal_type === "duration") {
        currentPlannerMode = "duration";
        if (activeGoal.target_key) {
          currentPlannerDurationKey = activeGoal.target_key;
        }
        btnDur?.classList.add("active");
        btnPheno?.classList.remove("active");
        if (durView) durView.style.display = "block";
        if (phenoView) phenoView.style.display = "none";
      }
    }

    renderSpiderwebTargetPlanner();
  } catch (err) {
    console.warn("Failed to load spiderweb target analysis:", err);
  }
}

function setupSpiderwebPlannerNav() {
  if (isPlannerNavBound) return;
  isPlannerNavBound = true;

  const btnDur = document.getElementById("btnPlannerTabDuration");
  const btnPheno = document.getElementById("btnPlannerTabPhenotype");
  const durView = document.getElementById("plannerDurationView");
  const phenoView = document.getElementById("plannerPhenotypeView");

  if (btnDur && btnPheno) {
    btnDur.addEventListener("click", () => {
      btnDur.classList.add("active");
      btnPheno.classList.remove("active");
      currentPlannerMode = "duration";
      if (durView) durView.style.display = "block";
      if (phenoView) phenoView.style.display = "none";
      renderSpiderwebTargetPlanner();
    });

    btnPheno.addEventListener("click", () => {
      btnPheno.classList.add("active");
      btnDur.classList.remove("active");
      currentPlannerMode = "phenotype";
      if (durView) durView.style.display = "none";
      if (phenoView) phenoView.style.display = "block";
      renderSpiderwebTargetPlanner();
    });
  }

  const clearBtn = document.getElementById("btnClearSpiderwebGoal");
  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to clear your active spiderweb training goal?")) return;
      try {
        const res = await fetch("/api/power/spiderweb/goal", { method: "DELETE" });
        if (res.ok) {
          const resp = await res.json();
          showToast("Active spiderweb goal cleared");
          if (resp.profile) {
            renderPowerSpiderweb(resp.profile);
          } else {
            loadPowerSpiderweb(currentSpiderwebTimeframe);
          }
          if (resp.program) {
            renderProgram(resp.program);
          }
          await loadDashboard();
          await loadWorkout(state.currentDuration, state.currentIntensity);
        }
      } catch (err) {
        console.error("Error clearing spiderweb goal:", err);
      }
    });
  }

  const togglePlannerBtn = document.getElementById("btnTogglePlannerSection");
  if (togglePlannerBtn) {
    togglePlannerBtn.addEventListener("click", () => {
      const section = document.getElementById("spiderwebPlannerSection");
      if (section) {
        section.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  const btnJumpToMacrocycle = document.getElementById("btnJumpToMacrocycleCard");
  if (btnJumpToMacrocycle) {
    btnJumpToMacrocycle.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof switchMainDashboardView === "function" && currentActiveMainView !== "analysis") {
        switchMainDashboardView("analysis", true);
      }
      const card = document.getElementById("cardProgram");
      if (card) {
        if (programCollapsible && typeof programCollapsible.expand === "function") {
          programCollapsible.expand();
        }
        card.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  const btnJumpToSpiderweb = document.getElementById("btnJumpToSpiderwebPlanner");
  if (btnJumpToSpiderweb) {
    btnJumpToSpiderweb.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof switchMainDashboardView === "function" && currentActiveMainView !== "analysis") {
        switchMainDashboardView("analysis", true);
      }
      if (powerSpiderwebCollapsible && typeof powerSpiderwebCollapsible.expand === "function") {
        powerSpiderwebCollapsible.expand();
      }
      const section = document.getElementById("spiderwebPlannerSection");
      if (section) {
        section.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  const btnResetBlock = document.getElementById("btnResetProgramBlock");
  if (btnResetBlock) {
    btnResetBlock.addEventListener("click", async (e) => {
      e.stopPropagation();
      const goalTitle = state.program?.goal_title || "your active goal";
      if (!confirm(`Reset macrocycle block to Week 1 (8-week adaptation cycle) for ${goalTitle}?`)) return;
      try {
        const res = await fetch("/api/program/reset-block", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ block_weeks: 8 })
        });
        if (res.ok) {
          const data = await res.json();
          showToast("🚀 Macrocycle block reset to Week 1 (Base Phase)");
          if (data.program) renderProgram(data.program);
          if (data.profile) renderPowerSpiderweb(data.profile);
        } else {
          showToast("Failed to reset block", "error");
        }
      } catch (err) {
        console.error("Error resetting block:", err);
        showToast("Error resetting block", "error");
      }
    });
  }

  const programSpiderwebBadge = document.getElementById("programSpiderwebBadge");
  if (programSpiderwebBadge) {
    programSpiderwebBadge.style.cursor = "pointer";
    programSpiderwebBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof switchMainDashboardView === "function" && currentActiveMainView !== "analysis") {
        switchMainDashboardView("analysis", true);
      }
      if (powerSpiderwebCollapsible && typeof powerSpiderwebCollapsible.expand === "function") {
        powerSpiderwebCollapsible.expand();
      }
      const section = document.getElementById("spiderwebPlannerSection") || document.getElementById("cardPowerSpiderweb");
      if (section) {
        section.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  const plannerSyncBadge = document.getElementById("plannerMacrocycleSyncBadge");
  if (plannerSyncBadge) {
    plannerSyncBadge.style.cursor = "pointer";
    plannerSyncBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      if (typeof switchMainDashboardView === "function" && currentActiveMainView !== "analysis") {
        switchMainDashboardView("analysis", true);
      }
      const card = document.getElementById("cardProgram");
      if (card) {
        if (programCollapsible && typeof programCollapsible.expand === "function") {
          programCollapsible.expand();
        }
        card.scrollIntoView({ behavior: "smooth" });
      }
    });
  }
}

function renderSpiderwebTargetPlanner() {
  if (!currentTargetAnalysisData) return;

  if (currentPlannerMode === "duration") {
    renderPlannerDurationView();
  } else {
    renderPlannerPhenotypeView();
  }
}

function renderPlannerDurationView() {
  const pillsContainer = document.getElementById("plannerDurationPills");
  const tiersContainer = document.getElementById("plannerTiersGrid");
  if (!pillsContainer || !tiersContainer || !currentTargetAnalysisData) return;

  const list = currentTargetAnalysisData.duration_category_targets || [];
  if (list.length === 0) return;

  const activeGoal = currentTargetAnalysisData.active_goal || null;
  const activeGoalKey = (activeGoal && activeGoal.goal_type === "duration") ? activeGoal.target_key : null;
  const activeGoalWatts = (activeGoal && activeGoal.goal_type === "duration" && activeGoal.target_envelope)
    ? activeGoal.target_envelope[activeGoalKey]
    : null;

  // Render pills
  pillsContainer.innerHTML = list.map(item => `
    <button type="button" class="duration-pill-btn ${item.key === currentPlannerDurationKey ? 'active' : ''}" data-dur="${item.key}">
      <span>${item.icon}</span>
      <span>${escapeSpiderwebHtml(item.label)}</span>
      <span style="opacity:0.75;font-size:0.75rem;">(${item.current_watts}W${activeGoalKey === item.key ? ' 🎯' : ''})</span>
    </button>
  `).join("");

  pillsContainer.querySelectorAll(".duration-pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentPlannerDurationKey = btn.dataset.dur;
      renderPlannerDurationView();
    });
  });

  const selected = list.find(item => item.key === currentPlannerDurationKey) || list[0];
  if (!selected) return;

  const t1 = selected.tier1_progressive;
  const t2 = selected.tier2_transformative;
  const t3 = selected.tier3_benchmark;
  const guidance = selected.guidance || {};

  const isTierActive = (watts) => activeGoalKey === selected.key && activeGoalWatts === watts;

  tiersContainer.innerHTML = `
    <!-- Current Baseline Card -->
    <div class="planner-tier-card" style="background:rgba(255,255,255,0.02);border-color:rgba(255,255,255,0.08);">
      <div class="tier-card-header">
        <span class="tier-title">${selected.icon} Current Best Envelope</span>
        <span class="spiderweb-goal-badge" style="background:rgba(6,182,212,0.15);color:var(--accent-cyan);border-color:rgba(6,182,212,0.3);">Baseline</span>
      </div>
      <div class="tier-power-row">
        <span class="tier-target-watts" style="color:var(--accent-cyan);">${selected.current_watts}W</span>
        <span style="font-size:0.85rem;color:var(--text-muted);">${selected.current_w_kg} W/kg</span>
      </div>
      <div class="tier-stimulus-text">
        <strong>Energy System:</strong> ${escapeSpiderwebHtml(selected.energy_system)}<br>
        <strong>Benchmark Ceiling:</strong> ${selected.benchmark_watts}W (${Math.round((selected.current_watts / selected.benchmark_watts) * 100)}%)
      </div>
    </div>

    <!-- Tier 1: Progressive +5% -->
    <div class="planner-tier-card" style="${isTierActive(t1.target_watts) ? 'border-color:#10b981;box-shadow:0 0 12px rgba(16,185,129,0.2);' : ''}">
      <div class="tier-card-header">
        <span class="tier-title">${escapeSpiderwebHtml(t1.label)}</span>
        <span class="tier-delta-chip">+${t1.delta_watts}W (+${t1.delta_pct}%)</span>
      </div>
      <div class="tier-power-row">
        <span class="tier-target-watts">${t1.target_watts}W</span>
        <span style="font-size:0.85rem;color:var(--text-muted);">${t1.target_w_kg} W/kg</span>
      </div>
      <div class="tier-stimulus-text">
        <strong>Timeline:</strong> ${t1.timeline}<br>
        <strong>Adaptation:</strong> ${escapeSpiderwebHtml(guidance.stimulus || 'Cardiovascular efficiency and progressive wattage density.')}
      </div>
      <button type="button" class="btn-set-goal" data-type="duration" data-key="${selected.key}" data-watts="${t1.target_watts}" style="${isTierActive(t1.target_watts) ? 'background:rgba(16,185,129,0.2);border-color:#10b981;color:#10b981;' : ''}">
        ${isTierActive(t1.target_watts) ? `✓ Active Goal (${t1.target_watts}W Synced to Program)` : `🎯 Set ${t1.target_watts}W as Active Goal`}
      </button>
    </div>

    <!-- Tier 2: Transformative Leap +10% -->
    <div class="planner-tier-card" style="${isTierActive(t2.target_watts) ? 'border-color:#10b981;box-shadow:0 0 12px rgba(16,185,129,0.2);' : ''}">
      <div class="tier-card-header">
        <span class="tier-title">${escapeSpiderwebHtml(t2.label)}</span>
        <span class="tier-delta-chip">+${t2.delta_watts}W (+${t2.delta_pct}%)</span>
      </div>
      <div class="tier-power-row">
        <span class="tier-target-watts">${t2.target_watts}W</span>
        <span style="font-size:0.85rem;color:var(--text-muted);">${t2.target_w_kg} W/kg</span>
      </div>
      <div class="tier-stimulus-text">
        <strong>Timeline:</strong> ${t2.timeline}<br>
        <strong>Workouts:</strong> ${escapeSpiderwebHtml(guidance.workouts || 'Progressive interval overload.')}
      </div>
      <button type="button" class="btn-set-goal" data-type="duration" data-key="${selected.key}" data-watts="${t2.target_watts}" style="${isTierActive(t2.target_watts) ? 'background:rgba(16,185,129,0.2);border-color:#10b981;color:#10b981;' : ''}">
        ${isTierActive(t2.target_watts) ? `✓ Active Goal (${t2.target_watts}W Synced to Program)` : `🎯 Set ${t2.target_watts}W as Active Goal`}
      </button>
    </div>

    <!-- Tier 3: Benchmark Ceiling -->
    <div class="planner-tier-card" style="${isTierActive(t3.target_watts) ? 'border-color:#10b981;box-shadow:0 0 12px rgba(16,185,129,0.2);' : ''}">
      <div class="tier-card-header">
        <span class="tier-title">${escapeSpiderwebHtml(t3.label)}</span>
        <span class="tier-delta-chip" style="color:#7C3AED;border-color:rgba(124,58,237,0.3);background:rgba(124,58,237,0.08);">
          +${t3.delta_watts}W (+${t3.delta_pct}%)
        </span>
      </div>
      <div class="tier-power-row">
        <span class="tier-target-watts" style="color:#7C3AED;">${t3.target_watts}W</span>
        <span style="font-size:0.85rem;color:var(--text-muted);">${t3.target_w_kg} W/kg</span>
      </div>
      <div class="tier-stimulus-text">
        <strong>Timeline:</strong> ${t3.timeline}<br>
        <strong>Peak Physiology:</strong> 100% outer radar benchmark cap.
      </div>
      <button type="button" class="btn-set-goal" data-type="duration" data-key="${selected.key}" data-watts="${t3.target_watts}" style="${isTierActive(t3.target_watts) ? 'background:rgba(16,185,129,0.2);border-color:#10b981;color:#10b981;' : ''}">
        ${isTierActive(t3.target_watts) ? `✓ Active Goal (${t3.target_watts}W Synced to Program)` : `🎯 Set ${t3.target_watts}W as Active Goal`}
      </button>
    </div>
  `;

  tiersContainer.querySelectorAll(".btn-set-goal").forEach(btn => {
    btn.addEventListener("click", async () => {
      const type = btn.dataset.type;
      const key = btn.dataset.key;
      const watts = parseInt(btn.dataset.watts, 10);
      const activeGoal = currentTargetAnalysisData?.active_goal;
      const isChanging = (!activeGoal || activeGoal.target_key !== key || activeGoal.target_watts !== watts);

      let resetBlock = false;
      if (isChanging) {
        resetBlock = confirm(
          `You are selecting a new duration target: ${key} @ ${watts}W.\n\nWould you like to reset your macrocycle block to Week 1 (8-week adaptation cycle)?\n\n• Click OK to reset the block to Week 1 (Base Phase)\n• Click Cancel to maintain your current block timeline`
        );
      }

      await submitSpiderwebGoal({
        goal_type: type,
        target_key: key,
        target_watts: watts,
        reset_block: resetBlock
      });
    });
  });
}

function renderPlannerPhenotypeView() {
  const container = document.getElementById("plannerPhenotypesGrid");
  if (!container || !currentTargetAnalysisData) return;

  const activeGoal = currentTargetAnalysisData.active_goal || null;
  const activePhenoKey = (activeGoal && activeGoal.goal_type === "phenotype") ? String(activeGoal.target_key || "").toLowerCase() : null;

  const phenotypes = currentTargetAnalysisData.rider_type_transformation_targets || [];
  container.innerHTML = phenotypes.map(p => {
    const isCurrent = p.is_current_type;
    const isGoalActive = activePhenoKey === String(p.id || "").toLowerCase();
    const badgeCls = isGoalActive
      ? "background:rgba(16,185,129,0.22);color:#10b981;border-color:#10b981;"
      : isCurrent
      ? "background:rgba(6,182,212,0.15);color:var(--accent-cyan);border-color:rgba(6,182,212,0.3);"
      : "background:rgba(16,185,129,0.15);color:#10b981;border-color:rgba(16,185,129,0.3);";
    const statusText = isGoalActive
      ? (p.total_delta_watts === 0 ? "🎯 Active Goal (100% Achieved)" : `🎯 Active Goal (${p.completion_pct}% Readiness • ${p.total_delta_watts}W gap)`)
      : isCurrent
      ? `🎯 Current Classification (${p.completion_pct}% Match)`
      : `${p.completion_pct}% Readiness (${p.total_delta_watts}W gap)`;

    const axesRows = (p.axis_gaps || []).map(ax => {
      const icon = ax.is_met ? "✓" : "▲";
      const valColor = ax.is_met ? "#10b981" : "#f59e0b";
      const deltaText = ax.is_met ? "Met" : `+${ax.delta_watts}W`;
      return `
        <div class="pheno-axis-row">
          <span>${ax.icon} ${escapeSpiderwebHtml(ax.name)}</span>
          <span style="color:${valColor};font-weight:700;">
            ${ax.target_watts}W <span style="font-weight:400;color:var(--text-muted);">(${icon} ${deltaText})</span>
          </span>
        </div>
      `;
    }).join("");

    return `
      <div class="planner-pheno-card ${isCurrent || isGoalActive ? 'selected' : ''}" style="${isGoalActive ? 'border-color:#10b981;box-shadow:0 0 12px rgba(16,185,129,0.2);' : ''}">
        <div class="planner-pheno-header">
          <span class="planner-pheno-title">${p.icon} ${escapeSpiderwebHtml(p.title)}</span>
          <span class="spiderweb-goal-badge" style="${badgeCls}">${statusText}</span>
        </div>
        <div class="planner-pheno-desc">${escapeSpiderwebHtml(p.description)}</div>
        <div class="planner-pheno-axes">
          <div style="font-weight:700;color:var(--text-muted);font-size:0.7rem;margin-bottom:0.15rem;">REQUIRED 5-AXIS ENVELOPE:</div>
          ${axesRows}
        </div>
        <div style="font-size:0.75rem;color:var(--text-muted);margin-top:0.25rem;">
          <strong>Prescribed Protocol:</strong> ${escapeSpiderwebHtml((p.recommended_workouts || [])[0] || '')}
        </div>
        <button type="button" class="btn-set-goal" data-type="phenotype" data-key="${p.id}" data-title="${escapeSpiderwebHtml(p.title)}" style="margin-top:0.5rem;${isGoalActive ? 'background:rgba(16,185,129,0.2);border-color:#10b981;color:#10b981;' : ''}">
          ${isGoalActive ? '✓ Active Goal (Synced to Macrocycle Program)' : '🎯 ' + (isCurrent ? 'Deepen Focus on ' + escapeSpiderwebHtml(p.title) + ' (+5% Specialty Overload)' : 'Transform to ' + escapeSpiderwebHtml(p.title))}
        </button>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".btn-set-goal").forEach(btn => {
    btn.addEventListener("click", async () => {
      const type = btn.dataset.type;
      const key = btn.dataset.key;
      const title = btn.dataset.title || key;

      const currentGoalKey = String(state.program?.goal_id || "").toLowerCase();
      const currentSpiderwebKey = String(state.power_spiderweb?.active_goal?.target_key || "").toLowerCase();
      const isChangingGoal = (key.toLowerCase() !== currentGoalKey && key.toLowerCase() !== currentSpiderwebKey);

      let resetBlock = false;
      if (isChangingGoal) {
        resetBlock = confirm(
          `You are changing your rider type goal to ${title}.\n\nWould you like to reset your macrocycle block to Week 1 (8-week adaptation cycle)?\n\n• Click OK to reset the block to Week 1 (Base Phase)\n• Click Cancel to maintain your current block timeline`
        );
      } else {
        resetBlock = confirm(
          `Reset macrocycle block to Week 1 (8-week adaptation cycle) for ${title}?`
        );
      }

      await submitSpiderwebGoal({
        goal_type: type,
        target_key: key,
        reset_block: resetBlock
      });
    });
  });
}

async function submitSpiderwebGoal(payload) {
  try {
    const res = await fetch("/api/power/spiderweb/goal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    hasSyncedInitialPlannerMode = false;
    showToast(`🎉 Active Goal & Macrocycle Synced: ${data.goal.target_title}!`);
    if (data.profile) {
      renderPowerSpiderweb(data.profile);
    } else {
      loadPowerSpiderweb(currentSpiderwebTimeframe);
    }
    if (data.program) {
      renderProgram(data.program);
    }
    await loadDashboard();
    await loadWorkout(state.currentDuration, state.currentIntensity);
    const card = document.getElementById("cardPowerSpiderweb");
    if (card) card.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    console.error("Failed to set spiderweb goal:", err);
    showToast("⚠️ Failed to set spiderweb goal");
  }
}

let whoopCollapsible = null;
let stravaCollapsible = null;
let coachTodayCollapsible = null;
let programCollapsible = null;
let upcomingPlanCollapsible = null;
let coachDebriefCollapsible = null;
let recentWorkoutsCollapsible = null;
let powerSpiderwebCollapsible = null;
let athleteCardCollapsible = null;
let archiveLibraryCollapsible = null;
let archiveEditorCollapsible = null;

// --- Main Dashboard View Switcher (Daily Training vs Long-Term Analysis vs Workout Archive) ---
let currentActiveMainView = "daily";

function switchMainDashboardView(targetView, updateHistory = true) {
  currentActiveMainView = (targetView === "analysis" || targetView === "archive" || targetView === "history") ? targetView : "daily";
  const tabDaily = document.getElementById("tabMainViewDaily");
  const tabAnalysis = document.getElementById("tabMainViewAnalysis");
  const tabArchive = document.getElementById("tabMainViewArchive");
  const tabHistory = document.getElementById("tabMainViewHistory");
  const paneDaily = document.getElementById("viewDailyContainer");
  const paneAnalysis = document.getElementById("viewAnalysisContainer");
  const paneArchive = document.getElementById("viewArchiveContainer");
  const paneHistory = document.getElementById("viewHistoryContainer");
  const toolbarTitle = document.getElementById("dashboardToolbarTitle");
  const dashboardToolbar = document.querySelector(".dashboard-toolbar");
  if (dashboardToolbar) {
    dashboardToolbar.style.display = (currentActiveMainView === "archive" || currentActiveMainView === "history") ? "none" : "";
  }

  const tabs = [
    { key: "daily", tab: tabDaily, pane: paneDaily },
    { key: "analysis", tab: tabAnalysis, pane: paneAnalysis },
    { key: "archive", tab: tabArchive, pane: paneArchive },
    { key: "history", tab: tabHistory, pane: paneHistory }
  ];

  tabs.forEach(({ key, tab, pane }) => {
    const isActive = key === currentActiveMainView;
    if (tab) {
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    }
    if (pane) {
      pane.classList.toggle("hidden-pane", !isActive);
      pane.style.display = isActive ? "block" : "none";
    }
  });

  if (currentActiveMainView === "analysis") {
    if (toolbarTitle) toolbarTitle.textContent = "📈 Long-Term Performance & Strategy";
    requestAnimationFrame(() => {
      if (typeof renderSpiderwebSvg === "function" && typeof currentSpiderwebData !== "undefined" && currentSpiderwebData && currentSpiderwebData.axes) {
        renderSpiderwebSvg(currentSpiderwebData.axes, currentSpiderwebData.active_goal);
      }
    });
  } else if (currentActiveMainView === "archive") {
    if (toolbarTitle) toolbarTitle.textContent = "📚 Workout Archive & Customizer";
    if (typeof loadWorkoutArchive === "function") {
      loadWorkoutArchive();
    }
    requestAnimationFrame(() => {
      if (typeof drawArchiveEditorCanvas === "function") {
        drawArchiveEditorCanvas();
      }
    });
  } else if (currentActiveMainView === "history") {
    if (toolbarTitle) toolbarTitle.textContent = "🗺️ Ride History & Explorer";
    if (typeof initRideHistoryTab === "function") {
      initRideHistoryTab();
    }
  } else {
    if (toolbarTitle) toolbarTitle.textContent = "⚡ Daily Training & Recovery";
    requestAnimationFrame(() => {
      if (state.currentWorkout && typeof drawWorkoutGraph === "function") {
        drawWorkoutGraph(state.currentWorkout);
      }
      if (typeof outdoorMap !== "undefined" && outdoorMap && typeof outdoorMap.invalidateSize === "function") {
        outdoorMap.invalidateSize(true);
      }
    });
  }

  try {
    localStorage.setItem("powersync_main_view", currentActiveMainView);
  } catch (_) {}

  if (updateHistory) {
    try {
      history.replaceState(null, "", `#${currentActiveMainView}`);
    } catch (_) {}
  }

  syncMasterToggleState();
}

function initMainViewSwitcher() {
  const tabDaily = document.getElementById("tabMainViewDaily");
  const tabAnalysis = document.getElementById("tabMainViewAnalysis");
  const tabArchive = document.getElementById("tabMainViewArchive");
  const tabHistory = document.getElementById("tabMainViewHistory");

  tabDaily?.addEventListener("click", () => switchMainDashboardView("daily"));
  tabAnalysis?.addEventListener("click", () => switchMainDashboardView("analysis"));
  tabArchive?.addEventListener("click", () => switchMainDashboardView("archive"));
  tabHistory?.addEventListener("click", () => switchMainDashboardView("history"));

  // Always default to opening on the Daily Training view ("daily") on startup
  const initialView = "daily";
  try {
    localStorage.setItem("powersync_main_view", "daily");
    if (window.location.hash && ["#analysis", "#archive", "#history"].includes(window.location.hash.toLowerCase())) {
      history.replaceState(null, "", "#daily");
    }
  } catch (_) {}

  switchMainDashboardView(initialView, false);

  // Cross-tab anchor navigation listener
  document.addEventListener("click", (e) => {
    const anchor = e.target.closest("a[href^='#']");
    if (!anchor) return;
    const href = anchor.getAttribute("href");
    if (["#cardPowerSpiderweb", "#cardProgram", "#cardAthlete"].includes(href)) {
      if (currentActiveMainView !== "analysis") {
        switchMainDashboardView("analysis", true);
      }
    } else if (["#cardWorkoutArchiveHeader", "#archiveEditorPanel"].includes(href)) {
      if (currentActiveMainView !== "archive") {
        switchMainDashboardView("archive", true);
      }
    } else if (["#cardWhoop", "#cardStrava", "#cardAiCoachToday", "#workoutStageSection", "#cardUpcomingPlan", "#cardCoachDebrief", "#cardRecentWorkouts"].includes(href)) {
      if (currentActiveMainView !== "daily") {
        switchMainDashboardView("daily", true);
      }
    }
  });

  window.addEventListener("hashchange", () => {
    const newHash = window.location.hash.toLowerCase();
    if (newHash.includes("analysis") || newHash.includes("spiderweb") || newHash.includes("program") || newHash.includes("athlete")) {
      if (currentActiveMainView !== "analysis") switchMainDashboardView("analysis", false);
    } else if (newHash.includes("archive")) {
      if (currentActiveMainView !== "archive") switchMainDashboardView("archive", false);
    } else if (newHash.includes("daily") || newHash.includes("today")) {
      if (currentActiveMainView !== "daily") switchMainDashboardView("daily", false);
    }
  });
}

function getAllCollapsiblesList() {
  if (currentActiveMainView === "analysis") {
    return [
      powerSpiderwebCollapsible,
      programCollapsible,
      athleteCardCollapsible
    ].filter(Boolean);
  }
  return [
    whoopCollapsible,
    stravaCollapsible,
    coachTodayCollapsible,
    upcomingPlanCollapsible,
    { isCollapsed: () => isWorkoutStageCollapsed(), setCollapsed: (c, cb, um) => setWorkoutStageCollapsed(c, cb, um) },
    coachDebriefCollapsible,
    recentWorkoutsCollapsible
  ].filter(Boolean);
}

function syncMasterToggleState() {
  const list = getAllCollapsiblesList();
  if (list.length === 0) return;
  const allCollapsed = list.every(c => c.isCollapsed());
  const icon = document.getElementById("toggleAllTilesIcon");
  const text = document.getElementById("toggleAllTilesText");
  const btn = document.getElementById("btnToggleAllTiles");
  if (icon) icon.textContent = allCollapsed ? "⊞" : "⊟";
  if (text) text.textContent = allCollapsed ? "Expand All" : "Collapse All";
  if (btn) {
    btn.setAttribute("aria-expanded", (!allCollapsed).toString());
    btn.title = allCollapsed ? "Expand all dashboard tiles" : "Collapse all dashboard tiles";
  }
}

function toggleAllTiles(forceState = null) {
  const list = getAllCollapsiblesList();
  if (list.length === 0) return;
  let targetCollapse;
  if (forceState !== null) {
    targetCollapse = forceState;
  } else {
    const anyExpanded = list.some(c => !c.isCollapsed());
    targetCollapse = anyExpanded; // if any expanded, collapse all
  }
  list.forEach(c => c.setCollapsed(targetCollapse, true, false));
  syncMasterToggleState();
}

function initMasterToggleAllTiles() {
  const btn = document.getElementById("btnToggleAllTiles");
  if (!btn) return;
  btn.addEventListener("click", () => {
    toggleAllTiles();
  });
}

function initAllCollapsibleTiles() {
  initWorkoutStageCollapsible();

  whoopCollapsible = setupCollapsibleTile({
    cardId: "cardWhoop",
    headerId: "whoopCardHeader",
    toggleBtnId: "btnToggleWhoopCard",
    toggleIconId: "whoopToggleIcon",
    toggleTextId: "whoopToggleText",
    storageKey: "whoopCardCollapsed"
  });

  stravaCollapsible = setupCollapsibleTile({
    cardId: "cardStrava",
    headerId: "stravaCardHeader",
    toggleBtnId: "btnToggleStravaCard",
    toggleIconId: "stravaToggleIcon",
    toggleTextId: "stravaToggleText",
    storageKey: "stravaCardCollapsed"
  });

  coachTodayCollapsible = setupCollapsibleTile({
    cardId: "cardAiCoachToday",
    headerId: "coachCardHeader",
    toggleBtnId: "btnToggleCoachCard",
    toggleIconId: "coachCardToggleIcon",
    toggleTextId: "coachCardToggleText",
    storageKey: "coachDirectiveCardCollapsed"
  });

  programCollapsible = setupCollapsibleTile({
    cardId: "cardProgram",
    headerId: "programCardHeader",
    toggleBtnId: "btnToggleProgramCard",
    toggleIconId: "programToggleIcon",
    toggleTextId: "programToggleText",
    storageKey: "programCardCollapsed"
  });

  upcomingPlanCollapsible = setupCollapsibleTile({
    cardId: "cardUpcomingPlan",
    headerId: "upcomingPlanHeader",
    toggleBtnId: "btnToggleUpcomingPlan",
    toggleIconId: "upcomingToggleIcon",
    toggleTextId: "upcomingToggleText",
    storageKey: "upcomingPlanCollapsed"
  });

  coachDebriefCollapsible = setupCollapsibleTile({
    cardId: "cardCoachDebrief",
    headerId: "coachDebriefHeader",
    toggleBtnId: "btnToggleCoachDebrief",
    toggleIconId: "coachDebriefToggleIcon",
    toggleTextId: "coachDebriefToggleText",
    storageKey: "coachDebriefCollapsed"
  });

  recentWorkoutsCollapsible = setupCollapsibleTile({
    cardId: "cardRecentWorkouts",
    headerId: "recentWorkoutsHeader",
    toggleBtnId: "btnToggleRecentWorkouts",
    toggleIconId: "recentWorkoutsToggleIcon",
    toggleTextId: "recentWorkoutsToggleText",
    storageKey: "recentWorkoutsCollapsed"
  });

  powerSpiderwebCollapsible = setupCollapsibleTile({
    cardId: "cardPowerSpiderweb",
    headerId: "powerSpiderwebHeader",
    toggleBtnId: "btnTogglePowerSpiderweb",
    toggleIconId: "powerSpiderwebToggleIcon",
    toggleTextId: "powerSpiderwebToggleText",
    storageKey: "powerSpiderwebCollapsed"
  });

  setupPowerSpiderwebTabs();

  athleteCardCollapsible = setupCollapsibleTile({
    cardId: "cardAthlete",
    headerId: "athleteCardHeader",
    toggleBtnId: "btnToggleAthleteCard",
    toggleIconId: "athleteToggleIcon",
    toggleTextId: "athleteToggleText",
    storageKey: "athleteCardCollapsed"
  });

  archiveLibraryCollapsible = setupCollapsibleTile({
    cardId: "cardWorkoutArchive",
    headerId: "archiveLibraryHeader",
    toggleBtnId: "btnToggleArchiveLibrary",
    toggleIconId: "archiveLibraryToggleIcon",
    toggleTextId: "archiveLibraryToggleText",
    storageKey: "archiveLibraryCollapsed"
  });

  archiveEditorCollapsible = setupCollapsibleTile({
    cardId: "archiveEditorPanel",
    headerId: "archiveEditorHeader",
    toggleBtnId: "btnToggleArchiveEditor",
    toggleIconId: "archiveEditorToggleIcon",
    toggleTextId: "archiveEditorToggleText",
    storageKey: "archiveEditorCollapsed",
    onToggle: (collapsed) => {
      if (!collapsed && typeof drawArchiveEditorCanvas === "function") {
        requestAnimationFrame(() => drawArchiveEditorCanvas());
      }
    }
  });

  // Jump link to full debrief auto-expands debrief tile if collapsed
  const coachJumpLink = document.getElementById("coachCardJumpLink");
  if (coachJumpLink) {
    coachJumpLink.addEventListener("click", () => {
      const coachCard = document.getElementById("cardCoachDebrief");
      if (coachCard && coachCard.classList.contains("collapsed")) {
        coachDebriefCollapsible?.setCollapsed(false);
      }
    });
  }

  initMasterToggleAllTiles();
  initMainViewSwitcher();
  initConnectionsDropdown();
  syncMasterToggleState();
}

// --- Multi-User Athlete Authentication & Google Sign-In ---
let currentAthleteUser = null;
let isGoogleOauthConfigured = false;
let primaryOwnerInfo = { is_locked: false, owner_email: null };

async function checkAuthStatus() {
  try {
    const [meRes, googleRes, ownerRes] = await Promise.all([
      fetch("/api/auth/me"),
      fetch("/api/auth/google/status").catch(() => null),
      fetch("/api/auth/owner-status").catch(() => null)
    ]);
    if (ownerRes && ownerRes.ok) {
      primaryOwnerInfo = await ownerRes.json();
    }
    if (googleRes && googleRes.ok) {
      const gData = await googleRes.json();
      isGoogleOauthConfigured = !!gData.configured;
    }
    if (meRes.ok) {
      let user = await meRes.json();
      currentAthleteUser = user;
      renderUserNavPill(user);
    }
    const isAuth = Boolean(currentAthleteUser && !currentAthleteUser.is_guest);
    applyAuthVisibility(isAuth);
    renderAuthModalContent(currentAthleteUser);
  } catch (e) {
    console.warn("Failed to check auth status:", e);
  }
}

function applyAuthVisibility(isAuthUser) {
  const gateEl = document.getElementById("unauthenticatedGate");
  const dailyViewEl = document.getElementById("viewDailyContainer");
  const analysisViewEl = document.getElementById("viewAnalysisContainer");
  const toolbarEl = document.querySelector(".dashboard-toolbar");
  const demoBannerEl = document.getElementById("demoModeBanner");
  const switcherEl = document.querySelector(".main-view-switcher");
  const gateGoogleSec = document.getElementById("gateGoogleSection");

  if (gateGoogleSec) {
    gateGoogleSec.style.display = isGoogleOauthConfigured ? "block" : "none";
  }

  const gateClaimLabel = document.getElementById("gateClaimLabel");
  const chkGateClaim = document.getElementById("chkGateClaimPrimary");
  if (gateClaimLabel) {
    if (primaryOwnerInfo && primaryOwnerInfo.is_locked) {
      gateClaimLabel.style.display = "none";
      if (chkGateClaim) chkGateClaim.checked = false;
    } else {
      gateClaimLabel.style.display = "flex";
    }
  }

  if (isAuthUser) {
    if (gateEl) gateEl.style.display = "none";
    if (switcherEl) switcherEl.style.display = "flex";
    if (toolbarEl) toolbarEl.style.display = "flex";
    const activeTab = document.querySelector(".main-view-tab-btn.active");
    const activeView = activeTab ? activeTab.getAttribute("data-view") : "daily";
    if (activeView === "analysis") {
      if (dailyViewEl) dailyViewEl.style.display = "none";
      if (analysisViewEl) analysisViewEl.style.display = "block";
    } else {
      if (dailyViewEl) dailyViewEl.style.display = "block";
      if (analysisViewEl) analysisViewEl.style.display = "none";
    }
  } else {
    if (gateEl) gateEl.style.display = "block";
    if (switcherEl) switcherEl.style.display = "none";
    if (toolbarEl) toolbarEl.style.display = "none";
    if (dailyViewEl) dailyViewEl.style.display = "none";
    if (analysisViewEl) analysisViewEl.style.display = "none";
    if (demoBannerEl) demoBannerEl.style.display = "none";
  }
}

function renderUserNavPill(user) {
  const avatarEl = document.getElementById("navUserAvatar");
  const nameEl = document.getElementById("navUserName");
  if (!user || user.is_guest) {
    if (avatarEl) avatarEl.textContent = "👤";
    if (nameEl) nameEl.textContent = "Sign In";
  } else {
    if (avatarEl) {
      if (user.picture) {
        avatarEl.innerHTML = `<img src="${user.picture}" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
      } else {
        const initials = (user.name || user.email || "U").substring(0, 2).toUpperCase();
        avatarEl.textContent = initials;
      }
    }
    if (nameEl) {
      nameEl.textContent = user.name || (user.email ? user.email.split("@")[0] : "Athlete");
    }
  }
}

function renderAuthModalContent(user) {
  const profileCard = document.getElementById("authProfileCard");
  const primaryDirectCard = document.getElementById("authPrimaryDirectCard");
  const avatarEl = document.getElementById("authProfileAvatar");
  const nameEl = document.getElementById("authProfileName");
  const emailEl = document.getElementById("authProfileEmail");
  const profileBadge = document.getElementById("authProfileBadge");
  const googleBtnText = document.querySelector("#btnGoogleSignIn span");
  const googleNotice = document.getElementById("googleConfigNotice");
  const chkClaimPrimary = document.getElementById("chkClaimPrimary");
  const chkClaimLabel = chkClaimPrimary ? chkClaimPrimary.closest("label") : null;

  // Google config alert
  if (googleNotice) {
    googleNotice.style.display = isGoogleOauthConfigured ? "none" : "block";
  }

  // Owner lock check: if locked to a specific email, hide the claim primary checkbox from random users
  if (chkClaimLabel) {
    if (primaryOwnerInfo && primaryOwnerInfo.is_locked && primaryOwnerInfo.owner_email) {
      const isOwnerNow = user && (user.id === "usr_default" || user.email === primaryOwnerInfo.owner_email);
      chkClaimLabel.style.display = isOwnerNow ? "flex" : "none";
      if (!isOwnerNow && chkClaimPrimary) chkClaimPrimary.checked = false;
    } else {
      chkClaimLabel.style.display = "flex";
    }
  }

  if (user && !user.is_guest) {
    if (profileCard) profileCard.style.display = "flex";
    if (primaryDirectCard) {
      primaryDirectCard.style.display = (user.id === "usr_default") ? "none" : "flex";
    }
    if (nameEl) nameEl.textContent = user.name || "Athlete";
    if (emailEl) emailEl.textContent = user.email || "";
    if (profileBadge) {
      if (user.id === "usr_default") {
        profileBadge.textContent = "⭐ Account Owner (Intervals.icu & Saved History)";
        profileBadge.style.color = "#06b6d4";
      } else {
        profileBadge.textContent = "🔒 Private Isolated Athlete Profile";
        profileBadge.style.color = "#10b981";
      }
    }
    if (avatarEl) {
      if (user.picture) {
        avatarEl.innerHTML = `<img src="${user.picture}" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
      } else {
        const initials = (user.name || user.email || "U").substring(0, 2).toUpperCase();
        avatarEl.textContent = initials;
      }
    }
    if (googleBtnText) googleBtnText.textContent = "Switch Google Account";
  } else {
    if (profileCard) profileCard.style.display = "none";
    if (primaryDirectCard) primaryDirectCard.style.display = "flex";
    if (googleBtnText) googleBtnText.textContent = "Continue with Google";
  }
}

const authModal = document.getElementById("authModal");
const btnUserAccount = document.getElementById("btnUserAccount");
const btnCloseAuthModal = document.getElementById("btnCloseAuthModal");

function openAuthModal() {
  if (authModal) authModal.classList.add("open");
  checkAuthStatus();
}

function closeAuthModal() {
  if (authModal) authModal.classList.remove("open");
}

if (btnUserAccount) btnUserAccount.addEventListener("click", openAuthModal);
if (btnCloseAuthModal) btnCloseAuthModal.addEventListener("click", closeAuthModal);
if (authModal) {
  authModal.addEventListener("click", (e) => {
    if (e.target === authModal) closeAuthModal();
  });
}

const linkOpenGoogleSettings = document.getElementById("linkOpenGoogleSettings");
if (linkOpenGoogleSettings) {
  linkOpenGoogleSettings.addEventListener("click", (e) => {
    e.preventDefault();
    closeAuthModal();
    openSettingsModal();
    setTimeout(() => {
      document.getElementById("settingGoogleClientId")?.focus();
    }, 300);
  });
}

const btnGoogleSignIn = document.getElementById("btnGoogleSignIn");
if (btnGoogleSignIn) {
  btnGoogleSignIn.addEventListener("click", (e) => {
    if (!isGoogleOauthConfigured) {
      e.preventDefault();
      showToast("⚙️ Google Sign-In needs Client ID & Secret. Opening Settings...");
      closeAuthModal();
      openSettingsModal();
      setTimeout(() => {
        document.getElementById("settingGoogleClientId")?.focus();
      }, 300);
    }
  });
}

const btnPrimaryAthleteLogin = document.getElementById("btnPrimaryAthleteLogin");
if (btnPrimaryAthleteLogin) {
  btnPrimaryAthleteLogin.addEventListener("click", async () => {
    try {
      showToast("Signing in as Primary Athlete (Account Owner)...");
      const res = await fetch("/api/auth/primary-login", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.session_token) {
          localStorage.setItem("powersync_token", data.session_token);
        }
        showToast("Signed in as Primary Athlete! Reloading...");
        setTimeout(() => { window.location.reload(); }, 400);
      } else {
        showToast("Failed to authenticate as primary athlete.");
      }
    } catch (e) {
      showToast("Error signing in.");
    }
  });
}

const btnSignOut = document.getElementById("btnSignOut");
if (btnSignOut) {
  btnSignOut.addEventListener("click", async () => {
    try {
      localStorage.removeItem("powersync_token");
      await fetch("/api/auth/logout", { method: "POST" });
      showToast("Signed out. Refreshing session...");
      setTimeout(() => { window.location.reload(); }, 400);
    } catch (e) {
      localStorage.removeItem("powersync_token");
      window.location.reload();
    }
  });
}

const btnClaimDefaultData = document.getElementById("btnClaimDefaultData");
if (btnClaimDefaultData) {
  btnClaimDefaultData.addEventListener("click", async () => {
    try {
      showToast("📥 Importing default athlete settings & history...");
      const res = await fetch("/api/auth/claim-default-data", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        showToast("✅ Settings and history imported! Reloading...");
        setTimeout(() => { window.location.reload(); }, 600);
      } else {
        showToast("⚠️ Could not import default settings.");
      }
    } catch (err) {
      showToast("Error importing data.");
    }
  });
}

document.querySelectorAll(".btn-dev-switch").forEach(btn => {
  btn.addEventListener("click", async () => {
    const email = btn.getAttribute("data-email");
    const name = btn.getAttribute("data-name");
    await performEmailLogin(email, name, false);
  });
});

const formEmailLogin = document.getElementById("formEmailLogin");
const inputAthleteEmail = document.getElementById("inputAthleteEmail");
const inputAthleteName = document.getElementById("inputAthleteName");
const chkClaimPrimary = document.getElementById("chkClaimPrimary");

if (formEmailLogin) {
  formEmailLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = inputAthleteEmail ? inputAthleteEmail.value.trim() : "";
    const name = inputAthleteName ? inputAthleteName.value.trim() : "";
    const claimPrimary = chkClaimPrimary ? chkClaimPrimary.checked : false;

    if (!email || !email.includes("@")) {
      showToast("Please enter a valid email address.");
      return;
    }
    await performEmailLogin(email, name, claimPrimary);
  });
}

// Landing Gate Email Login Handler
const formGateEmailLogin = document.getElementById("formGateEmailLogin");
const inputGateEmail = document.getElementById("inputGateEmail");
const inputGateName = document.getElementById("inputGateName");
const chkGateClaimPrimary = document.getElementById("chkGateClaimPrimary");

if (formGateEmailLogin) {
  formGateEmailLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = inputGateEmail ? inputGateEmail.value.trim() : "";
    const name = inputGateName ? inputGateName.value.trim() : "";
    const claimPrimary = chkGateClaimPrimary ? chkGateClaimPrimary.checked : false;

    if (!email || !email.includes("@")) {
      showToast("Please enter a valid email address.");
      return;
    }
    await performEmailLogin(email, name, claimPrimary);
  });
}

// Delegate all dev-switch clicks (handles dynamically rendered and gate buttons)
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".btn-dev-switch");
  if (btn) {
    const email = btn.getAttribute("data-email");
    const name = btn.getAttribute("data-name");
    if (email) {
      await performEmailLogin(email, name, false);
    }
  }
});

const btnDevLoginSubmit = document.getElementById("btnDevLoginSubmit");
const inputDevLoginEmail = document.getElementById("inputDevLoginEmail");
if (btnDevLoginSubmit && inputDevLoginEmail) {
  btnDevLoginSubmit.addEventListener("click", async () => {
    const email = inputDevLoginEmail.value.trim();
    if (!email) {
      showToast("Please enter an email address.");
      return;
    }
    await performEmailLogin(email, email.split("@")[0], false);
  });
}

async function performEmailLogin(email, name, claimPrimary = false) {
  try {
    showToast(`Signing in as ${name || email}...`);
    const res = await fetch("/api/auth/email-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        name: name || undefined,
        claim_primary: claimPrimary
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (data.session_token) {
        localStorage.setItem("powersync_token", data.session_token);
      }
      showToast(`Authenticated as ${data.user?.name || email}! Reloading...`);
      setTimeout(() => { window.location.reload(); }, 400);
    } else {
      showToast(data.detail || "Authentication failed.");
    }
  } catch (err) {
    showToast("Error connecting to login server.");
  }
}

async function performDevLogin(email, name) {
  return performEmailLogin(email, name, false);
}

const btnSaveOwnerLock = document.getElementById("btnSaveOwnerLock");
if (btnSaveOwnerLock) {
  btnSaveOwnerLock.addEventListener("click", async () => {
    const email = document.getElementById("settingPrimaryOwnerEmail")?.value.trim();
    if (!email || !email.includes("@")) {
      showToast("Please enter a valid owner email address.");
      return;
    }
    try {
      showToast(`Locking primary athlete to ${email}...`);
      const res = await fetch("/api/auth/lock-owner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast(`🔒 Primary account locked to ${email}`);
        await checkAuthStatus();
        const ownerPill = document.getElementById("ownerLockStatusPill");
        if (ownerPill) {
          ownerPill.textContent = "Lock Active";
          ownerPill.style.background = "rgba(16,185,129,0.15)";
          ownerPill.style.color = "#10b981";
        }
      } else {
        showToast(data.detail || "Could not lock account.");
      }
    } catch (e) {
      showToast("Error locking account.");
    }
  });
}

const btnCopyGoogleRedirect = document.getElementById("btnCopyGoogleRedirect");
if (btnCopyGoogleRedirect) {
  btnCopyGoogleRedirect.addEventListener("click", () => {
    const origin = window.location.origin;
    navigator.clipboard.writeText(`${origin}/api/auth/google/callback`);
    showToast("📋 Redirect URI copied to clipboard!");
  });
}

// Initial boot
async function bootApp() {
  try {
    initThemeSystem();
    initPullToReload();
    initAllCollapsibleTiles();
  } catch (e) {
    console.warn("Init UI error:", e);
  }

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("reload")) {
    try {
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (_) {}
  }
  const sessionTokenParam = urlParams.get("session_token");
  if (sessionTokenParam) {
    localStorage.setItem("powersync_token", sessionTokenParam);
  }
  if (urlParams.get("login_success")) {
    showToast("🎉 Signed in successfully! Welcome to PowerSync.");
    try {
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (_) {}
  } else if (urlParams.get("auth_error")) {
    showToast(`⚠️ Authentication: ${urlParams.get("auth_error")}`);
    try {
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (_) {}
  }
  if (urlParams.get("strava_connected")) {
    showToast("🎉 Strava connected successfully!");
    try {
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (_) {}
    await fetch("/api/settings", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ demo_mode: false }) }).catch(() => {});
  } else if (urlParams.get("whoop_connected")) {
    showToast("🎉 Whoop connected successfully!");
    try {
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (_) {}
    await fetch("/api/settings", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ demo_mode: false }) }).catch(() => {});
  }

  try {
    await checkAuthStatus();
  } catch (e) {
    console.warn("Auth check error in bootApp:", e);
  }

  const isAuthUser = Boolean(currentAthleteUser && !currentAthleteUser.is_guest);
  applyAuthVisibility(isAuthUser);

  try {
    await loadVersionInfo();
  } catch (e) {
    console.warn("Version load error in bootApp:", e);
  }

  if (!isAuthUser) {
    // Unauthenticated visitor: hide all athlete data and do not load private resources
    return;
  }

  try {
    await loadDashboard();
  } catch (e) {
    console.warn("Dashboard load error in bootApp:", e);
  }

  try {
    await checkCoachGeminiStatus();
  } catch (e) {
    console.warn("Gemini check error in bootApp:", e);
  }

  try {
    applyTheme("dark", false);
    if (isAuthUser) {
      const sRes = await fetch("/api/settings");
      if (sRes.ok) {
        const s = await sRes.json();
        state.googleMapsApiKey = s.google_maps_api_key_set ? "saved" : "";
        if (s.preferred_map_layer && ["google_roads", "google_hybrid", "google_terrain"].includes(s.preferred_map_layer)) {
          outdoorBaseLayerName = s.preferred_map_layer;
        } else {
          outdoorBaseLayerName = "google_roads";
        }
        const selectElem = document.getElementById("selectMapBaseLayer");
        if (selectElem) selectElem.value = outdoorBaseLayerName;
        if (outdoorMap) applyBaseTileLayer(outdoorBaseLayerName);
      }
    }
  } catch (err) {
    console.warn("Failed to load settings in bootApp:", err);
  }

  try {
    await loadUpcomingPlan();
  } catch (e) {
    console.warn("Upcoming plan load error in bootApp:", e);
  }

  try {
    await loadWorkout(null, 0, "");
  } catch (e) {
    console.error("Workout generation error in bootApp:", e);
  }

  try {
    await loadDebrief();
  } catch (e) {
    console.warn("Debrief load error in bootApp:", e);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootApp);
} else {
  bootApp();
}

// Auto-sync biometrics when athlete switches back into PowerSync (e.g. from Whoop or Strava app)
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    const now = Date.now();
    if ((now - (state.lastWhoopAutoSyncTime || 0)) > 60000 || (now - (state.lastStravaAutoSyncTime || 0)) > 60000) {
      loadDashboard();
    }
  }
});
window.addEventListener("focus", () => {
  const now = Date.now();
  if ((now - (state.lastWhoopAutoSyncTime || 0)) > 60000 || (now - (state.lastStravaAutoSyncTime || 0)) > 60000) {
    loadDashboard();
  }
});

// ==========================================================================
// WORKOUT ARCHIVE & CUSTOMIZER MODULE
// ==========================================================================

const archiveState = {
  ftp: 250,
  priorWorkouts: [],
  libraryWorkouts: [],
  filter: "all",
  search: "",
  durationFilter: "all",
  libraryDuration: 60,
  editingWorkout: null,
  initialized: false
};

function _archiveZoneColor(pct) {
  if (pct < 56) return "#94A3B8";      // Z1 Recovery
  if (pct < 76) return "#3B82F6";      // Z2 Endurance
  if (pct < 88) return "#10B981";      // Z3 Tempo
  if (pct < 95) return "#F59E0B";      // Sweet Spot
  if (pct < 106) return "#F97316";     // Z4 Threshold
  if (pct < 121) return "#EF4444";     // Z5 VO2 Max
  return "#EC4899";                    // Z6/Z7 Anaerobic/Sprint
}

function _buildIntervalSparklineSvg(intervals) {
  if (!Array.isArray(intervals) || intervals.length === 0) {
    return `<svg viewBox="0 0 200 36" width="100%" height="36" preserveAspectRatio="none"><line x1="0" y1="32" x2="200" y2="32" stroke="rgba(148,163,184,0.35)" stroke-width="2"/></svg>`;
  }
  const segs = [];
  let totalSec = 0;
  intervals.forEach(item => {
    const t = String(item.type || "SteadyState").toLowerCase();
    if (t === "repeats" || t === "intervalblock" || t === "intervals") {
      const rep = Math.max(1, parseInt(item.repeat || 1, 10));
      const onD = Math.max(1, parseInt(item.on_duration_sec || 60, 10));
      const offD = Math.max(1, parseInt(item.off_duration_sec || 60, 10));
      const onP = Number(item.on_power_pct || 95);
      const offP = Number(item.off_power_pct || 55);
      for (let i = 0; i < rep; i++) {
        segs.push({ dur: onD, p1: onP, p2: onP });
        segs.push({ dur: offD, p1: offP, p2: offP });
        totalSec += onD + offD;
      }
    } else if (t === "warmup" || t === "cooldown" || t === "ramp") {
      const d = Math.max(1, parseInt(item.duration_sec || 300, 10));
      segs.push({ dur: d, p1: Number(item.power_low_pct || 50), p2: Number(item.power_high_pct || 75) });
      totalSec += d;
    } else {
      const d = Math.max(1, parseInt(item.duration_sec || 300, 10));
      const p = Number(item.power_pct || 65);
      segs.push({ dur: d, p1: p, p2: p });
      totalSec += d;
    }
  });
  if (totalSec <= 0) totalSec = 1;
  const maxP = 140;
  let x = 0;
  const shapes = segs.map(s => {
    const w = (s.dur / totalSec) * 200;
    const h1 = Math.min(34, Math.max(3, (s.p1 / maxP) * 34));
    const h2 = Math.min(34, Math.max(3, (s.p2 / maxP) * 34));
    const y1 = 36 - h1;
    const y2 = 36 - h2;
    const avgP = (s.p1 + s.p2) / 2;
    const col = _archiveZoneColor(avgP);
    const pts = `${x.toFixed(2)},36 ${x.toFixed(2)},${y1.toFixed(2)} ${(x + w).toFixed(2)},${y2.toFixed(2)} ${(x + w).toFixed(2)},36`;
    x += w;
    return `<polygon points="${pts}" fill="${col}" fill-opacity="0.82"/>`;
  }).join("");
  return `<svg viewBox="0 0 200 36" width="100%" height="36" preserveAspectRatio="none">${shapes}</svg>`;
}

function drawArchiveEditorCanvas() {
  const canvas = document.getElementById("archiveEditorCanvas");
  if (!canvas || !archiveState.editingWorkout) return;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(280, Math.round(rect.width || 380));
  const height = 145;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const intervals = archiveState.editingWorkout.intervals || [];
  const ftp = archiveState.ftp || 250;
  const segs = [];
  let totalSec = 0;
  intervals.forEach(item => {
    const t = String(item.type || "SteadyState").toLowerCase();
    if (t === "repeats" || t === "intervalblock" || t === "intervals") {
      const rep = Math.max(1, parseInt(item.repeat || 1, 10));
      const onD = Math.max(1, parseInt(item.on_duration_sec || 60, 10));
      const offD = Math.max(1, parseInt(item.off_duration_sec || 60, 10));
      const onP = Number(item.on_power_pct || 95);
      const offP = Number(item.off_power_pct || 55);
      for (let i = 0; i < rep; i++) {
        segs.push({ dur: onD, p1: onP, p2: onP });
        segs.push({ dur: offD, p1: offP, p2: offP });
        totalSec += onD + offD;
      }
    } else if (t === "warmup" || t === "cooldown" || t === "ramp") {
      const d = Math.max(1, parseInt(item.duration_sec || 300, 10));
      segs.push({ dur: d, p1: Number(item.power_low_pct || 50), p2: Number(item.power_high_pct || 75) });
      totalSec += d;
    } else {
      const d = Math.max(1, parseInt(item.duration_sec || 300, 10));
      const p = Number(item.power_pct || 65);
      segs.push({ dur: d, p1: p, p2: p });
      totalSec += d;
    }
  });

  if (totalSec <= 0) return;

  const padL = 6, padR = 6, padT = 14, padB = 18;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const maxPct = Math.max(125, ...segs.map(s => Math.max(s.p1, s.p2) + 10));

  // FTP reference line
  const ftpY = padT + plotH - (100 / maxPct) * plotH;
  ctx.strokeStyle = "rgba(255, 94, 0, 0.45)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(padL, ftpY);
  ctx.lineTo(padL + plotW, ftpY);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(255, 94, 0, 0.85)";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText(`FTP ${ftp}W`, padL + 4, Math.max(10, ftpY - 3));

  let curX = padL;
  segs.forEach(s => {
    const segW = (s.dur / totalSec) * plotW;
    const y1 = padT + plotH - (s.p1 / maxPct) * plotH;
    const y2 = padT + plotH - (s.p2 / maxPct) * plotH;
    const baseY = padT + plotH;
    ctx.fillStyle = _archiveZoneColor((s.p1 + s.p2) / 2);
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.moveTo(curX, baseY);
    ctx.lineTo(curX, y1);
    ctx.lineTo(curX + segW, y2);
    ctx.lineTo(curX + segW, baseY);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1.0;
    curX += segW;
  });

  // Bottom time label
  ctx.fillStyle = "rgba(100, 116, 139, 0.9)";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText("0m", padL, height - 4);
  const totalMin = Math.round(totalSec / 60);
  ctx.fillText(`${totalMin}m`, padL + plotW - 26, height - 4);
}

function _updateArchiveMetricsStrip(w) {
  const durEl = document.getElementById("archiveMetricDur");
  const npEl = document.getElementById("archiveMetricNP");
  const ifEl = document.getElementById("archiveMetricIF");
  const tssEl = document.getElementById("archiveMetricTSS");
  const xssEl = document.getElementById("archiveMetricXSS");
  if (durEl) durEl.textContent = `${w.duration_minutes || 0}m`;
  if (npEl) npEl.textContent = w.normalized_power_watts ? `${w.normalized_power_watts} W` : "-- W";
  if (ifEl) ifEl.textContent = w.intensity_factor ? Number(w.intensity_factor).toFixed(2) : "--";
  if (tssEl) tssEl.textContent = w.estimated_tss != null ? `${w.estimated_tss}` : "--";
  if (xssEl) xssEl.textContent = w.total_xss != null ? `${Math.round(w.total_xss)}` : "--";
}

async function previewArchiveEditor(options = {}) {
  if (!archiveState.editingWorkout) return;
  const w = archiveState.editingWorkout;
  const titleInput = document.getElementById("archiveEditTitle");
  const notesInput = document.getElementById("archiveEditNotes");
  if (titleInput) w.title = titleInput.value.trim() || "Custom Workout";
  if (notesInput) w.ai_rationale = notesInput.value.trim();

  try {
    const res = await fetch("/api/workouts/archive/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: w.title,
        ai_rationale: w.ai_rationale || "",
        intervals: w.intervals || [],
        duration_minutes: options.duration_minutes || null,
        intensity_adjust_pct: options.intensity_adjust_pct || 0
      })
    });
    const data = await res.json();
    if (data.success && data.workout) {
      archiveState.ftp = data.ftp || archiveState.ftp;
      w.intervals = data.workout.intervals;
      w.duration_minutes = data.workout.duration_minutes;
      w.normalized_power_watts = data.workout.normalized_power_watts;
      w.intensity_factor = data.workout.intensity_factor;
      w.estimated_tss = data.workout.estimated_tss;
      w.total_xss = data.workout.total_xss;
      w.low_xss = data.workout.low_xss;
      w.high_xss = data.workout.high_xss;
      w.peak_xss = data.workout.peak_xss;
      w.zwo_content = data.workout.zwo_content;
      w.intervals_icu_text = data.workout.intervals_icu_text;

      const durInput = document.getElementById("archiveReconcileDur");
      if (durInput && w.duration_minutes) durInput.value = w.duration_minutes;
      _updateArchiveMetricsStrip(w);
      drawArchiveEditorCanvas();
      if (options.reRenderRows) renderArchiveEditorIntervals();
    }
  } catch (e) {
    console.warn("Preview archive workout failed:", e);
  }
}

function renderArchiveEditorIntervals() {
  const container = document.getElementById("archiveIntervalRows");
  if (!container || !archiveState.editingWorkout) return;
  const intervals = archiveState.editingWorkout.intervals || [];
  if (intervals.length === 0) {
    container.innerHTML = `<div style="font-size:0.78rem;color:var(--text-muted);padding:0.5rem;">No intervals yet. Click "+ Add Step" to build your workout.</div>`;
    return;
  }

  container.innerHTML = intervals.map((item, idx) => {
    const segType = String(item.type || "SteadyState");
    const lower = segType.toLowerCase();
    let fieldsHtml = "";

    if (lower === "repeats" || lower === "intervalblock" || lower === "intervals") {
      fieldsHtml = `
        <input type="number" title="Repeats" min="1" max="50" value="${item.repeat || 3}" data-idx="${idx}" data-field="repeat" style="width:46px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">x</span>
        <input type="number" title="On (sec)" min="5" max="3600" value="${item.on_duration_sec || 120}" data-idx="${idx}" data-field="on_duration_sec" style="width:54px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">s @</span>
        <input type="number" title="On % FTP" min="35" max="250" value="${item.on_power_pct || 95}" data-idx="${idx}" data-field="on_power_pct" style="width:48px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">% /</span>
        <input type="number" title="Off (sec)" min="5" max="3600" value="${item.off_duration_sec || 60}" data-idx="${idx}" data-field="off_duration_sec" style="width:54px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">s @</span>
        <input type="number" title="Off % FTP" min="35" max="150" value="${item.off_power_pct || 55}" data-idx="${idx}" data-field="off_power_pct" style="width:48px;" />%
      `;
    } else if (lower === "warmup" || lower === "cooldown" || lower === "ramp") {
      const mins = Math.round((item.duration_sec || 300) / 60);
      fieldsHtml = `
        <input type="number" title="Minutes" min="1" max="180" value="${mins}" data-idx="${idx}" data-field="duration_min" style="width:48px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">m</span>
        <input type="number" title="Start % FTP" min="35" max="200" value="${item.power_low_pct || 50}" data-idx="${idx}" data-field="power_low_pct" style="width:48px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">→</span>
        <input type="number" title="End % FTP" min="35" max="200" value="${item.power_high_pct || 75}" data-idx="${idx}" data-field="power_high_pct" style="width:48px;" />%
      `;
    } else {
      const mins = Math.round((item.duration_sec || 300) / 60);
      fieldsHtml = `
        <input type="number" title="Minutes" min="1" max="240" value="${mins}" data-idx="${idx}" data-field="duration_min" style="width:48px;" />
        <span style="font-size:0.7rem;color:var(--text-muted);">m @</span>
        <input type="number" title="% FTP" min="35" max="220" value="${item.power_pct || 75}" data-idx="${idx}" data-field="power_pct" style="width:50px;" />%
      `;
    }

    return `
      <div class="archive-interval-row">
        <select data-idx="${idx}" data-field="type">
          <option value="Warmup" ${lower === "warmup" ? "selected" : ""}>Warmup</option>
          <option value="SteadyState" ${lower === "steadystate" ? "selected" : ""}>Steady</option>
          <option value="Repeats" ${lower === "repeats" || lower === "intervalblock" || lower === "intervals" ? "selected" : ""}>Repeats</option>
          <option value="Ramp" ${lower === "ramp" ? "selected" : ""}>Ramp</option>
          <option value="Cooldown" ${lower === "cooldown" ? "selected" : ""}>Cooldown</option>
        </select>
        <div class="archive-interval-fields">
          ${fieldsHtml}
          <button type="button" class="btn btn-secondary btn-xs" data-action="up" data-idx="${idx}" title="Move Up">↑</button>
          <button type="button" class="btn btn-secondary btn-xs" data-action="down" data-idx="${idx}" title="Move Down">↓</button>
          <button type="button" class="btn btn-secondary btn-xs" data-action="remove" data-idx="${idx}" title="Delete Step">✕</button>
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll("select, input").forEach(el => {
    el.addEventListener("change", () => {
      const idx = parseInt(el.dataset.idx, 10);
      const field = el.dataset.field;
      const item = archiveState.editingWorkout.intervals[idx];
      if (!item) return;

      if (field === "type") {
        const newT = el.value;
        if (newT === "Repeats") {
          archiveState.editingWorkout.intervals[idx] = {
            type: "Repeats", repeat: 4, on_duration_sec: 120, off_duration_sec: 60, on_power_pct: 105, off_power_pct: 55, cadence: 95, name: "4x Intervals"
          };
        } else if (newT === "Warmup" || newT === "Cooldown" || newT === "Ramp") {
          archiveState.editingWorkout.intervals[idx] = {
            type: newT,
            duration_sec: item.duration_sec || 300,
            power_low_pct: newT === "Cooldown" ? 65 : 45,
            power_high_pct: newT === "Cooldown" ? 40 : 75,
            cadence: 88,
            name: newT
          };
        } else {
          archiveState.editingWorkout.intervals[idx] = {
            type: "SteadyState",
            duration_sec: item.duration_sec || 300,
            power_pct: item.power_pct || 75,
            cadence: 90,
            name: "Steady Block"
          };
        }
        renderArchiveEditorIntervals();
        previewArchiveEditor();
        return;
      }

      const val = Number(el.value);
      if (field === "duration_min") {
        item.duration_sec = Math.max(60, Math.round(val * 60));
      } else {
        item[field] = val;
      }
      previewArchiveEditor();
    });
  });

  container.querySelectorAll("button[data-action]").forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.dataset.idx, 10);
      const act = btn.dataset.action;
      const arr = archiveState.editingWorkout.intervals;
      if (act === "remove") {
        arr.splice(idx, 1);
      } else if (act === "up" && idx > 0) {
        [arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
      } else if (act === "down" && idx < arr.length - 1) {
        [arr[idx + 1], arr[idx]] = [arr[idx], arr[idx + 1]];
      }
      renderArchiveEditorIntervals();
      previewArchiveEditor();
    });
  });
}

function openArchiveEditor(workout) {
  const clone = JSON.parse(JSON.stringify(workout));
  archiveState.editingWorkout = clone;

  const titleInput = document.getElementById("archiveEditTitle");
  const dateInput = document.getElementById("archiveEditDate");
  const notesInput = document.getElementById("archiveEditNotes");
  const sourceLbl = document.getElementById("archiveEditorSourceLabel");
  const durInput = document.getElementById("archiveReconcileDur");

  if (titleInput) titleInput.value = clone.title || "Custom Workout";
  if (dateInput) {
    const todayIso = new Date().toISOString().slice(0, 10);
    dateInput.value = (clone.date && clone.date.length >= 10) ? clone.date.slice(0, 10) : todayIso;
  }
  if (notesInput) notesInput.value = clone.ai_rationale || clone.description || "";
  if (durInput) durInput.value = clone.duration_minutes || 60;
  if (sourceLbl) {
    sourceLbl.textContent = clone.source === "archive"
      ? `Editing Archived Workout (${clone.date || "Saved"})`
      : `Customizing Library Archetype (${clone.zone_label || "Template"})`;
  }

  _updateArchiveMetricsStrip(clone);
  renderArchiveEditorIntervals();
  drawArchiveEditorCanvas();
  renderArchiveGrid();
}

function renderArchiveGrid() {
  const grid = document.getElementById("archiveWorkoutsGrid");
  if (!grid) return;

  const q = (archiveState.search || "").trim().toLowerCase();
  const filter = archiveState.filter || "all";

  let items = [];
  if (filter === "all") {
    items = [...archiveState.priorWorkouts, ...archiveState.libraryWorkouts];
  } else if (filter === "archive") {
    items = [...archiveState.priorWorkouts];
  } else {
    items = archiveState.libraryWorkouts.filter(w => w.zone === filter);
  }

  if (q) {
    items = items.filter(w => {
      const hay = `${w.title || ""} ${w.focus_area || ""} ${w.zone_label || ""} ${w.ai_rationale || ""} ${w.date || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }

  if (archiveState.durationFilter !== "all" && Number.isFinite(Number(archiveState.durationFilter))) {
    const targetDur = Number(archiveState.durationFilter);
    items = items.filter(w => Math.abs((Number(w.duration_minutes) || 0) - targetDur) <= 5);
  }

  const badgeEl = document.getElementById("archiveCountBadge");
  if (badgeEl) {
    badgeEl.textContent = `${archiveState.priorWorkouts.length} Archived • ${archiveState.libraryWorkouts.length} Library`;
  }

  if (items.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:2rem;color:var(--text-muted);">No matching workouts found. Try clearing your filter or click "+ New Custom Workout".</div>`;
    return;
  }

  const selectedId = archiveState.editingWorkout ? archiveState.editingWorkout.id : null;

  grid.innerHTML = items.map(w => {
    const isArch = w.source === "archive";
    const isSelected = selectedId && w.id === selectedId;
    const badgeClass = (w.status === "scheduled" || w.pushed_to_zwift) ? "badge-zwift" : (isArch ? "badge-archive" : "");
    const badgeText = (w.status === "scheduled" || w.pushed_to_zwift)
      ? `🚀 Scheduled${w.date ? " • " + w.date : ""}`
      : (isArch ? `📦 Archived${w.date ? " • " + w.date : ""}` : `📚 ${w.zone_label || "Library"}`);
    const spark = _buildIntervalSparklineSvg(w.intervals || []);
    const safeTitle = (w.title || "Workout").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const safeFocus = (w.focus_area || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    return `
      <div class="archive-workout-card ${isSelected ? "selected" : ""}" data-id="${w.id}" data-source="${w.source}">
        <div class="archive-card-top">
          <span class="archive-card-badge ${badgeClass}">${badgeText}</span>
          ${isArch ? `<button type="button" class="btn btn-secondary btn-xs archive-card-del" data-del-id="${w.id}" title="Delete from Archive">🗑️</button>` : ""}
        </div>
        <div class="archive-card-title">${safeTitle}</div>
        <div class="archive-card-sub">${safeFocus}</div>
        <div class="archive-card-spark">${spark}</div>
        <div class="archive-card-stats">
          <span>⏱️ ${w.duration_minutes || 0}m</span>
          <span>⚡ ${w.normalized_power_watts || "--"}W NP</span>
          <span>🔥 ${w.estimated_tss || 0} TSS</span>
          <span>🧬 ${Math.round(w.total_xss || 0)} XSS</span>
        </div>
        <div class="archive-card-actions">
          <button type="button" class="btn btn-secondary btn-xs archive-btn-edit" style="flex:1;">✏️ Customize</button>
          <button type="button" class="btn btn-primary btn-xs archive-btn-zwift" style="flex:1;background:linear-gradient(135deg,#0052FF,#FF5E00);border:none;">🚀 Send to Zwift</button>
        </div>
      </div>
    `;
  }).join("");

  grid.querySelectorAll(".archive-workout-card").forEach(cardEl => {
    const id = cardEl.dataset.id;
    const src = cardEl.dataset.source;
    const pool = src === "archive" ? archiveState.priorWorkouts : archiveState.libraryWorkouts;
    const workoutObj = pool.find(x => x.id === id);
    if (!workoutObj) return;

    cardEl.addEventListener("click", (e) => {
      if (e.target.closest(".archive-card-del") || e.target.closest(".archive-btn-zwift")) return;
      openArchiveEditor(workoutObj);
    });

    cardEl.querySelector(".archive-btn-zwift")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "⏳ Sending...";
      await pushArchiveWorkoutToZwift({
        workout_id: src === "archive" ? workoutObj.id : null,
        archetype_id: src === "library" ? workoutObj.archetype_id : null,
        workout: workoutObj
      });
      btn.disabled = false;
      btn.textContent = "🚀 Send to Zwift";
    });

    cardEl.querySelector(".archive-card-del")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await deleteArchiveWorkout(id);
    });
  });
}

async function loadWorkoutArchive() {
  try {
    const url = `/api/workouts/archive?duration_min=${encodeURIComponent(archiveState.libraryDuration || 60)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.success) {
      archiveState.ftp = data.ftp || 250;
      archiveState.priorWorkouts = data.prior_workouts || [];
      archiveState.libraryWorkouts = data.library_workouts || [];
      renderArchiveGrid();
      if (!archiveState.editingWorkout && (archiveState.priorWorkouts.length > 0 || archiveState.libraryWorkouts.length > 0)) {
        openArchiveEditor(archiveState.priorWorkouts[0] || archiveState.libraryWorkouts[0]);
      }
    }
  } catch (e) {
    console.warn("Could not load workout archive:", e);
  }
}

async function saveArchiveEditorWorkout() {
  if (!archiveState.editingWorkout) return;
  const w = archiveState.editingWorkout;
  const titleInput = document.getElementById("archiveEditTitle");
  const dateInput = document.getElementById("archiveEditDate");
  const notesInput = document.getElementById("archiveEditNotes");

  const payload = {
    id: w.id || null,
    title: (titleInput?.value || w.title || "Custom Workout").trim(),
    description: (notesInput?.value || w.description || "").trim(),
    focus_area: w.focus_area || "Custom",
    ai_rationale: (notesInput?.value || w.ai_rationale || "").trim(),
    date: dateInput?.value || new Date().toISOString().slice(0, 10),
    status: "archived",
    intervals: w.intervals || []
  };

  const btn = document.getElementById("btnArchiveSave");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Saving..."; }
  try {
    const res = await fetch("/api/workouts/archive/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success && data.workout) {
      showToast(`💾 Saved '${data.workout.title}' to Workout Archive!`);
      archiveState.editingWorkout = data.workout;
      await loadWorkoutArchive();
      openArchiveEditor(data.workout);
    } else {
      showToast(`⚠️ ${data.detail || data.error || "Could not save workout."}`);
    }
  } catch (e) {
    showToast("⚠️ Error saving workout to archive.");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "💾 Save to Archive"; }
  }
}

async function pushArchiveWorkoutToZwift(payload) {
  const dateInput = document.getElementById("archiveEditDate");
  const targetDate = payload.target_date || dateInput?.value || new Date().toISOString().slice(0, 10);
  try {
    const res = await fetch("/api/workouts/archive/push-zwift", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workout_id: payload.workout_id || null,
        archetype_id: payload.archetype_id || null,
        workout: payload.workout || null,
        target_date: targetDate,
        save_to_archive: true
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`🚀 Sent '${data.workout?.title || "Workout"}' to Zwift for ${targetDate}!`);
      await loadWorkoutArchive();
      if (typeof loadWorkout === "function") loadWorkout();
    } else {
      showToast(`⚠️ ${data.error || data.detail || "Could not sync to Zwift."}`);
      if ((data.error || "").toLowerCase().includes("api key")) {
        openSettingsModal();
      }
    }
  } catch (e) {
    showToast("⚠️ Network error sending workout to Zwift.");
  }
}

async function deleteArchiveWorkout(workoutId) {
  try {
    const res = await fetch(`/api/workouts/archive/${encodeURIComponent(workoutId)}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      showToast("🗑️ Deleted workout from Archive.");
      if (archiveState.editingWorkout && archiveState.editingWorkout.id === workoutId) {
        archiveState.editingWorkout = null;
      }
      await loadWorkoutArchive();
    }
  } catch (e) {
    showToast("⚠️ Could not delete workout.");
  }
}

async function downloadArchiveZwo() {
  if (!archiveState.editingWorkout) return;
  const w = archiveState.editingWorkout;
  const titleInput = document.getElementById("archiveEditTitle");
  try {
    const res = await fetch("/api/workouts/archive/download-zwo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: titleInput?.value || w.title || "PowerSync_Workout",
        ai_rationale: w.ai_rationale || "",
        intervals: w.intervals || []
      })
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(titleInput?.value || w.title || "PowerSync_Workout").replace(/\s+/g, "_")}.zwo`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast("⚠️ Failed to download .zwo file.");
  }
}

function initWorkoutArchive() {
  if (archiveState.initialized) return;
  archiveState.initialized = true;

  const searchEl = document.getElementById("archiveSearchInput");
  searchEl?.addEventListener("input", () => {
    archiveState.search = searchEl.value;
    renderArchiveGrid();
  });

  const durSel = document.getElementById("archiveLibraryDuration");
  durSel?.addEventListener("change", () => {
    const val = durSel.value || "all";
    if (val === "all") {
      archiveState.durationFilter = "all";
      archiveState.libraryDuration = 60;
    } else {
      const parsed = parseInt(val, 10) || 60;
      archiveState.durationFilter = parsed;
      archiveState.libraryDuration = parsed;
    }
    loadWorkoutArchive();
  });

  document.querySelectorAll("#archiveFilterPills .archive-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#archiveFilterPills .archive-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      archiveState.filter = pill.dataset.filter || "all";
      renderArchiveGrid();
    });
  });

  document.getElementById("btnArchiveNewWorkout")?.addEventListener("click", (e) => {
    e.stopPropagation();
    openArchiveEditor({
      id: null,
      title: "Custom Interval Session",
      focus_area: "Custom",
      duration_minutes: 45,
      ai_rationale: "Custom workout built in PowerSync Workout Archive.",
      source: "archive",
      intervals: [
        { type: "Warmup", duration_sec: 420, power_low_pct: 45, power_high_pct: 75, cadence: 88, name: "Progressive Warmup Ramp" },
        { type: "SteadyState", duration_sec: 900, power_pct: 88, cadence: 90, name: "Sweet Spot Block" },
        { type: "SteadyState", duration_sec: 180, power_pct: 55, cadence: 85, name: "Recovery Spin" },
        { type: "SteadyState", duration_sec: 900, power_pct: 90, cadence: 92, name: "Sweet Spot Block 2" },
        { type: "Cooldown", duration_sec: 300, power_low_pct: 65, power_high_pct: 40, cadence: 82, name: "Progressive Cooldown Ramp" }
      ]
    });
    previewArchiveEditor();
  });

  document.getElementById("btnArchiveAddInterval")?.addEventListener("click", () => {
    if (!archiveState.editingWorkout) return;
    archiveState.editingWorkout.intervals.push({
      type: "SteadyState",
      duration_sec: 300,
      power_pct: 85,
      cadence: 90,
      name: "Custom Block"
    });
    renderArchiveEditorIntervals();
    previewArchiveEditor();
  });

  document.querySelectorAll(".archive-scale-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const delta = parseInt(btn.dataset.delta || "0", 10);
      previewArchiveEditor({ intensity_adjust_pct: delta, reRenderRows: true });
    });
  });

  document.getElementById("btnArchiveApplyDur")?.addEventListener("click", () => {
    const durVal = parseInt(document.getElementById("archiveReconcileDur")?.value || "60", 10);
    if (durVal >= 15) {
      previewArchiveEditor({ duration_minutes: durVal, reRenderRows: true });
    }
  });

  document.getElementById("btnArchiveSave")?.addEventListener("click", saveArchiveEditorWorkout);
  document.getElementById("btnArchiveDownloadZwo")?.addEventListener("click", downloadArchiveZwo);
  document.getElementById("btnArchivePushZwift")?.addEventListener("click", async () => {
    if (!archiveState.editingWorkout) return;
    const btn = document.getElementById("btnArchivePushZwift");
    const titleInput = document.getElementById("archiveEditTitle");
    const notesInput = document.getElementById("archiveEditNotes");
    archiveState.editingWorkout.title = titleInput?.value?.trim() || archiveState.editingWorkout.title;
    archiveState.editingWorkout.ai_rationale = notesInput?.value?.trim() || archiveState.editingWorkout.ai_rationale;
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Sending..."; }
    await pushArchiveWorkoutToZwift({ workout: archiveState.editingWorkout });
    if (btn) { btn.disabled = false; btn.textContent = "🚀 Send to Zwift"; }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initWorkoutArchive);
} else {
  initWorkoutArchive();
}



// ============================================================================
// RIDE HISTORY & EXPLORER (Baseline-Inspired Historical Analytics)
// ============================================================================

let historyState = {
  initialized: false,
  loading: false,
  range: "90d",
  env: "all",
  volumeMode: "env",
  showWhoopOverlay: true,
  search: "",
  sort: "date_desc",
  data: null,
  map: null,
  mapLayerGroup: null,
  inspectorMap: null,
};

function decodeStravaPolyline(encoded) {
  if (!encoded || typeof encoded !== "string") return [];
  let index = 0;
  const len = encoded.length;
  let lat = 0;
  let lng = 0;
  const coords = [];

  while (index < len) {
    let b, shift = 0, result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20 && index < len);
    const dlat = (result & 1) ? ~(result >> 1) : (result >> 1);
    lat += dlat;

    shift = 0;
    result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20 && index < len);
    const dlng = (result & 1) ? ~(result >> 1) : (result >> 1);
    lng += dlng;

    coords.push([lat * 1e-5, lng * 1e-5]);
  }
  return coords;
}

function escapeHistoryHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatHistoryDuration(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function initRideHistoryTab() {
  if (!historyState.initialized) {
    historyState.initialized = true;

    document.querySelectorAll("#historyRangePills .history-pill-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#historyRangePills .history-pill-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        historyState.range = btn.dataset.range || "90d";
        loadRideHistoryAnalytics();
      });
    });

    document.querySelectorAll("#historyEnvPills .history-pill-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#historyEnvPills .history-pill-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        historyState.env = btn.dataset.env || "all";
        loadRideHistoryAnalytics();
      });
    });

    document.querySelectorAll("#historyVolumeModePills .history-pill-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#historyVolumeModePills .history-pill-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        historyState.volumeMode = btn.dataset.vmode || "env";
        if (historyState.data) renderHistoryVolumeChart(historyState.data.volume_buckets || []);
      });
    });

    document.getElementById("chkPmcWhoopOverlay")?.addEventListener("change", (e) => {
      historyState.showWhoopOverlay = !!e.target.checked;
      if (historyState.data) renderHistoryPmcChart(historyState.data.pmc_series || []);
    });

    document.getElementById("btnHistoryRefresh")?.addEventListener("click", () => {
      loadRideHistoryAnalytics({ forceSync: true });
    });

    document.getElementById("btnHistoryMapFit")?.addEventListener("click", () => {
      if (historyState.map && historyState.mapLayerGroup) {
        try {
          const bounds = historyState.mapLayerGroup.getBounds();
          if (bounds.isValid()) historyState.map.fitBounds(bounds, { padding: [20, 20] });
        } catch (_) {}
      }
    });

    document.getElementById("historyRideSearch")?.addEventListener("input", (e) => {
      historyState.search = (e.target.value || "").trim().toLowerCase();
      if (historyState.data) renderHistoryRideTable(historyState.data.rides || []);
    });

    document.getElementById("historyRideSort")?.addEventListener("change", (e) => {
      historyState.sort = e.target.value || "date_desc";
      if (historyState.data) renderHistoryRideTable(historyState.data.rides || []);
    });

    document.getElementById("btnCloseRideInspector")?.addEventListener("click", closeRideInspectorModal);
    document.getElementById("modalRideInspector")?.addEventListener("click", (e) => {
      if (e.target && e.target.id === "modalRideInspector") closeRideInspectorModal();
    });
  }

  if (!historyState.data) {
    loadRideHistoryAnalytics({ forceSync: false });
  } else {
    requestAnimationFrame(() => {
      if (historyState.map) historyState.map.invalidateSize(true);
    });
  }
}

function getHistoryCacheKey(range, env) {
  const uid = (typeof currentAthleteUser !== "undefined" && currentAthleteUser && currentAthleteUser.id)
    ? String(currentAthleteUser.id)
    : "guest";
  return `${uid}:${range}:${env}`;
}

function openHistoryIndexedDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open("PowerSyncRideHistoryDB", 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains("analytics_cache")) {
        db.createObjectStore("analytics_cache", { keyPath: "cache_key" });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = () => reject(req.error || new Error("IndexedDB open failed"));
  });
}

async function getCachedHistoryAnalytics(range, env) {
  try {
    const db = await openHistoryIndexedDb();
    return await new Promise((resolve) => {
      const tx = db.transaction("analytics_cache", "readonly");
      const store = tx.objectStore("analytics_cache");
      const req = store.get(getHistoryCacheKey(range, env));
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch (_) {
    return null;
  }
}

async function saveCachedHistoryAnalytics(range, env, payload) {
  if (!payload || payload.is_guest) return;
  try {
    const db = await openHistoryIndexedDb();
    await new Promise((resolve) => {
      const tx = db.transaction("analytics_cache", "readwrite");
      const store = tx.objectStore("analytics_cache");
      store.put({
        cache_key: getHistoryCacheKey(range, env),
        saved_at: new Date().toISOString(),
        payload
      });
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    });
  } catch (_) {}
}

async function loadRideHistoryAnalytics(opts = {}) {
  const forceSync = Boolean(opts && opts.forceSync);
  if (historyState.loading) return;
  historyState.loading = true;
  const countPill = document.getElementById("historyRideCountPill");
  const refreshBtn = document.getElementById("btnHistoryRefresh");

  if (!forceSync) {
    const cached = await getCachedHistoryAnalytics(historyState.range, historyState.env);
    if (cached && cached.payload && !cached.payload.is_guest) {
      historyState.data = cached.payload;
      renderAllRideHistoryModules(cached.payload, { fromLocalDb: true, savedAt: cached.saved_at });
      historyState.loading = false;
      return;
    }
  }

  if (countPill) countPill.textContent = forceSync ? "Syncing newer rides..." : "Loading...";
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = forceSync ? "↻ Syncing..." : "↻ Loading...";
  }

  try {
    const url = `/api/history/analytics?range=${encodeURIComponent(historyState.range)}&env=${encodeURIComponent(historyState.env)}${forceSync ? "&sync=true" : ""}`;
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    historyState.data = data;
    await saveCachedHistoryAnalytics(historyState.range, historyState.env, data);
    renderAllRideHistoryModules(data, { fromLocalDb: false, synced: forceSync });
  } catch (err) {
    console.error("Failed to load ride history analytics:", err);
    if (countPill) countPill.textContent = "Error loading";
  } finally {
    historyState.loading = false;
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "↻ Refresh";
    }
  }
}

function renderAllRideHistoryModules(data, meta = {}) {
  const countPill = document.getElementById("historyRideCountPill");
  if (data.is_guest) {
    if (countPill) countPill.textContent = "Sign in to view history";
  } else {
    const cnt = (data.kpis && data.kpis.ride_count) || 0;
    const suffix = meta.fromLocalDb ? " · Local DB" : (meta.synced ? " · Synced" : "");
    if (countPill) countPill.textContent = `${cnt} ride${cnt === 1 ? "" : "s"}${suffix}`;
  }

  renderHistoryKpis(data.kpis || {}, data.deltas || {});
  renderHistoryHeatmap(data.heatmap_rides || []);
  renderHistoryVolumeChart(data.volume_buckets || []);
  renderHistoryPmcChart(data.pmc_series || []);
  renderHistoryRecoveryMatrix(data.recovery_matrix || { buckets: {}, scatter: [] });
  renderHistoryPowerCurve(data.power_curve || { curve: [], breakthroughs: [] });
  renderHistoryRecap(data.year_in_sport || {});
  renderHistoryRideTable(data.rides || []);
}

function formatDeltaBadge(val) {
  if (val === null || val === undefined) return "";
  const cls = val >= 0 ? "up" : "down";
  const sign = val >= 0 ? "+" : "";
  return `<span class="history-delta-badge ${cls}">${sign}${val}%</span>`;
}

function renderHistoryKpis(kpis, deltas) {
  const setKpi = (id, subId, val, subHtml) => {
    const el = document.getElementById(id);
    const sub = document.getElementById(subId);
    if (el) el.textContent = val;
    if (sub) sub.innerHTML = subHtml;
  };

  if (!kpis || !kpis.ride_count) {
    setKpi("hkpiDistance", "hkpiDistanceSub", "0 km", "No rides in range");
    setKpi("hkpiTime", "hkpiTimeSub", "0 hrs", "--");
    setKpi("hkpiElevation", "hkpiElevationSub", "0 m", "--");
    setKpi("hkpiWork", "hkpiWorkSub", "0 kJ", "--");
    setKpi("hkpiTss", "hkpiTssSub", "0", "--");
    setKpi("hkpiNpEf", "hkpiNpEfSub", "--", "No power/HR data");
    return;
  }

  setKpi(
    "hkpiDistance",
    "hkpiDistanceSub",
    `${kpis.distance_km.toLocaleString()} km`,
    `${kpis.distance_mi.toLocaleString()} mi ${formatDeltaBadge(deltas.distance_km)}`
  );
  setKpi(
    "hkpiTime",
    "hkpiTimeSub",
    `${kpis.moving_hours} hrs`,
    `${kpis.ride_count} rides ${formatDeltaBadge(deltas.moving_hours)}`
  );
  setKpi(
    "hkpiElevation",
    "hkpiElevationSub",
    `${Number(kpis.elevation_m).toLocaleString()} m`,
    `${Number(kpis.elevation_ft).toLocaleString()} ft ${formatDeltaBadge(deltas.elevation_m)}`
  );
  setKpi(
    "hkpiWork",
    "hkpiWorkSub",
    `${Number(kpis.kilojoules).toLocaleString()} kJ`,
    `Mechanical work ${formatDeltaBadge(deltas.kilojoules)}`
  );
  setKpi(
    "hkpiTss",
    "hkpiTssSub",
    `${Number(kpis.tss).toLocaleString()}`,
    `Training load ${formatDeltaBadge(deltas.tss)}`
  );
  const npTxt = kpis.avg_np ? `${Math.round(kpis.avg_np)} W` : "--";
  const efTxt = kpis.avg_ef ? `EF ${kpis.avg_ef}` : "EF --";
  setKpi(
    "hkpiNpEf",
    "hkpiNpEfSub",
    npTxt,
    `${efTxt}${kpis.avg_hr ? ` · ${Math.round(kpis.avg_hr)} bpm` : ""}`
  );
}

function renderHistoryHeatmap(heatmapRides) {
  const container = document.getElementById("historyHeatmapContainer");
  const emptyEl = document.getElementById("historyMapEmpty");
  const subtitleEl = document.getElementById("historyMapSubtitle");
  if (!container) return;

  if (!window.L) {
    container.style.display = "none";
    if (emptyEl) {
      emptyEl.style.display = "block";
      emptyEl.textContent = "Leaflet map library unavailable.";
    }
    return;
  }

  if (!heatmapRides || heatmapRides.length === 0) {
    container.style.display = "none";
    if (emptyEl) emptyEl.style.display = "block";
    if (subtitleEl) subtitleEl.textContent = "0 GPS routes in this filter";
    return;
  }

  container.style.display = "block";
  if (emptyEl) emptyEl.style.display = "none";
  if (subtitleEl) subtitleEl.textContent = `${heatmapRides.length} outdoor route${heatmapRides.length === 1 ? "" : "s"} layered with intensity bleed`;

  if (!historyState.map) {
    historyState.map = L.map(container, { zoomControl: true, attributionControl: false }).setView([37.77, -122.41], 10);
    const gKey = (typeof state !== "undefined" && state && state.googleMapsApiKey) || "";
    const tileCfg = typeof getTileLayerConfig === "function"
      ? getTileLayerConfig((typeof outdoorBaseLayerName !== "undefined" && outdoorBaseLayerName) || "google_roads", gKey)
      : { url: "https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", options: { maxZoom: 20, subdomains: "0123" } };
    L.tileLayer(tileCfg.url, tileCfg.options).addTo(historyState.map);
    historyState.mapLayerGroup = L.featureGroup().addTo(historyState.map);
  } else {
    historyState.mapLayerGroup.clearLayers();
  }

  // Draw outer soft glow + inner crisp line for Baseline "bleed" effect
  heatmapRides.forEach((ride) => {
    const pts = decodeStravaPolyline(ride.polyline);
    if (!pts.length) return;

    // Outer bleed
    L.polyline(pts, {
      color: "#FF5E00",
      weight: 6,
      opacity: 0.14,
      interactive: false
    }).addTo(historyState.mapLayerGroup);

    // Core route line
    const core = L.polyline(pts, {
      color: "#FF8A3D",
      weight: 2.2,
      opacity: 0.55
    }).addTo(historyState.mapLayerGroup);

    core.bindTooltip(
      `<strong>${escapeHistoryHtml(ride.name)}</strong><br>${ride.date} · ${ride.distance_km} km · ${Math.round(ride.tss)} TSS`,
      { sticky: true }
    );
    core.on("click", () => openRideInspectorModal(ride.id));
  });

  requestAnimationFrame(() => {
    historyState.map.invalidateSize(true);
    try {
      const bounds = historyState.mapLayerGroup.getBounds();
      if (bounds.isValid()) historyState.map.fitBounds(bounds, { padding: [20, 20] });
    } catch (_) {}
  });
}

function renderHistoryVolumeChart(buckets) {
  const wrap = document.getElementById("historyVolumeChart");
  if (!wrap) return;
  if (!buckets || !buckets.length) {
    wrap.innerHTML = `<div style="padding:3rem 1rem;text-align:center;color:var(--text-muted);font-size:0.84rem;">No ride volume in this range.</div>`;
    return;
  }

  const W = 560, H = 240;
  const padL = 38, padR = 14, padT = 18, padB = 34;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const isStrain = historyState.volumeMode === "strain";

  const totals = buckets.map((b) =>
    isStrain ? (b.strain_low + b.strain_high + b.strain_peak) : b.hours_total
  );
  const maxVal = Math.max(1, ...totals);
  const barSlot = chartW / buckets.length;
  const barW = Math.max(6, Math.min(28, barSlot * 0.65));

  let barsSvg = "";
  let labelsSvg = "";
  const labelStep = Math.max(1, Math.ceil(buckets.length / 8));

  buckets.forEach((b, i) => {
    const x = padL + i * barSlot + (barSlot - barW) / 2;
    const total = totals[i];

    if (isStrain) {
      const hLow = (b.strain_low / maxVal) * chartH;
      const hHigh = (b.strain_high / maxVal) * chartH;
      const hPeak = (b.strain_peak / maxVal) * chartH;
      let y = padT + chartH;
      if (hLow > 0) {
        y -= hLow;
        barsSvg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${hLow.toFixed(1)}" rx="2" fill="#0052FF"><title>${b.label}: Low ${b.strain_low} | High ${b.strain_high} | Peak ${b.strain_peak}</title></rect>`;
      }
      if (hHigh > 0) {
        y -= hHigh;
        barsSvg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${hHigh.toFixed(1)}" rx="2" fill="#F59E0B"><title>${b.label}: High Strain ${b.strain_high}</title></rect>`;
      }
      if (hPeak > 0) {
        y -= hPeak;
        barsSvg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${hPeak.toFixed(1)}" rx="2" fill="#EF4444"><title>${b.label}: Peak Strain ${b.strain_peak}</title></rect>`;
      }
    } else {
      const hOut = (b.hours_outdoor / maxVal) * chartH;
      const hIn = (b.hours_indoor / maxVal) * chartH;
      let y = padT + chartH;
      if (hOut > 0) {
        y -= hOut;
        barsSvg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${hOut.toFixed(1)}" rx="2" fill="#10B981"><title>${b.label}: Outdoor ${b.hours_outdoor}h | Indoor ${b.hours_indoor}h (${b.rides} rides)</title></rect>`;
      }
      if (hIn > 0) {
        y -= hIn;
        barsSvg += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${hIn.toFixed(1)}" rx="2" fill="#0052FF"><title>${b.label}: Indoor ${b.hours_indoor}h (${b.rides} rides)</title></rect>`;
      }
    }

    if (i % labelStep === 0 || i === buckets.length - 1) {
      labelsSvg += `<text x="${(x + barW / 2).toFixed(1)}" y="${H - 12}" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">${escapeHistoryHtml(b.label)}</text>`;
    }
  });

  // Grid lines
  let gridSvg = "";
  for (let g = 0; g <= 3; g++) {
    const val = (maxVal * g) / 3;
    const y = padT + chartH - (g / 3) * chartH;
    gridSvg += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="var(--border-color)" stroke-dasharray="3,3" />`;
    gridSvg += `<text x="${padL - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">${isStrain ? Math.round(val) : val.toFixed(1) + "h"}</text>`;
  }

  const legend = isStrain
    ? `<span style="color:#0052FF;">■ Low</span> &nbsp;<span style="color:#F59E0B;">■ High</span> &nbsp;<span style="color:#EF4444;">■ Peak</span>`
    : `<span style="color:#10B981;">■ Outdoor</span> &nbsp;<span style="color:#0052FF;">■ Indoor/Zwift</span>`;

  wrap.innerHTML = `
    <div style="text-align:right;font-size:0.72rem;font-weight:600;margin-bottom:0.25rem;">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
      ${gridSvg}
      ${barsSvg}
      ${labelsSvg}
    </svg>
  `;
}

function renderHistoryPmcChart(series) {
  const wrap = document.getElementById("historyPmcChart");
  if (!wrap) return;
  if (!series || series.length < 2) {
    wrap.innerHTML = `<div style="padding:3rem 1rem;text-align:center;color:var(--text-muted);font-size:0.84rem;">Not enough historical days to plot CTL/ATL/TSB.</div>`;
    return;
  }

  const W = 960, H = 250;
  const padL = 42, padR = 38, padT = 16, padB = 32;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const allVals = [];
  series.forEach((p) => {
    allVals.push(p.ctl, p.atl, p.tsb);
  });
  const minV = Math.min(-25, ...allVals);
  const maxV = Math.max(40, ...allVals);
  const span = Math.max(10, maxV - minV);

  const xFor = (i) => padL + (i / (series.length - 1)) * chartW;
  const yFor = (v) => padT + chartH - ((v - minV) / span) * chartH;

  const buildPath = (key) =>
    series.map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(p[key]).toFixed(1)}`).join(" ");

  let whoopDots = "";
  if (historyState.showWhoopOverlay) {
    series.forEach((p, i) => {
      if (p.recovery === null || p.recovery === undefined) return;
      const x = xFor(i);
      const y = padT + chartH - (Math.min(100, Math.max(0, p.recovery)) / 100) * chartH;
      const col = p.recovery >= 67 ? "#10B981" : p.recovery >= 34 ? "#F59E0B" : "#EF4444";
      whoopDots += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.6" fill="${col}" opacity="0.65"><title>${p.date}: Whoop ${p.recovery}% | CTL ${p.ctl} | ATL ${p.atl} | TSB ${p.tsb}</title></circle>`;
    });
  }

  let gridSvg = "";
  const zeroY = yFor(0);
  gridSvg += `<line x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${W - padR}" y2="${zeroY.toFixed(1)}" stroke="var(--text-muted)" stroke-opacity="0.45" stroke-dasharray="4,3" />`;
  for (let g = 0; g <= 4; g++) {
    const val = minV + (span * g) / 4;
    const y = yFor(val);
    gridSvg += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="var(--border-color)" stroke-dasharray="2,3" />`;
    gridSvg += `<text x="${padL - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="10" fill="var(--text-muted)">${Math.round(val)}</text>`;
  }

  // Right axis for Recovery %
  if (historyState.showWhoopOverlay) {
    [0, 50, 100].forEach((pct) => {
      const y = padT + chartH - (pct / 100) * chartH;
      gridSvg += `<text x="${W - padR + 6}" y="${(y + 3).toFixed(1)}" text-anchor="start" font-size="9.5" fill="#10B981">${pct}%</text>`;
    });
  }

  let xLabels = "";
  const step = Math.max(1, Math.floor(series.length / 7));
  series.forEach((p, i) => {
    if (i % step === 0 || i === series.length - 1) {
      xLabels += `<text x="${xFor(i).toFixed(1)}" y="${H - 10}" text-anchor="middle" font-size="10" fill="var(--text-muted)">${p.date.slice(5)}</text>`;
    }
  });

  const latest = series[series.length - 1];
  const subEl = document.getElementById("historyPmcSubtitle");
  if (subEl && latest) {
    subEl.textContent = `Latest: CTL (Fitness) ${latest.ctl} · ATL (Fatigue) ${latest.atl} · TSB (Form) ${latest.tsb >= 0 ? "+" : ""}${latest.tsb}`;
  }

  wrap.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
      ${gridSvg}
      ${whoopDots}
      <path d="${buildPath("tsb")}" fill="none" stroke="#10B981" stroke-width="1.8" stroke-dasharray="4,2" />
      <path d="${buildPath("atl")}" fill="none" stroke="#FF5E00" stroke-width="2" />
      <path d="${buildPath("ctl")}" fill="none" stroke="#0052FF" stroke-width="2.6" />
      ${xLabels}
    </svg>
  `;
}

function renderHistoryRecoveryMatrix(matrix) {
  const bucketsEl = document.getElementById("historyRecoveryBuckets");
  const scatterEl = document.getElementById("historyRecoveryScatter");
  const buckets = matrix.buckets || {};

  if (bucketsEl) {
    const order = ["green", "yellow", "red"];
    bucketsEl.innerHTML = order
      .map((k) => {
        const b = buckets[k] || { label: k.toUpperCase(), ride_count: 0 };
        return `
          <div class="history-rec-bucket ${k}">
            <div class="history-rec-title">${escapeHistoryHtml(b.label || k)}</div>
            <div class="history-rec-stats">
              <div><strong>${b.ride_count || 0}</strong> rides</div>
              <div>Avg NP: <strong>${b.avg_np ? Math.round(b.avg_np) + " W" : "--"}</strong></div>
              <div>Avg EF: <strong>${b.avg_ef ?? "--"}</strong></div>
              <div>Avg TSS: <strong>${b.avg_tss ? Math.round(b.avg_tss) : "--"}</strong></div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  if (!scatterEl) return;
  const pts = (matrix.scatter || []).filter((p) => p.ef !== null && p.ef !== undefined);
  if (pts.length < 2) {
    scatterEl.innerHTML = `<div style="padding:2rem 1rem;text-align:center;color:var(--text-muted);font-size:0.82rem;">Sync Whoop + Strava rides with power &amp; HR to unlock Recovery × Efficiency scatter.</div>`;
    return;
  }

  const W = 500, H = 195;
  const padL = 42, padR = 16, padT = 14, padB = 28;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const efVals = pts.map((p) => p.ef);
  const minEf = Math.max(0.5, Math.min(...efVals) - 0.1);
  const maxEf = Math.max(minEf + 0.3, Math.max(...efVals) + 0.1);

  let dots = "";
  pts.forEach((p) => {
    const x = padL + (Math.min(100, Math.max(0, p.recovery)) / 100) * chartW;
    const y = padT + chartH - ((p.ef - minEf) / (maxEf - minEf)) * chartH;
    const col = p.zone === "green" ? "#10B981" : p.zone === "yellow" ? "#F59E0B" : "#EF4444";
    dots += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${col}" fill-opacity="0.78" stroke="#FFFFFF" stroke-width="0.8" style="cursor:pointer;" onclick="openRideInspectorModal('${escapeHistoryHtml(p.id)}')"><title>${p.date} · ${escapeHistoryHtml(p.name)}\nWhoop: ${p.recovery}% | EF: ${p.ef} | NP: ${p.np_watts || '--'}W</title></circle>`;
  });

  scatterEl.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
      <line x1="${padL}" y1="${padT + chartH}" x2="${W - padR}" y2="${padT + chartH}" stroke="var(--border-color)" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + chartH}" stroke="var(--border-color)" />
      <text x="${padL + chartW / 2}" y="${H - 6}" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">Morning Whoop Recovery (%)</text>
      <text x="${padL - 6}" y="${padT + 8}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">${maxEf.toFixed(2)}</text>
      <text x="${padL - 6}" y="${padT + chartH}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">${minEf.toFixed(2)}</text>
      ${dots}
    </svg>
  `;
}

function renderHistoryPowerCurve(powerCurveData) {
  const chartEl = document.getElementById("historyPowerCurveChart");
  const btEl = document.getElementById("historyBreakthroughs");
  const curve = powerCurveData.curve || [];
  const breakthroughs = powerCurveData.breakthroughs || [];

  if (chartEl) {
    const maxW = Math.max(100, ...curve.map((c) => Math.max(c.all_time_watts || 0, c.range_watts || 0)));
    if (!curve.length || maxW <= 100 && curve.every((c) => !c.all_time_watts)) {
      chartEl.innerHTML = `<div style="padding:2rem 1rem;text-align:center;color:var(--text-muted);font-size:0.82rem;">No power meter data in this range.</div>`;
    } else {
      const W = 500, H = 195;
      const padL = 42, padR = 18, padT = 18, padB = 30;
      const chartW = W - padL - padR;
      const chartH = H - padT - padB;
      const xFor = (i) => padL + (i / (curve.length - 1)) * chartW;
      const yFor = (w) => padT + chartH - (w / maxW) * chartH;

      const allPath = curve.map((c, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(c.all_time_watts || 0).toFixed(1)}`).join(" ");
      const rngPath = curve.map((c, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(c.range_watts || 0).toFixed(1)}`).join(" ");

      let pointsSvg = "";
      curve.forEach((c, i) => {
        const x = xFor(i);
        const yAll = yFor(c.all_time_watts || 0);
        const yRng = yFor(c.range_watts || 0);
        pointsSvg += `<circle cx="${x.toFixed(1)}" cy="${yAll.toFixed(1)}" r="3.5" fill="#94A3B8"><title>All-Time ${c.label}: ${c.all_time_watts}W (${c.all_time_w_kg} W/kg) on ${c.all_time_date || ''}</title></circle>`;
        pointsSvg += `<circle cx="${x.toFixed(1)}" cy="${yRng.toFixed(1)}" r="4" fill="#FF5E00"><title>Range ${c.label}: ${c.range_watts}W (${c.range_w_kg} W/kg)</title></circle>`;
        pointsSvg += `<text x="${x.toFixed(1)}" y="${H - 10}" text-anchor="middle" font-size="10" font-weight="600" fill="var(--text-muted)">${c.key}</text>`;
      });

      chartEl.innerHTML = `
        <div style="text-align:right;font-size:0.72rem;font-weight:600;margin-bottom:0.2rem;">
          <span style="color:#FF5E00;">● Selected Range</span> &nbsp; <span style="color:#94A3B8;">● All-Time PR</span>
        </div>
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
          <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + chartH}" stroke="var(--border-color)" />
          <line x1="${padL}" y1="${padT + chartH}" x2="${W - padR}" y2="${padT + chartH}" stroke="var(--border-color)" />
          <text x="${padL - 6}" y="${padT + 8}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">${maxW}W</text>
          <text x="${padL - 6}" y="${padT + chartH}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">0W</text>
          <path d="${allPath}" fill="none" stroke="#94A3B8" stroke-width="2" stroke-dasharray="4,3" />
          <path d="${rngPath}" fill="none" stroke="#FF5E00" stroke-width="2.5" />
          ${pointsSvg}
        </svg>
      `;
    }
  }

  if (btEl) {
    btEl.innerHTML = breakthroughs
      .map(
        (b) => `
      <div class="history-breakthrough-pill" onclick="openRideInspectorModal('${escapeHistoryHtml(b.ride_id)}')">
        <div class="history-bt-badge">${escapeHistoryHtml(b.badge)}</div>
        <div class="history-bt-val">${escapeHistoryHtml(b.value)}</div>
        <div class="history-bt-ride">${escapeHistoryHtml(b.ride_name)} · ${b.date}</div>
      </div>
    `
      )
      .join("");
  }
}

function renderHistoryRecap(recap) {
  const el = document.getElementById("historyRecapContent");
  if (!el) return;
  if (!recap || !recap.has_data) {
    el.innerHTML = `<div style="color:var(--text-muted);font-size:0.84rem;">No rides recorded in this window yet.</div>`;
    return;
  }

  el.innerHTML = `
    <div class="history-recap-item">
      <div class="history-recap-lbl">Favorite Ride Day</div>
      <div class="history-recap-val">${escapeHistoryHtml(recap.favorite_day)}</div>
      <div class="history-recap-sub">${recap.favorite_day_count} rides on ${escapeHistoryHtml(recap.favorite_day)}s</div>
    </div>
    <div class="history-recap-item">
      <div class="history-recap-lbl">Best Streak</div>
      <div class="history-recap-val">${recap.longest_streak_days} days</div>
      <div class="history-recap-sub">${recap.active_days} active riding days</div>
    </div>
    <div class="history-recap-item">
      <div class="history-recap-lbl">Outdoor vs Indoor</div>
      <div class="history-recap-val">${recap.outdoor_pct}% / ${recap.indoor_pct}%</div>
      <div class="history-recap-sub">Road/Gravel vs Zwift</div>
    </div>
    <div class="history-recap-item">
      <div class="history-recap-lbl">Everests Climbed</div>
      <div class="history-recap-val">${recap.everests}×</div>
      <div class="history-recap-sub">8,849 m vertical each</div>
    </div>
    <div class="history-recap-item">
      <div class="history-recap-lbl">Energy Burned</div>
      <div class="history-recap-val">🍕 ${Number(recap.pizza_slices).toLocaleString()}</div>
      <div class="history-recap-sub">Pizza slices equivalent</div>
    </div>
  `;
}

function renderHistoryRideTable(rides) {
  const tbody = document.getElementById("historyRideTableBody");
  if (!tbody) return;

  let filtered = Array.isArray(rides) ? [...rides] : [];
  if (historyState.search) {
    filtered = filtered.filter((r) => (r.name || "").toLowerCase().includes(historyState.search));
  }

  const sortKey = historyState.sort || "date_desc";
  filtered.sort((a, b) => {
    if (sortKey === "tss_desc") return (b.tss || 0) - (a.tss || 0);
    if (sortKey === "dist_desc") return (b.distance_km || 0) - (a.distance_km || 0);
    if (sortKey === "elev_desc") return (b.elevation_m || 0) - (a.elevation_m || 0);
    if (sortKey === "np_desc") return (b.np_watts || 0) - (a.np_watts || 0);
    if (sortKey === "ef_desc") return (b.ef || 0) - (a.ef || 0);
    return String(b.date).localeCompare(String(a.date));
  });

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:1.5rem;color:var(--text-muted);">No matching rides found.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .slice(0, 150)
    .map((r) => {
      const envTag = r.is_indoor
        ? `<span class="history-env-tag indoor">Indoor</span>`
        : `<span class="history-env-tag outdoor">Outdoor</span>`;
      const pwr = r.avg_watts ? `${Math.round(r.avg_watts)} / ${Math.round(r.np_watts || r.avg_watts)} W` : "--";
      const hr = r.avg_hr ? `${Math.round(r.avg_hr)} bpm` : "--";
      const ef = r.ef ? r.ef : "--";
      const rec = r.whoop_recovery !== null && r.whoop_recovery !== undefined ? `${r.whoop_recovery}%` : "--";
      const distMi = r.distance_mi !== null && r.distance_mi !== undefined
        ? Number(r.distance_mi).toFixed(1)
        : ((Number(r.distance_km) || 0) * 0.621371).toFixed(1);
      return `
        <tr onclick="openRideInspectorModal('${escapeHistoryHtml(r.id)}')">
          <td>${escapeHistoryHtml(r.date)}</td>
          <td class="history-ride-name-cell" title="${escapeHistoryHtml(r.name)}">${escapeHistoryHtml(r.name)}</td>
          <td>${envTag}</td>
          <td>${distMi} mi</td>
          <td>${formatHistoryDuration(r.moving_time_sec)}</td>
          <td>${Math.round(r.elevation_m)} m</td>
          <td>${pwr}</td>
          <td>${hr}</td>
          <td>${ef}</td>
          <td><strong>${Math.round(r.tss)}</strong></td>
          <td>${rec}</td>
        </tr>
      `;
    })
    .join("");
}

async function openRideInspectorModal(rideId) {
  const modal = document.getElementById("modalRideInspector");
  const titleEl = document.getElementById("rideInspectorTitle");
  const subEl = document.getElementById("rideInspectorSubtitle");
  const bodyEl = document.getElementById("rideInspectorBody");
  if (!modal || !bodyEl) return;

  modal.classList.add("open");
  modal.style.display = "flex";
  if (titleEl) titleEl.textContent = "Loading ride telemetry...";
  if (subEl) subEl.textContent = "";
  bodyEl.innerHTML = `<div style="padding:1.5rem;text-align:center;color:var(--text-muted);">Loading...</div>`;

  try {
    const res = await fetch(`/api/history/ride/${encodeURIComponent(rideId)}`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    const r = payload.ride;
    const similar = payload.similar_rides || [];

    if (titleEl) titleEl.textContent = r.name;
    if (subEl) subEl.textContent = `${r.date} · ${r.is_indoor ? "Indoor / Virtual" : "Outdoor"} · ${r.sport_type}`;

    const totalStrain = Math.max(0.1, (r.strain_low || 0) + (r.strain_high || 0) + (r.strain_peak || 0));
    const pLow = Math.round(((r.strain_low || 0) / totalStrain) * 100);
    const pHigh = Math.round(((r.strain_high || 0) / totalStrain) * 100);
    const pPeak = Math.max(0, 100 - pLow - pHigh);

    const whoopHtml =
      r.whoop_recovery !== null && r.whoop_recovery !== undefined
        ? `<div class="history-inspector-stat"><div class="history-kpi-label">Morning Whoop</div><div style="font-weight:800;">${r.whoop_recovery}% Recovery</div><div style="font-size:0.72rem;color:var(--text-muted);">HRV ${r.whoop_hrv ?? "--"} ms · RHR ${r.whoop_rhr ?? "--"}</div></div>`
        : `<div class="history-inspector-stat"><div class="history-kpi-label">Morning Whoop</div><div style="font-weight:700;color:var(--text-muted);">Not synced</div></div>`;

    bodyEl.innerHTML = `
      ${r.has_polyline ? `<div id="rideInspectorMiniMap" class="history-inspector-minimap"></div>` : ""}
      <div class="history-inspector-stats">
        <div class="history-inspector-stat"><div class="history-kpi-label">Distance / Time</div><div style="font-weight:800;">${(r.distance_mi != null ? Number(r.distance_mi) : (Number(r.distance_km) || 0) * 0.621371).toFixed(1)} mi</div><div style="font-size:0.72rem;color:var(--text-muted);">${formatHistoryDuration(r.moving_time_sec)} · ${Math.round(r.elevation_m)}m elev</div></div>
        <div class="history-inspector-stat"><div class="history-kpi-label">Power</div><div style="font-weight:800;">${r.np_watts ? Math.round(r.np_watts) + " W NP" : "--"}</div><div style="font-size:0.72rem;color:var(--text-muted);">Avg ${r.avg_watts ? Math.round(r.avg_watts) + "W" : "--"} · IF ${r.intensity_factor ?? "--"}</div></div>
        <div class="history-inspector-stat"><div class="history-kpi-label">Load &amp; Efficiency</div><div style="font-weight:800;">${Math.round(r.tss)} TSS</div><div style="font-size:0.72rem;color:var(--text-muted);">EF ${r.ef ?? "--"} · ${r.avg_hr ? Math.round(r.avg_hr) + " bpm" : "--"}</div></div>
        ${whoopHtml}
      </div>
      <div>
        <div style="font-size:0.74rem;font-weight:700;color:var(--text-secondary);margin-bottom:0.3rem;">3-Tier Mechanical Strain Split (Low ${r.strain_low} · High ${r.strain_high} · Peak ${r.strain_peak})</div>
        <div style="display:flex;height:10px;border-radius:999px;overflow:hidden;background:var(--border-color);">
          <div style="width:${pLow}%;background:#0052FF;"></div>
          <div style="width:${pHigh}%;background:#F59E0B;"></div>
          <div style="width:${pPeak}%;background:#EF4444;"></div>
        </div>
      </div>
      ${
        similar.length
          ? `<div>
              <div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);margin-bottom:0.35rem;">Similar Duration Rides Comparison</div>
              <div style="display:flex;flex-direction:column;gap:0.3rem;">
                ${similar
                  .map(
                    (s) => `<div style="display:flex;justify-content:space-between;font-size:0.76rem;padding:0.35rem 0.55rem;border-radius:7px;border:1px solid var(--border-color);cursor:pointer;" onclick="openRideInspectorModal('${escapeHistoryHtml(s.id)}')">
                      <span><strong>${escapeHistoryHtml(s.date)}</strong> · ${escapeHistoryHtml(s.name)}</span>
                      <span>${s.np_watts ? Math.round(s.np_watts) + "W" : "--"} · EF ${s.ef ?? "--"} · ${Math.round(s.tss)} TSS</span>
                    </div>`
                  )
                  .join("")}
              </div>
            </div>`
          : ""
      }
    `;

    if (r.has_polyline && window.L) {
      requestAnimationFrame(() => {
        const mapEl = document.getElementById("rideInspectorMiniMap");
        if (!mapEl) return;
        if (historyState.inspectorMap) {
          historyState.inspectorMap.remove();
          historyState.inspectorMap = null;
        }
        const pts = decodeStravaPolyline(r.polyline);
        if (!pts.length) return;
        const m = L.map(mapEl, { zoomControl: true, attributionControl: false });
        const gKey = (typeof state !== "undefined" && state && state.googleMapsApiKey) || "";
        const tileCfg = typeof getTileLayerConfig === "function"
          ? getTileLayerConfig((typeof outdoorBaseLayerName !== "undefined" && outdoorBaseLayerName) || "google_roads", gKey)
          : { url: "https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", options: { maxZoom: 20, subdomains: "0123" } };
        L.tileLayer(tileCfg.url, tileCfg.options).addTo(m);
        const line = L.polyline(pts, { color: "#FF5E00", weight: 3.5, opacity: 0.9 }).addTo(m);
        m.fitBounds(line.getBounds(), { padding: [18, 18] });
        historyState.inspectorMap = m;
      });
    }
  } catch (err) {
    console.error("Failed to open ride inspector:", err);
    bodyEl.innerHTML = `<div style="padding:1rem;color:#EF4444;">Failed to load ride details.</div>`;
  }
}

function closeRideInspectorModal() {
  const modal = document.getElementById("modalRideInspector");
  if (modal) {
    modal.classList.remove("open");
    modal.style.display = "none";
  }
  if (historyState.inspectorMap) {
    historyState.inspectorMap.remove();
    historyState.inspectorMap = null;
  }
}
