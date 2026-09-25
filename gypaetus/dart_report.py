"""Reproduce the one-layout P550 gate: four mass IDs, three installation losses; wave-only uncertainty."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .atmosphere import atmosphere
from .dart import DartLayout, P550Engine, build_layout, geometry_polar, ENVELOPES, MASS_BUDGET_KG, wave_drag_area
from .models import Aircraft, Mission, aerodynamic_state
from .provenance import provenance
from .simulation import run_case
from .stress import CANDIDATES, INSTALLATION_FACTORS


def _json(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def geometry_artifacts(out,d,g):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon
    out.mkdir(parents=True,exist_ok=True)
    stations=pd.DataFrame({k:v for k,v in g.items() if k!='metrics'})
    stations.to_csv(out/'area_stations.csv',index=False)
    lock=dict(layout=asdict(d),metrics=g['metrics'],engine=asdict(P550Engine()),
        mass_allocations_kg=MASS_BUDGET_KG,uncertainty_envelopes=ENVELOPES,
        status='Concept geometry and unvalidated component-drag screen; not a validated flight design')
    _json(out/'layout.json',lock)
    x,r=g['x_m'],g['body_radius_m']
    fig,axes=plt.subplots(3,1,figsize=(13,10),layout='constrained',height_ratios=[1.7,1.1,1.3])
    ax=axes[0]
    for sign in (-1,1):
        y=np.linspace(0,d.span_m/2,200)
        le=d.wing_root_le_m+y*np.tan(np.radians(d.wing_sweep_deg))
        c=d.root_chord_m*(1-(1-d.wing_taper)*y/(d.span_m/2))
        ax.fill(np.r_[le,(le+c)[::-1]],sign*np.r_[y,y[::-1]],color='#6b9cca',alpha=.7)
        z=np.linspace(0,d.fin_height_m,100)
        lef=d.fin_root_le_m+z*np.tan(np.radians(d.fin_sweep_deg))
        cf=d.fin_root_chord_m+(d.fin_tip_chord_m-d.fin_root_chord_m)*z/d.fin_height_m
        tip_x=np.linspace(lef[-1],lef[-1]+cf[-1],30)
        root_x=np.linspace(d.fin_root_le_m+d.fin_root_chord_m,d.fin_root_le_m,30)
        outline_x=np.r_[lef,tip_x,(lef+cf)[::-1],root_x]
        outline_h=np.r_[z,np.full_like(tip_x,d.fin_height_m),z[::-1],np.zeros_like(root_x)]
        ax.fill(outline_x,sign*(np.interp(outline_x,x,r)+outline_h),color='#6b9cca',alpha=.7)
    ax.fill_between(x,-r,r,color='#dce7e9',edgecolor='#254652')
    ax.add_patch(Rectangle((d.engine_start_m,-d.case_diameter_m/2),d.engine_packaging_length_m-.108,d.case_diameter_m,facecolor='#d88a38',alpha=.7,label='Locked engine case envelope'))
    ax.add_patch(Rectangle((d.engine_start_m+d.engine_packaging_length_m-.108,-.054),d.length_m-(d.engine_start_m+d.engine_packaging_length_m-.108),.108,facecolor='#d88a38',alpha=.25,label='Nozzle / assumed exhaust extension'))
    ax.plot([0,d.engine_start_m],[d.duct_outer_diameter_m/2]*2,ls='--',color='#587879')
    ax.plot([0,d.engine_start_m],[-d.duct_outer_diameter_m/2]*2,ls='--',color='#587879')
    tank=(x>=d.tank_start_m)&(x<=d.tank_end_m)
    for sign in (-1,1):
        ax.fill_between(x[tank],sign*(d.duct_outer_diameter_m/2+.003),sign*(r[tank]-.005),color='#83af75',alpha=.7)
    for position in (d.engine_start_m+.157,d.engine_start_m+.247):
        ax.plot([position]*2,[-.115,.115],color='#985317',lw=4)
    ax.set(xlim=(-.02,d.length_m+.02),ylim=(-.30,.35),xlabel='Axial station x [m]',ylabel='Lateral y [m]',title='P550-dart-01 • one 2.4 m concept layout • plan view, equal scale')
    ax.set_aspect('equal');ax.legend(loc='upper right',fontsize=8)
    ax.text(.03,.29,'200 mm highlight / 190 mm clear aperture',fontsize=9)
    ax.text(.33,-.28,'Annular fuel-volume allocation',fontsize=9)
    ax.text(1.25,-.28,'178.6 mm case • 230 mm mounts • 248 mm max body',fontsize=9)
    ax=axes[1]
    ax.plot(x,1e4*g['body_area_m2'],label='Body after area compensation')
    ax.plot(x,1e4*g['total_area_m2'],label='Body + exposed wing + fins',lw=2)
    ax.plot(x,1e4*(g['target_area_m2']+g['wing_area_m2']+g['fin_area_m2']),ls='--',label='Same envelope without compensation',alpha=.7)
    ax.set(xlabel='Axial station x [m]',ylabel='Cross section [cm²]',title='Area rule subtracts appendage volume from body; engine and duct space stay fixed')
    ax.legend(fontsize=8,loc='lower left');ax.grid(alpha=.2)
    ax=axes[2]
    ax.plot(x,1e3*2*r,label='Outer body diameter')
    ax.plot(x,1e3*2*g['min_radius_m'],ls='--',label='Minimum packaging envelope')
    ax.set(xlabel='Axial station x [m]',ylabel='Diameter [mm]',title='Packaging check • gross S = 0.080 m², exposed wing ≈ %.3f m²'%g['metrics']['exposed_wing_planform_m2'])
    ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(out/'layout.png',dpi=170)
    fig.savefig(out/'layout.svg')
    plt.close(fig)

def run_dart(output='results/dart'):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    d=DartLayout();g=build_layout(d)
    geometry_artifacts(out/'geometry',d,g)
    mission=Mission(altitude_m=6000,hold_mach=1.01,hold_seconds=5)
    force_rows=[];branch_rows=[];curves=[];planned=[]
    sound=atmosphere(6000).sound_speed_m_s
    # PHASE 1: finish all twelve force cases before considering any trajectory.
    for design_id,(empty,fuel) in CANDIDATES.items():
        if empty < sum(MASS_BUDGET_KG.values())-1e-9 or fuel > g['metrics']['tank_usable_fuel_kg']:
            raise ValueError(f'{design_id} does not fit the declared mass/volume allocations')
        aircraft=Aircraft(empty_mass_kg=empty,fuel_mass_kg=fuel,wing_area_m2=.08,
                          slenderness=d.length_m/g['metrics']['max_body_diameter_m'])
        for factor in INSTALLATION_FACTORS:
            engine=P550Engine(installed_factor=factor)
            loss=round(100*(1-factor));case_id=f'{design_id}_loss{loss}'
            row=dict(force_case_id=case_id,design_id=design_id,empty_mass_kg=empty,
                fuel_kg=fuel,entry_mass_kg=empty+fuel,installation_loss_pct=loss,
                engine_mass_in_empty_kg=5.4,empty_mass_status='allocation_only_not_verified')
            for name in ENVELOPES:
                polar=geometry_polar(name,d)
                local=[]
                for basis,mass in [('entry',empty+fuel),('dry_lower_drag_bound',empty)]:
                    for mach in np.linspace(.8,1.0,401):
                        state=aerodynamic_state(aircraft,polar,mach*sound,6000,mass)
                        thrust,flow=engine.performance(mach,6000)
                        state.update(force_case_id=case_id,design_id=design_id,drag_case=name,loss_pct=loss,
                            audit_basis=basis,audit_mass_kg=mass,thrust_n=thrust,fuel_flow_kg_s=flow,
                            excess_thrust_n=thrust-state['drag_n'])
                        state['Dbody_N']=state['body_drag_n']  # body + inlet + nozzle
                        state['Dwing_tail_N']=state['wing_profile_drag_n']+state['tail_drag_n']+state['q_pa']*aircraft.wing_area_m2*(state['cd_induced']+aircraft.trim_cd)
                        state['Dwave_N']=state['wave_drag_n']
                        local.append(state)
                audit=pd.DataFrame(local);curves.append(audit)
                entry=audit[audit.audit_basis=='entry'];dry=audit[audit.audit_basis=='dry_lower_drag_bound']
                control=entry.loc[entry.excess_thrust_n.idxmin()]
                margin=float(control.excess_thrust_n)
                row[name+'_min_excess_n']=margin
                row[name+'_critical_mach']=float(control.mach)
                row[name+'_dry_min_excess_n']=float(dry.excess_thrust_n.min())
                row[name+'_force_pass']=bool(margin>=mission.force_margin_n)
                if name=='baseline':
                    sonic=entry.iloc[-1]
                    row.update(mach1_thrust_n=sonic.thrust_n,mach1_body_n=sonic.Dbody_N,
                        mach1_wing_tail_n=sonic.Dwing_tail_N,mach1_baseline_wave_n=sonic.Dwave_N)
                planned.append((case_id,name,margin,aircraft,engine,polar))
            force_rows.append(row)
    force_table=pd.DataFrame(force_rows)
    force_table.to_csv(out/'force_cases.csv',index=False)
    audit=pd.concat(curves,ignore_index=True)
    audit.to_csv(out/'force_audits.csv.gz',index=False,compression='gzip')
    # PHASE 2: trajectories ONLY for wave branches whose full gate force audit passes.
    for case_id,name,margin,aircraft,engine,polar in planned:
        passed=margin>=mission.force_margin_n
        status=dict(force_case_id=case_id,wave_envelope=name,force_pass=passed,
            trajectory_run=passed,gate_pass=None,endurance_pass=None,
            reason='negative_force_balance' if margin<0 else 'below_required_force_margin',
            geometry_gate_pass=False,empty_mass_verified=False)
        if passed:
            result=run_case(aircraft,engine,polar,mission)
            flags=result.summary['review_flags'].split(';')
            flags.remove('engine_mass_thrust_coupling_unverified')
            flags.extend(['empty_mass_allocations_unverified','transonic_wave_closure_unvalidated',
                'inlet_flow_matching_unverified','exhaust_extension_loss_unverified','body_lift_and_effective_wing_unverified'])
            result.summary.update(review_flags=';'.join(flags),engine_mass_in_empty_kg=5.4,
                empty_mass_verified=False,geometry_gate_pass=False)
            folder=out/'trajectories'/f'{case_id}_{name}';folder.mkdir(parents=True,exist_ok=True)
            _json(folder/'inputs.json',result.inputs());_json(folder/'summary.json',result.summary)
            result.trajectory.to_csv(folder/'trajectory.csv.gz',index=False,compression='gzip')
            result.hold_trajectory.to_csv(folder/'hold_trajectory.csv.gz',index=False,compression='gzip')
            status.update(gate_pass=result.summary['gate_pass'],endurance_pass=result.summary['endurance_pass'],
                reason=result.summary['termination'],endurance_reason=result.summary['endurance_termination'])
        branch_rows.append(status)
    branches=pd.DataFrame(branch_rows);branches.to_csv(out/'trajectory_decisions.csv',index=False)
    pd.DataFrame([dict(component=k,kg=v) for k,v in MASS_BUDGET_KG.items()]).to_csv(out/'mass_budget.csv',index=False)
    numerical=[]
    for modes in (40,80,160):
        numerical.append(dict(check='Fourier modes',resolution=modes,wave_area_m2=wave_drag_area(g['x_m'],g['total_area_m2'],modes)))
    for stations in (1001,2001,4001):
        gg=build_layout(d,stations=stations)
        numerical.append(dict(check='Axial stations',resolution=stations,wave_area_m2=gg['metrics']['compensated_wave_area_m2']))
    pd.DataFrame(numerical).to_csv(out/'numerical_convergence.csv',index=False)
    _json(out/'run_inputs.json',dict(layout=asdict(d),mission=asdict(mission),candidates=CANDIDATES,
        installation_factors=INSTALLATION_FACTORS,engine=asdict(P550Engine()),wave_envelopes=ENVELOPES,
        component_models={name:asdict(geometry_polar(name,d)) for name in ENVELOPES},
        force_case_count=12,trajectory_count=int(branches.trajectory_run.sum()),
        old_grid_rerun=False,provenance=provenance()))
    plot_forces(out,audit)
    write_report(out,force_table,branches,g,d)
    manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.rglob('*')) if p.is_file() and p.name!='sha256.json'}
    _json(out/'sha256.json',manifest)
    return force_table

def plot_forces(out,audit):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained',sharey=True)
    for ax,name in zip(axes,ENVELOPES):
        df=audit[(audit.design_id=='D0036')&(audit.drag_case==name)&(audit.audit_basis=='entry')]
        ref=df[df.loss_pct==15]
        ax.stackplot(ref.mach,ref.Dbody_N,ref.Dwing_tail_N,ref.Dwave_N,
                     labels=['Body + inlet + nozzle','Exposed wing + tail + lift/trim','Volume wave proxy'],alpha=.7)
        for loss in (15,20,25):
            line=df[df.loss_pct==loss]
            ax.plot(line.mach,line.thrust_n,label=f'Thrust, {loss}% loss',ls={15:'-',20:'--',25:':' }[loss],color='black')
        ax.set(title=name.capitalize(),xlabel='Mach',xlim=(.8,1.01));ax.grid(alpha=.2)
    axes[0].set_ylabel('Force [N]');axes[0].legend(fontsize=7,loc='upper left')
    fig.suptitle('D0036 • P550 550 N rating • 6 km • entry mass 24 kg\nFull-interval force audit, not a flown trajectory; drag closures unvalidated')
    fig.savefig(out/'forces.png',dpi=170);plt.close(fig)


def write_report(out,table,branches,g,d):
    m=g['metrics']
    closed=bool((table[table.installation_loss_pct==15].baseline_min_excess_n<0).all())
    verdict='This corner is closed under the declared model: baseline fails at 15% loss on all four masses.' if closed else 'Baseline retains a nonnegative branch at 15% loss; inspect wave sensitivity and trajectory decisions.'
    rows=[]
    for r in table.itertuples():
        rows.append(f'| {r.design_id} | {r.entry_mass_kg:.0f} | {r.installation_loss_pct}% | {r.optimistic_min_excess_n:+.1f} | {r.baseline_min_excess_n:+.1f} | {r.pessimistic_min_excess_n:+.1f} |')
    component=[]
    for r in table[table.installation_loss_pct==15].itertuples():
        component.append(f'| {r.design_id} | {r.mach1_body_n:.1f} | {r.mach1_wing_tail_n:.1f} | {r.mach1_baseline_wave_n:.1f} | {r.mach1_thrust_n:.1f} | {r.baseline_min_excess_n:+.1f} |')
    wave_reduction=100*(1-m['compensated_wave_area_m2']/m['uncompensated_wave_area_m2'])
    text=f'''# P550 dart: twelve force-balance cases

**{verdict}**

Only D0027, D0030, D0033 and D0036 were evaluated, at 15%, 20% and 25% total installation loss. One geometry; no design-grid expansion. Optimistic / baseline / pessimistic vary **only the wave term**. Body/inlet/nozzle and exposed-wing/tail drag are identical across those three columns.

## The requested table

Minimum T−D across Mach 0.8–1.0 at 6 km and each case's entry mass, in newtons. Positive means force margin remains; negative blocks a trajectory run. The CSV also records controlling Mach and dry-mass lower-drag bounds.

| ID | Entry mass [kg] | Installation loss | Optimistic wave [N] | Baseline wave [N] | Pessimistic wave [N] |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

**Trajectory runs: {int(branches.trajectory_run.sum())}.** Each wave branch is screened before integration; rejected branches have blank gate/hold simulation outcomes, not invented trajectories. The five-second Mach 1.01 hold remains configured for any qualifying trajectory. See [force table](force_cases.csv) and [trajectory decisions](trajectory_decisions.csv).

## Show the force balance

At Mach 1 and 15% installation loss, baseline wave assumption:

| ID | Fixed body + inlet + nozzle [N] | Exposed wing + tail + lift/trim [N] | Wave from area plot [N] | Installed thrust [N] | Minimum T−D [N] |
|---|---:|---:|---:|---:|---:|
{chr(10).join(component)}

![Force components](forces.png)

These are algebraic force audits at constant mass, not flown paths. The dry-mass audit is a generous lower-drag bound; it is not flight with an empty tank. Changing fuel mainly changes induced drag here. It cannot shrink the engine bay, wetted body or inlet.

## Frozen engine and area accounting

- P550-PRO-S: 550 N ISA static, 5.4 kg counted once inside empty mass, SFC 0.144 kg/N/h. Published 1650 ml/min equals 0.022 kg/s at the assumed fuel density 800 kg/m³.
- Conservative case diameter 178.6 mm; product length 419 mm; 427 mm packaging reservation from the linked dimension drawing, with 230 mm mounting hardware. Exact variant interface still needs confirmation.
- Highlight 200 mm, assumed clear aperture 190 mm and duct OD 194 mm. Fixed coefficient reference {m['inlet_reference_area_m2']:.6f} m²; this is **not** the maximum fuselage frontal area.
- The selected 2.4 m area distribution has {1000*m['max_body_diameter_m']:.0f} mm maximum body diameter ({m['max_body_frontal_area_m2']:.5f} m² frontal area), to enclose the mounts. Body wetted area is {m['body_wetted_area_m2']:.3f} m².
- S remains 0.080 m² gross; exposed wing is {m['exposed_wing_planform_m2']:.4f} m² and exposed fins total {m['fin_planform_m2']:.4f} m². Buried wing volume is excluded from the area plot.
- Engine package sits at x={d.engine_start_m:.3f}–{d.engine_start_m+d.engine_packaging_length_m:.3f} m. The smooth afterbody assumes a {d.length_m-d.engine_start_m-d.engine_packaging_length_m:.3f} m exhaust extension. Its losses are unresolved inside the 15–25% total installation assumption; no extra loss is silently applied.

![Area distribution and package](geometry/layout.png)

Area compensation removes exposed wing/fin cross section from body space where packaging allows it. The linear wave-area proxy changes from {m['uncompensated_wave_area_m2']:.6f} to {m['compensated_wave_area_m2']:.6f} m² ({wave_reduction:.1f}% lower). This compares two area plots, not more aircraft performance cases. Station coordinates are in [area_stations.csv](geometry/area_stations.csv).

## Empty mass: budget closure is conditional

Engine 5.4 kg + other allocated equipment 10.8 kg + reserve 1.8 kg = 18 kg empty. The 21 kg budget adds 3 kg reserve. The annular tank volume allocation holds about {m['tank_usable_fuel_kg']:.2f} kg using 75% packing and 10% ullage, sufficient for the requested 1 / 3 kg loads. [Explicit allocations](mass_budget.csv).

Only engine mass is sourced hardware data. The remaining masses are allocations, not weighed parts or engineering estimates derived from a structural design. The 18 kg budget closes arithmetically and has not been shown impossible; its IDs are retained here as conditional force-audit rows, **not accepted aircraft candidates**. If a substantiated mass budget exceeds 18 kg, remove D0027 and D0033. Fuel is remaining fuel at transonic entry, not takeoff fuel.

## What this result establishes

The model's force screen closes this particular corner; it does not establish that every possible P550 airplane fails. The body skin-friction estimate uses the actual wetted area, but external pressure drag is still an explicit coefficient assumption. The area-derived wave amplitude uses a linear slender-body functional; open-inlet streamtube, jet plume and transonic shock effects are unresolved. Its Mach ramp and three wave envelopes are assumptions, not validated polars or statistical bounds.

Next work, if resumed, is a slimmer engine bay / better total-area distribution and a defensible inlet/afterbody pressure estimate. **Stop here: no more mass/grid cases or downstream design work.**

## Reproduce

`python -m gypaetus.dart_report --output results/dart` generates the 12 force cases first and integrates only nonnegative branches. Open `notebooks/p550_dart.ipynb` for the same table and figures. `run_inputs.json` records exact inputs, engine map and source hashes; `sha256.json` fingerprints all outputs.

Engine data: [JetCat P550-PRO-S](https://www.jetcat.de/en/productdetails/produkte/jetcat/produkte/Professionell/P550%20PRO-S). Method, uncertainty values and primary references: [model notes](../../docs/dart_geometry.md).
'''
    (out/'REPORT.md').write_text(text)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='results/dart')
    table=run_dart(parser.parse_args().output)
    print(table[['design_id','entry_mass_kg','installation_loss_pct','optimistic_min_excess_n','baseline_min_excess_n','pessimistic_min_excess_n']].to_string(index=False))


if __name__=='__main__':main()
