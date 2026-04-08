import requests
import os
from typing import List, Dict, Tuple
from app.config import settings

class SFDataFetcher:
    def __init__(self):
        self.base_url = settings.SF_DATA_API_BASE
        self.api_key = os.getenv("SF_DATA_API_KEY")
        self.headers = {}
        if self.api_key:
            self.headers["X-App-Token"] = self.api_key

    def _get_bounds(self, lat: float, lng: float, radius_meters: int) -> Tuple[float, float]:
        # keep this simple for now, enough for neighborhood-level lookup
        safe_lat = max(abs(lat), 0.1)
        lat_offset = radius_meters / 111000
        lng_offset = radius_meters / (111000 * safe_lat)
        return lat_offset, lng_offset

    def _fetch_by_bbox(self, dataset_id: str, lat: float, lng: float, radius_meters: int, limit: int = 500) -> List[Dict]:
        url = f"{self.base_url}/{dataset_id}.json"
        lat_offset, lng_offset = self._get_bounds(lat, lng, radius_meters)
        params = {
            "$where": f"latitude between {lat - lat_offset} and {lat + lat_offset} and longitude between {lng - lng_offset} and {lng + lng_offset}",
            "$limit": limit
        }
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []

    def _fetch_with_where(self, dataset_id: str, where_clause: str, limit: int = 500) -> List[Dict]:
        url = f"{self.base_url}/{dataset_id}.json"
        params = {
            "$where": where_clause,
            "$limit": limit
        }
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
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
                return rows
        return []
    
    def fetch_crime_data(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf police incidents from datasf (current schema can vary)
        # keep only recent records so risk reflects current conditions
        strategies = [
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max} and incident_datetime >= date_add_ymd(now(), -1, 0, 0)",
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max}",
            "within_circle(location, {lat}, {lng}, {radius}) and incident_datetime >= date_add_ymd(now(), -1, 0, 0)",
            "within_circle(location, {lat}, {lng}, {radius})",
        ]
        rows = self._fetch_dataset_with_strategies("wg3w-h783", lat, lng, radius_meters, strategies, limit=1000)
        if rows:
            return rows
        return self._fetch_by_bbox("wg3w-h783", lat, lng, radius_meters, limit=1000)
    
    def fetch_street_lights(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf street lights from datasf
        strategies = [
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max}",
            "within_circle(location, {lat}, {lng}, {radius})",
            "within_circle(point, {lat}, {lng}, {radius})",
        ]
        rows = self._fetch_dataset_with_strategies("3psu-2p5q", lat, lng, radius_meters, strategies, limit=300)
        if rows:
            return rows
        return self._fetch_by_bbox("3psu-2p5q", lat, lng, radius_meters, limit=300)

    def fetch_accident_data(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf collisions from datasf
        strategies = [
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max} and accident_date >= date_add_ymd(now(), -1, 0, 0)",
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max}",
            "within_circle(point, {lat}, {lng}, {radius}) and accident_date >= date_add_ymd(now(), -1, 0, 0)",
            "within_circle(point, {lat}, {lng}, {radius})",
            "within_circle(location, {lat}, {lng}, {radius})",
        ]
        rows = self._fetch_dataset_with_strategies("ubvf-ztfx", lat, lng, radius_meters, strategies, limit=800)
        if rows:
            return rows
        return self._fetch_by_bbox("ubvf-ztfx", lat, lng, radius_meters, limit=800)

    def fetch_pedestrian_activity(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # pedestrian volume can come from multiple datasf datasets
        strategies = [
            "latitude between {lat_min} and {lat_max} and longitude between {lng_min} and {lng_max}",
            "within_circle(location, {lat}, {lng}, {radius})",
            "within_circle(point, {lat}, {lng}, {radius})",
        ]

        primary_rows = self._fetch_dataset_with_strategies("t2mb-5m2v", lat, lng, radius_meters, strategies, limit=1000)
        if primary_rows:
            return primary_rows

        # fallback portal dataset ids sometimes differ between terms and views
        alt_dataset_ids = ["uu24-3a2q", "dima-8yku"]
        for dataset_id in alt_dataset_ids:
            rows = self._fetch_dataset_with_strategies(dataset_id, lat, lng, radius_meters, strategies, limit=1000)
            if rows:
                return rows

        return self._fetch_by_bbox("t2mb-5m2v", lat, lng, radius_meters, limit=1000)
    
    def get_risk_features(self, lat: float, lng: float, radius: int = 500, is_night: bool = True) -> Dict:
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
        
        return {
            "total_crimes": len(crimes),
            "violent_crimes": violent_crimes,
            "night_violent_crimes": night_violent_crimes,
            "robberies": robberies,
            "assaults": assaults,
            "street_lights": light_count,
            "accidents": accident_count,
            "pedestrian_activity": pedestrian_volume,
            "is_night": is_night
        }

