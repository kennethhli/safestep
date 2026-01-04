import requests
import os
from typing import List, Dict, Optional
from app.config import settings

class SFDataFetcher:
    def __init__(self):
        self.base_url = settings.SF_DATA_API_BASE
        self.api_key = os.getenv("SF_DATA_API_KEY")
        self.headers = {}
        if self.api_key:
            self.headers["X-App-Token"] = self.api_key
    
    def fetch_crime_data(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf crime dataset
        dataset_id = "wg3w-h783"
        url = f"{self.base_url}/{dataset_id}.json"
        
        # approximate lat/lng bounds for radius
        lat_offset = radius_meters / 111000
        lng_offset = radius_meters / (111000 * abs(lat))
        
        params = {
            "$where": f"latitude between {lat - lat_offset} and {lat + lat_offset} and longitude between {lng - lng_offset} and {lng + lng_offset}",
            "$limit": 1000
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"error fetching crime data: {e}")
            return []
    
    def fetch_street_lights(self, lat: float, lng: float, radius_meters: int = 500) -> List[Dict]:
        # sf street lights dataset
        dataset_id = "3psu-2p5q"  # common sf street lights dataset
        url = f"{self.base_url}/{dataset_id}.json"
        
        lat_offset = radius_meters / 111000
        lng_offset = radius_meters / (111000 * abs(lat))
        
        params = {
            "$where": f"latitude between {lat - lat_offset} and {lat + lat_offset} and longitude between {lng - lng_offset} and {lng + lng_offset}",
            "$limit": 200
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # street lights data might not be available, that's ok
            return []
    
    def get_risk_features(self, lat: float, lng: float, radius: int = 500, is_night: bool = True) -> Dict:
        crimes = self.fetch_crime_data(lat, lng, radius)
        lights = self.fetch_street_lights(lat, lng, radius)
        
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
        
        return {
            "total_crimes": len(crimes),
            "violent_crimes": violent_crimes,
            "night_violent_crimes": night_violent_crimes,
            "robberies": robberies,
            "assaults": assaults,
            "street_lights": light_count,
            "is_night": is_night
        }

