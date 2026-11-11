"""Original provider lifetime when its normal authority callback is skipped."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.bootstrap.claimed_actor_resource import claimed_actor_resource
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.claimed_resource_authority import (
    ClaimedActorResourceAuthority,
)
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree
from lab_generate_skill.domain.errors import OwnershipConflict
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.bootstrap.claimed_actor_resource as module


def test_original_provider_scope_releases_pin_when_closure_callback_is_skipped(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        spec, op = r.model.spec, c.native.actor.op
        seen: list[ClaimedActorResourceAuthority] = []
        released: list[str] = []
        failures = [
            OwnershipConflict("Actor termination is unconfirmed"),
            TimeoutError("Original cleanup bookkeeping expired"),
        ]

        class Held:
            def close(self) -> None:
                released.append("original")

        @contextmanager
        def provider(*args: Any, **kwargs: Any) -> Iterator[SupervisedActorEngine]:
            assert kwargs["cleanup_seconds"] == r.owner.task_plan.cleanup_seconds
            authority = kwargs["authority"]
            assert isinstance(authority, ClaimedActorResourceAuthority)
            seen.append(authority)
            authority._scope()
            authority._pin = cast(PinnedUserTree, Held())
            yield cast(SupervisedActorEngine, object())
            raise failures[len(seen) - 1]

        monkeypatch.setattr(module, "registered_actor", provider)
        for failure in failures:
            with pytest.raises(type(failure)) as caught:
                with claimed_actor_resource(
                    r.owner,
                    spec,
                    op,
                    journal=c.p.original.resource.journal,
                    controls=c.p.original.resource.controls,
                    clock=c.p.original.resource.clock,
                    workspace_root=c.p.original.workspace,
                    allocation_verifier=cast(Any, object()),
                ):
                    pass
            assert caught.value is failure
            a = seen[-1]
            assert a._pin is None and not a.close_attempted
            with pytest.raises(OwnershipConflict):
                a.__enter__()
            with pytest.raises(OwnershipConflict):
                a.authorize_start(spec, op, c.p.original.resource.controls.bind(op))
        assert released == ["original", "original"]
        assert c.native.loader.session.calls == 0

        # Cleanup errors retain the original body error. Local handle release
        # does not claim that an unconfirmed process or GPU domain was closed.
        class BrokenHeld:
            def close(self) -> None:
                raise OSError("Original pin close failed")

        a = ClaimedActorResourceAuthority(r.owner, spec, op)
        primary = RuntimeError("Original provider failed")
        with pytest.raises(BaseExceptionGroup) as caught_group:
            with a:
                a._pin = cast(PinnedUserTree, BrokenHeld())
                raise primary
        assert caught_group.value.exceptions[0] is primary
        assert isinstance(caught_group.value.exceptions[1], OSError)
        assert a._pin is None and not a.close_attempted
