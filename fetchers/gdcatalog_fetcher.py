import csv, io, json, logging, re, time
from typing import Dict, List, Optional
from urllib.parse import quote
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from database.cache_manager import CacheManager
from database.schema import get_connection

try:
    import chardet
    HAVE_CHARDET = True
except ImportError:
    HAVE_CHARDET = False

logger = logging.getLogger(__name__)

CKAN_BASE = "https://gdcatalog.go.th/api/3/action"

TOURISM_KEYWORDS = [
    "ท่องเที่ยว", "tourism", "นักท่องเที่ยว", "tourist",
    "แหล่งท่องเที่ยว", "attraction", "ที่พัก", "accommodation",
    "โรงแรม", "hotel", "ร้านอาหาร", "restaurant",
    "วัฒนธรรม", "culture", "โบราณสถาน", "ancient",
    "วัด", "temple", "รายได้", "revenue",
    "การเดินทาง", "travel", "SME",
]

CATEGORY_MAP = [
    (["นักท่องเที่ยว", "tourist", "ผู้เยี่ยมเยือน", "visitor"], "tourist_count"),
    (["รายได้", "revenue", "income", "ค่าใช้จ่าย"], "revenue"),
    (["ที่พัก", "accommodation", "โรงแรม", "hotel", " occupancy"], "accommodation"),
    (["แหล่งท่องเที่ยว", "attraction"], "attraction"),
    (["วัฒนธรรม", "culture", "ประเพณี", "tradition"], "culture"),
    (["ร้านอาหาร", "restaurant", "อาหาร", "food"], "restaurant"),
    (["SME", "ผู้ประกอบการ"], "business"),
    (["โบราณสถาน", "ancient", "มรดก", "heritage"], "heritage"),
    (["วัด", "temple", "ศาสนา", "religion"], "temple"),
    (["การเดินทาง", "travel", "คมนาคม", "transport"], "transport"),
]


class GDCatalogFetcher:
    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "TourismAnalytics/1.0",
            "Accept": "application/json,text/csv",
        })

    def search_datasets(self, query: str, rows: int = 100) -> List[Dict]:
        url = f"{CKAN_BASE}/package_search"
        params = {"q": query, "rows": rows, "sort": "metadata_modified desc"}
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data["result"]["results"]
        return []

    def _classify_dataset(self, dataset: Dict) -> str:
        title = (dataset.get("title") or "").lower()
        notes = (dataset.get("notes") or "").lower()
        tags = [t["name"].lower() for t in dataset.get("tags", [])]
        groups = [g["display_name"] for g in dataset.get("groups", [])]
        text = f"{title} {notes} {' '.join(tags)} {' '.join(groups)}"

        for keywords, category in CATEGORY_MAP:
            if any(kw in text for kw in keywords):
                return category
        return "other"

    def fetch_all_tourism(self, max_datasets: int = 300) -> Dict[str, int]:
        seen_ids = set()
        collected = {}
        conn = get_connection()
        try:
            for keyword in TOURISM_KEYWORDS[:10]:
                try:
                    datasets = self.search_datasets(keyword, rows=100)
                except Exception as e:
                    logger.warning(f"Search failed for '{keyword}': {e}")
                    continue
                for ds in datasets:
                    ds_id = ds.get("id")
                    if ds_id in seen_ids:
                        continue
                    seen_ids.add(ds_id)
                    if len(collected) >= max_datasets:
                        break
                    cat = self._classify_dataset(ds)
                    resources = ds.get("resources", [])
                    csv_resources = [r for r in resources if r.get("format", "").upper() in ("CSV", "JSON")]
                    if not csv_resources:
                        continue
                    collected[ds_id] = {
                        "id": ds_id,
                        "name": ds.get("name"),
                        "title": ds.get("title"),
                        "notes": ds.get("notes"),
                        "category": cat,
                        "organization": ds.get("organization", {}).get("title", ""),
                        "resources": [
                            {
                                "url": r.get("url"),
                                "format": r.get("format"),
                                "name": r.get("name"),
                                "description": r.get("description"),
                                "size": r.get("size"),
                            }
                            for r in csv_resources[:2]
                        ],
                    }
                if len(collected) >= max_datasets:
                    break

            count_by_category = {}
            for ds_id, info in collected.items():
                cat = info["category"]
                self._store_dataset_metadata(conn, info)
                count_by_category[cat] = count_by_category.get(cat, 0) + 1
                for res in info["resources"]:
                    try:
                        rows_stored = self._download_and_store(conn, info, res)
                        if rows_stored:
                            logger.info(f"  Stored {rows_stored} rows from {res.get('name', '?')}")
                    except Exception as e:
                        logger.warning(f"  Failed to download {res.get('url', '?')}: {e}")

            conn.commit()
            logger.info(f"GD Catalog fetch complete. Categories: {count_by_category}")
            return count_by_category
        finally:
            conn.close()

    def _store_dataset_metadata(self, conn, info: Dict):
        conn.execute("""
            INSERT OR REPLACE INTO gdcatalog_datasets
            (dataset_id, name, title, notes, category, organization, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            info["id"], info["name"], info["title"],
            info["notes"], info["category"], info["organization"],
        ))

    def _is_direct_download(self, url: str) -> bool:
        return "/resource/" in url or "/download/" in url or "catalogapi.nso.go.th" in url or url.endswith(".csv") or url.endswith(".json")

    def _download_and_store(self, conn, dataset: Dict, resource: Dict) -> int:
        url = resource["url"]
        if not url:
            return 0

        if not self._is_direct_download(url):
            logger.debug(f"  Skip (not direct download): {url[:80]}")
            return 0

        fmt = resource.get("format", "").upper()
        if fmt == "CSV":
            return self._download_csv(conn, dataset, resource, url)
        elif fmt in ("JSON",):
            return self._download_json(conn, dataset, resource, url)
        return 0

    def _decode_csv(self, raw: bytes) -> str:
        if HAVE_CHARDET:
            result = chardet.detect(raw)
            enc = result.get("encoding", "utf-8") or "utf-8"
            try:
                return raw.decode(enc, errors="replace")
            except (UnicodeDecodeError, UnicodeError):
                pass
        for enc in ("utf-8-sig", "cp874", "windows-874", "tis-620", "utf-8", "latin-1"):
            try:
                return raw.decode(enc, errors="strict")
            except (UnicodeDecodeError, UnicodeError):
                continue
        return raw.decode("utf-8", errors="replace")

    def _download_csv(self, conn, dataset: Dict, resource: Dict, url: str) -> int:
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        content = resp.content
        if not content:
            return 0

        decoded = self._decode_csv(content)
        reader = csv.DictReader(io.StringIO(decoded))
        rows = list(reader)
        if not rows:
            return 0
        if not isinstance(rows[0], dict):
            return 0

        columns = list(rows[0].keys())
        ds_id = dataset["id"]
        res_id = resource.get("url", url)[-40:]
        cat = dataset["category"]

        stored = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not row or not any(v.strip() for v in row.values() if v):
                continue
            row_json = json.dumps(row, ensure_ascii=False)
            try:
                prov = self._extract_province(row, dataset)
                cols_json = json.dumps(columns, ensure_ascii=False)
                conn.execute("""
                    INSERT OR IGNORE INTO gdcatalog_data
                    (dataset_id, resource_id, category, province, columns, row_data, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (ds_id, res_id, cat, prov, cols_json, row_json))
                stored += 1
            except Exception as e:
                logger.warning(f"CSV row error: {type(row).__name__} {e}")
        return stored

    def _download_json(self, conn, dataset: Dict, resource: Dict, url: str) -> int:
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("result", data.get("data", data.get("rows", [data])))
        else:
            return 0
        if not isinstance(rows, list):
            rows = [rows]

        ds_id = dataset["id"]
        res_id = resource.get("url", url)[-40:]
        cat = dataset["category"]
        stored = 0

        columns = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not columns and row:
                columns = list(row.keys())
            row_json = json.dumps(row, ensure_ascii=False)
            try:
                prov = self._extract_province(row, dataset)
                cols_json = json.dumps(columns, ensure_ascii=False)
                conn.execute("""
                    INSERT OR IGNORE INTO gdcatalog_data
                    (dataset_id, resource_id, category, province, columns, row_data, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (ds_id, res_id, cat, prov, cols_json, row_json))
                stored += 1
            except Exception as e:
                logger.warning(f"JSON row error: {type(row).__name__} {e}")
        return stored

    def _download_excel(self, conn, dataset: Dict, resource: Dict, url: str) -> int:
        try:
            import openpyxl
        except ImportError:
            logger.warning("openpyxl not installed, skipping Excel file")
            return 0
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        wb = openpyxl.load_workbook(io.BytesIO(resp.content), read_only=True)
        ws = wb.active
        if not ws:
            return 0

        rows_iter = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(rows_iter, [])]
        ds_id = dataset["id"]
        res_id = resource.get("url", url)[-40:]
        cat = dataset["category"]
        stored = 0

        for row_values in rows_iter:
            row = {}
            for i, val in enumerate(row_values):
                if i < len(header):
                    row[header[i]] = str(val) if val is not None else ""
            if not row:
                continue
            row_json = json.dumps(row, ensure_ascii=False)
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO gdcatalog_data
                    (dataset_id, resource_id, category, province, columns, row_data, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    ds_id, res_id, cat,
                    self._extract_province(row, dataset),
                    json.dumps(header, ensure_ascii=False),
                    row_json,
                ))
                stored += 1
            except Exception as e:
                logger.warning(f"Row insert error: {e}")
        return stored

    PROVINCE_PATTERNS = [
        "จังหวัด", "province", "จ. ", "ภาค", "region",
        "อำเภอ", "district", "อ. ",
    ]

    @classmethod
    def _extract_province(cls, row, dataset: Dict) -> str:
        if not isinstance(row, dict):
            return ""
        org_raw = dataset.get("organization", "")
        if isinstance(org_raw, dict):
            org_title = org_raw.get("title", "")
        else:
            org_title = str(org_raw) if org_raw else ""
        if org_title and "จังหวัด" in org_title:
            return org_title.replace("จังหวัด", "").strip()

        row_lower = {k.lower(): v for k, v in row.items() if isinstance(v, str)}
        for key in ["จังหวัด", "province", "jhangwat", "region"]:
            val = row_lower.get(key, "")
            if val and val.strip():
                return val.strip()
        for key in ["province_th", "province_name", "area", "area_name"]:
            val = row_lower.get(key, "")
            if val and val.strip():
                return val.strip()

        title = (dataset.get("title") or "")
        for p in ["กรุงเทพ", "เชียงใหม่", "ภูเก็ต", "ชลบุรี", "กระบี่", "ประจวบคีรีขันธ์",
                   "เชียงราย", "อยุธยา", "พังงา", "นครศรีธรรมราช", "สงขลา", "สุราษฎร์",
                   "ขอนแก่น", "นครราชสีมา", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ"]:
            if p in title:
                return p
        return ""

    def get_summary_stats(self) -> Dict:
        conn = get_connection()
        try:
            cur = conn.execute("""
                SELECT category, COUNT(DISTINCT dataset_id) as datasets,
                       COUNT(*) as rows
                FROM gdcatalog_data
                GROUP BY category
                ORDER BY rows DESC
            """)
            categories = {}
            for row in cur.fetchall():
                categories[row["category"]] = {
                    "datasets": row["datasets"],
                    "rows": row["rows"],
                }
            cur2 = conn.execute("SELECT COUNT(DISTINCT dataset_id) as total FROM gdcatalog_datasets")
            total_datasets = cur2.fetchone()["total"]
            cur3 = conn.execute("SELECT COUNT(*) as total FROM gdcatalog_data")
            total_rows = cur3.fetchone()["total"]
            return {
                "total_datasets": total_datasets,
                "total_rows": total_rows,
                "categories": categories,
            }
        finally:
            conn.close()

    def get_province_data(self, province: str) -> List[Dict]:
        conn = get_connection()
        try:
            cur = conn.execute("""
                SELECT d.id, d.dataset_id, d.category, d.columns, d.row_data,
                       ds.title as dataset_title, ds.organization
                FROM gdcatalog_data d
                JOIN gdcatalog_datasets ds ON d.dataset_id = ds.dataset_id
                WHERE d.province LIKE ? OR d.province = ''
                ORDER BY d.category, d.id
                LIMIT 500
            """, (f"%{province}%",))
            results = []
            for row in cur.fetchall():
                try:
                    row_data = json.loads(row["row_data"])
                except (json.JSONDecodeError, TypeError):
                    row_data = {}
                results.append({
                    "id": row["id"],
                    "dataset_id": row["dataset_id"],
                    "category": row["category"],
                    "dataset_title": row["dataset_title"],
                    "organization": row["organization"],
                    "columns": json.loads(row["columns"]) if row["columns"] else [],
                    "data": row_data,
                })
            return results
        finally:
            conn.close()

    def get_tourist_stats(self, province: str) -> Dict:
        conn = get_connection()
        try:
            results = {}
            for cat in ("tourist_count", "revenue", "accommodation"):
                cur = conn.execute("""
                    SELECT row_data FROM gdcatalog_data
                    WHERE category = ? AND province LIKE ?
                    ORDER BY id DESC LIMIT 20
                """, (cat, f"%{province}%"))
                rows_data = []
                for row in cur.fetchall():
                    try:
                        rows_data.append(json.loads(row["row_data"]))
                    except (json.JSONDecodeError, TypeError):
                        pass
                if rows_data:
                    results[cat] = rows_data
            return results
        finally:
            conn.close()
