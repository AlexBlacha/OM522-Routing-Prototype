# Actual issues found during development

These entries document observations during implementation, the resulting corrections, and the evidence used to validate them.

## Input types: decimal conversion accepted fractional demand

The initial exploratory audit converted every numeric CSV field with `float(...)`. That reads a value such as `7.5` successfully even for a published integer column. It therefore did not enforce the input contract.

The project loader now reads text through Polars and explicitly validates string, integer and general-number fields. The fractional-demand regression test changes a copied case, expects an error naming `customers.csv` and `demand`, and ensures the invalid value cannot be silently accepted. The original input data are never edited.

**Evidence:** `tests/test_routing.py:test_fractional_integer_is_rejected`; the rejection is also demonstrated in `docs/type_validation_evidence.txt`.

## Marimo cells: underscore-prefixed names are local

The first notebook imported the helper as `_convert` and referred to it in another cell. Notebook structure checking passed, but an executed HTML export failed with:

> Name `_convert` is not defined. Names prefixed with an underscore are local to the cell that defines them.

The import was changed to `from routing.data import _convert as validate_value`, and the dependent cell now uses the public alias. The notebook was executed again after the correction. This demonstrates why structural checks alone do not establish that a notebook runs.

**Evidence:** the corrected import and final walkthrough cell in `app.py`; successful executed export and browser interaction after repair.

## Output handling: stale successful decisions

During review, we identified the risk of reusing an output folder: a later unsuccessful run could leave an earlier successful `decision.json` behind. The CLI now removes only its own previous generated files before loading/solving. Tests place a stale decision in the output folder, then verify that infeasible and malformed runs leave no decision file.

**Evidence:** `test_02_edge_case_reports_no_feasible_decision_and_no_stale_file` and `test_03_missing_required_column_rejected_with_file_and_column`.
