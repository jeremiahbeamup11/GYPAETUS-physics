"""Cartesian parameter sweeps with per-design drag-sensitivity classifications."""

from dataclasses import asdict, dataclass, replace
from itertools import product
import json
from pathlib import Path

import pandas as pd

from .models import Aircraft, Engine, Mission, DRAG_CASES
from .simulation import run_case
from .provenance import provenance


@dataclass(frozen=True)
class SweepGrid:
    wing_areas_m2: tuple = (0.08, 0.12, 0.18)
    rated_thrusts_n: tuple = (300.0, 450.0, 600.0)
    fuel_masses_kg: tuple = (1.0, 3.0)
    empty_masses_kg: tuple = (18.0, 21.0)
    altitudes_m: tuple = (0.0, 3000.0, 6000.0)
    drag_cases: tuple = ("optimistic", "baseline", "pessimistic")

    def __post_init__(self):
        for key, values in asdict(self).items():
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{key} must contain distinct, nonempty values")
        if any(name not in DRAG_CASES for name in self.drag_cases):
            raise ValueError("Unknown drag case")


def run_sweep(grid: SweepGrid = SweepGrid(), aircraft: Aircraft = Aircraft(),
              engine: Engine = Engine(), mission: Mission = Mission(),
              check_endurance: bool = True):
    rows = []
    combinations = product(grid.wing_areas_m2, grid.rated_thrusts_n, grid.fuel_masses_kg,
                           grid.empty_masses_kg, grid.altitudes_m)
    for index, (area, thrust, fuel, empty, altitude) in enumerate(combinations):
        a = replace(aircraft, wing_area_m2=area, fuel_mass_kg=fuel, empty_mass_kg=empty)
        e = replace(engine, sea_level_static_thrust_n=thrust)
        m = replace(mission, altitude_m=altitude)
        for name in grid.drag_cases:
            case = run_case(a, e, DRAG_CASES[name], m, check_endurance=check_endurance)
            rows.append(dict(design_id=f"D{index + 1:04d}", **case.summary))
    results = pd.DataFrame(rows)
    classes = {}
    for design_id, group in results.groupby("design_id"):
        passes = dict(zip(group.drag_case, group.gate_pass))
        if set(passes) != set(DRAG_CASES):
            label = "incomplete_drag_sensitivity"
        elif all(passes.values()):
            label = "passes_all_three_assumed_polars"
        elif passes["optimistic"] and not passes["baseline"] and not passes["pessimistic"]:
            label = "optimistic_only"
        elif passes["baseline"]:
            label = "baseline_pass_sensitive"
        elif not any(passes.values()):
            label = "fails_all_three"
        else:
            label = "mixed_sensitivity"
        classes[design_id] = label
    results["drag_sensitivity"] = results.design_id.map(classes)
    results.attrs["inputs"] = {
        "grid": asdict(grid), "aircraft": asdict(aircraft), "engine": asdict(engine),
        "mission": asdict(mission), "check_endurance": check_endurance,
        "drag_polars": {k: asdict(v) for k, v in DRAG_CASES.items()},
        "provenance": provenance(),
    }
    return results


def conclusion(results: pd.DataFrame) -> str:
    designs = results.drop_duplicates("design_id")
    counts = designs.drag_sensitivity.value_counts()
    n = len(results)
    passed = int(results.gate_pass.sum())
    held = int(results.endurance_pass.eq(True).sum())
    hold_note = (f"{held} cases also completed the configured supersonic hold."
                 if results.endurance_pass.notna().any() else "Endurance was not evaluated.")
    return (f"Under the recorded assumptions, {passed} of {n} drag-specific cases pass the Mach 0.8→1.0 gate. "
            f"Of {len(designs)} distinct parameter combinations, "
            f"{counts.get('passes_all_three_assumed_polars', 0)} pass all three assumed drag polars, "
            f"{counts.get('optimistic_only', 0)} pass only the optimistic polar, and "
            f"{counts.get('fails_all_three', 0)} fail all three. {hold_note} "
            "An optimistic-only pass is not a supported design claim. Even an all-polar pass is a numerical "
            "candidate: the engine/drag maps, installed engine mass, structural limits, flutter, and trim/control "
            "remain unvalidated. These results do not establish that a buildable aircraft meets the gate.")


def save_sweep(results, directory):
    if "inputs" not in results.attrs:
        raise ValueError("Missing run metadata: save the DataFrame returned by run_sweep")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    results.to_csv(directory / "all_cases.csv", index=False)
    results[results.gate_pass].to_csv(directory / "passing_cases.csv", index=False)
    results[(results.drag_case == "baseline") & (results.drag_sensitivity == "passes_all_three_assumed_polars")].to_csv(
        directory / "all_polar_candidates.csv", index=False)
    inputs = results.attrs["inputs"]
    (directory / "sweep_inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (directory / "conclusion.md").write_text(conclusion(results) + "\n")
