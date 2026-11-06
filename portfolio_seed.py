"""Generate deterministic, entirely synthetic portfolio data. No OCP source files are read."""
from pathlib import Path
import os
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from api.models import UserProfile

OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(2026)
rows = []
for i in range(120):
    recent = rng.poisson(rng.uniform(6, 60), size=13)
    stock = int(rng.integers(0, 120))
    row = {
        "code_piece": f"DEMO-{i+1:04d}",
        "qte_installee": int(rng.integers(1, 25)),
        "stock_actuel": stock,
        "stock_securite": int(rng.integers(5, 35)),
        "stock_min": 5, "stock_max": 150,
        "qte_demandee_3ans": int(recent[-3:].sum()),
        "Délai de livr prévi": int(rng.integers(7, 90)),
        "prix_uni_final": round(float(rng.uniform(15, 800)), 2),
        "Désignation langue": f"Synthetic industrial spare part {i+1}",
        "classif": ["urgent", "moyen", "normal"][i % 3],
        "cons_moy_mensuelle": float(recent[-3:].mean()/12),
    }
    for y, v in zip(range(2012, 2025), recent):
        row[f"cons_{y}"] = int(v)
    rows.append(row)
pd.DataFrame(rows).to_parquet(OUT / "part2_clean_step2.parquet", index=False)
User = get_user_model()
user, created = User.objects.get_or_create(username="portfolio_demo", defaults={"first_name":"Portfolio Demo","email":""})
if created:
    user.set_unusable_password()
    user.save(update_fields=["password"])
UserProfile.objects.update_or_create(user=user, defaults={"role":"manager","nom":"Portfolio Demo"})
print("Synthetic demo dataset generated: 120 spare parts; public demo account has no password.")
