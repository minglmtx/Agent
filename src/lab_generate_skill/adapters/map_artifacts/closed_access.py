"""Explicit engineering read-only access after original site/browser domain closure.

Uses retained acquisition/kernel/closure evidence. It never impersonates an old
controller, executes a task, or grants initialization/write/seal permission.
"""

import os
import json
import threading
from typing import Literal
from lab_generate_skill.adapters.map_artifacts.site_plan import original_site_plan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.lifecycle import ResourceRecord, ClosureReceipt
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactPlan,
    parse_map_artifact_plan,
)
from lab_generate_skill.domain.map_navigation_artifact import MapNavigationArtifactPlan
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.plans.closed_resource import review_resource
from lab_generate_skill.ports.evidence import EvidenceReader


class ClosedMapSourceAccess:
    def __init__(
        self,
        site: SiteResourceSpec,
        browser: BrowserResourceSpec,
        site_record: ResourceRecord,
        browser_record: ResourceRecord,
        store: EvidenceReader,
        control: OperationControl,
        *,
        allow_failed_consumer: bool = False,
    ) -> None:
        if type(allow_failed_consumer) is not bool:
            raise TypeError(
                "Closed failed-consumer reads require an explicit boolean selection"
            )
        control.checkpoint()
        site = SiteResourceSpec.model_validate(site)
        browser = BrowserResourceSpec.model_validate(browser)
        inputs, files = site.configuration.map_inputs, browser.configuration.map_inputs
        if inputs is None or inputs.scope != browser.configuration.spec.scope:
            raise OwnershipConflict("Original site/browser Map scope differs")
        self._browser_plan: MapPrivateArtifactPlan | None = None
        if isinstance(inputs, MapNavigationWorkerInputs):
            init = browser.configuration.initialization
            if (
                files is not None
                or not isinstance(init, MapNavigationInitialization)
                or init.native_contract_sha256 != inputs.native_contract_sha256
            ):
                raise OwnershipConflict(
                    "Original navigation closed browser contract differs"
                )
            init.check(browser.configuration.spec)
        elif files is None or inputs.scope != files.plan.scope:
            raise OwnershipConflict("Original MapData closed browser files missing")
        else:
            self._browser_plan = files.plan
        if site.token.owner != browser.token.owner or (
            files is not None
            and (
                files.plan.token != browser.token
                or files.plan.workspace_root != site.configuration.files.workspace_root
            )
        ):
            raise OwnershipConflict("Original Map closed resources/workspace differ")
        for spec, record in ((site, site_record), (browser, browser_record)):
            reviewed = review_resource(
                record.model_dump(mode="json"),
                spec.token,
                store,
                control,
                allow_failed_consumer=allow_failed_consumer,
            )
            if spec == browser:
                self.browser_closure = ClosureReceipt.model_validate_json(
                    json.dumps(reviewed["ending"]["closure"])
                )
            if reviewed["configuration"] != spec.model_dump(mode="json"):
                raise OwnershipConflict(
                    "Original closed acquisition configuration changed"
                )
        self.site, self.browser = site, browser
        self.plans: dict[str, MapArtifactPlan] = {}
        self.owner = os.getpid(), threading.get_ident()
        control.checkpoint()

    def _check(self, control: OperationControl) -> None:
        control.checkpoint()
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Read-only Map review capability left its owner")

    @property
    def browser_plan(self) -> MapPrivateArtifactPlan:
        if self._browser_plan is None:
            raise OwnershipConflict(
                "Navigation has no MapData browser process file plan"
            )
        return self._browser_plan

    def plan(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> MapArtifactPlan:
        self._check(control)
        value = original_site_plan(self.site.configuration, request)
        navigation = isinstance(
            self.site.configuration.map_inputs, MapNavigationWorkerInputs
        )
        if navigation != isinstance(value, MapNavigationArtifactPlan):
            raise OwnershipConflict("Closed Map review changed original file family")
        self.plans[value.digest] = value
        return value

    def verify(
        self,
        plan: MapArtifactPlan,
        phase: Literal["initialize", "write", "seal", "read"],
        control: OperationControl,
    ) -> None:
        self._check(control)
        plan = parse_map_artifact_plan(plan)
        if phase != "read" or (
            plan != self._browser_plan and self.plans.get(plan.digest) != plan
        ):
            raise OwnershipConflict(
                "Closed Map review only reads its exact original file plans"
            )
        control.checkpoint()
