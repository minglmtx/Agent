"""Frozen launch configuration rejects empty/foreign/implicit launch parameters."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from generator_resource_fixtures import resource_case


@pytest.mark.parametrize(
    "value",
    ["", None, True, 7, "relative", "/tmp/../python", "/tmp//python", "/tmp/py\0thon"],
)
def test_bad_executable_rejected(tmp_path: Path, value: object) -> None:
    c = resource_case(tmp_path, Path("/test/python"))
    with pytest.raises(ValidationError):
        GeneratorResourceSpec.model_validate(
            {**c.spec.model_dump(), "python_executable": value}
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        True,
        "-1",
        "0,",
        "MIG-x",
        "0",
        "GPU-00000000-0000-0000-0000-000000000001",
    ],
)
def test_removed_device_field_rejected(tmp_path: Path, value: object) -> None:
    c = resource_case(tmp_path, Path("/test/python"))
    with pytest.raises(ValidationError):
        GeneratorResourceSpec.model_validate(
            {**c.spec.model_dump(), "cuda_visible_devices": value}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("resource_kind", "actor"),
        ("provider_id", "arbitrary-import"),
        ("provider_version", "99"),
    ],
)
def test_provider_cannot_change(tmp_path: Path, field: str, value: str) -> None:
    c = resource_case(tmp_path, Path("/test/python"))
    with pytest.raises(ValidationError):
        GeneratorResourceSpec.model_validate(
            {
                **c.spec.model_dump(),
                "token": {**c.spec.token.model_dump(), field: value},
            }
        )


@pytest.mark.parametrize(
    "field,value", [("visibility", "public"), ("content_schema", "latest/1")]
)
def test_release_reference_cannot_be_implicit(
    tmp_path: Path, field: str, value: str
) -> None:
    c = resource_case(tmp_path, Path("/test/python"))
    with pytest.raises(ValidationError):
        GeneratorResourceSpec.model_validate(
            {
                **c.spec.model_dump(),
                "release_ref": {**c.spec.release_ref.model_dump(), field: value},
            }
        )
