"""
fault_signatures.py — 고장 위치별 '영향 프로파일'(influence profile) 라이브러리.

각 고장 = 하나의 근본 원인(root cause)이 공유 잠재 강도 s(t) ∈ [0,1]에 따라 여러 센서를
'가중치로' 끌어당기는 프로파일. 한 s(t)가 여러 센서를 동시에 끌기 때문에 도메인 간 상관 변동
(강사 원칙: 여러 값이 함께 요동 = 진짜 고장)이 자연히 만들어진다. 위치를 바꾸면 그에 맞는
센서 집합이 가중치대로 요동친다.

[형식] 한 고장 = 영향 행렬의 한 행(희소). 각 센서는 (적용방식, s=1일 때 목표)로 정의:
    "mul": base * (1 + (target - 1) * s)   → s=1이면 base*target  (배수, target<1=감소/>1=증가)
    "add": base + target * s                → s=1이면 base+target  (가산, 부호=방향)

[근거 정책] 도메인 간 '방향 패턴'(어떤 센서가 같이 움직이나)은 물리 결합 생성기
src/data_gen_jun.py의 clog 계수에서 가져온다(이미 물리 튜닝됨). '절대 크기'와 일부 '방향
보정'은 docs/modeling/10 §3 자료조사(ISO·논문·벤더)에서 가져온다.
  ※ 보정 예: jun은 하류 막힘 시 전류↑로 모델링했으나, 펌프 곡선([S6])상 하류 throttle은
    저유량→brake power 소폭↓이므로 여기선 전류 ~flat/↓로 둔다. (jun ≠ 무조건 정답)

[propagates_to] 그 고장이 '물리적으로 번지는 도메인' 목록 — 데이터 레벨 검증·baseline 평가에서
"올바른 도메인이 켜지나"를 확인하는 정답지로 쓴다.
"""

FAULT_SIGNATURES = {
    # ── 1) 하류(점적/노즐) 막힘 — 4도메인 전체로 번지는 광역 고장 ────────────────────
    #    근거: 방향=data_gen_jun clog 계수, 크기/전류방향=ledger §3-1 [S1][S3][S4][S6]
    "hydraulic_clog_downstream": {
        "root_domain": "hydraulic",
        "description": "점적/노즐 하류 막힘(scale·biofilm). 유량↓+토출압↑을 축으로 4도메인에 번짐.",
        "columns": {
            # hydraulic 본체
            "flow_rate_l_min":            ("mul", 0.65),   # ISO 막힘: 설계의 75% 미만 통과 → 65%
            "discharge_pressure_kpa":     ("mul", 1.25),   # 점적 2.0→2.5 bar 앵커 [S3]
            "suction_pressure_kpa":       ("add", -3.0),   # 약한 흡입 진공(jun -1.5c 방향)
            "filter_pressure_in_kpa":     ("mul", 1.04),   # 여과 전단 압력 소폭↑(jun +5c)
            "filter_pressure_out_kpa":    ("mul", 0.96),   # 차압 벌어짐(filter_delta↑)
            # motor로 번짐 — 단, 전류·전력은 ledger 보정으로 ~flat/약간↓ (jun과 반대)
            "motor_power_kw":             ("mul", 0.96),   # 저유량 brake power 소폭↓ [S6]
            "motor_current_a":            ("mul", 0.97),
            "bearing_vibration_rms_mm_s": ("mul", 1.15),   # 경미 진동↑(jun +0.8c, cavitation 동반시↑)
            "vibration_peak_mm_s":        ("mul", 1.15),
            "motor_temperature_c":        ("add", 1.5),    # 발열 소폭↑(jun +2.5c)
            # nutrient로 번짐 — 막히면 정체로 배수 EC 농축(jun +0.25c/+0.3b)
            "drain_ec_ds_m":              ("add", 0.30),
            "turbidity_ntu":              ("add", 0.40),   # 부유물↑(jun +0.5c)
        },
        "zone_flow_columns": ("mul", 0.65),   # zone{1,2,3}_flow_l_min — 말단 유량↓
        "failure_rule": {"column": "flow_rate_l_min", "ratio_below": 0.75},
        "propagates_to": ["hydraulic", "motor", "nutrient", "zone_drip"],
        "sources": "방향=data_gen_jun clog / 크기·전류방향=ledger §3-1 [S1][S3][S4][S6]",
    },

    # ── 2) 모터 베어링 마모 — 거의 motor 도메인에 국한된 '국소' 고장 (대비군) ──────────
    #    근거: ISO 10816 진동 존(§3 [S2]) + data_gen_jun 베어링 진동/온도 계수.
    #    유량·압력은 거의 불변 → '광역 막힘'과 대비되는 footprint.
    "motor_bearing_wear": {
        "root_domain": "motor",
        "description": "베어링 마모/윤활 불량. 진동·베어링온도·마찰전류↑. 수력 라인은 거의 불변.",
        "columns": {
            "bearing_vibration_rms_mm_s": ("mul", 2.2),    # ISO Zone A(1.4)→C(4.5) 진입 [S2]
            "vibration_peak_mm_s":        ("mul", 2.4),
            "vibration_bandpower_high_g": ("mul", 2.0),     # 고주파 성분↑(베어링 결함 특징)
            "bearing_temperature_c":      ("add", 8.0),     # 베어링 과열(jun +2.0c 확대)
            "motor_temperature_c":        ("add", 3.0),
            "motor_current_a":            ("mul", 1.06),    # 기계 마찰로 전류 소폭↑(부하 무관)
            "motor_power_kw":             ("mul", 1.05),
        },
        "failure_rule": {"column": "bearing_vibration_rms_mm_s", "ratio_above": 3.2},
        "propagates_to": ["motor"],
        "sources": "ISO 10816 베어링 진동 존 [S2] + data_gen_jun 진동/온도 계수",
    },

    # ── 3) 흡입측 막힘/공동현상 — 하류 막힘과 '반대' 수력 시그니처 (대비군) ────────────
    #    근거: ledger §3-1 흡입 고진공(-68~-85 kPa) + cavitation 진동. 하류와 달리 토출압↓.
    "hydraulic_suction_blockage": {
        "root_domain": "hydraulic",
        "description": "흡입측 막힘/스트레이너 막힘. 고진공+유량↓+토출압↓(굶음)+공동 진동↑.",
        "columns": {
            "suction_pressure_kpa":       ("add", -55.0),  # -10→-65 kPa 고진공 앵커
            "flow_rate_l_min":            ("mul", 0.70),   # 흡입 부족으로 유량↓
            "discharge_pressure_kpa":     ("mul", 0.85),   # 하류와 반대: 굶어서 토출압↓
            "bearing_vibration_rms_mm_s": ("mul", 1.6),    # cavitation 진동↑
            "vibration_bandpower_high_g": ("mul", 1.9),    # 공동 붕괴 고주파↑
            "motor_current_a":            ("mul", 0.94),   # 저유량 → 전류↓
            "motor_power_kw":             ("mul", 0.93),
        },
        "zone_flow_columns": ("mul", 0.70),
        "failure_rule": {"column": "suction_pressure_kpa", "below_abs": -50.0},
        "propagates_to": ["hydraulic", "motor"],
        "sources": "ledger §3-1 흡입 고진공·cavitation [S1][S5]",
    },

    # ── 4) 양액 배합 불균형 — nutrient 도메인 국소 고장 (대비군) ───────────────────────
    #    근거: ledger §3-3 / domain knowledge. EC·pH 드리프트, 제어 오차↑.
    "nutrient_imbalance": {
        "root_domain": "nutrient",
        "description": "A/B액 비율 오류·도징 이상. EC·pH가 목표에서 드리프트, 배수 EC↑.",
        "columns": {
            "mix_ec_ds_m":   ("add", 0.45),    # 목표 1.80에서 +0.45 드리프트
            "mix_ph":        ("add", -0.5),    # pH 산성 쪽 드리프트
            "drain_ec_ds_m": ("add", 0.50),    # 배수 EC↑(염류 축적)
        },
        "failure_rule": {"column": "mix_ec_ds_m", "ratio_above": 1.20},
        "propagates_to": ["nutrient"],
        "sources": "ledger §3-3 양액 화학 + domain knowledge",
    },
}
