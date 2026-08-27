from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import v20, v20_advanced


@dataclass(frozen=True)
class Operation:
    function: Callable[..., Any]
    category: str


REGISTRY: dict[str, Operation] = {
    'source.validate': Operation(v20.validate_source_snapshot,'provenance'),
    'dsm.roof-surfaces': Operation(v20.segment_roof_surfaces,'geometry'),
    'dsm.obstacles': Operation(v20.detect_dsm_obstacles,'geometry'),
    'solar.position': Operation(v20_advanced.solar_position,'solar-geometry'),
    'irradiance.poa': Operation(v20_advanced.plane_of_array_irradiance,'solar-resource'),
    'shadow.project': Operation(v20.project_shadows,'solar-geometry'),
    'roof.layout': Operation(v20_advanced.roof_rect_layout,'layout'),
    'electrical.string-mppt': Operation(v20_advanced.string_mppt_design,'electrical'),
    'energy.irradiance': Operation(v20.energy_from_irradiance,'energy'),
    'battery.simulate': Operation(v20.simulate_battery,'storage'),
    'tariff.apply': Operation(v20.apply_tariff_snapshot,'tariff'),
    'financial.project': Operation(v20_advanced.financial_projection,'finance'),
    'connection.precheck': Operation(v20.connection_precheck,'grid'),
    'ground-mount.layout': Operation(v20.ground_mount_layout,'ground-mount'),
    'safety.conditioning': Operation(v20.safety_conditioning,'safety'),
    'calibration.compare': Operation(v20.calibration_compare,'calibration'),
    'bill.parse-ocr': Operation(v20.parse_bill_ocr_text,'billing'),
    'equipment.snapshot': Operation(v20.equipment_snapshot,'catalog'),
    'scene.build': Operation(v20.build_scene_3d,'scene-3d'),
    'report.build': Operation(v20.build_scenario_report,'report'),
}


class SolarV20Call(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


def capabilities() -> list[dict]:
    out=[]
    for name,spec in sorted(REGISTRY.items()):
        sig=inspect.signature(spec.function)
        required=[key for key,p in sig.parameters.items() if p.default is inspect.Parameter.empty and p.kind not in (inspect.Parameter.VAR_POSITIONAL,inspect.Parameter.VAR_KEYWORD)]
        out.append({'operation':name,'category':spec.category,'solver_version':v20.SOLAR_V20_VERSION,'parameters':list(sig.parameters),'required_parameters':required})
    return out


def execute_operation(name: str, args: list[Any] | None=None, kwargs: dict[str,Any] | None=None):
    spec=REGISTRY.get(name)
    if spec is None:raise ValueError(f'unknown Solar v20 operation:{name}')
    a=args or [];kw=kwargs or {}
    try:inspect.signature(spec.function).bind(*a,**kw)
    except TypeError as exc:raise ValueError(f'invalid arguments for {name}:{exc}') from exc
    return spec.function(*a,**kw)


router=APIRouter(prefix='/solar/v20',tags=['Solar 360 v20'])


@router.get('/capabilities')
def list_capabilities():
    return {
        'status':'READY','solver_version':v20.SOLAR_V20_VERSION,'classification':v20.CLASSIFICATION,
        'operations':capabilities(),
        'policy':'Missing material inputs return REQUIRES_INPUT; commercial/legal/source values are never invented.',
        'external_gates':['current licensed source verification','utility approval','professional structural/fire review','independent calibration'],
    }


@router.post('/execute/{operation}')
def execute(operation: str, body: SolarV20Call):
    spec=REGISTRY.get(operation)
    if spec is None:raise HTTPException(404,f'unknown Solar v20 operation:{operation}')
    try:result=execute_operation(operation,body.args,body.kwargs)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    except Exception as exc:raise HTTPException(500,f'solar_v20_execution_failed:{operation}:{type(exc).__name__}') from exc
    return {'status':'EXECUTED','operation':operation,'category':spec.category,'solver_version':v20.SOLAR_V20_VERSION,'classification':v20.CLASSIFICATION,'result':result}
