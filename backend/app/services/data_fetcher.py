import requests
import os
from typing import List, Dict, Tuple, Optional
from app.config import settings

class SFDataFetcher:
    def __init__(self):
        self.base_url = settings.SF_DATA_API_BASE
        self.api_key = os.getenv("SF_DATA_API_KEY")
        self.headers = {}
        self.request_timeout = 7.0
        self._feature_cache: Dict[Tuple[float, float, int, bool], Dict] = {}
        if self.api_key:
            self.headers["X-App-Token"] = self.api_key
        self.debug = os.getenv("SF_DATA_DEBUG", "false").lower() == "true"

    def _debug_log(self, message: str):
        if self.debug:
            print(f"[sf-data-debug] {message}")

    def _get_bounds(self, lat: float, lng: float, radius_meters: int) -> Tuple[float, float]:
        # keep this simple for now, enough for neighborhood-level lookup
        safe_lat = max(abs(lat), 0.1)
        lat_offset = radius_meters / 111000
        lng_offset = radius_meters / (111000 * safe_lat)
        return lat_offset, lng_offset

    def _extract_lat_lng(self, row: Dict) -> Optional[Tuple[float, float]]:
        # handle common socrata shapes across datasets
        direct_pairs = [
            ("latitude", "longitude"),
            ("lat", "lon"),
            ("lat", "lng"),
        ]
        for lat_key, lng_key in direct_pairs:
            if row.get(lat_key) is not None and row.get(lng_key) is not None:
                try:
                    return float(row.get(lat_key)), float(row.get(lng_key))
                except Exception:
                    pass

        for geom_key in ["location", "point", "geolocation"]:
            geom = row.get(geom_key)
            if isinstance(geom, dict):
                coords = geom.get("coordinates")
                if isinstance(coords, list) and len(coords) >= 2:
                    try:
                        lng, lat = float(coords[0]), float(coords[1])
                        return lat, lng
                    except Exception:
                        pass
                if geom.get("latitude") is not None and geom.get("longitude") is not None:
                    try:
                        return float(geom.get("latitude")), float(geom.get("longitude"))
                    except Exception:
                        pass
        return None

    def _within_radius(self, lat1: float, lng1: float, lat2: float, lng2: float, radius_m: int) -> bool:
        # good enough for local filtering
        lat_scale = 111000
        lng_scale = 111000 * max(abs(lat1), 0.1)
        d_lat = (lat2 - lat1) * lat_scale
        d_lng = (lng2 - lng1) * lng_scale
        return (d_lat * d_lat + d_lng * d_lng) ** 0.5 <= radius_m

    def _filter_rows_near_point(self, rows: List[Dict], lat: float, lng: float, radius_meters: int) -> List[Dict]:
        filtered: List[Dict] = []
        for row in rows:
            extracted = self._extract_lat_lng(row)
            if not extracted:
                continue
            r_lat, r_lng = extracted
            if self._within_radius(lat, lng, r_lat, r_lng, radius_meters):
                filtered.append(row)
        return filtered

    def _fetch_by_bbox(self, dataset_id: str, lat: float, lng: float, radius_meters: int, limit: int = 500) -> List[Dict]:
        url = f"{self.base_url}/{dataset_id}.json"
        lat_offset, lng_offset = self._get_bounds(lat, lng, radius_meters)
        params = {
            "$where": f"latitude between {lat - lat_offset} and {lat + lat_offset} and longitude between {lng - lng_offset} and {lng + lng_offset}",
            "$limit": limit
        }
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            rows = response.json()
            self._debug_log(f"{dataset_id} bbox success rows={len(rows)}")
            return rows
        except Exception as e:
            self._debug_log(f"{dataset_id} bbox failed: {e}")
            return []

    def _fetch_with_where(self, dataset_id: str, where_clause: str, limit: int = 500) -> List[Dict]:
        url = f"{self.base_url}/{dataset_id}.json"
        params = {
            "$where": where_clause,
            "$limit": limit
        }
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            rows = response.json()
            self._debug_log(f"{dataset_id} where success rows={len(rows)}")
            return rows
        except Exception as e:
            status = None
            body_snippet = ""
            try:
                status = response.status_code  # type: ignore[name-defined]
                body_snippet = response.text[:180]  # type: ignore[name-defined]
            except Exception:
                pass
            self._debug_log(
                f"{dataset_id} where failed status={status} err={e} where='{where_clause[:110]}' body='{body_snippet}'"
            )
            return []

    def _fetch_raw(self, dataset_id: str, limit: int = 1000) -> List[Dict]:
        url = f"{self.base_url}/{dataset_id}.json"
        params = {"$limit": limit}
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.request_timeout)
            response.raise_for_status()
            rows = response.json()
            self._debug_log(f"{dataset_id} raw success rows={len(rows)}")
            return rows
        except Exception as e:
            self._debug_log(f"{dataset_id} raw failed: {e}")
            return []

    def _fetch_dataset_with_strategies(self, dataset_id: str, lat: float, lng: float, radius_meters: int,
                                       where_strategies: List[str], limit: int = 500) -> List[Dict]:
        lat_offset, lng_offset = self._get_bounds(lat, lng, radius_meters)
        for template in where_strategies:
            where_clause = template.format(
                lat=lat,
                lng=lng,
                lat_min=lat - lat_offset,
                lat_max=lat + lat_offset,
                lng_min=lng - lng_offset,
                lng_max=lng + lng_offset,
                radius=radius_meters
            )
            rows = self._fetch_with_where(dataset_id, where_clause, limit=limit)
            if rows:
                self._debug_log(f"{dataset_id} strategy hit with where='{where_clause[:100]}'")
                return rows
        self._debug_log(f"{dataset_id} all where strategies missed")
        return []
    
    def fetch_crime_data(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf police incidents from datasf (current schema can vary)
        strategies = [
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max}",
        ]
        rows = self._fetch_dataset_with_strategies("wg3w-h783", lat, lng, radius_meters, strategies, limit=1000)
        if rows:
            return rows
        # fallback: raw fetch then local geofilter
        raw_rows = self._fetch_raw("wg3w-h783", limit=2000)
        if raw_rows:
            return self._filter_rows_near_point(raw_rows, lat, lng, radius_meters)
        return []
    
    def fetch_street_lights(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # dataset ids can rotate; try a few and geofilter locally
        candidate_ids = ["3psu-2p5q", "jhmw-wxhj", "dvit-zf4x"]
        for dataset_id in candidate_ids:
            raw_rows = self._fetch_raw(dataset_id, limit=2000)
            if raw_rows:
                filtered = self._filter_rows_near_point(raw_rows, lat, lng, radius_meters)
                if filtered:
                    return filtered
        return []

    def fetch_accident_data(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        raw_rows = self._fetch_raw("ubvf-ztfx", limit=2500)
        if raw_rows:
            return self._filter_rows_near_point(raw_rows, lat, lng, radius_meters)
        return []

    def fetch_pedestrian_activity(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        candidate_ids = ["t2mb-5m2v", "uu24-3a2q", "dima-8yku"]
        for dataset_id in candidate_ids:
            raw_rows = self._fetch_raw(dataset_id, limit=2500)
            if raw_rows:
                filtered = self._filter_rows_near_point(raw_rows, lat, lng, radius_meters)
                if filtered:
                    return filtered
        return []
    
    def get_risk_features(self, lat: float, lng: float, radius: int = 500, is_night: bool = True) -> Dict:
        cache_key = (round(lat, 4), round(lng, 4), radius, is_night)
        if cache_key in self._feature_cache:
            return self._feature_cache[cache_key]

        crimes = self.fetch_crime_data(lat, lng, radius)
        lights = self.fetch_street_lights(lat, lng, radius)
        accidents = self.fetch_accident_data(lat, lng, radius)
        pedestrian_activity = self.fetch_pedestrian_activity(lat, lng, radius)
        
        # count crime types - focus on walking safety
        violent_crimes = 0
        night_violent_crimes = 0
        robberies = 0
        assaults = 0
        
        for c in crimes:
            category = c.get("category", "").upper() or c.get("incident_category", "").upper()
            time_str = c.get("time", "") or c.get("incident_time", "") or ""
            
            # check if crime happened at night (6pm-6am)
            is_night_crime = False
            try:
                hour = int(time_str.split(":")[0]) if ":" in time_str else None
                if hour is not None and (hour >= 18 or hour < 6):
                    is_night_crime = True
            except:
                pass
            
            if any(v in category for v in ["ASSAULT", "ROBBERY", "WEAPONS", "HOMICIDE"]):
                violent_crimes += 1
                if is_night_crime:
                    night_violent_crimes += 1
                if "ROBBERY" in category:
                    robberies += 1
                if "ASSAULT" in category:
                    assaults += 1
        
        # count street lights (more lights = safer)
        light_count = len(lights)
        accident_count = len(accidents)

        # fallback to row count if no explicit count field exists
        pedestrian_volume = 0
        for row in pedestrian_activity:
            for key in ["pedestrian_count", "count", "volume", "total"]:
                raw_value = row.get(key)
                if raw_value is None:
                    continue
                try:
                    pedestrian_volume += int(float(raw_value))
                    break
                except Exception:
                    continue
        if pedestrian_volume == 0:
            pedestrian_volume = len(pedestrian_activity)
        
        result = {
            "total_crimes": len(crimes),
            "violent_crimes": violent_crimes,
            "night_violent_crimes": night_violent_crimes,
            "robberies": robberies,
            "assaults": assaults,
            "street_lights": light_count,
            "accidents": accident_count,
            "pedestrian_activity": pedestrian_volume,
            "has_crime_data": len(crimes) > 0,
            "has_light_data": len(lights) > 0,
            "has_accident_data": len(accidents) > 0,
            "has_pedestrian_data": len(pedestrian_activity) > 0,
            "is_night": is_night
        }
        source_hits = sum(
            [
                1 if result["has_crime_data"] else 0,
                1 if result["has_light_data"] else 0,
                1 if result["has_accident_data"] else 0,
                1 if result["has_pedestrian_data"] else 0,
            ]
        )
        result["data_source_hits"] = source_hits
        result["data_unavailable"] = source_hits == 0
        self._feature_cache[cache_key] = result
        return result

