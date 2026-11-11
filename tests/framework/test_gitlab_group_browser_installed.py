"""Installed fixed Group browser on controlled HTTP; no benchmark site or Actor."""

from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, os, threading
from pathlib import Path
from urllib.parse import parse_qs
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from browser_resource_fixtures import resource_case
from browser_worker_fixtures import configuration
from test_browser_resource_installed import EngineeringTreeAuthority
from test_linux_cgroups import actual_slurm_execution
from gitlab_login_native import LOGIN
from test_slurm_commands import guard

GROUP_FORM = b"""<html><title>New group</title><script>window.gon={current_user_id:17};</script><h1>New group</h1><form method="post" action="/groups"><label for="group-name">Group name</label><input id="group-name" name="group[name]" value=""><button type="submit">Create group</button></form></html>"""


def test_installed_group_fixture_preflight() -> None:
    class Forms(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.forms: list[dict[str, str | None]] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag == "form":
                self.forms.append(dict(attrs))

    parser = Forms()
    parser.feed(GROUP_FORM.decode())
    assert parser.forms == [dict(method="post", action="/groups")]
    assert b'value=""' in GROUP_FORM and b"current_user_id:17" in GROUP_FORM
    assert "controlled-csrf" in LOGIN and "/users/sign_in" in LOGIN


def test_installed_fixed_group_unique_initial_and_original_resource_close(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _ = actual_slurm_execution()
    posts: list[str] = []
    public_gets: list[str] = []
    worker_before_navigation: list[BrowserWorkerAcquiredFact] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path in ("/users/sign_in", "/groups/new"):
                record = c.journal.read(c.spec.token, c.op)
                assert record.state == "acquired"
                fact = BrowserWorkerAcquiredFact.model_validate_json(
                    c.evidence.read(record.events[-1].evidence[0], guard())
                )
                fact.check_spec(c.spec)
                worker_before_navigation.append(fact)
            if self.path == "/users/sign_in":
                data = LOGIN.encode()
            elif self.path == "/groups/new":
                assert "controlled_auth=1" in self.headers.get("Cookie", "")
                public_gets.append(self.path)
                data = GROUP_FORM
            else:
                data = b"<html><title>Authenticated</title><script>window.gon={current_user_id:17};</script><p>Authenticated</p></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            # Only native initialization login is permitted. No group creation.
            assert self.path == "/users/sign_in"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            fields = parse_qs(body.decode())
            assert fields.get("authenticity_token") == ["controlled-csrf"]
            assert fields.get("user[login]") and fields.get("user[password]")
            posts.append(self.path)
            self.send_response(303)
            self.send_header("Set-Cookie", "controlled_auth=1; Path=/")
            self.send_header("Location", "/")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = None
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/"
        base = configuration(storage_installation(installed_sources), endpoint)
        identity = base.spec.task.identity.model_copy(
            update={
                "source_task_id": "controlled-group",
                "task_id": "controlled-group",
                "site": "gitlab",
                "family": "group_creation",
                "contract_version": 1,
                "split": "train",
            }
        )
        owner = base.spec.scope.owner.model_copy(update={"job_id": execution.job_id})
        scope = base.spec.scope.model_copy(update={"owner": owner, "task": identity})
        public = PublicTask(
            identity=identity,
            goal="Inspect the new group form",
            start_url=endpoint + "groups/new",
            allowed_actions=("click",),
        )
        session = BrowserSessionSpec.model_validate(
            {**base.spec.model_dump(), "scope": scope, "task": public}
        )
        root = tmp_path / "resource"
        root.mkdir()
        # These are explicit leaf-test declarations, never preparation authority.
        # Real preparation bytes/binding are checked separately by the joined test.
        from evidence_control_fixtures import EvidenceFixtureStore

        store_root = tmp_path / "leaf-evidence"
        store_root.mkdir()
        store = EvidenceFixtureStore(store_root)

        def declared_ref(schema: str) -> EvidenceRef:
            return store.put(
                b'{"engineering_leaf_declaration_only":true}',
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema=schema,
                    visibility="private",
                    producer="controlled-initializer-declaration",
                ),
                guard(),
            )

        init = GitlabGroupInitialization(
            endpoint=endpoint,
            native_account_id=17,
            prepared_ref=declared_ref("prepared-task/1"),
            site_ref=declared_ref("site-resource-started/1"),
        )
        config = BrowserWorkerConfiguration.model_validate(
            {**base.model_dump(), "spec": session, "initialization": init}
        )
        c = resource_case(root, monkeypatch, config=config, store=store, real_step=True)
        monkeypatch.setattr(
            "lab_generate_skill.adapters.browsergym.resource.FramedProcessSession",
            FramedProcessSession,
        )
        c.authority = EngineeringTreeAuthority(store)
        c.op = c.op.model_copy(
            update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=90)}
        )
        with registered_browser(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=store,
            controls=c.controls,
            clock=c.clock,
            authority=c.authority,
        ) as browser:
            assert isinstance(browser.engine, SupervisedBrowserSession)
            client = browser.engine
            assert (
                browser.observation_ref is not None and client.last_readout is not None
            )
            observation = Observation.model_validate_json(
                store.read(browser.observation_ref, guard())
            )
            assert observation.sequence == 0 and len(observation.tabs) == 1
            assert observation.tabs[0].url == public.start_url and "New group" in (
                observation.text or ""
            )
            assert (
                len(posts) == len(public_gets) == 1
                and len(worker_before_navigation) == 2
            )
            assert client.last_readout.action is None and client.sequence == 2
            assert not any(
                e.kind in ("before_action", "after_action")
                for e in client.last_readout.events
            )
        ended = c.journal.read(
            c.spec.token,
            c.op.cleanup(
                "group-leaf-closed-read", now=datetime.now(timezone.utc), seconds=20
            ),
        )
        assert ended.state == "closed"
        ending = json.loads(store.read(ended.events[-1].evidence[0], guard()))
        assert ending["details"]["cleanup_errors"] == []
        term = client.channel.capture.termination
        assert (
            term is not None
            and term.state == "reaped"
            and term.returncode == 0
            and not term.kill_requested
        )
        assert not term.cleanup_errors
        proof = dict(
            engineering_only=True,
            actual_installed_worker=True,
            actual_Chromium=True,
            actual_benchmark_site=False,
            actual_Group_preparation_authority=False,
            original_source_execution=False,
            Actor_calls=0,
            paid_calls=0,
            worker_acquired_before_all_native_navigation=True,
            private_login_posts=len(posts),
            group_creations=0,
            public_form_navigations=len(public_gets),
            unique_public_sequence=observation.sequence,
            launcher_returncode=term.returncode,
            kill_requested=term.kill_requested,
            resource_state=ended.state,
            cleanup_errors=ending["details"]["cleanup_errors"],
            ending_ref=ended.events[-1].evidence[0].model_dump(mode="json"),
        )
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "group-installed-initial-proof.json"
        ).write_text(json.dumps(proof, indent=2) + "\n")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
