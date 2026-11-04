# FILE: weather.py
# Gets current weather using Open-Meteo (free, no API key needed).
import httpx
from config import DEFAULT_CITY

WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    80: "light showers", 81: "showers", 82: "heavy showers", 95: "thunderstorm",
}

def get_weather(params: dict) -> str:
    city = (params.get("city") or DEFAULT_CITY).strip()
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}, timeout=10
        ).json()
        if not geo.get("results"):
            return f"I was unable to locate weather data for {city}, boss."
        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name", city)

        weather = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto"
            }, timeout=10
        ).json()
        cur = weather["current"]
        temp = cur["temperature_2m"]
        humidity = cur["relative_humidity_2m"]
        wind = cur["wind_speed_10m"]
        code = cur["weather_code"]
        desc = WMO_CODES.get(code, "unknown conditions")
        return f"Currently {temp}°C with {desc} in {name}, boss. Humidity is {humidity}%, wind speed {wind} km/h."
    except Exception as e:
        print(f"[Weather] Error: {e}")
        return "An error occurred, boss."
