import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from routing import providers

ROW = [41.9, -87.6, "2026-01-10T00:00", [10, None], [25.4, 0], [2.54, 0]]
CELL = (41.9, -87.6)


def rate_limited(*_args, **_kwargs):
    raise providers.ProviderError("limited", upstream_status=429)


class WeatherFallbackTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_429_asks_for_the_missing_cells(self):
        with patch.object(providers, "_get", rate_limited):
            with self.assertRaises(providers.WeatherRateLimited) as caught:
                providers.fetch_weather([CELL])
        self.assertEqual(caught.exception.cells, [CELL])

    def test_supplied_weather_is_converted_used_and_not_cached(self):
        supplied = providers.parse_supplied_weather([ROW])
        with patch.object(providers, "_get", rate_limited):
            series = providers.fetch_weather([CELL], supplied=supplied)[CELL]
        self.assertEqual(series["wind"], [10, 0.0])
        self.assertAlmostEqual(series["rain"][0], 1.0)
        self.assertAlmostEqual(series["snow"][0], 1.0)
        self.assertIsNone(cache.get(f"wx:{CELL}"))

    def test_bad_supplied_weather_is_rejected(self):
        for bad in ({}, [[1, 2]], [ROW[:3] + [["x"], [0], [0]]], [ROW[:3] + [[1], [], [0]]]):
            with self.assertRaises((TypeError, ValueError)):
                providers.parse_supplied_weather(bad)

    def test_api_returns_weather_request_on_rate_limit(self):
        error = providers.WeatherRateLimited([CELL])
        body = {"origin": "1,1", "destination": "2,2", "departure": "2026-01-10T00:00:00Z", "load_lb": 1}
        with patch("routing.views.build_plan", side_effect=error):
            res = self.client.post("/api/plan", json.dumps(body), content_type="application/json")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["weather_needed"]["cells"], [list(CELL)])
