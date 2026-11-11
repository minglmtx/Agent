"""One preparation effect before services, snapshot and Actor; retain partial failures."""

import os
from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import RedditServiceSpec
from .service_commands import container
from .service_files import checked
from .native_schema import NativeMedia
from .media_initialization_contract import MediaInitialization
from .media_initialization_program import INITIALIZE_MEDIA


def initialize_media(
    spec: RedditServiceSpec, commands: NativeCommands, control: OperationControl
) -> MediaInitialization:
    spec = RedditServiceSpec.model_validate(spec)
    root = Path(spec.files.state_root) / "media-native"
    checked(root, control)
    original = root.lstat()
    if (
        not stat.S_ISDIR(original.st_mode)
        or stat.S_IMODE(original.st_mode) != 0o700
        or original.st_uid != os.getuid()
        or any(root.iterdir())
    ):
        raise ValueError(
            "Fresh owned private media root required before native initialization"
        )
    before = NativeMedia(
        version="reddit-native-media-storage-candidate-v2", directories=(), files={}
    )
    # The owning RedditInstance has already entered preparing. Cancellation,
    # command failure, malformed reply or a partial directory quarantines it.
    raw = commands.run(
        container(spec, seeded=False) + ("/usr/local/bin/php", "-r", INITIALIZE_MEDIA),
        control,
    )
    control.checkpoint()
    checked(root, control)
    current = root.lstat()
    if (current.st_dev, current.st_ino, current.st_mode, current.st_uid) != (
        original.st_dev,
        original.st_ino,
        original.st_mode,
        original.st_uid,
    ) or tuple(p.name for p in root.iterdir()) != ("submission_images",):
        raise ValueError(
            "Native preparation replaced media root or changed unrelated entries"
        )
    target = root / "submission_images"
    checked(target, control)
    info = target.lstat()
    if (
        raw != b"native-storage-initialized/1"
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o755
        or any(target.iterdir())
    ):
        raise ValueError("Incomplete original native empty storage initialization")
    return MediaInitialization(
        service=spec,
        constructor_sha256="2e531b5f3b20a31d7b933b175d8a3519992ae13fc9dd937761fbaefb6cfe2bc6",
        adapter_sha256="462d0ed21f5e4d0f7c76cd402375655741af638d8bd760e7307a0481726dd991",
        configuration_sha256="f07d088abc00610fa5954659c7852ae215fb20d26b8cec98f19dabbfae02af08",
        before=before,
        after=NativeMedia(
            version=before.version, directories=("submission_images",), files={}
        ),
    )
