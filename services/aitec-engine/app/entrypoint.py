from __future__ import annotations

from fastapi import Depends

from .advanced_api import router as advanced_router
from .main import app, internal_token

# Keep RC3-compatible routes intact while exposing the v20 advanced solver plane
# behind the same machine-to-machine internal token boundary.
app.include_router(advanced_router, dependencies=[Depends(internal_token)])
