import random
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

from app.config import settings
from app.services.data_fetcher import SFDataFetcher


def compute_proxy_label(features: Dict) -> float:
    # proxy risk target derived from real source features
    risk = 0.0
    risk += min(0.45, features.get("violent_crimes", 0) * 0.04)
    risk += min(0.18, features.get("night_violent_crimes", 0) * 0.03)
    risk += min(0.20, features.get("accidents", 0) * 0.025)
    risk += min(0.12, max(0, 6 - features.get("street_lights", 0)) * 0.02)
    risk += min(0.10, max(0, 15 - features.get("pedestrian_activity", 0)) * 0.01)
    if features.get("is_night", True):
        risk += 0.05
    return float(min(max(risk, 0.0), 1.0))


def to_vector(features: Dict) -> List[float]:
    return [
        features.get("total_crimes", 0),
        features.get("violent_crimes", 0),
        features.get("night_violent_crimes", 0),
        features.get("robberies", 0),
        features.get("assaults", 0),
        features.get("street_lights", 0),
        features.get("accidents", 0),
        features.get("pedestrian_activity", 0),
        1 if features.get("is_night", False) else 0,
    ]


def sample_sf_points(n: int = 140):
    # rough sf bounds
    lat_min, lat_max = 37.70, 37.82
    lng_min, lng_max = -122.52, -122.36
    for _ in range(n):
        yield (
            random.uniform(lat_min, lat_max),
            random.uniform(lng_min, lng_max),
        )


def main():
    fetcher = SFDataFetcher()
    X: List[List[float]] = []
    y: List[float] = []

    points = list(sample_sf_points())
    total = len(points)
    print(f"collecting training features from {total} sampled sf points...", flush=True)
    for idx, (lat, lng) in enumerate(points, start=1):
        features = fetcher.get_risk_features(lat, lng, radius=220, is_night=True)
        if features.get("data_unavailable", False):
            # retry with broader windows before giving up on this sample
            features = fetcher.get_risk_features(lat, lng, radius=500, is_night=True)
        if features.get("data_unavailable", False):
            features = fetcher.get_risk_features(lat, lng, radius=900, is_night=True)
        # skip full miss points where all sources fail
        if features.get("data_unavailable", False):
            if idx % 10 == 0:
                print(f"[{idx}/{total}] skipped (no data sources hit)", flush=True)
            if idx == 30 and len(X) == 0:
                raise RuntimeError(
                    "no DataSF source hits in first 30 samples; check network/API access and dataset query connectivity"
                )
            continue
        X.append(to_vector(features))
        y.append(compute_proxy_label(features))
        if idx % 10 == 0:
            print(f"[{idx}/{total}] accepted rows: {len(X)}", flush=True)

    if len(X) < 30:
        raise RuntimeError("not enough training points collected from DataSF")

    X_arr = np.array(X, dtype=float)
    y_arr = np.array(y, dtype=float)

    X_train, X_test, y_train, y_test = train_test_split(
        X_arr, y_arr, test_size=0.2, random_state=42
    )
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=10,
        random_state=42,
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    print("training complete, saving model artifact...", flush=True)

    artifact_path = Path(settings.MODEL_ARTIFACT_PATH)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_names": [
                "total_crimes",
                "violent_crimes",
                "night_violent_crimes",
                "robberies",
                "assaults",
                "street_lights",
                "accidents",
                "pedestrian_activity",
                "is_night",
            ],
            "training_rows": len(X_arr),
            "mae": float(mae),
        },
        artifact_path,
    )
    print(f"saved model to {artifact_path}", flush=True)
    print(f"training rows: {len(X_arr)}", flush=True)
    print(f"holdout mae: {mae:.4f}", flush=True)


if __name__ == "__main__":
    main()
