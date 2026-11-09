"""Independent checking from original input data and an exported decision.

This module deliberately imports no route constructor or method-side evaluator.
It recomputes the clock, demand and every travel leg from the saved visit lists.
"""

from collections import Counter
import json
import math
from pathlib import Path

from .data import Instance, load_instance


TOLERANCE = 1e-8


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_decision(instance: Instance, decision) -> dict:
    errors, stops, route_summaries = [], [], []
    visited, used_vehicles = Counter(), Counter()
    travel_legs, waits, service_durations = [], [], []
    if not isinstance(decision, dict) or not isinstance(decision.get("routes"), list):
        return {"feasible": False, "violations": ["decision.json: 'routes' must be a list"],
                "metrics": {}, "stops": [], "route_summaries": []}

    def verify_reported(actual, expected, label):
        if not _number(actual):
            errors.append(f"{label}: expected a finite number")
        elif abs(actual - expected) > TOLERANCE:
            errors.append(f"{label}: reported {actual}, recomputed {expected}")

    for route_number, route in enumerate(decision["routes"], start=1):
        label = f"route {route_number}"
        if not isinstance(route, dict):
            errors.append(f"{label}: expected an object")
            continue
        vehicle_id, visits = route.get("vehicle_id"), route.get("visits")
        if not isinstance(vehicle_id, str) or vehicle_id not in instance.vehicles:
            errors.append(f"{label}: unknown vehicle_id {vehicle_id!r}")
            vehicle = None
        else:
            vehicle = instance.vehicles[vehicle_id]
            label = f"vehicle {vehicle_id}"
        if not isinstance(visits, list) or any(not isinstance(c, str) for c in visits):
            errors.append(f"{label}: 'visits' must be a list of customer identifiers")
            continue
        if not visits:
            errors.append(f"{label}: omit unused vehicles rather than exporting empty routes")
            continue
        if vehicle is not None:
            used_vehicles[vehicle_id] += 1
        for customer_id in visits:
            visited[customer_id] += 1
            if customer_id not in instance.customers:
                errors.append(f"{label}: unknown customer {customer_id!r}")
        for field in ("arrivals", "service_starts"):
            values = route.get(field)
            if not isinstance(values, list) or len(values) != len(visits):
                errors.append(f"{label}: '{field}' must have one value per visit")
        if vehicle is None or any(c not in instance.customers for c in visits):
            continue

        load = sum(instance.customers[c].demand for c in visits)
        if load > vehicle.capacity:
            errors.append(f"{label}: load {load} exceeds capacity {vehicle.capacity}")
        clock, previous = vehicle.shift_start, instance.depot_id
        route_travel, route_wait = [], []
        for position, customer_id in enumerate(visits):
            customer = instance.customers[customer_id]
            leg = instance.travel[previous, customer_id]
            arrival = clock + leg
            waiting = max(0.0, customer.window_start - arrival)
            start = arrival + waiting
            finish = start + customer.service_time
            if start > customer.window_end + TOLERANCE:
                errors.append(f"{label}, customer {customer_id}: service starts at {start}, after window end {customer.window_end}")
            for field, expected in (("arrivals", arrival), ("service_starts", start)):
                values = route.get(field)
                if isinstance(values, list) and position < len(values):
                    verify_reported(values[position], expected, f"{label}, customer {customer_id}, {field}")
            stops.append({
                "vehicle_id": vehicle_id, "stop": position + 1, "customer_id": customer_id,
                "from_id": previous, "travel_time": leg, "arrival": arrival,
                "window_start": customer.window_start, "window_end": customer.window_end,
                "waiting_time": waiting, "service_start": start,
                "service_time": customer.service_time, "departure": finish,
                "window_margin": customer.window_end - start, "demand": customer.demand,
            })
            route_travel.append(leg)
            route_wait.append(waiting)
            service_durations.append(customer.service_time)
            previous, clock = customer_id, finish
        return_leg = instance.travel[previous, instance.depot_id]
        return_time = clock + return_leg
        route_travel.append(return_leg)
        if return_time > vehicle.shift_end + TOLERANCE:
            errors.append(f"{label}: returns at {return_time}, after shift end {vehicle.shift_end}")
        verify_reported(route.get("return_time"), return_time, f"{label}, return_time")
        travel_legs.extend(route_travel)
        waits.extend(route_wait)
        route_summaries.append({
            "vehicle_id": vehicle_id, "visits": " -> ".join(visits), "load": load,
            "capacity": vehicle.capacity, "shift_start": vehicle.shift_start,
            "return_time": return_time, "shift_end": vehicle.shift_end,
            "return_margin": vehicle.shift_end - return_time,
            "travel_time": math.fsum(route_travel), "waiting_time": math.fsum(route_wait),
        })
    for vehicle_id, count in sorted(used_vehicles.items()):
        if count > 1:
            errors.append(f"vehicle {vehicle_id}: appears on {count} routes; at most one is allowed")
    for customer_id in sorted(instance.customers):
        count = visited[customer_id]
        if count != 1:
            errors.append(f"customer {customer_id}: served {count} times; exactly once is required")
    return {
        "feasible": not errors, "violations": errors,
        "metrics": {
            "total_travel_time": math.fsum(travel_legs),
            "vehicles_used": len(used_vehicles), "waiting_time": math.fsum(waits),
            "service_time": math.fsum(service_durations),
            "customers_served": sum(visited[c] > 0 for c in instance.customers),
        },
        "stops": stops, "route_summaries": route_summaries,
    }


def check_file(input_directory: str | Path, decision_path: str | Path) -> dict:
    """Reload both sources; do not trust solver state or any reported totals."""
    instance = load_instance(input_directory)
    try:
        decision = json.loads(Path(decision_path).read_text())
    except (OSError, ValueError) as error:
        return {"feasible": False, "violations": [f"decision.json: {error}"],
                "metrics": {}, "stops": [], "route_summaries": []}
    return check_decision(instance, decision)
