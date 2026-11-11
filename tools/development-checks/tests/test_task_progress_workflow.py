"""CLI integration scenarios; run under Slurm using system Python."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "task-progress-workflow.py"


class WorkflowScenarios(unittest.TestCase):
    def call(self, stage, result="show", resources="closed", basis="fixture#evidence"):
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--stage", stage,
                 "--result", result, "--resources", resources, "--basis", basis],
                cwd=directory, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])
        return proc

    def report(self, *args, **kwargs):
        proc = self.call(*args, **kwargs)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertFalse(report["runtime_authority"])
        self.assertFalse(report["evidence_verified"])
        return report

    def test_reused_prefix_and_current_execution(self):
        for stage, result, resources, target in (
            ("prepare", "reused", "none", "initialize"),
            ("initialize", "done", "live", "actor"),
            ("actor", "done", "live", "review"),
            ("review", "done", "live", "cleanup"),
        ):
            report = self.report(stage, result, resources)
            self.assertEqual((report["action"], report["next_stage"]), ("next", target))

    def test_cleanup_completion_is_not_task_completion(self):
        self.assertEqual(self.report("cleanup", "done")["action"], "reconcile_exit")
        self.assertEqual(self.report("cleanup", "close")["action"], "reported_closed")
        self.assertEqual(self.report("cleanup", "close", "live")["action"], "cleanup_first")
        self.assertEqual(self.report("cleanup", "close", "unknown")["action"], "inspect_resources")

    def test_business_failure_requires_review_then_cleanup(self):
        rejected = self.call("actor", "business_failure")
        self.assertEqual((rejected.returncode, rejected.stdout), (2, ""))
        accepted = self.report("review", "business_failure", "live")
        self.assertEqual(accepted["next_stage"], "cleanup")

    def test_missing_evidence_supplements_without_advancing_or_restarting(self):
        report = self.report("review", "evidence_gap")
        self.assertEqual((report["action"], report["next_stage"]), ("supplement", "review"))
        self.assertIn("最小补充实验", report["directive"])
        self.assertIn("新证据独立归属", report["directive"])

    def test_interruptions_require_cleanup_without_losing_failed_stage(self):
        for result in ("failed", "unknown", "interrupted", "evidence_gap", "interface_gap", "blocked", "outer_flow"):
            report = self.report("actor", result, "live")
            self.assertEqual((report["action"], report["next_stage"]), ("cleanup_first", "actor"))
        self.assertEqual(self.report("actor", "failed")["action"], "repair")
        self.assertEqual(self.report("actor", "unknown")["action"], "reconcile")
        self.assertEqual(self.report("actor", "interrupted")["action"], "reconcile")

    def test_partial_acquire_and_resource_uncertainty(self):
        self.assertEqual(self.report("prepare", "failed", "cleanup_due")["action"], "cleanup_first")
        self.assertEqual(self.report("prepare", "done", "unknown")["action"], "inspect_resources")
        self.assertEqual(self.report("actor", "waiting", "live")["action"], "wait")

    def test_contract_skip_and_outer_workflow(self):
        report = self.report("initialize", "not_applicable", "none", "fixture#no-initialization")
        self.assertEqual(report["next_stage"], "actor")
        self.assertEqual(self.report("prepare", "outer_flow", "none")["action"], "delegate")
        rejected = self.call("initialize", "not_applicable", "none", " ")
        self.assertEqual((rejected.returncode, rejected.stdout), (2, ""))

    def test_invalid_inputs_do_not_emit_a_transition(self):
        for args in (("other",), ("actor", "retry"), ("actor", "done", "other"),
                     ("actor", "close"), ("prepare", "done", "none", "")):
            rejected = self.call(*args)
            self.assertEqual((rejected.returncode, rejected.stdout), (2, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
