"""Fixed transport identities; distinct site contracts share no semantic default."""

from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract


class NativePrivateJsonProfile(Contract):
    site_id: Literal["gitlab", "reddit"]
    family: Literal["profile_ssh_key", "group_creation", "native_image_submission"]
    content_schema: Literal[
        "gitlab-native-private-json/1",
        "gitlab-group-native-private-json/1",
        "reddit-native-private-json/1",
    ]
    producer: Literal[
        "fixed-gitlab-native-private-v1",
        "fixed-gitlab-group-native-private-v1",
        "fixed-reddit-native-private-v1",
    ]

    @model_validator(mode="after")
    def exact_profile(self) -> Self:
        expected = {
            ("gitlab", "profile_ssh_key"): (
                "gitlab-native-private-json/1",
                "fixed-gitlab-native-private-v1",
            ),
            ("gitlab", "group_creation"): (
                "gitlab-group-native-private-json/1",
                "fixed-gitlab-group-native-private-v1",
            ),
            ("reddit", "native_image_submission"): (
                "reddit-native-private-json/1",
                "fixed-reddit-native-private-v1",
            ),
        }
        if (self.content_schema, self.producer) != expected.get(
            (self.site_id, self.family)
        ):
            raise ValueError("Exact fixed native site transport profile required")
        return self


GITLAB_PRIVATE_JSON = NativePrivateJsonProfile(
    site_id="gitlab",
    family="profile_ssh_key",
    content_schema="gitlab-native-private-json/1",
    producer="fixed-gitlab-native-private-v1",
)
GITLAB_GROUP_PRIVATE_JSON = NativePrivateJsonProfile(
    site_id="gitlab",
    family="group_creation",
    content_schema="gitlab-group-native-private-json/1",
    producer="fixed-gitlab-group-native-private-v1",
)
REDDIT_PRIVATE_JSON = NativePrivateJsonProfile(
    site_id="reddit",
    family="native_image_submission",
    content_schema="reddit-native-private-json/1",
    producer="fixed-reddit-native-private-v1",
)
