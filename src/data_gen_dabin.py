import pandas as pd
import numpy as np
from pathlib import Path

# dabin.csv는 컬럼 스키마와 day-1 일중 패턴 템플릿 추출용으로만 참조.
# 이후 30일치는 템플릿 반복 + 작은 gaussian 노이즈로 합성 → 소스의 주간 cleaning
# event와 선형 drift가 결과 데이터에 들어오지 않음. 월1 AE 학습용 구조적 평탄 보장.
src = Path("/Users/jun/GitStudy/human_A/data/dabin.csv")
out_path = Path("/Users/jun/GitStudy/human_A/data/generated_data_from_dabin_0420.csv")

# ── [Step 1] dabin day-1 일중 템플릿 추출 (1440분 × 컬럼) ────────────────────
ref = pd.read_csv(src)
ref["timestamp"] = pd.to_datetime(ref["timestamp"])
ref = ref.sort_values("timestamp").reset_index(drop=True)

start = ref["timestamp"].min()
day1 = ref[ref["timestamp"] < start + pd.Timedelta(days=1)].copy()
day1["mod"] = day1["timestamp"].dt.hour * 60 + day1["timestamp"].dt.minute
day1 = day1.set_index("mod").sort_index()
day1 = day1.reindex(range(1440)).ffill().bfill()  # 1440행 보장

# ── [Step 2] N일 합성: 매 분 = template[minute_of_day] + 작은 gaussian 노이즈 ─
# 월1(0~30) flat 학습 구간 + 월2(32~) phase 기반 drift 확인하려면 N_DAYS=60+ 권장
N_DAYS = 90
idx = pd.date_range(start, periods=N_DAYS * 1440, freq="1min")
mod_arr = (idx.hour * 60 + idx.minute).to_numpy()

out = pd.DataFrame({"timestamp": idx})

rng = np.random.default_rng(20260501)
_numeric_cols = [
    c
    for c in day1.columns
    if c != "timestamp" and pd.api.types.is_numeric_dtype(day1[c])
]
for _col in _numeric_cols:
    _tmpl = day1[_col].to_numpy().astype(float)
    _std = float(np.nanstd(_tmpl))
    if _std > 0:
        out[_col] = _tmpl[mod_arr] + rng.normal(0, _std * 0.3, len(out))
    else:
        out[_col] = _tmpl[mod_arr]

# ── [Step 3] 타이밍 변수 (합성 timestamp 기반) ────────────────────────────────
ts = out["timestamp"]
days = (ts - ts.min()).dt.total_seconds() / 86400.0
hour = ts.dt.hour + ts.dt.minute / 60.0

is_day = ((hour >= 6) & (hour < 18)).to_numpy()
is_night = ~is_day
startup = ((hour >= 6.0) & (hour < 6.5)).to_numpy()


# Smoothstep helper for natural transitions
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# Phase ramps
# - month1 (day  0~32): phase=0, 완전 클린 구간
# - month2 (day 32~60): sqrt 곡선 → 초반 day 32~33부터 미미한 신호 시작 ('생길락 말락')
#                        smoothstep 대신 sqrt 사용: 시작 기울기가 커서 초반에 즉시 미세 변화 생성
# - month3 (day 60~78): smoothstep으로 뚜렷한 이상 발현
ramp_12 = np.sqrt(np.clip((days - 32.0) / 28.0, 0.0, 1.0))  # day 32~60
ramp_23 = smoothstep((days - 60.0) / 18.0)  # day 60~78

# month2: 최대 phase 0.18 (미미한 신호), month3: 추가 0.42 (명확한 이상)
phase = 0.18 * ramp_12 + 0.42 * ramp_23
phase = np.clip(phase, 0, 0.60)

# phase=0 구간(월1)은 raw 신호 그대로 보존하기 위한 per-sample mix factor
# phase=0 → mix=0 (raw 유지), phase=max → mix=1 (drift 완전 반영)
mix = np.clip(phase / 0.60, 0.0, 1.0)

# Zone-specific milder asymmetry
zone1_phase = np.clip(phase * 1.10, 0, 0.66)
zone2_phase = np.clip(phase * 0.88, 0, 0.55)
zone3_phase = np.clip(phase * 0.70, 0, 0.45)

# (out은 Step 2에서 이미 생성됨; 소스 detrend 블록은 합성 방식에서 불필요)

# Reference baseline from full first-month daytime stable window (day 0~30)
anchor_mask = (days < 30.0) & is_day


def baseline(col):
    return out.loc[anchor_mask, col].median()


# Apply softened drift with continuity
main_specs = [
    # col, direction(+/-), max_shift, smoothing_window
    ("flow_rate_l_min", -1, 6.0, 31),
    ("mix_flow_l_min", -1, 5.2, 31),
    ("pump_rpm", -1, 85.0, 31),
    ("suction_pressure_kpa", -1, 2.8, 31),
    ("discharge_pressure_kpa", +1, 28.0, 31),
    ("motor_current_a", +1, 1.25, 31),
    ("motor_power_kw", +1, 0.48, 31),
    ("bearing_vibration_rms_mm_s", +1, 0.95, 31),
    ("motor_temperature_c", +1, 4.0, 41),
    ("bearing_temperature_c", +1, 3.2, 41),
    ("filter_pressure_in_kpa", +1, 24.0, 31),
    ("filter_pressure_out_kpa", +1, 15.0, 31),
    ("turbidity_ntu", +1, 0.95, 41),
]

for col, direction, max_shift, win in main_specs:
    raw = out[col].astype(float).to_numpy()
    base = baseline(col)

    # pull raw closer to stable baseline, then add reduced smooth drift
    # keeps daily/weekly natural shape while softening later-month extremes
    centered = base + (raw - base) * 0.78
    shifted = centered + direction * max_shift * phase

    # preserve daily shape via blending; nighttime motor sensors are zeroed explicitly below
    smoothed = (
        pd.Series(shifted).rolling(win, min_periods=1, center=True).mean().to_numpy()
    )
    blended = smoothed * 0.60 + shifted * 0.40

    # 월1(phase=0)은 raw 유지, drift 활성 구간만 blended 혼입
    out[col] = raw * (1.0 - mix) + blended * mix

# Zone-specific variables with softer worsening
zone_specs = [
    ("zone1_flow_l_min", zone1_phase, -1, 3.4, 31),
    ("zone2_flow_l_min", zone2_phase, -1, 2.2, 31),
    ("zone3_flow_l_min", zone3_phase, -1, 1.5, 31),
    ("zone1_pressure_kpa", zone1_phase, +1, 18.0, 31),
    ("zone2_pressure_kpa", zone2_phase, +1, 12.0, 31),
    ("zone3_pressure_kpa", zone3_phase, +1, 8.0, 31),
    ("zone1_substrate_moisture_pct", zone1_phase, -1, 6.8, 41),
    ("zone2_substrate_moisture_pct", zone2_phase, -1, 4.8, 41),
    ("zone3_substrate_moisture_pct", zone3_phase, -1, 3.4, 41),
    ("zone1_substrate_ec_ds_m", zone1_phase, +1, 0.10, 41),
    ("zone2_substrate_ec_ds_m", zone2_phase, +1, 0.07, 41),
    ("zone3_substrate_ec_ds_m", zone3_phase, +1, 0.05, 41),
]

for col, prog, direction, max_shift, win in zone_specs:
    raw = out[col].astype(float).to_numpy()
    base = baseline(col)
    centered = base + (raw - base) * 0.80
    shifted = centered + direction * max_shift * prog
    smoothed = (
        pd.Series(shifted).rolling(win, min_periods=1, center=True).mean().to_numpy()
    )
    blended = smoothed * 0.62 + shifted * 0.38
    # 월1 보호: phase=0 구간은 raw 그대로
    out[col] = raw * (1.0 - mix) + blended * mix

# Keep pH almost fixed and not explanatory
rng = np.random.default_rng(20260418)
out["mix_target_ph"] = 5.80
out["mix_ph"] = 5.80 + rng.normal(0, 0.0045, len(out))
out["zone1_substrate_ph"] = 5.84 + rng.normal(0, 0.006, len(out))
out["zone2_substrate_ph"] = 5.83 + rng.normal(0, 0.006, len(out))
out["zone3_substrate_ph"] = 5.82 + rng.normal(0, 0.006, len(out))

# ── [야간 처리 START] ─────────────────────────────────────────────────────────
# 야간(18:00~06:00)은 펌프 정지 상태 → 모터 구동 관련 센서 전부 0으로 강제 설정
for col in [
    "flow_rate_l_min",
    "mix_flow_l_min",
    "zone1_flow_l_min",
    "zone2_flow_l_min",
    "zone3_flow_l_min",
]:
    out.loc[is_night, col] = 0.0

for col in [
    "motor_current_a",
    "motor_power_kw",
    "bearing_vibration_rms_mm_s",
    "pump_rpm",
]:
    out.loc[is_night, col] = 0.0

# 토출압: 펌프 정지 후에도 배관 내 잔압 유지 (~45 kPa)
# → pressure_flow_ratio, dp_per_flow 지표가 야간에 왜곡되지 않도록
RESIDUAL_PRESSURE_KPA = 45.0
out.loc[is_night, "discharge_pressure_kpa"] = RESIDUAL_PRESSURE_KPA

# 흡입압: 펌프 off → 흡입 없음 → 0
# → dp_per_flow = (discharge - suction) / flow 야간 오염 방지
out.loc[is_night, "suction_pressure_kpa"] = 0.0
# ── [야간 처리 END] ───────────────────────────────────────────────────────────

# Keep startup overshoot visible but slightly moderated
for col, extra in [
    ("pump_rpm", 18.0),
    ("discharge_pressure_kpa", 4.5),
    ("motor_current_a", 0.35),
    ("motor_power_kw", 0.10),
    ("bearing_vibration_rms_mm_s", 0.12),
    ("zone1_pressure_kpa", 3.0),
    ("zone2_pressure_kpa", 2.2),
    ("zone3_pressure_kpa", 1.6),
]:
    out.loc[startup, col] = out.loc[startup, col] + extra

for col in [
    "flow_rate_l_min",
    "mix_flow_l_min",
    "zone1_flow_l_min",
    "zone2_flow_l_min",
    "zone3_flow_l_min",
]:
    out.loc[startup, col] = out.loc[startup, col] * 0.90

# EC 드리프트: 배관 막힘 → 양액 농축 및 배액 염분 축적 패턴 반영
# pid_error_ec(mix_ec - mix_target_ec), salt_accumulation_delta(drain_ec - mix_ec) 지표 활성화용
for col, direction, max_shift, win in [
    ("mix_ec_ds_m", +1, 0.08, 31),  # 막힘 시 배관 내 흐름 정체 → 농도 약간 증가
    (
        "drain_ec_ds_m",
        +1,
        0.12,
        31,
    ),  # 배지 내 염분 누적 → 배액 EC가 공급 EC보다 더 크게 증가
]:
    raw = out[col].astype(float).to_numpy()
    base = baseline(col)
    centered = base + (raw - base) * 0.80
    shifted = centered + direction * max_shift * phase
    smoothed = (
        pd.Series(shifted).rolling(win, min_periods=1, center=True).mean().to_numpy()
    )
    blended = smoothed * 0.60 + shifted * 0.40
    # 월1 보호: phase=0 구간은 raw 그대로
    out[col] = raw * (1.0 - mix) + blended * mix

# Preserve environmental/tank variables with slight smoothing only
# (mix_ec_ds_m, drain_ec_ds_m은 위 drift 블록에서 처리했으므로 제외)
for col in [
    "light_ppfd_umol_m2_s",
    "air_temp_c",
    "relative_humidity_pct",
    "co2_ppm",
    "raw_tank_level_pct",
    "raw_water_temp_c",
    "mix_target_ec_ds_m",
    "mix_temp_c",
    "dosing_acid_ml_min",
    "tank_a_level_pct",
    "tank_b_level_pct",
    "acid_tank_level_pct",
]:
    out[col] = (
        pd.Series(out[col]).rolling(7, min_periods=1, center=True).mean().to_numpy()
    )

# ── [세척 이벤트] ─────────────────────────────────────────────────────────────
# 월1(day 0~30)은 AE 정상 학습 구간이므로 cleaning event 금지.
# day 32부터 7일마다 (08:00~08:30) 산 세척 이벤트 → 월2 이후에만 발생.
# 세척 중: acid 도징 급증 + pH 약간 하락 (산 투입 효과)
days_arr = days.to_numpy()
hour_arr = hour.to_numpy()
clean_mask = np.zeros(len(out), dtype=int)
for d in range(32, int(days_arr.max()) + 1, 7):
    clean_window = (
        (days_arr >= d) & (days_arr < d + 1) & (hour_arr >= 8.0) & (hour_arr < 8.5)
    )
    clean_mask[clean_window] = 1

out["cleaning_event_flag"] = clean_mask
out.loc[clean_mask == 1, "dosing_acid_ml_min"] = (
    out.loc[clean_mask == 1, "dosing_acid_ml_min"] + 50.0
)
out.loc[clean_mask == 1, "mix_ph"] = out.loc[clean_mask == 1, "mix_ph"] - 0.15

# Physical consistency
out["filter_pressure_out_kpa"] = np.minimum(
    out["filter_pressure_out_kpa"], out["filter_pressure_in_kpa"] - 0.05
)
out["filter_pressure_out_kpa"] = np.maximum(out["filter_pressure_out_kpa"], 0)

# Non-negativity where needed
for c in out.columns:
    if c == "timestamp":
        continue
    out[c] = pd.to_numeric(out[c], errors="coerce")

nonneg_cols = [c for c in out.columns if c not in ["timestamp", "suction_pressure_kpa"]]
for c in nonneg_cols:
    out[c] = np.maximum(out[c], 0)

# Round to original style
for c in out.columns:
    if c != "timestamp":
        out[c] = out[c].round(3)

# Save
# hidden_* 컬럼은 계산/검증용이므로 최종 CSV에서 제외
export_out = out.drop(columns=[c for c in out.columns if c.startswith("hidden_")])
export_out.to_csv(out_path, index=False, encoding="utf-8-sig")

# Quick month summaries for sanity
m1 = (days < 30) & is_day
m2 = (days >= 30) & (days < 60) & is_day
m3 = (days >= 60) & is_day

summary_cols = [
    "flow_rate_l_min",
    "discharge_pressure_kpa",
    "motor_current_a",
    "motor_power_kw",
    "bearing_vibration_rms_mm_s",
    "zone1_flow_l_min",
    "zone1_pressure_kpa",
    "zone1_substrate_moisture_pct",
]

summary = pd.DataFrame(
    {
        "month1_mean": out.loc[m1, summary_cols].mean(),
        "month2_mean": out.loc[m2, summary_cols].mean(),
        "month3_mean": out.loc[m3, summary_cols].mean(),
    }
).round(3)

print(out_path)
print(out.shape)
print(summary)
