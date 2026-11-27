from django.test import SimpleTestCase

from routing.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE, classify, rain_level, snow_level, wind_level, wind_level_for_load


class WindTests(SimpleTestCase):
    def test_bands(self):
        cases = {0: LOW, 24.9: LOW, 25: MODERATE, 34.9: MODERATE, 35: HIGH, 44.9: HIGH, 45: SEVERE, 54.9: SEVERE, 55: NO_TRAVEL, 80: NO_TRAVEL}
        for mph, expected in cases.items():
            self.assertEqual(wind_level(mph), expected, mph)


class PrecipTests(SimpleTestCase):
    def test_rain_bands(self):
        cases = {0.09: LOW, 0.10: MODERATE, 0.25: MODERATE, 0.26: HIGH, 0.50: HIGH, 0.51: SEVERE, 1.00: SEVERE, 1.01: NO_TRAVEL}
        for value, expected in cases.items():
            self.assertEqual(rain_level(value), expected, value)

    def test_snow_bands(self):
        cases = {0.4: LOW, 0.5: MODERATE, 1.0: MODERATE, 1.5: HIGH, 2.0: HIGH, 2.5: SEVERE, 3.0: SEVERE, 3.1: NO_TRAVEL}
        for value, expected in cases.items():
            self.assertEqual(snow_level(value), expected, value)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(wind_level_for_load(55, 0), NO_TRAVEL)

    def test_45_to_54_with_heavy_load_is_no_travel(self):
        self.assertEqual(wind_level_for_load(50, 30_001), NO_TRAVEL)
        self.assertEqual(wind_level_for_load(50, 30_000), SEVERE)  # not "more than" 30,000
        self.assertEqual(wind_level_for_load(50, 10_000), SEVERE)

    def test_35_to_44_with_very_heavy_load_is_severe(self):
        self.assertEqual(wind_level_for_load(40, 40_001), SEVERE)
        self.assertEqual(wind_level_for_load(40, 40_000), HIGH)

    def test_light_wind_unaffected_by_load(self):
        self.assertEqual(wind_level_for_load(20, 80_000), LOW)


class ClassifyTests(SimpleTestCase):
    def test_worst_factor_wins(self):
        result = classify(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6, load_lb=20_000)
        self.assertEqual(result["level"], HIGH)
        self.assertEqual(result["label"], "High")
        self.assertEqual(result["factors"], {"wind": LOW, "rain": HIGH, "snow": MODERATE})

    def test_load_can_escalate_overall(self):
        self.assertEqual(classify(40, 0, 0, 50_000)["level"], SEVERE)
        self.assertEqual(classify(40, 0, 0, 10_000)["level"], HIGH)
