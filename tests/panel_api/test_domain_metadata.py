from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from panel.api.app import create_app
from qiskit_qkd.config.domain_metadata import DOMAIN_METADATA_VERSION
from qiskit_qkd.config.schema import CHANNEL_KINDS, DETECTOR_KINDS, PROTOCOL_NAMES


def test_catalog_publishes_additive_versioned_domain_metadata(tmp_path: Path) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata_version"] == DOMAIN_METADATA_VERSION
    assert payload["default_medium_id"] == "fiber"
    assert payload["default_scenario"]["channel"]["kind"] == "fiber"
    fields = {field["key"]: field for field in payload["fields"]}
    assert fields["channel.distance_km"]["unit"] == "km"
    assert fields["e91.bell_state"]["visible_when"] == {
        "target": "protocol.name",
        "equals": "e91",
    }
    assert "applicable_protocols" in fields["channel.distance_km"]
    assert fields["channel.pmd_coefficient_ps_sqrt_km"]["applicable_channel_kinds"] == [
        "fiber",
    ]


def test_presets_are_serialized_from_valid_domain_scenarios(tmp_path: Path) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    response = client.get("/api/presets")
    assert response.status_code == 200
    presets = response.json()["presets"]
    assert len(presets) >= 7
    assert len({preset["digest"] for preset in presets}) == len(presets)
    assert all(preset["scenario"]["schema_version"] in {1, 2} for preset in presets)


def test_catalog_covers_capability_targets_and_supported_options(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    payload = client.get("/api/catalog").json()
    fields = {field["key"]: field for field in payload["fields"]}
    capability_targets = set(payload["capabilities"]["parameters"])
    assert capability_targets <= set(fields)
    assert set(fields["protocol.name"]["options"]) == PROTOCOL_NAMES
    assert set(fields["channel.kind"]["options"]) == CHANNEL_KINDS
    assert set(fields["detector.kind"]["options"]) == DETECTOR_KINDS
