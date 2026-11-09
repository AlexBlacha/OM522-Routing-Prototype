# Worked example for option 3

Planning delivery routes.

This example applies the option's rule to beat (defined in option-3-brief.pdf) to ../hand_checkable/. It shows one feasible decision and how every measure except computation time is recomputed from that decision. It is not an optimal answer. The rule to beat is the team's first method, and the team's researched method must outperform this rule by more than 0.001 on the instructor's held-out case. solution.json has the structure that a team's decision.json must use. metrics.json is a reference for testing, not a required output, and its key names are not graded (e.g., makespan is the final or project completion time, and on_time_rate is the on-time fraction). Counts such as jobs_completed are consistency checks, not additional measures. The JSON files keep full numeric precision, and the tables below round to three decimals. All times are in minutes.

The rule fills vehicles in identifier order. Each vehicle leaves DEPOT at its shift start and repeatedly travels to the nearest unvisited customer that fits the remaining capacity, can start service by the window end, and still allows a return by shift end (ties by customer identifier). Service starts at the later of arrival and the window opening. When no customer fits, the vehicle returns and the next vehicle starts.

## Decisions

| Vehicle id | Visits | Arrivals | Service starts | Return time |
| --- | --- | --- | --- | --- |
| V01 | C003, C002, C004 | 28.324, 102.987, 199.686 | 67, 131, 303 | 361.875 |
| V02 | C001, C005, C006 | 31.547, 94.595, 234.881 | 34, 155, 234.881 | 289.403 |

Arrivals and service starts list the time at each visit, in route order.

## Recomputed measures

| Measure | Value |
| --- | ---: |
| Total travel time | 352.417 |
| Vehicles used | 2 |
| Waiting time | 232.861 |
| Customers served | 6 |
