from dataclasses import replace
import math

import pytest

from gypaetus import Aircraft, Engine, Mission, DRAG_CASES, run_case
from gypaetus.atmosphere import atmosphere
from gypaetus.models import aerodynamic_state
from gypaetus.stress import CANDIDATES, fixed_body_polar, force_audit, break_even_body_fraction


def test_only_requested_candidates():
    assert set(CANDIDATES) == {"D0027", "D0030", "D0033", "D0036"}
    assert CANDIDATES["D0036"] == (21, 3)


def test_anchor_matches_original_and_zero_allocation_is_identity():
    polar = DRAG_CASES["pessimistic"]
    for area in (0.08, 0.12):
        aircraft = Aircraft(wing_area_m2=area)
        original = aerodynamic_state(aircraft, polar, 300, 6000, 24)
        zero = aerodynamic_state(aircraft, fixed_body_polar(polar, 0), 300, 6000, 24)
        assert zero["drag_n"] == pytest.approx(original["drag_n"])
    anchored = aerodynamic_state(Aircraft(wing_area_m2=0.12), fixed_body_polar(polar), 300, 6000, 24)
    assert anchored["drag_n"] == pytest.approx(original["drag_n"])


def test_fixed_body_force_does_not_shrink_with_wing_or_change_with_wing_reynolds_length():
    polar = fixed_body_polar(DRAG_CASES["pessimistic"])
    atm = atmosphere(6000)
    body_areas = []
    for area, ar in ((0.08, 3), (0.12, 3), (0.18, 5)):
        aircraft = Aircraft(wing_area_m2=area, aspect_ratio=ar)
        re = atm.density_kg_m3 * 300 * aircraft.chord_m / atm.viscosity_pa_s
        parts = polar.drag_areas(300/atm.sound_speed_m_s, re, aircraft)
        body_areas.append(parts['body_parasite_drag_area_m2']+parts['body_wave_drag_area_m2'])
    assert body_areas == pytest.approx([body_areas[0]]*3, rel=1e-12)


def test_body_area_not_added_twice_and_increases_wing_referenced_cd():
    aircraft = Aircraft(wing_area_m2=0.08)
    polar = fixed_body_polar(DRAG_CASES["pessimistic"])
    state = aerodynamic_state(aircraft, polar, 300, 6000, 24)
    parts = polar.drag_areas(state['mach'], state['reynolds'], aircraft)
    assert (state['cd_parasite']+state['cd_wave'])*aircraft.wing_area_m2 == pytest.approx(sum(parts.values()))
    original = aerodynamic_state(aircraft, DRAG_CASES['pessimistic'], 300, 6000, 24)
    assert state['cd_total'] > original['cd_total']


def test_installation_losses_are_total_not_applied_twice_and_keep_fuel_flow():
    uninstalled = Engine(sea_level_static_thrust_n=600, installed_factor=1)
    for factor in (.85,.80,.75):
        e = replace(uninstalled, installed_factor=factor)
        assert e.performance(0,0)[0] == pytest.approx(600*factor)
        t, flow = e.performance(1,6000)
        t0, flow0 = uninstalled.performance(1,6000)
        assert t == pytest.approx(factor*t0)
        assert flow == flow0


def test_twenty_percent_loss_splits_gate_and_endurance_outcomes():
    result = run_case(Aircraft(empty_mass_kg=21, fuel_mass_kg=3, wing_area_m2=.08),
        Engine(sea_level_static_thrust_n=600, installed_factor=.8),
        DRAG_CASES['pessimistic'], Mission(altitude_m=6000))
    assert result.summary['gate_pass']
    assert not result.summary['endurance_pass']
    assert result.summary['endurance_termination'] == 'time_limit'


def test_fixed_body_fails_even_with_generous_dry_mass_drag_bound():
    aircraft=Aircraft(empty_mass_kg=21, fuel_mass_kg=3, wing_area_m2=.08)
    engine=Engine(sea_level_static_thrust_n=600, installed_factor=.85)
    polar=fixed_body_polar(DRAG_CASES['pessimistic'])
    mission=Mission(altitude_m=6000)
    bound=force_audit(aircraft,engine,polar,mission,aircraft.empty_mass_kg)
    assert bound.excess_thrust_n.min() < 0
    result=run_case(aircraft,engine,polar,mission)
    assert not result.summary['gate_pass']
    assert not result.summary['endurance_pass']
    assert result.trajectory.mach.max() < 1


def test_body_share_break_even_agrees_with_direct_force_calculation():
    aircraft=Aircraft(empty_mass_kg=21, fuel_mass_kg=3, wing_area_m2=.08)
    engine=Engine(sea_level_static_thrust_n=600)
    mission=Mission(altitude_m=6000)
    fraction,mach=break_even_body_fraction(aircraft,engine,DRAG_CASES['pessimistic'],mission,24)
    assert 0 < fraction < .5
    curve=force_audit(aircraft,engine,fixed_body_polar(DRAG_CASES['pessimistic'],fraction),mission,24)
    assert curve.excess_thrust_n.min() == pytest.approx(mission.force_margin_n,abs=1e-9)


def test_stressed_failure_is_stable_with_smaller_integration_steps():
    aircraft=Aircraft(empty_mass_kg=21, fuel_mass_kg=3, wing_area_m2=.08)
    engine=Engine(sea_level_static_thrust_n=600)
    polar=fixed_body_polar(DRAG_CASES['pessimistic'])
    coarse=run_case(aircraft,engine,polar,Mission(altitude_m=6000))
    fine=run_case(aircraft,engine,polar,Mission(altitude_m=6000,max_step_s=.05))
    assert not coarse.summary['gate_pass'] and not fine.summary['gate_pass']
    assert coarse.summary['termination'] == fine.summary['termination']
    assert coarse.summary['final_mach'] == pytest.approx(fine.summary['final_mach'],abs=1e-7)
    assert coarse.summary['final_fuel_kg'] == pytest.approx(fine.summary['final_fuel_kg'],abs=1e-7)


@pytest.mark.parametrize('fraction', [-.1,1.1,math.nan])
def test_invalid_body_allocations_rejected(fraction):
    with pytest.raises(ValueError):
        fixed_body_polar(DRAG_CASES['baseline'],fraction)
