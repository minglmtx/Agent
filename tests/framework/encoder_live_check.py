"""Real offline MiniLM numerical parity on a Slurm node, bound to software receipt."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from importlib.metadata import version

import numpy as np

from lab_generate_skill.adapters.retrieval.cpu_encoder import CpuEncoder
from lab_generate_skill.adapters.retrieval.encoder_files import verify_encoder
from lab_generate_skill.adapters.retrieval.sentence_model import (
    load_sentence_model,
    SentenceModel,
)
from lab_generate_skill.domain.encoding import (
    EncoderFiles,
    EncoderConfig,
    EncoderPackage,
)
from encoder_fixtures import control
from retriever_live_scenario import verify_retriever

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "code/lab-generate-skill"


def verify_source(receipt: Path) -> None:
    record = json.loads(receipt.read_text())
    if not record["passed"] or not record["source_stable_during_checks"]:
        raise ValueError("Software receipt not accepted")
    for relative, digest in record["files"].items():
        if hashlib.sha256((P / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("Source differs from software receipt: " + relative)


def run(output: Path, software: Path) -> dict[str, object]:
    verify_source(software)
    manifest_path = (
        W / "admin/retrieval-encoder-migration-v1/job-4719611/model-manifest.json"
    )
    manifest = EncoderFiles.model_validate_json(manifest_path.read_bytes())
    config = EncoderConfig(
        packages=tuple(
            EncoderPackage.model_validate(dict(name=name, version=version(name)))
            for name in (
                "numpy",
                "sentence-transformers",
                "tokenizers",
                "torch",
                "transformers",
            )
        ),
        cpu_threads=4,
        max_documents=1000,
        max_input_bytes=8 * 1024 * 1024,
    )
    source = W / "assets/retrieval-encoder-20261026-v1/all-MiniLM-L6-v2"
    verify_encoder(source, manifest, config, control())
    with tempfile.TemporaryDirectory(prefix="lab-encoder-", dir="/tmp") as temporary:
        local = Path(temporary) / "model"
        started = time.monotonic()
        shutil.copytree(source, local)
        copy_seconds = time.monotonic() - started
        os.environ["HF_HOME"] = str(Path(temporary) / "hf")
        loads = 0

        def loader(root: Path, threads: int) -> SentenceModel:
            nonlocal loads
            loads += 1
            return load_sentence_model(root, threads)

        backend = CpuEncoder(local, manifest, config, loader=loader)
        # Old path uses exactly the same local asset/runtime and original encode calls.
        old = load_sentence_model(local, 4)
        documents = tuple(
            f"Title: Route skill {i}\nPrinciple: Search the public place {i} and verify its displayed name.\nWhen to apply: When locating a place on a map."
            for i in range(65)
        )
        scenarios = [
            (documents, "Find a public place on the map."),
            (documents, "Find the route to place 14."),
            (tuple(reversed(documents)), "Find a public place on the map."),
            (documents[:6], "Find a public place on the map."),
        ]
        comparisons = []
        for rows, query in scenarios:
            started = time.monotonic()
            result = backend.score(rows, query, control())
            seconds = time.monotonic() - started
            vectors = old.encode(
                list(rows),
                normalize_embeddings=True,
                batch_size=32,
                show_progress_bar=False,
            )
            q = old.encode(
                [query],
                normalize_embeddings=True,
                batch_size=32,
                show_progress_bar=False,
            )[0]
            expected = vectors @ q
            actual = np.asarray(result.scores, dtype=np.float32)
            if not np.array_equal(expected, actual):
                raise AssertionError(
                    "Actual encoded scores differ from original CPU calls"
                )
            ids = [f"skill-{i:03d}" for i in range(len(rows))]
            old_top = sorted(
                range(len(rows)), key=lambda i: (-float(expected[i]), ids[i])
            )[:6]
            new_top = sorted(
                range(len(rows)), key=lambda i: (-result.scores[i], ids[i])
            )[:6]
            if old_top != new_top:
                raise AssertionError("Top-six mismatch")
            comparisons.append(
                dict(
                    documents=len(rows),
                    reused=result.documents_reused,
                    seconds=seconds,
                    max_absolute_error=float(np.max(np.abs(expected - actual))),
                    top6=[ids[i] for i in new_top],
                    result=result.model_dump(mode="json"),
                )
            )
        if loads != 1 or [x["reused"] for x in comparisons] != [
            False,
            True,
            False,
            False,
        ]:
            raise AssertionError("Residency/cache behavior differs")
        retrieval = verify_retriever(Path(temporary) / "evidence", output, backend, old)
        if loads != 1:
            raise AssertionError("Retriever caused an extra model load")
        backend.close(control())
        (output / "config.json").write_text(config.model_dump_json(indent=2) + "\n")
        (output / "model-manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n"
        )
    verify_source(software)
    return dict(
        passed=True,
        job_id=os.environ["SLURM_JOB_ID"],
        software_check=str(software),
        software_sha256=hashlib.sha256(software.read_bytes()).hexdigest(),
        model_source=str(source),
        model_files_sha256=manifest.digest,
        local_copy_seconds=copy_seconds,
        new_model_loads=loads,
        comparisons=comparisons,
        retrieval=retrieval,
        source_stable=True,
        temporary_removed=not Path(temporary).exists(),
        scope="synthetic public inputs; actual offline encoder, no formal dataset or generation API",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--software-check", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        parser.error("Compute allocation required")
    output = (
        W / "experiments/framework-encoder-v1" / ("check-" + os.environ["SLURM_JOB_ID"])
    )
    output.mkdir()
    try:
        result = run(output, args.software_check)
    except Exception as error:
        (output / "traceback.txt").write_text(traceback.format_exc())
        traceback.print_exc()
        result = dict(
            passed=False,
            job_id=os.environ["SLURM_JOB_ID"],
            error_type=type(error).__name__,
        )
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "output": str(output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
