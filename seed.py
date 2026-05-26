"""
Seed script: Populate tourism_data with realistic Thai tourism data
This demonstrates the full system capabilities (clusters, gaps, maps, charts)
Replace with real API data when API keys are available.
"""
import sys, os, json, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database.cache_manager import CacheManager
from database.schema import init_db, get_connection

PROVINCES = {
    "เชียงใหม่": {"center": [18.7883, 98.9853], "scale": 0.25},
    "ภูเก็ต":   {"center": [7.8804, 98.3923], "scale": 0.08},
    "ชลบุรี":   {"center": [13.3611, 100.9847], "scale": 0.12},
    "กระบี่":   {"center": [8.0863, 98.9063], "scale": 0.10},
    "สุราษฎร์ธานี": {"center": [9.1382, 99.3211], "scale": 0.15},
    "ประจวบคีรีขันธ์": {"center": [11.8122, 99.7940], "scale": 0.12},
    "พังงา":   {"center": [8.4409, 98.5182], "scale": 0.10},
    "อยุธยา":  {"center": [14.3532, 100.5786], "scale": 0.08},
    "เชียงราย": {"center": [19.9074, 99.8302], "scale": 0.15},
    "กรุงเทพมหานคร": {"center": [13.7563, 100.5018], "scale": 0.12},
}

NAMES_TH = {
    "accommodation": [
        "โรงแรม{name}", "รีสอร์ท{name}", "เกสต์เฮาส์{name}", "โฮสเทล{name}",
        "วิลล่า{name}", "บีชเฮ้าส์{name}", "บูติคโฮเทล{name}", "แมนชั่น{name}",
        "เซอร์วิสอพาร์ทเม้นท์{name}", "บังกะโล{name}"
    ],
    "attraction": [
        "วัด{name}", "น้ำตก{name}", "หาด{name}", "อุทยาน{name}",
        "พิพิธภัณฑ์{name}", "ตลาด{name}", "ถ้ำ{name}", " viewpoints {name}",
        "ศูนย์วัฒนธรรม{name}", "สวน{name}"
    ],
    "restaurant": [
        "ร้านอาหาร{name}", "คาเฟ่{name}", "ครัว{name}", "สเต็ก{name}",
        "ซีฟู้ด{name}", "ข้าวต้ม{name}", "ก๋วยเตี๋ยว{name}", "บุฟเฟ่ต์{name}",
        "อาหารตามสั่ง{name}", "เบเกอรี่{name}"
    ],
    "event": [
        "งานเทศกาล{name}", "คอนเสิร์ต{name}", "งานประเพณี{name}",
        "เทศกาลอาหาร{name}", "งานแสดงสินค้า{name}", "มหกรรม{name}"
    ],
    "transport": [
        "สถานีขนส่ง{name}", "ท่าเรือ{name}", "สถานีรถไฟ{name}",
        "สนามบิน{name}", "ป้ายรถเมล์{name}", "ที่จอดรถ{name}"
    ]
}

SUFFIXES = ["สยาม", "ล้านนา", "บุรี", "นคร", "ธานี", "ราษฎร์", "ทอง", "ใต้", "เหนือ", "ตะวันออก",
            "ตะวันตก", "ใหม่", "เก่า", "กลาง", "ใน", "นอก", "น้อย", "ใหญ่", "สวน", "บีช",
            "ฮิลล์", "วิลเลจ", "พาเลซ", "การ์เด้น", "เลค", "ริเวอร์", "วิว", "เพลส", "เฮ้าส์"]

TAGS = {
    "accommodation": ["โรงแรม", "ที่พัก", "รีสอร์ท", "วิลล่า", "บูติค"],
    "attraction": ["วัด", "ธรรมชาติ", "น้ำตก", "ชายหาด", "วัฒนธรรม", "ประวัติศาสตร์"],
    "restaurant": ["อาหาร", "คาเฟ่", "ซีฟู้ด", "อาหารเหนือ", "อาหารใต้"],
    "event": ["เทศกาล", "ประเพณี", "ดนตรี", "อาหาร", "วัฒนธรรม"],
    "transport": ["ขนส่ง", "รถโดยสาร", "เรือ", "รถไฟ", "สนามบิน"]
}

def random_point(center, scale):
    lat = center[0] + random.uniform(-scale, scale)
    lng = center[1] + random.uniform(-scale, scale)
    return round(lat, 6), round(lng, 6)

def random_phone():
    return f"08{random.randint(1,9)}{random.randint(10000000,99999999)}"

def seed_data(cache: CacheManager, count_per_category: int = 30):
    total = 0
    for province, info in PROVINCES.items():
        for category, templates in NAMES_TH.items():
            for i in range(count_per_category):
                suffix = random.choice(SUFFIXES)
                template = random.choice(templates)
                name = template.format(name=suffix)

                lat, lng = random_point(info["center"], info["scale"])
                # Generate a second word for accommodation names
                if category == "accommodation":
                    second_words = ["พูลวิลล่า", "สปา", "แกรนด์", "รอยัล", "เพชร",
                                    "ทอง", "เงิน", "บุษบา", "ชบา", "หยก",
                                    "มุก", "ไพลิน", "มรกต", "สโนว์", "ซัน"]
                    name = template.format(name=" ") + random.choice(second_words)
                elif category == "restaurant":
                    food_words = ["ทะเล", "บ้านสวน", "ป่าก็อบ", "เรือนไม้", "สวนอาหาร",
                                  "ริมน้ำ", "ข้าวหอม", "ครัวคุณ", "แม่", "น้ำ"]
                    name = template.format(name=" ") + random.choice(food_words)

                tags = random.sample(TAGS.get(category, []), min(3, len(TAGS.get(category, []))))

                record = {
                    "category": category,
                    "source": "seed_data",
                    "province": province,
                    "district": "",
                    "name_th": name,
                    "name_en": name,
                    "latitude": lat,
                    "longitude": lng,
                    "address": f"{province} ประเทศไทย",
                    "phone": random_phone(),
                    "website": "",
                    "tags": tags,
                    "details": {"seed": True}
                }
                if cache.store_tourism_record(record):
                    total += 1
        print(f"  {province}: seeded")
    print(f"\n✅ Total seeded: {total} records across {len(PROVINCES)} provinces")
    return total

if __name__ == "__main__":
    config_path = "config/config.yaml"
    import yaml
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except:
        config = {"database": {"path": "data/tourism_cache.db", "cache_ttl_hours": 24}}

    db_path = config.get("database", {}).get("path", "data/tourism_cache.db")
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    cache = CacheManager(config.get("database", {}).get("cache_ttl_hours", 24))
    seed_data(cache, count_per_category=40)
