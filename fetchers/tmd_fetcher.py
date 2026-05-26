import requests
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Optional
from fetchers.base_fetcher import BaseFetcher

logger = logging.getLogger(__name__)


class TMDFetcher(BaseFetcher):
    BASE_URL = "https://data.tmd.go.th/api/WeatherForecast7Days/v2/"

    # Province name mapping: our names -> TMD API names
    PROVINCE_MAP = {
        "อยุธยา": "พระนครศรีอยุธยา",
    }

    def __init__(self, cache, config):
        super().__init__(cache, config)
        self.api_uid = "api"
        self.api_ukey = "api12345"

    @property
    def source_name(self) -> str:
        return "tmd"

    def fetch_raw(self, endpoint: str, params: dict) -> Dict:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        resp = requests.get(url, params={**params, "uid": self.api_uid, "ukey": self.api_ukey}, timeout=30)
        resp.raise_for_status()
        return self._parse_xml(resp.text)

    NUMERIC_FIELDS = {"MaximumTemperature", "MinimumTemperature", "PercentRainCover", "WindSpeed", "WaveHeight", "Pressure", "Humidity"}

    def _parse_xml(self, xml_text: str) -> Dict:
        root = ET.fromstring(xml_text)
        result = {"provinces": []}
        for province_elem in root.findall(".//Province"):
            p = {
                "name_th": self._get_text(province_elem, "ProvinceNameThai"),
                "name_en": self._get_text(province_elem, "ProvinceNameEnglish"),
                "forecasts": []
            }
            sf = province_elem.find("SevenDaysForecast")
            if sf is not None:
                children = list(sf)
                # Group children by ForecastDate as record boundary
                record = {}
                for child in children:
                    tag = child.tag
                    val = child.text.strip() if child.text else ""
                    if tag == "ForecastDate" and record:
                        # save previous record and start new one
                        p["forecasts"].append(self._make_forecast(record))
                        record = {}
                    if tag in self.NUMERIC_FIELDS:
                        try:
                            record[tag] = float(val)
                        except (ValueError, TypeError):
                            record[tag] = None
                    else:
                        record[tag] = val
                if record:
                    p["forecasts"].append(self._make_forecast(record))
            result["provinces"].append(p)
        return result

    def _make_forecast(self, record: dict) -> dict:
        return {
            "date": record.get("ForecastDate", ""),
            "max_temp": record.get("MaximumTemperature"),
            "min_temp": record.get("MinimumTemperature"),
            "wind_direction": record.get("WindDirection", ""),
            "wind_speed": record.get("WindSpeed"),
            "rain_cover": record.get("PercentRainCover"),
            "weather_desc_th": record.get("DescriptionThai", ""),
            "weather_desc_en": record.get("DescriptionEnglish", ""),
            "temp_label_th": record.get("TemperatureThai", ""),
            "temp_label_en": record.get("TemperatureEnglish", ""),
            "wave_height_th": record.get("WaveHeightThai", ""),
            "wave_height_en": record.get("WaveHeightThaiEnglish", ""),
            "pressure": record.get("Pressure"),
            "humidity": record.get("Humidity"),
        }

    def _get_text(self, parent, tag: str) -> str:
        el = parent.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    def get_all_weather(self, force_refresh: bool = False) -> Dict:
        return self.get("", {}, force_refresh=force_refresh)

    def get_province_weather(self, province_name: str) -> Optional[Dict]:
        data = self.get_all_weather()
        lookup = self.PROVINCE_MAP.get(province_name.strip(), province_name.strip())
        for p in data.get("provinces", []):
            if p["name_th"].strip() == lookup:
                return p
        # fallback: partial match
        for p in data.get("provinces", []):
            if lookup in p["name_th"] or p["name_th"] in lookup:
                return p
        return None
