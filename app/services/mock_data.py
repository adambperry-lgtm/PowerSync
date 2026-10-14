import datetime
import random
from typing import Dict, Any, List

def get_mock_whoop_data() -> Dict[str, Any]:
    today = datetime.date.today().isoformat()
    return {
        "date": today,
        "recovery_score": 78,
        "recovery_zone": "green", # green, yellow, red
        "hrv_rmssd": 68.4,
        "resting_heart_rate": 48,
        "sleep_performance": 88,
        "sleep_duration_hours": 7.8,
        "sleep_needed_hours": 8.1,
        "day_strain": 11.2,
        "trailing_7d_strain_avg": 11.4,
        "recent_weighted_strain": 12.1,
        "yesterday_strain": 14.2,
        "strain_profile": "Recent Surge (Yesterday Heavy)",
        "trailing_7d_high_strain_days": 2,
        "trailing_strains": [14.2, 11.5, 15.1, 9.8, 12.0, 10.4, 6.8],
        "sleep_stages": {
            "rem_hours": 1.9,
            "deep_hours": 2.1,
            "light_hours": 3.8
        },
        "trends": {
            "hrv_vs_baseline": "+6.2 ms (Optimal)",
            "rhr_vs_baseline": "-2 bpm (Lower/Restful)",
            "sleep_consistency": "92%"
        }
    }

def get_mock_strava_activities() -> List[Dict[str, Any]]:
    today = datetime.date.today()
    
    activities = [
        {
            "id": "strava_101",
            "name": "Morning Outdoor Endurance Spin",
            "sport_type": "Ride",
            "start_date": (today - datetime.timedelta(days=1)).strftime("%Y-%m-%dT07:30:00Z"),
            "moving_time_sec": 4200, # 1h 10m
            "distance_meters": 33200, # 33.2 km
            "total_elevation_gain": 240,
            "average_watts": 185,
            "weighted_average_watts": 198,
            "average_heartrate": 136,
            "max_heartrate": 158,
            "suffer_score": 58,
            "kilojoules": 777,
            "summary_polyline": "ginwFry|dMVHvZmBfMyAz@pAVLpBiERuAq@sE{DoG{AoFOaAEmEi@oKi@cCw@w@}D}@qHgCwFeFyDoIo@uCUoJ{@}DiBoC~@eFKcAaA}CJ]lDjBzDxHbH`HfJpK|DrHbNlPvL~PzSdOlBzBbApBlEhP`AdChSj\\`PtXpRlY|GxOlKrT`HhJ~CrFrDxHhCpIxJlWjAhB~GdEnGtEtA^dAGpB_A~JgH@c@cBoK@sBj@wCnB_Eh@m@dBg@t@BpDpBhAO`Bs@bAAxAx@rBzCr@ZlESf@i@AkBk@mCgC}EyCeBsB}FiCuAoL{@oD}AyA_Bs@uB{@uGg@yB}@mAwEcDgAwBo@yDj@qB@mAoCkT}BuMy@iCoEiImFqN}BeD{BwAwCu@{GqCmKoCIi@HoOKw@gOwTuGyISyCYg@k@Q{@XWnAHj@~@jBNfDS~EHdBzAlJfBfEV|AGp@e@`AqE`CmAnBUlENzA\\jAtBhBjAV`AIj@[~@yA~@{DJoCQeDaBwEa@uB_BkDsAyHU{CPeEMsE|@qANo@Aq@]eAD_@hBaH`Aw@xAFjEzETzDN|@`AzAZtAb@p@hA^xFZpDzA`Dp@fAr@fBhDzA~@jGlAfAKv@WBd@_AbDArA~@xBxDbG|BpHxAlUjE`QnCjNiDrBWAyAwHe@_B{E_JwFgO_C_DcCuAiMkEiJkC?uPQiAaCwCuHkL_J}LOmCc@w@g@Q{@^SnAP~@t@vAPzDQpCDpCvAjJf@bB~@dB\\pBGn@e@z@qE`CaAvAYrAEnDd@~Bf@t@pAx@rAZ~@InAoAf@gA`@mBPgC?sBUwBoAmDe@eCaBsDaBkKFeGOqEXq@d@KhEjFjMvRnCdDPfAGjOLj@ZVnJbChMpE|B`B~A|B`G|O`EhHhA|DlB|KnCbT@z@k@xAEn@h@hDb@nAv@dApE~Cp@|@p@dCv@vGj@dB`BhBpCvAhB`@tIb@nClAh@z@fAxDdDxBzBbE|@~D@l@Uh@kEd@q@MyBaDsBkAs@FsCdAu@KgDkBuCh@g@j@sBhEi@dDBhBtArJMfAsLvHyARkAUkHcFeFuCwAyAkJyU}CqK_BqDiFmJyHcKqL{V_@Oy@`AHfBpBpFf@dCTlEMpCUr@gCrD]hBSpDq@dBoHrKaBv@eAK[k@iCqKoAkC{CuCkY_SqH{JqCwE{DyNiAcCiMeOaB`BmEZwF`ByEfDaCz@qXfBQ_GqBsISiCyCax@"
        },
        {
            "id": "strava_102",
            "name": "Tempo Laps on Zwift",
            "sport_type": "VirtualRide",
            "start_date": (today - datetime.timedelta(days=2)).strftime("%Y-%m-%dT18:15:00Z"),
            "moving_time_sec": 3600, # 1h
            "distance_meters": 34100,
            "total_elevation_gain": 180,
            "average_watts": 215,
            "weighted_average_watts": 228,
            "average_heartrate": 149,
            "max_heartrate": 169,
            "suffer_score": 74,
            "kilojoules": 810
        },
        {
            "id": "strava_103",
            "name": "Easy Coffee Spin",
            "sport_type": "Ride",
            "start_date": (today - datetime.timedelta(days=4)).strftime("%Y-%m-%dT08:00:00Z"),
            "moving_time_sec": 3000, # 50m
            "distance_meters": 22500,
            "total_elevation_gain": 110,
            "average_watts": 145,
            "weighted_average_watts": 152,
            "average_heartrate": 122,
            "max_heartrate": 138,
            "suffer_score": 28,
            "kilojoules": 435,
            "summary_polyline": "ymnwFjz|dM_ETgBMgDx@Hj@~EjPlArGZ|Dh@nUQjAmB`Go@lEUJmFw@cKg@gGu@eA?{@LQP?LN|B?jBKtAO~@mA`DiAhBWHqBuDOCkAnEK`AqCt{@WvA]v@mB|AORfFnSF|@On@gBlCaBfAqAb@uErIkElFaDvEsBzBqA`AaHvDoBlBkBzBi@jAiAdGi@lB}CtIeEjMc@dAo@~@{AvAmC|AiBn@kJjBeAh@kAnA{AvD}CrJaB~JaAvIm@lB{BpD_DlCmJdKo@b@cB`@Qb@MbASj@yCxCmGlL@XNZbCxB|@lA`DxF`C~Cp@hAlDjLjKrZZvADzAWdFKjLKjDUzRYxAaGjOD^f@j@`AdBv@xCIhDuAlJOjC\\nGbBbK?dCWdCNXVLpAN^Pd@b@z@rATr@`CbLrExInDnK\\zAR~A?fAaAfGk@nMDlA~AlM\\fF\\xAlDzFv@~Bh@rDj@lGjApGd@dDpBtHjHth@HHd@IfOaGbE_A~IgDlNgErB}@h@k@lDoFdA}B|@}Cb@m@`Bo@lFcAzBmC`@]`EyAl@]lCuCjDkCfN_NrDwC`B_CrBoBz@uArEyJjGgQb@q@\\W`@KlL[jDS~HMt@BdB`@`CDtN_IjRaJxP_FtNkBjBAFgBn@yG?kBf@wJCaHV{HLaA~@{CfA{Ax@e@fCOZUQ}CA}CUkBeAsDeEaLqD}MCeADc@|AeEN_BG{@gBkLc@{BkAmDa@eDoBoIaCcI}AgEaAkA_DgBw@iAq@iBeCuKq@}Bw@_BeHmL{L{WeDeGkByEkDkEqEuDi@k@sJ{UiH_NaH_MaE_IwBsCiDqDaAcBoGuNmNsX_BwD?i@V[`AQbE{ArACbHVhDOtMkAJKD_@eBaJ[aA_f@s}@gCqEF_@Xa@rIgIx@a@jAAPIP{@`@yF`@iA`AeAfE}C^KFKQa@uBsAiCi@iAg@cAkAa@}AIsALkCV_Br@uFvBsGHsAEiB_@uLEkDYkD_B}HyCmK{@_CFY|Bs@lCJvM_AR^VxEAfAHJDKEq@P]|QkAPXbAzE`@t@~@T~BMh@f@Ll@f@xLH`@TNxGc@hAHHOB{ED[dAmAj@a@JYLDd@]zAhDx@jCvA|HxBzQc@fA_@Zw@RcACgBVgEjAkAh@oDhCmBv@mATuLv@QWKkGYiBuDyHqC}Ns@qAkBiC}A{^UcLOwA}@qB_EoDuAs@oBYQ@QZNhHjAfTRJtEW"
        },
        {
            "id": "strava_104",
            "name": "Weekend Long Group Ride",
            "sport_type": "Ride",
            "start_date": (today - datetime.timedelta(days=5)).strftime("%Y-%m-%dT08:30:00Z"),
            "moving_time_sec": 9000, # 2h 30m
            "distance_meters": 76800,
            "total_elevation_gain": 780,
            "average_watts": 195,
            "weighted_average_watts": 222,
            "average_heartrate": 144,
            "max_heartrate": 174,
            "suffer_score": 145,
            "kilojoules": 1750,
            "summary_polyline": "gfp`G~nw~LxUdQpKc@jn@vw@|Rho@M`p@kHxUge@uE{T`CcVgJ}qAoLqJwRwYn[ik@xpAomAfy@oXpB{b@_g@iZwCk`AhPud@lQsYyKws@m@{a@aRaU}YwXsLuXu`@sJ_o@xt@qdAkp@~F_|Asl@m\\zCek@cPue@tBsPiSs\\tNqSu\\od@iZm\\ug@gPkv@yKwUlJ_I}BgScOoXpQyNgAkbBwXcBm{@yo@yk@uEiB_KlJwdAzjAe_@fQvC~C_FsK}@bDcOrLoU}AuoB}fBXmQuNiNdDsOgGioDgQsIgNitAyl@}h@}a@mjAkTyS}KmIxAoJs_@oTcI_IypAgJcAw`@eb@cxB]eM{G?sK}L{G{IM}IhIyNi@}_Asm@_|@mPqdAu@w\\gHy}@{y@wTck@{e@si@gLyJcZwEk{As_B}hAos@s}@wOqSdMws@uYg~@sv@aYaLg_@{h@gfAqd@}RmWeRm@vIkj@aJyDsfBqCmp@_Pgb@fEcv@uGyjAhZ{p@~n@gDhY{MDbc@jA}GfFrd@t[`Xbx@tsAnh@|@f`@cWpZnNrFgDrZrMwG{GnVn@`e@mEdOfVjN~D`Tte@uF|@gKhGaDl@iQ~SdMfMfZ~H|BnGa^lFaGpa@_E~^zPjN`t@hTzAfOgJeHmf@wNMcDxHlHrJnAoCqB~BsE_GKqIzUBpD~c@`FxChBn\\bGtJkJuCxSzf@f\\z^pK~n@pK~OxgCpJn]}GdEwOdNUff@v^fl@xCrKhMt^pC~q@r`@zKeChVlErBjGxGe@lBpM|XsAfHxV\\bs@zzAfS~WyHreAcBrb@vHrj@dj@lOvFo`@``AhHzP{Unj@~I|i@h`@re@lsA`Sj^SkDf{@jRdG|Jb^`[fV`gAfj@vr@nPdEk_@jkAjRlLwAtSzR`QrEhQjb@~HmXjZ{WpPlI|Zlb@pdA~c@`Qng@f^lx@hqAx~@v]lRx|@|I~p@la@nc@`MlYlf@jc@vYjp@xKrZn@R|EtD[mRdPbBnmAiIlfA~Pv]nB~a@rq@Mj^i_@t_@hLlO{F|VbHblA~AhCjH{CdUfAlU`Vvd@bPxHt^fb@~ZqBhYjPznC{\\d`AD~g@c^xHoXhS}E`lAgx@fn@cuAjr@kt@~RcGvTwWnOuc@\\gTkJ{A"
        }
    ]
    return activities

def get_mock_weekly_stats() -> Dict[str, Any]:
    return {
        "total_hours": 6.8,
        "total_distance_km": 166.6,
        "total_distance_miles": 103.5,
        "total_elevation_m": 1310,
        "total_elevation_ft": 4298,
        "total_tss": 305,
        "acute_weighted_tss": 335,
        "yesterday_tss": 58,
        "yesterday_hours": 1.2,
        "load_profile": "Optimal / Balanced",
        "form_status": "Fresh & Prime",
        "form_description": "Load is well-balanced with recovery. Fatigue decays appropriately across the cycle."
    }
