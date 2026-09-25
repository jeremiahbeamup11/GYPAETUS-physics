"""Targeted installation/reference-area audit of four existing designs only.

The fixed-body allocation is an explicit sensitivity assumption, not measured geometry.
Run: python -m gypaetus.stress --output results/stress
"""

from dataclasses import asdict, dataclass, replace
import argparse
import json
import math
import gzip
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .atmosphere import atmosphere
from .cli import save_case
from .models import Aircraft, DragPolar, Engine, Mission, DRAG_CASES, aerodynamic_state
from .provenance import provenance
from .simulation import run_case


CANDIDATES = {"D0027": (18.0, 1.0), "D0030": (21.0, 1.0),
              "D0033": (18.0, 3.0), "D0036": (21.0, 3.0)}
INSTALLATION_FACTORS = (0.85, 0.80, 0.75)


@dataclass(frozen=True)
class FixedBodyPolar(DragPolar):
    """Retain body/inlet/external-engine equivalent drag area as wing area changes.

    At the anchor area and aspect ratio, total drag equals the original polar.
    Fraction f is allocated to fixed non-wing geometry; (1-f) remains wing-scaled.
    No frontal dimensions were supplied: Cd*A, not a fictional physical diameter,
    is retained. The body Reynolds length is frozen at the anchor equivalent chord.
    External drag is separate from the engine's net-thrust installation loss.
    """
    anchor_area_m2: float = 0.12
    anchor_aspect_ratio: float = 3.0
    fixed_body_fraction: float = 0.50

    def __post_init__(self):
        super().__post_init__()
        if self.anchor_area_m2 <= 0 or self.anchor_aspect_ratio <= 0:
            raise ValueError("Body anchor area and aspect ratio must be positive")
        if not 0 <= self.fixed_body_fraction <= 1:
            raise ValueError("Fixed body fraction must be in [0, 1]")

    def drag_areas(self, mach, reynolds, aircraft):
        """Component Cd*A [m²]; induced and trim drag remain in the main model."""
        f = self.fixed_body_fraction
        body_reynolds = reynolds * math.sqrt(self.anchor_area_m2 / self.anchor_aspect_ratio) / aircraft.chord_m
        return {
            "wing_parasite_drag_area_m2": (1-f) * aircraft.wing_area_m2 * super().parasite_cd(reynolds, aircraft),
            "body_parasite_drag_area_m2": f * self.anchor_area_m2 * super().parasite_cd(body_reynolds, aircraft),
            "wing_wave_drag_area_m2": (1-f) * aircraft.wing_area_m2 * super().wave_cd(mach, aircraft),
            "body_wave_drag_area_m2": f * self.anchor_area_m2 * super().wave_cd(mach, aircraft),
        }

    def parasite_cd(self, reynolds, aircraft):
        f = self.fixed_body_fraction
        body_reynolds = reynolds * math.sqrt(self.anchor_area_m2 / self.anchor_aspect_ratio) / aircraft.chord_m
        return ((1-f) * super().parasite_cd(reynolds, aircraft)
                + f * self.anchor_area_m2 / aircraft.wing_area_m2 * super().parasite_cd(body_reynolds, aircraft))

    def wave_cd(self, mach, aircraft):
        return (1-self.fixed_body_fraction + self.fixed_body_fraction * self.anchor_area_m2 / aircraft.wing_area_m2) * super().wave_cd(mach, aircraft)


def fixed_body_polar(polar, fraction=0.50):
    return FixedBodyPolar(**asdict(polar), fixed_body_fraction=fraction)


def force_audit(aircraft, engine, polar, mission, mass_kg, count=1001, target=1.0):
    """Full-interval algebraic audit at declared constant mass, NOT a flight path."""
    atm = atmosphere(mission.altitude_m)
    rows = []
    for mach in np.linspace(0.8, target, count):
        aero = aerodynamic_state(aircraft, polar, mach * atm.sound_speed_m_s,
                                 mission.altitude_m, mass_kg)
        thrust, _ = engine.performance(mach, mission.altitude_m, mission.throttle)
        areas = polar.drag_areas(mach, aero["reynolds"], aircraft) if isinstance(polar, FixedBodyPolar) else {}
        rows.append(dict(**aero, **areas, audit_mass_kg=mass_kg, thrust_n=thrust,
                         excess_thrust_n=thrust-aero["drag_n"]))
    return pd.DataFrame(rows)


def break_even_body_fraction(aircraft, engine, polar, mission, mass_kg):
    """Largest f allowed by all force samples, with body drag linear in f.

    Negative f means the original polar already lacks thrust. This is a force-only
    boundary, not proof of adequate fuel, traversal time, or the supersonic hold.
    """
    zero = force_audit(aircraft, engine, fixed_body_polar(polar, 0), mission, mass_kg)
    full = force_audit(aircraft, engine, fixed_body_polar(polar, 1), mission, mass_kg)
    extra_drag = full.drag_n - zero.drag_n
    permitted = (zero.excess_thrust_n - mission.force_margin_n) / extra_drag
    finite = permitted[extra_drag > 0]
    if finite.empty:
        raise ValueError("Anchor must produce a positive added drag area for this audit")
    index = finite.idxmin()
    return float(finite.loc[index]), float(zero.loc[index, "mach"])


def run_stress(output="results/stress"):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    mission = Mission(altitude_m=6000, hold_mach=1.01, hold_seconds=5)
    rows, audits, thresholds = [], [], []
    for design_id, (empty, fuel) in CANDIDATES.items():
        aircraft = Aircraft(empty_mass_kg=empty, fuel_mass_kg=fuel, wing_area_m2=0.08)
        for installation_factor in INSTALLATION_FACTORS:
            engine = Engine(sea_level_static_thrust_n=600, installed_factor=installation_factor)
            for polar_name, original in DRAG_CASES.items():
                for model, polar in (("original_wing_scaled", original),
                                     ("fixed_body_50pct", fixed_body_polar(original))):
                    result = run_case(aircraft, engine, polar, mission)
                    case_id = f"{design_id}_{polar_name}_{model}_loss{round(100*(1-installation_factor))}"
                    save_case(result, out / "cases" / case_id)
                    # Keep dense numerical evidence compact without discarding failed paths.
                    for name in ("trajectory.csv", "hold_trajectory.csv"):
                        path = out / "cases" / case_id / name
                        if path.exists():
                            with path.open("rb") as src, gzip.open(str(path)+".gz", "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            path.unlink()
                        elif Path(str(path)+".gz").exists():
                            Path(str(path)+".gz").unlink()
                    entry = force_audit(aircraft, engine, polar, mission, aircraft.total_mass_kg)
                    # Generous lower-drag bound: thrust with dry mass, NOT an operable zero-fuel flight.
                    dry = force_audit(aircraft, engine, polar, mission, aircraft.empty_mass_kg)
                    for name, curve in (("entry_mass", entry), ("dry_mass_lower_drag_bound", dry)):
                        curve["case_id"] = case_id
                        curve["audit_basis"] = name
                        audits.append(curve)
                    hold_attempted = (not result.hold_trajectory.empty and
                                      bool((result.hold_trajectory.phase == "level_hold").any()))
                    rows.append(dict(case_id=case_id, design_id=design_id, drag_area_model=model,
                        total_installation_loss_pct=round(100*(1-installation_factor)),
                        installed_factor=installation_factor, fixed_body_fraction=getattr(polar, "fixed_body_fraction", 0),
                        wing_loading_kg_m2=aircraft.total_mass_kg/aircraft.wing_area_m2,
                        full_gate_entry_min_excess_n=float(entry.excess_thrust_n.min()),
                        full_gate_dry_bound_min_excess_n=float(dry.excess_thrust_n.min()),
                        mach1_entry_cd=float(entry.cd_total.iloc[-1]),
                        mach1_entry_drag_area_m2=float(entry.cd_total.iloc[-1]*aircraft.wing_area_m2),
                        mach1_thrust_n=float(entry.thrust_n.iloc[-1]),
                        level_hold_attempted=hold_attempted,
                        **result.summary))
                # Analytic body-share threshold, not an enlarged airframe grid.
                for basis, mass in (("entry_mass", aircraft.total_mass_kg), ("dry_mass_lower_drag_bound", aircraft.empty_mass_kg)):
                    fraction, mach = break_even_body_fraction(aircraft, engine, original, mission, mass)
                    ref = force_audit(aircraft, engine, original, mission, mass)
                    extra_area = ((ref.excess_thrust_n-mission.force_margin_n)/ref.q_pa).min()
                    thresholds.append(dict(design_id=design_id, drag_case=polar_name,
                        total_installation_loss_pct=round(100*(1-installation_factor)), audit_basis=basis,
                        critical_fixed_body_fraction=fraction, controlling_mach=mach,
                        permitted_extra_constant_drag_area_m2=float(extra_area),
                        permitted_extra_wing_cd=float(extra_area/aircraft.wing_area_m2)))
    table = pd.DataFrame(rows)
    table.to_csv(out / "stress_cases.csv", index=False)
    pd.concat(audits, ignore_index=True).to_csv(out / "force_audits.csv.gz", index=False, compression="gzip")
    obsolete = out / "force_audits.csv"
    if obsolete.exists():
        obsolete.unlink()
    pd.DataFrame(thresholds).to_csv(out / "break_even_limits.csv", index=False)
    inputs = dict(candidates=CANDIDATES, wing_area_m2=0.08, rated_thrust_n=600,
        mission=asdict(mission), total_installation_factors=INSTALLATION_FACTORS,
        body_area_assumption=asdict(fixed_body_polar(DRAG_CASES["pessimistic"])),
        geometry_status="No actual frontal area or component polar supplied; fixed equivalent drag area allocation is a sensitivity assumption.",
        original_grid_status="Unchanged; only D0027/D0030/D0033/D0036 evaluated.",
        provenance=provenance())
    (out / "stress_inputs.json").write_text(json.dumps(inputs, indent=2)+"\n")
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/stress")
    args = parser.parse_args()
    table = run_stress(args.output)
    print(table.groupby(["drag_case", "drag_area_model", "total_installation_loss_pct"])[["gate_pass", "endurance_pass"]].sum().to_string())


if __name__ == "__main__":
    main()
