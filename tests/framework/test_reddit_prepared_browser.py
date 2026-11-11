"""Verify the common PreparedBrowserBinding really calls native Reddit semantics."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceError
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.sites.reddit.tasks.image_browser_binding import (
    ImageBrowserChecks,
)
from reddit_prepared_browser_fixtures import bound
from reddit_preparation_fixtures import put
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "account",
        "username",
        "file-pin",
        "file-source",
        "staging",
        "attempt",
        "context",
        "prepared",
        "site",
        "configuration",
        "native-missing",
        "checker-missing",
        "checker-denied",
    ],
)
def test_common_entry_recomputes_native_account_and_exact_photos_before_spawn(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with bound(tmp_path, node_path, monkeypatch) as c:
        b, p = c.browser, c.qualified.preparation
        selected = b.spec.configuration.initialization
        assert isinstance(selected, RedditNativeImageInitialization)
        if fault in ("account", "username"):
            selected = selected.model_copy(
                update=(
                    {"native_account_id": selected.native_account_id + 1}
                    if fault == "account"
                    else {"native_account_username": "foreign"}
                )
            )
        elif fault in ("file-pin", "file-source", "staging", "attempt", "context"):
            files = selected.task_files
            if fault == "file-pin":
                source = files.source.model_copy(
                    update={
                        "files": (
                            files.source.files[0].model_copy(
                                update={"sha256": "f" * 64}
                            ),
                            files.source.files[1],
                        )
                    }
                )
                files = files.model_copy(update={"source": source})
            elif fault == "file-source":
                files = files.model_copy(
                    update={
                        "source": files.source.model_copy(
                            update={"root": files.source.root + "/foreign"}
                        )
                    }
                )
            elif fault == "staging":
                files = files.model_copy(
                    update={"staging_root": "/tmp/foreign/browser-uploads"}
                )
            else:
                files = files.model_copy(
                    update={
                        "scope": files.scope.model_copy(
                            update={
                                (
                                    "attempt_id" if fault == "attempt" else "context_id"
                                ): "foreign"
                            }
                        )
                    }
                )
            selected = selected.model_copy(update={"task_files": files})
        elif fault == "prepared":
            selected = selected.model_copy(
                update={
                    "prepared_ref": selected.prepared_ref.model_copy(
                        update={"producer": "foreign"}
                    )
                }
            )
        elif fault == "site":
            foreign = c.binding.site.model_copy(
                update={
                    "instance": c.binding.site.instance.model_copy(
                        update={
                            "endpoint": "http://127.0.0.1:12099/",
                            "ports": (12099, 12002),
                        }
                    )
                }
            )
            assert foreign.instance.endpoint != c.binding.site.instance.endpoint
            selected = selected.model_copy(update={"site_ref": put(p.store, foreign)})
        elif fault == "configuration":
            changed = p.configuration.model_copy(
                update={
                    "files": p.configuration.files.model_copy(
                        update={
                            "source_path": p.configuration.files.workspace_root
                            + "/foreign/reddit.sif"
                        }
                    )
                }
            )
            c.binding.site_spec = c.binding.site_spec.model_copy(
                update={"configuration": changed}
            )
        elif fault == "native-missing":
            assert p.native.task.snapshot is not None
            (
                node_path
                / "private-evidence/blobs"
                / p.native.task.snapshot.native_before.payload_ref.sha256
            ).unlink()
        elif fault == "checker-missing":
            c.binding.task_checks = None
        elif fault == "checker-denied":
            checks = c.binding.task_checks
            assert isinstance(checks, ImageBrowserChecks)

            def denied(*args: object, **kwargs: object) -> None:
                raise PermissionError("explicit native checker denial")

            monkeypatch.setattr(checks, "check", denied)
        b.spec = b.spec.model_copy(
            update={
                "configuration": b.spec.configuration.model_copy(
                    update={"initialization": selected}
                )
            }
        )
        before = p.native.reader.calls
        if fault == "none":
            authority = PreparedBrowserAuthority(b.spec, c.binding, b.authority)
            authority.authorize_start(b.spec, b.op, guard())
            assert (
                c.binding.verify(b.spec, b.op, guard()).public_task
                == p.inputs.public_task
            )
        else:
            with pytest.raises(
                (ValueError, OwnershipConflict, EvidenceError, PermissionError)
            ):
                authority = PreparedBrowserAuthority(b.spec, c.binding, b.authority)
                authority.authorize_start(b.spec, b.op, guard())
        assert p.native.reader.calls == before and not b.channels
