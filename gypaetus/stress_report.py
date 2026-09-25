"""Readable evidence and plots for the four-candidate stress test."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def write_report(directory):
    out = Path(directory)
    table = pd.read_csv(out / "stress_cases.csv")
    thresholds = pd.read_csv(out / "break_even_limits.csv")
    p = table[table.drag_case == "pessimistic"]
    original_p = p[p.drag_area_model == "original_wing_scaled"]
    mild = table[table.drag_case.isin(["optimistic", "baseline"])]
    expected_pattern = (
        len(table) == 72 and table.design_id.nunique() == 4
        and mild.gate_pass.all() and mild.endurance_pass.all()
        and original_p[original_p.total_installation_loss_pct == 15].gate_pass.all()
        and original_p[original_p.total_installation_loss_pct == 15].endurance_pass.all()
        and original_p[original_p.total_installation_loss_pct == 20].gate_pass.all()
        and not original_p[original_p.total_installation_loss_pct == 20].endurance_pass.any()
        and not original_p[original_p.total_installation_loss_pct == 25].gate_pass.any()
        and not p[p.drag_area_model == "fixed_body_50pct"].gate_pass.any()
    )
    if not expected_pattern:
        raise ValueError("Stress outcomes changed: revise the interpretation before publishing this report template")
    d36 = p[p.design_id == "D0036"]
    rows = []
    for _, row in d36.iterrows():
        rows.append(f"| {'Fixed body, 50% share' if row.fixed_body_fraction else 'Original area scaling'} | "
            f"{row.total_installation_loss_pct:g}% | {row.full_gate_entry_min_excess_n:+.2f} | "
            f"{'Pass' if row.gate_pass else 'Fail'} | {'Pass' if row.endurance_pass else 'Fail'} |")
    limit = thresholds[(thresholds.design_id == "D0036") & (thresholds.drag_case == "pessimistic") &
                       (thresholds.total_installation_loss_pct == 15) & (thresholds.audit_basis == "entry_mass")].iloc[0]
    original = d36[(d36.fixed_body_fraction == 0) & (d36.total_installation_loss_pct == 15)].iloc[0]
    original_masses = p[(p.fixed_body_fraction == 0) & (p.total_installation_loss_pct == 15)]
    candidate_rows = [f"| {r.design_id} | {r.empty_mass_kg:g} + {r.initial_fuel_kg:g} | "
                      f"{r.wing_loading_kg_m2:.1f} | {r.initial_installed_thrust_to_weight:.3f} |"
                      for _, r in original_masses.iterrows()]
    report = "\n".join([
        "# Four-candidate stress test — no design-grid expansion", "",
        "**Conservative robustness verdict: feasible only on the assumed polars, not after installation and reference-area consistency.**", "",
        "This verdict concerns the loss of the original all-three-polar pass: the pessimistic case fails the fixed-body sensitivity at every installation loss tested. "
        "The optimistic and baseline cases still pass both gate and hold for all four candidates. This is not proof of universal infeasibility, nor a geometry-calibrated drag prediction.", "",
        "## Scope", "",
        "Only D0027, D0030, D0033 and D0036 were rerun. Wing area stays 0.08 m², bench rating 600 N, geometric altitude 6,000 m, flight path level. "
        "The original three polar assumptions are retained. Total installation losses are 15%, 20%, 25%. There are 72 targeted evaluations (4 existing designs ×3 polars ×3 losses ×2 area-accounting assumptions); the original grid and its saved results are unchanged.", "",
        "| Candidate | Empty + fuel mass [kg] | Mass loading [kg/m²] | Entry installed T/W at 15% loss |",
        "| --- | --- | ---: | ---: |", *candidate_rows, "",
        "The high-altitude dart description fits this modeled region. Strictly the mass loading spans 237.5–300 kg/m², and the listed T/W values apply at Mach 0.8; they decrease with Mach. "
        "Proving a buildable airplane, or reaching the entry altitude/Mach with this remaining fuel, is a later gate.", "",
        "## Installation accounting", "",
        "The original model already included 15% loss. The tested multipliers are 0.85, 0.80, 0.75 applied once to the uninstalled altitude/Mach map; they are not another 15–25% multiplied into the existing 0.85. "
        "Sea-level static installed thrust is therefore 510, 480, 450 N. At Mach 1 and 6 km it is 269.44, 253.59, 237.74 N. Fuel flow is unchanged by installation loss at fixed throttle.", "",
        "## Fixed-body sensitivity assumption", "",
        "No frontal dimensions or component polars were supplied. The explicit assumption is that 50% of parasite and wave drag at the original 0.12 m² anchor reference belongs to body, inlet and external engine geometry. "
        "That component's equivalent drag area (Cd×A) and Reynolds length remain fixed when wing area is 0.08 m². The other 50% scales with the wing. "
        "Induced drag is still computed from lift and actual wing area; trim CD remains 0.002. The body anchor equivalent chord is sqrt(0.12/3)=0.20 m. "
        "This is a controlled sensitivity allocation, not a measured frontal area, and includes no second inlet/ram-drag subtraction from engine net thrust.", "",
        "```text\nD = q × [(1−f) S CD_wing + f S_anchor CD_body] + D_induced + D_trim\nCD_on_wing = (1−f) CD_wing + f (S_anchor/S) CD_body + CD_induced + CD_trim\n```", "",
        "Changing reference units alone never changes physical drag. This test changes the assumption that non-wing drag shrinks with the wing. "
        "At the anchor geometry it reproduces the original polar, with no added/double-counted body drag. Fixed-body force is tested to remain invariant under changes in wing area and aspect ratio at the same flight condition.", "",
        "## D0036: pessimistic polar", "",
        f"The original integrated minimum margin was **{original.min_excess_thrust_n:+.2f} N**. The comparable full-interval entry-mass margins are below. "
        "They evaluate the complete Mach 0.8–1 interval at the same 24 kg mass, even when the trajectory cannot reach Mach 1.", "",
        "| Area accounting | Total installation loss | Minimum entry-mass T−D [N] | Mach 1 gate | Mach 1.01 / 5 s hold |",
        "| --- | ---: | ---: | --- | --- |", *rows, "",
        "![Targeted margin and outcome evidence](stress_evidence.png)", "",
        "With the 50% fixed-body allocation at 15% loss, the negative D0036 bound remains −39.55 N even at empty mass (a deliberately generous lower-drag bound). "
        "That bound is not a zero-fuel flight: it asks whether eliminating fuel weight could rescue the force balance. It cannot. "
        "Actual failed trajectories stop or time out below Mach 1 and do not continue through the plotted negative full-interval margin. Their sampled minima remain near zero; reporting those as −40 N would be incorrect.", "",
        "## How little extra drag erases the pass?", "",
        f"For D0036 with the original 15% loss, the entry-mass force margin permits only **{limit.permitted_extra_constant_drag_area_m2:.7f} m²** "
        f"of additional equivalent drag area (**{limit.permitted_extra_constant_drag_area_m2*1e4:.2f} cm² of Cd×A**, not physical frontal area), or "
        f"**ΔCD = {limit.permitted_extra_wing_cd:.5f}** on S=0.08 m². "
        f"The critical fixed-body share at the stated 0.12 m² anchor is only **{100*limit.critical_fixed_body_fraction:.2f}%**. "
        "This is a force-only threshold. Adequate crossing time, fuel and hold performance must still be tested.", "",
        "## Five-second hold retained independently", "",
        "With the original area scaling, all four pass gate and hold at 15% loss. At 20%, all four reach Mach 1 but none completes the extension to the five-second Mach 1.01 hold: "
        "the one-kilogram-fuel cases exhaust fuel, and the three-kilogram cases hit the acceleration time limit before the hold starts. At 25%, none reaches Mach 1. "
        "The fixed-body pessimistic cases fail the gate at all three losses. Endurance is not forced to equal gate_pass, and a hold that is never reached is not counted as completed.", "",
        "## Evidence files and reproduction", "",
        "- `stress_cases.csv`: every targeted outcome; trajectory minima and full-interval bounds have separate columns.",
        "- `force_audits.csv.gz`: Mach-resolved entry-mass and dry-mass bounds; these are not trajectories.",
        "- `break_even_limits.csv`: permissible extra drag area/CD and fixed-body fraction at each loss/polar.",
        "- `cases/`: exact inputs, actual trajectories, hold extensions, flags and terminations.",
        "- `stress_inputs.json`: assumptions and source/dependency identities.",
        "- `notebooks/four_candidate_stress.ipynb`: rerunnable targeted notebook in the project.", "",
        "```sh\npython -m gypaetus.stress --output results/stress\npython -m gypaetus.stress_report --output results/stress\npython scripts/execute_notebook.py notebooks/four_candidate_stress.ipynb\n```", "",
    ])
    (out / "REPORT.md").write_text(report)
    return report


def plot_evidence(directory):
    out = Path(directory)
    table = pd.read_csv(out / "stress_cases.csv")
    force = pd.read_csv(out / "force_audits.csv.gz")
    rows = table[(table.design_id == "D0036") & (table.drag_case == "pessimistic")]
    fig, (ax, ax_table) = plt.subplots(1, 2, figsize=(13, 5.8), gridspec_kw={"width_ratios": [1.15, 1]})
    colors = {15: "#007f86", 20: "#bb7023", 25: "#9e405d"}
    for _, row in rows.iterrows():
        curve = force[(force.case_id == row.case_id) & (force.audit_basis == "entry_mass")]
        fixed = row.fixed_body_fraction > 0
        ax.plot(curve.mach, curve.excess_thrust_n, color=colors[row.total_installation_loss_pct],
                linestyle="--" if fixed else "-", lw=2,
                label=f"{'Fixed body' if fixed else 'Original'} · {row.total_installation_loss_pct:g}% loss")
    ax.axhline(0, color="#374151", lw=1.2)
    ax.axhspan(-100, 0, color="#b85025", alpha=.06)
    ax.set(xlabel="Mach", ylabel="Installed thrust − drag [N]", xlim=(.8,1), ylim=(-85,220),
           title="Full interval, same 24 kg mass\nNegative margin is beyond the reachable trajectory")
    ax.grid(alpha=.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, loc="upper right")
    labels = []
    cells = []
    for _, row in rows.iterrows():
        labels.append(f"{'Fixed body' if row.fixed_body_fraction else 'Original'} / {row.total_installation_loss_pct:g}%")
        cells.append([f"{row.full_gate_entry_min_excess_n:+.1f}", "PASS" if row.gate_pass else "FAIL",
                      "PASS" if row.endurance_pass else "FAIL"])
    ax_table.axis("off")
    chart = ax_table.table(cellText=[[label]+cell for label,cell in zip(labels,cells)],
                          colLabels=["Assumption / loss", "Min N", "Gate", "5 s hold"],
                          colWidths=[.48,.17,.17,.18], loc="center", cellLoc="center")
    chart.auto_set_font_size(False)
    chart.set_fontsize(9)
    chart.scale(1,2)
    for (r,c), cell in chart.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if r==0:
            cell.set_facecolor("#e9eef0")
            cell.set_text_props(weight="bold")
        elif c in (2,3):
            cell.set_text_props(color="#007f86" if cell.get_text().get_text()=="PASS" else "#a33d25", weight="bold")
    ax_table.set_title("Actual integration checks\nAll four candidates have this pass/fail pattern")
    fig.suptitle("D0036 stress test — the +19 N margin does not survive\n0.08 m² wing · 6 km · 600 N bench rating · pessimistic polar",fontsize=15)
    fig.subplots_adjust(left=.07,right=.98,bottom=.17,top=.77,wspace=.2)
    fig.text(.5,.025,"Fixed body: assumed 50% share at 0.12 m² anchor; component drag area held fixed.\nLosses are total (15% was already included). Body geometry and drag split are unmeasured.",ha="center",fontsize=10,color="#4b5563")
    fig.savefig(out / "stress_evidence.png",dpi=160)
    return fig


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="results/stress")
    args=parser.parse_args()
    plt.close(plot_evidence(args.output))
    write_report(args.output)
    print(Path(args.output) / "REPORT.md")


if __name__ == "__main__":
    main()
