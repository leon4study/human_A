import pandas as pd


def check_columns(new_file_path: str):
    """
    새 CSV 또는 Excel 파일을 받아 기준 컬럼과 비교.
    빠진 컬럼 / 추가된 컬럼 / 일치 여부 출력.
    """
    if new_file_path.endswith(".csv"):
        new_df = pd.read_csv(new_file_path, nrows=0)  # 헤더만 읽음
    else:
        new_df = pd.read_excel(new_file_path, nrows=0)

    new_cols = set(new_df.columns.tolist())
    baseline_cols = set(BASELINE_COLS)

    missing = sorted(baseline_cols - new_cols)  # 기준엔 있는데 새 파일엔 없음
    extra = sorted(new_cols - baseline_cols)  # 새 파일에만 있음
    matched = sorted(baseline_cols & new_cols)

    print("=" * 55)
    print(f"  파일: {new_file_path}")
    print(f"  기준 컬럼: {len(baseline_cols)}개 | 새 파일 컬럼: {len(new_cols)}개")
    print("=" * 55)

    if not missing and not extra:
        print("  ✅ 완전 일치 — 컬럼 변동 없음")
    else:
        if missing:
            print(f"\n  ❌ 빠진 컬럼 ({len(missing)}개) — 기준엔 있는데 새 파일에 없음")
            for c in missing:
                print(f"      - {c}")

        if extra:
            print(f"\n  ➕ 추가된 컬럼 ({len(extra)}개) — 새 파일에만 있음")
            for c in extra:
                print(f"      + {c}")

    print(f"\n  ✔  일치 컬럼: {len(matched)}개")
    return {"missing": missing, "extra": extra, "matched": matched}


# ── 사용법 ────────────────────────────────────────────────────────
result = check_columns(
    "C:/Users/ui203/OneDrive/문서/green_project/smartfarm_code/output/selected_smartfarm.csv"
)
result = check_columns(
    "C:/Users/ui203/OneDrive/문서/green_project/output/smartfarm_20260401.csv"
)
