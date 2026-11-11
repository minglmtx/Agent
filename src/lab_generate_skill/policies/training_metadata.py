"""One canonical private SFT metadata producer, shared by parent and worker."""

from lab_generate_skill.domain.evidence import EvidenceMetadata


def training_metadata(schema: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="framework-sft-v1",
    )
