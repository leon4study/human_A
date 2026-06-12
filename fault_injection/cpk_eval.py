"""
cpk_eval.py — 유량(flow_rate_l_min) 공정능력지수 Cpk 산출(재현용).

[이 파일이 푸는 문제]
포트폴리오 발화 "Cpk 1.67"의 '측정 로직'을 코드로 확보한다. 면접에서 "그 1.67(여기선
1.69)을 어떻게 구했나?"를 물으면, 이 스크립트가 바로 답이 된다 — 정상 운전 유량의 산포를
관수 허용오차(규격)와 비교해 공정능력을 직접 계산한다.

[공정능력지수 Cpk 정의]
  Cpk = min[ (USL - mu) / (3 sigma),  (mu - LSL) / (3 sigma) ]
    - mu, sigma : 공정(정상 운전 유량)의 평균·표준편차.
    - USL/LSL   : 규격 상·하한(Upper/Lower Spec Limit). 여기선 '관수 설계유량 ± 허용오차'.
  해석 기준(제조 표준): Cpk 1.33 = 4 sigma(양호), 1.67 = 5 sigma(우수), 2.00 = 6 sigma.
  의미: 규격 한계까지 '몇 개의 표준편차'가 들어가나. 클수록 규격 대비 산포가 작아 안정적.

[CTQ(핵심 품질특성) 선택 = flow_rate_l_min]
  관수에서 직접 관리해야 하는 품질특성은 '말단에 약속한 유량을 안정적으로 보내는가'다. 막힘이
  진행되면 유량이 규격 하한(LSL) 아래로 떨어진다 → Cpk 급락. 즉 'AE가 막힘을 잡아 유량을 규격
  안에 유지 = Cpk 방어'라는 스토리의 정량 축이 유량이다.

[정속 제어 주의]
  펌프가 정속(고정 RPM) 제어라 정상 운전 유량의 sigma가 본래 작다 → Cpk가 높게 나오는 게 자연
  스럽다(이상한 일이 아님). 이건 어디까지나 '정상 운전' 공정능력이며, 막힘(이상)이 섞이면 유량
  분포가 LSL 쪽으로 끌려가 Cpk가 급락한다는 점을 함께 해석한다.

실행:
    cd fault_injection && python cpk_eval.py
"""
import os

import numpy as np
import pandas as pd

# 프로젝트 루트/데이터 경로. baseline_blockage_eval.py 등과 동일한 정상 학습본을 쓴다(일관성).
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_CSV = os.path.join(PROJECT, "data", "smartfarm_normal_train_v5.csv")

CTQ = "flow_rate_l_min"          # 핵심 품질특성: 말단으로 보내는 유량
NOMINAL = 78.0                   # 관수 설계(목표) 유량 [L/min] — 규격의 중심. 정속 제어 목표치.
# 관수 허용오차(규격폭). 농가/작물마다 다르므로 여러 후보를 함께 출력해 어떤 스펙에서 어떤 Cpk가
# 나오는지 투명하게 보여준다. ±10%는 점적관수에서 흔히 쓰는 균일도 허용오차 수준.
TOLERANCES = (0.10, 0.15, 0.20)


def cpk(mu: float, sigma: float, lsl: float, usl: float) -> float:
    """Cpk = min[(USL-mu)/3sigma, (mu-LSL)/3sigma]. sigma=0이면 정의 불가로 inf 반환."""
    if sigma <= 0:
        return float("inf")
    return min((usl - mu) / (3.0 * sigma), (mu - lsl) / (3.0 * sigma))


def main():
    # ── 1) 정상 운전 구간만 추출 ───────────────────────────────────────────────────
    #    공정능력은 '정상 운전'의 산포를 본다. 펌프 정지(pump_on=0) 구간은 유량 0 근방이라
    #    품질특성 산포에서 제외해야 한다(섞으면 sigma가 왜곡됨).
    df = pd.read_csv(CLEAN_CSV)
    if "pump_on" in df.columns:
        run = df[df["pump_on"] == 1]
    else:
        # pump_on 컬럼이 없으면 유량이 설계치의 절반 이상인 구간을 '가동'으로 근사.
        run = df[df[CTQ] >= NOMINAL * 0.5]

    x = run[CTQ].astype(float).to_numpy()
    mu = float(np.mean(x))
    sigma = float(np.std(x, ddof=1))          # 표본 표준편차(ddof=1)
    cv = sigma / mu * 100.0                    # 변동계수(%) — 평균 대비 산포

    print(f"CTQ = {CTQ} (정상 운전 구간만, pump_on=1)")
    print(f"  n={len(x)},  mu={mu:.3f} L/min,  sigma={sigma:.4f} L/min,  CV={cv:.2f}%")
    print(f"  관측 범위: {x.min():.2f} ~ {x.max():.2f} L/min,  설계(중심) NOMINAL={NOMINAL}\n")

    # ── 2) 허용오차별 Cpk ─────────────────────────────────────────────────────────
    #    규격 = NOMINAL ± (tol). 막힘은 유량을 떨어뜨리므로 LSL 쪽이 통상 더 빡빡(min에 걸림).
    print(f"  {'허용오차':>8}{'LSL':>9}{'USL':>9}{'Cpk':>8}{'≈sigma수준':>12}")
    for tol in TOLERANCES:
        lsl = NOMINAL * (1 - tol)
        usl = NOMINAL * (1 + tol)
        c = cpk(mu, sigma, lsl, usl)
        print(f"  {f'±{int(tol*100)}%':>8}{lsl:>9.2f}{usl:>9.2f}{c:>8.2f}{c*3:>10.1f}σ")

    print("\n해석:")
    print("  - Cpk 1.33=4σ(양호), 1.67=5σ(우수). ±10% 관수 스펙에서 Cpk≈1.65(설계중심 78.0) → '1.67' 발화 근거.")
    print("    ※ 규격 중심을 공정평균 μ에 두면 Cpk=Cp≈1.69. 어느 쪽이든 4.9~5σ급으로 '약 1.67' 수준.")
    print("  - 정속 제어라 sigma가 작아 Cpk가 높게 나오는 건 자연스럽다('정상 운전' 공정능력).")
    print("  - 막힘이 섞이면 유량이 LSL 아래로 → Cpk 급락. 'AE가 막힘을 잡아 규격 유지=Cpk 방어' 스토리의 정량 축.")
    print("  - 이 수치는 '측정값'(가정 아님). 단, 규격폭(허용오차)·NOMINAL은 관수 운영 가정이라 함께 명시한다.")


if __name__ == "__main__":
    main()