"""Read the original preparation and still-acquired site before browser use.

This joins existing records; it neither prepares a site nor publishes a second
initial observation. Physical/source/exclusivity authority remains mandatory in
PreparationRecords and the enclosing BrowserResourceAuthority.
"""

import hashlib
import json
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.browser_initialization import (
    AdminProductInitialization,
    ShoppingOrderInitialization,
)
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.preparation import EnvironmentBaseline, PreparedTask
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl, ResourceJournal
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.ports.prepared_browser import PreparedBrowserInputs
from lab_generate_skill.ports.prepared_browser import PreparedBrowserInputScope
from .state_reads import StateReads
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)


def read_operation(
    original: OperationContext, caller: OperationContext
) -> OperationContext:
    """Only a bounded read of original facts, never permission to replay effects."""
    return OperationContext.model_validate(
        {
            **original.model_dump(),
            "operation_id": "browser-read-"
            + hashlib.sha256(
                (original.operation_id + "/" + caller.operation_id).encode()
            ).hexdigest(),
            "parent_operation_id": original.operation_id,
            "mode": "cleanup",
            "deadline": caller.deadline,
            "cancellation_ref": caller.cancellation_ref,
        }
    )


class PreparedBrowserBinding:
    def __init__(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        site_operation: OperationContext,
        *,
        evidence: EvidenceReader,
        preparations: PreparationRecords,
        journal: ResourceJournal,
        task_checks: PreparedBrowserTaskChecks | None = None,
        inputs: PreparedBrowserInputScope | None = None,
    ) -> None:
        self.publication = PreparedPublication.model_validate(publication)
        self.site_spec = SiteResourceSpec.model_validate(site_spec)
        self.site = SiteResourceStarted.model_validate(site)
        self.site_operation = OperationContext.model_validate(site_operation)
        self.site_spec.check_operation(self.site_operation, "execute")
        self.reads, self.preparations, self.journal = (
            StateReads(evidence),
            preparations,
            journal,
        )
        self.task_checks = task_checks
        self.inputs = inputs

    def verify(
        self,
        browser: BrowserResourceSpec,
        op: OperationContext,
        control: OperationControl,
    ) -> PreparedTask:
        control.checkpoint()
        held = None
        if self.inputs is not None:
            self.inputs.check(op, control)
            held = self.inputs.prepared_browser
            if held is not None and (
                held.binding is not self or held.browser != browser
            ):
                raise OwnershipConflict(
                    "Prepared browser inputs changed original binding"
                )
        browser.check_operation(op, "execute")
        config = browser.configuration
        selection = config.initialization
        if not isinstance(
            selection,
            (
                AdminProductInitialization,
                AdminNavigationInitialization,
                ShoppingOrderInitialization,
                ShoppingCategoryInitialization,
                GitlabSshKeyInitialization,
                GitlabGroupInitialization,
                RedditNativeImageInitialization,
                MapNativeInitialization,
                MapNavigationInitialization,
            ),
        ):
            raise OwnershipConflict("Prepared browser requires explicit initialization")
        selection.check(config.spec)
        if (
            isinstance(
                selection,
                (
                    AdminNavigationInitialization,
                    ShoppingCategoryInitialization,
                    GitlabSshKeyInitialization,
                    GitlabGroupInitialization,
                    RedditNativeImageInitialization,
                    MapNativeInitialization,
                    MapNavigationInitialization,
                ),
            )
            and self.task_checks is None
        ):
            raise OwnershipConflict(
                "Selected prepared browser requires fixed task checks"
            )
        expected_site = (
            "map"
            if isinstance(
                selection, (MapNativeInitialization, MapNavigationInitialization)
            )
            else (
                "reddit"
                if isinstance(selection, RedditNativeImageInitialization)
                else (
                    "gitlab"
                    if isinstance(
                        selection,
                        (GitlabSshKeyInitialization, GitlabGroupInitialization),
                    )
                    else (
                        "shopping"
                        if isinstance(
                            selection,
                            (
                                ShoppingOrderInitialization,
                                ShoppingCategoryInitialization,
                            ),
                        )
                        else "shopping_admin"
                    )
                )
            )
        )
        if self.site_spec.configuration.site_id != expected_site:
            raise OwnershipConflict(
                "Prepared browser changed original site initialization kind"
            )
        if (
            selection.prepared_ref != self.publication.prepared_ref
            or selection.endpoint != self.site.instance.endpoint
            or browser.token.owner != self.site_spec.token.owner
            or browser.slurm.execution != self.site_spec.slurm.execution
            or browser.slurm.parent != self.site_spec.slurm.parent
            or config.installation != self.site_spec.configuration.installation
            or self.site.instance.files != self.site_spec.configuration.files
        ):
            raise OwnershipConflict(
                "Browser changed original preparation/site/release/allocation"
            )
        actual_site = (
            self.site
            if held is not None
            else self.reads.parse(
                selection.site_ref,
                "site-resource-started/1",
                SiteResourceStarted,
                control,
            )
        )
        if actual_site != self.site:
            raise OwnershipConflict(
                "Browser site reference differs from original resource"
            )
        site_bodies = self._site_acquired(op, control, held)
        request = (
            held.request
            if held is not None
            else self.reads.parse(
                self.publication.selection.request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
        )
        prepared = self.preparations.load(
            self.publication, read_operation(request.operation, op)
        )
        environment = (
            held.environment
            if held is not None
            else self.reads.parse(
                self.publication.selection.environment_ref,
                "environment-baseline/1",
                EnvironmentBaseline,
                control,
            )
        )
        if (
            prepared.scope != config.spec.scope
            or prepared.public_task != config.spec.task
            or environment.scope != prepared.scope
            or environment.allocation != self.site_spec.token
        ):
            raise OwnershipConflict(
                "Prepared browser changed original task/attempt/context/site"
            )
        if isinstance(
            selection,
            (
                AdminNavigationInitialization,
                ShoppingCategoryInitialization,
                GitlabSshKeyInitialization,
                GitlabGroupInitialization,
                RedditNativeImageInitialization,
                MapNativeInitialization,
                MapNavigationInitialization,
            ),
        ):
            assert self.task_checks is not None
            if held is None or held.checked_by is not self.task_checks:
                self.task_checks.check(
                    self.publication,
                    self.site_spec,
                    self.site,
                    request,
                    selection,
                    control,
                )
        if self.inputs is not None:
            self.inputs.check(op, control)
            self.inputs.prepared_browser = PreparedBrowserInputs(
                self, browser, request, environment, self.task_checks, site_bodies
            )
        control.checkpoint()
        return prepared

    def _site_acquired(
        self,
        op: OperationContext,
        control: OperationControl,
        held: PreparedBrowserInputs | None = None,
    ) -> tuple[tuple[EvidenceRef, bytes], ...]:
        record = self.journal.read(
            self.site_spec.token, read_operation(self.site_operation, op)
        )
        if record.token != self.site_spec.token or record.state != "acquired":
            raise OwnershipConflict("Browser requires the original acquired site")
        event = record.events[-1]
        if len(event.evidence) != 1:
            raise OwnershipConflict("Site acquisition must identify its original fact")
        if held is None:
            bodies = tuple(
                (ref, self.reads.read(ref, control))
                for ref in (event.evidence[0], self.site.evidence)
            )
        else:
            bodies = held.site_bodies
            if tuple(ref for ref, _ in bodies) != (
                event.evidence[0],
                self.site.evidence,
            ):
                raise OwnershipConflict(
                    "Site journal changed original acquisition facts"
                )
        for ref, raw in bodies:
            require_complete_bytes(ref, raw)
        acquired, started = (json.loads(raw) for _, raw in bodies)
        digest = hashlib.sha256(self.site_spec.model_dump_json().encode()).hexdigest()
        for fact in (acquired, started):
            if (
                fact.get("schema_version"),
                fact.get("spec_sha256"),
                fact.get("token"),
                fact.get("state"),
            ) != (
                "site-resource-fact/1",
                digest,
                self.site_spec.token.model_dump(mode="json"),
                "acquired",
            ):
                raise OwnershipConflict(
                    "Site fact changed original resource declaration"
                )
        if (
            acquired.get("operation") != event.operation.model_dump(mode="json")
            or acquired.get("details")
            != {"ready": self.site.ready.model_dump(mode="json"), "site_started": False}
            or started.get("details")
            != {
                "ready_ref": event.evidence[0].model_dump(mode="json"),
                "started": self.site.instance.model_dump(mode="json"),
            }
        ):
            raise OwnershipConflict("Site startup does not follow original acquisition")
        start_op = OperationContext.model_validate_json(
            json.dumps(started.get("operation"))
        )
        self.site_spec.check_operation(start_op, "execute")
        if start_op.parent_operation_id != self.site_operation.operation_id:
            raise OwnershipConflict("Site startup changed original operation")
        control.checkpoint()
        return bodies
