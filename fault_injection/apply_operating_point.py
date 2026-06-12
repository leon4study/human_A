"""
apply_operating_point.py — 운영점(임계 분위) 재보정. 재학습 없이 config 임계값만 갱신한다.

[근거]
operating_point_eval.py의 운영점 곡선에서 막힘 검출 12/12가 P97~P99.9 분위 내내 유지됨을 확인했다.
즉 현재 caution=P99는 검출에 필요한 것보다 느슨해, 분위를 올려도 검출 손실 없이 정상 FAR만 내려간다
(P99 정상FAR 2.3% → P99.5 1.7%, lead-time 32.9h→32.4h로 거의 불변). 그래서 정상 운전 main 임계를
P99.5로 올린다(보수적 선택 — 더 미세한 전조까지 잡을 마진을 남겨, 과튜닝을 피한다).

[왜 재학습이 필요 없나]
임계값은 학습 가중치가 아니라 '정상 점수 분포의 분위'다. train.py가 학습 직후 정상 MSE(기동 제외)의
percentile로 임계를 잡는데, 그 계산을 같은 방식으로 분위만 바꿔 다시 할 뿐이다. 모델 가중치·scaler·
scoring_features·기동 band는 전혀 건드리지 않는다.

[안전]
라이브 config를 덮기 전에 models/_threshold_backup_pre_P995/ 로 원본을 백업한다(학습 run 보존본
models/runs/<run_id>/ 에도 원본 임계가 남아 있다). 기본은 dry-run(미리보기), --apply 시에만 기록.

[윈도잉 정합 — 이 스크립트가 동시에 고치는 것]
train.py는 임계를 sliding 윈도우(겹침, 학습 표본 증강)로 계산하는데, 서빙/평가(s3-sink 10분 배치,
evaluate_test_metrics, baseline_blockage_eval)는 tumbling 윈도우(비겹침)를 쓴다. 즉 기존 config 임계는
'sliding 분포의 분위'인데 'tumbling 점수'에 적용돼 왔다(eval==serve 임계 불일치). 여기서는 임계를 서빙과
같은 tumbling 분포의 분위로 다시 잡으므로, 운영점 상향(P99.5)과 윈도잉 정합을 동시에 달성한다.
출력의 'sliding격차'는 그 불일치 크기(기존 sliding 임계 대비 tumbling P99 차이)다.

실행:
    cd fault_injection && python apply_operating_point.py           # dry-run(미리보기)
    cd fault_injection && python apply_operating_point.py --apply   # 실제 적용
"""
import os
import sys
import json
import glob
import shutil

import numpy as np

# operating_point_eval의 검증된 헬퍼 재사용(중복 구현 방지, 동일 채점/윈도우 보장).
from operating_point_eval import (
    window, load_domain, domain_mse, startup_mask_of,
    MODELS_DIR, CLEAN_CSV,
)
import pandas as pd

# 새 운영점 분위. caution만 곡선으로 근거가 잡힌 값(99.5)이고, warning/critical은 그 위에서
# 단조 증가하는 격상 tier로 배치한다(곡선은 알람 트리거=caution 기준이라 warning/critical은
# '더 심각' 표시용 — 순서만 보존). 기동 band는 별도 레버라 여기서 안 바꾼다.
NEW_PCT = {"caution": 99.5, "warning": 99.8, "critical": 99.95}
SANITY_PCT_CAUTION = 99.0   # 기존 정본 caution 분위 — 재계산 검증용

BACKUP_DIR = os.path.join(MODELS_DIR, "_threshold_backup_pre_P995")


def critical_key(cfg):
    """config가 쓰는 critical 키 이름 반환(threshold_critical 또는 threshold_error)."""
    return "threshold_critical" if "threshold_critical" in cfg else "threshold_error"


def main():
    apply = "--apply" in sys.argv
    print(f"모드: {'APPLY(실제 적용)' if apply else 'DRY-RUN(미리보기)'}")
    print(f"새 분위: caution=P{NEW_PCT['caution']} / warning=P{NEW_PCT['warning']} / critical=P{NEW_PCT['critical']}\n")

    # train 정상(기동 제외) 점수로 임계를 재계산 — train.py와 동일 기준.
    clean = pd.read_csv(CLEAN_CSV)
    clean["timestamp"] = pd.to_datetime(clean["timestamp"])
    clean = clean.set_index("timestamp")
    clean["anomaly_label"] = 0
    da = window(clean)
    su = startup_mask_of(da)   # 기동 윈도우(임계는 기동 제외 분포에서 산출)

    cfg_files = sorted(glob.glob(os.path.join(MODELS_DIR, "*_config.json")))
    domains = [os.path.basename(f).replace("_config.json", "") for f in cfg_files]

    if apply:
        os.makedirs(BACKUP_DIR, exist_ok=True)

    print(f"  {'도메인':<10}{'기존(sliding)':>14}{'tumblP99':>10}{'sliding격차':>11}  ->  {'새caut(P99.5)':>14}{'새warn':>11}{'새crit':>11}")
    changes = []
    for dom in domains:
        model, scaler, cfg = load_domain(dom)
        scores = domain_mse(da, model, scaler, cfg)
        base = scores[~su]                              # 기동 제외 정상 점수(tumbling, 서빙과 동일)

        old_caut = float(cfg["threshold_caution"])      # 기존 = sliding 분포 분위(train.py)
        tumbl_p99 = float(np.percentile(base, SANITY_PCT_CAUTION))
        # sliding격차: 기존(sliding) 임계와 tumbling P99의 차이 = 윈도잉 불일치 크기(고치는 대상)
        gap = abs(tumbl_p99 - old_caut) / max(old_caut, 1e-12)

        new_caut = float(np.percentile(base, NEW_PCT["caution"]))
        new_warn = float(np.percentile(base, NEW_PCT["warning"]))
        new_crit = float(np.percentile(base, NEW_PCT["critical"]))
        ckey = critical_key(cfg)

        print(f"  {dom:<10}{old_caut:>14.6f}{tumbl_p99:>10.6f}{f'{gap:.0%}':>11}  ->  "
              f"{new_caut:>14.6f}{new_warn:>11.6f}{new_crit:>11.6f}")
        changes.append((dom, cfg, ckey, old_caut, new_caut, new_warn, new_crit))

    if not apply:
        print("\n[DRY-RUN] 변경 안 함. 적용하려면 --apply 로 다시 실행.")
        print("  'sliding격차'는 train(sliding)·serve(tumbling) 윈도잉 차이로 예상된 값(버그 아님).")
        print("  적용하면 임계가 serve와 같은 tumbling 분위(P99.5)로 정합 + 운영점 상향. 적용 후 baseline_blockage_eval로 검증.")
        return

    # 실제 적용 — 백업 후 main 임계만 교체(기동 band·scoring_features 등은 보존).
    cfg_path = lambda d: os.path.join(MODELS_DIR, f"{d}_config.json")
    for dom, cfg, ckey, old_caut, new_caut, new_warn, new_crit in changes:
        shutil.copy2(cfg_path(dom), os.path.join(BACKUP_DIR, f"{dom}_config.json"))  # 원본 백업
        cfg["threshold_caution"] = new_caut
        cfg["threshold_warning"] = new_warn
        cfg[ckey] = new_crit
        # 운영점 변경 이력을 config 안에도 한 줄 남긴다(재현/추적용).
        cfg.setdefault("operating_point_history", []).append({
            "change": "caution->tumbling P99.5 (운영점 곡선 근거 + sliding->tumbling 임계 윈도잉 정합)",
            "from_caution_sliding": old_caut, "to_caution_tumbling": new_caut,
            "pct": NEW_PCT, "basis": "tumbling(serve-consistent), 기동 제외",
        })
        with open(cfg_path(dom), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n[APPLY 완료] {len(changes)}개 도메인 main 임계 갱신. 원본 백업: {BACKUP_DIR}")
    print("  다음: baseline_blockage_eval.py 재실행으로 새 FAR/검출 확인.")


if __name__ == "__main__":
    main()