import math
from typing import List, Tuple, Dict
from app.services.data_fetcher import SFDataFetcher
from app.services.risk_model import RiskScorer

class RouteCalculator:
    def __init__(self):
        self.data_fetcher = SFDataFetcher()
        self.risk_scorer = RiskScorer()
    
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        # calculate distance between two points in meters
        R = 6371000  # earth radius in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def generate_waypoints(self, start_lat: float, start_lng: float, 
                          end_lat: float, end_lng: float, num_points: int = 10) -> List[Tuple[float, float]]:
        # simple linear interpolation for waypoints
        # in production, would use actual routing api like mapbox/osrm
        waypoints = []
        for i in range(num_points + 1):
            t = i / num_points
            lat = start_lat + (end_lat - start_lat) * t
            lng = start_lng + (end_lng - start_lng) * t
            waypoints.append((lat, lng))
        return waypoints
    
    def calculate_route(self, start_lat: float, start_lng: float,
                       end_lat: float, end_lng: float) -> Dict:
        # generate waypoints along route
        waypoints = self.generate_waypoints(start_lat, start_lng, end_lat, end_lng)
        
        # fetch risk data for each waypoint (assume night time for walking safety)
        risk_features = []
        for lat, lng in waypoints:
            features = self.data_fetcher.get_risk_features(lat, lng, radius=200, is_night=True)
            risk_features.append(features)
        
        # calculate overall risk score
        risk_score = self.risk_scorer.score_route(waypoints, risk_features)
        
        # calculate distance
        total_distance = 0.0
        for i in range(len(waypoints) - 1):
            lat1, lng1 = waypoints[i]
            lat2, lng2 = waypoints[i + 1]
            total_distance += self.haversine_distance(lat1, lng1, lat2, lng2)
        
        # estimate walking time (average 5 km/h = 1.39 m/s)
        walking_speed = 1.39  # meters per second
        estimated_time = total_distance / walking_speed
        
        return {
            "risk_score": risk_score,
            "distance": total_distance,
            "estimated_time": estimated_time,
            "waypoints": waypoints
        }

