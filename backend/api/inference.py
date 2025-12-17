"""
Lightweight inference pipeline to produce monthly forecasts and n_ac using the trained HistGradientBoosting model.
If anything fails, caller should handle fallback (predictions JSON).
"""

import json
from pathlib import Path
from typing import List, Dict

import joblib
import numpy as np
import pandas as pd


# Project root is the repository root (one level above the Django backend folder)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

MIN_YEAR = 2012
MAX_YEAR = 2024
N_LAGS = 3


def load_model():
    model_path = RESULTS_DIR / "hist_gradient_boosting_model.pkl"
    meta_path = RESULTS_DIR / "hist_gradient_boosting_model_meta.json"
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    bundle = joblib.load(model_path)
    model = bundle["model"]
    feature_cols = bundle["features"]
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return model, feature_cols, meta


def build_features_2025(feature_cols: List[str]) -> pd.DataFrame:
    part2_path = PROCESSED_DIR / "part2_clean_step2.parquet"
    if not part2_path.exists():
        raise FileNotFoundError(f"Dataset not found: {part2_path}")

    p2 = pd.read_parquet(part2_path)
    years = list(range(MIN_YEAR, MAX_YEAR + 1))
    target_year = MAX_YEAR + 1  # 2025
    lag_years = [target_year - i for i in range(1, N_LAGS + 1)]
    lag_cols = [f"cons_{y}" for y in lag_years]

    records: List[Dict] = []
    for _, row in p2.iterrows():
        lag_values = [float(row.get(c, 0.0) or 0.0) for c in lag_cols]
        cons_mean_3y = float(np.mean(lag_values))
        past_cols = [f"cons_{y}" for y in years if f"cons_{y}" in p2.columns]
        cons_mean_all_past = float(row[past_cols].mean()) if past_cols else 0.0
        cons_trend = lag_values[0] - lag_values[1]

        rec = {
            "code_piece": row["code_piece"],
            "lag1": lag_values[0],
            "lag2": lag_values[1],
            "lag3": lag_values[2],
            "cons_mean_3y": cons_mean_3y,
            "cons_trend": cons_trend,
            "cons_mean_all_past": cons_mean_all_past,
            "qte_installee": float(row.get("qte_installee", 0.0) or 0.0),
            "stock_actuel": float(row.get("stock_actuel", 0.0) or 0.0),
            "stock_securite": float(row.get("stock_securite", 0.0) or 0.0),
            "stock_min": float(row.get("stock_min", 0.0) or 0.0),
            "stock_max": float(row.get("stock_max", 0.0) or 0.0),
            "qte_demandee_3ans": float(row.get("qte_demandee_3ans", 0.0) or 0.0),
            "lag1_was_missing": 0,
            "lag2_was_missing": 0,
            "lag3_was_missing": 0,
            "qte_installee_was_missing": int(row.get("part2_qte_installee_was_missing", False)),
            "stock_securite_was_missing": int(row.get("part2_stock_securite_was_missing", False)),
        }
        records.append(rec)

    df_2025 = pd.DataFrame.from_records(records)
    for col in feature_cols:
        if col not in df_2025.columns:
            df_2025[col] = 0.0
    X_2025 = df_2025[feature_cols].astype(float).reset_index(drop=True)
    return df_2025[["code_piece"]].copy().assign(**{col: X_2025[col] for col in feature_cols})


def run_inference() -> pd.DataFrame:
    model, feature_cols, _ = load_model()
    feats = build_features_2025(feature_cols)
    X_2025 = feats[feature_cols].astype(float)
    preds = np.clip(model.predict(X_2025), 0, None)
    out = feats[["code_piece"]].copy()
    out["pred_2025_histgradboost"] = preds
    out["n_pm_2025"] = preds / 12.0
    return out
