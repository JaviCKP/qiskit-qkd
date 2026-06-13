from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors


def validation_exception_handler(
    _request: Request,
    exc: ApiValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": exc.errors})


def api_validation_error(
    exc: ValueError | TypeError,
    *,
    payload: Mapping[str, Any] | None = None,
) -> ApiValidationError:
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
