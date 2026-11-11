"""Small real files for native copy/inventory; no real DB or uploaded image."""

from pathlib import Path
from lab_generate_skill.sites.reddit.service_contract import RedditServiceSpec
from reddit_native_program_fixture import prepare

PAYLOADS = {
    "postgres/PG_VERSION": b"14\n",
    "postgres/base/engineering-row": b"explicit fake pg data, not a database",
    "var/cache/engineering-cache": b"original cache",
    "session/engineering-session": b"original session",
    "uploads/engineering-upload": b"original temporary upload",
    "media-native/submission_images/engineering-file.jpg": b"explicit fake media bytes",
    "tmp/engineering-temp": b"original temp",
    "var-tmp/engineering-temp": b"original var temp",
}


def prepare_tree(root: Path) -> RedditServiceSpec:
    selected = prepare(root)
    for name, content in PAYLOADS.items():
        path = root / "state" / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(content)
        path.chmod(0o600)
    return selected


def contents(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
