"""Small geometry helpers for polylines given as [lon, lat] pairs."""
import math

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344


def haversine_m(a, b) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def cumulative_m(coords) -> list:
    """Distance from the start to every vertex."""
    out = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_m(prev, cur))
    return out


def interpolate_at(coords, cum, target_m):
    """Point on the polyline `target_m` metres from the start, plus the fractional vertex index."""
    if target_m <= 0:
        return coords[0], 0.0
    if target_m >= cum[-1]:
        return coords[-1], float(len(coords) - 1)
    lo, hi = 0, len(cum) - 1
    while hi - lo > 1:  # binary search for the segment
        mid = (lo + hi) // 2
        if cum[mid] <= target_m:
            lo = mid
        else:
            hi = mid
    span = cum[hi] - cum[lo] or 1.0
    t = (target_m - cum[lo]) / span
    lon = coords[lo][0] + (coords[hi][0] - coords[lo][0]) * t
    lat = coords[lo][1] + (coords[hi][1] - coords[lo][1]) * t
    return [lon, lat], lo + t


def interpolate_value(values, index):
    """Linearly interpolate `values` at a fractional index."""
    lo = int(index)
    if lo >= len(values) - 1:
        return values[-1]
    t = index - lo
    return values[lo] + (values[lo + 1] - values[lo]) * t


def thin(coords, min_spacing_m=500):
    """Drop vertices closer than `min_spacing_m` (always keeps first and last)."""
    if len(coords) <= 2:
        return coords
    kept = [coords[0]]
    for c in coords[1:-1]:
        if haversine_m(kept[-1], c) >= min_spacing_m:
            kept.append(c)
    kept.append(coords[-1])
    return kept


def sample_distances_m(total_m, step_m):
    """0, step, 2*step ... and always the exact end of the route."""
    marks = []
    d = 0.0
    while d < total_m:
        marks.append(d)
        d += step_m
    marks.append(total_m)
    return marks
