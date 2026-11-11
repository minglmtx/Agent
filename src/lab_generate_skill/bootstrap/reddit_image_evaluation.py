"""One current evaluator using original input/projection and Reddit native rules."""

from lab_generate_skill.sites.reddit.evidence_schema import ImageEvidence
from lab_generate_skill.sites.reddit.evaluation_reads import ImageEvaluationReads
from lab_generate_skill.sites.reddit.tasks.image_rules import decide_image
from lab_generate_skill.evaluators.reddit.native_image import ImageEvaluator
from .reddit_native_image import load_image_inputs
from .reddit_issued_ax import last_issued_ax


def reddit_image_evaluator(selected: ImageEvidence) -> ImageEvaluator:
    return ImageEvaluator(
        selected, ImageEvaluationReads(load_image_inputs, last_issued_ax), decide_image
    )
