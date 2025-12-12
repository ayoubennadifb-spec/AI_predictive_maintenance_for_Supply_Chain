import json
from pathlib import Path
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import joblib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
panel_path = PROJECT_ROOT / 'data' / 'processed' / 'consumption_panel_dataset.parquet'
results_dir = PROJECT_ROOT / 'data' / 'results'
results_dir.mkdir(parents=True, exist_ok=True)

if not panel_path.exists():
    raise SystemExit(f"Missing dataset {panel_path}")

df = pd.read_parquet(panel_path)
feature_cols = [c for c in df.columns if c not in {'code_piece','year','target_cons','split'}]
X = df[feature_cols].astype(float).reset_index(drop=True)
y = df['target_cons'].astype(float).reset_index(drop=True)

model = HistGradientBoostingRegressor(
    learning_rate=0.1,
    max_depth=3,
    max_iter=200,
    min_samples_leaf=5,
    random_state=0,
)
model.fit(X, y)

out_model = results_dir / 'hist_gradient_boosting_model.pkl'
joblib.dump({'model': model, 'features': feature_cols}, out_model)

meta = {
    'model_path': str(out_model),
    'model_type': 'HistGradientBoostingRegressor',
    'params': {
        'learning_rate': 0.1,
        'max_depth': 3,
        'max_iter': 200,
        'min_samples_leaf': 5,
        'random_state': 0,
    },
    'feature_cols': feature_cols,
    'dataset': str(panel_path),
}
with (results_dir / 'hist_gradient_boosting_model_meta.json').open('w', encoding='utf-8') as f:
    json.dump(meta, f, indent=2)
print('Saved model to', out_model)
