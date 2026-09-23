import copy
import itertools
import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.calculator import calculate_plan, load_data


def plan(*pairs):
    return [{"measure_id": m, "district_id": d} for m, d in pairs]


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.data = load_data()
        self.example = self.data["test_example"]["selections"]

    def row(self, result, district, metric):
        return next(r for r in result["comparison"] if r["district_id"] == district and r["metric_id"] == metric)

    def test_official_example_and_weights(self):
        result = calculate_plan(self.example)
        for key, expected in self.data["test_example"]["expected"].items():
            if key.startswith("critical_"):
                self.assertEqual(result["critical_counts"][key.removeprefix("critical_")], expected)
            else:
                self.assertEqual(result[key], expected)
        self.assertEqual(len(result["comparison"]), 50)
        self.assertEqual(sum(Decimal(str(d["population_share"])) for d in self.data["districts"]), 1)
        self.assertEqual(sum(Decimal(str(w)) for w in self.data["metric_weights"].values()), 1)
        self.assertEqual([d["before"] for d in result["district_scores"]], [62.99, 57.06, 54.65, 56.63, 49.18])
        json.dumps(result)

    def test_order_independence_and_no_mutation(self):
        original = copy.deepcopy(self.example)
        expected = calculate_plan(self.example)
        for order in itertools.permutations(self.example):
            self.assertEqual(calculate_plan(list(order)), expected)
        self.assertEqual(self.example, original)

    def test_lag_city_effect_and_fixed_synergy(self):
        result = calculate_plan(self.example)
        self.assertEqual(self.row(result, "nura", "S1")["after"], 48)
        self.assertEqual(self.row(result, "nura", "S2")["after"], 43.75)
        self.assertEqual(self.row(result, "nura", "B1")["delta"], 12.5)
        for district in self.data["districts"]:
            self.assertEqual(self.row(result, district["id"], "C2")["delta"], 4.375)
        self.assertEqual(self.row(result, "saryarka", "E2")["delta"], 8.75)
        self.assertEqual(self.row(result, "almaty", "S1")["delta"], 0)

    def test_other_synergies(self):
        result = calculate_plan(plan(("M1", "nura"), ("M2", None), ("M9", "esil"), ("M11", "esil"), ("M12", None)))
        self.assertEqual(self.row(result, "nura", "T1")["delta"], 9.5)
        result = calculate_plan(plan(("M5", "nura"), ("M6", None), ("M9", "esil"), ("M11", "esil"), ("M12", None)))
        self.assertEqual(self.row(result, "nura", "E2")["delta"], 12.25)
        self.assertEqual(self.row(result, "esil", "E2")["delta"], 1.5)

    def test_cheapest_example_negative_effect_and_strict_threshold(self):
        result = calculate_plan(plan(("M9", "esil"), ("M11", "almaty"), ("M10", "esil"), ("M12", None), ("M4", "esil")))
        self.assertEqual(result["budget_spent"], 61)
        row = self.row(result, "almaty", "T1")
        self.assertFalse(row["critical_before"])
        self.assertTrue(row["critical_after"])
        self.assertEqual(row["after"], 38.25)
        self.assertEqual(result["critical_counts"]["after"], 3)
        self.assertEqual(result["score_components"]["after"]["critical_penalty"], 3)

    def test_global_and_local_incompatibilities(self):
        cases = [
            (plan(("M1", "nura"), ("M3", "esil"), ("M9", "nura"), ("M11", "nura"), ("M12", None)), "M1 и M3"),
            (plan(("M4", "nura"), ("M7", "nura"), ("M9", "esil"), ("M11", "nura"), ("M12", None)), "M4 и M7"),
            (plan(("M5", "nura"), ("M13", "nura"), ("M9", "esil"), ("M11", "nura"), ("M12", None)), "M5 и M13"),
        ]
        for selections, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                calculate_plan(selections)
        for selections, _ in cases[1:]:
            selections[1]["district_id"] = "esil"
            calculate_plan(selections)

    def test_budget_boundary(self):
        selections = plan(("M3", "nura"), ("M7", "nura"), ("M8", "nura"), ("M10", "nura"), ("M12", None))
        self.assertEqual(calculate_plan(selections)["budget_remaining"], 0)
        selections[-1] = {"measure_id": "M14", "district_id": None}
        with self.assertRaisesRegex(ValueError, "Бюджет превышен: 102"):
            calculate_plan(selections)

    def test_direction_limit(self):
        with self.assertRaisesRegex(ValueError, "максимум 2"):
            calculate_plan(plan(("M7", "nura"), ("M8", "nura"), ("M9", "nura"), ("M11", "nura"), ("M12", None)))

    def test_invalid_inputs_and_duplicates(self):
        for value in (None, {}, [], self.example[:4], self.example + [self.example[0]]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_plan(value)
        for replacement in (None, {}, {"measure_id": []}, {"measure_id": "M99"}, {"measure_id": "M7"}, {"measure_id": "M7", "district_id": []}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                calculate_plan([replacement] + self.example[1:])
        self.example[1] = {"measure_id": "M7", "district_id": "esil"}
        with self.assertRaisesRegex(ValueError, "Повтор мероприятия"):
            calculate_plan(self.example)

    def test_city_district_and_cost_contract(self):
        self.example[3].pop("district_id")
        self.example[0]["cost"] = 0
        self.assertEqual(calculate_plan(self.example)["budget_spent"], 95)
        self.example[3]["district_id"] = "nura"
        with self.assertRaisesRegex(ValueError, "городской меры"):
            calculate_plan(self.example)

    def test_clipping_at_both_bounds(self):
        # Синтетические граничные значения проверяют clip; официальный JSON не меняется.
        self.data["districts"][0]["indicators"].update({"T1": 1, "B1": 99})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(self.data), encoding="utf-8")
            with patch("backend.calculator.DATA_PATH", path):
                result = calculate_plan(plan(("M9", "esil"), ("M11", "esil"), ("M10", "esil"), ("M12", None), ("M4", "esil")))
        self.assertEqual(self.row(result, "esil", "T1")["after"], 0)
        self.assertEqual(self.row(result, "esil", "B1")["after"], 100)


if __name__ == "__main__":
    unittest.main()
