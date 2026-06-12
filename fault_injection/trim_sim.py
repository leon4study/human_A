"""trim_sim.py — (B) trimmed-mean 집계 효과를 재학습 없이 시뮬(평균 vs 상위1제외)."""
import os, sys, json, glob, joblib
import numpy as np, pandas as pd, tensorflow as tf
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "src"))
from operating_point_eval import window, startup_mask_of, FAULTY_CSV, MODELS_DIR, CLEAN_CSV, EXCLUDE_FROM_OVERALL
from inference_core import actionable_feature_mask
from plot_early_warning import build_episodes

def score(sq, mask, trim):
    e = sq[:, mask]; F = e.shape[1]
    if trim <= 0 or F - trim < 1: return e.mean(1)
    s = np.sort(e, axis=1); return s[:, :F - trim].mean(1)

def load(dom):
    cfg = json.load(open(os.path.join(MODELS_DIR, f"{dom}_config.json"), encoding="utf-8"))
    m = tf.keras.models.load_model(os.path.join(MODELS_DIR, f"{dom}_model.keras"))
    sc = joblib.load(os.path.join(MODELS_DIR, f"{dom}_scaler.pkl"))
    return m, sc, cfg

def sqerr(da, m, sc, feats):
    X = pd.DataFrame(index=da.index, columns=feats, dtype=float)
    for f in feats: X[f] = da[f].astype(float).values if f in da.columns else 0.0
    Xs = sc.transform(X); return (Xs - m.predict(Xs, batch_size=512, verbose=0)) ** 2

cl = pd.read_csv(CLEAN_CSV); cl["timestamp"]=pd.to_datetime(cl["timestamp"]); cl=cl.set_index("timestamp"); cl["anomaly_label"]=0
dac = window(cl); suc = startup_mask_of(dac)
fr = pd.read_csv(FAULTY_CSV); fr["timestamp"]=pd.to_datetime(fr["timestamp"]); fr=fr.set_index("timestamp")
da = window(fr); su = startup_mask_of(da); y = da["anomaly_label"].astype(int).to_numpy(); base=(y==0)&(~su)
doms = sorted(os.path.basename(f).replace("_config.json","") for f in glob.glob(os.path.join(MODELS_DIR,"*_config.json")))
eps_nut = [e for e in build_episodes(fr) if e["mode"].startswith("nutrient")]
idx = da.index
print(f"  {'도메인':<10}{'집계':<10}{'caution':>10}{'정상FAR':>9}{'  검출(nutrient만)':<16}")
for dom in doms:
    m, sc, cfg = load(dom); feats=cfg["features"]; scoring=cfg.get("scoring_features") or feats
    mask=np.array([f in set(scoring) for f in feats],bool)
    sqc=sqerr(dac,m,sc,feats); sqv=sqerr(da,m,sc,feats)
    for trim,lbl in [(0,"mean"),(1,"trim-1")]:
        thr=float(np.percentile(score(sqc,mask,trim)[~suc],99.5))
        sv=score(sqv,mask,trim); far=sv[base].mean()
        det=""
        if dom=="nutrient":
            d=sum(((idx>=e["start"])&(idx<=e["failure"])&(sv>=thr)).any() for e in eps_nut)
            det=f"{d}/{len(eps_nut)}"
        print(f"  {dom:<10}{lbl:<10}{thr:>10.6f}{far:>8.1%}   {det}")
