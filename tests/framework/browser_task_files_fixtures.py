"""Small pinned engineering files; no claim about Reddit native publication."""

import hashlib
from pathlib import Path
from lab_generate_skill.adapters.browsergym.task_files import LocalBrowserTaskFiles
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_task_files import BrowserTaskFilesPlan
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from browsergym_fixtures import spec


def upload_spec(url: str = "http://127.0.0.1:8000/") -> BrowserSessionSpec:
    old = spec(url)
    task = old.task.model_copy(
        update={"allowed_actions": (*old.task.allowed_actions, "upload_file")}
    )
    return old.model_copy(update={"task": task})


def delivery(
    source: Path, parent: Path, frozen: BrowserSessionSpec, size: int = 31
) -> LocalBrowserTaskFiles:
    (source / "assets").mkdir()
    entries = []
    for name, content in [("photo.jpg", b"x" * size), ("other.jpg", b"y")]:
        (source / "assets" / name).write_bytes(content)
        entries.append(
            ReleaseFile(
                path="assets/" + name,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                executable=False,
            )
        )
    plan = BrowserTaskFilesPlan(
        scope=frozen.scope,
        workspace_root=str(source),
        source=ReleaseArtifact(
            artifact_id="public-photos", root=str(source), files=tuple(entries)
        ),
        staging_root=str(parent / "browser-uploads"),
    )
    return LocalBrowserTaskFiles(plan)


def action(
    payload: str = "upload_file('7', 'assets/photo.jpg')", name: str = "upload_file"
) -> BrowserAction:
    return BrowserAction(
        action_id="upload",
        protocol_id="browsergym-highlevel-v1",
        name=name,
        payload=payload,
    )
