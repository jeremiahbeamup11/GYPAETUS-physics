"""Explicit, uncalibrated engineering surrogates. See docs/assumptions.md."""

from dataclasses import dataclass, fields
import math

import numpy as np

from .atmosphere import atmosphere
from .constants import G0


def finite_fields(obj):
    for field in fields(obj):
        value = getattr(obj, field.name)
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(f"{field.name} must be finite")


@dataclass(frozen=True)
class Aircraft:
    empty_mass_kg: float = 20.0  # includes installed engine, tanks, avionics, all hardware
    fuel_mass_kg: float = 3.0  # usable fuel remaining at Mach 0.8
    wing_area_m2: float = 0.12
    aspect_ratio: float = 3.0
    oswald_efficiency: float = 0.75
    cl_limit: float = 0.60  # assumed transonic buffet/stall bound
    cl_max_landing: float = 1.20
    trim_cd: float = 0.002
    slenderness: float = 10.0  # length / maximum diameter
    area_rule_factor: float = 1.0  # manual sensitivity multiplier, NOT a geometry solver
    q_limit_pa: float = 65_000.0  # assumed, NOT a structural allowable
    flutter_review_q_pa: float = 40_000.0
    flutter_review_mach: float = 0.85

    def __post_init__(self):
        finite_fields(self)
        for name in ("empty_mass_kg", "wing_area_m2", "aspect_ratio", "cl_limit", "cl_max_landing",
                     "slenderness", "area_rule_factor", "q_limit_pa", "flutter_review_q_pa", "flutter_review_mach"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fuel_mass_kg < 0 or self.trim_cd < 0:
            raise ValueError("Fuel and trim drag must be nonnegative")
        if not 0 < self.oswald_efficiency <= 1:
            raise ValueError("Oswald efficiency must be in (0, 1]")

    @property
    def total_mass_kg(self):
        return self.empty_mass_kg + self.fuel_mass_kg

    @property
    def chord_m(self):
        return math.sqrt(self.wing_area_m2 / self.aspect_ratio)


@dataclass(frozen=True)
class DragPolar:
    name: str = "baseline"
    cd0: float = 0.022
    wave_peak_cd: float = 0.035
    wave_onset_mach: float = 0.78
    wave_peak_mach: float = 1.02
    wave_width_mach: float = 0.16
    reynolds_reference: float = 4e6
    viscous_fraction: float = 0.65

    def __post_init__(self):
        finite_fields(self)
        if self.cd0 < 0 or self.wave_peak_cd < 0:
            raise ValueError("Drag coefficients must be nonnegative")
        if not 0 <= self.wave_onset_mach < self.wave_peak_mach:
            raise ValueError("Wave peak must follow nonnegative onset Mach")
        if self.wave_width_mach <= 0 or self.reynolds_reference <= 0:
            raise ValueError("Wave width and reference Reynolds number must be positive")
        if not 0 <= self.viscous_fraction <= 1:
            raise ValueError("Viscous fraction must be in [0, 1]")

    def wave_cd(self, mach: float, aircraft: Aircraft) -> float:
        if mach <= self.wave_onset_mach:
            shape = 0.0
        elif mach <= self.wave_peak_mach:
            x = (mach - self.wave_onset_mach) / (self.wave_peak_mach - self.wave_onset_mach)
            shape = x * x * (3 - 2 * x)
        else:
            shape = 0.65 + 0.35 * math.exp(-((mach - self.wave_peak_mach) / self.wave_width_mach) ** 2)
        return self.wave_peak_cd * shape * aircraft.area_rule_factor * (10 / aircraft.slenderness) ** 2

    def parasite_cd(self, reynolds: float, aircraft: Aircraft) -> float:
        """Wing-referenced parasite coefficient; subclasses can retain fixed body drag area."""
        return self.cd0 * (1 - self.viscous_fraction + self.viscous_fraction * (reynolds / self.reynolds_reference) ** -0.2)

    def profile_drag_areas(self, mach, reynolds, aircraft):
        """Dimensional Cd*A interface; keeps fixed geometry independent of Sref."""
        return dict(parasite_drag_area_m2=aircraft.wing_area_m2 * self.parasite_cd(reynolds, aircraft),
                    wave_drag_area_m2=aircraft.wing_area_m2 * self.wave_cd(mach, aircraft))


DRAG_CASES = {
    "optimistic": DragPolar("optimistic", 0.016, 0.018, 0.82),
    "baseline": DragPolar(),
    "pessimistic": DragPolar("pessimistic", 0.030, 0.060, 0.74),
}


@dataclass(frozen=True)
class Engine:
    sea_level_static_thrust_n: float = 450.0
    tsfc_kg_n_s: float = 4e-5
    installed_factor: float = 0.85
    altitude_exponent: float = 0.75
    propulsion_class: str = "turbojet"
    assist_fraction: float = 0.30

    def __post_init__(self):
        finite_fields(self)
        if self.sea_level_static_thrust_n <= 0 or self.tsfc_kg_n_s <= 0:
            raise ValueError("Rated thrust and TSFC must be positive")
        if not 0 < self.installed_factor <= 1 or self.altitude_exponent < 0 or self.assist_fraction < 0:
            raise ValueError("Invalid installation, altitude, or assist factor")
        if self.propulsion_class not in ("turbojet", "turbofan", "ramjet_assist"):
            raise ValueError("Use turbojet, turbofan, or ramjet_assist (turbine core); ramjet alone is unsupported")

    def performance(self, mach: float, altitude_m: float, throttle: float = 1.0):
        """Return installed net thrust [N], fuel flow [kg/s]. No extrapolation."""
        if not math.isfinite(mach) or not 0 <= mach <= 1.2:
            raise ValueError("Engine surrogate Mach domain is [0, 1.2]")
        if not math.isfinite(throttle) or not 0 <= throttle <= 1:
            raise ValueError("Throttle must be in [0, 1]")
        atm = atmosphere(altitude_m)
        sigma = atm.density_kg_m3 / atmosphere(0).density_kg_m3
        knots = [0, 0.4, 0.8, 1.0, 1.2]
        factors = [1, 0.97, 0.90, 0.84, 0.79]
        if self.propulsion_class == "turbofan":
            factors = [1, 0.90, 0.76, 0.66, 0.58]
        speed_factor = float(np.interp(mach, knots, factors))
        core = self.sea_level_static_thrust_n * sigma ** self.altitude_exponent * speed_factor * throttle
        assist = 0.0
        if self.propulsion_class == "ramjet_assist":
            assist = self.sea_level_static_thrust_n * sigma * self.assist_fraction * max(0.0, min(1.0, (mach - 0.9) / 0.3)) * throttle
        # TSFC is referenced to UNINSTALLED net thrust. Installation reduces thrust, not fuel flow.
        tsfc = self.tsfc_kg_n_s * (1 + 0.15 * mach) * math.sqrt(atm.temperature_k / 288.15) * (1 + 0.2 * (1 - throttle))
        return self.installed_factor * (core + assist), tsfc * (core + 1.5 * assist)


@dataclass(frozen=True)
class Mission:
    altitude_m: float = 3_000.0
    start_mach: float = 0.8
    target_mach: float = 1.0
    gamma_deg: float = 0.0
    throttle: float = 1.0
    max_time_s: float = 120.0
    max_step_s: float = 0.25
    hold_mach: float = 1.01
    hold_seconds: float = 5.0
    force_margin_n: float = 0.01

    def __post_init__(self):
        finite_fields(self)
        atmosphere(self.altitude_m)
        if self.start_mach != 0.8 or self.target_mach != 1.0:
            raise ValueError("This design gate is fixed at Mach 0.8 → 1.0")
        if not 0 <= self.gamma_deg <= 10:
            raise ValueError("Flight path angle must be 0–10 degrees; dives are disallowed")
        if not 0 < self.throttle <= 1 or self.max_time_s <= 0 or self.max_step_s <= 0:
            raise ValueError("Throttle, time and step size must be positive; throttle ≤ 1")
        if not 1 < self.hold_mach <= 1.15 or self.hold_seconds < 0 or self.force_margin_n <= 0:
            raise ValueError("Hold Mach must be (1, 1.15], duration ≥ 0 and force margin > 0")


def aerodynamic_state(aircraft: Aircraft, polar: DragPolar, speed_m_s: float,
                      altitude_m: float, mass_kg: float, gamma_rad: float = 0.0):
    if not math.isfinite(speed_m_s) or speed_m_s <= 0 or not math.isfinite(mass_kg) or mass_kg <= 0:
        raise ValueError("Speed and mass must be finite and positive")
    atm = atmosphere(altitude_m)
    mach = speed_m_s / atm.sound_speed_m_s
    q = 0.5 * atm.density_kg_m3 * speed_m_s ** 2
    cl = mass_kg * G0 * math.cos(gamma_rad) / (q * aircraft.wing_area_m2)
    reynolds = atm.density_kg_m3 * speed_m_s * aircraft.chord_m / atm.viscosity_pa_s
    # Turbulent Re^-1/5 sensitivity applied ONLY to the viscous share of Cd0.
    areas = polar.profile_drag_areas(mach, reynolds, aircraft)
    cd_parasite = areas['parasite_drag_area_m2'] / aircraft.wing_area_m2
    cd_induced = cl ** 2 / (math.pi * aircraft.oswald_efficiency * aircraft.aspect_ratio)
    cd_wave = areas['wave_drag_area_m2'] / aircraft.wing_area_m2
    cd = cd_parasite + cd_induced + cd_wave + aircraft.trim_cd
    return dict(mach=mach, q_pa=q, cl=cl, reynolds=reynolds, cd_parasite=cd_parasite,
                cd_induced=cd_induced, cd_wave=cd_wave, cd_total=cd,
                drag_n=q * aircraft.wing_area_m2 * cd, **areas,
                **{key.replace('_area_m2', '_n'): q * value for key, value in areas.items()})
