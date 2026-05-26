import requests
import logging
import time
from typing import Dict, List, Optional
from database.cache_manager import CacheManager

logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

PROVINCE_BOUNDS = {
    "เชียงใหม่":       [18.2, 98.0, 20.3, 99.6],
    "ภูเก็ต":          [7.6,  98.1, 8.3,  98.6],
    "ชลบุรี":          [12.8, 100.6, 13.7, 101.3],
    "กระบี่":          [7.4,  98.5, 8.9,  99.4],
    "สุราษฎร์ธานี":    [8.3,  98.5, 10.0, 99.9],
    "กรุงเทพมหานคร":  [13.5, 100.3, 14.0, 100.8],
    "ประจวบคีรีขันธ์": [10.7, 99.0, 12.9, 100.2],
    "พังงา":          [7.9,  98.0, 9.9,  99.0],
    "อยุธยา":         [14.0, 100.1, 14.8, 101.0],
    "เชียงราย":       [19.4, 99.3, 20.6, 100.9],
}


class OSMFetcher:
    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.last_call = 0.0
        self.min_interval = 6.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        })

    def _rate_limit(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()

    def _overpass_query(self, query: str) -> Optional[Dict]:
        for url in OVERPASS_URLS:
            try:
                self._rate_limit()
                resp = self.session.post(url, data={"data": query}, timeout=150)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Overpass {url} -> {resp.status_code}")
                if resp.status_code in (403, 429, 504):
                    time.sleep(8)
                    continue
            except Exception as e:
                logger.warning(f"Overpass {url} error: {e}")
                time.sleep(5)
        return None

    def fetch_temples(self, province: str) -> List[Dict]:
        bounds = PROVINCE_BOUNDS.get(province)
        if not bounds:
            return []
        minlat, minlon, maxlat, maxlon = bounds
        query = f"""[out:json][timeout:90];
(node["amenity"="place_of_worship"]["religion"="buddhist"]({minlat},{minlon},{maxlat},{maxlon});
 way["amenity"="place_of_worship"]["religion"="buddhist"]({minlat},{minlon},{maxlat},{maxlon}););
out center tags 1500;"""
        data = self._overpass_query(query)
        if not data:
            return []
        return self._parse_elements(data, province, "temple")

    def fetch_ancient_sites(self, province: str) -> List[Dict]:
        bounds = PROVINCE_BOUNDS.get(province)
        if not bounds:
            return []
        minlat, minlon, maxlat, maxlon = bounds
        query = f"""[out:json][timeout:60];
(node["historic"="archaeological_site"]({minlat},{minlon},{maxlat},{maxlon}););
out center tags 500;"""
        data = self._overpass_query(query)
        if not data:
            return []
        return self._parse_elements(data, province, "ancient_site")

    def fetch_restaurants(self, province: str) -> List[Dict]:
        bounds = PROVINCE_BOUNDS.get(province)
        if not bounds:
            return []
        minlat, minlon, maxlat, maxlon = bounds
        query = f"""[out:json][timeout:60];
(node["amenity"~"restaurant|fast_food|cafe"]({minlat},{minlon},{maxlat},{maxlon});
 way["amenity"~"restaurant|fast_food|cafe"]({minlat},{minlon},{maxlat},{maxlon}););
out center tags 1000;"""
        data = self._overpass_query(query)
        if not data:
            return []
        return self._parse_elements(data, province, "restaurant")

    def fetch_accommodations(self, province: str) -> List[Dict]:
        bounds = PROVINCE_BOUNDS.get(province)
        if not bounds:
            return []
        minlat, minlon, maxlat, maxlon = bounds
        query = f"""[out:json][timeout:60];
(node["tourism"~"hotel|guest_house|hostel|motel|resort|chalet"]({minlat},{minlon},{maxlat},{maxlon});
 way["tourism"~"hotel|guest_house|hostel|motel|resort|chalet"]({minlat},{minlon},{maxlat},{maxlon}););
out center tags 1000;"""
        data = self._overpass_query(query)
        if not data:
            return []
        return self._parse_elements(data, province, "accommodation")

    def fetch_attractions(self, province: str) -> List[Dict]:
        bounds = PROVINCE_BOUNDS.get(province)
        if not bounds:
            return []
        minlat, minlon, maxlat, maxlon = bounds
        query = f"""[out:json][timeout:60];
(node["tourism"~"attraction|museum|zoo|theme_park|viewpoint"]({minlat},{minlon},{maxlat},{maxlon});
 way["tourism"~"attraction|museum|zoo|theme_park|viewpoint"]({minlat},{minlon},{maxlat},{maxlon}););
out center tags 1000;"""
        data = self._overpass_query(query)
        if not data:
            return []
        return self._parse_elements(data, province, "attraction")

    def _parse_elements(self, data: Dict, province: str, category: str) -> List[Dict]:
        results = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name_th = tags.get("name:th", "") or tags.get("name", "")
            name_en = tags.get("name:en", "")
            if not name_th and not name_en:
                continue
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            results.append({
                "category": category,
                "source": "osm",
                "province": province,
                "name_th": name_th,
                "name_en": name_en,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "address": tags.get("addr:full", ""),
                "tags": [t for t in [tags.get("historic"), tags.get("religion")] if t],
                "details": {
                    "osm_id": el["id"],
                    "osm_type": el["type"],
"osm_tags": {k: v for k, v in tags.items()
             if k in ("addr:province", "addr:district", "historic", "religion", "website", "tourism", "amenity", "cuisine", "stars", "opening_hours", "phone", "email", "description", "wikipedia", "wheelchair", "addr:full", "contact:phone", "contact:website")}
                }
            })
        return results

    def fetch_and_store(self, province: str, category: str = None) -> Dict:
        stored = {"temple": 0, "ancient_site": 0, "restaurant": 0, "accommodation": 0, "attraction": 0}
        cats = [category] if category else list(stored.keys())
        FETCH_MAP = {
            "temple": self.fetch_temples,
            "ancient_site": self.fetch_ancient_sites,
            "restaurant": self.fetch_restaurants,
            "accommodation": self.fetch_accommodations,
            "attraction": self.fetch_attractions,
        }
        for cat in cats:
            fetcher = FETCH_MAP.get(cat)
            if not fetcher:
                logger.warning(f"Unknown OSM category: {cat}")
                continue
            try:
                records = fetcher(province)
            except Exception as e:
                logger.error(f"Error fetching {cat} for {province}: {e}")
                continue
            for rec in records:
                if self.cache.store_tourism_record(rec):
                    stored[cat] = stored.get(cat, 0) + 1
            logger.info(f"OSM {province}/{cat}: {len(records)} found, {stored[cat]} stored")
        return stored
