import requests
import logging
from typing import Dict, List, Any
from fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)


class DataGoThFetcher(BaseFetcher):
    """
    Fetcher for data.go.th Open Government Data CKAN API
    Base: https://opend.data.go.th/get-ckan/
    """
    BASE_URL = "https://opend.data.go.th/get-ckan"

    @property
    def source_name(self) -> str:
        return "data.go.th"

    def _get_api_key(self) -> str:
        return self.config.get("api_keys", {}).get("data_go_th", "")

    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("data.go.th API key not configured. Set api_keys.data_go_th in config.yaml")

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        req_params = dict(params)
        req_params["api-key"] = api_key

        resp = requests.get(url, params=req_params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_datasets(self, query: str = "ท่องเที่ยว", rows: int = 50) -> List[Dict]:
        data = self.get("package_search", {
            "q": query,
            "rows": rows
        })
        return data.get("result", {}).get("results", [])

    def get_dataset(self, dataset_id: str) -> Dict:
        return self.get("package_show", {"id": dataset_id})

    def get_resource_data(self, resource_id: str, limit: int = 100) -> Dict:
        return self.get("datastore_search", {
            "resource_id": resource_id,
            "limit": limit
        })

    def get_procurement(self, year: int = 2568, keyword: str = None, limit: int = 20) -> Dict:
        params = {"year": year, "limit": limit}
        if keyword:
            params["keyword"] = keyword
        return self.get("govspending/cgdcontract", params)

    def search_by_category(self, category: str = "ท่องเที่ยว", rows: int = 50) -> List[Dict]:
        return self.search_datasets(query=f"groups:{category}", rows=rows)

    def get_tourism_datasets(self, rows: int = 100) -> List[Dict]:
        return self.search_datasets(query="ท่องเที่ยว", rows=rows)

    def get_tambon(self, province: str) -> List[Dict]:
        """Get tambon (sub-district) data for a province"""
        data = self.get("map/tambon", {"CHANGWAT_T": f"จ.{province}"})
        return data.get("result", [])

    def search_cocktail(self, query: str, resource_id: str = None, limit: int = 100) -> Dict:
        params = {"q": query, "limit": limit}
        if resource_id:
            params["resource_id"] = resource_id
        return self.get("datastore_search_sql", params)
