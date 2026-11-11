"""Read a pinned shared-JSON proof without retaining another expanded copy.

The entire archive is verified against its manifest. Only the requested JSON
and its content store are temporarily materialized; the regular JSON resolver
still checks every chunk and the logical digest. This grants no admission.
"""
import json
from pathlib import Path
import tempfile
from .gitlab_grouped_evidence_archive import digest, _bytes, SHA
from .evidence_store import VERSION as SHARED_VERSION, STORE, resolve

VERSION = 'archived-shared-json-proof-v1'


def load(reference):
    if not isinstance(reference, dict) or reference.get('storage_format') != VERSION:
        return reference
    keys = {'storage_format', 'archive', 'archive_sha256', 'member_manifest',
            'member_manifest_sha256', 'member', 'store_member'}
    if set(reference) != keys:
        raise ValueError('Complete pinned archive proof reference required')
    for path, pin in [('archive', 'archive_sha256'), ('member_manifest', 'member_manifest_sha256')]:
        if not isinstance(reference[pin], str) or not SHA.fullmatch(reference[pin]) or digest(reference[path]) != reference[pin]:
            raise ValueError('Archived proof or manifest changed')
    names = (reference['member'], reference['store_member'])
    for name in names:
        if not isinstance(name, str) or not name or Path(name).is_absolute() or '..' in Path(name).parts or str(Path(name)) != name:
            raise ValueError('Exact safe proof member required')
    if names[0] == names[1] or Path(names[1]).name != STORE:
        raise ValueError('Distinct JSON and content-store members required')
    data = _bytes(reference['archive'], reference['archive_sha256'],
                  reference['member_manifest'], reference['member_manifest_sha256'], names)
    document = json.loads(data[names[0]])
    if not isinstance(document, dict) or document.get('storage_format') != SHARED_VERSION:
        raise ValueError('Expected chunk-verified shared JSON proof')
    with tempfile.TemporaryDirectory(prefix='verified-proof-') as temp:
        root = Path(temp)
        path = root / names[0]
        store = root / names[1]
        if (path.parent / document['store']).resolve() != store:
            raise ValueError('Proof content store differs from pinned member')
        for name, body in data.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        return resolve(path, document)
