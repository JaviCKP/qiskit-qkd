from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from qiskit_qkd.config import CapabilityError

from .jobs import JobCapacityError, JobManagerShutdownError
from .store import StoreValidationError


class ApiValidationError(Exception):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors


def validation_exception_handler(
    _request: Request,
    exc: ApiValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": exc.errors})


def capability_exception_handler(
    _request: Request,
    exc: CapabilityError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"errors": [dict(issue) for issue in exc.errors]},
    )


def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ())]
        if loc and loc[0] == "body":
            loc.pop(0)
        if loc and loc[0] == "scenario":
            loc.pop(0)
        errors.append(
            {
                "loc": ".".join(loc) or "request",
                "msg": str(error.get("msg", "invalid request value")),
            },
        )
    return JSONResponse(status_code=422, content={"errors": errors})


def job_capacity_exception_handler(
    _request: Request,
    exc: JobCapacityError,
) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)})


def job_shutdown_exception_handler(
    _request: Request,
    exc: JobManagerShutdownError,
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def store_validation_exception_handler(
    _request: Request,
    exc: StoreValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": exc.errors})


def api_validation_error(
    exc: KeyError | ValueError | TypeError,
    *,
    payload: Mapping[str, Any] | None = None,
) -> ApiValidationError:
    if isinstance(exc, CapabilityError):
        return ApiValidationError([dict(issue) for issue in exc.errors])
    if isinstance(exc, KeyError):
        field = str(exc.args[0]) if exc.args else "scenario"
        return ApiValidationError(
            [{"loc": field, "msg": f"{field} is required"}],
        )
    message = str(exc)
    return ApiValidationError(
        [{"loc": infer_field_path(message, payload or {}), "msg": message}],
    )


def infer_field_path(message: str, payload: Mapping[str, Any]) -> str:
    field = message.split(" ", 1)[0].strip("'\"")
    if "." in field:
        return field
    path = _find_field_path(payload, field)
    return ".".join(path) if path else field or "scenario"


def _find_field_path(value: Any, field: str) -> list[str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == field:
                return [str(key)]
            path = _find_field_path(nested, field)
            if path is not None:
                return [str(key), *path]
    if isinstance(value, list):
        for index, nested in enumerate(value):
            path = _find_field_path(nested, field)
            if path is not None:
                return [str(index), *path]
    return None
