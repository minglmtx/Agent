"""Original pinned photographs through real BrowserGym file chooser; no site DB."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import tempfile
import threading
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.browsergym.task_files import LocalBrowserTaskFiles
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.reddit_browser_files import reddit_photo_plan
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from browsergym_fixtures import CHROMIUM, LoopbackAuthority, operation
from browser_task_files_fixtures import upload_spec
from test_slurm_commands import guard


def frozen(url: str = "http://127.0.0.1:8000/") -> BrowserSessionSpec:
    base = upload_spec(url)
    task_id = base.task.identity.model_copy(
        update={
            "site": "reddit",
            "family": "native_image_submission",
            "contract_version": 1,
            "split": "train",
            "source_task_id": "292ad3eb62765c7e6d93",
        }
    )
    return base.model_copy(
        update={
            "task": base.task.model_copy(update={"identity": task_id}),
            "scope": base.scope.model_copy(update={"task": task_id}),
        }
    )


def test_original_photo_fixture_plan_is_bounded_and_rejects_wrong_family() -> None:
    scope = frozen().scope
    plan = reddit_photo_plan(scope, "/tmp/engineering-only/browser-uploads")
    assert [(p.path, p.size_bytes) for p in plan.source.files] == [
        ("assets/fixed-beach-sunset-photo.jpg", 224646),
        ("assets/fixed-landscape-photo.jpg", 259654),
    ]
    with pytest.raises(ValueError, match="family"):
        reddit_photo_plan(upload_spec().scope, "/tmp/engineering-only/browser-uploads")


def test_original_photos_native_upload_clear_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b'<html><title>Upload fixture</title><label for="photo">Photo</label><input type="file" id="photo" accept="image/*"><p id="status">No file</p><script>document.getElementById("photo").onchange=()=>{const f=document.getElementById("photo").files[0];document.getElementById("status").textContent=f?f.name+":"+f.size:"No file";};</script></html>'
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old = Path.cwd()
    engine: BrowserGymEngine | None = None
    primary: BaseException | None = None
    with tempfile.TemporaryDirectory(
        prefix="lab-native-upload-", dir="/tmp"
    ) as directory:
        try:
            spec = frozen(f"http://127.0.0.1:{server.server_port}/")
            files = LocalBrowserTaskFiles(
                reddit_photo_plan(spec.scope, str(Path(directory) / "browser-uploads"))
            )
            engine = BrowserGymEngine(
                spec,
                LoopbackAuthority(),
                SystemClock(),
                NavigatePublicTask(),
                task_files=files,
            )
            initial = engine.start(operation(spec, "initial"), control=guard(90))
            assert (
                initial.observation.sequence == 0
                and not initial.observation.last_action_error
            )
            text = initial.observation.text or ""
            match = re.search(r"\[([^\]]+)\] button [\'\"]Photo[\'\"]", text)
            assert match, text
            bid = match.group(1)
            for index, (argument, expected_name, expected_size) in enumerate(
                [
                    (
                        "'assets/fixed-beach-sunset-photo.jpg'",
                        "fixed-beach-sunset-photo.jpg",
                        224646,
                    ),
                    (
                        "['assets/fixed-landscape-photo.jpg']",
                        "fixed-landscape-photo.jpg",
                        259654,
                    ),
                    ("[]", None, 0),
                ],
                1,
            ):
                payload = f"upload_file({bid!r}, {argument})"
                action = BrowserAction(
                    action_id=f"upload-{index}",
                    protocol_id="browsergym-highlevel-v1",
                    name="upload_file",
                    payload=payload,
                )
                returned = engine.step(
                    action, operation(spec, f"step-{index}"), control=guard(45)
                )
                assert (
                    returned.action == action and returned.observation.sequence == index
                )
                assert (
                    not returned.observation.last_action_error
                ), returned.observation.last_action_error
                selected = engine.env.page.locator("#photo").evaluate(
                    "async e => Promise.all(Array.from(e.files).map(async f => ({name:f.name,size:f.size,sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await f.arrayBuffer()))).map(b=>b.toString(16).padStart(2,'0')).join('')})))"
                )
                assert selected == (
                    []
                    if expected_name is None
                    else [
                        {
                            "name": expected_name,
                            "size": expected_size,
                            "sha256": files.plan.source.files[index - 1].sha256,
                        }
                    ]
                )
        except BaseException as error:
            primary = error
            raise
        finally:
            errors: list[BaseException] = []
            if engine is not None:
                try:
                    engine.close(
                        operation(engine.spec, "cleanup-parent").cleanup(
                            "close", now=datetime.now(timezone.utc), seconds=30
                        ),
                        control=guard(30),
                    )
                except BaseException as error:
                    errors.append(error)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            if thread.is_alive():
                errors.append(RuntimeError("Original HTTP thread did not stop"))
            if errors:
                raise BaseExceptionGroup(
                    "Native upload or cleanup failed",
                    ([primary] if primary else []) + errors,
                )
    assert engine is not None and str(engine.state) == "closed" and Path.cwd() == old
    assert not Path(directory).exists()
