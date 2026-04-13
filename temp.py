
#!/usr/bin/env python3
"""
스마트팜 딸기 수경재배 관수 시스템 — 최종 가상 데이터 생성기
==============================================================

설계 원칙
---------
- 야간 급액 없음
- 주간 순환/가압 + 부드러운 펄스 급액
- 연속 센서는 "마지막에 스무딩"하지 않고, 처음부터 상태(state)로 생성
- raw 65 호환 유지 (vibration_bandpower_high, cavitation_index 포함)
- 라벨은 normal_operation / maintenance / warning_state / sensor_issue / fault 로 분리
- 마지막 수정: 압력 대비 완화, 약품탱크 보충 패턴 현실화, 한글 주석/섹션 헤더 복구
"""

from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timedelta
from typing import Tuple

import numpy as np
import pandas as pd

# ╔══════════════════════════════════════════════════════════════╗
# ║  §0. 설정 (CONFIG) — 이 부분만 수정하면 됨                       ║
# ╚══════════════════════════════════════════════════════════════╝

DEFAULT_START = "2026-04-01"
DEFAULT_DAYS = 90
DEFAULT_SEED = 42
OUTPUT_DIR = "output"
CROP_STAGE = "flowering_fruiting"
NUM_ZONES = 3

ENV = {
    "photoperiod": (6, 20),     # 06:00~20:00
    "day_temp": (20.0, 25.0),
    "night_temp": (7.0, 10.0),
    "day_rh": (60.0, 70.0),
    "night_rh": (70.0, 85.0),
    "ppfd": (200.0, 400.0),
}

NUTRIENT = {
    "ec_target_base": 1.72,
    "ph_target_base": 5.98,
    "drain_ratio_pct": 25.0,
}

PUMP = {
    "rpm_nom": 2850.0,
    "flow_nom": 42.0,       # delivery flow during fertigation
    "Pdis_standby": 142.0,  # 주간 순환/대기 가압
    "Pdis_fert": 214.0,     # 급액 시 토출압 (기존보다 대비 완화)
    "Psuc_standby": 116.5,
    "Psuc_night": 104.0,
    "V_nom": 220.0,
    "I_standby": 0.85,
    "I_fert": 2.55,
    "cos_phi": 0.92,
    "vib_rms_standby": 0.65,
    "vib_rms_fert": 1.15,
}

FILTER = {
    "dp_clean": 11.5,
    "dp_warn": 17.0,
    "dp_clogged": 24.0,
    "turb_clean": 0.45,
}

CONTROL = {
    "start_after_sunrise_h": 1.0,
    "stop_before_sunset_h": 1.0,
    "events_per_day_min": 5,
    "events_per_day_max": 12,
    "event_duration_min": (8, 18),
    "event_gap_min": 35,
    "double_zone_probability": 0.20,
    "weekly_flush_minutes": 35,
    "acid_cleaning_minutes": 60,
    "acid_every_n_weeks": 2,
    "ramp_minutes": 4,          # smooth valve/pulse ramp
    "chem_refill_prob_workhour": 0.018,
    "chem_refill_soft_prob": 0.003,
}

FAULT_CONFIG = {
    "water_hammer_events_90d": (2, 4),
    "water_hammer_duration_min": (1, 2),
    "cavitation_events_90d": (0, 2),
    "cavitation_duration_min": (6, 14),
    "mild_dosing_bias_events_90d": (0, 2),
    "dosing_failure_events_90d": (0, 1),
    "sensor_dropout_events_90d": (1, 2),
    "sensor_dropout_duration_min": (8, 20),
    "sensor_drift_blocks_90d": (0, 1),
}

ZONE_HYDRAULIC = np.array([1.00, 0.97, 1.03], dtype=float)

EVENT_GROUP_POLICY = {
    "idle": ("normal_operation", 0, 0, 0),
    "normal_irrigation": ("normal_operation", 0, 0, 0),
    "tank_refill": ("normal_operation", 0, 0, 0),
    "setpoint_change": ("normal_operation", 0, 0, 0),
    "seasonal_shift": ("normal_operation", 0, 0, 0),

    "weekly_flush": ("maintenance", 0, 0, 0),
    "acid_cleaning": ("maintenance", 0, 0, 0),

    "filter_fouling_warning": ("warning_state", 0, 1, 1),
    "bearing_wear_warning": ("warning_state", 0, 1, 1),
    "mild_dosing_bias": ("warning_state", 0, 1, 1),

    "sensor_drift": ("sensor_issue", 0, 1, 1),
    "sensor_dropout": ("sensor_issue", 0, 1, 1),

    "filter_clog": ("fault", 1, 1, 2),
    "bearing_wear_fault": ("fault", 1, 1, 2),
    "cavitation": ("fault", 1, 1, 2),
    "water_hammer": ("fault", 1, 1, 2),
    "dosing_failure": ("fault", 1, 1, 2),
    "severe_clog_shutdown": ("fault", 1, 1, 3),
}


# ╔══════════════════════════════════════════════════════════════╗
# ║  §1. 공통 유틸리티                                              ║
# ╚══════════════════════════════════════════════════════════════╝

def clamp(x, lo, hi):
    return np.minimum(np.maximum(x, lo), hi)


def es_kpa(temp_c):
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def make_rng(seed: int):
    return np.random.default_rng(seed)


def make_time_index(start_str: str, n_days: int):
    start = datetime.strptime(start_str, "%Y-%m-%d")
    N = n_days * 1440
    ts = np.array([start + timedelta(minutes=int(i)) for i in range(N)])
    hour = np.array([t.hour for t in ts], dtype=int)
    minute_of_day = np.arange(N) % 1440
    day_index = np.arange(N) // 1440 + 1
    return ts, hour, minute_of_day, day_index, N


def choose_count_for_horizon(rng, span_90d_range: Tuple[int, int], n_days: int):
    lo, hi = span_90d_range
    scale = n_days / 90.0
    lo2 = int(np.floor(lo * scale))
    hi2 = int(np.ceil(hi * scale))
    hi2 = max(hi2, lo2)
    return int(rng.integers(lo2, hi2 + 1))


def pulse_envelope(length: int, ramp: int):
    if length <= 1:
        return np.ones(max(length, 1))
    ramp = max(1, min(ramp, length // 2))
    env = np.ones(length)
    x = np.linspace(0, np.pi / 2, ramp)
    rise = np.sin(x) ** 2
    fall = rise[::-1]
    env[:ramp] = rise
    env[-ramp:] = np.minimum(env[-ramp:], fall)
    return env


# ╔══════════════════════════════════════════════════════════════╗
# ║  §2. 실내 환경 생성                                            ║
# ║  - 주야 온도 / 습도 / CO₂ / 광량 / VPD                           ║
# ╚══════════════════════════════════════════════════════════════╝

def gen_environment(hour, minute_of_day, day_index, N, rng):
    ph_start, ph_end = ENV["photoperiod"]
    lights_on = ((hour >= ph_start) & (hour < ph_end)).astype(int)
    hod = hour + (minute_of_day % 60) / 60.0
    phase = np.clip((hod - ph_start) / (ph_end - ph_start), 0, 1)
    sun_shape = np.sin(np.pi * phase)
    sun_shape = np.where(lights_on == 1, np.maximum(sun_shape, 0), 0)

    context_type = np.array(["steady_operation"] * N, dtype=object)
    n_days = int(day_index.max())
    if n_days >= 10:
        hot_start = int(rng.integers(5, max(6, n_days - 5)))
        hot_len = int(rng.integers(2, 5))
        context_type[(day_index >= hot_start) & (day_index < hot_start + hot_len)] = "hot_dry_spell"
        if n_days >= 20:
            cool_start = int(rng.integers(6, max(7, n_days - 4)))
            cool_len = int(rng.integers(1, 3))
            context_type[(day_index >= cool_start) & (day_index < cool_start + cool_len)] = "cool_humid_spell"

    ppfd = lights_on * (ENV["ppfd"][0] + (ENV["ppfd"][1] - ENV["ppfd"][0]) * sun_shape)
    ppfd += lights_on * rng.normal(0, 10, N)
    ppfd = clamp(ppfd, 0, 450)

    day_temp_mid = 22.2 + 2.1 * sun_shape
    night_temp_mid = 8.3 + 0.7 * np.sin(2 * np.pi * hod / 24.0)
    temp = np.where(lights_on == 1, day_temp_mid, night_temp_mid)

    day_rh_mid = 66.0 - 3.2 * sun_shape
    night_rh_mid = 79.5 + 1.2 * np.sin(2 * np.pi * (hod - 2) / 24.0)
    rh = np.where(lights_on == 1, day_rh_mid, night_rh_mid)

    hot = context_type == "hot_dry_spell"
    cool = context_type == "cool_humid_spell"
    temp[hot] += 1.5
    rh[hot] -= 6.5
    temp[cool] -= 0.8
    rh[cool] += 4.5

    season_frac = np.arange(N) / max(N - 1, 1)
    ext_temp = 16.5 + 8.5 * season_frac + 4.8 * np.sin(2 * np.pi * (hod - 14) / 24.0) + 0.9 * np.sin(2 * np.pi * np.arange(N) / (7 * 1440))
    ext_temp += rng.normal(0, 0.45, N)
    ext_rh = 58 + 10 * np.sin(2 * np.pi * (hod - 4) / 24.0) + rng.normal(0, 1.8, N)

    temp += 0.10 * (ext_temp - 20) + 0.25 * np.sin(2 * np.pi * day_index / 7.0) + rng.normal(0, 0.15, N)
    rh += -0.45 * (temp - 15) + rng.normal(0, 1.3, N)

    temp = clamp(temp, 6.0, 27.5)
    rh = clamp(rh, 48.0, 92.0)

    co2 = np.where(lights_on == 1, 960 + 110 * sun_shape + rng.normal(0, 16, N),
                   500 + rng.normal(0, 14, N))
    co2 = clamp(co2, 380, 1300)

    svp = es_kpa(temp)
    vpd = (1 - rh / 100.0) * svp

    vent = ((rh > 85) | (temp > 26)).astype(int)
    dehum = (rh > 82).astype(int)

    ppfd_by_day = pd.DataFrame({"day_index": day_index, "ppfd": ppfd}).groupby("day_index")["ppfd"].sum() * 60 / 1e6
    dli = np.array([ppfd_by_day.loc[int(d)] for d in day_index])

    return {
        "context_type": context_type,
        "lights_on": lights_on,
        "light_ppfd_umol_m2_s": np.round(ppfd, 1),
        "daily_light_integral_mol_m2_d": np.round(dli, 4),
        "air_temp_c": np.round(temp, 2),
        "relative_humidity_pct": np.round(rh, 2),
        "co2_ppm": np.round(co2, 1),
        "vpd_kpa": np.round(vpd, 3),
        "external_temp_c": np.round(ext_temp, 2),
        "external_humidity_pct": np.round(ext_rh, 2),
        "ventilation_state": vent,
        "dehumidifier_state": dehum,
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §3. 운영 컨텍스트 이벤트                                       ║
# ║  - hot_dry_spell / cool_humid_spell / setpoint_change         ║
# ╚══════════════════════════════════════════════════════════════╝

def build_background_context(day_index, N, rng):
    context_event = np.array(["none"] * N, dtype=object)
    n_days = int(day_index.max())
    if n_days >= 40:
        start_day = int(rng.integers(max(15, n_days // 3), max(16, n_days - 15)))
        length = int(rng.integers(5, 9))
        mask = (day_index >= start_day) & (day_index < start_day + length)
        context_event[mask] = "setpoint_change"
    return context_event


# ╔══════════════════════════════════════════════════════════════╗
# ║  §4. 관수 스케줄 생성                                           ║
# ║  - 하루 5~12회 펄스 이벤트                                      ║
# ║  - 8~18분 지속, 4분 ramp, 이벤트 간 최소 35분 간격              ║
# ╚══════════════════════════════════════════════════════════════╝

def build_irrigation_schedule(hour, minute_of_day, day_index, env, rng):
    N = len(hour)
    pump_on = np.zeros(N, dtype=int)  # daytime circulation/pressurization
    fertigation_on = np.zeros(N, dtype=int)
    fertigation_demand_pct = np.zeros(N)
    event_id = np.full(N, -1, dtype=int)
    zone1 = np.zeros(N, dtype=int)
    zone2 = np.zeros(N, dtype=int)
    zone3 = np.zeros(N, dtype=int)

    ph_start, ph_end = ENV["photoperiod"]
    start_h = ph_start + CONTROL["start_after_sunrise_h"]
    stop_h = ph_end - CONTROL["stop_before_sunset_h"]
    hod = hour + (minute_of_day % 60) / 60.0
    daytime = (hod >= start_h) & (hod <= stop_h)
    pump_on[daytime] = 1

    zone_cursor = 0
    eid = 0
    events_per_day = []

    for d in range(1, int(day_index.max()) + 1):
        mask = day_index == d
        idx_day = np.where(mask)[0]
        if len(idx_day) == 0:
            continue
        active_idx = idx_day[daytime[mask]]
        if len(active_idx) == 0:
            events_per_day.append(0)
            continue

        mean_ppfd = float(np.mean(env["light_ppfd_umol_m2_s"][mask]))
        mean_vpd = float(np.mean(env["vpd_kpa"][mask]))
        target = 5 + 0.012 * mean_ppfd + 2.0 * max(mean_vpd - 0.55, 0)
        if np.any(env["context_type"][mask] == "hot_dry_spell"):
            target += 1.0
        n_events = int(round(clamp(target, CONTROL["events_per_day_min"], CONTROL["events_per_day_max"])))
        events_per_day.append(n_events)

        window = len(active_idx)
        anchors = np.linspace(0, window - 1, n_events, dtype=int)
        jitter = rng.integers(-20, 21, size=n_events)
        starts = np.clip(anchors + jitter, 0, window - 1)
        starts = np.sort(np.unique(starts))
        while len(starts) < n_events:
            starts = np.sort(np.unique(np.concatenate([starts, rng.choice(np.arange(window), size=1)])))
        starts = starts[:n_events]

        last_end = -10**9
        for s in starts:
            base_row = active_idx[int(s)]
            if base_row < last_end + CONTROL["event_gap_min"]:
                base_row = last_end + CONTROL["event_gap_min"]
                if base_row >= active_idx[-1]:
                    continue
            duration = int(rng.integers(CONTROL["event_duration_min"][0], CONTROL["event_duration_min"][1] + 1))
            rows = np.arange(base_row, min(base_row + duration, N))
            if len(rows) == 0:
                continue
            env_pulse = pulse_envelope(len(rows), CONTROL["ramp_minutes"])
            fertigation_on[rows] = 1
            fertigation_demand_pct[rows] = np.maximum(fertigation_demand_pct[rows], env_pulse)
            event_id[rows] = eid

            primary = zone_cursor % NUM_ZONES
            zone_cursor += 1
            active_zones = [primary]
            if rng.random() < CONTROL["double_zone_probability"]:
                secondary = (primary + int(rng.integers(1, NUM_ZONES))) % NUM_ZONES
                if secondary not in active_zones:
                    active_zones.append(secondary)

            for z in active_zones:
                if z == 0:
                    zone1[rows] = 1
                elif z == 1:
                    zone2[rows] = 1
                else:
                    zone3[rows] = 1
            eid += 1
            last_end = rows[-1]

    return {
        "pump_on": pump_on,
        "fertigation_on": fertigation_on,
        "fertigation_demand_pct": np.round(fertigation_demand_pct, 3),
        "event_id": event_id,
        "zone1_valve_on": zone1,
        "zone2_valve_on": zone2,
        "zone3_valve_on": zone3,
        "events_per_day_target": np.repeat(events_per_day, 1440)[:N],
        "day_fert_start_hour": np.full(N, start_h),
        "day_fert_stop_hour": np.full(N, stop_h),
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §5. 정기 점검 / 세정 이벤트                                    ║
# ║  - weekly flush                                                ║
# ║  - acid cleaning (기본 2주 1회)                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def build_maintenance_schedule(day_index, rng):
    N = len(day_index)
    weekly_flush_on = np.zeros(N, dtype=int)
    acid_cleaning_on = np.zeros(N, dtype=int)
    n_weeks = int(np.ceil(day_index.max() / 7.0))
    for week in range(1, n_weeks + 1):
        day0 = week * 7
        flush_start = (day0 - 1) * 1440 + 18 * 60 + int(rng.integers(-15, 16))
        flush_end = min(flush_start + CONTROL["weekly_flush_minutes"], N)
        if 0 <= flush_start < N:
            weekly_flush_on[flush_start:flush_end] = 1
        if week % CONTROL["acid_every_n_weeks"] == 0:
            acid_start = (day0 - 1) * 1440 + 19 * 60 + int(rng.integers(-10, 11))
            acid_end = min(acid_start + CONTROL["acid_cleaning_minutes"], N)
            if 0 <= acid_start < N:
                acid_cleaning_on[acid_start:acid_end] = 1
    return {"weekly_flush_on": weekly_flush_on, "acid_cleaning_on": acid_cleaning_on}


# ╔══════════════════════════════════════════════════════════════╗
# ║  §6. 이상 / 경고 이벤트 스케줄                                  ║
# ║  - water_hammer / cavitation / dosing / sensor issue          ║
# ╚══════════════════════════════════════════════════════════════╝

def build_fault_schedule(pump_on, N, n_days, rng):
    water_hammer_on = np.zeros(N, dtype=int)
    cavitation_on = np.zeros(N, dtype=int)
    mild_dosing_bias_on = np.zeros(N, dtype=int)
    dosing_failure_on = np.zeros(N, dtype=int)
    sensor_dropout_on = np.zeros(N, dtype=int)
    sensor_dropout_target = np.array(["none"] * N, dtype=object)
    sensor_drift_on = np.zeros(N, dtype=int)

    on_idx = np.where(pump_on == 1)[0]
    if len(on_idx) == 0:
        return {
            "water_hammer_on": water_hammer_on,
            "cavitation_on": cavitation_on,
            "mild_dosing_bias_on": mild_dosing_bias_on,
            "dosing_failure_on": dosing_failure_on,
            "sensor_dropout_on": sensor_dropout_on,
            "sensor_dropout_target": sensor_dropout_target,
            "sensor_drift_on": sensor_drift_on,
        }

    n_wh = choose_count_for_horizon(rng, FAULT_CONFIG["water_hammer_events_90d"], n_days)
    for _ in range(n_wh):
        start = int(rng.choice(on_idx[1440:] if len(on_idx) > 1440 else on_idx))
        dur = int(rng.integers(FAULT_CONFIG["water_hammer_duration_min"][0], FAULT_CONFIG["water_hammer_duration_min"][1] + 1))
        water_hammer_on[start:min(start + dur, N)] = 1

    n_cav = choose_count_for_horizon(rng, FAULT_CONFIG["cavitation_events_90d"], n_days)
    for _ in range(n_cav):
        start = int(rng.choice(on_idx))
        dur = int(rng.integers(FAULT_CONFIG["cavitation_duration_min"][0], FAULT_CONFIG["cavitation_duration_min"][1] + 1))
        cavitation_on[start:min(start + dur, N)] = 1

    n_bias = choose_count_for_horizon(rng, FAULT_CONFIG["mild_dosing_bias_events_90d"], n_days)
    for _ in range(n_bias):
        start = int(rng.choice(on_idx))
        dur = int(rng.integers(120, 360))
        mild_dosing_bias_on[start:min(start + dur, N)] = 1

    n_fail = choose_count_for_horizon(rng, FAULT_CONFIG["dosing_failure_events_90d"], n_days)
    for _ in range(n_fail):
        start = int(rng.choice(on_idx))
        dur = int(rng.integers(20, 80))
        dosing_failure_on[start:min(start + dur, N)] = 1

    n_drop = choose_count_for_horizon(rng, FAULT_CONFIG["sensor_dropout_events_90d"], n_days)
    dropout_cols = ["suction_pressure_kpa", "flow_rate_l_min", "bearing_vibration_rms_mm_s", "mix_ec_ds_m"]
    for _ in range(n_drop):
        start = int(rng.choice(on_idx))
        dur = int(rng.integers(FAULT_CONFIG["sensor_dropout_duration_min"][0], FAULT_CONFIG["sensor_dropout_duration_min"][1] + 1))
        sensor_dropout_on[start:min(start + dur, N)] = 1
        sensor_dropout_target[start:min(start + dur, N)] = rng.choice(dropout_cols)

    n_drift = choose_count_for_horizon(rng, FAULT_CONFIG["sensor_drift_blocks_90d"], n_days)
    if n_drift > 0 and n_days >= 20:
        start_day = int(rng.integers(max(12, n_days // 3), max(13, n_days - 8)))
        dur_day = int(rng.integers(1, 3))
        start = (start_day - 1) * 1440
        end = min(start + dur_day * 1440, N)
        sensor_drift_on[start:end] = 1

    return {
        "water_hammer_on": water_hammer_on,
        "cavitation_on": cavitation_on,
        "mild_dosing_bias_on": mild_dosing_bias_on,
        "dosing_failure_on": dosing_failure_on,
        "sensor_dropout_on": sensor_dropout_on,
        "sensor_dropout_target": sensor_dropout_target,
        "sensor_drift_on": sensor_drift_on,
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §7. 원수탱크 / 공급부                                          ║
# ╚══════════════════════════════════════════════════════════════╝

def gen_tank(schedule, env_temp, N, rng):
    level = np.full(N, 92.0)
    refill = np.zeros(N, dtype=int)
    for i in range(1, N):
        drain = 0.004 * schedule["pump_on"][i] + 0.050 * schedule["fertigation_demand_pct"][i]
        evap = 0.0014 + 0.00015 * max(env_temp[i] - 15, 0)
        level[i] = level[i - 1] - drain - evap + rng.normal(0, 0.003)
        dow = (i // 1440) % 7
        hod = (i % 1440) / 60.0
        if level[i] < 35 and dow < 5 and 9 <= hod <= 17 and rng.random() < 0.06:
            level[i] += rng.uniform(18, 30)
            refill[i] = 1
        level[i] = float(clamp(level[i], 15, 98))
    level_rate = np.diff(level, prepend=level[0])
    water_temp = 16.8 + 0.16 * (env_temp - 15) + rng.normal(0, 0.06, N)
    raw_ec = 0.27 + 0.012 * np.sin(2 * np.pi * np.arange(N) / (14 * 1440)) + rng.normal(0, 0.004, N)
    raw_ph = 7.08 + rng.normal(0, 0.030, N)
    tank_press = 101.3 + 0.098 * (level / 100) * 50 + rng.normal(0, 0.12, N)
    return {
        "raw_tank_level_pct": np.round(level, 1),
        "raw_tank_level_change_pct_per_min": np.round(level_rate, 4),
        "raw_water_temp_c": np.round(water_temp, 2),
        "raw_water_ec_ds_m": np.round(clamp(raw_ec, 0.15, 0.5), 3),
        "raw_water_ph": np.round(clamp(raw_ph, 6.8, 7.5), 2),
        "raw_tank_pressure_kpa": np.round(tank_press, 2),
        "tank_refill_on": refill,
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §8. 펌프 + 필터 + 모터 동특성                                  ║
# ║  수학식 핵심                                                    ║
# ║   - P_motor = V × I × cosφ / 1000                              ║
# ║   - P_hyd   = ΔP × Q / 60000                                   ║
# ║   - η_w2w   = P_hyd / P_motor                                  ║
# ║  생성 방식                                                      ║
# ║   - target 기반 상태 갱신: new = old + α(target-old) + noise   ║
# ╚══════════════════════════════════════════════════════════════╝

def simulate_pump_filter_mechanics(schedule, maintenance, env, context_event, faults, N, rng):
    pump_on = schedule["pump_on"].astype(bool)
    demand = schedule["fertigation_demand_pct"]
    flush_on = maintenance["weekly_flush_on"].astype(bool)
    acid_on = maintenance["acid_cleaning_on"].astype(bool)
    cav_on = faults["cavitation_on"].astype(bool)
    wh_on = faults["water_hammer_on"].astype(bool)

    fouling = np.zeros(N)
    wear = np.zeros(N)
    flow = np.zeros(N)
    psuc = np.full(N, PUMP["Psuc_night"])
    pdis = np.full(N, 102.0)
    curr = np.full(N, 0.08)
    rpm = np.zeros(N)
    vib = np.full(N, 0.18)
    acoustic = np.full(N, 40.0)
    mtemp = np.full(N, 22.8)
    btemp = np.full(N, 23.8)
    band_hi = np.full(N, 0.35)
    cav_idx = np.zeros(N)

    mode_shift = np.zeros(N)
    sp_mask = context_event == "setpoint_change"
    if sp_mask.any():
        idx = np.where(sp_mask)[0]
        start = idx[0]
        end = min(start + 6 * 60, N)
        mode_shift[start:end] = np.linspace(0, 1, end - start)
        if end < N:
            mode_shift[end:idx[-1] + 1] = 1.0

    for i in range(1, N):
        fouling[i] = fouling[i - 1]
        if demand[i] > 0.02:
            fouling[i] += 0.00016 + 0.00008 * max(env["vpd_kpa"][i] - 0.7, 0)
        elif pump_on[i]:
            fouling[i] += 0.00003
        if flush_on[i]:
            fouling[i] *= 0.92
        if acid_on[i]:
            fouling[i] *= 0.55
        fouling[i] = float(clamp(fouling[i], 0.02, 1.0))

        wear[i] = wear[i - 1]
        if i > int(0.70 * N) and pump_on[i]:
            wear[i] += 0.00040
        wear[i] = float(clamp(wear[i], 0.0, 1.0))

        base_flow_nom = PUMP["flow_nom"] + 4.0 * mode_shift[i]
        base_pdis_fert = PUMP["Pdis_fert"] + 8.0 * mode_shift[i]

        if pump_on[i]:
            flow_target = demand[i] * base_flow_nom * (1.0 - 0.13 * fouling[i] - 0.04 * wear[i])
            if cav_on[i]:
                flow_target *= 0.92
            flow[i] = max(0.0, flow[i - 1] + 0.32 * (flow_target - flow[i - 1]) + rng.normal(0, 0.14))

            psuc_target = PUMP["Psuc_standby"] - 2.8 * fouling[i] - 8.0 * cav_on[i]
            # 압력 대비를 너무 크게 만들지 않도록 standby↔fert gap 축소
            pdis_target = PUMP["Pdis_standby"] + demand[i] * (base_pdis_fert - PUMP["Pdis_standby"]) + 7.5 * fouling[i]
            if wh_on[i]:
                pdis_target *= rng.uniform(1.08, 1.16)

            # 응답을 조금 더 느리게 해서 10분 EDA에서 cliff 느낌 완화
            psuc[i] = psuc[i - 1] + 0.16 * (psuc_target - psuc[i - 1]) + rng.normal(0, 0.15)
            pdis[i] = pdis[i - 1] + 0.18 * (pdis_target - pdis[i - 1]) + rng.normal(0, 0.28)

            curr_target = PUMP["I_standby"] + demand[i] * (PUMP["I_fert"] - PUMP["I_standby"]) + 0.15 * fouling[i] + 0.10 * wear[i]
            if cav_on[i]:
                curr_target += 0.08
            curr[i] = max(0.05, curr[i - 1] + 0.22 * (curr_target - curr[i - 1]) + rng.normal(0, 0.010))

            rpm_target = PUMP["rpm_nom"] - 35 * (1 - demand[i])
            rpm[i] = max(0.0, rpm[i - 1] + 0.30 * (rpm_target - rpm[i - 1]) + rng.normal(0, 6))

            vib_target = PUMP["vib_rms_standby"] + demand[i] * (PUMP["vib_rms_fert"] - PUMP["vib_rms_standby"]) + 0.18 * fouling[i] + 0.95 * wear[i]
            if cav_on[i]:
                vib_target += 1.1
            if wh_on[i]:
                vib_target *= rng.uniform(1.7, 2.4)
            vib[i] = max(0.10, vib[i - 1] + 0.20 * (vib_target - vib[i - 1]) + rng.normal(0, 0.020))

            acoustic_target = 52 + demand[i] * 9 + 1.4 * fouling[i] + 2.0 * wear[i] + 2.5 * cav_on[i]
            if wh_on[i]:
                acoustic_target += rng.uniform(4, 7)
            acoustic[i] = max(38.0, acoustic[i - 1] + 0.20 * (acoustic_target - acoustic[i - 1]) + rng.normal(0, 0.14))

            heat = 0.024 * (curr[i] ** 2 / max(PUMP["I_fert"] ** 2, 1e-6))
            cool = 0.018 * (mtemp[i - 1] - (21.5 + 0.12 * env["air_temp_c"][i])) / 10.0
            mtemp[i] = mtemp[i - 1] + heat - cool + rng.normal(0, 0.016)
        else:
            flow[i] = max(0.0, flow[i - 1] * 0.78 + rng.normal(0, 0.008))
            psuc[i] = psuc[i - 1] + 0.10 * (PUMP["Psuc_night"] - psuc[i - 1]) + rng.normal(0, 0.06)
            pdis[i] = pdis[i - 1] + 0.10 * (106.0 - pdis[i - 1]) + rng.normal(0, 0.08)
            curr[i] = max(0.05, curr[i - 1] + 0.15 * (0.08 - curr[i - 1]) + rng.normal(0, 0.004))
            rpm[i] = max(0.0, rpm[i - 1] * 0.55 + rng.normal(0, 3))
            vib[i] = max(0.12, vib[i - 1] + 0.18 * (0.18 - vib[i - 1]) + rng.normal(0, 0.006))
            acoustic[i] = max(38.0, acoustic[i - 1] + 0.18 * (40.0 - acoustic[i - 1]) + rng.normal(0, 0.06))
            mtemp[i] = mtemp[i - 1] + 0.06 * ((21.5 + 0.12 * env["air_temp_c"][i]) - mtemp[i - 1]) + rng.normal(0, 0.012)

        btemp[i] = mtemp[i] + 2.0 + 3.4 * wear[i] + max(vib[i] - 1.0, 0) * 0.32 + rng.normal(0, 0.03)
        if btemp[i] <= mtemp[i]:
            btemp[i] = mtemp[i] + 0.6

        band_target = 0.35 + 0.18 * fouling[i] + 0.30 * wear[i]
        if cav_on[i]:
            band_target += 1.2
        if wh_on[i]:
            band_target += 0.6
        band_hi[i] = max(0.05, band_hi[i - 1] + 0.24 * (band_target - band_hi[i - 1]) + rng.normal(0, 0.020))
        cav_idx[i] = np.clip(0.55 * np.clip((PUMP["Psuc_standby"] - psuc[i]) / 18.0, 0, 1) +
                             0.45 * np.clip((band_hi[i] - 0.45) / 1.8, 0, 1), 0, 1)

    dp = pdis - psuc
    volt = np.where(pump_on, PUMP["V_nom"] + rng.normal(0, 0.8, N), PUMP["V_nom"])
    pmotor = volt * curr * PUMP["cos_phi"] / 1000.0
    phyd = np.where(flow > 0.01, dp * flow / 60000.0, 0.0)
    eta = np.where(pmotor > 0.01, phyd / pmotor, 0.0)

    filter_in = np.where(pump_on, pdis + rng.normal(0, 0.25, N), pdis)
    filter_dp = np.where(
        pump_on,
        3.0 + 7.8 * np.clip(demand, 0, 1) + 9.0 * fouling + rng.normal(0, 0.22, N),
        rng.uniform(0.8, 1.4, N)
    )
    filter_dp = clamp(filter_dp, 0, 40)
    filter_out = filter_in - filter_dp
    clogging_index = clamp((filter_dp - FILTER["dp_clean"]) / max(FILTER["dp_clogged"] - FILTER["dp_clean"], 1e-6), 0, 1)
    scale_factor = clamp(0.17 + 0.45 * fouling + rng.normal(0, 0.002, N), 0, 1.5)
    turbidity = clamp(np.where(pump_on, FILTER["turb_clean"] + 0.9 * fouling + rng.normal(0, 0.03, N), 0.0), 0, 8)

    return {
        "pump_rpm": np.round(rpm, 1),
        "flow_rate_l_min": np.round(clamp(flow, 0, PUMP["flow_nom"] * 1.35), 2),
        "suction_pressure_kpa": np.round(psuc, 2),
        "discharge_pressure_kpa": np.round(pdis, 2),
        "differential_pressure_kpa": np.round(dp, 2),
        "motor_current_a": np.round(clamp(curr, 0, 5), 3),
        "voltage_v": np.round(volt, 2),
        "motor_power_kw": np.round(pmotor, 4),
        "hydraulic_power_kw": np.round(phyd, 4),
        "wire_to_water_efficiency": np.round(eta, 4),
        "acoustic_db": np.round(acoustic, 2),
        "bearing_vibration_rms_mm_s": np.round(vib, 3),
        "bearing_vibration_peak_mm_s": np.round(vib * rng.uniform(1.8, 2.3, N), 3),
        "vibration_bandpower_high": np.round(clamp(band_hi, 0, 10), 3),
        "cavitation_index": np.round(cav_idx, 3),
        "motor_temperature_c": np.round(mtemp, 2),
        "bearing_temperature_c": np.round(btemp, 2),
        "temp_slope_c_per_s": np.round(np.diff(mtemp, prepend=mtemp[0]) / 60.0, 5),
        "filter_pressure_in_kpa": np.round(filter_in, 2),
        "filter_pressure_out_kpa": np.round(filter_out, 2),
        "filter_delta_p_kpa": np.round(filter_dp, 2),
        "clogging_index": np.round(clogging_index, 4),
        "scale_factor": np.round(scale_factor, 4),
        "turbidity_ntu": np.round(turbidity, 3),
        "bearing_wear_index": np.round(wear, 4),
        "fouling_index_hidden": np.round(fouling, 4),
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §9. 혼합기 / 양액 상태                                         ║
# ║  - mix EC / pH / 온도는 탱크 상태값으로 천천히 움직임            ║
# ║  - 펌프 OFF여도 0으로 붕괴하지 않음                             ║
# ╚══════════════════════════════════════════════════════════════╝

def simulate_solution_states(schedule, maintenance, tank, context_event, faults, mechanics, N, rng):
    pump_on = schedule["pump_on"].astype(bool)
    fert_on = schedule["fertigation_on"].astype(bool)
    demand = schedule["fertigation_demand_pct"]
    mild_bias = faults["mild_dosing_bias_on"].astype(bool)
    failure = faults["dosing_failure_on"].astype(bool)

    target_ec = np.full(N, NUTRIENT["ec_target_base"])
    target_ph = np.full(N, NUTRIENT["ph_target_base"])

    sp_mask = context_event == "setpoint_change"
    if sp_mask.any():
        idx = np.where(sp_mask)[0]
        start = idx[0]
        ramp_end = min(start + 6 * 60, N)
        new_target = 1.84 + rng.uniform(-0.03, 0.03)
        target_ec[start:ramp_end] = np.linspace(NUTRIENT["ec_target_base"], new_target, ramp_end - start)
        if ramp_end < N:
            target_ec[ramp_end:idx[-1] + 1] = new_target

    mix_ec = np.full(N, NUTRIENT["ec_target_base"])
    mix_ph = np.full(N, NUTRIENT["ph_target_base"])
    mix_temp = np.full(N, float(tank["raw_water_temp_c"][0] + 0.45))
    dos_a = np.zeros(N)
    dos_b = np.zeros(N)
    dos_acid = np.zeros(N)
    agit_rpm = np.zeros(N)
    agit_curr = np.zeros(N)

    for i in range(1, N):
        ec_bias = 0.0
        ph_bias = 0.0
        if mild_bias[i]:
            ec_bias += 0.06 * np.sin(2 * np.pi * i / 180.0)
            ph_bias += 0.05
        if failure[i]:
            ec_bias += 0.14
            ph_bias += 0.16

        ec_t = target_ec[i] + ec_bias
        ph_t = target_ph[i] + ph_bias

        if pump_on[i]:
            mix_ec[i] = mix_ec[i - 1] + 0.05 * (ec_t - mix_ec[i - 1]) + rng.normal(0, 0.003)
            mix_ph[i] = mix_ph[i - 1] + 0.04 * (ph_t - mix_ph[i - 1]) + rng.normal(0, 0.004)
            mix_temp[i] = mix_temp[i - 1] + 0.03 * ((tank["raw_water_temp_c"][i] + 0.35) - mix_temp[i - 1]) + rng.normal(0, 0.010)
        else:
            mix_ec[i] = mix_ec[i - 1] + 0.008 * (ec_t - mix_ec[i - 1]) + rng.normal(0, 0.0012)
            mix_ph[i] = mix_ph[i - 1] + 0.008 * (ph_t - mix_ph[i - 1]) + rng.normal(0, 0.0018)
            mix_temp[i] = mix_temp[i - 1] + 0.02 * (tank["raw_water_temp_c"][i] - mix_temp[i - 1]) + rng.normal(0, 0.008)

        if fert_on[i]:
            flow_factor = mechanics["flow_rate_l_min"][i] / max(PUMP["flow_nom"], 1e-6)
            dos_a[i] = clamp(4.0 * flow_factor + 0.8 * max(mix_ec[i] - 1.60, 0) + rng.normal(0, 0.10), 0, 10)
            dos_b[i] = clamp(3.4 * flow_factor + 0.7 * max(mix_ec[i] - 1.60, 0) + rng.normal(0, 0.10), 0, 10)
            dos_acid[i] = clamp(0.9 * flow_factor + 0.8 * max(mix_ph[i] - 5.9, 0) + rng.normal(0, 0.05), 0, 5)
            agit_rpm[i] = 340 + 40 * demand[i] + rng.normal(0, 6)
            agit_curr[i] = 0.42 + 0.04 * demand[i] + rng.normal(0, 0.010)
        else:
            dos_a[i] = 0
            dos_b[i] = 0
            dos_acid[i] = 0
            agit_rpm[i] = (260 + rng.normal(0, 4)) if pump_on[i] else 0
            agit_curr[i] = (0.18 + rng.normal(0, 0.010)) if pump_on[i] else 0

    pid_ec = mix_ec - target_ec
    pid_ph = mix_ph - target_ph
    uniformity = clamp(np.abs(pid_ec) * 0.7 + np.abs(pid_ph) * 0.3 + rng.normal(0.01, 0.0015, N), 0, 1)
    mix_eff = np.where(pump_on, clamp(0.95 - 0.05 * np.abs(pid_ec) + rng.normal(0, 0.006, N), 0.82, 0.99), 0.0)
    drainage_ratio = clamp(NUTRIENT["drain_ratio_pct"] + rng.normal(0, 1.0, N), 15, 38)

    drain_multiplier = np.where(
        maintenance["weekly_flush_on"].astype(bool) | maintenance["acid_cleaning_on"].astype(bool),
        rng.uniform(0.96, 1.02, N),
        rng.uniform(1.02, 1.10, N)
    )
    leach_mask = rng.random(N) < 0.15
    drain_multiplier[leach_mask] = rng.uniform(0.98, 1.00, leach_mask.sum())
    drain_ec = mix_ec * drain_multiplier

    mix_flow = mechanics["flow_rate_l_min"] * demand

    return {
        "mix_target_ec_ds_m": np.round(target_ec, 3),
        "mix_ec_ds_m": np.round(clamp(mix_ec, 1.55, 1.95), 3),
        "mix_target_ph": np.round(target_ph, 3),
        "mix_ph": np.round(clamp(mix_ph, 5.82, 6.10), 3),
        "mix_temp_c": np.round(mix_temp, 2),
        "mix_flow_l_min": np.round(clamp(mix_flow, 0, PUMP["flow_nom"] * 1.2), 2),
        "dosing_a_ml_min": np.round(dos_a, 2),
        "dosing_b_ml_min": np.round(dos_b, 2),
        "dosing_acid_ml_min": np.round(dos_acid, 2),
        "agitator_rpm": np.round(agit_rpm, 1),
        "agitator_current_a": np.round(agit_curr, 3),
        "mixing_uniformity_cv": np.round(uniformity, 4),
        "pid_error_ec": np.round(pid_ec, 4),
        "pid_error_ph": np.round(pid_ph, 4),
        "mixing_efficiency": np.round(mix_eff, 4),
        "drainage_ratio_pct": np.round(drainage_ratio, 1),
        "drain_ec_ds_m": np.round(clamp(drain_ec, 1.35, 2.25), 3),
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §10. 약품 탱크                                                 ║
# ║  마지막 보정                                                    ║
# ║   - 너무 예쁜 직선 하강을 피하려고 "작업자 보충 이벤트" 추가      ║
# ║   - 업무시간 부분보충 / 조기 topping-up / 주중 편차 반영          ║
# ╚══════════════════════════════════════════════════════════════╝

def simulate_chem_tanks(solution, N, rng):
    def sim(level0, dosing, low_threshold, soft_threshold):
        lv = np.full(N, float(level0))
        refill_flag = np.zeros(N, dtype=int)
        for i in range(1, N):
            # 소비는 도징량에 비례하되 미세 오차 포함
            lv[i] = lv[i - 1] - 0.0012 * dosing[i] + rng.normal(0, 0.004)

            dow = (i // 1440) % 7
            hod = (i % 1440) / 60.0
            workhour = (dow < 5) and (9 <= hod <= 17)

            # 1) 임계치 이하이면 업무시간에 부분 보충
            if lv[i] < low_threshold and workhour and rng.random() < CONTROL["chem_refill_prob_workhour"]:
                lv[i] += rng.uniform(10, 18)
                refill_flag[i] = 1
            # 2) 아직 충분히 남아 있어도 가끔 미리 topping-up
            elif lv[i] < soft_threshold and workhour and rng.random() < CONTROL["chem_refill_soft_prob"]:
                lv[i] += rng.uniform(4, 9)
                refill_flag[i] = 1

            lv[i] = float(clamp(lv[i], 5, 100))
        return lv, refill_flag

    tk_a, refill_a = sim(88.0, solution["dosing_a_ml_min"], low_threshold=57, soft_threshold=70)
    tk_b, refill_b = sim(86.0, solution["dosing_b_ml_min"], low_threshold=56, soft_threshold=69)
    tk_acid, refill_acid = sim(84.0, solution["dosing_acid_ml_min"], low_threshold=60, soft_threshold=72)

    cons_a = np.clip(-np.diff(tk_a, prepend=tk_a[0]), 1e-6, None)
    cons_b = np.clip(-np.diff(tk_b, prepend=tk_b[0]), 1e-6, None)
    cons_acid = np.clip(-np.diff(tk_acid, prepend=tk_acid[0]), 1e-6, None)

    est_a = np.where(cons_a > 0.0001, tk_a / cons_a / 60, 999)
    est_b = np.where(cons_b > 0.0001, tk_b / cons_b / 60, 999)
    est_acid = np.where(cons_acid > 0.0001, tk_acid / cons_acid / 60, 999)

    v_a = (solution["dosing_a_ml_min"] > 0.4).astype(int)
    v_b = (solution["dosing_b_ml_min"] > 0.4).astype(int)
    v_acid = (solution["dosing_acid_ml_min"] > 0.2).astype(int)

    return {
        "tank_a_level_pct": np.round(tk_a, 1),
        "tank_b_level_pct": np.round(tk_b, 1),
        "acid_tank_level_pct": np.round(tk_acid, 1),
        "valve_a_on": v_a,
        "valve_b_on": v_b,
        "valve_acid_on": v_acid,
        "tank_a_refill_on": refill_a,
        "tank_b_refill_on": refill_b,
        "acid_tank_refill_on": refill_acid,
        "tank_a_est_hours_to_empty": np.round(clamp(est_a, 0, 999), 1),
        "tank_b_est_hours_to_empty": np.round(clamp(est_b, 0, 999), 1),
        "acid_tank_est_hours_to_empty": np.round(clamp(est_acid, 0, 999), 1),
    }



# ╔══════════════════════════════════════════════════════════════╗
# ║  §11. 분배 라인 / 배지 상태                                     ║
# ║  핵심 수정                                                      ║
# ║   - 배지 EC가 위로만 누적되지 않도록 washout / drydown 분리      ║
# ║   - 관수 시: mix EC 쪽으로 세척 / 수렴                          ║
# ║   - 비관수 시: 건조에 따라 아주 약하게만 농축                   ║
# ╚══════════════════════════════════════════════════════════════╝

def simulate_zones(schedule, env, solution, mechanics, N, rng):
    valve = np.column_stack([schedule["zone1_valve_on"], schedule["zone2_valve_on"], schedule["zone3_valve_on"]]).astype(bool)
    total_delivery = solution["mix_flow_l_min"]
    filter_out = mechanics["filter_pressure_out_kpa"]
    demand = schedule["fertigation_demand_pct"]

    zone_flow = np.zeros((N, 3))
    zone_pressure = np.zeros((N, 3))
    zone_moisture = np.full((N, 3), 63.0)
    zone_sub_ec = np.full((N, 3), 1.82)
    zone_sub_ph = np.full((N, 3), 6.00)
    zone_response = np.zeros((N, 3))

    for i in range(N):
        active = np.where(valve[i])[0]
        if len(active) > 0 and total_delivery[i] > 0:
            weights = ZONE_HYDRAULIC[active] * rng.uniform(0.99, 1.01, len(active))
            weights = weights / weights.sum()
            zone_flow[i, active] = total_delivery[i] * weights
            zone_pressure[i, active] = (
                filter_out[i]
                - np.array([8.5 + 2.0 * z for z in (active + 1)])
                + rng.normal(0, 0.35, len(active))
            )

        if i == 0:
            continue

        for z in range(3):
            prev_m = zone_moisture[i - 1, z]
            prev_ec = zone_sub_ec[i - 1, z]
            prev_ph = zone_sub_ph[i - 1, z]

            if valve[i, z]:
                # ── 관수 시: 배지 수분 상승 ─────────────────────────────
                inc = 0.10 + 0.007 * zone_flow[i, z]
                zone_moisture[i, z] = prev_m + inc + rng.normal(0, 0.015)

                # ── 관수 시 배지 EC: 누적이 아니라 washout / leaching ──
                # 현실:
                #   배지가 건조하면 관수 직후에도 EC가 약간 높을 수 있지만,
                #   반복 관수 중에는 공급 EC 근처로 서서히 세척되어 내려와야 함.
                dry_bonus = 0.03 * np.clip((64.0 - prev_m) / 25.0, 0, 1)
                ec_target = solution["mix_ec_ds_m"][i] * rng.uniform(1.00, 1.02) + dry_bonus

                # demand가 클수록 세척이 강하게 걸리도록 설정
                wash_gain = 0.18 + 0.18 * float(np.clip(demand[i], 0, 1))

                # prev_ec가 target보다 높을수록 추가 washout 부여
                extra_wash = 0.06 * max(prev_ec - ec_target, 0.0)
                zone_sub_ec[i, z] = (
                    prev_ec
                    + wash_gain * (ec_target - prev_ec)
                    - extra_wash
                    + rng.normal(0, 0.0018)
                )

                # ── 관수 시 배지 pH: mix pH보다 살짝 낮은 쪽으로 천천히 수렴 ──
                ph_target = solution["mix_ph"][i] - rng.uniform(0.02, 0.05)
                ph_gain = 0.030 + 0.018 * float(np.clip(demand[i], 0, 1))
                zone_sub_ph[i, z] = prev_ph + ph_gain * (ph_target - prev_ph) + rng.normal(0, 0.0012)

            else:
                # ── 비관수 시: 수분은 천천히 감소 ───────────────────────
                evap = 0.008 * (1 + 0.8 * env["lights_on"][i] + max(env["vpd_kpa"][i] - 0.5, 0))
                zone_moisture[i, z] = prev_m - evap + rng.normal(0, 0.008)

                # ── 비관수 시 배지 EC: 아주 약한 농축만 허용 ────────────
                # 건조가 심할수록 조금 오르지만, 무한정 누적되면 안 됨.
                dry_factor = np.clip((60.0 - zone_moisture[i, z]) / 20.0, 0, 1)
                concentrate = 0.00010 + 0.00040 * dry_factor

                # 높아진 EC는 시간이 지나며 약하게 자연 복귀하도록 감쇠항 부여
                relax_target = solution["mix_ec_ds_m"][i] * 1.03
                relax = 0.004 * max(prev_ec - relax_target, 0.0)

                zone_sub_ec[i, z] = prev_ec + concentrate - relax + rng.normal(0, 0.0007)

                # ── 비관수 시 배지 pH: 매우 느린 drift ─────────────────
                zone_sub_ph[i, z] = prev_ph + 0.002 * ((solution["mix_ph"][i] - 0.03) - prev_ph) + rng.normal(0, 0.0007)

            zone_moisture[i, z] = float(clamp(zone_moisture[i, z], 30, 85))
            zone_sub_ec[i, z] = float(clamp(zone_sub_ec[i, z], 1.35, 2.15))
            zone_sub_ph[i, z] = float(clamp(zone_sub_ph[i, z], 5.6, 6.4))
            zone_response[i, z] = zone_moisture[i, z] - prev_m

    result = {}
    for z in range(3):
        result[f"zone{z+1}_flow_l_min"] = np.round(zone_flow[:, z], 2)
        result[f"zone{z+1}_pressure_kpa"] = np.round(zone_pressure[:, z], 2)
        result[f"zone{z+1}_substrate_moisture_pct"] = np.round(zone_moisture[:, z], 2)
        result[f"zone{z+1}_substrate_ec_ds_m"] = np.round(zone_sub_ec[:, z], 3)
        result[f"zone{z+1}_substrate_ph"] = np.round(zone_sub_ph[:, z], 3)
        result[f"zone{z+1}_moisture_response_pct"] = np.round(zone_response[:, z], 3)

    active_zone_count = valve.sum(axis=1)
    balance = np.ones(N)
    for i in range(N):
        vals = zone_flow[i, zone_flow[i] > 0]
        if len(vals) > 1:
            balance[i] = 1 - np.std(vals) / max(np.mean(vals), 1e-6)
    result["active_zone_count"] = active_zone_count.astype(int)
    result["supply_balance_index"] = np.round(balance, 3)
    return result


# ╔══════════════════════════════════════════════════════════════╗
# ║  §12. 센서 드리프트 / 드롭아웃 반영                             ║
# ╚══════════════════════════════════════════════════════════════╝

def apply_sensor_effects(df, faults):
    if faults["sensor_drift_on"].any():
        idx = np.where(faults["sensor_drift_on"] == 1)[0]
        frac = np.linspace(0, 1, len(idx))
        df.loc[idx, "discharge_pressure_kpa"] += 3.0 * frac
        df.loc[idx, "suction_pressure_kpa"] += 1.0 * frac
        df.loc[idx, "flow_rate_l_min"] *= (1.0 + 0.02 * frac)
        df.loc[idx, "mix_ec_ds_m"] *= (1.0 + 0.015 * frac)
    for col in np.unique(faults["sensor_dropout_target"]):
        if col == "none" or col not in df.columns:
            continue
        mask = faults["sensor_dropout_target"] == col
        df.loc[mask, col] = np.nan
    return df


# ╔══════════════════════════════════════════════════════════════╗
# ║  §13. 이벤트 라벨링                                             ║
# ║  - normal_operation / maintenance / warning / fault            ║
# ╚══════════════════════════════════════════════════════════════╝

def assign_event_labels(df, maintenance, faults, mechanics):
    N = len(df)
    event_type = np.array(["idle"] * N, dtype=object)
    event_type[df["fertigation_on"] == 1] = "normal_irrigation"
    event_type[df["context_event"] == "setpoint_change"] = "setpoint_change"

    event_type[maintenance["weekly_flush_on"] == 1] = "weekly_flush"
    event_type[maintenance["acid_cleaning_on"] == 1] = "acid_cleaning"

    warning_filter = (df["fertigation_on"] == 1) & (mechanics["clogging_index"] > 0.35) & (mechanics["clogging_index"] <= 0.52)
    event_type[warning_filter] = "filter_fouling_warning"
    warning_bearing = (df["fertigation_on"] == 1) & (mechanics["bearing_wear_index"] > 0.45) & (mechanics["bearing_wear_index"] <= 0.68)
    event_type[warning_bearing] = "bearing_wear_warning"

    severe_filter = (df["fertigation_on"] == 1) & (mechanics["clogging_index"] > 0.72)
    event_type[severe_filter] = "severe_clog_shutdown"
    fault_filter = (df["fertigation_on"] == 1) & (mechanics["clogging_index"] > 0.52) & (~severe_filter)
    event_type[fault_filter] = "filter_clog"
    fault_bearing = (df["fertigation_on"] == 1) & (mechanics["bearing_wear_index"] > 0.68)
    event_type[fault_bearing] = "bearing_wear_fault"

    event_type[faults["cavitation_on"] == 1] = "cavitation"
    event_type[faults["water_hammer_on"] == 1] = "water_hammer"
    event_type[faults["mild_dosing_bias_on"] == 1] = "mild_dosing_bias"
    event_type[faults["dosing_failure_on"] == 1] = "dosing_failure"
    event_type[faults["sensor_drift_on"] == 1] = "sensor_drift"
    event_type[faults["sensor_dropout_on"] == 1] = "sensor_dropout"

    event_group = np.empty(N, dtype=object)
    anomaly_label = np.zeros(N, dtype=int)
    warning_label = np.zeros(N, dtype=int)
    anomaly_severity = np.zeros(N, dtype=int)
    for etype, policy in EVENT_GROUP_POLICY.items():
        group, a, w, sev = policy
        mask = event_type == etype
        event_group[mask] = group
        anomaly_label[mask] = a
        warning_label[mask] = w
        anomaly_severity[mask] = sev
    return {
        "event_type": event_type,
        "event_group": event_group,
        "warning_label": warning_label,
        "anomaly_label": anomaly_label,
        "anomaly_severity": anomaly_severity,
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §14. 파생변수 계산                                              ║
# ║  - pressure_flow_ratio / dp_per_flow / flow_drop_rate 등        ║
# ╚══════════════════════════════════════════════════════════════╝

def calc_derived(df):
    eps = 1e-6
    fert_normal = (df["fertigation_on"] == 1) & (df["anomaly_label"] == 0)
    Q = df["flow_rate_l_min"]
    Pd = df["discharge_pressure_kpa"]
    dP = df["differential_pressure_kpa"]
    Pm = df["motor_power_kw"]

    baseline = np.zeros(len(df))
    regimes = df["context_type"].copy()
    for reg in pd.Series(regimes).unique():
        m = (regimes == reg) & fert_normal & (Q > 0.1)
        baseline[regimes == reg] = float(df.loc[m, "flow_rate_l_min"].median()) if m.sum() > 0 else PUMP["flow_nom"]
    df["flow_baseline_l_min"] = np.round(np.where(df["fertigation_on"] == 1, baseline, 0), 2)

    bl = df["flow_baseline_l_min"]
    on = df["flow_rate_l_min"] > 0.1
    df["pressure_flow_ratio"] = np.where(on, Pd / (Q + eps), 0)
    df["dp_per_flow"] = np.where(on, dP / (Q + eps), 0)
    df["flow_drop_rate"] = np.where((df["fertigation_on"] == 1) & (bl > 0), (bl - Q) / (bl + eps), 0)
    df["flow_per_power"] = np.where(on & (Pm > 0.01), Q / (Pm + eps), 0)
    df["pressure_per_power"] = np.where((df["pump_on"] == 1) & (Pm > 0.01), Pd / (Pm + eps), 0)

    pstd = Pd.rolling(15, min_periods=1).std().fillna(0)
    piqr = Pd.rolling(15, min_periods=1).apply(lambda x: np.percentile(x, 75) - np.percentile(x, 25), raw=True).fillna(0)
    fstd = Q.rolling(15, min_periods=1).std().fillna(0)
    fmean = Q.rolling(15, min_periods=1).mean().fillna(0)

    df["pressure_std_15m"] = np.round(pstd, 3)
    df["pressure_iqr_15m"] = np.round(piqr, 3)
    df["pressure_std_iqr_ratio"] = np.where(piqr > 0, pstd / (piqr + eps), 0)
    df["flow_std_15m"] = np.round(fstd, 3)
    df["flow_cv_15m"] = np.where(fmean > 0, fstd / (fmean + eps), 0)

    hist = pd.Series(df["anomaly_label"]).rolling(1440, min_periods=1).sum().fillna(0).astype(int)
    df["fault_history_24h_min"] = hist.values
    return df


# ╔══════════════════════════════════════════════════════════════╗
# ║  §15. 검증 / 감사 지표                                          ║
# ╚══════════════════════════════════════════════════════════════╝

def build_audit(df):
    night = df["lights_on"] == 0
    fert = df["fertigation_on"] == 1
    zone_sum = df[["zone1_flow_l_min", "zone2_flow_l_min", "zone3_flow_l_min"]].sum(axis=1)
    fert_mask = fert & (df["mix_flow_l_min"] > 0)
    ratio = zone_sum[fert_mask] / df.loc[fert_mask, "mix_flow_l_min"].replace(0, np.nan)

    daily_pump_minutes = pd.Series(df["pump_on"].values).groupby(df["day_index"]).sum()
    daily_fert_minutes = pd.Series(df["fertigation_on"].values).groupby(df["day_index"]).sum()
    ir_events = []
    for d in sorted(df["day_index"].unique()):
        mask = df["day_index"] == d
        fert_arr = df.loc[mask, "fertigation_on"].values.astype(int)
        cnt = int(np.sum((fert_arr[1:] == 1) & (fert_arr[:-1] == 0)) + (1 if fert_arr[0] == 1 else 0))
        ir_events.append(cnt)

    return {
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
        "night_fertigation_minutes": int((fert & night).sum()),
        "pump_on_ratio_pct": round(float((df["pump_on"] == 1).mean() * 100), 2),
        "avg_pump_minutes_per_day": round(float(daily_pump_minutes.mean()), 2),
        "avg_fertigation_minutes_per_day": round(float(daily_fert_minutes.mean()), 2),
        "avg_irrigation_events_per_day": round(float(np.mean(ir_events)), 2),
        "min_irrigation_events_per_day": int(np.min(ir_events)),
        "max_irrigation_events_per_day": int(np.max(ir_events)),
        "zone_mass_ratio_mean": round(float(np.nanmean(ratio)), 4),
        "zone_mass_ratio_std": round(float(np.nanstd(ratio)), 4),
        "bearing_le_motor_count": int((df["bearing_temperature_c"] <= df["motor_temperature_c"]).sum()),
        "drain_gt_mix_ec_ratio_pct": round(float((df["drain_ec_ds_m"] > df["mix_ec_ds_m"]).mean() * 100), 2),
        "mix_ec_min": float(np.nanmin(df["mix_ec_ds_m"])),
        "mix_ec_max": float(np.nanmax(df["mix_ec_ds_m"])),
        "mix_ph_min": float(np.nanmin(df["mix_ph"])),
        "mix_ph_max": float(np.nanmax(df["mix_ph"])),
        "warning_ratio_pct": round(float(df["warning_label"].mean() * 100), 2),
        "anomaly_ratio_pct": round(float(df["anomaly_label"].mean() * 100), 2),
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║  §16. raw 65 컬럼 호환성 검사                                   ║
# ╚══════════════════════════════════════════════════════════════╝

def validate_selected_65(df):
    selected_65 = [
        "timestamp", "pump_on", "lights_on", "light_ppfd_umol_m2_s", "air_temp_c",
        "relative_humidity_pct", "co2_ppm", "vpd_kpa", "ventilation_state", "dehumidifier_state",
        "raw_tank_level_pct", "raw_water_temp_c", "raw_water_ec_ds_m", "raw_water_ph",
        "raw_tank_pressure_kpa", "pump_rpm",
        "flow_baseline_l_min", "flow_rate_l_min", "suction_pressure_kpa", "discharge_pressure_kpa",
        "motor_current_a", "voltage_v", "motor_power_kw", "acoustic_db",
        "bearing_vibration_peak_mm_s", "vibration_bandpower_high",
        "motor_temperature_c", "bearing_temperature_c", "cavitation_index",
        "filter_pressure_in_kpa", "filter_pressure_out_kpa", "turbidity_ntu",
        "mix_target_ec_ds_m", "mix_ec_ds_m", "mix_target_ph", "mix_ph", "mix_temp_c",
        "mix_flow_l_min", "dosing_acid_ml_min", "drainage_ratio_pct", "drain_ec_ds_m",
        "tank_a_level_pct", "tank_b_level_pct", "acid_tank_level_pct",
        "valve_acid_on", "valve_a_on", "valve_b_on",
        "zone1_valve_on", "zone1_flow_l_min", "zone1_pressure_kpa",
        "zone1_substrate_moisture_pct", "zone1_substrate_ec_ds_m", "zone1_substrate_ph",
        "zone2_valve_on", "zone2_flow_l_min", "zone2_pressure_kpa",
        "zone2_substrate_moisture_pct", "zone2_substrate_ec_ds_m", "zone2_substrate_ph",
        "zone3_valve_on", "zone3_flow_l_min", "zone3_pressure_kpa",
        "zone3_substrate_moisture_pct", "zone3_substrate_ec_ds_m", "zone3_substrate_ph",
    ]
    missing = [c for c in selected_65 if c not in df.columns]
    return missing


# ╔══════════════════════════════════════════════════════════════╗
# ║  §17. 메인 생성 루틴                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def generate(start_str: str, n_days: int, seed: int):
    rng = make_rng(seed)
    ts, hour, minute_of_day, day_index, N = make_time_index(start_str, n_days)

    env = gen_environment(hour, minute_of_day, day_index, N, rng)
    context_event = build_background_context(day_index, N, rng)
    schedule = build_irrigation_schedule(hour, minute_of_day, day_index, env, rng)
    maintenance = build_maintenance_schedule(day_index, rng)
    maint_mask = (maintenance["weekly_flush_on"] == 1) | (maintenance["acid_cleaning_on"] == 1)
    schedule["pump_on"] = np.where(maint_mask, 0, schedule["pump_on"])
    schedule["fertigation_on"] = np.where(maint_mask, 0, schedule["fertigation_on"])
    schedule["fertigation_demand_pct"] = np.where(maint_mask, 0, schedule["fertigation_demand_pct"])
    schedule["zone1_valve_on"] = np.where(schedule["fertigation_on"] == 1, schedule["zone1_valve_on"], 0)
    schedule["zone2_valve_on"] = np.where(schedule["fertigation_on"] == 1, schedule["zone2_valve_on"], 0)
    schedule["zone3_valve_on"] = np.where(schedule["fertigation_on"] == 1, schedule["zone3_valve_on"], 0)

    tank = gen_tank(schedule, env["air_temp_c"], N, rng)
    faults = build_fault_schedule(schedule["pump_on"], N, n_days, rng)
    mechanics = simulate_pump_filter_mechanics(schedule, maintenance, env, context_event, faults, N, rng)
    solution = simulate_solution_states(schedule, maintenance, tank, context_event, faults, mechanics, N, rng)
    chem = simulate_chem_tanks(solution, N, rng)
    zones = simulate_zones(schedule, env, solution, mechanics, N, rng)

    df = pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in ts],
        "day_index": day_index,
        "minute_of_day": minute_of_day,
        "hour": hour + (minute_of_day % 60) / 60.0,
        "crop_stage": CROP_STAGE,
        "context_type": env["context_type"],
        "context_event": context_event,
        "pump_on": schedule["pump_on"],
        "fertigation_on": schedule["fertigation_on"],
        "event_id": schedule["event_id"],
        "day_fert_start_hour": schedule["day_fert_start_hour"],
        "day_fert_stop_hour": schedule["day_fert_stop_hour"],
        "events_per_day_target": schedule["events_per_day_target"],
        "weekly_flush_on": maintenance["weekly_flush_on"],
        "acid_cleaning_on": maintenance["acid_cleaning_on"],
    })

    for block in [env, tank, mechanics, solution, chem, zones]:
        for k, v in block.items():
            if k in df.columns:
                continue
            df[k] = v

    df["zone1_valve_on"] = schedule["zone1_valve_on"]
    df["zone2_valve_on"] = schedule["zone2_valve_on"]
    df["zone3_valve_on"] = schedule["zone3_valve_on"]
    df["sensor_drift_on"] = faults["sensor_drift_on"]
    df["sensor_dropout_on"] = faults["sensor_dropout_on"]
    df["sensor_dropout_target"] = faults["sensor_dropout_target"]
    df["water_hammer_on"] = faults["water_hammer_on"]
    df["cavitation_on"] = faults["cavitation_on"]
    df["mild_dosing_bias_on"] = faults["mild_dosing_bias_on"]
    df["dosing_failure_on"] = faults["dosing_failure_on"]

    df = apply_sensor_effects(df, faults)

    labels = assign_event_labels(df, maintenance, faults, mechanics)
    for k, v in labels.items():
        df[k] = v

    # ── 파생변수 계산 ─────────────────────────────────────
    df = calc_derived(df)

    # ── 저장 및 감사 지표 출력 ─────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, f"smartfarm_statefirst_{start_str}_{n_days}d.csv")
    audit_path = os.path.join(OUTPUT_DIR, f"smartfarm_statefirst_audit_{start_str}_{n_days}d.json")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    audit = build_audit(df)
    audit["missing_selected_65"] = validate_selected_65(df)
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    print(f"saved_csv: {csv_path}")
    print(f"saved_audit: {audit_path}")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return df, audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="State-first smartfarm scenario generator")
    parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    generate(args.start, args.days, args.seed)
