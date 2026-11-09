"""Behavior checks for the assignment contract and common routing mistakes."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from routing.checker import check_decision, check_file
from routing.cli import main, solve_instance
from routing.data import Customer, InputError, Instance, Vehicle, load_instance
from routing.methods import export_decision, improve_routes, nearest_feasible_neighbor


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def rewrite_csv(path, transform):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    fields, rows = transform(fields, rows)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hand = load_instance(DATA / "hand_checkable")
        cls.baseline = export_decision(cls.hand, nearest_feasible_neighbor(cls.hand).plan)

    def copied_case(self, temporary, profile="hand_checkable"):
        target = Path(temporary) / "a fresh input folder"
        shutil.copytree(DATA / profile, target)
        return target

    def test_01_rule_reproduces_worked_example_decision_and_measures(self):
        expected = json.loads((DATA / "worked-example/solution.json").read_text())
        self.assertEqual(len(self.baseline["routes"]), len(expected["routes"]))
        for actual, reference in zip(self.baseline["routes"], expected["routes"]):
            self.assertEqual(actual["vehicle_id"], reference["vehicle_id"])
            self.assertEqual(actual["visits"], reference["visits"])
            for field in ("arrivals", "service_starts"):
                self.assertEqual(len(actual[field]), len(reference[field]))
                for left, right in zip(actual[field], reference[field]):
                    self.assertAlmostEqual(left, right, delta=1e-8)
            self.assertAlmostEqual(actual["return_time"], reference["return_time"], delta=1e-8)
        report = check_decision(self.hand, self.baseline)
        self.assertTrue(report["feasible"], report["violations"])
        reference = json.loads((DATA / "worked-example/metrics.json").read_text())
        for key, value in reference.items():
            self.assertAlmostEqual(report["metrics"][key], value, delta=1e-8)

    def test_02_edge_case_reports_no_feasible_decision_and_no_stale_file(self):
        for method in ("baseline", "improved"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "out"
                output.mkdir()
                (output / "decision.json").write_text('{"stale": true}')
                captured = io.StringIO()
                with redirect_stdout(captured):
                    code = main(["solve", str(DATA / "edge_case"), str(output), "--method", method])
                self.assertEqual(code, 0)
                self.assertIn("no feasible decision found", captured.getvalue())
                self.assertFalse((output / "decision.json").exists())
                self.assertIn("C010", (output / "summary.json").read_text())

    def test_03_missing_required_column_rejected_with_file_and_column(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            rewrite_csv(case / "customers.csv", lambda fields, rows: (
                [f for f in fields if f != "demand"],
                [{k: v for k, v in row.items() if k != "demand"} for row in rows],
            ))
            output = Path(temporary) / "out"
            output.mkdir()
            (output / "decision.json").write_text('{"stale": true}')
            captured = io.StringIO()
            with redirect_stderr(captured):
                code = main(["solve", str(case), str(output)])
            self.assertNotEqual(code, 0)
            self.assertIn("customers.csv", captured.getvalue())
            self.assertIn("demand", captured.getvalue())
            self.assertFalse((output / "decision.json").exists())

    def test_fractional_integer_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            def fractional(fields, rows):
                rows[0]["demand"] = "7.5"
                return fields, rows
            rewrite_csv(case / "customers.csv", fractional)
            with self.assertRaisesRegex(InputError, "customers.csv.*demand.*integer"):
                load_instance(case)

    def test_zero_service_duration_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            def zero(fields, rows):
                rows[0]["service_time"] = "0"
                return fields, rows
            rewrite_csv(case / "customers.csv", zero)
            with self.assertRaisesRegex(InputError, "customers.csv.*service_time.*positive"):
                load_instance(case)

    def test_missing_value_and_unknown_reference_rejected(self):
        for filename, column, value in (("customers.csv", "demand", ""),
                                         ("travel_times.csv", "from_id", "UNKNOWN")):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as temporary:
                case = self.copied_case(temporary)
                def mutate(fields, rows):
                    rows[0][column] = value
                    return fields, rows
                rewrite_csv(case / filename, mutate)
                with self.assertRaisesRegex(InputError, filename + ".*" + column):
                    load_instance(case)

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            (case / "vehicles.csv").unlink()
            with self.assertRaisesRegex(InputError, "vehicles.csv.*missing"):
                load_instance(case)

    def test_row_order_does_not_change_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            for path in case.glob("*.csv"):
                rewrite_csv(path, lambda fields, rows: (fields, list(reversed(rows))))
            instance = load_instance(case)
            self.assertEqual(export_decision(instance, nearest_feasible_neighbor(instance).plan), self.baseline)

    def test_renamed_identifiers_and_fresh_path_work_without_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.copied_case(temporary)
            names = {self.hand.depot_id: "warehouse", **{c: f"stop-{c}" for c in self.hand.customers}}
            for filename, columns in (("depots.csv", ("node_id",)),
                                      ("customers.csv", ("customer_id",)),
                                      ("travel_times.csv", ("from_id", "to_id"))):
                def rename(fields, rows):
                    for row in rows:
                        for column in columns:
                            row[column] = names[row[column]]
                    return fields, rows
                rewrite_csv(case / filename, rename)
            output = Path(temporary) / "results"
            summary = solve_instance(case, output, "baseline")
            self.assertAlmostEqual(summary["metrics"]["total_travel_time"], 352.417, delta=1e-8)
            self.assertTrue(check_file(case, output / "decision.json")["feasible"])

    def test_improvement_is_feasible_no_worse_and_reproducible(self):
        instance = load_instance(DATA / "development_small")
        reference = check_decision(instance, export_decision(instance, nearest_feasible_neighbor(instance).plan))
        first = improve_routes(instance)
        second = improve_routes(instance)
        self.assertEqual(first.plan, second.plan)
        self.assertEqual(first.evaluations, second.evaluations)
        self.assertLessEqual(first.evaluations, 30000)
        report = check_decision(instance, export_decision(instance, first.plan))
        self.assertTrue(report["feasible"], report["violations"])
        self.assertLessEqual(report["metrics"]["total_travel_time"], reference["metrics"]["total_travel_time"])
        for move in first.accepted_moves:
            self.assertLess(move["travel_after"], move["travel_before"])

    def test_search_count_limit_retains_feasible_incumbent(self):
        result = improve_routes(self.hand, max_evaluations=1)
        self.assertLessEqual(result.evaluations, 1)
        self.assertEqual(result.stop_reason, "evaluation_limit")
        self.assertTrue(check_decision(self.hand, export_decision(self.hand, result.plan))["feasible"])

    def test_checker_catches_missing_duplicate_and_forged_times(self):
        for mutation, expected in (
            (lambda d: d["routes"].pop(), "served 0 times"),
            (lambda d: d["routes"].append(copy.deepcopy(d["routes"][0])), "served 2 times"),
            (lambda d: d["routes"][0]["arrivals"].__setitem__(0, -99), "recomputed"),
        ):
            with self.subTest(expected=expected):
                decision = copy.deepcopy(self.baseline)
                mutation(decision)
                report = check_decision(self.hand, decision)
                self.assertFalse(report["feasible"])
                self.assertIn(expected, " ".join(report["violations"]))

    def test_service_start_at_window_end_and_finish_after_end_are_allowed(self):
        instance = Instance(
            "D", 0, 0,
            {"C": Customer("C", 1, 1, 10, 10, 0, 20)},
            {"V": Vehicle("V", 10, 10, 40)},
            {("D", "D"): 0, ("D", "C"): 10, ("C", "D"): 10, ("C", "C"): 0},
        )
        decision = {"routes": [{"vehicle_id": "V", "visits": ["C"], "arrivals": [20],
                                "service_starts": [20], "return_time": 40}]}
        report = check_decision(instance, decision)
        self.assertTrue(report["feasible"], report["violations"])
        self.assertEqual(export_decision(instance, nearest_feasible_neighbor(instance).plan), decision)
        overloaded = replace(instance, vehicles={"V": Vehicle("V", 9, 10, 40)})
        self.assertIn("exceeds capacity", " ".join(check_decision(overloaded, decision)["violations"]))
        late_window = replace(instance, customers={"C": replace(instance.customers["C"], window_end=19)})
        self.assertIn("after window end", " ".join(check_decision(late_window, decision)["violations"]))
        late_return = replace(instance, vehicles={"V": Vehicle("V", 10, 10, 39)})
        self.assertIn("after shift end", " ".join(check_decision(late_return, decision)["violations"]))


if __name__ == "__main__":
    unittest.main()
