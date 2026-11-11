"""Generator wire contracts over the shared release installation fields.

Existing generator wire bytes remain unchanged. Shared verification and future
non-model consumers use release_installation; no alternate signatures/fallback.
"""

from typing import Literal
from .release_installation import InstallationDeclaration, InstalledSourceProjection


class GeneratorInstallation(InstallationDeclaration):
    schema_version: Literal["generator-installation/1"] = "generator-installation/1"


class GeneratorInstalledSources(InstalledSourceProjection):
    schema_version: Literal["generator-installed-sources/1"] = (
        "generator-installed-sources/1"
    )
