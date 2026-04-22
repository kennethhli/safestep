import math
from typing import List, Tuple, Dict, Optional
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

        base_url = "https://api.mapbox.com/directions/v5/mapbox/walking/"
        direct_coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
        url = f"{base_url}{direct_coords}"
        params = {
            "access_token": self.mapbox_token,
            "alternatives": "true",
            "geometries": "geojson",
            "steps": "false",
            "overview": "full",
        }
        routes: List[Dict] = []
        try:
            response = requests.get(url, params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
            routes.extend(data.get("routes", []))
        except Exception:
            pass

        # fallback: ask for gentle midpoint detours to force more candidates
        mid_lat = (start_lat + end_lat) / 2
        mid_lng = (start_lng + end_lng) / 2
        d_lat = end_lat - start_lat
        d_lng = end_lng - start_lng
        length = math.sqrt((d_lat ** 2) + (d_lng ** 2)) or 1e-6
        perp_lat = -d_lng / length
        perp_lng = d_lat / length

        # about 300-500m offsets depending on latitude
        offset_deg = 0.0035
        detour_points = [
            (mid_lat + (perp_lat * offset_deg), mid_lng + (perp_lng * offset_deg)),
            (mid_lat - (perp_lat * offset_deg), mid_lng - (perp_lng * offset_deg)),
        ]

        for detour_lat, detour_lng in detour_points:
            coords = f"{start_lng},{start_lat};{detour_lng},{detour_lat};{end_lng},{end_lat}"
            detour_url = f"{base_url}{coords}"
            try:
                detour_response = requests.get(detour_url, params=params, timeout=12)
                detour_response.raise_for_status()
                detour_data = detour_response.json()
                routes.extend(detour_data.get("routes", []))
            except Exception:
                continue

        # dedupe near-identical geometry so we keep only unique options
        unique_routes: List[Dict] = []
        seen = set()
        for route in routes:
            coords = route.get("geometry", {}).get("coordinates", [])
            if not coords:
                continue
            key_points = coords[::max(1, len(coords) // 8)]
            key = tuple((round(lng, 4), round(lat, 4)) for lng, lat in key_points[:8])
            if key in seen:
                continue
            seen.add(key)
            unique_routes.append(route)

        return unique_routes

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

    def _build_hazards(self, waypoints: List[Tuple[float, float]], risk_features: List[Dict]) -> List[Dict]:
        hazards: List[Dict] = []
        for idx, features in enumerate(risk_features):
            if idx >= len(waypoints):
                continue
            lat, lng = waypoints[idx]

            if (not features.get("data_unavailable", False)) and features.get("street_lights", 0) <= 1:
                hazards.append({
                    "type": "low_lighting",
                    "severity": "low",
                    "lat": lat,
                    "lng": lng,
                    "message": "limited street lighting in this segment"
                })
            if features.get("violent_crimes", 0) >= 4:
                hazards.append({
                    "type": "high_incident_density",
                    "severity": "high",
                    "lat": lat,
                    "lng": lng,
                    "message": "higher violent incident density nearby"
                })
            elif features.get("violent_crimes", 0) >= 2:
                hazards.append({
                    "type": "incident_density",
                    "severity": "medium",
                    "lat": lat,
                    "lng": lng,
                    "message": "elevated incident activity nearby"
                })
            if features.get("accidents", 0) >= 5:
                hazards.append({
                    "type": "collision_hotspot",
                    "severity": "high",
                    "lat": lat,
                    "lng": lng,
                    "message": "collision hotspot near this segment"
                })
            elif features.get("accidents", 0) >= 3:
                hazards.append({
                    "type": "collision_risk",
                    "severity": "medium",
                    "lat": lat,
                    "lng": lng,
                    "message": "moderate collision risk in this area"
                })

        # dedupe nearby same-type hazards so map stays readable
        deduped: List[Dict] = []
        seen = set()
        for hazard in hazards:
            key = (
                hazard["type"],
                round(hazard["lat"], 4),
                round(hazard["lng"], 4),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hazard)
        return deduped[:20]

    def _risk_along_path(self, dist_from_start: float, path_length: float, waypoint_risks: List[float]) -> float:
        # smooth blend between scored waypoints so the line is not one flat color
        if not waypoint_risks:
            return 0.5
        if path_length <= 1e-6 or len(waypoint_risks) == 1:
            return min(1.0, max(0.0, waypoint_risks[0]))
        t = min(1.0, max(0.0, dist_from_start / path_length))
        pos = t * (len(waypoint_risks) - 1)
        i = int(pos)
        frac = pos - i
        if i >= len(waypoint_risks) - 1:
            return min(1.0, max(0.0, waypoint_risks[-1]))
        a = waypoint_risks[i]
        b = waypoint_risks[i + 1]
        return min(1.0, max(0.0, a * (1.0 - frac) + b * frac))

    def _build_risk_segments(
        self,
        coords_lng_lat: List[List[float]],
        waypoints: List[Tuple[float, float]],
        risk_features: List[Dict],
    ) -> List[Dict]:
        waypoint_risks = [self.risk_scorer.calculate_risk_score(f) for f in risk_features]
        if len(coords_lng_lat) < 2 or not waypoint_risks:
            return []

        n = len(coords_lng_lat)
        # more samples along the line = more chances for color breaks
        stride = max(1, n // 900)
        indices: List[int] = list(range(0, n, stride))
        if indices[-1] != n - 1:
            indices.append(n - 1)

        sampled = [coords_lng_lat[i] for i in indices]
        cum_dist: List[float] = [0.0]
        for i in range(1, len(sampled)):
            lng_a, lat_a = sampled[i - 1]
            lng_b, lat_b = sampled[i]
            cum_dist.append(
                cum_dist[-1]
                + self.haversine_distance(lat_a, lng_a, lat_b, lng_b)
            )
        path_len = cum_dist[-1]

        vertex_risks = [
            self._risk_along_path(d, path_len, waypoint_risks) for d in cum_dist
        ]

        # local feature bump so map picks up DataSF variation along the line (not just one flat model value)
        for j in range(len(vertex_risks)):
            lng_j, lat_j = sampled[j]
            bump_num = 0.0
            bump_den = 0.0
            for k, (wlat, wlng) in enumerate(waypoints):
                dist_m = self.haversine_distance(lat_j, lng_j, wlat, wlng) + 75.0
                wgt = 1.0 / dist_m
                f = risk_features[k]
                bump_k = min(
                    0.28,
                    f.get("violent_crimes", 0) * 0.017
                    + f.get("night_violent_crimes", 0) * 0.012
                    + f.get("accidents", 0) * 0.009
                    + max(0, 6 - f.get("street_lights", 0)) * 0.013
                    + max(0, 15 - f.get("pedestrian_activity", 0)) * 0.004,
                )
                bump_num += wgt * bump_k
                bump_den += wgt
            local_bump = bump_num / bump_den if bump_den > 0 else 0.0
            blended = vertex_risks[j] * 0.55 + (vertex_risks[j] + local_bump * 0.85) * 0.45
            vertex_risks[j] = min(1.0, max(0.0, blended))

        def bucket(r: float) -> float:
            return round(r * 24) / 24

        segments: List[Dict] = []
        cur_bucket: Optional[float] = None
        cur_coords: Optional[List[List[float]]] = None
        cur_max = 0.0

        def flush_segment():
            nonlocal cur_coords, cur_max
            if cur_coords is not None and len(cur_coords) >= 2:
                segments.append({"coordinates": cur_coords, "risk": min(1.0, cur_max)})
            cur_coords = None

        for i in range(1, len(sampled)):
            lng_a, lat_a = sampled[i - 1]
            lng_b, lat_b = sampled[i]
            edge_risk = max(vertex_risks[i - 1], vertex_risks[i])
            b = bucket(edge_risk)
            if cur_bucket is None:
                cur_bucket = b
                cur_coords = [[lng_a, lat_a], [lng_b, lat_b]]
                cur_max = edge_risk
            elif b == cur_bucket:
                assert cur_coords is not None
                cur_coords.append([lng_b, lat_b])
                cur_max = max(cur_max, edge_risk)
            else:
                flush_segment()
                cur_bucket = b
                cur_coords = [[lng_a, lat_a], [lng_b, lat_b]]
                cur_max = edge_risk

        flush_segment()

        if not segments:
            return []

        if len(segments) <= 2 and len(sampled) >= 3:
            segments = []
            for i in range(1, len(sampled)):
                lng_a, lat_a = sampled[i - 1]
                lng_b, lat_b = sampled[i]
                edge_risk = max(vertex_risks[i - 1], vertex_risks[i])
                segments.append(
                    {
                        "coordinates": [[lng_a, lat_a], [lng_b, lat_b]],
                        "risk": min(1.0, edge_risk),
                    }
                )

        # blend model risk with local feature pressure so color differences are visible along the path
        raw_vals = [s["risk"] for s in segments]
        lo = min(raw_vals)
        hi = max(raw_vals)
        span = hi - lo

        waypoint_pressure = []
        for f in risk_features:
            pressure = (
                f.get("violent_crimes", 0) * 0.30
                + f.get("night_violent_crimes", 0) * 0.22
                + f.get("accidents", 0) * 0.18
                + max(0, 5 - f.get("street_lights", 0)) * 0.17
                + max(0, 14 - f.get("pedestrian_activity", 0)) * 0.04
            )
            waypoint_pressure.append(max(0.0, pressure))
        p_lo = min(waypoint_pressure) if waypoint_pressure else 0.0
        p_hi = max(waypoint_pressure) if waypoint_pressure else 1.0
        p_span = max(1e-6, p_hi - p_lo)

        risk_norm_vals = []
        for s in segments:
            if span < 1e-6:
                risk_norm_vals.append(0.5)
            else:
                risk_norm_vals.append(min(1.0, max(0.0, (s["risk"] - lo) / span)))

        display_vals = []
        p_norm_vals = []
        for idx, s in enumerate(segments):
            coords = s["coordinates"]
            mid = coords[len(coords) // 2]
            mid_lng, mid_lat = mid[0], mid[1]

            nearest_idx = 0
            nearest_dist = float("inf")
            for i, (wlat, wlng) in enumerate(waypoints):
                d = self.haversine_distance(mid_lat, mid_lng, wlat, wlng)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = i

            p_val = waypoint_pressure[nearest_idx] if waypoint_pressure else 0.0
            p_norm = min(1.0, max(0.0, (p_val - p_lo) / p_span))
            p_norm_vals.append(p_norm)

            # mostly model risk, partly local pressure for better spatial contrast
            blended = (risk_norm_vals[idx] * 0.65) + (p_norm * 0.35)
            display_vals.append(blended)

        d_lo = min(display_vals) if display_vals else 0.0
        d_hi = max(display_vals) if display_vals else 1.0
        d_span = d_hi - d_lo
        avg_source_hits = (
            sum(f.get("data_source_hits", 0) for f in risk_features) / len(risk_features)
            if risk_features else 0.0
        )
        for idx, s in enumerate(segments):
            if d_span < 1e-4:
                if avg_source_hits < 0.5:
                    # very low data coverage: show neutral caution instead of false green
                    s["risk_display"] = 0.58
                else:
                    # if model variance is flat, fall back to local feature pressure
                    s["risk_display"] = min(1.0, max(0.0, p_norm_vals[idx]))
            else:
                s["risk_display"] = min(1.0, max(0.0, (display_vals[idx] - d_lo) / d_span))

        return segments[:240]

    def calculate_route(self, start_lat: float, start_lng: float,
                       end_lat: float, end_lng: float) -> Dict:
        candidate_routes = self._fetch_walking_routes(start_lat, start_lng, end_lat, end_lng)
        if not candidate_routes:
            candidate_routes = [self._build_linear_fallback(start_lat, start_lng, end_lat, end_lng)]

        evaluated_routes = []
        for route in candidate_routes:
            coords = route.get("geometry", {}).get("coordinates", [])
            waypoints = self._sample_waypoints(coords, max_points=9)
            if len(waypoints) < 2:
                continue

            risk_features = []
            for lat, lng in waypoints:
                features = self.data_fetcher.get_risk_features(lat, lng, radius=140, is_night=True)
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
                "avg_data_source_hits": sum(f.get("data_source_hits", 0) for f in risk_features) / len(risk_features),
            }
            hazards = self._build_hazards(waypoints, risk_features)
            risk_segments = self._build_risk_segments(coords, waypoints, risk_features)
            evaluated_routes.append({
                "risk_score": risk_score,
                "distance": route_distance,
                "estimated_time": route_duration,
                "route_geometry": [(latlng[1], latlng[0]) for latlng in coords],
                "waypoints": waypoints,
                "risk_features": risk_features,
                "feature_summary": feature_summary,
                "hazards": hazards,
                "risk_segments": risk_segments,
            })

        if not evaluated_routes:
            return {
                "risk_score": 0.5,
                "distance": 0.0,
                "estimated_time": 0.0,
                "route_geometry": [],
                "waypoints": [],
                "risk_features": [],
                "feature_summary": {},
                "hazards": [],
                "risk_segments": [],
                "route_options": [],
            }

        by_safety = sorted(evaluated_routes, key=lambda r: (round(r["risk_score"], 3), r["distance"]))
        by_speed = sorted(evaluated_routes, key=lambda r: r["estimated_time"])
        safest = by_safety[0]
        fastest = by_speed[0]

        option_pool = []
        for route in [safest, fastest]:
            if route not in option_pool:
                option_pool.append(route)
        for route in by_safety:
            if route not in option_pool:
                option_pool.append(route)
            if len(option_pool) >= 3:
                break

        route_options = []
        safest_risk = safest["risk_score"]
        fastest_time = fastest["estimated_time"]
        eps_risk = 1e-6
        eps_time = 1e-6
        for idx, route in enumerate(option_pool):
            route_copy = dict(route)
            route_copy["option_id"] = idx + 1
            if route is safest and route is fastest:
                route_copy["label"] = "safest & fastest"
            elif route is safest:
                route_copy["label"] = "safest"
            elif route is fastest:
                route_copy["label"] = "fastest"
            else:
                time_delta = route["estimated_time"] - fastest_time
                risk_delta = route["risk_score"] - safest_risk
                is_strictly_slower = time_delta > eps_time
                is_strictly_riskier = risk_delta > eps_risk
                if (not is_strictly_riskier) and is_strictly_slower:
                    route_copy["label"] = "safer alternative"
                elif is_strictly_riskier and (not is_strictly_slower):
                    route_copy["label"] = "faster alternative"
                elif is_strictly_riskier and is_strictly_slower:
                    route_copy["label"] = "balanced alternative"
                elif abs(risk_delta) <= eps_risk and abs(time_delta) <= eps_time:
                    route_copy["label"] = "similar alternative"
                elif not is_strictly_riskier:
                    route_copy["label"] = "safer alternative"
                else:
                    route_copy["label"] = "faster alternative"
            route_options.append(route_copy)

        selected = route_options[0]
        return {
            **selected,
            "route_options": route_options,
            "route_options_considered": len(evaluated_routes),
        }

