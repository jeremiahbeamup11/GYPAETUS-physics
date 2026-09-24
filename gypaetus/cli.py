"""Run from a clean process: python -m gypaetus demo --output results."""

import argparse
import json
from pathlib import Path

from .estimates import runway_estimates
from .models import Aircraft, Engine, Mission, DRAG_CASES
from .simulation import run_case
from .sweep import SweepGrid, conclusion, run_sweep, save_sweep
from .provenance import provenance


def save_case(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result.trajectory.to_csv(directory / "trajectory.csv", index=False)
    if not result.hold_trajectory.empty:
        result.hold_trajectory.to_csv(directory / "hold_trajectory.csv", index=False)
    elif (directory / "hold_trajectory.csv").exists():
        (directory / "hold_trajectory.csv").unlink()
    (directory / "inputs.json").write_text(json.dumps(result.inputs(), indent=2) + "\n")
    (directory / "provenance.json").write_text(json.dumps(provenance(), indent=2) + "\n")
    (directory / "summary.json").write_text(json.dumps(result.summary, indent=2, allow_nan=False) + "\n")
    (directory / "runway_estimates.json").write_text(json.dumps(
        runway_estimates(result.aircraft, result.engine, result.polar), indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="GYPAETUS transonic numerical design gate")
    parser.add_argument("command", choices=["case", "sweep", "demo"], nargs="?", default="demo")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--altitude", type=float, default=3000, help="Geometric altitude [m]")
    parser.add_argument("--thrust", type=float, default=450, help="Sea-level static bench thrust [N]")
    parser.add_argument("--area", type=float, default=0.12, help="Wing reference area [m²]")
    parser.add_argument("--empty-mass", type=float, default=20, help="Includes all installed hardware [kg]")
    parser.add_argument("--fuel", type=float, default=3, help="Usable fuel at Mach 0.8 [kg]")
    parser.add_argument("--drag", choices=list(DRAG_CASES), default="baseline")
    parser.add_argument("--gamma", type=float, default=0, help="Prescribed climb angle [degrees]")
    parser.add_argument("--propulsion", choices=["turbojet", "turbofan", "ramjet_assist"], default="turbojet")
    args = parser.parse_args()
    # Headless output also works in CI. Import pyplot only after selecting backend.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .plots import plot_case, plot_drag_cases, plot_pass_fail

    aircraft = Aircraft(empty_mass_kg=args.empty_mass, fuel_mass_kg=args.fuel, wing_area_m2=args.area)
    engine = Engine(sea_level_static_thrust_n=args.thrust, propulsion_class=args.propulsion)
    mission = Mission(altitude_m=args.altitude, gamma_deg=args.gamma)
    if args.command in ("case", "demo"):
        result = run_case(aircraft, engine, DRAG_CASES[args.drag], mission)
        save_case(result, args.output / "single_case")
        plt.close(plot_case(result, args.output / "single_case"))
        plt.close(plot_drag_cases(aircraft, args.output))
        print(json.dumps(result.summary, indent=2))
    if args.command in ("sweep", "demo"):
        grid = SweepGrid()
        results = run_sweep(grid, aircraft, engine, mission)
        save_sweep(results, args.output)
        for name in grid.drag_cases:
            plt.close(plot_pass_fail(results, args.output, name))
        print(conclusion(results))
