"""Fixed selected initializer from complete actual preparation, never a profile guess."""

from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from lab_generate_skill.bootstrap.gitlab_group_browser_declarations import (
    group_browser_declaration,
)
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import SshKeyObserved
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from site_preparation_native import NativePreparation
from gitlab_preparation_native import GitlabPreparation
from test_slurm_commands import guard


def initialization(
    native: NativePreparation,
    site: SiteResourceStarted,
    publication: PreparedPublication,
) -> GitlabSshKeyInitialization | GitlabGroupInitialization:
    if not isinstance(native, GitlabPreparation):
        raise TypeError("Original selected GitLab preparation required")
    native.selection.check_configuration(native.c.spec.configuration)
    assert native.request is not None and native.result is not None
    if native.selection.group:
        group_observed = GroupObserved.model_validate_json(native.result.private_result)
        assert group_observed.request == native.request
        group_spec = GroupSpec.model_validate_json(native.private_input_json())
        groups = load_group_capture(
            native.c.evidence.read(
                group_observed.native.payload_ref, control=guard(60)
            ),
            group_spec,
        )
        return group_browser_declaration(
            public=native.public,
            endpoint=site.instance.endpoint,
            native_account_id=groups.state.user.id,
            prepared_ref=publication.prepared_ref,
            site_ref=native.put(site),
        )
    observed = SshKeyObserved.model_validate_json(native.result.private_result)
    assert observed.request == native.request
    spec = SshKeySpec.model_validate_json(native.private_input_json())
    state = load_ssh_key_state(
        native.c.evidence.read(observed.native.payload_ref, control=guard(60)), spec
    )
    return GitlabSshKeyInitialization(
        endpoint=site.instance.endpoint,
        native_account_id=state.account.id,
        prepared_ref=publication.prepared_ref,
        site_ref=native.put(site),
    )
