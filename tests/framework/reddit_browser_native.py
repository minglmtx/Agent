"""Original native account and fixed public photographs from one prepared source."""

from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.sites.reddit.tasks.image_recovery import ImageObserved
from lab_generate_skill.sites.reddit.state_reads import RedditStateReads
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
from site_preparation_native import NativePreparation
from test_slurm_commands import guard


def initialization(
    native: NativePreparation,
    site: SiteResourceStarted,
    publication: PreparedPublication,
) -> RedditNativeImageInitialization:
    assert (
        native.c.spec.configuration.site_id == "reddit"
        and native.request is not None
        and native.result is not None
    )
    observed = ImageObserved.model_validate_json(native.result.private_result)
    assert observed.request == native.request
    reads = RedditStateReads(native.c.evidence)
    reference = reads.reference(
        observed.snapshot.native_before, observed.snapshot.request, guard(60)
    )
    prepared = native.records.load(publication, native.request.operation)
    return RedditNativeImageInitialization(
        endpoint=site.instance.endpoint,
        native_account_id=reference.account.id,
        native_account_username=reference.account.username,
        prepared_ref=publication.prepared_ref,
        site_ref=native.put(site),
        task_files=reddit_photo_plan(
            prepared.scope,
            native.c.spec.configuration.files.node_root + "/browser-uploads",
        ),
    )
