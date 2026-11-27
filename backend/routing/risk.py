"""Weather risk classification for a single checkpoint.

Pure functions only (no I/O) so the rules are easy to read and test.

Levels are integers so they can be compared and averaged:
    0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel
"""

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)
LEVEL_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"]

# Upper bounds per level. A value at or above the last bound is "No Travel".
# Wind ranges are "25-34", "35-44", "45-54": 35.0 belongs to High, so the
# bounds are exclusive (value < bound).
WIND_LIMITS_MPH = (25, 35, 45, 55)
# Rain/snow ranges are written "0.10-0.25", "0.25-0.50": a value equal to the
# shared edge is placed in the lower band (value <= bound), while "<0.10" and
# ">1.00" in the table are respected exactly.
RAIN_LIMITS_IN_HR = (0.10, 0.25, 0.50, 1.00)
SNOW_LIMITS_IN_HR = (0.5, 1.0, 2.0, 3.0)

HEAVY_LOAD_LB = 30_000
VERY_HEAVY_LOAD_LB = 40_000


def wind_level(mph: float) -> int:
    for level, bound in enumerate(WIND_LIMITS_MPH):
        if mph < bound:
            return level
    return NO_TRAVEL


def _precip_level(value: float, limits) -> int:
    low, mod, high, severe = limits
    if value < low:
        return LOW
    if value <= mod:
        return MODERATE
    if value <= high:
        return HIGH
    if value <= severe:
        return SEVERE
    return NO_TRAVEL


def rain_level(in_per_hr: float) -> int:
    return _precip_level(in_per_hr, RAIN_LIMITS_IN_HR)


def snow_level(in_per_hr: float) -> int:
    return _precip_level(in_per_hr, SNOW_LIMITS_IN_HR)


def wind_level_for_load(mph: float, load_lb: float) -> int:
    """Wind level after applying the load rules."""
    level = wind_level(mph)
    if mph >= 55:
        return NO_TRAVEL  # any load
    if 45 <= mph < 55 and load_lb > HEAVY_LOAD_LB:
        return NO_TRAVEL
    if 35 <= mph < 45 and load_lb > VERY_HEAVY_LOAD_LB:
        return max(level, SEVERE)
    return level


def classify(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> dict:
    """Overall level is the worst of wind, rain and snow."""
    levels = {
        "wind": wind_level_for_load(wind_mph, load_lb),
        "rain": rain_level(rain_in_hr),
        "snow": snow_level(snow_in_hr),
    }
    overall = max(levels.values())
    return {"level": overall, "label": LEVEL_NAMES[overall], "factors": levels}
