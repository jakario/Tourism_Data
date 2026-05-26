import sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml
from flask import Flask, render_template, jsonify, request
from database.cache_manager import CacheManager
from database.schema import init_db
from fetchers.mots_fetcher import MOTSFetcher
from fetchers.tmd_fetcher import TMDFetcher
from fetchers.osm_fetcher import OSMFetcher
from fetchers.gdcatalog_fetcher import GDCatalogFetcher
from analytics.location_insights import LocationInsights

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webapp")

app = Flask(__name__)

def load_config():
    path = "config/config.yaml"
    default = {
        "database": {"path": "data/tourism_cache.db", "cache_ttl_hours": 24},
        "api_keys": {"data_go_th": "", "tat_api_key": "", "dasta_api_key": ""},
        "rate_limits": {"max_calls_per_day": 800, "min_interval_seconds": 1},
        "target_provinces": ["เชียงใหม่", "ภูเก็ต", "ชลบุรี", "กระบี่", "ประจวบคีรีขันธ์", "เชียงราย", "อยุธยา", "พังงา"]
    }
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or {}
            for k, v in loaded.items():
                if isinstance(v, dict) and k in default:
                    default[k].update(v)
                else:
                    default[k] = v
    except FileNotFoundError:
        pass
    return default

config = load_config()
os.makedirs(os.path.dirname(config["database"]["path"]) or ".", exist_ok=True)
cache = CacheManager(config["database"]["cache_ttl_hours"])
mots = MOTSFetcher(cache, config)
tmd = TMDFetcher(cache, config)
osm = OSMFetcher(cache)
gdcat = GDCatalogFetcher(cache)
insights = LocationInsights(cache)

@app.route("/")
def index():
    return render_template("index.html", provinces=config["target_provinces"])

@app.route("/api/cache-stats")
def api_cache_stats():
    return jsonify(cache.get_cache_stats())

@app.route("/api/province-summary")
def api_province_summary():
    province = request.args.get("province", config["target_provinces"][0])
    result = insights.get_province_summary(province)
    return jsonify(result)

@app.route("/api/clusters")
def api_clusters():
    province = request.args.get("province", config["target_provinces"][0])
    grid = float(request.args.get("grid", 3.0))
    category = request.args.get("category")
    cls = insights.find_density_clusters(province, category, grid)
    return jsonify(cls)

@app.route("/api/gaps")
def api_gaps():
    province = request.args.get("province", config["target_provinces"][0])
    return jsonify(insights.find_gaps(province))

@app.route("/api/fetch-now")
def api_fetch_now():
    province = request.args.get("province", config["target_provinces"][0])
    try:
        records = mots.search_tourism_by_province(province)
        new_count = 0
        for rec in records:
            stored = cache.store_tourism_record({
                "category": rec.get("category", rec.get("type", "unknown")),
                "source": "mots",
                "province": province,
                "name_th": rec.get("name", rec.get("title", rec.get("name_th", "?"))),
                "name_en": rec.get("name_en", ""),
                "latitude": rec.get("latitude", rec.get("lat")),
                "longitude": rec.get("longitude", rec.get("lng")),
                "details": rec
            })
            if stored:
                new_count += 1
        return jsonify({"status": "ok", "province": province, "new_records": new_count})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/search")
def api_search():
    province = request.args.get("province")
    category = request.args.get("category")
    keyword = request.args.get("keyword")
    limit = int(request.args.get("limit", 100))
    records = cache.search_tourism(province, category, keyword, limit)
    # remove details field to reduce payload
    for r in records:
        r.pop("details", None)
    return jsonify(records)

@app.route("/api/nearby")
def api_nearby():
    lat = float(request.args.get("lat", 0))
    lng = float(request.args.get("lng", 0))
    radius = float(request.args.get("radius", 5))
    category = request.args.get("category")
    return jsonify(insights.nearby_places(lat, lng, radius, category, limit=30))

@app.route("/api/provinces")
def api_provinces():
    return jsonify(config["target_provinces"])

@app.route("/api/usage-today")
def api_usage_today():
    sources = ["mots", "data.go.th", "tat", "dasta"]
    result = {}
    for s in sources:
        result[s] = cache.get_todays_calls(s)
    return jsonify(result)

@app.route("/api/fetch-osm")
def api_fetch_osm():
    province = request.args.get("province", config["target_provinces"][0])
    category = request.args.get("category")
    try:
        result = osm.fetch_and_store(province, category)
        return jsonify({"status": "ok", "province": province, **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/gdcatalog/fetch")
def api_gdcatalog_fetch():
    try:
        result = gdcat.fetch_all_tourism()
        return jsonify({"status": "ok", "categories": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/gdcatalog/stats")
def api_gdcatalog_stats():
    return jsonify(gdcat.get_summary_stats())

@app.route("/api/gdcatalog/data")
def api_gdcatalog_data():
    province = request.args.get("province", "")
    return jsonify(gdcat.get_province_data(province))

@app.route("/api/gdcatalog/tourist-stats")
def api_gdcatalog_tourist_stats():
    province = request.args.get("province", "")
    return jsonify(gdcat.get_tourist_stats(province))

@app.route("/api/weather")
def api_weather():
    province = request.args.get("province", config["target_provinces"][0])
    try:
        weather = tmd.get_province_weather(province)
        if weather:
            today = weather["forecasts"][0] if weather["forecasts"] else {}
            return jsonify({
                "province": province,
                "current": today,
                "forecast": weather["forecasts"],
                "cached": True
            })
        return jsonify({"province": province, "current": {}, "forecast": [], "cached": False})
    except Exception as e:
        return jsonify({"province": province, "error": str(e), "current": {}, "forecast": [], "cached": False}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
