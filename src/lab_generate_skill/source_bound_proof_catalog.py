"""Private, lifetime-bound full proofs with immutable archive references on disk.

The catalogue changes storage only. A descriptor cannot establish admission:
it resolves only in the process that constructed the full original proof, and
the caller still runs its unchanged source/native guards on that full object.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

VERSION = 'source-bound-original-proof-reference-v1'


def _digest(value):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False)
    for part in encoder.iterencode(value):
        digest.update(part.encode())
    return digest.hexdigest()


class ProofCatalog:
    def __init__(self, source_ids):
        self.sources = frozenset(source_ids)
        if not self.sources or len(self.sources) != len(source_ids):
            raise ValueError('Distinct declared proof source IDs required')
        self._proofs = {}
        self._cached = None

    def register(self, source, proof, references, *, loader=None):
        if source not in self.sources or source in self._proofs:
            raise ValueError('One full proof per declared original source required')
        if not isinstance(proof, dict) or not isinstance(references, list) or len(references) != 2:
            raise ValueError('Complete original proof and two cold source references required')
        for ref in references:
            if (ref.get('source_task_id') != source or ref.get('member') != 'gitlab/' + source + '/cycle.json'
                    or not Path(ref.get('live_path', '')).is_absolute()
                    or not isinstance(ref.get('archive'), dict)
                    or not isinstance(ref.get('cycle_pin'), dict)):
                raise ValueError('Exact original source archive/cycle references required')
        descriptor = {'storage_format': VERSION, 'source_task_id': source,
                      'full_proof_sha256': _digest(proof),
                      'original_cold_source_cycles': deepcopy(references),
                      'descriptor_is_not_admission': True}
        if loader is not None and not callable(loader):
            raise ValueError('Explicit original full proof loader required')
        # Large original proofs need not all stay resident during model work.
        # A checked loader reconstructs one from still-open original suppliers.
        self._proofs[source] = (deepcopy(descriptor), proof if loader is None else loader, loader is not None)
        return descriptor

    def resolve(self, source, descriptor):
        if source not in self._proofs:
            raise ValueError('Actual lifetime-bound original proof is unavailable')
        expected, original, lazy = self._proofs[source]
        if descriptor != expected:
            raise ValueError('Original proof source/reference binding changed')
        if lazy:
            if self._cached is None or self._cached[0] != source:
                self._cached = (source, original())
            proof = self._cached[1]
        else:
            proof = original
        if _digest(proof) != expected['full_proof_sha256']:
            raise ValueError('Actual original proof changed after binding')
        return proof

    def close(self):
        self._proofs.clear()
        self._cached = None


def asset_manifest_from_verified_index(runtime_index, destination):
    """Use a checked frozen index; never derive the declaration from live files."""
    rows = json.loads(Path(runtime_index).read_text())['files']
    manifest = {name: row['sha256'] for name, row in rows.items()}
    if not manifest:
        raise ValueError('Complete explicit frozen runtime index required')
    path = Path(destination)
    if not path.is_absolute():
        raise ValueError('Absolute frozen asset manifest destination required')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as stream:
        path.chmod(0o600)
        json.dump(manifest, stream, sort_keys=True)
        stream.write('\n')
    return path
