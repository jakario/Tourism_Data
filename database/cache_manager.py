import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from database.schema import get_connection, init_db

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, ttl_hours: int = 24):
        self.ttl_hours = ttl_hours
        init_db()

    def _hash_params(self, params: dict) -> str:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, source: str, endpoint: str, params: dict = None) -> Optional[Dict]:
        params = params or {}
        params_hash = self._hash_params(params)
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT response, expires_at FROM api_cache
                   WHERE source = ? AND endpoint = ? AND params_hash = ?
                   LIMIT 1""",
                (source, endpoint, params_hash)
            ).fetchone()

            if row is None:
                return None

            expires = datetime.fromisoformat(row["expires_at"])
            is_expired = datetime.now() > expires

            conn.execute(
                "UPDATE api_cache SET hit_count = hit_count + 1, last_accessed = datetime('now') WHERE source = ? AND endpoint = ? AND params_hash = ?",
                (source, endpoint, params_hash)
            )
            conn.commit()

            return {
                "data": json.loads(row["response"]),
                "cached": True,
                "expired": is_expired,
                "expires_at": row["expires_at"]
            }
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
        finally:
            conn.close()

    def set(self, source: str, endpoint: str, params: dict, response_data: Any, status_code: int = 200) -> bool:
        params = params or {}
        params_hash = self._hash_params(params)
        expires_at = (datetime.now() + timedelta(hours=self.ttl_hours)).isoformat()
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO api_cache
                   (source, endpoint, params_hash, response, status_code, expires_at, last_accessed, hit_count)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 1)""",
                (source, endpoint, params_hash, json.dumps(response_data, ensure_ascii=False), status_code, expires_at)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
        finally:
            conn.close()

    def record_api_call(self, source: str) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO api_usage (date, source, calls)
                   VALUES (?, ?, COALESCE((SELECT calls FROM api_usage WHERE date = ? AND source = ?), 0) + 1)""",
                (today, source, today, source)
            )
            conn.commit()
        finally:
            conn.close()

    def get_todays_calls(self, source: str) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT calls FROM api_usage WHERE date = ? AND source = ?",
                (today, source)
            ).fetchone()
            return row["calls"] if row else 0
        finally:
            conn.close()

    def get_cache_stats(self) -> Dict:
        conn = get_connection()
        try:
            total_entries = conn.execute("SELECT COUNT(*) as cnt FROM api_cache").fetchone()["cnt"]
            total_hits = conn.execute("SELECT SUM(hit_count) as total FROM api_cache").fetchone()["total"] or 0
            expired = conn.execute("SELECT COUNT(*) as cnt FROM api_cache WHERE expires_at < datetime('now')").fetchone()["cnt"]
            today_calls = conn.execute("SELECT COALESCE(SUM(calls), 0) as total FROM api_usage WHERE date = date('now')").fetchone()["total"]
            total_calls = conn.execute("SELECT COALESCE(SUM(calls), 0) as total FROM api_usage").fetchone()["total"]

            return {
                "cached_entries": total_entries,
                "cache_hits": total_hits,
                "expired_entries": expired,
                "today_api_calls": today_calls,
                "total_api_calls_overall": total_calls,
                "saved_calls_estimate": total_hits - total_entries  # estimate
            }
        finally:
            conn.close()

    def invalidate(self, source: str = None, endpoint: str = None) -> int:
        conn = get_connection()
        try:
            if source and endpoint:
                n = conn.execute("DELETE FROM api_cache WHERE source = ? AND endpoint = ?", (source, endpoint)).rowcount
            elif source:
                n = conn.execute("DELETE FROM api_cache WHERE source = ?", (source,)).rowcount
            else:
                n = conn.execute("DELETE FROM api_cache").rowcount
            conn.commit()
            return n
        finally:
            conn.close()

    def store_tourism_record(self, record: Dict) -> bool:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO tourism_data
                   (category, source, province, district, name_th, name_en,
                    latitude, longitude, address, phone, website, tags, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("category"),
                    record.get("source"),
                    record.get("province"),
                    record.get("district"),
                    record.get("name_th"),
                    record.get("name_en"),
                    record.get("latitude"),
                    record.get("longitude"),
                    record.get("address"),
                    record.get("phone"),
                    record.get("website"),
                    json.dumps(record.get("tags", []), ensure_ascii=False),
                    json.dumps(record.get("details", {}), ensure_ascii=False)
                )
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning(f"Store tourism record error: {e}")
            return False
        finally:
            conn.close()

    def search_tourism(self, province: str = None, category: str = None, keyword: str = None, limit: int = 5000) -> List[Dict]:
        conn = get_connection()
        try:
            query = "SELECT * FROM tourism_data WHERE 1=1"
            params = []
            if province:
                query += " AND province = ?"
                params.append(province)
            if category:
                query += " AND category = ?"
                params.append(category)
            if keyword:
                query += " AND (name_th LIKE ? OR name_en LIKE ? OR address LIKE ?)"
                kw = f"%{keyword}%"
                params.extend([kw, kw, kw])
            query += " LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        conn = get_connection()
        try:
            n = conn.execute("DELETE FROM api_cache WHERE expires_at < datetime('now')").rowcount
            conn.commit()
            return n
        finally:
            conn.close()
