"""Exact original native asset publication response; private capture input."""

from typing import Literal, Self
from pathlib import PurePosixPath
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256


class NativeStaticAssets(Contract):
    installed_source: Literal[
        "/var/www/magento2/vendor/magento/module-offline-payments/view/frontend/web"
    ]
    original_published_namespace: Literal[
        "/var/www/magento2/pub/static/frontend/Magento/blank/en_US/Magento_OfflinePayments"
    ]
    original_published_sha256: dict[str, Sha256] = Field(min_length=1)
    added_installed_sha256: dict[str, Sha256] = Field(min_length=1)
    native_bytes_only: Literal[True]
    original_published_bytes_unchanged: Literal[True]
    external_source_used: Literal[False]

    @model_validator(mode="after")
    def native_paths(self) -> Self:
        if set(self.original_published_sha256) & set(self.added_installed_sha256):
            raise ValueError(
                "Added native assets cannot replace original published paths"
            )
        for name in (*self.original_published_sha256, *self.added_installed_sha256):
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or str(path) != name
                or name == "."
                or ".." in path.parts
                or any(c in name for c in ("\0", "\n", "\r"))
            ):
                raise ValueError("Invalid installed native asset path")
        return self


class NativeStaticPublication(Contract):
    Magento_OfflinePayments: NativeStaticAssets
