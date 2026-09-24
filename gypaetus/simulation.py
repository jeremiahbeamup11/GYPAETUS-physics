"""Event-terminated variable-mass trajectories and explicit screening checks."""

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from .atmosphere import atmosphere
from .constants import G0, MASS_LIMIT_KG
from .models import Aircraft, DragPolar, Engine, Mission, aerodynamic_state


@dataclass
class CaseResult:
    aircraft: Aircraft
    engine: Engine
    polar: DragPolar
    mission: Mission
    trajectory: pd.DataFrame
    hold_trajectory: pd.DataFrame
    summary: dict

    def inputs(self):
        return {k: asdict(getattr(self, k)) for k in ("aircraft", "engine", "polar", "mission")}


def _point(aircraft, engine, polar, state, gamma, throttle):
    speed, fuel, altitude = state
    # Event solvers can probe just past exhaustion; never create negative physical mass.
    mass = aircraft.empty_mass_kg + max(0.0, fuel)
    aero = aerodynamic_state(aircraft, polar, speed, altitude, mass, gamma)
    thrust, flow = engine.performance(aero["mach"], altitude, throttle)
    excess = thrust - aero["drag_n"]
    force = excess - mass * G0 * math.sin(gamma)
    return dict(**aero, speed_m_s=speed, altitude_m=altitude,
                mass_kg=mass, fuel_kg=max(0.0, fuel), thrust_n=thrust,
                fuel_flow_kg_s=flow, excess_thrust_n=excess,
                acceleration_force_n=force, acceleration_m_s2=force / mass,
                climb_rate_m_s=speed * math.sin(gamma),
                specific_excess_power_m_s=excess * speed / (mass * G0), throttle=throttle)


def _accelerate(aircraft, engine, polar, mission, initial, target, duration):
    gamma = math.radians(mission.gamma_deg)

    def point(state):
        return _point(aircraft, engine, polar, state, gamma, mission.throttle)

    def rhs(t, state):
        p = point(state)
        return [p["acceleration_m_s2"], -p["fuel_flow_kg_s"], p["climb_rate_m_s"]]

    def reached(t, y):
        return y[0] / atmosphere(y[2]).sound_speed_m_s - target

    def exhausted(t, y):
        return y[1]

    def stalled_acceleration(t, y):
        return point(y)["acceleration_force_n"] - mission.force_margin_n

    def buffet(t, y):
        return aircraft.cl_limit - point(y)["cl"]

    def dynamic_pressure(t, y):
        return aircraft.q_limit_pa - point(y)["q_pa"]

    def atmosphere_limit(t, y):
        # Buffer prevents RK stages from exceeding the atmosphere's 20 km domain.
        return 19_900 - y[2]

    events = [reached, exhausted, stalled_acceleration, buffet, dynamic_pressure, atmosphere_limit]
    labels = ["target_reached", "fuel_exhausted", "insufficient_acceleration", "cl_limit", "q_limit", "altitude_limit"]
    for event in events:
        event.terminal = True
        event.direction = -1
    reached.direction = 1
    initial_point = point(initial)
    initial_point["time_s"] = 0.0
    for event, label in zip(events[1:], labels[1:]):
        value = event(0, initial)
        if value < 0 or (value == 0 and label in ("fuel_exhausted", "insufficient_acceleration", "altitude_limit")):
            return pd.DataFrame([initial_point]), np.array(initial), label
    if duration <= 0:
        return pd.DataFrame([initial_point]), np.array(initial), "time_limit"
    sol = solve_ivp(rhs, (0, duration), initial, events=events, dense_output=True,
                    max_step=min(mission.max_step_s, 0.5), rtol=1e-8, atol=1e-10)
    if not sol.success:
        raise RuntimeError(f"Integration failed: {sol.message}")
    end = sol.t[-1]
    # Audit both solver nodes and a fine time/Mach grid, including exact event endpoint.
    times = np.unique(np.r_[sol.t, np.linspace(0, end, max(2, math.ceil(end / 0.05) + 1))])
    states = sol.sol(times)
    machs = np.array([v / atmosphere(h).sound_speed_m_s for v, h in zip(states[0], states[2])])
    if machs[-1] > machs[0] and np.all(np.diff(machs) >= 0):
        grid = np.linspace(machs[0], machs[-1], max(2, math.ceil((machs[-1] - machs[0]) / 0.0002) + 1))
        times = np.unique(np.r_[times, np.interp(grid, machs, times)])
    rows = [dict(time_s=t, **point(sol.sol(t))) for t in times]
    reason = next((label for label, hits in zip(labels, sol.t_events) if len(hits)), "time_limit")
    return pd.DataFrame(rows), sol.y[:, -1], reason


def _hold(aircraft, engine, polar, mission, state):
    """Level constant-Mach hold with algebraic throttle control; gamma transition idealized."""
    speed, fuel, altitude = state

    def point(f):
        full = _point(aircraft, engine, polar, [speed, f, altitude], 0.0, 1.0)
        throttle = full["drag_n"] / full["thrust_n"]
        controlled = _point(aircraft, engine, polar, [speed, f, altitude], 0.0, min(1.0, throttle))
        controlled["required_throttle"] = throttle
        return controlled

    p0 = point(fuel)
    if (fuel <= 0 or p0["required_throttle"] > mission.throttle or
            p0["cl"] > aircraft.cl_limit or p0["q_pa"] > aircraft.q_limit_pa):
        return pd.DataFrame([dict(time_s=0.0, **p0)]), False

    def exhausted(t, y):
        return y[0]

    exhausted.terminal = True
    exhausted.direction = -1
    sol = solve_ivp(lambda t, y: [-point(y[0])["fuel_flow_kg_s"]],
                    (0, mission.hold_seconds), [fuel], events=exhausted,
                    max_step=min(mission.max_step_s, 0.1), rtol=1e-9, atol=1e-11)
    if not sol.success:
        raise RuntimeError(sol.message)
    history = pd.DataFrame([dict(time_s=t, **point(f)) for t, f in zip(sol.t, sol.y[0])])
    passed = (sol.t[-1] >= mission.hold_seconds - 1e-8 and sol.y[0, -1] >= -1e-8
              and history.required_throttle.max() <= mission.throttle + 1e-8
              and history.cl.max() <= aircraft.cl_limit and history.q_pa.max() <= aircraft.q_limit_pa)
    return history, bool(passed)


def run_case(aircraft: Aircraft = Aircraft(), engine: Engine = Engine(),
             polar: DragPolar = DragPolar(), mission: Mission = Mission(),
             check_endurance: bool = True) -> CaseResult:
    """Pass requires complete Mach 0.8→1.0 traversal and ALL documented checks."""
    initial = [mission.start_mach * atmosphere(mission.altitude_m).sound_speed_m_s,
               aircraft.fuel_mass_kg, mission.altitude_m]
    history, final, reason = _accelerate(aircraft, engine, polar, mission, initial,
                                        mission.target_mach, mission.max_time_s)
    checks = {
        "reached_mach_1": reason == "target_reached",
        "mass_within_limit": aircraft.total_mass_kg <= MASS_LIMIT_KG,
        "fuel_nonnegative": bool(history.fuel_kg.min() >= 0),
        "never_descends": bool(history.climb_rate_m_s.min() >= 0 and np.all(np.diff(history.altitude_m) >= -1e-7)),
        "positive_excess_thrust": bool(history.excess_thrust_n.min() >= mission.force_margin_n - 1e-7),
        "positive_acceleration": bool(history.acceleration_force_n.min() >= mission.force_margin_n - 1e-7),
        "cl_within_limit": bool(history.cl.max() <= aircraft.cl_limit + 1e-9),
        "q_within_limit": bool(history.q_pa.max() <= aircraft.q_limit_pa + 1e-5),
    }
    gate_pass = all(checks.values())
    hold_history = pd.DataFrame()
    endurance_pass = None
    endurance_reason = "not_requested" if not check_endurance or mission.hold_seconds == 0 else "gate_failed"
    if check_endurance and mission.hold_seconds > 0:
        endurance_pass = False
        if gate_pass:
            bridge, state, bridge_reason = _accelerate(aircraft, engine, polar, mission, final,
                                                      mission.hold_mach, mission.max_time_s - history.time_s.iloc[-1])
            bridge["time_s"] += history.time_s.iloc[-1]
            bridge["phase"] = "accelerate_to_hold"
            hold_history = bridge
            endurance_reason = bridge_reason
            if bridge_reason == "target_reached":
                held, endurance_pass = _hold(aircraft, engine, polar, mission, state)
                held["time_s"] += bridge.time_s.iloc[-1]
                held["phase"] = "level_hold"
                hold_history = pd.concat([bridge, held], ignore_index=True)
                endurance_reason = "hold_complete" if endurance_pass else "hold_failed"
    all_history = pd.concat([history, hold_history], ignore_index=True)
    flags = ["uncalibrated_drag_and_engine", "trim_stability_control_unverified", "engine_mass_thrust_coupling_unverified"]
    if all_history.q_pa.max() >= aircraft.flutter_review_q_pa or all_history.mach.max() >= aircraft.flutter_review_mach:
        flags.append("flutter_analysis_required")
    summary = dict(
        gate_pass=bool(gate_pass), endurance_pass=endurance_pass, termination=reason,
        failure_reasons=";".join(([reason] if reason != "target_reached" else []) + [k for k, passed in checks.items() if not passed]),
        endurance_termination=endurance_reason, drag_case=polar.name,
        empty_mass_kg=aircraft.empty_mass_kg, initial_fuel_kg=aircraft.fuel_mass_kg,
        initial_mass_kg=aircraft.total_mass_kg, wing_area_m2=aircraft.wing_area_m2,
        altitude_m=mission.altitude_m, gamma_deg=mission.gamma_deg,
        rated_thrust_n=engine.sea_level_static_thrust_n,
        initial_installed_thrust_to_weight=history.thrust_n.iloc[0] / (aircraft.total_mass_kg * G0),
        wing_loading_n_m2=aircraft.total_mass_kg * G0 / aircraft.wing_area_m2,
        elapsed_s=history.time_s.iloc[-1], final_mach=history.mach.iloc[-1],
        time_to_mach_1_s=history.time_s.iloc[-1] if gate_pass else None,
        fuel_at_mach_1_kg=history.fuel_kg.iloc[-1] if gate_pass else None,
        final_fuel_kg=all_history.fuel_kg.iloc[-1],
        min_excess_thrust_n=history.excess_thrust_n.min(),
        min_acceleration_force_n=history.acceleration_force_n.min(),
        max_cl=history.cl.max(), max_q_pa=history.q_pa.max(),
        review_flags=";".join(flags), **checks)
    return CaseResult(aircraft, engine, polar, mission, history, hold_history, summary)


def reference_curve(result: CaseResult, count: int = 401) -> pd.DataFrame:
    """Full gate at INITIAL mass/altitude, clearly distinct from an integrated path."""
    sound = atmosphere(result.mission.altitude_m).sound_speed_m_s
    return pd.DataFrame([_point(result.aircraft, result.engine, result.polar,
                               [m * sound, result.aircraft.fuel_mass_kg, result.mission.altitude_m],
                               math.radians(result.mission.gamma_deg), result.mission.throttle)
                         for m in np.linspace(0.8, 1.0, count)])
