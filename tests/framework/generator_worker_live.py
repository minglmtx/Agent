"""Actual installed GPU child + durable parent inference; engineering inputs only."""

from local_generator_fixtures import EngineeringInvocationEngine

import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    MAX_WORKER_PACKET,
)
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    sync_directory,
)
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.generator_model import (
    GeneratorMessage,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import GeneratorInputBudgetExceeded
from generator_engine_live import staging, verify_source, W
from generator_engine_fixtures import config
from generator_model_assets import pinned_model
from local_generator_fixtures import case
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from generator_installation_fixtures import installed_declaration


from generator_worker_diagnostics import record_failure


def test_real_generator_worker(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    receipt = Path(os.environ["LAB_WORKER_SOFTWARE_RECEIPT"])
    verify_source(receipt)
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    c = case(tmp_path)
    op = OperationContext(
        operation_id="worker-engineering",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=700),
    )
    control = c.controls.bind(op)
    original, inventory_sha = pinned_model(W)
    cfg = config().model_copy(update={"context_window": 40960})
    request = c.request.model_copy(
        update={
            "messages": (
                GeneratorMessage(
                    role="system",
                    content="Reply with exactly the requested short text.",
                ),
                GeneratorMessage(role="user", content="Say exactly: Hello world."),
            )
        }
    )
    params = LocalGeneratorParameters(
        max_input_tokens=512,
        max_new_tokens=16,
        top_p=0.9,
        enable_thinking=False,
        seed=request.seed,
        temperature=request.temperature,
    )
    cleanup_allowed = True
    with staging(preserve_if=lambda: not cleanup_allowed) as local:
        for file in original.files:
            copy_pinned_file(Path(original.root), local, file, control)
        local.chmod(0o555)
        artifact = ReleaseArtifact(
            artifact_id="worker-qwen3", root=str(local), files=original.files
        )
        worker = FramedProcessSession(
            (
                str(installed_sources.executable),
                "-I",
                "-B",
                "-m",
                "lab_generate_skill.bootstrap.generator_worker",
            ),
            max_frame_bytes=MAX_WORKER_PACKET,
            cuda_visible_devices=os.environ["CUDA_VISIBLE_DEVICES"],
        )
        # Engineering intent is synced before this one process start. It is not
        # the production launch ledger/authority or a replacement claim.
        intent = {
            "job_id": os.environ["SLURM_JOB_ID"],
            "python": str(installed_sources.executable),
            "artifact": artifact.model_dump(mode="json"),
            "config": cfg.model_dump(mode="json"),
            "production_authority": False,
        }
        with (output / "engineering-launch-intent.json").open("xb") as f:
            f.write(json.dumps(intent, sort_keys=True).encode())
            f.flush()
            os.fsync(f.fileno())
        sync_directory(output)
        cleanup_allowed = False
        engine = SupervisedGeneratorEngine(
            worker,
            "engineering-session",
            artifact,
            cfg,
            installed_declaration(installed_sources),
        )
        primary: BaseException | None = None
        try:
            worker.start(control)
            start = time.monotonic()
            engine.validate(request, params, control)
            load_seconds = time.monotonic() - start
            response = engine.generate(request, params, control)
            repeated = engine.generate(request, params, control)
            assert repeated == response
            try:
                engine.validate(
                    request, params.model_copy(update={"max_input_tokens": 1}), control
                )
            except GeneratorInputBudgetExceeded:
                pass
            else:
                raise AssertionError("Worker must reject overflow without truncation")
            base = LocalGeneratorBaseParameters(
                max_input_tokens=512,
                max_new_tokens=16,
                top_p=0.9,
                enable_thinking=False,
            )
            binding = c.binding.model_copy(
                update={
                    "base_parameters_ref": c.evidence.put(
                        base.model_dump_json().encode(),
                        local_metadata("model-parameters/1"),
                    ),
                    "model_binding_ref": c.evidence.put(
                        json.dumps(intent, sort_keys=True).encode(),
                        local_metadata("model-binding/1"),
                    ),
                }
            )
            inference = DurableGeneratorInference(
                c.root,
                binding,
                EngineeringInvocationEngine(engine),
                c.evidence,
                c.controls,
                c.authority,
            )
            ref = inference.generate(request, op)
            assert inference.generate(request, op) == ref
            saved = GeneratorTextCompletion.model_validate_json(c.evidence.read(ref))
            assert saved.text == response.text
            result = {
                "passed": True,
                "job_id": os.environ["SLURM_JOB_ID"],
                "model_inventory_sha256": inventory_sha,
                "software_receipt": str(receipt),
                "load_and_validate_seconds": load_seconds,
                "output": response.model_dump(mode="json"),
                "same_worker_explicit_generation_repeat_equal": True,
                "budget_rejection_keeps_worker_usable": True,
                "durable_response_ref": ref.model_dump(mode="json"),
                "production_authority": False,
                "production_launch_ledger": False,
                "formal_experiments_run": False,
            }
        except BaseException as error:
            primary = record_failure(output, "operation", error, worker.capture)
            raise primary
        finally:
            try:
                engine.close(
                    c.controls.bind(
                        op.cleanup(
                            "worker-close", now=datetime.now(timezone.utc), seconds=30
                        )
                    )
                )
            except BaseException as cleanup:
                cleanup = record_failure(output, "cleanup", cleanup, worker.capture)
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Live worker and cleanup failed", [primary, cleanup]
                    ) from None
                raise cleanup
            finally:
                observed = worker.capture.termination
                cleanup_allowed = (
                    observed is not None
                    and observed.state in ("not_started", "reaped")
                    and not observed.cleanup_errors
                )
        assert worker.capture.complete and worker.capture.termination is not None
        assert (
            worker.capture.termination.state == "reaped"
            and worker.capture.termination.returncode == 0
        )
        result["worker_pid"] = worker.capture.termination.process_id
        result["graceful_zero_exit"] = True
    verify_source(receipt)
    (output / "actual-worker-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
