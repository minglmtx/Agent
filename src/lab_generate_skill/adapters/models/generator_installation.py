"""Generator wire projection of the common installed-release verifier.

Preserves this component's versioned envelope; physical verification has one
implementation in releases and is independent of model construction.
"""

from lab_generate_skill.domain.generator_installation import (
    GeneratorInstallation,
    GeneratorInstalledSources,
)
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)


def verify_generator_installation(
    installation: GeneratorInstallation, control: OperationControl
) -> GeneratorInstalledSources:
    original = GeneratorInstallation.model_validate(installation)
    shared = ReleaseInstallation.model_validate(
        {
            **original.model_dump(),
            "schema_version": "release-installation/1",
        }
    )
    actual = verify_release_installation(shared, control)
    return GeneratorInstalledSources.model_validate(
        {
            **actual.model_dump(),
            "schema_version": "generator-installed-sources/1",
        }
    )
