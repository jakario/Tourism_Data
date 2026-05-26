import argparse
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
from database.cache_manager import CacheManager
from database.schema import init_db
from fetchers.mots_fetcher import MOTSFetcher
from fetchers.tat_fetcher import TATFetcher, DASTAFetcher
from analytics.location_insights import LocationInsights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cli")


def load_config(path: str = "config/config.yaml") -> dict:
    default_cfg = {
        "database": {"path": "data/tourism_cache.db", "cache_ttl_hours": 24},
        "api_keys": {"data_go_th": "", "tat_api_key": "", "dasta_api_key": ""},
        "rate_limits": {"max_calls_per_day": 800, "min_interval_seconds": 2},
        "cache_strategy": {"mode": "cache_first", "stale_while_revalidate": True},
        "target_provinces": ["เชียงใหม่", "ภูเก็ต", "ชลบุรี"]
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            for k, v in loaded.items():
                if isinstance(v, dict) and k in default_cfg:
                    default_cfg[k].update(v)
                else:
                    default_cfg[k] = v
    except FileNotFoundError:
        logger.warning(f"Config not found at {path}, using defaults")
    return default_cfg


def cmd_fetch(args, config):
    db_path = config["database"]["path"]
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    cache = CacheManager(config["database"]["cache_ttl_hours"])

    mots = MOTSFetcher(cache, config)
    province = args.province or config.get("target_provinces", [None])[0]

    if args.source in ("mots", "all"):
        logger.info(f"=== Fetching MOTS data for {province or 'all'} ===")
        try:
            datasets = mots.search_tourism_by_province(province) if province else mots.search_datasets(rows=20)
            print(json.dumps(datasets, ensure_ascii=False, indent=2)[:2000])
            logger.info(f"Fetched {len(datasets)} records from MOTS")
        except Exception as e:
            logger.error(f"MOTS fetch failed: {e}")

    if args.source in ("tat", "all"):
        logger.info("=== TAT API (requires API key) ===")
        if config.get("api_keys", {}).get("tat_api_key"):
            tat = TATFetcher(cache, config)
            try:
                att = tat.get_attractions(province if province else None, limit=10)
                print(json.dumps(att, ensure_ascii=False, indent=2)[:2000])
            except Exception as e:
                logger.error(f"TAT fetch failed: {e}")
        else:
            logger.warning("TAT API key not found, skipping")

    if args.source in ("dasta", "all"):
        logger.info("=== DASTA CBT API (requires API key) ===")
        if config.get("api_keys", {}).get("dasta_api_key"):
            dasta = DASTAFetcher(cache, config)
            try:
                comm = dasta.search_communities(province if province else None)
                print(json.dumps(comm, ensure_ascii=False, indent=2)[:2000])
            except Exception as e:
                logger.error(f"DASTA fetch failed: {e}")
        else:
            logger.warning("DASTA API key not found, skipping")


def cmd_insights(args, config):
    cache = CacheManager(config["database"]["cache_ttl_hours"])
    insights = LocationInsights(cache)

    province = args.province
    if not province:
        logger.error("--province is required for insights")
        return

    if args.type == "summary":
        result = insights.get_province_summary(province)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.type == "clusters":
        clusters = insights.find_density_clusters(province, args.category, args.grid)
        print(f"\n=== Density Clusters for {province} ===")
        if not clusters:
            print("No clusters found (insufficient location data)")
            return
        print(f"Found {len(clusters)} clusters\n")
        for i, c in enumerate(clusters[:10]):
            print(f"  Cluster {i+1}: {c['count']} spots @ ({c['center_lat']:.4f}, {c['center_lng']:.4f})")

    elif args.type == "gaps":
        result = insights.find_gaps(province)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.type == "nearby":
        result = insights.nearby_places(args.lat, args.lng, args.radius, args.category)
        print(f"\n=== Nearby places within {args.radius}km ===")
        for r in result:
            print(f"  [{r.get('category')}] {r.get('name_th', '?')} ({r.get('distance_km', '?')} km)")


def cmd_stats(args, config):
    from analytics.tourism_stats import TourismStats
    cache = CacheManager(config["database"]["cache_ttl_hours"])
    stats = TourismStats(cache)

    if args.action == "cache":
        print(json.dumps(cache.get_cache_stats(), ensure_ascii=False, indent=2))

    elif args.action == "search":
        records = cache.search_tourism(
            province=args.province,
            category=args.category,
            keyword=args.keyword,
            limit=args.limit
        )
        print(f"\n=== Found {len(records)} records ===")
        for r in records[:20]:
            print(f"  [{r['category']}] {r.get('name_th', '?')} - {r.get('province', '?')}")

    elif args.action == "cleanup":
        n = cache.cleanup_expired()
        print(f"Cleaned up {n} expired cache entries")


def cmd_fetch_provinces(args, config):
    """Pre-fetch tourism data for all target provinces into the database"""
    cache = CacheManager(config["database"]["cache_ttl_hours"])
    mots = MOTSFetcher(cache, config)
    provinces = args.provinces or config.get("target_provinces", [])

    total_new = 0
    for p in provinces:
        logger.info(f"Fetching data for {p}...")
        try:
            records = mots.search_tourism_by_province(p)
            for rec in records:
                stored = cache.store_tourism_record({
                    "category": rec.get("category", rec.get("type", "unknown")),
                    "source": "mots",
                    "province": p,
                    "name_th": rec.get("name", rec.get("title", rec.get("name_th", "?"))),
                    "name_en": rec.get("name_en", ""),
                    "latitude": rec.get("latitude", rec.get("lat")),
                    "longitude": rec.get("longitude", rec.get("lng")),
                    "details": rec
                })
                if stored:
                    total_new += 1
            logger.info(f"  {p}: stored {total_new} records so far")
        except Exception as e:
            logger.error(f"  {p}: error - {e}")

    print(f"\nDone! Total new records stored: {total_new}")


def main():
    parser = argparse.ArgumentParser(
        description="Thailand Tourism Data Caching & Analytics System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่าง:
  # ดึงข้อมูลท่องเที่ยวจาก MOTS
  python cli.py fetch --source mots --province เชียงใหม่

  # หาความหนาแน่นของสถานที่ท่องเที่ยว (หา gold zone)
  python cli.py insights --type clusters --province ภูเก็ต --grid 2.0

  # หาโอกาสทางธุรกิจ (ขาดร้านอาหารในแหล่งท่องเที่ยว)
  python cli.py insights --type gaps --province กระบี่

  # ค้นหาสถานที่ใกล้พิกัด
  python cli.py insights --type nearby --lat 7.890 --lng 98.392 --radius 3

  # สถิติ cache
  python cli.py stats --action cache

  # เตรียมข้อมูลจังหวัดเป้าหมายทั้งหมด (fetch + store)
  python cli.py fetch-provinces --provinces เชียงใหม่ ภูเก็ต กระบี่
        """
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch raw data from APIs")
    p_fetch.add_argument("--source", default="mots", choices=["mots", "tat", "dasta", "all"])
    p_fetch.add_argument("--province", default=None)
    p_fetch.add_argument("--limit", type=int, default=50)
    p_fetch.set_defaults(func=cmd_fetch)

    # insights
    p_ins = sub.add_parser("insights", help="Location analytics & insights")
    p_ins.add_argument("--type", required=True, choices=["summary", "clusters", "gaps", "nearby"])
    p_ins.add_argument("--province", default=None)
    p_ins.add_argument("--category", default=None)
    p_ins.add_argument("--grid", type=float, default=5.0, help="Grid size in km for clustering")
    p_ins.add_argument("--lat", type=float, default=None)
    p_ins.add_argument("--lng", type=float, default=None)
    p_ins.add_argument("--radius", type=float, default=2.0)
    p_ins.set_defaults(func=cmd_insights)

    # stats
    p_stat = sub.add_parser("stats", help="Cache stats & database management")
    p_stat.add_argument("--action", default="cache", choices=["cache", "search", "cleanup"])
    p_stat.add_argument("--province", default=None)
    p_stat.add_argument("--category", default=None)
    p_stat.add_argument("--keyword", default=None)
    p_stat.add_argument("--limit", type=int, default=50)
    p_stat.set_defaults(func=cmd_stats)

    # fetch-provinces
    p_fp = sub.add_parser("fetch-provinces", help="Pre-fetch & cache data for target provinces")
    p_fp.add_argument("--provinces", nargs="*", default=None)
    p_fp.set_defaults(func=cmd_fetch_provinces)

    args = parser.parse_args()
    config = load_config()
    args.func(args, config)


if __name__ == "__main__":
    main()
