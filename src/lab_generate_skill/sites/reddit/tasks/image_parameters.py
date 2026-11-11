"""Original licensed public image identities; logical names, no host paths."""

import json
from typing import Literal, Self
from pydantic import Field, model_validator, field_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText


class PublicPhoto(Contract):
    relative_file: Literal[
        "assets/fixed-beach-sunset-photo.jpg", "assets/fixed-landscape-photo.jpg"
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0, le=1024 * 1024)
    description: NonEmptyText
    dimensions: tuple[int, int]

    def public_file(self) -> dict[str, str | int]:
        return dict(
            path=self.relative_file,
            sha256=self.sha256,
            bytes=self.bytes,
            description=self.description,
        )


PHOTOS = (
    PublicPhoto(
        relative_file="assets/fixed-beach-sunset-photo.jpg",
        sha256="f81de71a1d4962a541210f1bdd2059c0aeb016d639084102d67e8e62c06c025b",
        bytes=224646,
        dimensions=(1280, 1280),
        description="Cable Beach, Broome, Western Australia sunset photograph; Wikimedia 1280px published thumbnail; no local image transformation.",
    ),
    PublicPhoto(
        relative_file="assets/fixed-landscape-photo.jpg",
        sha256="c7c9a1b3c6f035d93c274ae68d5b7d8c49cfaafa7d4d640daf8383d0f52479c8",
        bytes=259654,
        dimensions=(1280, 853),
        description="Yosemite National Park mountains, forest and river landscape photograph; Wikimedia 1280px published thumbnail; no local image transformation.",
    ),
)


class ImageParameters(Contract):
    body: Literal[""]
    fixture_status: Literal["real_photo_visually_reviewed"]
    forum: NonEmptyText
    image_bytes: int = Field(gt=0, le=1024 * 1024)
    image_description: NonEmptyText
    image_dimensions: list[int] = Field(min_length=2, max_length=2)
    image_fixture: NonEmptyText
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: NonEmptyText

    @field_validator("forum", "title")
    @classmethod
    def single_line(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("One nonempty original forum/title required")
        return value

    @model_validator(mode="after")
    def declared_photo(self) -> Self:
        asset = next((a for a in PHOTOS if a.relative_file == self.image_fixture), None)
        if asset is None or (
            self.image_sha256,
            self.image_bytes,
            self.image_description,
            tuple(self.image_dimensions),
        ) != (asset.sha256, asset.bytes, asset.description, asset.dimensions):
            raise ValueError("Exact original licensed photograph identity required")
        return self


def render_public_goal(goal: str, parameters: ImageParameters) -> str:
    parameters = ImageParameters.model_validate(parameters)
    if type(goal) is not str or not goal.strip():
        raise ValueError("Original nonempty public image goal required")
    return (
        goal
        + "\nPublic task parameters: "
        + json.dumps(
            parameters.model_dump(), ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        + "\nAvailable local photographs: "
        + json.dumps(
            [p.public_file() for p in PHOTOS],
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    )
