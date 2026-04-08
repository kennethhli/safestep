import math
from typing import List, Tuple, Dict
import requests
from app.services.data_fetcher import SFDataFetcher
from app.services.risk_model import RiskScorer
from app.config import settings

class RouteCalculator:
    def __init__(self):
        self.data_fetcher = SFDataFetcher()
        self.risk_scorer = RiskScorer()
        self.mapbox_token = settings.MAPBOX_ACCESS_TOKEN
    
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
    
    def _sample_waypoints(self, coordinates: List[List[float]], max_points: int = 14) -> List[Tuple[float, float]]:
        if not coordinates:
            return []
        if len(coordinates) <= max_points:
            return [(latlng[1], latlng[0]) for latlng in coordinates]

        sampled = []
        last_idx = len(coordinates) - 1
        for i in range(max_points):
            idx = round(i * last_idx / (max_points - 1))
            lng, lat = coordinates[idx]
            sampled.append((lat, lng))
        return sampled

    def _fetch_walking_routes(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> List[Dict]:
        if not self.mapbox_token:
            return []

        url = (
            "https://api.mapbox.com/directions/v5/mapbox/walking/"
            f"{start_lng},{start_lat};{end_lng},{end_lat}"
        )
        params = {
            "access_token": self.mapbox_token,
            "alternatives": "true",
            "geometries": "geojson",
            "steps": "false",
            "overview": "full",
        }
        try:
            response = requests.get(url, params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
            return data.get("routes", [])
        except Exception:
            return []

    def _build_linear_fallback(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> Dict:
        # keep this fallback so api still works if routing provider is unavailable
        coordinates = []
        num_points = 10
        for i in range(num_points + 1):
            t = i / num_points
            lat = start_lat + (end_lat - start_lat) * t
            lng = start_lng + (end_lng - start_lng) * t
            coordinates.append([lng, lat])
        return {"geometry": {"coordinates": coordinates}, "distance": None, "duration": None}
    
    def calculate_route(self, start_lat: float, start_lng: float,
                       end_lat: float, end_lng: float) -> Dict:
        candidate_routes = self._fetch_walking_routes(start_lat, start_lng, end_lat, end_lng)
        if not candidate_routes:
            candidate_routes = [self._build_linear_fallback(start_lat, start_lng, end_lat, end_lng)]

        ranked_routes = []
        for route in candidate_routes:
            coords = route.get("geometry", {}).get("coordinates", [])
            waypoints = self._sample_waypoints(coords, max_points=14)
            if len(waypoints) < 2:
                continue

            risk_features = []
            for lat, lng in waypoints:
                features = self.data_fetcher.get_risk_features(lat, lng, radius=200, is_night=True)
                risk_features.append(features)

            risk_score = self.risk_scorer.score_route(waypoints, risk_features)
            route_distance = route.get("distance")
            route_duration = route.get("duration")

            # if provider didn't return these, compute rough values
            if route_distance is None:
                route_distance = 0.0
                for i in range(len(waypoints) - 1):
                    lat1, lng1 = waypoints[i]
                    lat2, lng2 = waypoints[i + 1]
                    route_distance += self.haversine_distance(lat1, lng1, lat2, lng2)
            if route_duration is None:
                walking_speed = 1.39
                route_duration = route_distance / walking_speed

            feature_summary = {
                "avg_total_crimes": sum(f.get("total_crimes", 0) for f in risk_features) / len(risk_features),
                "avg_violent_crimes": sum(f.get("violent_crimes", 0) for f in risk_features) / len(risk_features),
                "avg_street_lights": sum(f.get("street_lights", 0) for f in risk_features) / len(risk_features),
                "avg_accidents": sum(f.get("accidents", 0) for f in risk_features) / len(risk_features),
                "avg_pedestrian_activity": sum(f.get("pedestrian_activity", 0) for f in risk_features) / len(risk_features),
            }
            ranked_routes.append({
                "risk_score": risk_score,
                "distance": route_distance,
                "estimated_time": route_duration,
                "route_geometry": [(latlng[1], latlng[0]) for latlng in coords],
                "waypoints": waypoints,
                "risk_features": risk_features,
                "feature_summary": feature_summary,
            })

        if not ranked_routes:
            return {
                "risk_score": 0.5,
                "distance": 0.0,
                "estimated_time": 0.0,
                "route_geometry": [],
                "waypoints": [],
                "risk_features": [],
                "feature_summary": {},
            }

        # pick safest first, then shortest among very similar safety scores
        ranked_routes.sort(key=lambda r: (round(r["risk_score"], 3), r["distance"]))
        safest_route = ranked_routes[0]
        safest_route["route_options_considered"] = len(ranked_routes)
        return safest_route

