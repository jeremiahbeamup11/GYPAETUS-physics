"""One P550 dart geometry, component drag and explicitly unvalidated closures.

No airframe search. Dimensions in metres; drag is assembled as Cd*A [m²].
See docs/dart_geometry.md for provenance, equations and applicability limits.
"""
from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.interpolate import PchipInterpolator

from .models import Engine


@dataclass(frozen=True)
class DartLayout:
    name: str = 'P550-dart-01'
    length_m: float = 2.4
    case_diameter_m: float = .1786
    engine_nominal_length_m: float = .419
    engine_packaging_length_m: float = .427
    engine_mass_kg: float = 5.4
    mount_span_m: float = .230
    inlet_highlight_diameter_m: float = .200
    inlet_clear_diameter_m: float = .190
    duct_outer_diameter_m: float = .194
    aft_opening_diameter_m: float = .108
    skin_allowance_m: float = .002
    radial_clearance_m: float = .005
    wing_area_m2: float = .08  # gross reference, including buried centre
    wing_aspect_ratio: float = 3.0
    wing_taper: float = .35
    wing_sweep_deg: float = 50.0
    wing_root_le_m: float = .80
    wing_thickness_ratio: float = .04
    fin_count: int = 4
    fin_height_m: float = .08
    fin_root_chord_m: float = .16
    fin_tip_chord_m: float = .06
    fin_root_le_m: float = 2.13
    fin_sweep_deg: float = 40.0
    fin_thickness_ratio: float = .04
    tank_start_m: float = .30
    tank_end_m: float = .95
    tank_packing_fraction: float = .75
    fuel_density_kg_m3: float = 800.0
    fuel_ullage_fraction: float = .10

    @property
    def inlet_reference_area_m2(self):
        return math.pi * (self.inlet_highlight_diameter_m / 2)**2

    @property
    def engine_start_m(self):
        return 1.30

    @property
    def span_m(self):
        return math.sqrt(self.wing_area_m2 * self.wing_aspect_ratio)

    @property
    def root_chord_m(self):
        return 2*self.wing_area_m2/(self.span_m*(1+self.wing_taper))


@dataclass(frozen=True)
class P550Engine(Engine):
    sea_level_static_thrust_n: float = 550.0
    tsfc_kg_n_s: float = .144/3600
    hardware_mass_kg: float = 5.4
    model: str = 'JetCat P550-PRO-S'

    def __post_init__(self):
        super().__post_init__()
        if (self.sea_level_static_thrust_n != 550 or self.hardware_mass_kg != 5.4
                or not math.isclose(self.tsfc_kg_n_s, .144/3600)
                or self.propulsion_class != 'turbojet'):
            raise ValueError('P550 lock is 550 N, 5.4 kg, 0.144 kg/N/h, turbojet')

    def performance(self, mach, altitude_m, throttle=1.0):
        if altitude_m > 10000:
            raise ValueError('P550 screen is restricted to <=10 km; engine already running')
        thrust, _ = super().performance(mach, altitude_m, throttle)
        # Published maximum-RPM SFC anchors burn. Constant off-design SFC is an
        # explicit assumption, NOT an OEM altitude/Mach/part-throttle fuel map.
        return thrust, self.tsfc_kg_n_s * thrust / self.installed_factor


def wave_drag_area(x, area, modes=80, theta_count=4097):
    """Linear slender-body volume-wave functional, NOT validated transonic drag.

    B_n = 2/pi integral S'(L/2*(1+cos(theta))) sin(n theta) dtheta [m].
    D/q = pi/4 sum n B_n² [m²]. Open end pressure drag is not included.
    """
    x, area = np.asarray(x), np.asarray(area)
    if len(x) != len(area) or np.any(np.diff(x) <= 0) or np.any(area < 0):
        raise ValueError('Area stations must be ordered and nonnegative')
    theta = np.linspace(0, np.pi, theta_count)
    length = x[-1]-x[0]
    derivative = PchipInterpolator(x, area).derivative()
    slope = derivative(x[0]+length/2*(1+np.cos(theta)))
    n = np.arange(1, modes+1)
    coefficients = 2/np.pi * np.trapezoid(slope[None, :]*np.sin(n[:, None]*theta), theta, axis=1)
    return float(np.pi/4 * np.sum(n*coefficients**2))


def _appendages(x, radius, layout, strips):
    """Exterior thickness integration; wing material inside body is excluded."""
    d = layout
    dy = d.span_m/2/strips
    y = (np.arange(strips)+.5)*dy
    chord = d.root_chord_m*(1-(1-d.wing_taper)*y/(d.span_m/2))
    le = d.wing_root_le_m+y*np.tan(np.radians(d.wing_sweep_deg))
    u = (x[:, None]-le)/chord
    plan = (u >= 0) & (u <= 1) & (y[None, :] > radius[:, None])
    thickness = 4*d.wing_thickness_ratio*chord*np.clip(u,0,1)*(1-np.clip(u,0,1))
    wing_area = 2*np.sum(thickness*plan, axis=1)*dy
    wing_plan_width = 2*np.sum(plan,axis=1)*dy
    # Fins start at the outer body surface, so all fin height is exposed.
    dr = d.fin_height_m/strips
    r = (np.arange(strips)+.5)*dr
    chord_f = d.fin_root_chord_m+(d.fin_tip_chord_m-d.fin_root_chord_m)*r/d.fin_height_m
    le_f = d.fin_root_le_m+r*np.tan(np.radians(d.fin_sweep_deg))
    uf = (x[:,None]-le_f)/chord_f
    thickness_f = 4*d.fin_thickness_ratio*chord_f*np.clip(uf,0,1)*(1-np.clip(uf,0,1))
    fin_area = d.fin_count*np.sum(thickness_f,axis=1)*dr
    return wing_area, fin_area, wing_plan_width


@lru_cache(maxsize=8)
def build_layout(layout=DartLayout(), stations=2001, strips=400):
    """Area compensation on ONE prescribed volume envelope, not a design search.

    Subtract exposed wing/fin volume from a smooth target cross section wherever
    packaging permits. Constrained stations retain engine/mount/duct clearances.
    """
    d = layout
    x = np.linspace(0,d.length_m,stations)
    # Nose highlight and rear cowl are fixed. Wider body reserves standard mounts.
    smooth = lambda u: np.clip(u,0,1)**2*(3-2*np.clip(u,0,1))
    target = np.pi*(.100**2+(.124**2-.100**2)*smooth(x/.60)
                    -(.124**2-.061**2)*smooth((x-1.60)/(d.length_m-1.60)))
    # Minimum outer radius before engine: duct, skin and small routing gap.
    minimum = np.full_like(x, d.duct_outer_diameter_m/2+d.skin_allowance_m+.001)
    minimum[x < .10] = .100
    # Conservative cylindrical case through package minus 108 mm nozzle length.
    engine_case = (x >= d.engine_start_m) & (x <= d.engine_start_m+d.engine_packaging_length_m-.108)
    minimum[x >= d.engine_start_m] = d.aft_opening_diameter_m/2+d.skin_allowance_m+d.radial_clearance_m
    minimum[engine_case] = d.case_diameter_m/2+d.skin_allowance_m+d.radial_clearance_m
    # Drawing brackets at 157 and 247 mm from forward package datum, 20 mm wide.
    for centre in (d.engine_start_m+.157, d.engine_start_m+.247):
        bracket = np.abs(x-centre) <= .010
        minimum[bracket] = d.mount_span_m/2+d.skin_allowance_m+d.radial_clearance_m
    minimum[-1] = .061
    radius = np.sqrt(target/np.pi)
    for _ in range(12):
        wing, fins, width = _appendages(x,radius,d,strips)
        body = np.maximum(target-wing-fins,np.pi*minimum**2)
        radius = np.sqrt(body/np.pi)
    wing, fins, width = _appendages(x,radius,d,strips)
    total = body+wing+fins
    slope = np.gradient(radius,x)
    wetted = float(np.trapezoid(2*np.pi*radius*np.sqrt(1+slope**2),x))
    exposed = float(np.trapezoid(width,x))
    tail_plan = d.fin_count*d.fin_height_m*(d.fin_root_chord_m+d.fin_tip_chord_m)/2
    # Tank capacity is a packing estimate inside the annulus, not a tank drawing.
    tank = (x >= d.tank_start_m) & (x <= d.tank_end_m)
    usable_annulus = np.maximum(0,np.pi*((radius-d.skin_allowance_m-.003)**2-(d.duct_outer_diameter_m/2+.003)**2))
    tank_gross = float(np.trapezoid(usable_annulus[tank],x[tank])*d.tank_packing_fraction)
    metrics = dict(
        inlet_reference_area_m2=d.inlet_reference_area_m2,
        max_body_diameter_m=float(2*radius.max()),
        max_body_frontal_area_m2=float(body.max()),
        body_wetted_area_m2=wetted,
        exposed_wing_planform_m2=exposed,
        wing_wetted_area_m2=2*exposed*(1+2*d.wing_thickness_ratio**2),
        fin_planform_m2=tail_plan,
        fin_wetted_area_m2=2*tail_plan*(1+2*d.fin_thickness_ratio**2),
        tank_gross_volume_l=tank_gross*1000,
        tank_usable_fuel_kg=tank_gross*(1-d.fuel_ullage_fraction)*d.fuel_density_kg_m3,
        min_packaging_radial_margin_m=float((radius-minimum).min()),
        compensated_wave_area_m2=wave_drag_area(x,total),
        uncompensated_wave_area_m2=wave_drag_area(x,target+wing+fins),
        volume_m3=float(np.trapezoid(total,x)),
        max_radius_over_length=float(radius.max()/d.length_m),
    )
    return dict(x_m=x,body_radius_m=radius,body_area_m2=body,wing_area_m2=wing,
                fin_area_m2=fins,total_area_m2=total,target_area_m2=target,
                min_radius_m=minimum,metrics=metrics)


# Only the wave term varies. Body/wing/tail drag is identical in all envelopes.
# These are uncertainty assumptions on THIS geometry, not the old whole-aircraft
# polars or confidence intervals. No coefficients are tuned to a desired outcome.
ENVELOPES = {
    'optimistic': dict(wave_multiplier=.75, wave_onset=.85),
    'baseline': dict(wave_multiplier=1.0, wave_onset=.80),
    'pessimistic': dict(wave_multiplier=1.5, wave_onset=.75),
}


@dataclass(frozen=True)
class DartPolar:
    # Store only scalars, so exact simulation inputs remain JSON serializable.
    name: str = "baseline"
    body_length_m: float = 2.4
    body_wetted_m2: float = 0.0
    wing_wetted_m2: float = 0.0
    fin_wetted_m2: float = 0.0
    wing_chord_m: float = .1632993162
    fin_chord_m: float = .11
    inlet_area_m2: float = math.pi*.1**2
    geometry_wave_area_m2: float = 0.0
    viscous_multiplier: float = 1.15
    external_pressure_cd: float = .05
    wave_multiplier: float = 1.0
    wave_onset: float = .80

    def profile_drag_areas(self,mach,reynolds,aircraft):
        re_per_m = reynolds/aircraft.chord_m
        # Fully turbulent flat-plate mean Cf, no laminar-flow credit. Compressible
        # viscous/form effects are covered only by the declared multipliers.
        cf = lambda length: .074/(re_per_m*length)**.2
        body_friction = self.viscous_multiplier*cf(self.body_length_m)*self.body_wetted_m2
        external = self.external_pressure_cd*self.inlet_area_m2
        wing = self.viscous_multiplier*cf(self.wing_chord_m)*self.wing_wetted_m2
        tail = self.viscous_multiplier*cf(self.fin_chord_m)*self.fin_wetted_m2
        u = np.clip((mach-self.wave_onset)/(1.02-self.wave_onset),0,1)
        # Explicit transonic closure: no validated CFD or pressure-recovery map.
        wave = self.wave_multiplier*self.geometry_wave_area_m2*float(u*u*(3-2*u))
        body = body_friction+external
        return dict(parasite_drag_area_m2=body+wing+tail,wave_drag_area_m2=wave,
                    body_drag_area_m2=body,wing_profile_drag_area_m2=wing,tail_drag_area_m2=tail,
                    body_friction_drag_area_m2=body_friction,external_pressure_drag_area_m2=external)


def geometry_polar(name,layout=DartLayout()):
    m = build_layout(layout)['metrics']
    return DartPolar(name=name,body_length_m=layout.length_m,
        body_wetted_m2=m['body_wetted_area_m2'],wing_wetted_m2=m['wing_wetted_area_m2'],
        fin_wetted_m2=m['fin_wetted_area_m2'],wing_chord_m=layout.wing_area_m2/layout.span_m,
        inlet_area_m2=layout.inlet_reference_area_m2,geometry_wave_area_m2=m['compensated_wave_area_m2'],
        **ENVELOPES[name])


# Allocations, not weighed parts; engine counted once and no extra engine mass
# added to the original total. The 21 kg budget carries 3 kg extra reserve.
MASS_BUDGET_KG = {
    'P550-PRO-S engine (manufacturer)':5.4,
    'body shell and frames (allocation)':3.2,
    'wing and fins (allocation)':1.8,
    'inlet and duct (allocation)':1.2,
    'mounts and thermal protection (allocation)':1.0,
    'tank and plumbing (allocation)':.8,
    'avionics and actuators (allocation)':.8,
    'battery and wiring (allocation)':.5,
    'recovery equipment (allocation)':1.0,
    'fasteners and miscellaneous (allocation)':.5,
    'unallocated reserve in 18 kg budget':1.8,
}
