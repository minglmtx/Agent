"""Explicit SSH evaluation v2 declares the actual current browser schema4."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator
from gitlab_evaluator_fixtures import evaluation_case
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_current_ssh_schema_descriptor_and_version_are_explicit(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        evaluator = gitlab_ssh_evaluator(c.selected)
        assert (
            next(
                f
                for f in evaluator.requirements(c.contract).facts
                if f.name == "browser"
            ).content_schema
            == "browser-resource-spec/4"
        )
        result = evaluator.evaluate(c.contract, c.source.preparation.store, guard())
        assert (
            result.evaluator_version == "gitlab-complete-native-ssh-v2"
            and result.status == "success"
        )
        requirements = c.contract.requirements.model_copy(
            update={
                "facts": tuple(
                    (
                        f.model_copy(
                            update={"content_schema": "browser-resource-spec/3"}
                        )
                        if f.name == "browser"
                        else f
                    )
                    for f in c.contract.requirements.facts
                )
            }
        )
        with pytest.raises(ValueError, match="Unsupported"):
            evaluator.requirements(
                c.contract.model_copy(update={"requirements": requirements})
            )
