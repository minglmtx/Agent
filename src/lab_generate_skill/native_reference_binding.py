"""Relocate a verified private reference without changing its task or predicate."""
from copy import deepcopy
import json
from pathlib import Path

from . import gitlab_native_content as content
from .io_utils import atomic_write_json


def bind_document_reference(contract, reference, destination):
    """Call after the original source gate; never recover data from a stale path.

    The original contract already pins the reference content. Only its private
    storage location changes; goal, start, source identity and predicate remain
    byte-equivalent as data. An existing different file is never overwritten.
    """
    spec = content.validate(contract)
    content.validate_reference(reference)
    if (content.canonical_digest(reference) != spec['reference_sha256']
            or reference['kind'] != spec['kind']):
        raise ValueError('Private reference does not match the admitted content')
    destination = Path(destination)
    if not destination.is_absolute() or destination.is_symlink():
        raise ValueError('Absolute regular private reference destination required')
    if destination.exists():
        if not destination.is_file() or json.loads(destination.read_text()) != reference:
            raise ValueError('Existing private reference differs; no overwrite permitted')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(destination, reference)
        destination.chmod(0o600)
    result = deepcopy(contract)
    result['native_content_reference_file'] = str(destination)
    if content.load_reference(result) != reference:
        raise ValueError('Relocated reference did not survive the actual reader')
    return result
