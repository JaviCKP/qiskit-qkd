from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from panel.api.app import (
    _canonicalize_spa_path,
    _resolve_spa_request,
    create_app,
)

DIST_DIR = Path(__file__).resolve().parents[2] / "panel" / "web" / "dist"


def _client() -> TestClient:
    return TestClient(create_app())


def test_root_and_index_serve_index_html() -> None:
    index = (DIST_DIR / "index.html").read_bytes()
    client = _client()

    assert client.get("/").content == index
    assert client.get("/index.html").content == index


def test_existing_asset_is_served() -> None:
    asset = next(path for path in (DIST_DIR / "assets").iterdir() if path.is_file())

    response = _client().get(f"/assets/{asset.name}")

    assert response.status_code == 200
    assert response.content == asset.read_bytes()


def test_missing_client_route_falls_back_to_index() -> None:
    response = _client().get("/scenarios/does-not-exist")

    assert response.status_code == 200
    assert response.content == (DIST_DIR / "index.html").read_bytes()


def test_encoded_parent_path_cannot_read_package_json() -> None:
    response = _client().get("/%2e%2e/package.json")

    assert response.status_code == 404
    assert response.text == "Not Found"
    assert b"package.json" not in response.content
    assert b"panel/web" not in response.content


def test_double_encoded_parent_path_cannot_read_package_json() -> None:
    response = _client().get("/%252e%252e/package.json")

    assert response.status_code == 404
    assert response.text == "Not Found"
    assert b"package.json" not in response.content
    assert b"panel/web" not in response.content


@pytest.mark.parametrize(
    "raw_path",
    [
        "../package.json",
        "/../package.json",
        "%2e%2e/package.json",
        "%252e%252e/package.json",
        r"..\package.json",
        "%2e%2e%5cpackage.json",
        "%2fpackage.json",
        "%5cpackage.json",
        r"C:\package.json",
        "C:/package.json",
        r"\\server\share\package.json",
        "//server/share/package.json",
    ],
)
def test_path_traversal_and_absolute_variants_are_unsafe(raw_path: str) -> None:
    _, unsafe = _canonicalize_spa_path(raw_path)

    assert unsafe is True


def test_normal_client_route_is_distinguished_from_unsafe_path() -> None:
    segments, unsafe = _canonicalize_spa_path("scenarios/does-not-exist")
    resolution = _resolve_spa_request(DIST_DIR, "scenarios/does-not-exist")

    assert segments == ("scenarios", "does-not-exist")
    assert unsafe is False
    assert resolution.file is None
    assert resolution.unsafe is False


@pytest.mark.parametrize(
    "raw_path",
    [b"/../package.json", b"//server/share/package.json"],
)
def test_raw_asgi_path_is_rejected_at_the_route_boundary(raw_path: bytes) -> None:
    app = create_app(use_processes=False)
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/{path:path}"
    )
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": raw_path.decode("ascii"),
            "raw_path": raw_path,
            "query_string": b"",
            "headers": [],
        },
    )

    response = route.endpoint(
        path=raw_path.decode("ascii").lstrip("/"),
        request=request,
    )

    assert response.status_code == 404
    assert response.body == b"Not Found"


def test_symlink_outside_dist_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    link = dist / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    resolution = _resolve_spa_request(dist, "link.txt")

    assert resolution.file is None
    assert resolution.unsafe is True
