# Model sources and provenance

The following primary references support the physical equations. They do **not**
validate this repository's engine multipliers, transonic drag curves, mass budget,
stall/buffet bound, dynamic-pressure limit or flutter flag.

- [U.S. Standard Atmosphere, 1976, NASA-TM-X-74335](https://ntrs.nasa.gov/citations/19770009539):
  basis for the lower-atmosphere hydrostatic layers, thermodynamic constants,
  geometric/geopotential conversion and transport-property approximation.
- [NASA Glenn: Drag Equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/drag-equation/):
  reference-area convention and `D = CD ρV²S/2`.
- [NASA Glenn: Induced Drag Coefficient](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/induced-drag-coefficient/):
  `CDi = CL²/(π AR e)`. Its use here remains a low-order approximation across
  transonic flow, not an assertion that incompressible lifting-line theory is exact.
- [NASA Glenn: Turbojet Thrust](https://www.grc.nasa.gov/www/k-12/airplane/turbth.html):
  distinction between gross and net thrust, including incoming-flow momentum.
- [NASA Glenn: Specific Fuel Consumption](https://www.grc.nasa.gov/WWW/k-12/airplane/sfc.html):
  TSFC definition, `fuel_mass_flow = TSFC × thrust`, and dependence on conditions.

The Reynolds power-law sensitivity, smooth wave-drag shape, slenderness
multiplier, installed-thrust correction, engine speed/altitude/throttle factors,
ramjet-assist placeholder and ground-roll estimates are explicitly chosen
engineering simplifications. None is presented as data extracted from these sources.

Validation consists of atmosphere reference points, lift and energy balances,
fuel conservation, map behavior, rejection of invalid inputs, hard failure cases,
step-size convergence, sweep completeness, and fresh-kernel notebook execution.
Empirical validation remains outstanding.

