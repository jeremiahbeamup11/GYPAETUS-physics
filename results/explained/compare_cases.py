"""Reproduce two cases already in all_cases.csv and plot the numerical evidence."""
from pathlib import Path
import sys
import os
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from gypaetus import Aircraft, Engine, Mission, DRAG_CASES, run_case
from gypaetus.cli import save_case
from gypaetus.simulation import reference_curve

OUT = Path(__file__).parent
all_cases = pd.read_csv(ROOT / 'results/all_cases.csv')
settings = [
    ('strongest_pessimistic', 'D0036', 'pessimistic', 0.08, 600, 6000),
    ('failed_baseline', 'D0059', 'baseline', 0.12, 450, 3000),
]
reproduced = []
for name, design, polar, area, thrust, altitude in settings:
    result = run_case(Aircraft(empty_mass_kg=21, fuel_mass_kg=3, wing_area_m2=area),
                      Engine(sea_level_static_thrust_n=thrust), DRAG_CASES[polar], Mission(altitude_m=altitude))
    saved = all_cases[(all_cases.design_id == design) & (all_cases.drag_case == polar)].iloc[0]
    assert result.summary['gate_pass'] == saved.gate_pass
    assert np.isclose(result.summary['elapsed_s'], saved.elapsed_s, rtol=1e-9)
    save_case(result, OUT / name)
    reproduced.append(result)
    h = result.trajectory
    print(name, {k: result.summary[k] for k in ['gate_pass','endurance_pass','elapsed_s','final_mach','min_excess_thrust_n','final_fuel_kg']})
    print('At end of gate: thrust N', h.thrust_n.iloc[-1], 'drag N', h.drag_n.iloc[-1], 'fuel kg', h.fuel_kg.iloc[-1], 'q Pa', h.q_pa.iloc[-1])

plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.spines.top':False,
                     'axes.spines.right':False, 'axes.grid':True, 'grid.alpha':0.18})
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
colors = ['#007f86', '#b85025']
for col, result in enumerate(reproduced):
    h = result.trajectory
    ax = axes[0, col]
    ax.plot(h.mach, h.thrust_n, color='#007f86', lw=2.7, label='Engine push (installed thrust)')
    ax.plot(h.mach, h.drag_n, color='#b85025', lw=2.7, label='Air resistance (drag)')
    ax.fill_between(h.mach, h.drag_n, h.thrust_n, color='#007f86', alpha=.12)
    if not result.summary['gate_pass']:
        reference = reference_curve(result)
        tail = reference[reference.mach > h.mach.iloc[-1]]
        ax.plot(tail.mach, tail.thrust_n, ':', color='#007f86', lw=2)
        ax.plot(tail.mach, tail.drag_n, ':', color='#b85025', lw=2)
        ax.annotate('Push and drag meet\nnear Mach 0.939', xy=(h.mach.iloc[-1], h.drag_n.iloc[-1]),
                    xytext=(.815, 310), arrowprops={'arrowstyle':'->','color':'#374151'}, fontsize=10)
    ax.set(xlabel='Mach (1.0 = speed of sound)', ylabel='Force [N]', xlim=(.8,1.002), ylim=(0,380))
    ax.legend(loc='lower left', fontsize=9)
    lower = axes[1, col]
    lower.plot(h.time_s, h.mach, color=colors[col], lw=2.7, label='Computed flight')
    if not result.hold_trajectory.empty:
        hold = result.hold_trajectory
        lower.plot(hold.time_s, hold.mach, '--', color=colors[col], lw=2.7, label='Extension and 5-second hold')
    lower.axhline(1.0, color='#6b7280', linestyle=':', lw=1.5)
    lower.set(xlabel='Time starting at Mach 0.8 [s]', ylabel='Mach', ylim=(.79,1.025))
    lower.legend(loc='lower right', fontsize=9)

axes[0,0].set_title('PASS even with pessimistic drag\n600 N rating · 0.08 m² wing · 6,000 m', fontsize=12, color='#007f86')
axes[0,1].set_title('FAIL with baseline drag\n450 N rating · 0.12 m² wing · 3,000 m', fontsize=12, color='#b85025')
axes[1,0].set_title('Mach 1 in 18.9 s; then holds Mach 1.01', fontsize=12)
axes[1,1].set_title('Levels off below Mach 1; fuel remains', fontsize=12)
fig.suptitle('What the simulation actually shows\nTwo designs at the same 24 kg starting mass, including 3 kg fuel', fontsize=16)
fig.subplots_adjust(left=.075, right=.98, bottom=.15, top=.82, hspace=.40, wspace=.22)
fig.text(.5,.018,'Solid lines = simulated path. Dotted force lines = unflown estimates at initial mass/altitude.\nIllustrative engine and drag assumptions — these curves are not flight-test data.',ha='center',fontsize=10,color='#4b5563')
fig.savefig(OUT / 'pass_vs_fail.png', dpi=160)
plt.close(fig)

matched = all_cases[(all_cases.empty_mass_kg == 21) & (all_cases.initial_fuel_kg == 3)]
matched.to_csv(OUT / 'same_mass_comparisons.csv', index=False)
print('Saved', OUT / 'pass_vs_fail.png')
