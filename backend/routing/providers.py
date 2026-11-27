"""Thin clients for the third-party APIs: geocoding, routing and weather."""
import hashlib
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import cumulative_m, haversine_m, interpolate_at

TIMEOUT = 25
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54
MAX_DETOUR_RATIO = 1.3
WEATHER_CHUNK = 80  # locations per Open-Meteo request
WEATHER_TTL_S = 30 * 60


class ProviderError(Exception):
    """A third-party API failed or returned nothing useful (maps to HTTP 502/400)."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _get(url, **kwargs):
    headers = {"User-Agent": settings.HTTP_USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise ProviderError(f"Upstream request failed: {exc.__class__.__name__}") from exc


# ----------------------------------------------------------------- geocoding
_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def geocode(query: str) -> dict:
    """Accepts a place name or a 'lat,lon' string. Returns {name, lat, lon}."""
    match = _LATLON.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        return {"name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}

    key = "geo:" + hashlib.md5(query.strip().lower().encode()).hexdigest()
    hit = cache.get(key)
    if hit:
        return hit
    data = _get(f"{settings.NOMINATIM_URL}/search", params={"q": query, "format": "json", "limit": 1})
    if not data:
        raise ProviderError(f'Could not find a place called "{query}".', status=400)
    place = {"name": data[0]["display_name"], "lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    cache.set(key, place, 24 * 3600)
    return place


# ------------------------------------------------------------------- routing
def _osrm(points, alternatives):
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    data = _get(
        f"{settings.OSRM_URL}/route/v1/driving/{coords}",
        params={
            "alternatives": "3" if alternatives else "false",
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",  # needed for the road-name summary
            "annotations": "duration,distance",
        },
    )
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ProviderError("No drivable route found between those places.", status=400)
    return data["routes"]


def _normalise(osrm_route) -> dict:
    """Flatten an OSRM route into geometry plus per-vertex cumulative distance/time."""
    coords = osrm_route["geometry"]["coordinates"]
    seg_m, seg_s = [], []
    for leg in osrm_route["legs"]:
        seg_m += leg["annotation"]["distance"]
        seg_s += leg["annotation"]["duration"]
    cum_m, cum_s = [0.0], [0.0]
    for m, s in zip(seg_m, seg_s):
        cum_m.append(cum_m[-1] + m)
        cum_s.append(cum_s[-1] + s)
    summary = " / ".join(dict.fromkeys(l["summary"] for l in osrm_route["legs"] if l["summary"]))
    return {
        "coords": coords,
        "cum_m": cum_m,
        "cum_s": cum_s,
        "distance_m": osrm_route["distance"],
        "duration_s": osrm_route["duration"],
        "summary": summary or "Local roads",
    }


def _is_duplicate(route, others) -> bool:
    """Two routes are the same if their midpoints are close and totals nearly equal."""
    mid, _ = interpolate_at(route["coords"], cumulative_m(route["coords"]), route["distance_m"] / 2)
    for other in others:
        other_mid, _ = interpolate_at(other["coords"], cumulative_m(other["coords"]), other["distance_m"] / 2)
        close_totals = abs(route["distance_m"] - other["distance_m"]) / other["distance_m"] < 0.01
        if haversine_m(mid, other_mid) < 3000 and close_totals:
            return True
    return False


def _detour_via_points(route, scale):
    """Points on either side of the route midpoint, used to force a different road."""
    cum = route["cum_m"]
    (lon, lat), idx = interpolate_at(route["coords"], cum, cum[-1] / 2)
    i = min(int(idx), len(route["coords"]) - 2)
    (lon1, lat1), (lon2, lat2) = route["coords"][i], route["coords"][i + 1]
    # Perpendicular to the local direction, in degrees (good enough for an offset).
    dx, dy = (lon2 - lon1) * math.cos(math.radians(lat)), lat2 - lat1
    norm = math.hypot(dx, dy) or 1.0
    px, py = -dy / norm, dx / norm
    offset_deg = max(0.15, min(2.0, (cum[-1] / 1000) / 111 * scale))
    return [
        [lon + px * offset_deg / math.cos(math.radians(lat)), lat + py * offset_deg],
        [lon - px * offset_deg / math.cos(math.radians(lat)), lat - py * offset_deg],
    ]


def get_routes(origin, destination, wanted=3):
    """Return up to `wanted` distinct routes, fastest first.

    OSRM's `alternatives` often returns only one or two routes. When that
    happens we ask for extra routes through a via-point on each side of the
    main route and keep the ones that are genuinely different.
    """
    start, end = [origin["lon"], origin["lat"]], [destination["lon"], destination["lat"]]
    routes = [_normalise(r) for r in _osrm([start, end], alternatives=True)]
    unique = []
    for r in routes:
        if not _is_duplicate(r, unique):
            unique.append(r)

    for scale in (0.05, 0.10, 0.18):  # try small detours first, then wider ones
        if len(unique) >= wanted:
            break
        for via in _detour_via_points(unique[0], scale):
            if len(unique) >= wanted:
                break
            try:
                candidate = _normalise(_osrm([start, via, end], alternatives=False)[0])
            except ProviderError:
                continue
            # Skip silly detours (more than 30% longer than the best route) and duplicates.
            if candidate["duration_s"] > unique[0]["duration_s"] * MAX_DETOUR_RATIO:
                continue
            if candidate["distance_m"] > unique[0]["distance_m"] * MAX_DETOUR_RATIO:
                continue
            if not _is_duplicate(candidate, unique):
                unique.append(candidate)

    unique.sort(key=lambda r: r["duration_s"])
    return unique[:wanted]


# ------------------------------------------------------------------- weather
def _grid_key(lat, lon):
    # Forecast models are ~10 km resolution, so 0.1 degree is a fair cache grid.
    return round(lat, 1), round(lon, 1)


def _parse_time(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)


def _fetch_chunk(cells):
    data = _get(
        settings.OPEN_METEO_URL,
        params={
            "latitude": ",".join(str(c[0]) for c in cells),
            "longitude": ",".join(str(c[1]) for c in cells),
            "hourly": "wind_speed_10m,rain,snowfall",
            "wind_speed_unit": "mph",
            "timezone": "GMT",
            "past_days": 1,
            "forecast_days": 16,
        },
    )
    results = data if isinstance(data, list) else [data]  # one location -> a bare object
    out = {}
    for cell, item in zip(cells, results):
        hourly = item["hourly"]
        out[cell] = {
            "start": _parse_time(hourly["time"][0]),
            "wind": [v or 0.0 for v in hourly["wind_speed_10m"]],  # mph
            "rain": [(v or 0.0) / MM_PER_INCH for v in hourly["rain"]],  # in/hr
            "snow": [(v or 0.0) / CM_PER_INCH for v in hourly["snowfall"]],  # in/hr
        }
    return out


def fetch_weather(points):
    """Hourly forecast series for many (lat, lon) points.

    Returns {grid_cell: series}. Cells are cached for 30 minutes and missing
    ones are fetched in parallel batches (Open-Meteo accepts many locations
    in a single request).
    """
    cells = {_grid_key(lat, lon) for lat, lon in points}
    found, missing = {}, []
    for cell in cells:
        hit = cache.get(f"wx:{cell}")
        if hit:
            found[cell] = hit
        else:
            missing.append(cell)

    chunks = [missing[i : i + WEATHER_CHUNK] for i in range(0, len(missing), WEATHER_CHUNK)]
    if chunks:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for chunk_result in pool.map(_fetch_chunk, chunks):
                for cell, series in chunk_result.items():
                    cache.set(f"wx:{cell}", series, WEATHER_TTL_S)
                    found[cell] = series
    return found


def weather_at(series_by_cell, lat, lon, when: datetime):
    """Forecast at the hour closest to `when`. Returns (wind_mph, rain_in_hr, snow_in_hr, in_range)."""
    series = series_by_cell[_grid_key(lat, lon)]
    hours = (when - series["start"]).total_seconds() / 3600
    idx = round(hours)
    in_range = 0 <= idx < len(series["wind"])
    idx = max(0, min(len(series["wind"]) - 1, idx))
    return series["wind"][idx], series["rain"][idx], series["snow"][idx], in_range
