"""Turns raw routes into checkpoints with ETAs, weather risk and a recommendation."""
from datetime import timedelta

from . import providers
from .geo import METERS_PER_MILE, interpolate_at, sample_distances_m, thin
from .risk import HIGH, LEVEL_NAMES, NO_TRAVEL, SEVERE, classify

# OSRM times are for cars; trucks are slower on grades and legally limited.
TRUCK_TIME_FACTOR = 1.10

HEAT_HOURS = 49  # forecast hours 0..48 after departure
HEAT_MAX_SAMPLES = 80
HEAT_MIN_SPACING_MI = 10

# Differences smaller than this count as a tie when ranking (see rank_key).
MILE_TOLERANCE = 1.0
RISK_TOLERANCE = 0.05


def _plan_points(route, step_miles, departure):
    """Positions along the route with the truck's ETA at each one."""
    total_m = route["cum_m"][-1]
    points = []
    for dist_m in sample_distances_m(total_m, step_miles * METERS_PER_MILE):
        (lon, lat), idx = interpolate_at(route["coords"], route["cum_m"], dist_m)
        # Time at this distance = interpolated cumulative seconds, scaled for a truck.
        lo = min(int(idx), len(route["cum_s"]) - 2)
        t = idx - lo
        secs = route["cum_s"][lo] + (route["cum_s"][lo + 1] - route["cum_s"][lo]) * t
        points.append(
            {"mile": dist_m / METERS_PER_MILE, "lat": lat, "lon": lon, "eta": departure + timedelta(seconds=secs * TRUCK_TIME_FACTOR)}
        )
    return points


def _segment_miles(points):
    """Miles each checkpoint 'owns': halfway to its neighbours on each side."""
    miles = [p["mile"] for p in points]
    out = []
    for i, m in enumerate(miles):
        left = (miles[i - 1] + m) / 2 if i > 0 else m
        right = (m + miles[i + 1]) / 2 if i < len(miles) - 1 else m
        out.append(right - left)
    return out


def _route_stats(checkpoints):
    total = sum(c["segment_miles"] for c in checkpoints) or 1.0
    by_level = [0.0] * 5
    weighted = 0.0
    for c in checkpoints:
        by_level[c["risk"]["level"]] += c["segment_miles"]
        weighted += c["risk"]["level"] * c["segment_miles"]
    return {
        "miles_by_level": [round(v, 1) for v in by_level],
        "no_travel_miles": by_level[NO_TRAVEL],
        "severe_miles": by_level[SEVERE],
        "high_miles": by_level[HIGH],
        "avg_risk": weighted / total,
        "worst_level": max(c["risk"]["level"] for c in checkpoints),
    }


def rank_key(route):
    """Lower is better. Mirrors the brief: severe, then high, then average risk, then time.

    Two extras make the result sensible in practice:
    * No Travel miles come first: a route you may not drive is never "best".
    * Small gaps (under a mile, or 0.05 risk points) count as ties so a
      trivial difference in weather does not beat a much faster route.
    """
    s = route["stats"]
    return (
        round(s["no_travel_miles"] / MILE_TOLERANCE),
        round(s["severe_miles"] / MILE_TOLERANCE),
        round(s["high_miles"] / MILE_TOLERANCE),
        round(s["avg_risk"] / RISK_TOLERANCE),
        route["duration_s"],
    )


_CRITERIA = ["No Travel miles", "Severe miles", "High miles", "average risk", "travel time"]


def recommend(routes):
    """Returns (best_index, explanation)."""
    order = sorted(range(len(routes)), key=lambda i: rank_key(routes[i]))
    best = routes[order[0]]
    if len(order) == 1:
        return order[0], "Only one route was found."
    runner = routes[order[1]]
    kb, kr = rank_key(best), rank_key(runner)
    first_diff = next((i for i in range(5) if kb[i] != kr[i]), 4)

    s_best, s_run = best["stats"], runner["stats"]
    if first_diff == 0:
        text = f"{best['label']} avoids {s_run['no_travel_miles'] - s_best['no_travel_miles']:.0f} more No Travel miles than {runner['label']}."
    elif first_diff == 1:
        text = f"{best['label']} has {s_best['severe_miles']:.0f} Severe miles vs {s_run['severe_miles']:.0f} on {runner['label']}."
    elif first_diff == 2:
        text = f"Severe miles are tied; {best['label']} has {s_best['high_miles']:.0f} High-risk miles vs {s_run['high_miles']:.0f} on {runner['label']}."
    elif first_diff == 3:
        text = f"Severe and High miles are tied; {best['label']} has lower average risk ({s_best['avg_risk']:.2f} vs {s_run['avg_risk']:.2f})."
    else:
        text = f"Weather risk is about the same on the top routes, so {best['label']} wins on travel time."
    if s_best["no_travel_miles"] > 0:
        text += " Warning: every route has No Travel weather. Consider changing the departure time."
    return order[0], text


def build_plan(origin, destination, departure, load_lb, interval_miles, fetch=providers.fetch_weather):
    routes = providers.get_routes(origin, destination)

    # 1. Work out where we need weather (checkpoints + heatmap samples) for every route.
    for i, route in enumerate(routes):
        route["label"] = f"Route {chr(65 + i)}"
        route["checkpoint_points"] = _plan_points(route, interval_miles, departure)
        total_mi = route["cum_m"][-1] / METERS_PER_MILE
        heat_step = max(HEAT_MIN_SPACING_MI, total_mi / HEAT_MAX_SAMPLES)
        route["heat_points"] = _plan_points(route, heat_step, departure)

    all_points = [
        (p["lat"], p["lon"])
        for r in routes
        for p in r["checkpoint_points"] + r["heat_points"]
    ]
    # 2. One batched, cached weather lookup for everything.
    weather = fetch(all_points)

    # 3. Classify.
    for route in routes:
        route["checkpoints"] = _build_checkpoints(route, weather, load_lb)
        route["stats"] = _route_stats(route["checkpoints"])
        route["heat"] = _build_heat(route, weather, departure, load_lb)

    best_index, reason = recommend(routes)
    fastest = min(r["duration_s"] for r in routes)
    return {
        "origin": origin,
        "destination": destination,
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_miles": interval_miles,
        "level_names": LEVEL_NAMES,
        "recommended_index": best_index,
        "recommendation_reason": reason,
        "heat_hours": HEAT_HOURS,
        "routes": [_serialise(r, departure, fastest) for r in routes],
    }


def _build_checkpoints(route, weather, load_lb):
    seg = _segment_miles(route["checkpoint_points"])
    out = []
    for p, segment_miles in zip(route["checkpoint_points"], seg):
        wind, rain, snow, in_range = providers.weather_at(weather, p["lat"], p["lon"], p["eta"])
        out.append(
            {
                "mile": round(p["mile"], 1),
                "segment_miles": segment_miles,
                "lat": round(p["lat"], 5),
                "lon": round(p["lon"], 5),
                "eta": p["eta"].isoformat(),
                "wind_mph": round(wind, 1),
                "rain_in_hr": round(rain, 3),
                "snow_in_hr": round(snow, 3),
                "forecast_in_range": in_range,
                "risk": classify(wind, rain, snow, load_lb),
            }
        )
    return out


def _build_heat(route, weather, departure, load_lb):
    """For each sample along the corridor, the risk level for each of the next 48 hours."""
    samples = []
    for p in route["heat_points"]:
        levels = []
        for h in range(HEAT_HOURS):
            wind, rain, snow, _ = providers.weather_at(weather, p["lat"], p["lon"], departure + timedelta(hours=h))
            levels.append(classify(wind, rain, snow, load_lb)["level"])
        samples.append({"mile": round(p["mile"], 1), "lat": round(p["lat"], 5), "lon": round(p["lon"], 5), "levels": levels})
    return samples


def _serialise(route, departure, fastest_s):
    duration_s = route["duration_s"] * TRUCK_TIME_FACTOR
    stats = route["stats"]
    return {
        "label": route["label"],
        "summary": route["summary"],
        "distance_miles": round(route["distance_m"] / METERS_PER_MILE, 1),
        "duration_s": round(duration_s),
        "arrival": (departure + timedelta(seconds=duration_s)).isoformat(),
        "extra_minutes_vs_fastest": round((route["duration_s"] - fastest_s) * TRUCK_TIME_FACTOR / 60),
        "geometry": thin(route["coords"]),  # [lon, lat] pairs
        "stats": {
            **stats,
            "avg_risk": round(stats["avg_risk"], 2),
            "no_travel_miles": round(stats["no_travel_miles"], 1),
            "severe_miles": round(stats["severe_miles"], 1),
            "high_miles": round(stats["high_miles"], 1),
        },
        "checkpoints": [{k: v for k, v in c.items() if k != "segment_miles"} for c in route["checkpoints"]],
        "heat": route["heat"],
    }
