import numpy as np
from sklearn.ensemble import RandomForestRegressor
from typing import List, Dict, Tuple
import math

class RiskScorer:
    def __init__(self):
        # simple risk model - could be trained on historical data
        self.model = RandomForestRegressor(n_estimators=50, random_state=42)
        # initialize with dummy data to get it working
        self._initialize_model()
    
    def _initialize_model(self):
        # features: [total_crimes, violent_crimes, night_violent, robberies, assaults, lights, accidents, pedestrian_activity, is_night]
        X_dummy = np.array([
            [0, 0, 0, 0, 0, 12, 0, 40, 1],
            [6, 1, 0, 0, 1, 9, 1, 30, 1],
            [18, 5, 2, 1, 2, 6, 4, 20, 1],
            [45, 14, 9, 5, 5, 2, 10, 5, 1],
            [10, 3, 1, 1, 1, 14, 2, 55, 0],
        ] * 10)
        y_dummy = np.array([0.1, 0.3, 0.6, 0.9, 0.2] * 10)
        self.model.fit(X_dummy, y_dummy)
    
    def calculate_risk_score(self, features: Dict) -> float:
        # extract features focused on walking safety
        feature_vector = np.array([[
            features.get("total_crimes", 0),
            features.get("violent_crimes", 0),
            features.get("night_violent_crimes", 0),
            features.get("robberies", 0),
            features.get("assaults", 0),
            features.get("street_lights", 0),
            features.get("accidents", 0),
            features.get("pedestrian_activity", 0),
            1 if features.get("is_night", False) else 0
        ]])
        
        # get base risk from model
        base_risk = self.model.predict(feature_vector)[0]
        
        # adjust for lighting - more lights = safer
        light_count = features.get("street_lights", 0)
        light_factor = max(0.7, 1.0 - (light_count * 0.02))  # each light reduces risk slightly
        
        # if it's night and no lights, increase risk
        if features.get("is_night", False) and light_count == 0:
            base_risk *= 1.3

        accidents = features.get("accidents", 0)
        if accidents > 0:
            base_risk *= min(1.35, 1.0 + (accidents * 0.03))

        # busier pedestrian areas can feel safer up to a point
        pedestrian_activity = features.get("pedestrian_activity", 0)
        if pedestrian_activity > 20:
            base_risk *= 0.92
        elif pedestrian_activity < 5 and features.get("is_night", False):
            base_risk *= 1.08
        
        # normalize to 0-1 scale
        risk_score = min(max(base_risk * light_factor, 0.0), 1.0)
        
        return float(risk_score)
    
    def score_route(self, waypoints: List[Tuple[float, float]], risk_features: List[Dict]) -> float:
        # calculate weighted risk along route
        if not waypoints or not risk_features:
            return 0.5  # default medium risk
        
        total_risk = 0.0
        total_weight = 0.0
        
        for i, (lat, lng) in enumerate(waypoints):
            if i < len(risk_features):
                features = risk_features[i]
                risk = self.calculate_risk_score(features)
                
                # weight by distance (closer waypoints matter more)
                weight = 1.0 / (i + 1)
                total_risk += risk * weight
                total_weight += weight
        
        if total_weight > 0:
            return total_risk / total_weight
        return 0.5

