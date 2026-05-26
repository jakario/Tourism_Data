# Tourism Data Caching & Analytics System

ระบบดึงข้อมูลการท่องเที่ยวจาก API ภาครัฐไทย พร้อมระบบ Cache ใน SQLite เพื่อลดการใช้ API call และวิเคราะห์ Location Intelligence

## สถาปัตยกรรม

```
                                    ┌──────────────────┐
                                    │   API Sources     │
                                    │  ┌──────────────┐ │
                                    │  │   MOTS API   │ │
                                    │  │ (ckan.mots)  │ │
                                    │  ├──────────────┤ │
                                    │  │ data.go.th   │ │
                                    │  │ (DGA CKAN)   │ │
                                    │  ├──────────────┤ │
                                    │  │  TAT API     │ │
                                    │  │ (ททท.)       │ │
                                    │  ├──────────────┤ │
                                    │  │ DASTA CBT    │ │
                                    │  │ (ท่องเที่ยว   │ │
                                    │  │  ชุมชน)      │ │
                                    │  └──────────────┘ │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │   BaseFetcher     │
                                    │   (Cache Layer)   │
                                    │                   │
                                    │  ┌─ Cache HIT? ──┐│
                                    │  │ YES → return  ││
                                    │  │ NO  → API call││
                                    │  │     → store   ││
                                    │  │     → return  ││
                                    │  └───────────────┘│
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │   SQLite Cache    │
                                    │                   │
                                    │  api_cache        │
                                    │  tourism_data     │
                                    │  province_stats   │
                                    │  api_usage        │
                                    │  fetcher_metadata │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │   Analytics       │
                                    │                   │
                                    │  LocationInsights │
                                    │  TourismStats     │
                                    └────────┬─────────┘
                                             │
                                    ┌────────▼─────────┐
                                    │   CLI / API       │
                                    │                   │
                                    │  fetch           │
                                    │  insights         │
                                    │  stats            │
                                    │  fetch-provinces  │
                                    └───────────────────┘
```

## การทำงานของ Cache (ลด API Call)

```
Request 1: API Call → เก็บใน SQLite → return data
Request 2: Cache HIT → return data (ไม่มี API Call)
Request 3: Cache HIT → return data (ไม่มี API Call)
...
เมื่อ cache expire (24 ชม.): API Call → refresh → store → return
```

## การติดตั้ง

```bash
cd /mnt/d/myopencode/tourism-analytics
pip install -r requirements.txt
```

## การใช้งาน CLI

### 1. ดึงข้อมูลการท่องเที่ยวจาก MOTS

```bash
# ดึงข้อมูลท่องเที่ยวทั้งหมด
python cli.py fetch --source mots --limit 20

# ดึงข้อมูลเฉพาะจังหวัด
python cli.py fetch --source mots --province เชียงใหม่

# ดึงจากหลายแหล่งพร้อมกัน
python cli.py fetch --source all --province ภูเก็ต
```

### 2. วิเคราะห์ Location Insights

```bash
# สรุปข้อมูลจังหวัด
python cli.py insights --type summary --province ภูเก็ต

# หา gold zone (จุดที่มีสถานที่ท่องเที่ยวหนาแน่น)
python cli.py insights --type clusters --province เชียงใหม่ --grid 2.0

# หาโอกาสทางธุรกิจ (ขาดร้านอาหารในแหล่งท่องเที่ยว)
python cli.py insights --type gaps --province กระบี่

# หาสถานที่ใกล้พิกัด
python cli.py insights --type nearby --lat 7.890 --lng 98.392 --radius 3
```

### 3. จัดการ Cache

```bash
# ดูสถิติ cache
python cli.py stats --action cache

# ค้นหาข้อมูลใน cache
python cli.py stats --action search --province ภูเก็ต --category attraction

# ล้าง cache ที่หมดอายุ
python cli.py stats --action cleanup
```

### 4. Pre-fetch ข้อมูลจังหวัดเป้าหมาย

```bash
# เตรียมข้อมูลจังหวัดที่ต้องการวิเคราะห์
python cli.py fetch-provinces --provinces เชียงใหม่ ภูเก็ต กระบี่ ชลบุรี
```

## การตั้งค่า API Keys

แก้ไขไฟล์ `config/config.yaml`:

```yaml
api_keys:
  data_go_th: "YOUR_TOKEN"    # สมัครได้ที่ https://api.data.go.th
  tat_api_key: "YOUR_KEY"     # สมัครได้ที่ https://developers.tourismthailand.org
  dasta_api_key: "YOUR_KEY"   # สมัครได้ที่ https://cbtthailand.dasta.or.th
```

**หมายเหตุ:** MOTS API (ckan.mots.go.th) ไม่ต้องใช้ API key สามารถใช้งานได้ทันที

## ตัวอย่างผลลัพธ์ทางธุรกิจ

### หา Gold Zone สำหรับเปิดธุรกิจ

```bash
$ python cli.py insights --type clusters --province ภูเก็ต --grid 2.0
Found 12 clusters
Cluster 1: 8 spots @ (7.890, 98.392) - ย่านหาดป่าตอง
Cluster 2: 5 spots @ (7.850, 98.290) - ย่านกะรน
...
```

### หาโอกาสทางธุรกิจ

```bash
$ python cli.py insights --type gaps --province กระบี่
opportunity_notes:
  - มี accommodation (45) มากกว่า restaurant (8) ถึง 5.6 เท่า
    → โอกาสเปิดร้านอาหาร/คาเฟ่ในแหล่งที่พัก
```

### สถิติประหยัด API Call

```bash
$ python cli.py stats --action cache
{
  "cached_entries": 150,
  "cache_hits": 320,
  "today_api_calls": 2,
  "total_api_calls_overall": 150,
  "saved_calls_estimate": 170
}
```

## API Sources

| Source | URL | Auth | Data |
|--------|-----|------|------|
| MOTS | ckan.mots.go.th | None | สถิตินักท่องเที่ยว, ค่าใช้จ่าย, ข้อมูลพื้นฐาน |
| data.go.th | opend.data.go.th | Token | ท่องเที่ยว 2,858+ datasets |
| TAT | developers.tourismthailand.org | API Key | ที่พัก, แหล่งท่องเที่ยว, งานอีเวนท์ |
| DASTA | cbtthailand.dasta.or.th | API Key | ท่องเที่ยวชุมชน, เส้นทาง, เทศกาล |

## โครงสร้าง Database

```sql
-- ตารางหลัก: api_cache (เก็บ raw API response)
(source, endpoint, params_hash, response, expires_at, hit_count)

-- ตารางข้อมูลท่องเที่ยวปกติ
(category, province, name_th, lat, lng, address, tags)

-- ตารางสถิติรายจังหวัด
(province, year, month, tourists_thai, tourists_foreign, revenue)

-- ตารางติดตามการใช้งาน API
(date, source, calls)
```
