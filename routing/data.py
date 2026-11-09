"""Load the published CSV contract without changing or filling input values.

Polars reads every column as text first. We then enforce the published types;
this preserves identifiers such as '001' and catches fractional integer values.
"""

from dataclasses import dataclass
import math
from pathlib import Path
import re

import polars as pl


class InputError(ValueError):
    """A clear input error that names the affected file and column."""


SCHEMA = {
    "depots.csv": {"node_id": "string", "x": "number", "y": "number"},
    "customers.csv": {
        "customer_id": "string", "x": "number", "y": "number",
        "demand": "integer", "service_time": "integer",
        "window_start": "integer", "window_end": "integer",
    },
    "vehicles.csv": {
        "vehicle_id": "string", "capacity": "integer",
        "shift_start": "integer", "shift_end": "integer",
    },
    "travel_times.csv": {
        "from_id": "string", "to_id": "string", "travel_time": "number",
    },
}


@dataclass(frozen=True)
class Customer:
    customer_id: str
    x: float
    y: float
    demand: int
    service_time: int
    window_start: int
    window_end: int


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    capacity: int
    shift_start: int
    shift_end: int


@dataclass(frozen=True)
class Instance:
    depot_id: str
    depot_x: float
    depot_y: float
    customers: dict[str, Customer]
    vehicles: dict[str, Vehicle]
    travel: dict[tuple[str, str], float]


def _convert(value, kind, filename, column, row_number):
    location = f"{filename}, column '{column}', row {row_number}"
    if value is None or not value.strip():
        raise InputError(f"{location}: required value is missing")
    if kind == "string":
        return value  # Identifiers are matched by value, never by row number.
    try:
        if kind == "integer":
            if not re.fullmatch(r"[+-]?\d+", value.strip()):
                raise ValueError
            return int(value)
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return number
    except (ValueError, OverflowError):
        raise InputError(f"{location}: expected {kind}, received {value!r}") from None


def _read_table(directory, filename):
    path = directory / filename
    if not path.is_file():
        raise InputError(f"{filename}, column '*': required file is missing")
    try:
        frame = pl.read_csv(path, infer_schema=False, raise_if_empty=False)
    except Exception as error:
        raise InputError(f"{filename}, column '*': cannot read CSV ({error})") from None
    for column in SCHEMA[filename]:
        if column not in frame.columns:
            raise InputError(f"{filename}, column '{column}': required column is missing")
    return [
        {
            column: _convert(row[column], kind, filename, column, number)
            for column, kind in SCHEMA[filename].items()
        }
        for number, row in enumerate(frame.iter_rows(named=True), start=2)
    ]


def _unique(rows, filename, column):
    lookup = {}
    for row in rows:
        identifier = row[column]
        if identifier in lookup:
            raise InputError(f"{filename}, column '{column}': duplicate identifier {identifier!r}")
        lookup[identifier] = row
    return lookup


def load_instance(directory: str | Path) -> Instance:
    """Load any instance folder; schema row counts and row order are not assumed."""
    directory = Path(directory)
    tables = {name: _read_table(directory, name) for name in SCHEMA}
    depots = tables["depots.csv"]
    if len(depots) != 1:
        raise InputError("depots.csv, column 'node_id': exactly one depot is required")
    depot = depots[0]
    customer_rows = _unique(tables["customers.csv"], "customers.csv", "customer_id")
    vehicle_rows = _unique(tables["vehicles.csv"], "vehicles.csv", "vehicle_id")
    if depot["node_id"] in customer_rows:
        raise InputError("customers.csv, column 'customer_id': identifier also names the depot")
    for row in customer_rows.values():
        if row["service_time"] <= 0:
            raise InputError(f"customers.csv, column 'service_time': must be positive for {row['customer_id']}")
        if row["demand"] < 0:
            raise InputError(f"customers.csv, column 'demand': cannot be negative for {row['customer_id']}")
        if row["window_start"] > row["window_end"]:
            raise InputError(f"customers.csv, column 'window_end': precedes window_start for {row['customer_id']}")
    for row in vehicle_rows.values():
        if row["capacity"] < 0:
            raise InputError(f"vehicles.csv, column 'capacity': cannot be negative for {row['vehicle_id']}")
        if row["shift_start"] > row["shift_end"]:
            raise InputError(f"vehicles.csv, column 'shift_end': precedes shift_start for {row['vehicle_id']}")
    location_ids = {depot["node_id"], *customer_rows}
    travel = {}
    for row in tables["travel_times.csv"]:
        for column in ("from_id", "to_id"):
            if row[column] not in location_ids:
                raise InputError(f"travel_times.csv, column '{column}': unknown location {row[column]!r}")
        key = (row["from_id"], row["to_id"])
        if key in travel:
            raise InputError(f"travel_times.csv, column 'from_id/to_id': duplicate ordered pair {key}")
        if row["travel_time"] < 0:
            raise InputError(f"travel_times.csv, column 'travel_time': negative time for {key}")
        travel[key] = row["travel_time"]
    for origin in sorted(location_ids):
        for destination in sorted(location_ids):
            if (origin, destination) not in travel:
                raise InputError(f"travel_times.csv, column 'travel_time': missing ordered pair {(origin, destination)}")
    return Instance(
        depot_id=depot["node_id"], depot_x=depot["x"], depot_y=depot["y"],
        customers={key: Customer(**row) for key, row in customer_rows.items()},
        vehicles={key: Vehicle(**row) for key, row in vehicle_rows.items()},
        travel=travel,
    )
