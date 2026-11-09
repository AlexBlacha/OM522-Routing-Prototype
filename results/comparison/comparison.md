# Deterministic comparison

Both methods use identical inputs and the same independent checker.

| Instance | Method | Feasible | Travel (min) | Vehicles | Compute (s) |
| --- | --- | --- | ---: | ---: | ---: |
| hand_checkable | baseline | True | 352.417 | 2 | 0.0000 |
| hand_checkable | improved | True | 352.417 | 2 | 0.0003 |
| development_small | baseline | True | 620.581 | 5 | 0.0001 |
| development_small | improved | True | 491.661 | 5 | 0.0053 |
| development_medium | baseline | True | 1683.397 | 11 | 0.0004 |
| development_medium | improved | True | 1167.546 | 8 | 0.1052 |
| development_large | baseline | True | 3523.223 | 25 | 0.0032 |
| development_large | improved | True | 3200.921 | 23 | 0.1055 |

Travel excludes waiting and service. Runtime measures construction and improvement; the run metadata records the computer and limits.
These are supplied-instance results, not proof of optimality or held-out performance.
