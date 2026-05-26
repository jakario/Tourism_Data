import time
import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from database.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    def __init__(self, cache: CacheManager, config: Dict):
        self.cache = cache
        self.config = config
        self.max_calls_per_day = config.get("rate_limits", {}).get("max_calls_per_day", 800)
        self.min_interval = config.get("rate_limits", {}).get("min_interval_seconds", 2)
        self._last_call_time = 0.0

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        pass

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call_time = time.time()

    def _check_daily_limit(self) -> bool:
        today_calls = self.cache.get_todays_calls(self.source_name)
        if today_calls >= self.max_calls_per_day:
            logger.warning(f"[{self.source_name}] Daily limit {self.max_calls_per_day} reached!")
            return False
        return True

    def get(self, endpoint: str, params: dict = None, force_refresh: bool = False) -> Dict:
        params = params or {}

        if not force_refresh:
            cached = self.cache.get(self.source_name, endpoint, params)
            if cached is not None and not cached.get("expired", False):
                logger.info(f"[{self.source_name}] Cache HIT for {endpoint}")
                return cached["data"]
            if cached is not None and self.config.get("cache_strategy", {}).get("stale_while_revalidate", False):
                logger.info(f"[{self.source_name}] Cache STALE - returning stale + will refresh")
                thread = self._background_refresh(endpoint, params)
                return cached["data"]

        if not self._check_daily_limit():
            fallback = self.cache.get(self.source_name, endpoint, params)
            if fallback:
                logger.warning(f"[{self.source_name}] Rate limited, returning stale cache")
                return fallback["data"]
            raise RuntimeError(f"[{self.source_name}] Rate limit exceeded and no cache fallback")

        self._rate_limit()
        try:
            response = self.fetch_raw(endpoint, params)
            self.cache.set(self.source_name, endpoint, params, response)
            self.cache.record_api_call(self.source_name)
            logger.info(f"[{self.source_name}] API call SUCCESS for {endpoint}")
            return response
        except Exception as e:
            logger.error(f"[{self.source_name}] API error for {endpoint}: {e}")
            fallback = self.cache.get(self.source_name, endpoint, params)
            if fallback:
                logger.warning(f"[{self.source_name}] Error but cache fallback available")
                return fallback["data"]
            raise

    def _background_refresh(self, endpoint: str, params: dict):
        import threading
        def _refresh():
            try:
                if self._check_daily_limit():
                    self._rate_limit()
                    response = self.fetch_raw(endpoint, params)
                    self.cache.set(self.source_name, endpoint, params, response)
                    self.cache.record_api_call(self.source_name)
            except Exception as e:
                logger.warning(f"Background refresh failed for {endpoint}: {e}")
        t = threading.Thread(target=_refresh, daemon=True)
        t.start()
        return t

    def bulk_fetch(self, endpoints: List[tuple]) -> Dict[str, Any]:
        results = {}
        for endpoint, params in endpoints:
            try:
                results[f"{endpoint}_{params}"] = self.get(endpoint, params)
            except Exception as e:
                logger.error(f"Bulk fetch error {endpoint}: {e}")
                results[f"{endpoint}_{params}"] = {"error": str(e)}
        return results
