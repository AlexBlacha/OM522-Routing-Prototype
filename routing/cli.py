"""Documented terminal entry points for solving, checking and comparing."""

import argparse
import csv
import json
import math
from pathlib import Path
import platform
import shutil
import sys
from tempfile import NamedTemporaryFile
from time import perf_counter

from .checker import check_file
from .data import InputError, load_instance
from .methods import export_decision, improve_routes, nearest_feasible_neighbor


PROFILES = ("hand_checkable", "development_small", "development_medium", "development_large")
DEFAULT_EVALUATIONS = 30000
DEFAULT_TIME_LIMIT = 480.0


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, suffix=".tmp") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def solve_instance(input_directory, output_directory, method="improved",
                   max_evaluations=DEFAULT_EVALUATIONS, time_limit=DEFAULT_TIME_LIMIT):
    """Write a decision, then independently reload and check that exact file."""
    started = perf_counter()
    input_directory, output_directory = Path(input_directory), Path(output_directory)
    if input_directory.resolve() == output_directory.resolve():
        raise InputError("output directory: must differ from the input directory")
    output_directory.mkdir(parents=True, exist_ok=True)
    # Remove only our own generated files, preventing a stale successful decision
    # from surviving a later invalid or unsuccessful run in the same directory.
    for name in ("decision.json", "summary.json", "checker.json", "stops.csv", "routes.csv", "search_history.json"):
        (output_directory / name).unlink(missing_ok=True)
    instance = load_instance(input_directory)
    solve_started = perf_counter()
    if method == "baseline":
        outcome = nearest_feasible_neighbor(instance)
    elif method == "improved":
        outcome = improve_routes(instance, max_evaluations, started + time_limit)
    else:
        raise ValueError(f"Unknown method {method}")
    computation_seconds = perf_counter() - solve_started
    summary = {
        "method": method, "instance": input_directory.name,
        "status": "no feasible decision found" if outcome.plan is None else "feasible",
        "reason": outcome.reason, "computation_seconds": computation_seconds,
        "runtime_definition": "route construction plus improvement; excludes input loading, export and independent checking",
        "max_evaluations": max_evaluations if method == "improved" else None,
        "time_limit_seconds": time_limit,
        "evaluations": outcome.evaluations, "accepted_moves": len(outcome.accepted_moves),
        "stop_reason": outcome.stop_reason, "randomization": "none",
    }
    if outcome.plan is None:
        summary["total_elapsed_seconds"] = perf_counter() - started
        write_json(output_directory / "summary.json", summary)
        return summary
    decision = export_decision(instance, outcome.plan)
    write_json(output_directory / "decision.json", decision)
    report = check_file(input_directory, output_directory / "decision.json")
    write_json(output_directory / "checker.json", report)
    if not report["feasible"]:
        (output_directory / "decision.json").unlink(missing_ok=True)
        raise RuntimeError("Exported decision failed the independent checker: " + "; ".join(report["violations"]))
    summary["metrics"] = report["metrics"]
    summary["independent_check"] = "PASS"
    write_csv(output_directory / "stops.csv", report["stops"])
    write_csv(output_directory / "routes.csv", report["route_summaries"])
    write_json(output_directory / "search_history.json", outcome.accepted_moves)
    summary["total_elapsed_seconds"] = perf_counter() - started
    write_json(output_directory / "summary.json", summary)
    return summary


def print_summary(summary):
    print(f"Method: {summary['method']}")
    print(f"Status: {summary['status']}")
    if "metrics" in summary:
        measures = summary["metrics"]
        print(f"Independent checker: {summary['independent_check']}")
        print(f"Travel: {measures['total_travel_time']:.3f} minutes")
        print(f"Vehicles used: {measures['vehicles_used']}")
        print(f"Customers served: {measures['customers_served']}")
        print(f"Waiting: {measures['waiting_time']:.3f} minutes (excluded from travel)")
    print(f"Computation: {summary['computation_seconds']:.4f} seconds")
    print(f"Stopping reason: {summary['stop_reason']}")
    print(summary["reason"])


def compare_instances(data_directory, output_directory, profiles=PROFILES,
                      max_evaluations=DEFAULT_EVALUATIONS, time_limit=DEFAULT_TIME_LIMIT):
    data_directory, output_directory = Path(data_directory), Path(output_directory)
    rows = []
    for profile in profiles:
        for method in ("baseline", "improved"):
            summary = solve_instance(data_directory / profile, output_directory / profile / method,
                                     method, max_evaluations, time_limit)
            metrics = summary.get("metrics", {})
            rows.append({
                "instance": profile, "method": method,
                "feasible": summary["status"] == "feasible",
                "total_travel_time": metrics.get("total_travel_time"),
                "vehicles_used": metrics.get("vehicles_used"),
                "waiting_time": metrics.get("waiting_time"),
                "customers_served": metrics.get("customers_served"),
                "computation_seconds": summary["computation_seconds"],
                "evaluations": summary["evaluations"], "accepted_moves": summary["accepted_moves"],
                "stop_reason": summary["stop_reason"],
            })
    write_csv(output_directory / "comparison.csv", rows)
    write_json(output_directory / "comparison.json", rows)
    write_json(output_directory / "run_information.json", {
        "computer": {"system": platform.system(), "release": platform.release(),
                     "machine": platform.machine(), "python": platform.python_version(),
                     "processor": platform.processor()},
        "max_evaluations": max_evaluations, "time_limit_seconds": time_limit,
        "randomization": "none; sorted identifiers and fixed first-improvement order",
        "runtime_definition": "construction plus improvement, independently timed for each method",
    })
    lines = ["# Deterministic comparison", "",
             "Both methods use identical inputs and the same independent checker.", "",
             "| Instance | Method | Feasible | Travel (min) | Vehicles | Compute (s) |",
             "| --- | --- | --- | ---: | ---: | ---: |"]
    for row in rows:
        travel = f"{row['total_travel_time']:.3f}" if row["feasible"] else "n/a"
        lines.append(f"| {row['instance']} | {row['method']} | {row['feasible']} | {travel} | {row['vehicles_used']} | {row['computation_seconds']:.4f} |")
    lines.extend(["", "Travel excludes waiting and service. Runtime measures construction and improvement; the run metadata records the computer and limits.",
                  "These are supplied-instance results, not proof of optimality or held-out performance.", ""])
    (output_directory / "comparison.md").write_text("\n".join(lines))
    return rows


def run_demo(project_root):
    """Create fresh copies and show the minimum prototype demonstration."""
    project_root = Path(project_root)
    demo_root = project_root / "results" / "demo"
    hand = demo_root / "fresh_hand_case"
    small = demo_root / "fresh_small_case"
    for profile, target in (("hand_checkable", hand), ("development_small", small)):
        shutil.copytree(project_root / "data" / profile, target, dirs_exist_ok=True)
    print("Fresh input folders copied; no code edits were made.\n")
    hand_summary = solve_instance(hand, demo_root / "hand_baseline", "baseline")
    expected_decision = json.loads((project_root / "data" / "worked-example" / "solution.json").read_text())
    actual_decision = json.loads((demo_root / "hand_baseline" / "decision.json").read_text())
    expected_metrics = json.loads((project_root / "data" / "worked-example" / "metrics.json").read_text())
    # Compare visits exactly and floating-point timings to the instructor tolerance.
    if [(r["vehicle_id"], r["visits"]) for r in actual_decision["routes"]] != [
        (r["vehicle_id"], r["visits"]) for r in expected_decision["routes"]
    ]:
        raise RuntimeError("Worked-example route order does not match")
    for key, expected in expected_metrics.items():
        if not math.isclose(hand_summary["metrics"][key], expected, abs_tol=1e-8, rel_tol=0):
            raise RuntimeError(f"Worked-example measure does not match: {key}")
    print("WORKED EXAMPLE: PASS (route order and all reference measures)")
    print_summary(hand_summary)
    print("\nDEVELOPMENT CASE: 15 customers")
    for method in ("baseline", "improved"):
        print()
        print_summary(solve_instance(small, demo_root / f"small_{method}", method))
    print("\nSaved decisions and independent checker reports are in results/demo/.")


def _positive_integer(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="OM 522 delivery routing prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)
    solve = subparsers.add_parser("solve", help="solve one instance and check its exported routes")
    solve.add_argument("input_directory", type=Path)
    solve.add_argument("output_directory", type=Path)
    solve.add_argument("--method", choices=("baseline", "improved"), default="improved")
    solve.add_argument("--max-evaluations", type=_positive_integer, default=DEFAULT_EVALUATIONS)
    solve.add_argument("--time-limit", type=_positive_number, default=DEFAULT_TIME_LIMIT)
    check = subparsers.add_parser("check", help="independently check an existing decision.json")
    check.add_argument("input_directory", type=Path)
    check.add_argument("decision_path", type=Path)
    check.add_argument("--report", type=Path)
    compare = subparsers.add_parser("compare", help="compare both methods on supplied cases")
    compare.add_argument("data_directory", type=Path)
    compare.add_argument("output_directory", type=Path)
    compare.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    compare.add_argument("--max-evaluations", type=_positive_integer, default=DEFAULT_EVALUATIONS)
    compare.add_argument("--time-limit", type=_positive_number, default=DEFAULT_TIME_LIMIT)
    subparsers.add_parser("demo", help="run the prototype on fresh copies of two supplied cases")
    args = parser.parse_args(argv)
    try:
        if args.command == "solve":
            print_summary(solve_instance(args.input_directory, args.output_directory,
                                         args.method, args.max_evaluations, args.time_limit))
        elif args.command == "check":
            report = check_file(args.input_directory, args.decision_path)
            if args.report:
                write_json(args.report, report)
            print("Independent checker: " + ("PASS" if report["feasible"] else "FAIL"))
            if report["feasible"]:
                print(f"Travel: {report['metrics']['total_travel_time']:.3f} minutes")
                print(f"Vehicles used: {report['metrics']['vehicles_used']}")
                print(f"Customers served: {report['metrics']['customers_served']}")
            for violation in report["violations"]:
                print(f"- {violation}")
            return 0 if report["feasible"] else 1
        elif args.command == "compare":
            rows = compare_instances(args.data_directory, args.output_directory, args.profiles,
                                     args.max_evaluations, args.time_limit)
            for row in rows:
                travel = f"{row['total_travel_time']:.3f}" if row["feasible"] else "n/a"
                print(f"{row['instance']:20} {row['method']:9} feasible={row['feasible']} "
                      f"travel={travel} vehicles={row['vehicles_used']} "
                      f"seconds={row['computation_seconds']:.4f}")
            print(f"Saved comparison to {args.output_directory}")
        elif args.command == "demo":
            run_demo(Path(__file__).resolve().parents[1])
    except InputError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Run failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
