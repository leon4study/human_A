"""
sensor_faults.py — 단일 센서 고장(센서 자체 결함)을 데이터에 주입.

docs/modeling/10 §6 대조군. inject.py(실제 설비 막힘 = 다중 센서 동반 변동)와 반대로,
여기서는 '센서 하나만' 비정상이 되는 경우를 만든다. 강사 원칙의 반대 축:
  - 진짜 고장: 물리적으로 연결된 여러 센서가 함께 요동친다(inject.py).
  - 센서 문제: 회로/캘리브레이션 결함으로 그 센서 값 하나만 튄다(이 파일).

세 가지 전형적 센서 결함 모드(단일 컬럼에만 적용):
  - drift : 캘리브레이션 드리프트. 시간에 따라 천천히 누적되는 오프셋.
  - spike : 일시적 급변. 한 구간에서 큰 폭으로 치솟거나 떨어짐(전기적 노이즈/접촉 불량).
  - stuck : 고착(flatline). 센서가 한 값에 얼어붙어 변동이 사라짐(통신 두절/래치).

모두 raw 데이터(윈도잉 전)에 적용하며, 10분 집계에서도 보이도록 충분한 지속시간을 준다.
"""
import numpy as np
import pandas as pd


def apply_sensor_fault(
    df: pd.DataFrame,
    column: str,
    mode: str,
    start_idx: int,
    length: int,
    magnitude: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    df의 단일 컬럼 `column`에 센서 결함을 주입한다.

    Parameters
    ----------
    column : 결함을 넣을 단일 센서 컬럼(이것 하나만 변형된다).
    mode   : "drift" | "spike" | "stuck".
    start_idx, length : 결함 구간(행 인덱스 기준).
    magnitude :
      - drift: 구간 끝에서의 누적 오프셋(해당 컬럼 표준편차의 배수).
      - spike: 급변 크기(표준편차의 배수). 부호는 양/음 모두 가능.
      - stuck: 사용 안 함(고착값은 start 직전 값).

    Returns
    -------
    (df_faulty, labels)
      labels: anomaly_label(구간 1), sensor_fault_mode, sensor_fault_column
    """
    if column not in df.columns:
        raise KeyError(f"컬럼 없음: {column}")
    out = df.copy()
    n = len(out)
    end_idx = min(start_idx + length, n)
    col = out[column].to_numpy(dtype=float).copy()
    sd = float(np.nanstd(col)) or 1.0

    if mode == "drift":
        # 0 → magnitude*sd 로 선형 누적되는 오프셋(캘리브레이션 드리프트).
        ramp = np.linspace(0.0, magnitude * sd, end_idx - start_idx)
        col[start_idx:end_idx] = col[start_idx:end_idx] + ramp
    elif mode == "spike":
        # 구간 전체를 magnitude*sd 만큼 들어올림(윈도우에 보이는 지속 급변).
        col[start_idx:end_idx] = col[start_idx:end_idx] + magnitude * sd
    elif mode == "stuck":
        # start 직전 값으로 고착(변동 소멸).
        held = col[max(start_idx - 1, 0)]
        col[start_idx:end_idx] = held
    else:
        raise ValueError(f"알 수 없는 모드: {mode}")

    out[column] = col

    labels = pd.DataFrame(index=out.index)
    active = np.zeros(n, dtype=int)
    active[start_idx:end_idx] = 1
    labels["anomaly_label"] = active
    labels["sensor_fault_mode"] = np.where(active == 1, mode, "")
    labels["sensor_fault_column"] = np.where(active == 1, column, "")
    return out, labels
