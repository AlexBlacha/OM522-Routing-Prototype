"""The two routing methods. The independent checker lives in another module.

Method 1 implements the option brief verbatim. Method 2 starts from method 1,
then applies first-improvement relocate and inter-route exchange moves.
"""

from dataclasses import dataclass, field
from time import perf_counter

from .data import Instance


TOLERANCE = 1e-8


@dataclass
class MethodResult:
    plan: dict[str, list[str]] | None
    reason: str
    evaluations: int = 0
    accepted_moves: list[dict] = field(default_factory=list)
    stop_reason: str = "construction_complete"


def route_schedule(instance: Instance, vehicle_id: str, visits: list[str]):
    """Method-side route evaluation. The checker does NOT call this function."""
    vehicle = instance.vehicles[vehicle_id]
    load = sum(instance.customers[c].demand for c in visits)
    if load > vehicle.capacity:
        return None
    clock = vehicle.shift_start
    previous = instance.depot_id
    arrivals, starts = [], []
    travel_total = 0.0
    for customer_id in visits:
        customer = instance.customers[customer_id]
        leg = instance.travel[previous, customer_id]
        arrival = clock + leg
        service_start = max(arrival, customer.window_start)
        if service_start > customer.window_end + TOLERANCE:
            return None
        arrivals.append(arrival)
        starts.append(service_start)
        # The window constrains service START, not completion.
        clock = service_start + customer.service_time
        travel_total += leg
        previous = customer_id
    return_leg = instance.travel[previous, instance.depot_id] if visits else 0.0
    return_time = clock + return_leg
    if return_time > vehicle.shift_end + TOLERANCE:
        return None
    return {
        "vehicle_id": vehicle_id, "visits": list(visits), "arrivals": arrivals,
        "service_starts": starts, "return_time": return_time,
        "travel_time": travel_total + return_leg,
    }


def nearest_feasible_neighbor(instance: Instance) -> MethodResult:
    """Vehicles and travel-time ties follow identifier order, as required."""
    unserved = set(instance.customers)
    plan = {vehicle_id: [] for vehicle_id in sorted(instance.vehicles)}
    for vehicle_id, visits in plan.items():
        vehicle = instance.vehicles[vehicle_id]
        clock = vehicle.shift_start
        origin = instance.depot_id
        load = 0
        while unserved:
            candidates = []
            for customer_id in sorted(unserved):
                customer = instance.customers[customer_id]
                travel = instance.travel[origin, customer_id]
                arrival = clock + travel
                service_start = max(arrival, customer.window_start)
                departure = service_start + customer.service_time
                if (
                    load + customer.demand <= vehicle.capacity
                    and service_start <= customer.window_end + TOLERANCE
                    and departure + instance.travel[customer_id, instance.depot_id]
                    <= vehicle.shift_end + TOLERANCE
                ):
                    candidates.append((travel, customer_id, departure))
            if not candidates:
                break  # Return to depot; the next vehicle starts at its own shift start.
            _, selected, departure = min(candidates)
            visits.append(selected)
            unserved.remove(selected)
            load += instance.customers[selected].demand
            origin, clock = selected, departure
    if unserved:
        oversized = [
            customer_id for customer_id in sorted(unserved)
            if all(instance.customers[customer_id].demand > v.capacity for v in instance.vehicles.values())
        ]
        reason = f"Unserved customers: {', '.join(sorted(unserved))}."
        if oversized:
            reason += f" Demand exceeds every vehicle capacity: {', '.join(oversized)}."
        return MethodResult(None, reason, stop_reason="construction_failed")
    return MethodResult(plan, "Every customer assigned by the published rule.")


def improve_routes(instance: Instance, max_evaluations=30000, deadline=None) -> MethodResult:
    """Deterministic variable-neighborhood descent on travel minutes.

After any accepted move, restart relocation from the beginning. Try exchanges
only after relocation finds no improvement. Accept only feasible strict travel
reductions; this protects the initial feasible plan but cannot prove optimality.
"""
    result = nearest_feasible_neighbor(instance)
    if result.plan is None:
        return result
    plan = {vehicle: list(visits) for vehicle, visits in result.plan.items()}
    vehicle_ids = sorted(plan)
    schedules = {vehicle: route_schedule(instance, vehicle, plan[vehicle]) for vehicle in vehicle_ids}
    if any(schedule is None for schedule in schedules.values()):
        raise RuntimeError("Initial plan failed method-side route evaluation")
    total = sum(schedule["travel_time"] for schedule in schedules.values())

    def budget_available():
        if result.evaluations >= max_evaluations:
            result.stop_reason = "evaluation_limit"
            return False
        if deadline is not None and perf_counter() >= deadline:
            result.stop_reason = "time_safety_cap"
            return False
        return True

    def consider(patch, description):
        nonlocal total
        result.evaluations += 1
        replacements = {vehicle: route_schedule(instance, vehicle, visits) for vehicle, visits in patch.items()}
        if any(schedule is None for schedule in replacements.values()):
            return False
        old_cost = sum(schedules[vehicle]["travel_time"] for vehicle in patch)
        new_cost = sum(schedule["travel_time"] for schedule in replacements.values())
        if new_cost >= old_cost - 1e-9:
            return False
        before = total
        total += new_cost - old_cost
        for vehicle, visits in patch.items():
            plan[vehicle] = visits
            schedules[vehicle] = replacements[vehicle]
        result.accepted_moves.append({
            "move": description, "travel_before": before, "travel_after": total,
            "saving": old_cost - new_cost,
        })
        return True

    def try_relocate():
        for source in vehicle_ids:
            for position, customer_id in enumerate(plan[source]):
                shortened = plan[source][:position] + plan[source][position + 1:]
                for destination in vehicle_ids:
                    destination_base = shortened if source == destination else plan[destination]
                    for insertion in range(len(destination_base) + 1):
                        candidate = destination_base[:insertion] + [customer_id] + destination_base[insertion:]
                        if source == destination and candidate == plan[source]:
                            continue
                        if not budget_available():
                            return None
                        patch = {destination: candidate}
                        if source != destination:
                            patch[source] = shortened
                        description = f"relocate {customer_id}: {source} -> {destination}, position {insertion + 1}"
                        if consider(patch, description):
                            return True
        return False

    def try_exchange():
        for index, first in enumerate(vehicle_ids):
            for second in vehicle_ids[index + 1:]:
                for first_position, first_customer in enumerate(plan[first]):
                    for second_position, second_customer in enumerate(plan[second]):
                        if not budget_available():
                            return None
                        first_route, second_route = list(plan[first]), list(plan[second])
                        first_route[first_position] = second_customer
                        second_route[second_position] = first_customer
                        description = f"exchange {first_customer} ({first}) with {second_customer} ({second})"
                        if consider({first: first_route, second: second_route}, description):
                            return True
        return False

    while True:
        moved = try_relocate()
        if moved is None:
            break
        if moved:
            continue
        moved = try_exchange()
        if moved is None:
            break
        if moved:
            continue
        result.stop_reason = "no_improving_relocate_or_exchange"
        break
    result.plan = plan
    result.reason = f"Retained a feasible plan after {len(result.accepted_moves)} improving moves."
    return result


def export_decision(instance: Instance, plan: dict[str, list[str]]) -> dict:
    routes = []
    for vehicle_id in sorted(plan):
        if not plan[vehicle_id]:
            continue
        route = route_schedule(instance, vehicle_id, plan[vehicle_id])
        if route is None:
            raise RuntimeError(f"Cannot export an infeasible route for {vehicle_id}")
        routes.append({key: value for key, value in route.items() if key != "travel_time"})
    return {"routes": routes}
