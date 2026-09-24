# GYPAETUS physics

An assumption-explicit numerical screen for a ≤55 lb, air-breathing aircraft
accelerating from Mach 0.8 to 1.0 without descending. It includes a reproducible
notebook, a Python package, a command-line runner, parameter sweeps, and tests.

**Start with [the assumptions page](docs/assumptions.md).** The engine and drag
maps are illustrative surrogates, not measured aircraft data. A numerical pass
identifies a combination to investigate; it does not establish a buildable design.

## Run it

To browse the existing results without installing anything, open
[the executed notebook](notebooks/design_gate.ipynb),
[the conclusion](results/conclusion.md), or
[the baseline pass/fail plot](results/pass_fail_baseline.png) on GitHub.
GitHub displays saved results; running new calculations requires Python.

To run it on your computer, install Python 3.11 or newer and Git, then:

```sh
git clone https://github.com/jeremiahbeamup11/GYPAETUS-physics.git
cd GYPAETUS-physics
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m gypaetus demo --output results
```

On Windows PowerShell, use `py -m venv .venv` and
`.venv\Scripts\Activate.ps1` for environment creation and activation.
If you already have the project locally, skip cloning and open a terminal in
that project folder. Re-running the demo replaces the example results.

The demo runs one baseline case and 324 cases spanning wing area, bench thrust,
fuel, empty mass, altitude, and all three drag assumptions. The baseline single
case intentionally demonstrates a transonic thrust shortfall. All three altitude
panels use the same axes; a sea-level failure may be caused by the assumed
dynamic-pressure limit even when thrust is sufficient.

```sh
# A different single case, with a prescribed three-degree climb:
python -m gypaetus case --thrust 600 --area 0.08 --gamma 3 --output results/climb
# Run the default grid (the six grid dimensions are specified by SweepGrid):
python -m gypaetus sweep --output results
# Execute the notebook from a fresh kernel, clearing all old outputs first:
python scripts/execute_notebook.py
```

For interactive use, select this environment's Python kernel in
[notebooks/design_gate.ipynb](notebooks/design_gate.ipynb), then **Restart Kernel
and Run All**. The final conclusion is generated from that run's table.
The execution script chooses its own Python executable, so a globally installed
Jupyter kernel cannot silently select a different environment.

Launch the notebook from your activated environment:

```sh
python -m jupyterlab notebooks/design_gate.ipynb
```

In the notebook, edit `Aircraft(...)`, `Engine(...)`, and `Mission(...)` in the
editable-inputs cell, then restart the kernel and run every cell. The single-case
inputs control that example; `SweepGrid(...)` independently specifies the six
dimensions searched in the sweep. Modify that grid to change the search range.

For a single calculation without opening a notebook:

```sh
python -m gypaetus case --empty-mass 20 --fuel 3 --area 0.08 --thrust 600 --altitude 6000 --drag pessimistic --output results/my-design
```

Here mass and fuel are kg, wing area is m², thrust is the uninstalled sea-level
static rating in N, and altitude is m. Read the resulting `summary.json` and
`single_case.png` inside `results/my-design/single_case/`. A `gate_pass: true`
means the Mach 1 screen passed under the selected assumptions; the separate
`endurance_pass` reports whether the Mach 1.01 hold also succeeded.

## Outputs

| Output | Meaning |
| --- | --- |
| `results/single_case/inputs.json` | Exact single-case inputs |
| `results/single_case/summary.json` | Individual checks, termination reason, review flags |
| `results/single_case/trajectory.csv` | Integrated gate trajectory, SI columns |
| `results/single_case/hold_trajectory.csv` | Optional Mach 1.01 acceleration and level hold, when attempted |
| `results/single_case/single_case.png` | Thrust/drag, Mach/time, mass/fuel/time, specific excess power |
| `results/all_cases.csv` | Every tested case, including failures |
| `results/passing_cases.csv` | Gate passes with their drag assumptions and endurance outcomes |
| `results/all_polar_candidates.csv` | One baseline row per combination passing all three polars |
| `results/sweep_inputs.json` | Grid, shared inputs, and every drag polar |
| `results/pass_fail_*.png` | T/W versus W/S, one panel per altitude and one figure per drag case |
| `results/wave_drag_cases.png` | Assumed optimistic/baseline/pessimistic drag rise |
| `results/conclusion.md` | Short generated design-gate answer |

Checked-in results are an example run, not measured performance. `time_to_mach_1_s`
and `fuel_at_mach_1_kg` are blank for failed gates; inspect `elapsed_s` and
`final_mach` for their stopping points. Empty endurance outcomes mean not evaluated.

## Change a design or grid

```python
from gypaetus import Aircraft, Engine, Mission, DRAG_CASES, run_case
from gypaetus.sweep import SweepGrid, run_sweep, save_sweep

case = run_case(
    Aircraft(empty_mass_kg=20, fuel_mass_kg=3, wing_area_m2=0.08),
    Engine(sea_level_static_thrust_n=600, installed_factor=0.85),
    DRAG_CASES['pessimistic'],
    Mission(altitude_m=6000, gamma_deg=0),
)
print(case.summary)

grid = SweepGrid(wing_areas_m2=(0.08, 0.12), rated_thrusts_n=(450, 600))
table = run_sweep(grid)
save_sweep(table, 'results/custom')
```

The three propulsion classes share `Engine.performance(Mach, altitude, throttle)`.
Replace that method with a validated map before making a hardware claim. Engine
mass must already be included in empty mass; the sweep does not infer a credible
engine mass from its thrust rating. Reject unrealistic mass/thrust pairings using
actual hardware data. CFD, wind-tunnel data, inlet recovery, engine operating
limits, flight trim, structure, and flutter are not supplied by this repository.

## Layout

- `gypaetus/atmosphere.py`, `constants.py`: atmosphere and SI conversions.
- `gypaetus/models.py`: mass, lift, drag, engine and mission parameters.
- `gypaetus/simulation.py`: equations of motion, events, checks and endurance.
- `gypaetus/sweep.py`, `plots.py`, `cli.py`: reproducible results and figures.
- `gypaetus/estimates.py`: indicative takeoff and landing ground rolls.
- `tests/`: reference values, physical identities, failure cases and convergence.
- [Model sources and validation limits](docs/sources.md).

## Automated checks on GitHub

[docs/ci/verify.yml](docs/ci/verify.yml) is an inactive GitHub Actions template
that runs the tests and executes the notebook. To activate it, move it to
`.github/workflows/verify.yml` and push with a GitHub credential that has
permission to manage workflows. The publishing credential used for the initial
upload lacks that permission; the local test and notebook commands work normally.
