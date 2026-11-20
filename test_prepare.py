"""Small drivers with analytically known effects."""
import math
from datetime import date
import unittest

from prepare import completed_quarter_labels, hedonic_step, stratum_step


def many(town, flat, price, count=25, features=None):
    return [(town, flat, price, features) for _ in range(count)]


class HousingIndexTests(unittest.TestCase):
    def test_period_cutoff(self):
        self.assertEqual(completed_quarter_labels(date(2025, 1, 1), date(2025, 10, 2)),
                         ["2025-Q1", "2025-Q2", "2025-Q3"])

    def test_stratification_ignores_mix_shift(self):
        older = many("A", "3 ROOM", 100, 50) + many("B", "3 ROOM", 220, 15)
        newer = many("A", "3 ROOM", 100, 15) + many("B", "3 ROOM", 220, 50)
        result, coverage, matched = stratum_step({("A", "3 ROOM"): 50, ("B", "3 ROOM"): 15}, older, newer)
        self.assertEqual(result, 1)
        self.assertEqual((coverage, matched), (1, 2))

    def test_stratum_suppresses_insufficient_coverage(self):
        older = many("A", "3 ROOM", 100) + many("B", "3 ROOM", 220)
        newer = many("A", "3 ROOM", 130)
        result, coverage, matched = stratum_step({("A", "3 ROOM"): 30, ("B", "3 ROOM"): 70}, older, newer)
        self.assertIsNone(result)
        self.assertAlmostEqual(coverage, .3)
        self.assertEqual(matched, 1)

    def test_hedonic_recovers_known_time_effect_with_shifted_sizes(self):
        def quarter(start, rate):
            rows = []
            for i in range(160):
                area = start + i / 10
                inputs = (math.log(area), 5 + (i % 4) / 10, (i % 7) / 10)
                amount = rate * math.exp(6 + .65 * inputs[0] + .09 * inputs[1] + .22 * inputs[2])
                rows.append(("A", "3 ROOM", amount, inputs))
            return rows
        rate, rows = hedonic_step(quarter(55, 1), quarter(60, 1.15))
        self.assertAlmostEqual(rate, 1.15)
        self.assertEqual(rows, 320)

    def test_small_model_is_suppressed(self):
        price = many("A", "3 ROOM", 85, 90, (1, 2, 3))
        result, count = hedonic_step(price, price)
        self.assertIsNone(result)
        self.assertEqual(count, 180)


if __name__ == "__main__":
    unittest.main()
