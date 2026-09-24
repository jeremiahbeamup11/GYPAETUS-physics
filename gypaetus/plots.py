"""Saved, labeled scientific plots; projections never imply a completed trajectory."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .simulation import reference_curve


def _style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.2, "figure.dpi": 130,
                         "savefig.facecolor": "white"})


def plot_case(result, directory=None):
    _style()
    h = result.trajectory
    reference = reference_curve(result)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    ax = axes[0, 0]
    ax.plot(reference.mach, reference.thrust_n, "--", color="#9ca3af", label="Thrust at entry conditions")
    ax.plot(reference.mach, reference.drag_n, ":", color="#6b7280", label="Drag at entry mass/altitude")
    ax.plot(h.mach, h.thrust_n, color="#007f86", label="Thrust on trajectory")
    ax.plot(h.mach, h.drag_n, color="#c55a25", label="Drag on trajectory")
    ax.set(xlabel="Mach", ylabel="Force [N]", title="Thrust and drag", xlim=(0.8, 1.0))
    ax.legend(fontsize=8)
    axes[0, 1].plot(h.time_s, h.mach, color="#007f86")
    axes[0, 1].axhline(1, color="#6b7280", linestyle=":")
    axes[0, 1].set(xlabel="Time since Mach 0.8 [s]", ylabel="Mach", title="Integrated acceleration")
    axes[1, 0].plot(h.time_s, h.mass_kg, label="Total mass", color="#007f86")
    axes[1, 0].plot(h.time_s, h.fuel_kg, label="Fuel", color="#c55a25")
    axes[1, 0].set(xlabel="Time since Mach 0.8 [s]", ylabel="Mass [kg]", title="Mass and usable fuel")
    axes[1, 0].legend()
    axes[1, 1].plot(reference.mach, reference.specific_excess_power_m_s, ":", color="#6b7280", label="At entry mass/altitude")
    axes[1, 1].plot(h.mach, h.specific_excess_power_m_s, color="#007f86", label="Trajectory")
    axes[1, 1].axhline(0, color="#c55a25", linestyle="--")
    if result.mission.gamma_deg:
        axes[1, 1].plot(h.mach, h.climb_rate_m_s, label="Power used to climb", color="#b29228")
    axes[1, 1].set(xlabel="Mach", ylabel="Specific excess power [m/s]", title="(T − D)V / W", xlim=(0.8, 1.0))
    axes[1, 1].legend(fontsize=8)
    if not result.hold_trajectory.empty:
        hold = result.hold_trajectory
        axes[0, 1].plot(hold.time_s, hold.mach, "--", color="#7865ad", label="Hold extension")
        axes[0, 1].legend(fontsize=8)
        axes[1, 0].plot(hold.time_s, hold.mass_kg, "--", color="#007f86")
        axes[1, 0].plot(hold.time_s, hold.fuel_kg, "--", color="#c55a25")
    outcome = "PASS" if result.summary["gate_pass"] else "FAIL"
    fig.suptitle(f"GYPAETUS  /  {result.polar.name}  /  {outcome}\n"
                 f"{result.mission.altitude_m:,.0f} m · {result.aircraft.total_mass_kg:g} kg · "
                 f"{result.engine.sea_level_static_thrust_n:g} N bench rating · illustrative models", fontsize=14)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(directory) / "single_case.png")
    return fig


def plot_pass_fail(results, directory=None, drag_case="baseline"):
    """One panel per altitude. Shared axes; mixed overlapping cases shown explicitly."""
    _style()
    subset = results[results.drag_case == drag_case]
    if subset.empty:
        raise ValueError(f"No results for drag case {drag_case}")
    altitudes = sorted(subset.altitude_m.unique())
    fig, axes = plt.subplots(1, len(altitudes), figsize=(4.5 * len(altitudes), 4.6),
                             squeeze=False, sharex=True, sharey=True, layout="constrained")
    styles = {"pass": ("#007f86", "o", "All coincident cases pass"),
              "fail": ("#c55a25", "x", "All coincident cases fail"),
              "mixed": ("#b29228", "D", "Mixed at same coordinates")}
    for altitude, ax in zip(altitudes, axes[0]):
        at_altitude = subset[subset.altitude_m == altitude]
        grouped = at_altitude.groupby(["wing_loading_n_m2", "initial_installed_thrust_to_weight"]).gate_pass.agg(["all", "any"]).reset_index()
        for state, (color, marker, label) in styles.items():
            mask = grouped["all"] if state == "pass" else (~grouped["any"] if state == "fail" else grouped["any"] & ~grouped["all"])
            part = grouped[mask]
            ax.scatter(part.wing_loading_n_m2, part.initial_installed_thrust_to_weight,
                       color=color, marker=marker, s=45, label=label)
        ax.set(title=f"{altitude:,.0f} m", xlabel="Initial wing loading W/S [N/m²]")
    axes[0, 0].set_ylabel("Installed T/W at Mach 0.8")
    axes[0, -1].legend(fontsize=7, loc="best")
    fig.suptitle(f"{drag_case.capitalize()} gate map  /  illustrative models\nAll checks included, including assumed q limit", fontsize=13)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(directory) / f"pass_fail_{drag_case}.png")
    return fig


def plot_drag_cases(aircraft, directory=None):
    from .models import DRAG_CASES
    _style()
    fig, ax = plt.subplots(figsize=(7.5, 4), layout="constrained")
    machs = np.linspace(0.65, 1.15, 300)
    for name, polar in DRAG_CASES.items():
        ax.plot(machs, [polar.wave_cd(m, aircraft) for m in machs], label=name)
    ax.axvspan(0.8, 1, color="#007f86", alpha=0.07)
    ax.set(xlabel="Mach", ylabel="Wave drag coefficient [wing-area reference]",
           title="Assumed wave-drag sensitivity — requires calibration")
    ax.legend()
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(directory) / "wave_drag_cases.png")
    return fig
