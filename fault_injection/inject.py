"""
inject.py — 열화 트라젝토리(s(t) ramp) → 고장 이벤트로 고장을 데이터에 주입.

docs/modeling/10_anomaly_signature_ledger.md §4 구현.
정적 이상이 아니라 '점진 누적(ramp) 후 고장(failure)' 궤적으로 넣는다.
하나의 고장강도 s(t)가 여러 센서를 함께 끌어 상관된 다중 센서 편차를 만든다(강사 원칙).
"""
import numpy as np
import pandas as pd

from fault_signatures import FAULT_SIGNATURES


def severity_ramp(n: int, shape: str = "sigmoid") -> np.ndarray:
    """
    누적 고장강도 s를 0→1로 만드는 ramp 배열(길이 n).
      - "linear": 등속 누적
      - "sigmoid": 초반 완만 → 후반 가속. scale·biofilm 누적처럼 임계 근처에서 빨라지는 거동 모사.
    """
    if n <= 1:
        return np.ones(max(n, 0))
    x = np.linspace(0.0, 1.0, n)
    if shape == "sigmoid":
        s = 1.0 / (1.0 + np.exp(-10.0 * (x - 0.5)))   # 중심 0.5 기준 S자
        s = (s - s.min()) / (s.max() - s.min())       # 정확히 0~1로 정규화
        return s
    return x  # linear


def inject_fault(
    df: pd.DataFrame,
    mode: str,
    start_idx: int,
    ramp_len: int,
    severity_max: float = 1.0,
    shape: str = "sigmoid",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    정상 데이터 df(시간순 인덱스)에 고장 mode를 주입한다.

    [궤적] start_idx 부터 ramp_len 동안 s(t)가 0→severity_max로 상승(누적 구간),
           그 이후는 severity_max로 유지(고장 지속). 각 영향 센서의 값은 s에 비례해 변형.
    [고장 이벤트] signature의 failure_rule(예: 유량 < 정상의 75%)이 처음 충족되는 시점을
                 failure_time으로 마킹 — lead-time 평가의 기준점.

    Returns
    -------
    (df_faulty, labels)
      labels 컬럼: degradation_severity(s), anomaly_label(누적 구간 1), fault_mode, failure_time
    """
    if mode not in FAULT_SIGNATURES:
        raise KeyError(f"알 수 없는 고장 모드: {mode}")
    sig = FAULT_SIGNATURES[mode]
    out = df.copy()
    n = len(out)

    # 1) 누적 고장강도 s(t)(잠재 상태): [start, start+ramp_len) ramp, 이후 유지
    s = np.zeros(n, dtype=float)
    end_idx = min(start_idx + ramp_len, n)
    seg = end_idx - start_idx
    if seg > 0:
        s[start_idx:end_idx] = severity_ramp(seg, shape) * severity_max
    s[end_idx:] = severity_max

    # 펌프 가동 게이트 — 정지 중엔 유량이 없어 막힘이 압력/유량에 영향을 못 준다.
    #   따라서 센서에 실제로 보이는 강도 s_eff = s × (펌프 가동 여부). 정지 구간은 정상값 유지.
    #   가동 판정은 변형 전 원본의 pump_rpm(>100) 우선, 없으면 flow_baseline(>1)로.
    if "pump_rpm" in df.columns:
        running = df["pump_rpm"].to_numpy(dtype=float) > 100.0
    elif "flow_baseline_l_min" in df.columns:
        running = df["flow_baseline_l_min"].to_numpy(dtype=float) > 1.0
    else:
        running = np.ones(n, dtype=bool)
    s_eff = s * running.astype(float)

    # 2) 영향 센서에 상관 델타 적용 (mul: base*(1+(target-1)*s_eff), add: base+target*s_eff)
    def _apply(col, how, target):
        if col not in out.columns:
            return
        base = out[col].to_numpy(dtype=float)
        if how == "mul":
            out[col] = base * (1.0 + (target - 1.0) * s_eff)
        elif how == "add":
            out[col] = base + target * s_eff

    for col, (how, target) in sig.get("columns", {}).items():
        _apply(col, how, target)

    # 구역 유량(존재하는 zone만)
    if "zone_flow_columns" in sig:
        how, target = sig["zone_flow_columns"]
        for z in (1, 2, 3):
            _apply(f"zone{z}_flow_l_min", how, target)

    # 3) 고장 이벤트 시점 마킹 (failure_rule: 특정 컬럼이 정상 baseline의 ratio_below 미만)
    failure_time = None
    rule = sig.get("failure_rule")
    if rule and rule["column"] in out.columns:
        col = rule["column"]
        # 정상 baseline = 고장 시작 전 구간의 평균(없으면 전체 평균)
        pre = df[col].to_numpy(dtype=float)[:start_idx]
        baseline = float(np.mean(pre)) if len(pre) > 0 else float(np.mean(df[col]))
        thresh = baseline * rule["ratio_below"]
        faulty_col = out[col].to_numpy(dtype=float)
        crossed = np.where((np.arange(n) >= start_idx) & (faulty_col < thresh))[0]
        if len(crossed) > 0:
            failure_time = out.index[crossed[0]]

    # 4) 라벨
    #   degradation_severity: 누적 잠재 손상 s(정지 중에도 진행, 단조 증가).
    #   anomaly_label: 센서에 '실제로 보이는' 구간만 1 (s_eff>0 = 가동 중 열화). 정지 중엔 정상으로 보임.
    labels = pd.DataFrame(index=out.index)
    labels["degradation_severity"] = s
    labels["anomaly_label"] = (s_eff > 0).astype(int)
    labels["fault_mode"] = np.where(s_eff > 0, mode, "")
    labels["failure_time"] = failure_time           # 단일 시점(브로드캐스트)
    return out, labels
