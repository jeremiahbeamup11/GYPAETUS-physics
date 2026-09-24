"""SI constants; pounds here mean mass, never force."""

G0 = 9.80665  # m/s²
R_AIR = 287.05287  # J/(kg K)
GAMMA_AIR = 1.4
KG_PER_LB = 0.45359237  # exact
M_PER_FT = 0.3048  # exact
N_PER_LBF = KG_PER_LB * G0
MASS_LIMIT_KG = min(25.0, 55.0 * KG_PER_LB)
EARTH_RADIUS_M = 6_356_766.0


def lb_to_kg(value: float) -> float:
    return value * KG_PER_LB


def ft_to_m(value: float) -> float:
    return value * M_PER_FT

