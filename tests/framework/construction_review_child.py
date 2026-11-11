"""Fixed test child: persistent unit evidence -> readonly production review_run."""

import json
import os
from pathlib import Path
import sys
from construction_review_recorded_fixtures import UnitReviewBundle, read_recorded_bundle
from lab_generate_skill.application.review_run import review_run


def main() -> None:
    bundle = UnitReviewBundle.model_validate_json(Path(sys.argv[1]).read_bytes())
    plan, deps = read_recorded_bundle(bundle)
    receipt = review_run(plan, deps)
    Path(sys.argv[2]).write_text(receipt.model_dump_json())
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "status": receipt.status,
                "training_admission": receipt.training_admission,
                "findings": len(receipt.findings),
            }
        )
    )


if __name__ == "__main__":
    main()
