"""Compute-node read-only history entry. Prints exact bytes, never executes them."""

import argparse
import os
import sys
from pathlib import Path
from lab_generate_skill.bootstrap.historical_reading import read_historical_reference
from lab_generate_skill.domain.historical_reference import HistoricalKey


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--map-sha256", required=True)
    parser.add_argument("--original-path", required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        parser.error("Historical record reading requires a Slurm compute allocation")
    sys.stdout.buffer.write(
        read_historical_reference(
            args.root,
            args.map,
            args.map_sha256,
            HistoricalKey(original_path=args.original_path, sha256=args.sha256),
        )
    )


if __name__ == "__main__":
    main()
