from dataclasses import replace
import math
import numpy as np
import pandas as pd
import pytest

from gypaetus.dart import DartLayout, P550Engine, build_layout, wave_drag_area, geometry_polar, ENVELOPES, MASS_BUDGET_KG
from gypaetus.models import Aircraft, aerodynamic_state, Engine, DRAG_CASES
from gypaetus.atmosphere import atmosphere


def test_p550_hardware_fuel_anchor_and_lapse_are_coupled():
    e=P550Engine(installed_factor=1)
    assert e.performance(0,0) == pytest.approx((550,.022))
    assert .022/800*60*1e6 == pytest.approx(1650)
    for factor in (.85,.8,.75):
        t,f=replace(e,installed_factor=factor).performance(1,6000)
        old=Engine(sea_level_static_thrust_n=600,installed_factor=factor)
        assert t/old.performance(1,6000)[0] == pytest.approx(550/600)
        assert f == pytest.approx(e.performance(1,6000)[1])
    with pytest.raises(ValueError):replace(e,sea_level_static_thrust_n=600)
    assert sum(MASS_BUDGET_KG.values()) == pytest.approx(18)


def test_wave_functional_against_independent_sears_haack_solution():
    x=np.linspace(0,2,8001);amax=.02
    area=amax*(4*(x/2)*(1-x/2))**1.5
    assert wave_drag_area(x,area) == pytest.approx(9*math.pi/2*(amax/2)**2,rel=1e-5)
    assert wave_drag_area(3*x,9*area) == pytest.approx(9*wave_drag_area(x,area),rel=1e-8)


def test_physical_package_clearance_fuel_volume_and_reference_distinction():
    d=DartLayout();g=build_layout(d);m=g['metrics']
    assert np.all(g['body_radius_m'] >= g['min_radius_m']-1e-12)
    assert m['max_body_frontal_area_m2'] > d.inlet_reference_area_m2
    assert d.inlet_reference_area_m2 == pytest.approx(math.pi*.1**2)
    assert m['tank_usable_fuel_kg'] > 3
    assert 0 < m['exposed_wing_planform_m2'] < .08
    assert g['total_area_m2'] == pytest.approx(g['body_area_m2']+g['wing_area_m2']+g['fin_area_m2'])
    assert m['compensated_wave_area_m2'] < m['uncompensated_wave_area_m2']


def test_wave_area_numerical_convergence():
    g=build_layout();fine=build_layout(stations=4001,strips=800)
    assert fine['metrics']['compensated_wave_area_m2'] == pytest.approx(g['metrics']['compensated_wave_area_m2'],rel=.001)
    k160=wave_drag_area(g['x_m'],g['total_area_m2'],160)
    assert k160 == pytest.approx(g['metrics']['compensated_wave_area_m2'],rel=.001)


def test_only_wave_changes_and_three_force_terms_sum():
    a=Aircraft(wing_area_m2=.08)
    for mach in (.8,.9,1):
        states=[aerodynamic_state(a,geometry_polar(name),mach*atmosphere(6000).sound_speed_m_s,6000,23) for name in ENVELOPES]
        for key in ('parasite_drag_n','body_drag_n','wing_profile_drag_n','tail_drag_n','cd_induced'):
            assert [s[key] for s in states] == pytest.approx([states[0][key]]*3)
        for s in states:
            body=s['body_drag_n']
            wing_tail=s['wing_profile_drag_n']+s['tail_drag_n']+s['q_pa']*.08*(s['cd_induced']+a.trim_cd)
            assert s['drag_n'] == pytest.approx(body+wing_tail+s['wave_drag_n'])


def test_reference_area_change_cannot_change_fixed_physical_drag():
    a=Aircraft(wing_area_m2=.08);b=replace(a,wing_area_m2=.16,aspect_ratio=1.5,trim_cd=.001)
    p=geometry_polar('baseline')
    first=aerodynamic_state(a,p,300,6000,23)
    second=aerodynamic_state(b,p,300,6000,23)
    assert first['drag_n'] == pytest.approx(second['drag_n'],rel=1e-12)
    assert first['cd_total'] == pytest.approx(2*second['cd_total'])


def test_legacy_polar_force_unchanged_by_component_interface():
    a=Aircraft();p=DRAG_CASES['pessimistic'];s=aerodynamic_state(a,p,300,6000,23)
    expected=(p.parasite_cd(s['reynolds'],a)+p.wave_cd(s['mach'],a)+s['cd_induced']+a.trim_cd)*s['q_pa']*a.wing_area_m2
    assert s['drag_n'] == pytest.approx(expected,rel=1e-14)


def test_force_first_runner_does_not_integrate_negative_branches(tmp_path,monkeypatch):
    import gypaetus.dart_report as runner
    def forbidden(*args,**kwargs):
        raise AssertionError('Negative force branch must never be integrated')
    monkeypatch.setattr(runner,'run_case',forbidden)
    monkeypatch.setattr(runner,'geometry_artifacts',lambda *args:None)
    monkeypatch.setattr(runner,'plot_forces',lambda *args:None)
    t=runner.run_dart(tmp_path)
    assert len(t)==12
    assert set(t.design_id)=={'D0027','D0030','D0033','D0036'}
    assert set(t.installation_loss_pct)=={15,20,25}
    assert (t[t.installation_loss_pct==15].baseline_min_excess_n<0).all()
    decisions=pd.read_csv(tmp_path/'trajectory_decisions.csv')
    assert not decisions.trajectory_run.any()
    assert decisions.gate_pass.isna().all() and decisions.endurance_pass.isna().all()
    assert not (tmp_path/'trajectories').exists()
