from __future__ import annotations

import base64
import hashlib
import inspect
import os
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from . import basement_parking_solver
from . import building_solver
from . import environment_solver
from . import export_solver
from . import finance_solver
from . import ingest_solver
from . import optimization_solver
from . import road_engineering_solver
from . import room_solver
from . import terrain_solver
from . import unit_solver

CLASSIFICATION = 'STUDY_PREPROJECT_NOT_EXECUTIVE'
DEFAULT_MAX_BINARY_BYTES = 25 * 1024 * 1024
MAX_BINARY_BYTES = int(os.getenv('AITEC_MAX_BINARY_BYTES', str(DEFAULT_MAX_BINARY_BYTES)))


@dataclass(frozen=True)
class OperationSpec:
    function: Callable[..., Any]
    solver_version: str
    category: str


def _spec(function: Callable[..., Any], solver_version: str, category: str) -> OperationSpec:
    return OperationSpec(function=function, solver_version=solver_version, category=category)


OP_REGISTRY: dict[str, OperationSpec] = {
    'unit.solve': _spec(unit_solver.solve_unit_distribution, unit_solver.DESIGN_DNA_VERSION, 'architecture'),
    'unit.compare': _spec(unit_solver.compare_designs, unit_solver.DESIGN_DNA_VERSION, 'architecture'),
    'terrain.tin': _spec(terrain_solver.build_tin, terrain_solver.TERRAIN_SOLVER_VERSION, 'terrain'),
    'terrain.contours': _spec(terrain_solver.contour_segments, terrain_solver.TERRAIN_SOLVER_VERSION, 'terrain'),
    'terrain.plateaus': _spec(terrain_solver.plateau_candidates, terrain_solver.TERRAIN_SOLVER_VERSION, 'terrain'),
    'terrain.cut-fill': _spec(terrain_solver.cut_fill_against_pad, terrain_solver.TERRAIN_SOLVER_VERSION, 'terrain'),
    'building.solve': _spec(building_solver.solve_building_system, building_solver.BUILDING_SOLVER_VERSION, 'architecture'),
    'parking.basement': _spec(basement_parking_solver.solve_basement_parking, basement_parking_solver.BASEMENT_PARKING_VERSION, 'parking'),
    'unit.room-graph': _spec(room_solver.solve_unit_room_graph, room_solver.ROOM_SOLVER_VERSION, 'architecture'),
    'road.evaluate': _spec(road_engineering_solver.evaluate_road_engineering, road_engineering_solver.ROAD_SOLVER_VERSION, 'road'),
    'environment.analyze': _spec(environment_solver.analyze_environment, environment_solver.ENVIRONMENT_SOLVER_VERSION, 'environment'),
    'finance.calculate': _spec(finance_solver.calculate_project_finance, finance_solver.FINANCE_SOLVER_VERSION, 'finance'),
    'export.geojson': _spec(export_solver.export_geojson, export_solver.EXPORT_VERSION, 'export'),
    'export.kml': _spec(export_solver.export_kml, export_solver.EXPORT_VERSION, 'export'),
    'export.kmz': _spec(export_solver.export_kmz, export_solver.EXPORT_VERSION, 'export'),
    'export.dxf': _spec(export_solver.export_dxf, export_solver.EXPORT_VERSION, 'export'),
    'export.ifc': _spec(export_solver.export_ifc, export_solver.EXPORT_VERSION, 'export'),
    'export.xlsx': _spec(export_solver.export_xlsx, export_solver.EXPORT_VERSION, 'export'),
    'export.pdf': _spec(export_solver.export_pdf, export_solver.EXPORT_VERSION, 'export'),
    'export.gltf': _spec(export_solver.export_gltf, export_solver.EXPORT_VERSION, 'export'),
    'export.manifest': _spec(export_solver.export_manifest, export_solver.EXPORT_VERSION, 'export'),
    'ingest.dataset': _spec(ingest_solver.ingest_dataset, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.geojson': _spec(ingest_solver.ingest_geojson, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.kml': _spec(ingest_solver.ingest_kml, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.kmz': _spec(ingest_solver.ingest_kmz, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.shapefile': _spec(ingest_solver.ingest_shapefile, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.gpkg': _spec(ingest_solver.ingest_gpkg, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.dxf': _spec(ingest_solver.ingest_dxf, ingest_solver.INGEST_VERSION, 'ingest'),
    'ingest.ifc': _spec(ingest_solver.ingest_ifc, ingest_solver.INGEST_VERSION, 'ingest'),
    'optimization.pareto': _spec(optimization_solver.explain_pareto, optimization_solver.OPTIMIZATION_VERSION, 'optimization'),
    'optimization.diff': _spec(optimization_solver.visual_geometry_diff, optimization_solver.OPTIMIZATION_VERSION, 'optimization'),
}


class ExecutionContext(BaseModel):
    tenant_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    constraint_snapshot_id: str | None = Field(default=None, max_length=256)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class AdvancedCall(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    context: ExecutionContext = Field(default_factory=ExecutionContext)


def _decode_special(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_special(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {'$base64'}:
            try:
                payload = base64.b64decode(str(value['$base64']), validate=True)
            except Exception as exc:
                raise ValueError('invalid $base64 payload') from exc
            if len(payload) > MAX_BINARY_BYTES:
                raise ValueError(f'binary payload exceeds {MAX_BINARY_BYTES} bytes')
            return payload
        if set(value) == {'$geojson'}:
            try:
                return shape(value['$geojson'])
            except Exception as exc:
                raise ValueError('invalid $geojson geometry') from exc
        return {str(key): _decode_special(item) for key, item in value.items()}
    return value


def serialize_result(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        if len(value) > MAX_BINARY_BYTES:
            raise ValueError(f'binary result exceeds {MAX_BINARY_BYTES} bytes')
        return {
            '$binary': {
                'encoding': 'base64',
                'size': len(value),
                'sha256': hashlib.sha256(value).hexdigest(),
                'data': base64.b64encode(value).decode('ascii'),
            }
        }
    if isinstance(value, BaseGeometry):
        return {'$geojson': mapping(value)}
    if isinstance(value, dict):
        return {str(key): serialize_result(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_result(item) for item in value]
    if isinstance(value, set):
        return [serialize_result(item) for item in sorted(value, key=repr)]
    if hasattr(value, 'model_dump'):
        return serialize_result(value.model_dump())
    return repr(value)


def _required_parameters(function: Callable[..., Any]) -> list[str]:
    required = []
    for name, parameter in inspect.signature(function).parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return required


def capabilities() -> list[dict[str, Any]]:
    items = []
    for name, spec in sorted(OP_REGISTRY.items()):
        signature = inspect.signature(spec.function)
        items.append({
            'operation': name,
            'category': spec.category,
            'solver_version': spec.solver_version,
            'required_parameters': _required_parameters(spec.function),
            'parameters': list(signature.parameters),
        })
    return items


def execute_operation(operation: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None) -> Any:
    spec = OP_REGISTRY.get(operation)
    if spec is None:
        raise ValueError(f'unknown A.I TEC operation:{operation}')
    decoded_args = _decode_special(args or [])
    decoded_kwargs = _decode_special(kwargs or {})
    try:
        inspect.signature(spec.function).bind(*decoded_args, **decoded_kwargs)
    except TypeError as exc:
        raise ValueError(f'invalid arguments for {operation}:{exc}') from exc
    return spec.function(*decoded_args, **decoded_kwargs)


router = APIRouter(prefix='/aitec/v20', tags=['A.I TEC v20'])


@router.get('/capabilities')
def list_capabilities():
    return {
        'status': 'READY',
        'classification': CLASSIFICATION,
        'professional_review_required': True,
        'binary_limit_bytes': MAX_BINARY_BYTES,
        'operations': capabilities(),
        'limitations': [
            'As operações são estudos/pré-projetos verificáveis e nunca projeto executivo.',
            'Dados ausentes, CRS e restrições não são inventados pelo gateway de runtime.',
            'Homologação profissional e fontes externas permanecem gates independentes.',
        ],
    }


@router.post('/execute/{operation}')
def execute(operation: str, body: AdvancedCall):
    spec = OP_REGISTRY.get(operation)
    if spec is None:
        raise HTTPException(404, f'unknown A.I TEC operation:{operation}')
    try:
        result = execute_operation(operation, body.args, body.kwargs)
        serialized = serialize_result(result)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f'solver_execution_failed:{operation}:{type(exc).__name__}') from exc
    return {
        'status': 'EXECUTED',
        'operation': operation,
        'category': spec.category,
        'solver_version': spec.solver_version,
        'classification': CLASSIFICATION,
        'professional_review_required': True,
        'context': body.context.model_dump(exclude_none=True),
        'result': serialized,
        'limitations': [
            'Resultado de estudo/pré-projeto; não usar como projeto executivo ou responsabilidade técnica.',
            'Reprodutibilidade exige preservar entradas, constraint_snapshot_id, seed quando aplicável e solver_version.',
        ],
    }
