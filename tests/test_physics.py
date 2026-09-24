from dataclasses import replace
import math

import numpy as np
import pytest
from scipy.integrate import trapezoid

from gypaetus.atmosphere import atmosphere
from gypaetus.constants import G0, MASS_LIMIT_KG, lb_to_kg, ft_to_m
from gypaetus.models import Aircraft, DragPolar, Engine, Mission, DRAG_CASES, aerodynamic_state
from gypaetus.simulation import run_case
from gypaetus.sweep import SweepGrid, run_sweep


def test_units_and_strictest_mass_cap():
    assert lb_to_kg(55) == pytest.approx(24.94758035)
    assert MASS_LIMIT_KG < 25
    assert ft_to_m(1000) == pytest.approx(304.8)


def test_standard_atmosphere_reference_and_layer_continuity():
    sea = atmosphere(0)
    assert sea.temperature_k == 288.15
    assert sea.pressure_pa == 101325
    assert sea.density_kg_m3 == pytest.approx(1.225, rel=1e-5)
    assert sea.sound_speed_m_s == pytest.approx(340.294, rel=1e-5)
    assert sea.viscosity_pa_s == pytest.approx(1.789e-5, rel=1e-3)
    # 11 km geopotential corresponds to slightly more geometric altitude.
    from gypaetus.constants import EARTH_RADIUS_M
    z11 = EARTH_RADIUS_M * 11000 / (EARTH_RADIUS_M - 11000)
    assert atmosphere(z11).pressure_pa == pytest.approx(22632.06, rel=1e-5)
    assert atmosphere(z11 - 0.001).density_kg_m3 == pytest.approx(atmosphere(z11 + 0.001).density_kg_m3, rel=1e-6)
    assert atmosphere(6000).sound_speed_m_s < sea.sound_speed_m_s
    z = 3000
    finite_difference = (atmosphere(z + 0.1).sound_speed_m_s - atmosphere(z - 0.1).sound_speed_m_s) / 0.2
    assert atmosphere(z).sound_speed_gradient_s_inv == pytest.approx(finite_difference, rel=1e-7)


def test_lift_balance_and_drag_components():
    aircraft = Aircraft()
    p = aerodynamic_state(aircraft, DragPolar(), 300, 3000, 23)
    assert p["cl"] * p["q_pa"] * aircraft.wing_area_m2 == pytest.approx(23 * G0)
    assert p["cd_total"] == pytest.approx(p["cd_parasite"] + p["cd_induced"] + p["cd_wave"] + aircraft.trim_cd)
    assert p["drag_n"] == pytest.approx(p["q_pa"] * aircraft.wing_area_m2 * p["cd_total"])
    heavy = aerodynamic_state(aircraft, DragPolar(), 300, 3000, 46)
    assert heavy["cd_induced"] == pytest.approx(4 * p["cd_induced"])
    climb = aerodynamic_state(aircraft, DragPolar(), 300, 3000, 23, math.radians(5))
    assert climb["cl"] / p["cl"] == pytest.approx(math.cos(math.radians(5)))


def test_wave_drag_and_reynolds_sensitivity():
    aircraft = Aircraft()
    for polar in DRAG_CASES.values():
        assert polar.wave_cd(0.6, aircraft) == 0
        assert polar.wave_cd(1.0, aircraft) > polar.wave_cd(0.8, aircraft)
    assert DRAG_CASES["pessimistic"].wave_cd(1, aircraft) > DRAG_CASES["baseline"].wave_cd(1, aircraft) > DRAG_CASES["optimistic"].wave_cd(1, aircraft)
    p1 = aerodynamic_state(aircraft, DragPolar(), 300, 0, 23)
    p2 = aerodynamic_state(replace(aircraft, wing_area_m2=0.03), DragPolar(), 300, 0, 23)
    assert p2["reynolds"] < p1["reynolds"]
    assert p2["cd_parasite"] > p1["cd_parasite"]


def test_installation_reduces_thrust_not_bench_fuel_flow():
    engine = Engine()
    t, f = engine.performance(0.9, 3000)
    tb, fb = replace(engine, installed_factor=1).performance(0.9, 3000)
    assert t == pytest.approx(tb * 0.85)
    assert f == fb
    assert engine.performance(0.9, 6000)[0] < t
    assert engine.performance(0.9, 3000, 0) == (0, 0)
    assert engine.performance(0.9, 3000, 0.5)[0] == pytest.approx(t * 0.5)
    assert engine.performance(1, 3000)[0] < engine.performance(0.8, 3000)[0]


def passing_case(**kwargs):
    return run_case(Aircraft(wing_area_m2=0.08), Engine(sea_level_static_thrust_n=600),
                    DRAG_CASES["baseline"], kwargs.pop("mission", Mission()), **kwargs)


def test_pass_reaches_target_burns_fuel_and_holds_supersonic():
    result = passing_case()
    h = result.trajectory
    assert result.summary["gate_pass"]
    assert h.mach.iloc[-1] == pytest.approx(1, abs=1e-9)
    assert (h.altitude_m == 3000).all()
    assert np.all(np.diff(h.fuel_kg) <= 0)
    assert (h.mass_kg - h.fuel_kg).to_numpy() == pytest.approx(20)
    burn = trapezoid(h.fuel_flow_kg_s, h.time_s)
    assert h.fuel_kg.iloc[0] - h.fuel_kg.iloc[-1] == pytest.approx(burn, rel=2e-5)
    assert result.summary["endurance_pass"]
    held = result.hold_trajectory.query("phase == 'level_hold'")
    assert held.time_s.iloc[-1] - held.time_s.iloc[0] == pytest.approx(5)
    assert held.mach.to_numpy() == pytest.approx(1.01)
    assert held.excess_thrust_n.to_numpy() == pytest.approx(0, abs=1e-9)


def test_drag_barrier_cannot_be_skipped():
    result = run_case()
    assert not result.summary["gate_pass"]
    assert result.summary["termination"] == "insufficient_acceleration"
    assert result.trajectory.mach.iloc[-1] < 1


@pytest.mark.parametrize("aircraft,expected", [
    (Aircraft(wing_area_m2=0.08, empty_mass_kg=24, fuel_mass_kg=1), "mass_within_limit"),
    (Aircraft(wing_area_m2=0.08, fuel_mass_kg=0), "reached_mach_1"),
    (Aircraft(wing_area_m2=0.08, cl_limit=0.001), "cl_within_limit"),
    (Aircraft(wing_area_m2=0.08, q_limit_pa=1000), "q_within_limit"),
])
def test_constraints_reject_false_passes(aircraft, expected):
    result = run_case(aircraft, Engine(sea_level_static_thrust_n=600))
    assert not result.summary["gate_pass"]
    assert not result.summary[expected]


def test_fuel_exhaustion_is_event_not_negative_mass():
    result = run_case(Aircraft(wing_area_m2=0.08, fuel_mass_kg=0.001), Engine(sea_level_static_thrust_n=600))
    assert result.summary["termination"] == "fuel_exhausted"
    assert not result.summary["gate_pass"]
    assert result.trajectory.fuel_kg.min() >= 0
    assert result.trajectory.fuel_kg.iloc[-1] == pytest.approx(0, abs=1e-9)


def test_short_timeout_is_not_a_pass():
    result = passing_case(mission=Mission(max_time_s=0.01))
    assert result.summary["termination"] == "time_limit"
    assert not result.summary["gate_pass"]


def test_gate_pass_does_not_imply_endurance_pass():
    result = run_case(Aircraft(wing_area_m2=0.08, fuel_mass_kg=0.16),
                      Engine(sea_level_static_thrust_n=600))
    assert result.summary["gate_pass"]
    assert not result.summary["endurance_pass"]
    assert result.summary["final_fuel_kg"] == pytest.approx(0, abs=1e-8)


def test_q_limit_crossing_stops_before_mach_1():
    result = run_case(Aircraft(wing_area_m2=0.08), Engine(sea_level_static_thrust_n=900),
                      mission=Mission(altitude_m=0))
    assert result.summary["termination"] == "q_limit"
    assert not result.summary["gate_pass"]
    assert result.trajectory.q_pa.iloc[-1] == pytest.approx(65000)
    assert result.trajectory.mach.iloc[-1] < 1


def test_positive_thrust_margin_is_not_enough_for_climb():
    aircraft = Aircraft(wing_area_m2=0.18)
    engine = Engine(sea_level_static_thrust_n=280)
    result = run_case(aircraft, engine, mission=Mission(gamma_deg=10))
    first = result.trajectory.iloc[0]
    assert first.excess_thrust_n > 0
    assert first.acceleration_force_n < 0
    assert not result.summary["gate_pass"]


def test_sweep_preserves_actual_custom_inputs(tmp_path):
    from gypaetus.sweep import save_sweep
    import json
    grid = SweepGrid(wing_areas_m2=(0.08,), rated_thrusts_n=(600,), fuel_masses_kg=(1,),
                     empty_masses_kg=(20,), altitudes_m=(3000,))
    engine = Engine(installed_factor=0.79)
    results = run_sweep(grid, engine=engine, check_endurance=False)
    save_sweep(results, tmp_path)
    inputs = json.loads((tmp_path / "sweep_inputs.json").read_text())
    assert inputs["engine"]["installed_factor"] == 0.79
    assert inputs["check_endurance"] is False
    assert "simulation.py" in inputs["provenance"]["source_sha256"]
    assert (tmp_path / "passing_cases.csv").exists()


def test_climb_uses_gravity_and_updates_atmosphere():
    result = passing_case(mission=Mission(gamma_deg=3))
    h = result.trajectory
    assert result.summary["gate_pass"]
    assert h.altitude_m.iloc[-1] > h.altitude_m.iloc[0]
    assert h.acceleration_force_n.to_numpy() == pytest.approx((h.excess_thrust_n - h.mass_kg * G0 * math.sin(math.radians(3))).to_numpy())
    # Energy equation: d(h + V²/2g)/dt = (T-D)V/W.
    assert (h.climb_rate_m_s + h.speed_m_s * h.acceleration_m_s2 / G0).to_numpy() == pytest.approx(h.specific_excess_power_m_s.to_numpy())


def test_step_size_convergence():
    a = passing_case(check_endurance=False)
    b = passing_case(mission=Mission(max_step_s=0.05), check_endurance=False)
    assert a.summary["gate_pass"] == b.summary["gate_pass"]
    assert a.summary["elapsed_s"] == pytest.approx(b.summary["elapsed_s"], rel=2e-6)
    assert a.summary["final_fuel_kg"] == pytest.approx(b.summary["final_fuel_kg"], rel=2e-6)


def test_sweep_classification_and_dimensions():
    grid = SweepGrid(wing_areas_m2=(0.08, 0.18), rated_thrusts_n=(450,), fuel_masses_kg=(1,),
                     empty_masses_kg=(20,), altitudes_m=(3000,))
    results = run_sweep(grid, check_endurance=False)
    assert len(results) == 6
    assert results.design_id.nunique() == 2
    assert all(results.groupby("design_id").drag_case.nunique() == 3)
    assert "incomplete_drag_sensitivity" not in results.drag_sensitivity.values
    smaller = run_sweep(replace(grid, drag_cases=("optimistic",)), check_endurance=False)
    assert (smaller.drag_sensitivity == "incomplete_drag_sensitivity").all()


@pytest.mark.parametrize("call", [
    lambda: Aircraft(fuel_mass_kg=-1), lambda: Aircraft(wing_area_m2=0),
    lambda: Aircraft(empty_mass_kg=float("nan")), lambda: Mission(gamma_deg=-1),
    lambda: Engine(propulsion_class="ramjet"), lambda: Engine(installed_factor=1.1),
    lambda: Engine().performance(1.3, 0), lambda: atmosphere(-1),
    lambda: atmosphere(21000), lambda: DragPolar(wave_peak_mach=0.5),
])
def test_invalid_inputs_raise(call):
    with pytest.raises(ValueError):
        call()
