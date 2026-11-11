"""Declare the existing private source with deliberately no Actor effects."""

from pathlib import Path
from lab_generate_skill.actor.instructions import ACTIONS
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from evidence_control_fixtures import EvidenceFixtureStore
from reddit_site_native_plan import private_site_plan
from site_worker_fixtures import configuration
from source_task_hooks import SourceTaskHooks
from reddit_source_selection import RedditSourceSelection


def source_hooks(
    root: Path,
    installation: ReleaseInstallation,
    job_id: str,
    *,
    selection: RedditSourceSelection | None = None,
) -> SourceTaskHooks:
    owner = configuration(installation, job_id=job_id).token.owner
    sessions = root / "private-sessions"
    sessions.mkdir(mode=0o700)
    (root / "source-evidence").mkdir(mode=0o700)
    return SourceTaskHooks(
        owner=owner,
        evidence=EvidenceFixtureStore(root / "source-evidence"),
        allowed_actions=tuple(ACTIONS),
        reddit_selection=selection,
        execute=lambda source, browser, session, result: None,
        evaluate=lambda source, facts: None,
        private_site_plan=private_site_plan(
            owner,
            installation,
            evidence_root=root / "source-evidence",
            session_root=sessions,
            journal_root=root / "journal",
        ),
    )
