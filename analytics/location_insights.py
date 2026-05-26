import json
import math
from typing import List, Dict, Tuple, Optional
from database.cache_manager import CacheManager


class LocationInsights:
    def __init__(self, cache: CacheManager):
        self.cache = cache

    def get_province_summary(self, province: str) -> Dict:
        """Get a summary of all tourism data for a province"""
        records = self.cache.search_tourism(province=province)
        categories = {}
        for r in records:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"count": 0, "items": []}
            categories[cat]["count"] += 1
            categories[cat]["items"].append({
                "name": r["name_th"] or r["name_en"],
                "lat": r["latitude"],
                "lng": r["longitude"]
            })

        return {
            "province": province,
            "total_records": len(records),
            "categories": categories,
            "has_location_data": any(r["latitude"] for r in records)
        }

    def find_density_clusters(self, province: str, category: str = None, grid_km: float = 5.0) -> List[Dict]:
        """
        Find high-density clusters of tourism spots using grid-based clustering.
        Useful for identifying 'hot zones' for business investment.
        Includes items with names, categories, and available details.
        """
        records = self.cache.search_tourism(province=province, category=category)
        if not records:
            return []

        coords = [(r.get("latitude"), r.get("longitude"))
                  for r in records if r.get("latitude") and r.get("longitude")]
        if not coords:
            return []

        lat_min = min(c[0] for c in coords)
        lat_max = max(c[0] for c in coords)
        lng_min = min(c[1] for c in coords)
        lng_max = max(c[1] for c in coords)

        lat_step = grid_km / 111.0
        lng_step = grid_km / (111.0 * math.cos(math.radians((lat_min + lat_max) / 2)))

        grid = {}
        for r in records:
            lat, lng = r.get("latitude"), r.get("longitude")
            if not lat or not lng:
                continue
            cell_x = int((lat - lat_min) / lat_step)
            cell_y = int((lng - lng_min) / lng_step)
            key = (cell_x, cell_y)
            if key not in grid:
                grid[key] = {"count": 0, "lats": [], "lngs": [], "items": []}
            grid[key]["count"] += 1
            grid[key]["lats"].append(lat)
            grid[key]["lngs"].append(lng)
            details = {}
            try:
                raw = r.get("details")
                if raw:
                    details = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pass
            osm_tags = details.get("osm_tags", {}) if isinstance(details, dict) else {}
            grid[key]["items"].append({
                "name": r.get("name_th") or r.get("name_en") or "?",
                "category": r.get("category"),
                "lat": lat,
                "lng": lng,
                "opening_hours": osm_tags.get("opening_hours", ""),
                "website": osm_tags.get("website", ""),
                "phone": osm_tags.get("phone", ""),
                "cuisine": osm_tags.get("cuisine", ""),
                "stars": osm_tags.get("stars", ""),
                "historic": osm_tags.get("historic", ""),
                "tourism": osm_tags.get("tourism", ""),
                "amenity": osm_tags.get("amenity", ""),
            })

        clusters = []
        for (cx, cy), data in grid.items():
            if data["count"] >= 2:
                clusters.append({
                    "grid_x": cx,
                    "grid_y": cy,
                    "count": data["count"],
                    "center_lat": sum(data["lats"]) / len(data["lats"]),
                    "center_lng": sum(data["lngs"]) / len(data["lngs"]),
                    "bounds": {
                        "lat_min": min(data["lats"]),
                        "lat_max": max(data["lats"]),
                        "lng_min": min(data["lngs"]),
                        "lng_max": max(data["lngs"])
                    },
                    "items": data["items"]
                })

        clusters.sort(key=lambda c: c["count"], reverse=True)
        return clusters

    def find_gaps(self, province: str, amenities: List[str] = None) -> Dict:
        """
        Find gaps: areas that have accommodation but few restaurants,
        or many attractions but few amenities.
        Useful for identifying business opportunities.
        """
        if amenities is None:
            amenities = ["accommodation", "restaurant", "attraction"]

        category_data = {}
        all_locations = set()
        for cat in amenities:
            records = self.cache.search_tourism(province=province, category=cat)
            category_data[cat] = records
            for r in records:
                if r.get("latitude") and r.get("longitude"):
                    all_locations.add((r["latitude"], r["longitude"]))

        pairs = []
        for i, cat1 in enumerate(amenities):
            for cat2 in amenities[i+1:]:
                if category_data[cat1] and category_data[cat2]:
                    ratio = len(category_data[cat1]) / max(len(category_data[cat2]), 1)
                    pairs.append({
                        "category_a": cat1,
                        "category_b": cat2,
                        "ratio": round(ratio, 2),
                        "count_a": len(category_data[cat1]),
                        "count_b": len(category_data[cat2]),
                        "imbalance": abs(ratio - 1.0)
                    })

        return {
            "province": province,
            "total_locations": len(all_locations),
            "per_category": {cat: len(category_data[cat]) for cat in amenities},
            "pair_comparisons": sorted(pairs, key=lambda p: p["imbalance"], reverse=True),
            "opportunity_notes": self._generate_opportunity_notes(pairs, province)
        }

    def _generate_opportunity_notes(self, pairs: List[Dict], province: str) -> List[str]:
        notes = []
        for p in pairs:
            if p["ratio"] > 3:
                notes.append(
                    f"[{province}] มี {p['category_a']} ({p['count_a']}) มากกว่า {p['category_b']} ({p['count_b']}) ถึง {p['ratio']:.0f} เท่า "
                    f"→ โอกาสเปิดธุรกิจ {p['category_b']} เพิ่ม"
                )
            elif p["ratio"] < 0.33:
                notes.append(
                    f"[{province}] มี {p['category_a']} ({p['count_a']}) น้อยกว่า {p['category_b']} ({p['count_b']}) มาก "
                    f"→ โอกาสเปิดธุรกิจ {p['category_a']} เพิ่ม"
                )
        return notes

    def nearby_places(self, lat: float, lng: float, radius_km: float = 2.0,
                      category: str = None, limit: int = 20) -> List[Dict]:
        """Find tourism records near a specific location (GPS-based)"""
        lat_range = radius_km / 111.0
        lng_range = radius_km / (111.0 * math.cos(math.radians(lat)))

        records = self.cache.search_tourism(category=category)
        nearby = []
        for r in records:
            rlat, rlng = r.get("latitude"), r.get("longitude")
            if rlat and rlng:
                if abs(rlat - lat) <= lat_range and abs(rlng - lng) <= lng_range:
                    dist = math.sqrt((rlat - lat) ** 2 + (rlng - lng) ** 2) * 111.0
                    nearby.append({**r, "distance_km": round(dist, 2)})

        nearby.sort(key=lambda x: x["distance_km"])
        return nearby[:limit]
