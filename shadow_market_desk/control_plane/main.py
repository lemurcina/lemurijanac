from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shadow_market_desk import __version__

from .models import AppInfo, ErrorModel, HealthResponse
from .routes import router

app = FastAPI(
    title="Shadow Market Desk Control Plane",
    version=__version__,
    description="Operator-safe API for control-plane reads and controls.",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    model = ErrorModel(error="http_error", detail=str(exc.detail), code=str(exc.status_code))
    return JSONResponse(status_code=exc.status_code, content=model.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    model = ErrorModel(error="validation_error", detail=str(exc), code="422")
    return JSONResponse(status_code=422, content=model.model_dump())


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/v1", response_model=AppInfo, tags=["meta"])
def api_root() -> AppInfo:
    return AppInfo(version=app.version)


app.include_router(router)
