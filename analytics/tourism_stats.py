from typing import Dict, List, Optional
from database.cache_manager import CacheManager
from fetchers.mots_fetcher import MOTSFetcher


class TourismStats:
    def __init__(self, cache: CacheManager, mots_fetcher: Optional[MOTSFetcher] = None):
        self.cache = cache
        self.mots = mots_fetcher

    def get_province_rankings(self, year: int = 2568, metric: str = "tourists") -> List[Dict]:
        """Get ranking of all provinces by tourism metric"""
        conn = self.cache.get_connection()
        try:
            order_field = {
                "tourists": "tourists_thai + tourists_foreign",
                "revenue": "revenue",
                "thai": "tourists_thai",
                "foreign": "tourists_foreign"
            }.get(metric, "tourists_thai + tourists_foreign")

            rows = conn.execute(
                f"""SELECT province,
                           SUM(tourists_thai) as thai,
                           SUM(tourists_foreign) as foreign,
                           SUM(revenue) as total_revenue
                    FROM province_stats
                    WHERE year = ?
                    GROUP BY province
                    ORDER BY ({order_field}) DESC
                    LIMIT 20""",
                (year,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_province_trend(self, province: str, years: int = 3) -> List[Dict]:
        """Get monthly trend for a specific province"""
        conn = self.cache.get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM province_stats
                   WHERE province = ? AND year >= ?
                   ORDER BY year, month""",
                (province, 2568 - years)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def compare_provinces(self, provinces: List[str], year: int = 2568) -> Dict:
        """Compare multiple provinces side by side"""
        results = {}
        for p in provinces:
            conn = self.cache.get_connection()
            try:
                row = conn.execute(
                    """SELECT SUM(tourists_thai) as thai, SUM(tourists_foreign) as foreign,
                              SUM(revenue) as revenue
                       FROM province_stats
                       WHERE province = ? AND year = ?""",
                    (p, year)
                ).fetchone()
                results[p] = dict(row) if row and row["thai"] else None
            finally:
                conn.close()
        return results
