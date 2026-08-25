from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from shapely.geometry import MultiPoint, Polygon, mapping
from shapely.ops import triangulate, unary_union

TERRAIN_SOLVER_VERSION = 'aitec-terrain-v20.1'


def _sample_xyz(raw: dict) -> tuple[float, float, float]:
    x = raw.get('x', raw.get('easting_m', raw.get('easting')))
    y = raw.get('y', raw.get('northing_m', raw.get('northing')))
    z = raw.get('z', raw.get('elevation_m', raw.get('elevation')))
    if x is None or y is None or z is None:
        raise ValueError('terrain samples require explicit x/y/z or easting/northing/elevation values')
    return float(x), float(y), float(z)


def _normalize_samples(samples: list[dict]) -> list[tuple[float, float, float]]:
    by_xy: dict[tuple[float, float], float] = {}
    for raw in samples or []:
        x, y, z = _sample_xyz(raw)
        key = (round(x, 9), round(y, 9))
        if key in by_xy and abs(by_xy[key] - z) > 1e-6:
            raise ValueError(f'duplicate terrain XY with conflicting elevation:{key[0]}:{key[1]}')
        by_xy[key] = z
    return [(x, y, by_xy[(x, y)]) for x, y in sorted(by_xy)]


def _plane_from_triangle(vertices: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = vertices
    det = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
    if abs(det) <= 1e-12:
        raise ValueError('degenerate terrain triangle')
    a = (z1 * (y2 - y3) + z2 * (y3 - y1) + z3 * (y1 - y2)) / det
    b = (z1 * (x3 - x2) + z2 * (x1 - x3) + z3 * (x2 - x1)) / det
    c = (
        z1 * (x2 * y3 - x3 * y2)
        + z2 * (x3 * y1 - x1 * y3)
        + z3 * (x1 * y2 - x2 * y1)
    ) / det
    return a, b, c


def build_tin(samples: list[dict]) -> dict:
    """Build a deterministic Delaunay TIN from explicit metric XYZ samples."""
    normalized = _normalize_samples(samples)
    if len(normalized) < 3:
        return {
            'status': 'INSUFFICIENT_DATA',
            'solver_version': TERRAIN_SOLVER_VERSION,
            'sample_count': len(normalized),
            'triangle_count': 0,
            'triangles': [],
            'reason': 'at_least_three_unique_metric_xyz_samples_required',
        }

    z_by_xy = {(round(x, 9), round(y, 9)): z for x, y, z in normalized}
    points = MultiPoint([(x, y) for x, y, _ in normalized])
    raw_triangles = triangulate(points)
    triangles = []
    for poly in raw_triangles:
        coords = list(poly.exterior.coords)[:3]
        vertices = []
        missing = False
        for x, y in coords:
            key = (round(float(x), 9), round(float(y), 9))
            if key not in z_by_xy:
                missing = True
                break
            vertices.append((float(x), float(y), float(z_by_xy[key])))
        if missing or len(vertices) != 3 or poly.area <= 1e-12:
            continue
        try:
            a, b, c = _plane_from_triangle(vertices)
        except ValueError:
            continue
        slope_ratio = math.sqrt(a * a + b * b)
        slope_percent = slope_ratio * 100.0
        slope_degrees = math.degrees(math.atan(slope_ratio))
        # Downslope azimuth clockwise from north: atan2(east, north).
        aspect = (math.degrees(math.atan2(-a, -b)) + 360.0) % 360.0 if slope_ratio > 1e-12 else None
        z_values = [v[2] for v in vertices]
        triangles.append({
            'id': '',
            'vertices': [[round(v[0], 6), round(v[1], 6), round(v[2], 6)] for v in vertices],
            'area_m2': round(float(poly.area), 6),
            'plane': {'a': a, 'b': b, 'c': c},
            'slope_percent': round(slope_percent, 6),
            'slope_degrees': round(slope_degrees, 6),
            'aspect_deg': None if aspect is None else round(aspect, 6),
            'min_elevation_m': round(min(z_values), 6),
            'max_elevation_m': round(max(z_values), 6),
            'mean_elevation_m': round(sum(z_values) / 3.0, 6),
        })

    triangles.sort(key=lambda item: tuple(tuple(v) for v in item['vertices']))
    for index, item in enumerate(triangles, start=1):
        item['id'] = f'TIN-{index:05d}'

    if not triangles:
        return {
            'status': 'INSUFFICIENT_DATA',
            'solver_version': TERRAIN_SOLVER_VERSION,
            'sample_count': len(normalized),
            'triangle_count': 0,
            'triangles': [],
            'reason': 'samples_do_not_form_non_degenerate_tin',
        }

    elevations = [z for _, _, z in normalized]
    slopes = [float(item['slope_percent']) for item in triangles]
    return {
        'status': 'CALCULATED',
        'solver_version': TERRAIN_SOLVER_VERSION,
        'sample_count': len(normalized),
        'triangle_count': len(triangles),
        'surface_area_2d_m2': round(sum(float(item['area_m2']) for item in triangles), 6),
        'min_elevation_m': round(min(elevations), 6),
        'max_elevation_m': round(max(elevations), 6),
        'slope_percent_min': round(min(slopes), 6),
        'slope_percent_max': round(max(slopes), 6),
        'slope_percent_mean': round(sum(slopes) / len(slopes), 6),
        'triangles': triangles,
        'limitations': [
            'TIN calculado somente a partir de amostras XYZ métricas fornecidas; o solver não inventa DEM/topografia.',
            'Não substitui levantamento topográfico, geotecnia, drenagem, contenções ou projeto de terraplenagem.',
        ],
    }


def _edge_intersection(p1: tuple[float, float, float], p2: tuple[float, float, float], level: float):
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    d1 = z1 - level
    d2 = z2 - level
    eps = 1e-9
    if abs(d1) <= eps and abs(d2) <= eps:
        return None
    if abs(d1) <= eps:
        return (x1, y1)
    if abs(d2) <= eps:
        return (x2, y2)
    if d1 * d2 > 0:
        return None
    t = (level - z1) / (z2 - z1)
    if t < -eps or t > 1 + eps:
        return None
    return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)


def contour_segments(tin: dict, interval_m: float, base_elevation_m: float | None = None) -> list[dict]:
    if interval_m <= 0:
        raise ValueError('contour interval_m must be > 0')
    if tin.get('status') != 'CALCULATED':
        return []
    min_z = float(tin['min_elevation_m'])
    max_z = float(tin['max_elevation_m'])
    base = math.floor(min_z / interval_m) * interval_m if base_elevation_m is None else float(base_elevation_m)
    start_index = math.ceil((min_z - base) / interval_m - 1e-12)
    end_index = math.floor((max_z - base) / interval_m + 1e-12)
    dedupe = set()
    out = []
    for index in range(start_index, end_index + 1):
        level = base + index * interval_m
        for triangle in tin['triangles']:
            vertices = [tuple(float(v) for v in row) for row in triangle['vertices']]
            points = []
            for edge in ((0, 1), (1, 2), (2, 0)):
                pt = _edge_intersection(vertices[edge[0]], vertices[edge[1]], level)
                if pt is not None:
                    key = (round(pt[0], 8), round(pt[1], 8))
                    if key not in {(round(p[0], 8), round(p[1], 8)) for p in points}:
                        points.append(pt)
            if len(points) < 2:
                continue
            if len(points) > 2:
                best = None
                for i in range(len(points)):
                    for j in range(i + 1, len(points)):
                        dx = points[i][0] - points[j][0]
                        dy = points[i][1] - points[j][1]
                        distance2 = dx * dx + dy * dy
                        if best is None or distance2 > best[0]:
                            best = (distance2, points[i], points[j])
                p1, p2 = best[1], best[2]
            else:
                p1, p2 = points[0], points[1]
            endpoint_key = tuple(sorted(((round(p1[0], 8), round(p1[1], 8)), (round(p2[0], 8), round(p2[1], 8)))))
            key = (round(level, 8), endpoint_key)
            if key in dedupe:
                continue
            dedupe.add(key)
            out.append({
                'elevation_m': round(level, 6),
                'coordinates': [[round(p1[0], 6), round(p1[1], 6)], [round(p2[0], 6), round(p2[1], 6)]],
            })
    return sorted(out, key=lambda item: (item['elevation_m'], item['coordinates']))


def plateau_candidates(tin: dict, max_slope_percent: float = 8.0, min_area_m2: float = 25.0) -> list[dict]:
    if max_slope_percent < 0 or min_area_m2 < 0:
        raise ValueError('plateau thresholds must be >= 0')
    if tin.get('status') != 'CALCULATED':
        return []
    polygons = []
    for triangle in tin['triangles']:
        if float(triangle['slope_percent']) <= max_slope_percent + 1e-9:
            polygons.append(Polygon([(v[0], v[1]) for v in triangle['vertices']]))
    if not polygons:
        return []
    merged = unary_union(polygons)
    parts = [merged] if merged.geom_type == 'Polygon' else list(getattr(merged, 'geoms', []))
    out = []
    for geom in parts:
        if geom.is_empty or float(geom.area) + 1e-9 < min_area_m2:
            continue
        out.append({
            'area_m2': round(float(geom.area), 6),
            'max_slope_percent': float(max_slope_percent),
            'geometry': mapping(geom),
        })
    return sorted(out, key=lambda item: (-item['area_m2'], str(item['geometry'])))


def _clip_by_sign(vertices: list[tuple[float, float, float]], keep_positive: bool) -> list[tuple[float, float, float]]:
    def inside(v):
        return v[2] >= -1e-12 if keep_positive else v[2] <= 1e-12

    out = vertices[:]
    clipped = []
    if not out:
        return clipped
    previous = out[-1]
    previous_inside = inside(previous)
    for current in out:
        current_inside = inside(current)
        if current_inside != previous_inside:
            d1 = previous[2]
            d2 = current[2]
            denom = d1 - d2
            if abs(denom) > 1e-15:
                t = d1 / denom
                clipped.append((
                    previous[0] + (current[0] - previous[0]) * t,
                    previous[1] + (current[1] - previous[1]) * t,
                    0.0,
                ))
        if current_inside:
            clipped.append(current)
        previous = current
        previous_inside = current_inside
    return clipped


def _integrate_linear_polygon(vertices: list[tuple[float, float, float]]) -> float:
    if len(vertices) < 3:
        return 0.0
    origin = vertices[0]
    total = 0.0
    for index in range(1, len(vertices) - 1):
        a, b, c = origin, vertices[index], vertices[index + 1]
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2.0
        total += area * (a[2] + b[2] + c[2]) / 3.0
    return total


def cut_fill_against_pad(tin: dict, pad_elevation_m: float) -> dict:
    if tin.get('status') != 'CALCULATED':
        return {'status': 'INSUFFICIENT_DATA', 'cut_m3': None, 'fill_m3': None, 'net_m3': None}
    pad = float(pad_elevation_m)
    cut = 0.0
    fill = 0.0
    for triangle in tin['triangles']:
        vertices = [(float(v[0]), float(v[1]), float(v[2]) - pad) for v in triangle['vertices']]
        positive = _clip_by_sign(vertices, True)
        negative = _clip_by_sign(vertices, False)
        cut += max(0.0, _integrate_linear_polygon(positive))
        fill += max(0.0, -_integrate_linear_polygon(negative))
    return {
        'status': 'CALCULATED_PRELIMINARY',
        'pad_elevation_m': round(pad, 6),
        'cut_m3': round(cut, 6),
        'fill_m3': round(fill, 6),
        'earthwork_m3': round(cut + fill, 6),
        'net_m3': round(cut - fill, 6),
        'method': 'exact integration of piecewise-linear TIN against horizontal pad',
        'limitations': [
            'Volume geométrico conceitual; não inclui empolamento, compactação, solo impróprio, contenções, drenagem ou logística de obra.',
        ],
    }


def analyze_terrain(
    samples: list[dict],
    contour_interval_m: float = 1.0,
    plateau_max_slope_percent: float = 8.0,
    plateau_min_area_m2: float = 25.0,
    pad_elevation_m: float | None = None,
) -> dict:
    tin = build_tin(samples)
    result: dict[str, Any] = {
        'status': tin.get('status'),
        'solver_version': TERRAIN_SOLVER_VERSION,
        'tin': tin,
        'contours': contour_segments(tin, contour_interval_m) if tin.get('status') == 'CALCULATED' else [],
        'plateaus': plateau_candidates(tin, plateau_max_slope_percent, plateau_min_area_m2) if tin.get('status') == 'CALCULATED' else [],
        'cut_fill': None,
    }
    if pad_elevation_m is not None:
        result['cut_fill'] = cut_fill_against_pad(tin, pad_elevation_m)
    return result
