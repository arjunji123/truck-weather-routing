from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from routing import planner, providers
from routing.risk import HIGH, LOW, SEVERE

DEPARTURE = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


def make_route(duration_s, lon_offset=0.0, miles=100):
    """A straight west-east route of `miles` miles split into 100 vertices."""
    n = 101
    coords = [[-100 + lon_offset * 0 + i * 0.0178 * miles / 100 * 1.0, 40.0 + lon_offset] for i in range(n)]
    total_m = miles * 1609.344
    return {
        "coords": coords,
        "cum_m": [total_m * i / (n - 1) for i in range(n)],
        "cum_s": [duration_s * i / (n - 1) for i in range(n)],
        "distance_m": total_m,
        "duration_s": duration_s,
        "summary": "I-80",
    }


def uniform_weather(wind=5.0, rain=0.0, snow=0.0, start=DEPARTURE - timedelta(hours=24)):
    def fetch(points):
        series = {"start": start, "wind": [wind] * 400, "rain": [rain] * 400, "snow": [snow] * 400}
        return {providers._grid_key(lat, lon): series for lat, lon in points}

    return fetch


class CheckpointTests(SimpleTestCase):
    def test_checkpoints_every_interval_and_end(self):
        pts = planner._plan_points(make_route(7200), 25, DEPARTURE)
        self.assertEqual([round(p["mile"]) for p in pts], [0, 25, 50, 75, 100])

    def test_final_partial_interval_included(self):
        pts = planner._plan_points(make_route(7200, miles=90), 25, DEPARTURE)
        self.assertEqual(round(pts[-1]["mile"]), 90)

    def test_eta_scales_with_truck_factor(self):
        pts = planner._plan_points(make_route(7200), 50, DEPARTURE)
        self.assertEqual(pts[0]["eta"], DEPARTURE)
        expected = DEPARTURE + timedelta(seconds=7200 * planner.TRUCK_TIME_FACTOR)
        self.assertAlmostEqual((pts[-1]["eta"] - expected).total_seconds(), 0, delta=1)

    def test_segment_miles_sum_to_route_length(self):
        pts = planner._plan_points(make_route(7200, miles=90), 25, DEPARTURE)
        self.assertAlmostEqual(sum(planner._segment_miles(pts)), 90, places=3)


class WeatherTimingTests(SimpleTestCase):
    def test_weather_is_read_at_eta_not_departure(self):
        """Wind picks up 3 hours after departure; only far checkpoints should see it."""
        start = DEPARTURE
        wind = [5.0] * 3 + [40.0] * 100
        series = {"start": start, "wind": wind, "rain": [0.0] * 103, "snow": [0.0] * 103}

        def fetch(points):
            return {providers._grid_key(lat, lon): series for lat, lon in points}

        route = make_route(4 * 3600)  # 4 h trip, ~4.4 h for a truck
        route["checkpoint_points"] = planner._plan_points(route, 25, DEPARTURE)
        route["heat_points"] = route["checkpoint_points"]
        weather = fetch([(p["lat"], p["lon"]) for p in route["checkpoint_points"]])
        cps = planner._build_checkpoints(route, weather, load_lb=10_000)
        self.assertEqual(cps[0]["risk"]["level"], LOW)
        self.assertEqual(cps[-1]["risk"]["level"], HIGH)


class RecommendationTests(SimpleTestCase):
    def _route(self, label, severe=0, high=0, avg=0.0, duration=3600):
        return {"label": label, "duration_s": duration, "stats": {"no_travel_miles": 0, "severe_miles": severe, "high_miles": high, "avg_risk": avg}}

    def test_fewest_severe_wins_even_if_slower(self):
        routes = [self._route("Route A", severe=30, duration=3000), self._route("Route B", severe=0, duration=9000)]
        self.assertEqual(planner.recommend(routes)[0], 1)

    def test_high_miles_break_severe_tie(self):
        routes = [self._route("Route A", high=50), self._route("Route B", high=10, duration=5000)]
        self.assertEqual(planner.recommend(routes)[0], 1)

    def test_average_risk_then_time(self):
        routes = [self._route("Route A", avg=0.9), self._route("Route B", avg=0.4, duration=5000)]
        self.assertEqual(planner.recommend(routes)[0], 1)
        same = [self._route("Route A", avg=0.4, duration=5000), self._route("Route B", avg=0.4, duration=3000)]
        self.assertEqual(planner.recommend(same)[0], 1)

    def test_sub_mile_differences_are_ties(self):
        routes = [self._route("Route A", severe=0.4, duration=9000), self._route("Route B", severe=0.0, duration=3000)]
        self.assertEqual(planner.recommend(routes)[0], 1)

    def test_no_travel_route_is_never_preferred(self):
        a = self._route("Route A", duration=3000)
        a["stats"]["no_travel_miles"] = 5
        b = self._route("Route B", severe=40, duration=9000)
        self.assertEqual(planner.recommend([a, b])[0], 1)


class BuildPlanTests(SimpleTestCase):
    def test_end_to_end_with_stubbed_routing(self):
        routes = [make_route(3600, lon_offset=0), make_route(4000, lon_offset=0.01), make_route(5000, lon_offset=0.02)]
        original = providers.get_routes
        providers.get_routes = lambda *_a, **_k: routes
        try:
            origin = {"name": "A", "lat": 40, "lon": -100}
            dest = {"name": "B", "lat": 40, "lon": -98}
            result = planner.build_plan(origin, dest, DEPARTURE, 20_000, 25, fetch=uniform_weather(wind=40))
        finally:
            providers.get_routes = original
        self.assertEqual(len(result["routes"]), 3)
        self.assertEqual(result["recommended_index"], 0)  # identical weather -> fastest
        first = result["routes"][0]
        self.assertEqual(first["stats"]["worst_level"], HIGH)
        self.assertEqual(len(first["heat"][0]["levels"]), 49)
        self.assertEqual(first["checkpoints"][0]["mile"], 0)

    def test_heavy_load_escalates_in_plan(self):
        route = make_route(3600)
        original = providers.get_routes
        providers.get_routes = lambda *_a, **_k: [route]
        try:
            origin = {"name": "A", "lat": 40, "lon": -100}
            result = planner.build_plan(origin, origin, DEPARTURE, 45_000, 50, fetch=uniform_weather(wind=40))
        finally:
            providers.get_routes = original
        self.assertEqual(result["routes"][0]["stats"]["worst_level"], SEVERE)
