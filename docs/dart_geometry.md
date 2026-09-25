# P550-dart-01: fixed geometry and force-first model

This is the next model after the four-design reference-area stress test. It replaces
600 N with a sourced P550 engine and replaces the old whole-aircraft polars with
three dimensional drag terms. It does not enlarge or rerun the original grid.

## Engine lock

[JetCat's P550-PRO-S product page](https://www.jetcat.de/en/productdetails/produkte/jetcat/produkte/Professionell/P550%20PRO-S)
lists 550 N, 175 mm diameter, 419 mm length, 5.4 kg, SFC 0.144 kg/N/h and
1650 ml/min full-load fuel flow. We reserve a conservative 178.6 mm case per the
user's instruction. The [linked drawing](https://www.jetcat.de/jetcat/produkte/pro/p550-pro/JetCat%20P550%20Pro%20Size.PDF)
shows 427 mm overall, 230 mm mounting span and 108 mm nozzle maximum diameter.
Those drawing dimensions are conservative packaging reservations, not a claim
that every P550 variant has the same interface. The compressor face is **not**
identified by the case diameter.

The engine's rated thrust, installed mass and fuel anchor move together:

```
T_uninstalled = 550 * (rho/rho_ISA_SL)^0.75 * speed_factor(M) * throttle
T_installed   = installation_factor * T_uninstalled
fuel_flow     = (0.144/3600) * T_uninstalled
speed_factor knots: M=[0, .4, .8, 1, 1.2], factor=[1, .97, .90, .84, .79]
installation_factor = .85, .80, .75 (total losses, applied once)
```

Altitude/Mach lapse is the **existing unvalidated map**, anchored to 550 N. It
is not an OEM altitude/Mach map. Maximum-RPM SFC remains constant off design as
an explicit assumption, replacing the old generic temperature/Mach fuel correction.
The ISA static fuel anchor is 0.022 kg/s, matching 1650 ml/min at 800 kg/m³.
Part-throttle fuel consumption is not validated. The engine is assumed already
running at 6 km; startup and the climb to the entry condition are outside this
slice. The user-supplied PRO-line 2600 m start / 10000 m operation limits are
mission constraints, not proof of a P550 Mach 1 installation.

## One geometric object

`DartLayout` fixes 2.4 m length, 200 mm inlet highlight, 190 mm aperture,
194 mm duct outside diameter, a 178.6 mm engine case and clearance for 230 mm
mounts. Maximum body diameter is 248 mm. The 200 mm circle is a reference for
external pressure coefficients, **not the maximum body cross section**.

Engine package x=1.300–1.727 m; the remaining 0.673 m afterbody assumes an
exhaust extension. Its thermal, back-pressure and net-thrust consequences are
unresolved within the declared total installation losses. A simpler flow-through
installation is not silently claimed. The inlet lip contour and compressor-face
adapter are also unresolved; specifying an aperture does not establish recovery.

The gross wing has S=.08 m², AR=3, taper=.35, leading-edge sweep 50 degrees,
root leading edge x=.80 m, t/c=.04. Four radial fins have .08 m height,
.16/.06 m root/tip chord, 40 degree sweep, root leading edge x=2.13 m, t/c=.04.
These are geometry assumptions, not flight-stability decisions.

For section coordinate u between leading and trailing edge, thickness is
`4*(t/c)*chord*u*(1-u)`. Sections are integrated in strips; wing material inside
the body is excluded. Gross S remains the lift reference, but only about .030 m²
is exposed wing. The existing induced-drag model therefore remains a weak
approximation to the combined wing/body lift, and is explicitly flagged.

The target total cross section uses smooth cubic transitions from the inlet to
a .124 m radius envelope, and from x=1.6 m to the aft .061 m cowl radius.
Body area is target minus exposed wing/fin area, constrained by duct/case/mount
clearances. This is direct area compensation, not optimization for a thrust pass.
Normal section area, radius, required envelope and appendage contributions are
exported at 2001 stations. [NASA's area-rule history](https://www.nasa.gov/history/SP-4219/Chapter5.html)
explains why the combined cross section matters and why engine packaging can
prevent a narrow waist.

## Three force terms, one reference convention

All component models return drag area K = CD*A [m²]; forces are q*K. Dividing the
sum by .08 m² produces a wing-referenced coefficient only for reporting. Fixed
geometry cannot shrink when that reference is changed.

1. **Dbody** = q*(1.15*Cf_body*body_wetted_area + .05*A_inlet).
   The fixed .05 coefficient covers unresolved external inlet/cowl/nozzle/base
   pressure drag as a sensitivity assumption. It is not measured, and does not
   include a second ram-drag or thrust-loss deduction. Inlet recovery, internal
   flow and exhaust thrust losses are assigned to total installation loss.
2. **Dwing_tail** = q*1.15*(Cf_wing*wing_wetted_area + Cf_fin*fin_wetted_area)
   + q*S*(CL²/(pi*e*AR) + .002 trim CD). All these values are identical across
   the wave envelopes for a given Mach and mass. e=.75 and AR=3 are inherited
   approximations. Wetted appendage areas are twice exposed planform with a
   small explicit thickness correction `1+2*(t/c)^2`.
3. **Dwave** = q*K_geometry*wave_multiplier*ramp(M).

Fully turbulent mean flat-plate skin friction is `Cf=.074/Re_length^.2`, with
body length, fixed wing reference chord and fin mean chord as the respective
lengths. No laminar-flow benefit is taken. This classical relation is summarized
in [NASA/CR-2006-214679](https://ntrs.nasa.gov/api/citations/20060053240/downloads/20060053240.pdf).
Its use on this transonic body and the fixed 1.15 viscous allowance remain
uncalibrated. The pressure coefficient .05 is a declared assumption, not a value
inferred from that source.

## Only the wave term has three envelopes

The linear volume-wave functional follows the Fourier area-derivative method in
[this primary comparison study](https://www.mdpi.com/2226-4310/11/5/359):

```
x(theta) = L/2 * (1 + cos(theta))
B_n = (2/pi) integral_0^pi A'(x(theta))*sin(n*theta) dtheta
K_geometry = (pi/4) sum_n n*B_n^2
```

B_n has dimensions of length; K has dimensions of area. The implementation uses
80 modes and 4097 angular quadrature points. It is independently checked against
the closed-body Sears–Haack result `K=(9*pi/2)*(Amax/L)^2`, as well as finer
axial stations and more Fourier modes.

| Wave envelope | Multiplier on K | Ramp onset Mach |
|---|---:|---:|
| Optimistic | .75 | .85 |
| Baseline | 1.00 | .80 |
| Pessimistic | 1.50 | .75 |

The ramp is zero before onset, `u²*(3−2u)` from onset to M=1.02 and unity
above that point; `u=(M-onset)/(1.02-onset)`. These three transonic closures are
explicit sensitivity assumptions; they are **not** the original three polars,
measured bounds, confidence intervals or validation of a particular inlet.

The normal-area method does not resolve inclined Mach-plane areas, lift-dependent
wave drag, open-inlet streamtube/jet effects or transonic shock separation.
Rmax/L is about .052. The cited slender-body study does not validate this open-ended
configuration at Mach .8–1.01. In particular, numerical convergence is not physical
validation. [NACA RM A56K26](https://ntrs.nasa.gov/api/citations/19930089658/downloads/19930089658.pdf)
expressly discusses limitations of linearized theory near Mach 1.

## Twelve force cases before trajectories

Only 4 entry masses × 3 installation factors = 12 rows. Each row contains the
three wave-envelope minima on 401 Mach stations from .8 to 1.0. This is not a
new design grid. Full-interval audits are at fixed entry mass, with separate
fixed dry-mass lower-drag bounds. Nothing is labeled a flown trajectory.

A wave branch is eligible for integration only if its minimum excess thrust is
at least the existing .01 N requirement. All force cases are completed first.
An eligible trajectory still needs Mach 1, then Mach 1.01 and a five-second hold;
a nonnegative force audit alone is not an endurance pass. Skipped trajectories
have null gate/hold outcomes and a reason, rather than fabricated failures.

The 18 kg empty allocation includes the 5.4 kg engine, 10.8 kg other equipment
allocations and 1.8 kg reserve. The 21 kg budget has 4.8 kg reserve. Only the engine
is substantiated hardware mass. Tank volume includes 75% packing, 10% ullage
and 800 kg/m³ fuel density. The two lighter IDs are conditional force-audit rows,
not accepted candidates; delete them if a substantiated budget exceeds 18 kg.

If every baseline row at 15% loss is negative, this corner closes under the
model. Stop at the table. A subsequent task can change bay geometry or the area
plot; do not add cases to the old sweep to bypass that result.
