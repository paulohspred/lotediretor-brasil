from __future__ import annotations

from fastapi import Depends
from fastapi.responses import PlainTextResponse

from .main import app, internal_token
from .telemetry import http_telemetry, render_metrics
from .v20_api import router as solar_v20_router

# Preserve RC3 endpoints while exposing Solar 360 v20 under the existing
# machine-to-machine authentication boundary.
app.include_router(solar_v20_router, dependencies=[Depends(internal_token)])
app.middleware('http')(http_telemetry)

# Replace the legacy service-up-only endpoint with the same readiness/build
# contract plus low-cardinality RED metrics. Keep /metrics stable for Prometheus.
app.router.routes[:]=[route for route in app.router.routes if getattr(route,'path',None)!='/metrics']

@app.get('/metrics',include_in_schema=False)
def metrics():
    body='\n'.join([
        '# HELP lotediretor_service_up Service readiness',
        '# TYPE lotediretor_service_up gauge',
        'lotediretor_service_up{service="solar-engine"} 1',
        '# HELP lotediretor_build_info Static build information',
        '# TYPE lotediretor_build_info gauge',
        'lotediretor_build_info{service="solar-engine",version="19.0.0-rc.3"} 1',
        render_metrics('solar-engine'),
        '',
    ])
    return PlainTextResponse(body,media_type='text/plain; version=0.0.4')
