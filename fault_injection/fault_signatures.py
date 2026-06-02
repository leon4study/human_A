"""
fault_signatures.py — 실제 고장의 다중 센서 시그니처를 코드 파라미터로 인코딩.

각 값의 근거(논문·벤더·표준)는 docs/modeling/10_anomaly_signature_ledger.md(SSOT)에 있다.
이 파일은 그 ledger를 '주입 가능한 숫자'로 옮긴 것이다. 값을 바꿀 때는 ledger도 함께 갱신한다.

[구조] 한 고장 모드 = 영향 센서들의 묶음. 각 센서는 (적용방식, s=1일 때 목표값)으로 정의.
  공통 고장강도 s(t) ∈ [0,1] (inject.py가 ramp로 생성)에 대해:
    "mul": base * (1 + (target - 1) * s)   → s=0이면 base, s=1이면 base*target  (배수 변화)
    "add": base + target * s                → s=0이면 base, s=1이면 base+target  (가산 변화)
  하나의 s(t)가 여러 센서를 동시에 끌기 때문에 '상관된 다중 센서 편차'(강사 원칙)가 자연히 만들어진다.

[중요] 막힘은 위치별로 시그니처가 다르다(ledger §3-1):
  - 하류(점적/노즐) 막힘: 유량↓ + 토출압↑ (전류는 약한 보조, 오히려 약간↓).
  - 임펠러 막힘: 전류↑ + 진동↑ (효율 손실). 흡입측: 흡입 고진공.
  여기서는 프로젝트 핵심인 '하류 막힘'을 먼저 구현한다.
"""

FAULT_SIGNATURES = {
    # ── 하류(점적/노즐) 막힘 — ledger §3-1 [S1][S3][S4][S6] ──────────────────────
    "hydraulic_clog_downstream": {
        "domain": "hydraulic",
        "description": "점적/노즐 하류 막힘(scale·biofilm 누적). 유량↓ + 토출압↑가 상관되어 진행.",
        # 메인 라인 센서. s=1에서의 목표:
        "columns": {
            # 유량: 정상의 65%까지 하락(ISO 막힘 기준 '설계의 75% 미만'을 ramp 도중 통과)
            "flow_rate_l_min":            ("mul", 0.65),
            # 토출압: +25% (점적 정상 2.0 bar → 경보 상한 2.5 bar 앵커, ledger [S3])
            "discharge_pressure_kpa":     ("mul", 1.25),
            # 모터 전력/전류: 약 -5% (펌프 곡선상 저유량 → brake power 소폭↓. 약한 보조 신호)
            "motor_power_kw":             ("mul", 0.95),
            "motor_current_a":            ("mul", 0.97),
            # 진동: +15% (경미. 심한 cavitation 동반 시 ISO 10816 Zone C까지 갈 수 있음 [S2])
            "bearing_vibration_rms_mm_s": ("mul", 1.15),
        },
        # 말단 막힘이라 구역 유량도 함께 하락(존재하는 zone만 적용)
        "zone_flow_columns": ("mul", 0.65),  # zone{1,2,3}_flow_l_min 에 동일 적용
        # 고장 이벤트 정의: 유량이 설계의 75% 미만이 되는 시점(ISO 막힘) — inject.py가 마킹
        "failure_rule": {"column": "flow_rate_l_min", "ratio_below": 0.75},
        "sources": "ledger §3-1 [S1 SpringPump/UNITEC] [S2 ISO10816] [S3 점적WSN] [S4 점적막힘ISO] [S6 펌프곡선]",
    },
}
