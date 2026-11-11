"""Private, bounded delivery of declared logical files to one browser worker."""

import ast
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .browser import BrowserAction
from .browser_session import BrowserSessionSpec
from .release import ReleaseArtifact
from .state_scope import StateScope
from .validation import Contract


class BrowserTaskFilesPlan(Contract):
    schema_version: Literal["browser-task-files-plan/1"] = "browser-task-files-plan/1"
    scope: StateScope
    workspace_root: str = Field(min_length=1, max_length=4096)
    source: ReleaseArtifact
    staging_root: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def bounded_files(self) -> Self:
        workspace, source, staging = map(
            PurePosixPath, (self.workspace_root, self.source.root, self.staging_root)
        )
        for path, raw in zip(
            (workspace, source, staging),
            (self.workspace_root, self.source.root, self.staging_root),
        ):
            if (
                not path.is_absolute()
                or str(path) != raw
                or ".." in path.parts
                or any(c in raw for c in ("\0", "\\"))
            ):
                raise ValueError("Task file paths must be canonical absolute paths")
        if not source.is_relative_to(workspace) or not staging.is_relative_to("/tmp"):
            raise ValueError(
                "Task files require workspace source and private node /tmp"
            )
        if staging.name != "browser-uploads" or len(staging.parts) < 4:
            raise ValueError(
                "Dedicated browser-uploads child of an existing private root required"
            )
        if not 1 <= len(self.source.files) <= 2:
            raise ValueError(
                "Current browser file delivery supports one or two public files"
            )
        if any(
            e.executable
            or not 0 < e.size_bytes <= 1024**2
            or len(PurePosixPath(e.path).parts) != 2
            or PurePosixPath(e.path).parts[0] != "assets"
            for e in self.source.files
        ):
            raise ValueError(
                "Only bounded nonexecutable assets/<filename> files allowed"
            )
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        if self.scope != spec.scope or self.scope.task != spec.task.identity:
            raise ValueError("Browser task files changed original task/attempt scope")
        if "upload_file" not in spec.task.allowed_actions:
            raise ValueError("Task files require the declared upload_file action")


def upload_paths(action: BrowserAction) -> tuple[str, ...]:
    """Read only native upload_file's file argument; [] legitimately clears it."""
    if action.name != "upload_file":
        raise ValueError("Expected upload_file")
    call = ast.parse(action.payload, mode="eval").body
    if (
        not isinstance(call, ast.Call)
        or not isinstance(call.func, ast.Name)
        or call.func.id != "upload_file"
        or len(call.args) > 2
    ):
        raise ValueError("Exactly one native upload_file call required")
    args = dict(zip(("bid", "file"), (ast.literal_eval(n) for n in call.args)))
    for keyword in call.keywords:
        if keyword.arg not in ("bid", "file") or keyword.arg in args:
            raise ValueError("Unknown, expanded or duplicate upload argument")
        args[keyword.arg] = ast.literal_eval(keyword.value)
    if set(args) != {"bid", "file"}:
        raise ValueError("Native upload requires bid and file arguments")
    value = args["file"]
    paths = [value] if type(value) is str else value
    if (
        type(paths) is not list
        or len(paths) > 1
        or any(type(p) is not str or not p for p in paths)
    ):
        raise ValueError(
            "The current single-image input accepts a path or list of zero/one paths"
        )
    return tuple(paths)
