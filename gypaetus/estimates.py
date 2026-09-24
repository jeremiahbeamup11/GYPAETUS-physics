"""Indicative ground-roll estimates, not a runway feasibility determination."""

import math

from .atmosphere import atmosphere
from .constants import G0
from .models import Aircraft, DragPolar, Engine


def runway_estimates(aircraft: Aircraft, engine: Engine, polar: DragPolar,
                     runway_altitude_m: float = 0, rolling_mu: float = 0.03, braking_mu: float = 0.3):
    if not math.isfinite(rolling_mu) or not math.isfinite(braking_mu) or not 0 <= rolling_mu < 1 or not 0 < braking_mu < 1:
        raise ValueError("Rolling friction must be [0, 1), braking friction (0, 1)")
    atm = atmosphere(runway_altitude_m)
    mass = aircraft.total_mass_kg
    weight = mass * G0
    stall = math.sqrt(2 * weight / (atm.density_kg_m3 * aircraft.wing_area_m2 * aircraft.cl_max_landing))
    liftoff, approach = 1.2 * stall, 1.3 * stall
    representative_speed = 0.7 * liftoff
    thrust, _ = engine.performance(representative_speed / atm.sound_speed_m_s, runway_altitude_m)
    q = 0.5 * atm.density_kg_m3 * representative_speed ** 2
    ground_cl = 0.5 * weight / (q * aircraft.wing_area_m2)
    ground_cd = polar.cd0 + aircraft.trim_cd + ground_cl ** 2 / (math.pi * aircraft.oswald_efficiency * aircraft.aspect_ratio)
    drag = q * aircraft.wing_area_m2 * ground_cd
    acceleration = (thrust - drag - rolling_mu * 0.5 * weight) / mass
    return dict(stall_speed_m_s=stall, liftoff_speed_m_s=liftoff, approach_speed_m_s=approach,
                takeoff_ground_roll_m=liftoff ** 2 / (2 * acceleration) if acceleration > 0 else None,
                landing_ground_roll_m=approach ** 2 / (2 * braking_mu * G0),
                assumption="Constant representative takeoff acceleration; 50% weight on wheels; landing braking only; no obstacle, flare, slope, wind or safety factor; transonic-entry mass used")

