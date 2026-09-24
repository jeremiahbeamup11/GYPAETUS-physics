"""Dry 1976 standard atmosphere, geometric altitude 0–20 km."""

from dataclasses import dataclass
import math

from .constants import EARTH_RADIUS_M, G0, GAMMA_AIR, R_AIR


@dataclass(frozen=True)
class Atmosphere:
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    sound_speed_m_s: float
    viscosity_pa_s: float
    sound_speed_gradient_s_inv: float


def atmosphere(altitude_m: float) -> Atmosphere:
    if not math.isfinite(altitude_m) or not 0 <= altitude_m <= 20_000:
        raise ValueError("Geometric altitude must be finite and within 0–20,000 m")
    h = EARTH_RADIUS_M * altitude_m / (EARTH_RADIUS_M + altitude_m)
    dh_dz = (EARTH_RADIUS_M / (EARTH_RADIUS_M + altitude_m)) ** 2
    lapse = -0.0065
    t11 = 288.15 + lapse * 11_000
    p11 = 101_325 * (t11 / 288.15) ** (-G0 / (R_AIR * lapse))
    if h <= 11_000:
        temperature = 288.15 + lapse * h
        pressure = 101_325 * (temperature / 288.15) ** (-G0 / (R_AIR * lapse))
        dt_dz = lapse * dh_dz
    else:
        temperature = t11
        pressure = p11 * math.exp(-G0 * (h - 11_000) / (R_AIR * t11))
        dt_dz = 0.0
    sound = math.sqrt(GAMMA_AIR * R_AIR * temperature)
    viscosity = 1.716e-5 * (temperature / 273.15) ** 1.5 * (273.15 + 110.4) / (temperature + 110.4)
    return Atmosphere(temperature, pressure, pressure / (R_AIR * temperature), sound,
                      viscosity, sound * dt_dz / (2 * temperature))

