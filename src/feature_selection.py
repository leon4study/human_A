# run_shap_ensemble (SHAP 계산 로직 전체)
# step3_4_select_features_and_finalize (투표 및 최종 데이터셋 생성)
# run_feature_selection_experiment (총괄 오케스트레이터 함수)

import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# preprocessing.py 에서 만들어둔 전처리 함수 가져오기
from preprocessing import step1_prepare_window_data, step2_clean_and_drop_collinear


# =====================================================================
# 1. 단일 타겟에 대한 모델 학습 및 SHAP 중요도 추출 함수
# =====================================================================
def get_shap_importance(X, y, target_name, n_estimators=100, random_state=42):
    print(f"[{target_name}] 모델 학습 및 SHAP 계산 중... (전체 데이터: {len(X)}개)")

    # 1. 모델 학습 (학습은 빠르므로 전체 데이터 43,199개 모두 사용)
    # 트리가 너무 깊어지는 것을 방지하기 위해 max_depth를 15 정도로 제한하면 훨씬 빠르고 과적합도 막아줍니다.
    model = RandomForestRegressor(
        n_estimators=n_estimators, max_depth=15, random_state=random_state, n_jobs=-1
    )
    model.fit(X, y)

    # 2. SHAP 값 계산 (★핵심 최적화: SHAP 계산용 데이터는 3000개만 무작위 샘플링)
    sample_size = min(3000, len(X))
    X_sample = X.sample(n=sample_size, random_state=random_state)

    print(f"  -> SHAP 연산 가속을 위해 {sample_size}개 샘플링 완료. 계산 시작...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # 3. 피처별 SHAP 중요도 계산
    shap_sum = np.abs(shap_values).mean(axis=0)
    importance_df = (
        pd.DataFrame({"Feature": X.columns, "SHAP_Importance": shap_sum})
        .sort_values("SHAP_Importance", ascending=False)
        .reset_index(drop=True)
    )

    return explainer, shap_values, importance_df


def get_shap_importance_kmeans(X, y, target_name, n_estimators=100, random_state=42):
    """
    트리 기반 모델(Random Forest, XGBoost)은 데이터의 크기나 비율보다는 '순서(Rank)'를 기준으로 분기를 나누기 때문에 스케일링이 전혀 필요 없습니다.
    하지만 K-Means는 '유클리디안 거리(Euclidean Distance)'를 계산하기 때문에 스케일링을 안 하면 대참사가 일어납니다.
    예를 들어 압력 센서는 1000 단위로 움직이고, 밸브 상태는 0~1로 움직인다면 K-Means는 압력 센서만 보고 군집을 엉터리로 나눠버립니다.
    """

    print(
        f"[{target_name}] 모델 학습 및 K-Means SHAP 계산 중... (전체 데이터: {len(X)}개)"
    )

    # 1. 모델 학습 (RF는 스케일링이 필요 없으므로 원본 데이터 X를 그대로 사용)
    model = RandomForestRegressor(
        n_estimators=n_estimators, max_depth=15, random_state=random_state, n_jobs=-1
    )
    model.fit(X, y)

    # =====================================================================
    # 🌟 [스케일링 및 K-Means 압축 로직]
    # =====================================================================
    print(f"  -> K-Means 클러스터링을 위한 데이터 스케일링 및 대표 패턴 압축 중...")

    # [추가됨] K-Means를 위한 임시 스케일링 (평균 0, 분산 1)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(300, len(X))

    # K-Means 모델은 '스케일링된 데이터'로 학습하여 공평하게 거리를 잼
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
    kmeans.fit(X_scaled)

    # [추가됨] 💥 핵심: SHAP 계산 시 원래의 센서 단위(압력, 유량 등)로 해석하기 위해
    # 스케일링된 군집 중심점들을 다시 원래 스케일로 역변환(inverse_transform) 해줍니다.
    centers_original_scale = scaler.inverse_transform(kmeans.cluster_centers_)

    # 역변환된 중심점을 DataFrame으로 만듦
    X_background = pd.DataFrame(centers_original_scale, columns=X.columns)

    print(f"  -> 대표 패턴 {n_clusters}개 추출 및 역변환 완료. SHAP 계산 시작...")
    # =====================================================================

    # 3. SHAP 값 계산 (원래 스케일로 돌아온 X_background를 넣습니다)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_background, approximate=True)

    # 4. 피처별 SHAP 중요도 계산
    shap_sum = np.abs(shap_values).mean(axis=0)
    importance_df = (
        pd.DataFrame({"Feature": X.columns, "SHAP_Importance": shap_sum})
        .sort_values("SHAP_Importance", ascending=False)
        .reset_index(drop=True)
    )

    return explainer, shap_values, X_background, importance_df


# =====================================================================
# 2. Multi-Target SHAP Ensemble 메인 함수
# =====================================================================
def run_shap_ensemble(df, target_dict, top_ratio=0.2):
    """
    여러 타겟에 대해 SHAP 분석을 수행하고, 상위 피처들의 교집합/합집합을 도출합니다.

    :param df: 전체 데이터프레임 (파생변수 포함, 결측치 처리 완료 상태)
    :param target_dict: 타겟 이름과 해당 타겟의 '누수(Leakage) 방지용 제외 컬럼'을 매핑한 딕셔너리
    :param top_ratio: 각 타겟별로 상위 몇 %의 피처를 선정할 것인지 (기본 20%)
    :return: 최종 선정된 피처 리스트, 각 타겟별 중요도 DF 딕셔너리
    """
    all_features = df.columns.tolist()

    importance_results = {}
    shap_values_dict = {}
    x_background_dict = {}

    top_features_per_target = {}

    # 각 타겟별로 순회하며 SHAP 추출
    for target, leak_cols in target_dict.items():
        # X, y 분리 (타겟 본인과, 타겟을 계산하는 데 쓰인 부모 컬럼들 제외)
        cols_to_drop = [target] + leak_cols
        X = df.drop(columns=[col for col in cols_to_drop if col in df.columns])
        y = df[target]

        # 결측치가 있으면 RF가 안 돌아가므로 임시로 평균 채우기 (이미 전처리 하셨다면 생략 가능)
        X = X.fillna(X.mean())
        y = y.fillna(y.mean())

        # SHAP 중요도 계산
        _, shap_vals, x_bg, imp_df = get_shap_importance_kmeans(X, y, target)

        # 딕셔너리에 저장
        importance_results[target] = imp_df
        shap_values_dict[target] = shap_vals
        x_background_dict[target] = x_bg

        # 상위 N% 피처 추출
        top_n_count = max(1, int(len(X.columns) * top_ratio))
        top_features = imp_df.head(top_n_count)["Feature"].tolist()
        top_features_per_target[target] = set(top_features)

        print(f"  -> 상위 {top_ratio*100}% ({top_n_count}개) 피처 선정 완료\n")

    # 3. 앙상블 논리 적용 (교집합 및 합집합)
    list_of_sets = list(top_features_per_target.values())

    # 교집합: 3개 고장 모드 모두에서 공통으로 중요한 핵심 피처 (가장 강력함)
    intersection_features = set.intersection(*list_of_sets)

    # 합집합: 하나라도 중요하다고 뜬 피처 (풀(Pool)을 넓게 가져갈 때)
    union_features = set.union(*list_of_sets)

    # 최소 2개 이상의 타겟에서 중요하다고 꼽힌 피처 (가장 추천하는 현실적 타협안)
    from collections import Counter

    all_selected_features = [
        feat for feature_set in list_of_sets for feat in feature_set
    ]
    feature_counts = Counter(all_selected_features)
    robust_features = [feat for feat, count in feature_counts.items() if count >= 2]

    print("=" * 50)
    print("🏆 Multi-Target SHAP Ensemble 결과 요약")
    print("=" * 50)
    print(f"1. 교집합 (모두에서 중요): {len(intersection_features)}개")
    print(
        f"2. 투표(Voting, 2개 이상 타겟에서 중요): {len(robust_features)}개  <-- [AutoEncoder 추천]"
    )
    print(f"3. 합집합 (전체 풀): {len(union_features)}개")

    # 🌟 [수정됨] 3가지 앙상블 리스트를 딕셔너리로 묶어서 반환합니다.
    ensemble_lists = {
        "intersection": list(intersection_features),
        "robust": robust_features,
        "union": list(union_features),
    }

    return ensemble_lists, importance_results, shap_values_dict, x_background_dict


# ==============================================================================
# [Pipeline Step 3 & 4] SHAP 앙상블 실행 및 최종 AE 데이터 확정
# ==============================================================================
def step3_4_select_features_and_finalize(
    df_clean, df_interpret, target_dict, top_ratio=0.25
):
    print("\n🔍 [Step 3] 정제된 데이터로 SHAP 기반 피처 셀렉션을 시작합니다...")

    # 1. 앙상블 실행
    ensemble_lists, shap_results, shap_vals_dict, X_bg_dict = run_shap_ensemble(
        df_clean, target_dict, top_ratio=top_ratio
    )

    # 2. 결과 출력 (Phase 4 기능 통합)
    print("\n🎯 [Step 4] 선정된 핵심 피처 리스트 및 최종 오토인코더 데이터 확정")
    print("-" * 60)
    print(
        f"1. 교집합 피처 ({len(ensemble_lists['intersection'])}개 - 모든 고장에 관여):"
    )
    print(ensemble_lists["intersection"])

    print(
        f"\n2. Robust 피처 ({len(ensemble_lists['robust'])}개 - 추천! 2개 이상 고장에 관여):"
    )
    print(ensemble_lists["robust"])

    print(f"\n3. 합집합 피처 ({len(ensemble_lists['union'])}개 - 전체 후보군):")
    print(ensemble_lists["union"])
    print("-" * 60)

    # 3. 최종 학습용 데이터셋(X_train_ae) 구축
    X_train_ae = df_clean[ensemble_lists["robust"]].copy()

    print(f"\n✅ 최종 데이터 준비 완료!")
    print(f"  - 오토인코더 학습용 데이터 (X_train_ae) 형태: {X_train_ae.shape}")
    print(f"  - 결과 해석/모니터링용 데이터 (df_interpret) 형태: {df_interpret.shape}")

    return X_train_ae, ensemble_lists, shap_results, shap_vals_dict, X_bg_dict


# =====================================================================
# 4. 전체 파이프라인 총괄 (매니저 함수)
# =====================================================================
def run_feature_selection_experiment(df_raw, window_method, target_dict):
    """전처리부터 피처 선정까지 원스톱 실행"""
    print(f"\n" + "=" * 60)
    print(f"🚀 [EXPERIMENT] 시작: {window_method.upper()} WINDOW 방식")
    print("=" * 60)

    start_time = time.time()

    df_agg, df_interpret = step1_prepare_window_data(
        df_raw, window_method=window_method
    )
    df_clean = step2_clean_and_drop_collinear(df_agg)
    X_train_ae, ensemble_lists, shap_results, shap_vals_dict, X_bg_dict = (
        step3_4_select_features_and_finalize(
            df_clean, df_interpret, target_dict, top_ratio=0.25
        )
    )

    robust_features = ensemble_lists["robust"]
    end_time = time.time()

    print(f"\n✅ [{window_method.upper()}] 실험 완료!")
    return robust_features, X_train_ae, df_interpret, shap_results
