"""Fixed Reddit metadata specialization on the shared native JSON transport."""

from lab_generate_skill.domain.site_evidence import SitePrivateEvidencePlan
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.native_private_json import REDDIT_PRIVATE_JSON
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.site_evidence import SitePrivateEvidenceAdmission
from .native_private_evidence import NativePrivateEvidence, check_native_payload

PAYLOAD_SCHEMA = REDDIT_PRIVATE_JSON.content_schema
PRODUCER = REDDIT_PRIVATE_JSON.producer


def check_payload(reference: EvidenceRef, plan: SitePrivateEvidencePlan) -> None:
    check_native_payload(reference, plan, REDDIT_PRIVATE_JSON)


class RedditPrivateEvidence(NativePrivateEvidence):
    def __init__(
        self,
        plan: SitePrivateEvidencePlan,
        context: SitePrivateEvidenceContext,
        evidence: EvidenceStore,
        admission: SitePrivateEvidenceAdmission,
    ) -> None:
        super().__init__(
            plan, context, evidence, admission, profile=REDDIT_PRIVATE_JSON
        )
