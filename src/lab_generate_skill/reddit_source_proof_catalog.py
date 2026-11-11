"""Storage references for independently verified Reddit source cold pairs.

An old four-source proof and a repaired two-source proof remain different
suppliers. Nothing here manufactures a successful six-source worker. The
original family admission gate and hook constructor must still consume the
full proof, while its original path suppliers are alive.
"""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import hashlib
import re

from .source_bound_proof_catalog import _digest

VERSION = 'reddit-sourcewise-original-proof-reference-v1'


def canonical(contract):
    return {key: deepcopy(value) for key, value in contract.items()
            if key != 'admission_result'}


def _pin(value, *, path=False):
    if (not isinstance(value, dict) or type(value.get('bytes')) is not int
            or value['bytes'] < 0
            or not re.fullmatch('[0-9a-f]{64}', value.get('sha256', ''))
            or (path and not Path(value.get('path', '')).is_absolute())):
        raise ValueError('Exact original archive/member byte pin required')


def _actual_pin(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Restored original regular source cycle required')
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(part)
    return {'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}


class RedditProofCatalog:
    def __init__(self, contracts):
        self.contracts = {}
        for contract in contracts:
            c = canonical(contract)
            source = c.get('source_task_id')
            if (not isinstance(source, str) or not re.fullmatch('[A-Za-z0-9_-]+', source)
                    or source in self.contracts or c.get('domain') != 'reddit'
                    or c.get('heldout_quarantine') is not False):
                raise ValueError('Distinct exact nonheldout Reddit sources required')
            self.contracts[source] = c
        if not self.contracts:
            raise ValueError('A nonempty original source scope is required')
        self._proofs = {}
        self._cached = None

    def register(self, contract, full_proof, references, *, loader):
        c = canonical(contract)
        source = c.get('source_task_id')
        if (source not in self.contracts or self.contracts[source] != c
                or source in self._proofs or not callable(loader)
                or not isinstance(full_proof, dict)):
            raise ValueError('One checked full proof for the exact original source required')
        if not isinstance(references, list) or len(references) != 2:
            raise ValueError('Two original source cold archive references required')
        for cold, ref in enumerate(references):
            if not isinstance(ref, dict):
                raise ValueError('Exact original source reference object required')
            member = PurePosixPath(ref.get('member', ''))
            if (ref.get('source_task_id') != source or ref.get('cold') != cold
                    or member.is_absolute() or '..' in member.parts
                    or member.parts.count(source) != 1
                    or member.name != 'cycle.json'
                    or not Path(ref.get('live_path', '')).is_absolute()):
                raise ValueError('Exact Reddit source/member/cold binding required')
            _pin(ref.get('archive'), path=True)
            _pin(ref.get('member_manifest'), path=True)
            _pin(ref.get('cycle_pin'))
            if _actual_pin(ref['live_path']) != ref['cycle_pin']:
                raise ValueError('Restored source cycle differs from its original archive member')
        if (references[0]['archive']['path'] == references[1]['archive']['path']
                or references[0]['live_path'] == references[1]['live_path']):
            raise ValueError('The same source archive cannot masquerade as two cold starts')
        descriptor = {'storage_format': VERSION, 'source_task_id': source,
                      'contract_sha256': _digest(c),
                      'full_proof_sha256': _digest(full_proof),
                      'original_cold_source_cycles': deepcopy(references),
                      'descriptor_is_not_admission': True}
        self._proofs[source] = (deepcopy(descriptor), loader)
        return descriptor

    def require_complete(self):
        if set(self._proofs) != set(self.contracts):
            raise ValueError('One sourcewise supplier is still pending')

    def resolve(self, contract, descriptor):
        source = contract.get('source_task_id')
        if (source not in self._proofs or canonical(contract) != self.contracts[source]):
            raise ValueError('Lifetime-bound exact original Reddit proof is unavailable')
        expected, loader = self._proofs[source]
        if descriptor != expected:
            raise ValueError('Original sourcewise descriptor binding changed')
        if self._cached is None or self._cached[0] != source:
            self._cached = (source, loader())
        full = self._cached[1]
        if _digest(full) != expected['full_proof_sha256']:
            raise ValueError('Actual full original proof changed after source binding')
        return full

    def close(self):
        self._proofs.clear()
        self._cached = None

