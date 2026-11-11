"""Original image compiler before real database, no schema execution or seed copy."""

from pathlib import Path
from lab_generate_skill.sites.gitlab.group_sql_capture import GROUP_CAPTURE
from gitlab_programs_live import native, RUBY
from site_instance_fixtures import node_path as node_path


def test_original_group_capture_compiles_with_original_ruby(node_path: Path) -> None:
    for name in ("state", "snapshot", "control"):
        (node_path / name).mkdir()
    assert native(node_path, (RUBY, "-c", "-e", GROUP_CAPTURE)) == b"Syntax OK\n"
    assert not list((node_path / "state").iterdir())
