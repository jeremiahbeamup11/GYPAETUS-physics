# Assumptions and design-gate rules

Read these rules before interpreting any result. All performance maps and design
limits supplied here are hypotheses. There is no measured GYPAETUS data in this
repository and no calibrated engine or aerodynamic model.

## 1. Scope, units, and mass

- SI internally: kg, m, s, N, Pa, K; angles are explicitly suffixed `_deg` or `_rad`.
  Mach, lift coefficients and drag coefficients are dimensionless.
- “25 kg / 55 lb” is ambiguous because 55 lb = **24.94758035 kg**, not 25 kg.
  The gate enforces the stricter value. Pounds mean mass; `N_PER_LBF` is separate.
- Initial mass = empty mass + usable fuel. Empty mass includes the installed
  engine, inlet, nozzle, tanks, avionics, control system, structure, and any
  unusable fuel. There is no free engine mass or uncounted hardware allowance.
- Initial conditions are at Mach 0.8. Fuel used for takeoff, climb, and acceleration
  to Mach 0.8 is outside this mission. A gate pass does not prove takeoff mass is
  under the cap or that the aircraft can reach these initial conditions.
- Air-breathing propulsion only. No rocket boost, stored oxidizer, launch energy,
  downhill flight path, or gravitational acceleration from descent is credited.
- Still, dry standard air; no wind, gusts or atmospheric uncertainty model.

## 2. What “pass” means

`gate_pass` is true only when the integration completes the **entire Mach
0.8→1.0 interval** within 120 s (configurable) and every check below passes:

1. Initial total mass ≤24.94758035 kg; fuel burn subsequently reduces mass.
2. No descent: prescribed flight-path angle γ is 0–10°, with nondecreasing altitude.
3. Installed net thrust exceeds drag over the evaluated path. The default
   numerical force margin is 0.01 N, chosen to reject equilibrium/stagnation.
4. Tangential accelerating force `T − D − mg sin(γ)` also meets that margin.
   For level flight this reduces to `T − D`. Positive excess thrust alone does
   not guarantee acceleration in a climb.
5. Fuel never becomes negative. Fuel exhaustion before completion fails.
6. Required `CL ≤ 0.60`, an assumed transonic stall/buffet limit.
7. Dynamic pressure `q ≤ 65,000 Pa`, an assumed structural screening limit.

Reaching exactly Mach 1 completes the numerical gate. It is **not supersonic
endurance**. `endurance_pass` separately requires accelerating to Mach 1.01,
then maintaining that Mach in level flight for five seconds with usable fuel
and sufficient thrust. Both are configurable. For a climbing entry, leveling
off is idealized as instantaneous; maneuver loads and transition trim are omitted.
The acceleration budget is shared by the Mach 1 gate and acceleration to the
hold condition. Hold time is additional. Disabling the hold produces an
unevaluated result, not a pass.

Failure to accelerate does not by itself predict a dive: the aircraft might
maintain level flight at a lower speed. This model stops the prescribed run;
it does not simulate pilot recovery, a glide, or a descent.

## 3. Atmosphere

The dry U.S. Standard Atmosphere 1976 lower layers supply temperature, pressure,
density, viscosity, and local sound speed for **geometric altitude 0–20 km**.
Geometric altitude `z` is converted to geopotential height
`H = Re z / (Re + z)` using `Re = 6,356,766 m`.

- Up to H=11,000 m: `T = 288.15 − 0.0065 H`; pressure follows the hydrostatic
  ideal-gas lapse-rate equation from 101,325 Pa.
- Above H=11,000 m: T=216.65 K and pressure decays exponentially.
- `ρ = p/(R T)`, `a = sqrt(1.4 R T)`, `R = 287.05287 J/(kg K)`.
- Sutherland viscosity: reference 1.716×10⁻⁵ Pa·s at 273.15 K, S=110.4 K.

Mach is always `V/a(z)`, with V true airspeed. In a climb, both atmosphere and
Mach are recalculated from current altitude. Integration stops at 19,900 m to
keep numerical solver stages inside the 20 km atmosphere domain. No extrapolation
is permitted by the public atmosphere or engine functions.

## 4. Lift and drag

Straight, unbanked, prescribed-γ point-mass flight assumes the aircraft can trim.
Thrust is aligned with velocity and has no normal component. No pitch dynamics,
turn loads, or changing flight-path angle is solved.

```
q  = ½ ρ V²
L  = mg cos(γ)              # L = mg for level flight
CL = L / (q S)
CD = CD_parasite + CL²/(π e AR) + CD_wave + CD_trim
D  = q S CD
```

All coefficients use **wing planform area S**. Default AR=3, e=0.75,
trim CD=0.002. Effective chord is `sqrt(S/AR)`, which assumes an equivalent
rectangular planform, not an actual tapered wing geometry.

| Drag assumption | CD0 at reference Reynolds number | Peak wave CD | Rise onset Mach |
| --- | ---: | ---: | ---: |
| Optimistic | 0.016 | 0.018 | 0.82 |
| Baseline | 0.022 | 0.035 | 0.78 |
| Pessimistic | 0.030 | 0.060 | 0.74 |

Wave drag rises via smoothstep `3x²−2x³`, where x spans onset to the peak at
Mach 1.02. Beyond the peak it decays as `0.65 + 0.35 exp(−((M−1.02)/0.16)²)`
times the peak coefficient. This is an **invented sensitivity family**, not a
published transonic polar. It represents a drag rise rather than a constant CD.
No claimed confidence interval or probability attaches to these three curves.

Reynolds number is `ρ V chord/μ`. The viscous share (default 65%) of CD0 is
scaled by `(Re/4e6)^−0.2`; the remaining 35% is unchanged. This is a simple
turbulent-friction sensitivity, not a transition/separation/compressibility model.
It does not validate extrapolation to a particular small wing.

Wave CD is additionally multiplied by
`area_rule_factor × (10/slenderness)²`, with both default factors giving unity.
This allows shape sensitivity only. It does not compute an area distribution,
an area-rule optimum, shock interactions, or actual wave drag from CAD.

## 5. Engine and fuel map

The default is a turbine surrogate with a **450 N sea-level static uninstalled
net-thrust rating**, TSFC=4×10⁻⁵ kg/(N·s), installation multiplier 0.85, and
altitude scaling `(ρ/ρSL)^0.75`. These are editable assumptions, not a named
engine's specifications. The domain is Mach 0–1.2 and geometric altitude 0–20 km.

| Mach knot | 0 | 0.4 | 0.8 | 1.0 | 1.2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Turbojet speed multiplier | 1.00 | 0.97 | 0.90 | 0.84 | 0.79 |
| Turbofan speed multiplier | 1.00 | 0.90 | 0.76 | 0.66 | 0.58 |

Linear interpolation connects knots. Uninstalled thrust equals bench rating
times altitude factor, speed factor and throttle. Installed thrust is 85% of
that value by default; installation loss does **not** reduce fuel flow.
The map already represents net thrust: do not subtract ram drag again.

Fuel flow is uninstalled thrust times the base TSFC and
`(1+0.15M) sqrt(T/288.15) (1+0.2(1−throttle))`. Throttle=0 models engine-off,
with zero thrust and fuel flow; idle, spool dynamics, thermal limits, inlet
unstart, and fuel scheduling are absent. The same configurable TSFC parameter
is available for each class; no measured efficiency comparison is implied.

`ramjet_assist` retains the turbojet core and adds a hypothetical assist term
starting above Mach 0.9, reaching the specified assist fraction at Mach 1.2.
Assist thrust scales with density and throttle, and assist fuel uses 1.5 times
core TSFC. This is only an interface/sensitivity placeholder; no real ramjet
operation at these speeds is asserted. A ramjet-only class is rejected.

## 6. Equations, integration, and numerical evidence

```
dV/dt     = (T − D)/m − g sin(γ)
dfuel/dt  = −fuel_flow
dz/dt     = V sin(γ)
m         = empty_mass + fuel
Ps        = (T − D) V / (mg)
```

Net engine thrust already accounts for propulsion momentum flux. An additional
`V dm/dt` term would double-count the open-system propulsion contribution.
Specific excess power Ps is split between climbing and kinetic energy change:
`Ps = dz/dt + V(dV/dt)/g`. Thus a positive Ps in a climb need not mean increasing V.

SciPy RK45 uses relative tolerance 10⁻⁸, absolute tolerance 10⁻¹⁰, and default
maximum step 0.25 s (never above 0.5 s). Terminal events detect Mach completion,
fuel exhaustion, insufficient accelerating force, CL/q limits and altitude limit.
Post-integration checks use solver nodes, ≤0.05 s samples, and a Mach grid with
nominal spacing ≤0.0002 along a monotonic trajectory. This is numerical evidence,
not a mathematical guarantee of positivity at every real-valued Mach. Inputs with
sharper calibrated features require a smaller step and renewed convergence checks.
Tiny fuel-event roundoff is clamped to zero; fuel exhaustion is still a stop event.

The hold uses level flight with throttle selected to balance drag, bounded by
the mission's available throttle. Decreasing fuel mass updates lift, drag, and
fuel flow. It does not reuse initial fuel or ignore the acceleration to Mach 1.01.

Dashed/dotted thrust and drag curves over the full gate are evaluated at the
**initial mass and altitude**. Solid curves cover only the integrated trajectory.
For climbs the entry-condition curves do not represent the later atmosphere.

## 7. Sweep, robustness, and unresolved design work

The default Cartesian grid covers S=(0.08,0.12,0.18) m², bench thrust=(300,450,600) N,
fuel=(1,3) kg, empty mass=(18,21) kg, altitude=(0,3000,6000) m and three drag cases.
That is 108 parameter combinations ×3 assumed polars =324 runs. No independence
between engine thrust, engine mass, tank volume, wing mass or geometry is physically
established by this grid. It is a search of assumptions, not a catalogue of aircraft.

The table distinguishes optimistic-only, baseline-sensitive, all-three-polar
and all-three-failed combinations. An all-three-polar pass means robustness
**only to this selected drag family**, not overall design robustness. The pass/fail
maps use installed T/W at Mach 0.8 and initial W/S. Coincident coordinates with
different outcomes are marked mixed; they are not hidden by overplotting.

The q cap is a configurable screen, not a calculated structural allowable. A
separate flag requests flutter analysis at q≥40 kPa or Mach≥0.85. There is no
flutter solver or validated flutter boundary. Trim drag is budgeted, but tail
volume, control authority, center-of-gravity travel, static margin and stability
remain unresolved and are flagged on every run.

Ground-roll estimates assume a stated landing CLmax=1.2, liftoff=1.2Vs,
approach=1.3Vs, constant representative takeoff acceleration at 0.7 liftoff speed
with half the weight on the wheels, rolling friction=0.03, and landing braking
friction=0.3. Landing roll ignores aerodynamic drag and reverse thrust. They use
the transonic-entry mass and runway altitude zero by default; they do not include
takeoff fuel, flare, reaction, obstacles, slope, wind, ground effect or reserves.
These estimates do not clear runway feasibility.

## 8. Reproducibility

Record inputs with each result. Run tests and execute the entire notebook with a
fresh kernel. The final notebook cell builds its conclusion from the freshly
computed table; never hand-edit that conclusion to claim a pass. The supplied
fresh-kernel script clears old outputs and fails on any cell error. Do not replace
missing empirical inputs with authoritative-looking constants.

