"""Prospective storage preparation evidence; never an exception to media protection."""

from typing import Literal, Self
from pydantic import model_validator
from lab_generate_skill.domain.validation import Contract
from .native_schema import NativeMedia
from .service_contract import RedditServiceSpec


class MediaInitialization(Contract):
    schema_version: Literal["reddit-media-initialization/1"] = (
        "reddit-media-initialization/1"
    )
    service: RedditServiceSpec
    constructor_sha256: Literal[
        "2e531b5f3b20a31d7b933b175d8a3519992ae13fc9dd937761fbaefb6cfe2bc6"
    ]
    adapter_sha256: Literal[
        "462d0ed21f5e4d0f7c76cd402375655741af638d8bd760e7307a0481726dd991"
    ]
    configuration_sha256: Literal[
        "f07d088abc00610fa5954659c7852ae215fb20d26b8cec98f19dabbfae02af08"
    ]
    before: NativeMedia
    after: NativeMedia

    @model_validator(mode="after")
    def original_constructor_effect(self) -> Self:
        if (
            self.before.directories
            or self.before.files
            or self.after.files
            or self.after.directories != ("submission_images",)
        ):
            raise ValueError(
                "Only the native constructor's empty directory belongs to preparation"
            )
        return self

    def check_baseline(self, media: NativeMedia) -> None:
        if NativeMedia.model_validate(media) != self.after:
            raise ValueError(
                "Media changed between native storage preparation and task baseline"
            )
