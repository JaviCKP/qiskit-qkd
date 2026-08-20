from __future__ import annotations

from qiskit_qkd.config import Scenario
from qiskit_qkd.config.domain_metadata import (
    DEFAULT_SCENARIO,
    DOMAIN_METADATA_VERSION,
    builtin_presets,
    domain_metadata_payload,
)


def _flatten(value: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for section, section_value in value.items():
        if section in {"schema_version", "metadata"}:
            continue
        if isinstance(section_value, dict):
            result.update(
                {f"{section}.{key}": field for key, field in section_value.items()},
            )
        else:
            result[f"scenario.{section}"] = section_value
    eavesdropper = value.get("eavesdropper")
    if isinstance(eavesdropper, dict) and "attack_position" not in eavesdropper:
        result["eavesdropper.attack_position"] = "post_loss"
    return result


def test_domain_defaults_are_derived_from_canonical_scenario() -> None:
    payload = domain_metadata_payload()
    assert payload["metadata_version"] == DOMAIN_METADATA_VERSION
    assert payload["default_scenario"] == DEFAULT_SCENARIO.to_dict()
    assert payload["field_defaults"] == _flatten(DEFAULT_SCENARIO.to_dict())


def test_every_published_field_has_a_dataclass_default_and_unique_key() -> None:
    payload = domain_metadata_payload()
    defaults = payload["field_defaults"]
    fields = payload["fields"]
    keys = [field["key"] for field in fields]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(defaults)
    assert all(field["default"] == defaults[field["key"]] for field in fields)


def test_attack_position_metadata_publishes_choices_and_scientific_scope() -> None:
    payload = domain_metadata_payload()
    field = next(
        field
        for field in payload["fields"]
        if field["key"] == "eavesdropper.attack_position"
    )

    assert field["default"] == "post_loss"
    assert field["options"] == ["post_loss", "pre_loss"]
    assert field["applicable_protocols"] == ["bb84"]
    assert "post_loss" in field["scope"]
    assert "pre_loss" in field["scope"]


def test_medium_payloads_are_valid_scenarios_and_include_aliases() -> None:
    payload = domain_metadata_payload()
    media = payload["media"]
    assert {medium["id"] for medium in media} == {
        "ideal",
        "fiber",
        "vacuum",
        "air",
        "satellite",
        "underwater",
        "custom",
    }
    for medium in media:
        scenario = Scenario.from_dict(medium["scenario"])
        assert scenario.metadata["mediumId"] == medium["id"]


def test_builtin_presets_retain_names_and_digests_from_previous_runtime() -> None:
    expected = [
        (
            "Fibra metropolitana (Ideal)",
            "76362ce99f8919912c9eaa1c4d3bd2adea495e45abeda8c467101f7c4516d7b4",
        ),
        (
            "Satélite LEO (Ideal)",
            "0ae2d3f3166cbcab9c329faebe867cfa4b61b6b5ec14d4d071fe7df6c3821527",
        ),
        (
            "PNS sobre decoy débil",
            "8108a12719ae86ed4d68d0a3e62295863d38dd52002177be46303f4ca219f409",
        ),
        (
            "E91 con scintillation",
            "6c2ded7d59395fcf52c275407028604c019f87ea81723421751bada9f3688f0c",
        ),
        (
            "Telecom Fibra 100 km (SNSPD Real)",
            "7d12fcf3fad4de28bb403d0449a94115690cea49d012cc2fccfdf4a416be97d5",
        ),
        (
            "Free Space Urbano 1.5 km (SPAD Real)",
            "9e6f354cc5b0c5b8f9e7c5f9e6f04dc463f607b4f4e3ff8e1a69566cb4efab53",
        ),
        (
            "Enlace Submarino 30 m (Real)",
            "63f4c71ee4c3150176f5071de278d9232ca7258b3b316b598e47988c099e80fb",
        ),
    ]
    actual = [(name, scenario.digest()) for name, scenario in builtin_presets()]
    assert actual == expected
