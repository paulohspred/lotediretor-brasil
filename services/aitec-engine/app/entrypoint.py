from __future__ import annotations

from fastapi import Depends
from fastapi.responses import PlainTextResponse

from .advanced_api import router as advanced_router
from .main import app, internal_token
from .telemetry import http_telemetry, render_metrics

# Keep RC3-compatible routes intact while exposing the v20 advanced solver plane
# behind the same machine-to-machine internal token boundary.
app.include_router(advanced_router, dependencies=[Depends(internal_token)])
app.middleware('http')(http_telemetry)

# Keep /metrics stable while replacing the legacy service-up-only payload with
# readiness/build info plus low-cardinality RED metrics.
app.router.routes[:]=[route for route in app.router.routes if getattr(route,'path',None)!='/metrics']

@app.get('/metrics',include_in_schema=False)
def metrics():
    body='\n'.join([
        '# HELP lotediretor_service_up Service readiness',
        '# TYPE lotediretor_service_up gauge',
        'lotediretor_service_up{service="aitec-engine"} 1',
        '# HELP lotediretor_build_info Static build information',
        '# TYPE lotediretor_build_info gauge',
        'lotediretor_build_info{service="aitec-engine",version="19.0.0-rc.3"} 1',
        render_metrics('aitec-engine'),
        '',
    ])
    return PlainTextResponse(body,media_type='text/plain; version=0.0.4')
