import requests
import logging
from typing import Dict, List, Any
from fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)


class MOTSFetcher(BaseFetcher):
    """
    Fetcher for กระทรวงการท่องเที่ยวและกีฬา (MOTS) CKAN API
    Base: https://ckan.mots.go.th/api/3/action/
    """
    BASE_URL = "https://ckan.mots.go.th/api/3/action"

    @property
    def source_name(self) -> str:
        return "mots"

    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        resp = requests.get(url, params=params, timeout=30)
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

    def get_resources(self, dataset_id: str) -> List[Dict]:
        dataset = self.get_dataset(dataset_id)
        return dataset.get("result", {}).get("resources", [])

    def get_resource_data(self, resource_id: str, limit: int = 100) -> Dict:
        return self.get("datastore_search", {
            "resource_id": resource_id,
            "limit": limit
        })

    def search_tourism_by_province(self, province: str) -> List[Dict]:
        """Search MOTS datasets for a specific province"""
        results = []
        datasets = self.search_datasets(query=province, rows=30)
        for ds in datasets:
            resources = ds.get("resources", [])
            for res in resources:
                res_id = res.get("id")
                if res_id:
                    try:
                        data = self.get_resource_data(res_id, limit=200)
                        records = data.get("result", {}).get("records", [])
                        results.extend(records)
                    except Exception as e:
                        logger.warning(f"Error fetching resource {res_id}: {e}")
        return results

    def list_organizations(self) -> List[Dict]:
        data = self.get("organization_list")
        org_list = data.get("result", [])
        result = []
        for org_id in org_list:
            org_data = self.get("organization_show", {"id": org_id})
            result.append(org_data.get("result", {}))
        return result

    def list_groups(self) -> List[Dict]:
        data = self.get("group_list")
        groups = data.get("result", [])
        result = []
        for g in groups:
            group_data = self.get("group_show", {"id": g})
            result.append(group_data.get("result", {}))
        return result

    def tag_search(self, tag: str) -> List[Dict]:
        data = self.get("tag_search", {"query": tag})
        return data.get("result", {}).get("results", [])
