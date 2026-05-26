import requests
import logging
from typing import Dict, List
from fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)


class TATFetcher(BaseFetcher):
    """
    Fetcher for Tourism Authority of Thailand (TAT) API
    Base: https://developers.tourismthailand.org/
    Need to register at: https://developers.tourismthailand.org/
    """
    BASE_URL = "https://developers.tourismthailand.org/api/v1"

    @property
    def source_name(self) -> str:
        return "tat"

    def _get_api_key(self) -> str:
        return self.config.get("api_keys", {}).get("tat_api_key", "")

    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        api_key = self._get_api_key()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_accommodations(self, province: str = None, limit: int = 50) -> List[Dict]:
        params = {"limit": limit}
        if province:
            params["province"] = province
        data = self.get("accommodations", params)
        return data.get("data", [])

    def get_attractions(self, province: str = None, category: str = None, limit: int = 50) -> List[Dict]:
        params = {"limit": limit}
        if province:
            params["province"] = province
        if category:
            params["category"] = category
        data = self.get("attractions", params)
        return data.get("data", [])

    def get_events(self, province: str = None, limit: int = 50) -> List[Dict]:
        params = {"limit": limit}
        if province:
            params["province"] = province
        data = self.get("events", params)
        return data.get("data", [])

    def get_restaurants(self, province: str = None, limit: int = 50) -> List[Dict]:
        params = {"limit": limit}
        if province:
            params["province"] = province
        data = self.get("restaurants", params)
        return data.get("data", [])


class DASTAFetcher(BaseFetcher):
    """
    Fetcher for CBT Thailand by DASTA (Community Based Tourism)
    Base: https://cbtthailand.dasta.or.th/webapi/webserviceapi
    """
    BASE_URL = "https://cbtthailand.dasta.or.th/webapi"

    @property
    def source_name(self) -> str:
        return "dasta"

    def _get_api_key(self) -> str:
        return self.config.get("api_keys", {}).get("dasta_api_key", "")

    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        api_key = self._get_api_key()
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        req_params = dict(params)
        if api_key:
            req_params["api-key"] = api_key
        resp = requests.get(url, params=req_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_communities(self, province: str = None) -> List[Dict]:
        params = {}
        if province:
            params["province"] = province
        data = self.get("community", params)
        return data.get("data", data.get("result", []))

    def get_attractions(self, province: str = None) -> List[Dict]:
        params = {}
        if province:
            params["province"] = province
        data = self.get("attractions", params)
        return data.get("data", data.get("result", []))

    def get_events(self, province: str = None, start_date: str = None, end_date: str = None) -> List[Dict]:
        params = {}
        if province:
            params["province"] = province
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        data = self.get("events", params)
        return data.get("data", data.get("result", []))

    def get_accommodations(self, province: str = None) -> List[Dict]:
        params = {}
        if province:
            params["province"] = province
        data = self.get("accommodations", params)
        return data.get("data", data.get("result", []))

    def get_tour_routes(self, province: str = None) -> List[Dict]:
        params = {}
        if province:
            params["province"] = province
        data = self.get("tour-routes", params)
        return data.get("data", data.get("result", []))
