import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="Delivery routing | OM 522")


@app.cell
def _():
    import inspect
    import json
    from pathlib import Path
    import matplotlib.pyplot as plt
    import marimo as mo
    import polars as pl
    from routing.cli import solve_instance
    from routing.data import _convert as validate_value, load_instance

    project_root = Path(__file__).resolve().parent
    return inspect, json, plt, mo, pl, solve_instance, validate_value, load_instance, project_root


@app.cell
def _(mo):
    mo.md("""
    # Delivery routing prototype
    **OM 522 · Option 3 · Capacity and delivery time windows**

    Assign every customer to a vehicle and choose the stop order. Reduce travel
    while respecting truck capacity, service-start windows, and driver shifts.

    This notebook runs two methods and checks their exported routes independently.
    """)
    return


@app.cell
def _(mo):
    case_selector = mo.ui.dropdown(
        options={"Hand-checkable · 6 customers": "hand_checkable",
                 "Small · 15 customers": "development_small",
                 "Medium · 45 customers": "development_medium",
                 "Large · 120 customers": "development_large"},
        value="Small · 15 customers", label="Choose an instance", allow_select_none=False,
    )
    rerun_button = mo.ui.button(value=0, on_click=lambda value: value + 1, label="Run both methods again")
    mo.hstack([case_selector, rerun_button], align="end")
    return case_selector, rerun_button


@app.cell
def _(case_selector, json, project_root, rerun_button, solve_instance):
    rerun_button.value
    selected_case = case_selector.value
    input_folder = project_root / "data" / selected_case
    live_results = {}
    for _method in ("baseline", "improved"):
        _output = project_root / "results" / "live" / selected_case / _method
        _summary = solve_instance(input_folder, _output, _method)
        live_results[_method] = {
            "summary": _summary,
            "decision": json.loads((_output / "decision.json").read_text()),
            "check": json.loads((_output / "checker.json").read_text()),
        }
    baseline_summary = live_results["baseline"]["summary"]
    improved_summary = live_results["improved"]["summary"]
    return selected_case, input_folder, live_results, baseline_summary, improved_summary


@app.cell
def _(baseline_summary, improved_summary, mo):
    _before = baseline_summary["metrics"]["total_travel_time"]
    _after = improved_summary["metrics"]["total_travel_time"]
    _saving = _before - _after
    _percentage = 100 * _saving / _before if _before else 0
    mo.vstack([
        mo.callout("Both exported decisions passed the independent checker. Every customer is served exactly once.", kind="success"),
        mo.hstack([
            mo.stat(f"{_before:,.3f}", label="Baseline travel minutes", bordered=True),
            mo.stat(f"{_after:,.3f}", label="Improved travel minutes", bordered=True),
            mo.stat(f"{_saving:,.3f}", label="Travel minutes saved", caption=f"{_percentage:.1f}% reduction", bordered=True),
        ], widths="equal"),
        mo.md("Travel includes every trip from the depot, between customers, and back to the depot. **Waiting and service are excluded from this objective.**"),
    ])
    return


@app.cell
def _(live_results, mo, pl):
    _rows = []
    for _method, _result in live_results.items():
        _summary = _result["summary"]
        _metrics = _summary["metrics"]
        _rows.append({
            "Method": "Baseline" if _method == "baseline" else "Local search",
            "Checker": _summary["independent_check"],
            "Travel (min)": _metrics["total_travel_time"],
            "Vehicles": _metrics["vehicles_used"], "Customers": _metrics["customers_served"],
            "Waiting (min)": _metrics["waiting_time"],
            "Compute (s)": _summary["computation_seconds"],
        })
    mo.ui.table(pl.DataFrame(_rows), selection=None, pagination=False,
                show_data_types=False, show_column_summaries=False, show_search=False,
                column_widths={"Method": 110, "Checker": 80, "Travel (min)": 110,
                               "Vehicles": 80, "Customers": 90, "Waiting (min)": 110, "Compute (s)": 100},
                format_mapping={"Travel (min)": "{:.3f}", "Waiting (min)": "{:.3f}", "Compute (s)": "{:.4f}"},
                label="Same input, same measures, same independent checker")
    return


@app.cell
def _(baseline_summary, improved_summary, mo):
    _waiting_before = baseline_summary["metrics"]["waiting_time"]
    _waiting_after = improved_summary["metrics"]["waiting_time"]
    _stop = improved_summary["stop_reason"]
    _explanation = (
        "The search examined its allowed 30,000 candidate moves and retained the best plan reached. It did not exhaust the neighborhood."
        if _stop == "evaluation_limit" else
        "The search stopped after finding no improving relocate or exchange move in a complete pass. This does not establish a global optimum."
        if _stop == "no_improving_relocate_or_exchange" else
        f"The search stopped because of: {_stop}."
    )
    mo.md(f"""
    **How to interpret this result.** {_explanation}
    The search accepted **{improved_summary['accepted_moves']}** moves and evaluated
    **{improved_summary['evaluations']:,}** candidate moves.

    Waiting changes from **{_waiting_before:,.3f}** to **{_waiting_after:,.3f} minutes**.
    Discuss that operational consequence alongside the travel result. These results
    describe supplied test cases; performance on unseen data remains unverified.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## How the two methods make decisions

    **1 · Nearest feasible neighbor.** Take vehicles in identifier order. Choose the
    nearest unserved customer that fits the remaining capacity, can start service
    within its window, and permits a return by shift end. Break travel-time ties
    by customer identifier. Return when no customer qualifies.

    **2 · Feasible local search.** Start from those routes. Try moving one customer
    to another position or vehicle (*relocate*). When relocation cannot improve
    travel, try swapping two customers on different vehicles (*exchange*). Recompute
    the affected routes and accept only a feasible reduction in travel. Restart
    relocation after each accepted change.

    Both methods represent a plan as a vehicle identifier paired with an **ordered
    customer list**. The search uses a fixed order and no randomness. It stops after
    a full unsuccessful pass or 30,000 candidate evaluations, with a 480-second
    safety cap. It is a heuristic, not a proof of optimality.

    **Published source:** Bräysy & Gendreau (2005), *Vehicle Routing Problem with
    Time Windows, Part I: Route Construction and Local Search Algorithms*,
    Transportation Science 39(1), 104–118.
    [Read the publication](https://doi.org/10.1287/trsc.1030.0056).
    Our adaptation prioritizes travel minutes, as required by this project.
    """)
    return


@app.cell
def _(input_folder, live_results, load_instance, mo, plt):
    _instance = load_instance(input_folder)
    route_figure, _axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    for _ax, (_method, _result) in zip(_axes, live_results.items()):
        for _index, _route in enumerate(_result["decision"]["routes"]):
            _customers = [_instance.customers[c] for c in _route["visits"]]
            _xs = [_instance.depot_x] + [c.x for c in _customers] + [_instance.depot_x]
            _ys = [_instance.depot_y] + [c.y for c in _customers] + [_instance.depot_y]
            _ax.plot(_xs, _ys, "o-", linewidth=1.4, markersize=3.5,
                     color=plt.get_cmap("tab20")(_index % 20), label=_route["vehicle_id"])
        _ax.scatter([_instance.depot_x], [_instance.depot_y], s=100, marker="s", color="#182b45", zorder=5)
        _ax.annotate("Depot", (_instance.depot_x, _instance.depot_y), xytext=(6, 6), textcoords="offset points")
        _ax.set_title("Baseline" if _method == "baseline" else "After local search", fontweight="bold")
        _ax.set_xlabel("Display coordinate x")
        _ax.set_ylabel("Display coordinate y")
        _ax.set_aspect("equal", adjustable="datalim")
        _ax.grid(alpha=0.15)
        if len(_result["decision"]["routes"]) <= 12:
            _ax.legend(fontsize=7, ncol=2, loc="upper right")
    plt.close(route_figure)
    mo.vstack([
        mo.md("## See the assignments"), route_figure,
        mo.md("Lines show visit order using display coordinates. Travel minutes come from the supplied ordered-pair table; these lines are not road navigation."),
    ])
    return


@app.cell
def _(mo):
    trace_method = mo.ui.dropdown(
        {"Baseline": "baseline", "Improved": "improved"}, value="Baseline",
        label="Inspect a plan", allow_select_none=False,
    )
    mo.vstack([mo.md("## Trace a route, one stop at a time"), trace_method])
    return (trace_method,)


@app.cell
def _(live_results, mo, trace_method):
    trace_report = live_results[trace_method.value]["check"]
    _vehicles = [route["vehicle_id"] for route in trace_report["route_summaries"]]
    vehicle_selector = mo.ui.dropdown(_vehicles, value=_vehicles[0], label="Vehicle", allow_select_none=False)
    vehicle_selector
    return trace_report, vehicle_selector


@app.cell
def _(mo, pl, trace_report, vehicle_selector):
    _vehicle_id = vehicle_selector.value
    _stops = [row for row in trace_report["stops"] if row["vehicle_id"] == _vehicle_id]
    _route = next(row for row in trace_report["route_summaries"] if row["vehicle_id"] == _vehicle_id)
    _first = _stops[0]
    _frame = pl.DataFrame(_stops).select(
        "stop", "customer_id", "arrival", "window_start", "window_end",
        "waiting_time", "service_start", "departure",
    ).rename({"stop": "Stop", "customer_id": "Customer", "arrival": "Arrive",
              "window_start": "Opens", "window_end": "Closes", "waiting_time": "Wait",
              "service_start": "Start", "departure": "Leave"})
    mo.vstack([
        mo.md(f"**{_vehicle_id}:** {_route['visits']} → depot. Load **{_route['load']}/{_route['capacity']}**. "
              f"Leaves at **{_route['shift_start']}**; returns at **{_route['return_time']:.3f}**, "
              f"before shift end **{_route['shift_end']}**."),
        mo.ui.table(_frame, selection=None, pagination=True, page_size=10, show_data_types=False,
                    show_column_summaries=False, show_search=False,
                    format_mapping={column: "{:.3f}" for column in ("Arrive", "Wait", "Start", "Leave")}),
        mo.callout(
            f"Read the first stop: arrive at {_first['arrival']:.3f}; the window opens at {_first['window_start']}. "
            f"Wait {_first['waiting_time']:.3f}, start service at {_first['service_start']:.3f}, "
            f"serve for {_first['service_time']} minutes, and leave at {_first['departure']:.3f}. "
            "Service must START by the window end; it may finish afterward.", kind="info"),
    ])
    return


@app.cell
def _(improved_summary, live_results, mo, pl):
    _history_path_note = "Every accepted move is saved in search_history.json beside the decision."
    mo.accordion({
        "What the independent checker verifies": mo.md("""
        The checker reloads the input CSV files and exported `decision.json`.
        It does not call either routing method or their route evaluator. It checks
        complete and unique customer coverage, vehicle use, capacity, every service
        window, shift returns, and the reported times. It rebuilds all travel legs,
        including the return to the depot, and recomputes the measures.
        """),
        "What remains for the final submission": mo.md("""
        Run the same fixed medium-case plans through 30 saved uncertainty scenarios,
        report late services and late returns, examine robustness and runtime,
        and make an evidence-based recommendation. Test stronger search settings
        on the development data. The instructor's 60-customer held-out case is unseen.
        """),
        "Where the search evidence is saved": mo.md(_history_path_note),
    })
    return


@app.cell
def _(inspect, mo, validate_value):
    _code = inspect.getsource(validate_value)
    mo.vstack([
        mo.md("""
        ## Component example

        **Input type checking.** An early exploratory loader converted all numeric
        columns to decimals. That would accept demand `7.5` even though the published
        format requires an integer. The revised loader distinguishes integers from
        general numbers and gives a file-and-column error. The automated test
        `test_fractional_integer_is_rejected` checks this correction.

        The example below shows how the loader distinguishes whole-number demand
        from decimal travel times.
        """),
        mo.accordion({"Show the type-checking function": mo.md("```python\n" + _code + "\n```")}),
    ])
    return


if __name__ == "__main__":
    app.run()
