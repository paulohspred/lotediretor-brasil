from __future__ import annotations

from fastapi import Depends

from .main import app, internal_token
from .v20_api import router as solar_v20_router

# Preserve RC3 endpoints while exposing Solar 360 v20 under the existing
# machine-to-machine authentication boundary.
app.include_router(solar_v20_router, dependencies=[Depends(internal_token)])
