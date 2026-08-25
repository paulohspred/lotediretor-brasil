from __future__ import annotations

import math
from typing import Any

ENVIRONMENT_SOLVER_VERSION = 'aitec-environment-v20.1'


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _status_from_gate(value: float, threshold: float | None, *, minimum: bool) -> tuple[str, dict | None]:
    if threshold is None:
        return 'UNVERIFIED', None
    passed = value + 1e-12 >= threshold if minimum else value <= threshold + 1e-12
    return ('PASS' if passed else 'FAIL'), {
        'status': 'PASS' if passed else 'FAIL',
        'observed': round(value, 6),
        ('minimum' if minimum else 'maximum'): float(threshold),
    }


def analyze_solar_exposure(surfaces: list[dict], sun_samples: list[dict], min_exposure_index: float | None = None) -> dict[str, Any]:
    """Compute a geometric solar-exposure index from explicit sun samples.

    This is not irradiance or energy yield. Each sample carries an explicit
    weight and each surface an explicit shading factor. Angles are degrees,
    azimuth clockwise from north and tilt from horizontal.
    """
    if not surfaces or not sun_samples:
        return {'status': 'NOT_PROVIDED', 'surface_results': [], 'exposure_index': None, 'hard_results': []}
    sample_weight = 0.0
    normalized_samples = []
    for raw in sun_samples:
        altitude = float(raw['altitude_deg'])
        azimuth = float(raw['azimuth_deg']) % 360.0
        weight = float(raw.get('weight', 1.0))
        if not -90 <= altitude <= 90 or weight < 0:
            raise ValueError('invalid sun sample altitude/weight')
        sample_weight += weight
        normalized_samples.append((altitude, azimuth, weight))
    if sample_weight <= 0:
        raise ValueError('sun sample total weight must be > 0')

    results = []
    area_total = 0.0
    weighted_total = 0.0
    for index, raw in enumerate(surfaces):
        name = str(raw.get('name') or f'SURFACE-{index + 1}')
        area = float(raw.get('area_m2') or 0)
        tilt = float(raw.get('tilt_deg') or 0)
        azimuth = float(raw.get('azimuth_deg') or 0) % 360.0
        shading = _clamp01(float(raw.get('shading_factor', 1.0)))
        if area <= 0 or not 0 <= tilt <= 180:
            raise ValueError(f'invalid solar surface:{name}')
        tr = math.radians(tilt)
        ar = math.radians(azimuth)
        normal = (math.sin(tr) * math.sin(ar), math.sin(tr) * math.cos(ar), math.cos(tr))
        exposure = 0.0
        for altitude, sun_azimuth, weight in normalized_samples:
            al = math.radians(altitude)
            saz = math.radians(sun_azimuth)
            sun = (math.cos(al) * math.sin(saz), math.cos(al) * math.cos(saz), math.sin(al))
            incidence = max(0.0, normal[0] * sun[0] + normal[1] * sun[1] + normal[2] * sun[2])
            exposure += incidence * weight * shading
        exposure /= sample_weight
        results.append({'name': name, 'area_m2': area, 'exposure_index': round(exposure, 6), 'shading_factor': shading})
        area_total += area
        weighted_total += exposure * area
    index = weighted_total / area_total if area_total > 0 else 0.0
    status, gate = _status_from_gate(index, min_exposure_index, minimum=True)
    hard = [] if gate is None else [{'code': 'SOLAR_EXPOSURE_MIN', **gate}]
    return {'status': status, 'exposure_index': round(index, 6), 'surface_results': results, 'hard_results': hard}


def analyze_daylight(rooms: list[dict], min_daylight_proxy: float | None = None) -> dict[str, Any]:
    """Compute a simple opening/floor-area daylight proxy from explicit factors."""
    if not rooms:
        return {'status': 'NOT_PROVIDED', 'rooms': [], 'minimum_proxy': None, 'hard_results': []}
    results = []
    for index, raw in enumerate(rooms):
        name = str(raw.get('name') or f'ROOM-{index + 1}')
        floor_area = float(raw.get('floor_area_m2') or 0)
        opening_area = float(raw.get('opening_area_m2') or 0)
        transmittance = _clamp01(float(raw.get('transmittance', 1.0)))
        sky_view = _clamp01(float(raw.get('sky_view_factor', 1.0)))
        if floor_area <= 0 or opening_area < 0:
            raise ValueError(f'invalid daylight room:{name}')
        proxy = opening_area / floor_area * transmittance * sky_view
        results.append({'name': name, 'daylight_proxy': round(proxy, 6), 'floor_area_m2': floor_area, 'opening_area_m2': opening_area})
    minimum_proxy = min(item['daylight_proxy'] for item in results)
    status, gate = _status_from_gate(minimum_proxy, min_daylight_proxy, minimum=True)
    hard = [] if gate is None else [{'code': 'DAYLIGHT_PROXY_MIN', **gate}]
    return {'status': status, 'minimum_proxy': minimum_proxy, 'rooms': results, 'hard_results': hard}


def analyze_noise(sources: list[dict], receptors: list[dict], max_noise_db: float | None = None) -> dict[str, Any]:
    """Estimate free-field point-source noise from explicit reference levels.

    Uses spherical 20*log10 distance attenuation and optional explicit loss.
    It is not an acoustic simulation and does not infer barriers/reflections.
    """
    if not sources or not receptors:
        return {'status': 'NOT_PROVIDED', 'receptors': [], 'maximum_db': None, 'hard_results': []}
    normalized_sources = []
    for index, raw in enumerate(sources):
        x = float(raw['x']); y = float(raw['y'])
        level = float(raw['reference_db'])
        reference = float(raw.get('reference_distance_m', 1.0))
        loss = max(0.0, float(raw.get('additional_loss_db', 0.0)))
        if reference <= 0:
            raise ValueError('noise reference distance must be > 0')
        normalized_sources.append((str(raw.get('name') or f'SOURCE-{index + 1}'), x, y, level, reference, loss))
    outputs = []
    for index, raw in enumerate(receptors):
        name = str(raw.get('name') or f'RECEPTOR-{index + 1}')
        rx = float(raw['x']); ry = float(raw['y'])
        energy = 0.0
        contributions = []
        for source_name, sx, sy, level, reference, loss in normalized_sources:
            distance = max(reference, math.hypot(rx - sx, ry - sy))
            observed = level - 20.0 * math.log10(distance / reference) - loss
            energy += 10.0 ** (observed / 10.0)
            contributions.append({'source': source_name, 'distance_m': round(distance, 3), 'level_db': round(observed, 3)})
        total = 10.0 * math.log10(energy) if energy > 0 else -math.inf
        outputs.append({'name': name, 'level_db': round(total, 3), 'contributions': contributions})
    maximum = max(item['level_db'] for item in outputs)
    status, gate = _status_from_gate(maximum, max_noise_db, minimum=False)
    hard = [] if gate is None else [{'code': 'NOISE_MAX_DB', **gate}]
    return {'status': status, 'maximum_db': maximum, 'receptors': outputs, 'hard_results': hard}


def analyze_wind(scenarios: list[dict], receptors: list[dict], max_comfort_speed_mps: float | None = None) -> dict[str, Any]:
    """Compute an explicit-factor wind comfort proxy; this is not CFD."""
    if not scenarios or not receptors:
        return {'status': 'NOT_PROVIDED', 'receptors': [], 'maximum_speed_mps': None, 'hard_results': []}
    normalized = []
    for index, raw in enumerate(scenarios):
        speed = float(raw.get('speed_mps') or 0)
        weight = float(raw.get('weight', 1.0))
        exposure = float(raw.get('exposure_factor', 1.0))
        if speed < 0 or weight < 0 or exposure < 0:
            raise ValueError('invalid wind scenario')
        normalized.append((str(raw.get('name') or f'WIND-{index + 1}'), speed, weight, exposure))
    weight_total = sum(item[2] for item in normalized)
    if weight_total <= 0:
        raise ValueError('wind total weight must be > 0')
    outputs = []
    for index, raw in enumerate(receptors):
        name = str(raw.get('name') or f'RECEPTOR-{index + 1}')
        shelter = max(0.0, float(raw.get('shelter_factor', 1.0)))
        weighted = 0.0
        peak = 0.0
        for _, speed, weight, exposure in normalized:
            local = speed * exposure * shelter
            weighted += local * weight
            peak = max(peak, local)
        outputs.append({'name': name, 'weighted_speed_mps': round(weighted / weight_total, 6), 'peak_speed_mps': round(peak, 6), 'shelter_factor': shelter})
    maximum = max(item['peak_speed_mps'] for item in outputs)
    status, gate = _status_from_gate(maximum, max_comfort_speed_mps, minimum=False)
    hard = [] if gate is None else [{'code': 'WIND_COMFORT_MAX_SPEED', **gate}]
    return {'status': status, 'maximum_speed_mps': maximum, 'receptors': outputs, 'hard_results': hard}


def analyze_environment(
    solar: dict | None = None,
    daylight: dict | None = None,
    noise: dict | None = None,
    wind: dict | None = None,
) -> dict[str, Any]:
    sections = {
        'solar': analyze_solar_exposure(**solar) if solar else {'status': 'NOT_PROVIDED', 'hard_results': []},
        'daylight': analyze_daylight(**daylight) if daylight else {'status': 'NOT_PROVIDED', 'hard_results': []},
        'noise': analyze_noise(**noise) if noise else {'status': 'NOT_PROVIDED', 'hard_results': []},
        'wind': analyze_wind(**wind) if wind else {'status': 'NOT_PROVIDED', 'hard_results': []},
    }
    statuses = [item['status'] for item in sections.values() if item['status'] != 'NOT_PROVIDED']
    if not statuses:
        status = 'NOT_PROVIDED'
    elif 'FAIL' in statuses:
        status = 'FAIL'
    elif 'UNVERIFIED' in statuses:
        status = 'UNVERIFIED'
    else:
        status = 'PASS'
    return {
        'status': status,
        'solver_version': ENVIRONMENT_SOLVER_VERSION,
        **sections,
        'hard_results': [gate for item in sections.values() for gate in item.get('hard_results', [])],
        'limitations': [
            'Sol é índice geométrico de incidência, não irradiância/energia.',
            'Daylight é proxy abertura/área com fatores explícitos, não simulação luminotécnica normativa.',
            'Ruído usa propagação pontual em campo livre, sem reflexões, difração ou barreiras inferidas.',
            'Vento usa fatores explícitos e não substitui CFD, túnel de vento ou avaliação profissional.',
            'Sem threshold explícito a seção permanece UNVERIFIED e não é promovida a PASS.',
        ],
    }
