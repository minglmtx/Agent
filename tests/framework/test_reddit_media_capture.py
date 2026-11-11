"""Original photo decoding, complete native files and unsafe/cancel exits."""

import os
from pathlib import Path
import shutil
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.reddit.media_capture import NativeMediaCapture
from lab_generate_skill.bootstrap.reddit_browser_files import PHOTO_ROOT
from lab_generate_skill.sites.reddit.tasks.image_parameters import PHOTOS
from reddit_services_fixtures import spec
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def root(node: Path) -> Path:
    value = node / "state/media-native"
    value.mkdir(parents=True, mode=0o700)
    return value


@pytest.mark.parametrize("index", [0, 1])
def test_actual_original_declared_photo_bytes_decode_without_transformation(
    node_path: Path, index: int
) -> None:
    directory = root(node_path)
    (directory / "submission_images").mkdir(mode=0o700)
    photo = PHOTOS[index]
    path = directory / "submission_images" / (photo.sha256 + ".jpg")
    shutil.copyfile(Path(PHOTO_ROOT) / photo.relative_file, path)
    (directory / "opaque").write_bytes(b"")
    observed = NativeMediaCapture(spec(node_path)).capture(guard(5))
    value = observed.files["submission_images/" + photo.sha256 + ".jpg"]
    assert (value.sha256, value.bytes, value.format, value.dimensions) == (
        photo.sha256,
        photo.bytes,
        "JPEG",
        photo.dimensions,
    )
    assert (
        observed.directories == ("submission_images",)
        and observed.files["opaque"].bytes == 0
    )


@pytest.mark.parametrize(
    "kind", ["symlink", "hardlink", "fifo", "bad-jpeg", "root-alias"]
)
def test_unsafe_or_invalid_media_cannot_become_empty_native_state(
    node_path: Path, kind: str
) -> None:
    directory = root(node_path)
    if kind == "symlink":
        (directory / "unsafe").symlink_to(node_path / "outside")
    elif kind == "hardlink":
        (directory / "one").write_bytes(b"original")
        os.link(directory / "one", directory / "two")
    elif kind == "fifo":
        os.mkfifo(directory / "fifo", 0o600)
    elif kind == "bad-jpeg":
        (directory / "corrupt.jpg").write_bytes(b"not jpeg")
    else:
        directory.rename(directory.with_name("actual"))
        directory.symlink_to(directory.with_name("actual"), target_is_directory=True)
    with pytest.raises((EvidenceIntegrityError, OSError)):
        NativeMediaCapture(spec(node_path)).capture(guard(5))


def test_empty_native_media_and_cancellation_are_distinct(node_path: Path) -> None:
    root(node_path)
    capture = NativeMediaCapture(spec(node_path))
    value = capture.capture(guard(5))
    assert value.files == {} and value.directories == ()
    (node_path / "state/media-native/one").write_bytes(b"one")

    class Cancelled:
        def checkpoint(self) -> float:
            raise TimeoutError("cancelled")

        def wait(self, seconds: float) -> None:
            raise TimeoutError("cancelled")

    with pytest.raises(TimeoutError):
        capture.capture(Cancelled())
