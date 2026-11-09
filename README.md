This prototype helps a delivery dispatcher decide which vehicle serves each customer and in what order the vehicle visits them. The dispatcher can run it on a new folder of operating data, inspect the proposed routes, and compare a published nearest-feasible-neighbor rule with a route-improvement method. No additional business assumptions are added to the option brief; search order and stopping limits are documented below.

# OM 522 — option 3 prototype

## Start here

Open a terminal in this project folder. Pixi installs the locked environment; no AI account or paid service is needed to run or grade the project.

```sh
pixi install --locked
pixi run test
pixi run demo
pixi run present
```

`present` opens the explanatory Marimo app. To inspect or edit its code, use `pixi run app` instead. Stop the Marimo server with Control-C in its terminal.

The demonstration creates fresh copies of two supplied cases in `results/demo/`, runs the baseline and independent checker on the hand case, verifies the worked example, and compares both methods on the small case. No source data are changed.

## Commands

Run the researched method with default settings:

```sh
pixi run solve data/development_small results/my-run
```

Run the exact rule to beat:

```sh
pixi run solve data/hand_checkable results/hand-baseline --method baseline
```

Independently check an already exported decision:

```sh
pixi run check data/hand_checkable results/hand-baseline/decision.json
```

Regenerate all submitted deterministic comparisons and the notebook's figures:

```sh
pixi run reproduce
```

This one command regenerates the comparisons and the executed notebook, including its figures. `pixi run export` is also available when only the notebook snapshot is needed.

Run only the small comparison:

```sh
pixi run compare data results/small-comparison --profiles development_small
```

Check notebook structure with `pixi run notebook-check`. The exported `results/prototype.html` is a snapshot of the default small-case notebook. Use the live Marimo app to change instances and rerun methods.

## Inputs and outputs

The published column contract is encoded in `routing/data.py` and matches the supplied `schema.json` files. Polars reads CSV fields as strings before explicit type conversion, preserving identifiers and enforcing integer columns. Required fields are not filled or silently replaced. The loader checks required files and columns, types and nulls, identifier references, and positive service durations. It also checks the supplied structural conventions (one depot, unique identifiers, complete ordered travel pairs, valid interval ordering, and nonnegative demands/travel/capacities). It never relies on schema row counts or row order.

Pass **any input folder** with the published four CSV files; no code edit is required. `instance.json` and `schema.json` are retained as supplied documentation and are not needed at runtime. Coordinates support display only. Directed travel-table entries determine every travel leg; symmetry is not assumed by the code.

A successful run writes:

- `decision.json`: used vehicles, ordered visits, arrivals, service starts, and return times, with full precision.
- `summary.json`: status, independently checked measures, runtime definition, search settings and stop reason.
- `checker.json`: independently reconstructed measures, stop details and violations.
- `stops.csv` and `routes.csv`: readable stop and vehicle tables.
- `search_history.json`: every accepted improvement and its travel saving.

Travel minutes include the return to the depot and exclude waiting and service. Vehicles used counts nonempty routes. Computation time measures construction plus improvement; total elapsed time is also saved. Comparisons save the computer information in `run_information.json`.

Malformed input prints an error naming the file and column, produces no `decision.json`, and exits nonzero. Valid input on which the method finds no feasible plan prints `no feasible decision found`, produces no `decision.json`, and exits zero. A failed search is not generally proof that the instance is infeasible; the supplied edge case does have an oversized customer that proves infeasibility. Reusing an output directory removes the project's previous generated decision before starting, avoiding stale success files. Use a distinct output directory for each method/instance.

## Method 1: exact nearest feasible neighbor

**Representation:** a dictionary mapping each vehicle identifier to an ordered list of customer identifiers. Unused vehicles have empty internal lists and are omitted from the exported decision.

1. Take vehicles in identifier order and start each at its shift start.
2. Among unserved customers, keep those that fit capacity, can start service by the window end, and allow return by shift end after service.
3. Choose the minimum `(travel_time, customer_id)` pair, visit it, and update load, location and clock.
4. If none qualifies, return and continue with the next vehicle.
5. Stop after all customers are assigned or all vehicles have been considered.

There is no randomness. This is the required rule, not a global optimizer. `routing/methods.py:nearest_feasible_neighbor` implements it. The hand-case test compares route order, every reported time and every supplied reference measure.

## Method 2: deterministic feasible local search

**Published source:** Olli Bräysy and Michel Gendreau (2005), *Vehicle Routing Problem with Time Windows, Part I: Route Construction and Local Search Algorithms*, Transportation Science 39(1), 104–118. DOI: [10.1287/trsc.1030.0056](https://doi.org/10.1287/trsc.1030.0056). The route-improvement discussion covers relocate and exchange neighborhoods. This project implements its own simple adaptation, not the complete collection of algorithms in the survey.

**Representation and construction:** start with Method 1's feasible plan. Method 2 includes that construction in its measured computation time.

**Improvement:** enumerate relocation candidates in sorted vehicle order, customer position order, destination vehicle order, and insertion-position order. A relocation can move a customer within one route or to another vehicle, including an unused vehicle. Accept the first feasible reduction in total travel and restart relocation. If a complete relocation pass finds no improvement, enumerate cross-vehicle customer exchanges in sorted vehicle/position order. Accept the first feasible reduction and restart relocation. All affected routes have their full timing and load recalculated before acceptance.

**Acceptance:** travel must decrease by more than `1e-9` minutes. Feasibility uses the instructor's `1e-8` endpoint tolerance. Vehicle count is reported separately, not combined into a made-up monetary objective. All saved times retain full precision.

**Stopping:** stop after a full unsuccessful pass through both neighborhoods, 30,000 candidate move evaluations, or a 480-second safety cap measured from command start. The cap leaves room within the instructor's ten-minute command limit for checking and export; it is not the intended stopping mechanism. The default evaluation count and enumeration order make reruns reproducible unless the safety cap is reached. There is no randomness or seed. Overrides are `--max-evaluations` and `--time-limit`.

**Why it may help:** nearest neighbor commits to locally attractive assignments. Moving or exchanging customers can revise those choices while preserving all constraints. Keeping only feasible improvements prevents deterioration from the starting baseline.

**Limitations:** the search cannot cross a temporary worsening or infeasible state, so it can get trapped. An evaluation-limit stop is not evidence of local optimality. The starting construction may fail on other valid instances even when a feasible plan exists. No global optimality or held-out improvement is claimed. Many published VRPTW studies prioritize vehicles first; this adaptation follows the brief's travel-first measure.

## Independent checker

`routing/checker.py` reloads the input files and exported decision and reconstructs every route. It does **not** import either constructor or the method-side route evaluator. It independently checks coverage, duplicates, capacity, vehicle reuse, service windows and shift returns, recalculates travel/waiting/service, and checks the reported times. A better travel number cannot compensate for an infeasible plan.

## Validation evidence

`pixi run test` runs the three required tests plus checks for fractional integers, missing values and files, unknown references, zero service times, row order, renamed identifiers, search limits, determinism, corrupted decisions, capacity, late windows/returns, and service-start boundary semantics.

Verified prototype results (travel minutes):

| Instance | Customers | Baseline travel | Improved travel | Baseline vehicles | Improved vehicles |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hand-checkable | 6 | 352.417 | 352.417 | 2 | 2 |
| Small | 15 | 620.581 | 491.661 | 5 | 5 |
| Medium | 45 | 1683.397 | 1167.546 | 11 | 8 |
| Large | 120 | 3523.223 | 3200.921 | 25 | 23 |

Every exported comparison decision passes the checker. The large case reaches the 30,000-candidate limit. Runtime measurements and stop reasons are in `results/comparison/`; runtime varies by machine. The small-case travel reduction is 128.920 minutes, approximately 20.8%. Waiting increases there from 845.804 to 1037.629 minutes, an operational tradeoff worth explaining. The hand case does not improve. These observations do not establish unseen-instance performance.

## Development review

`docs/REVIEW_LOG.md` records implementation issues, corrections, and validation evidence. `docs/type_validation_evidence.txt` demonstrates the input-type correction. Submit the repository link, the commit hash of the version demonstrated, and an accessible unlisted video link through Blackboard.

## What remains for the final

The fixed-plan stress test is **not implemented** in this prototype. The next stage selects travel or service uncertainty, documents assumptions, saves 30 common scenarios before execution, runs both fixed medium-instance plans, and reports the required means, 90th percentiles, violations and plots. Vehicle count stays fixed within each plan's scenarios. Use the evidence to form a recommendation and identify a condition that would change it. Also review instructor feedback, assess stronger search settings, and confirm the final deadline on Blackboard.

## Attribution and tools

- Input data, the worked example, option brief and project guide: OM 522 instructor-provided synthetic materials, October 14, 2026 release. Original package files are retained under `data/`; source hashes appear in `docs/data_provenance.json`. The project guide is under `docs/`.
- Research: Bräysy and Gendreau (2005), cited above.
- Course concepts: nearest-neighbor construction, local improvement, explicit data structures and independent evaluation. No algorithm code was copied from in-class notebooks.
- OpenAI Codex drafted and revised the code, tests and explanatory material with local execution. Python, Polars, Marimo, Matplotlib, Pixi and Git support implementation and reproducibility. The student remains responsible for reviewing and understanding the submitted work.
