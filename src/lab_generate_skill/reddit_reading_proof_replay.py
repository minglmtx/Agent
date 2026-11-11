"""Reuse closed native controls without claiming they ran newer code.

Only the three measured reading producers below share the unchanged v2 normal
lifecycle. Their immutable observations are evaluated by the current reader;
every positive and negative judgment must remain identical. The archived proof
and executed dependency identities are preserved, never rewritten as current.
This is an offline admission adapter, not a retry or an actor strategy.
"""
import hashlib
from pathlib import Path

from .source_revision_binding import binding, fingerprint

VERSION = 'reddit-reading-retained-control-replay-v1'
LEGACY_RUNTIME = '71fcc703bbf47a5912b7f4e0de6082e4eb4e90bf06fb94c09dcb86e35cfd6824'
PROTECTION = '31a91e9454856e09a00fb63f99f695b80d6bab3bd7bc9d8344637c502abc51fd'
# Packet -> original reader, maximum reader, issued-text helper (if present).
EXECUTED_PACKETS = {
    'b08b0e64f808bf389aaacd96e958bbd8a7a7a2d96cbd8b3ff50851714c316358': (
        '1c05e3c7588e376dbb6a93a1fee02c5b1a312483e0a4cd70b651cfab77675627',
        'e1ec9316397d4692869624eda0339db6db8eaee9237aac367db2d55ce0341b62', None),
    '158c3d9076af98c12caafc36783ac055412c4960e168716aa840979058dae3ba': (
        'fa07d7ee815241fd2b4540d38f87f06f8a0e3af76a352a8ef376cdb8fc9cdc04',
        'e3ca19b1e1858110060e4e98522ebcc4f1fed0f3014f9b33a7037cd57c5a82e4',
        '73159d215d099eef39e8ebf00fb0cabf4530042dc060cc64a29e2e2e704d392e'),
    'c2da68d93d041ec28dfe1432b69daa3ff46b770c8de79a0432b5d6fca46f0dac': (
        'fa07d7ee815241fd2b4540d38f87f06f8a0e3af76a352a8ef376cdb8fc9cdc04',
        'e3ca19b1e1858110060e4e98522ebcc4f1fed0f3014f9b33a7037cd57c5a82e4',
        '74459955f87a614b878dee43c5ffb1f3ba9de1075d0014c28afc884f167f314d'),
}


def replay_provenance():
    from . import reddit_final_read_runtime as runtime
    return dict(runtime.provenance(), replay_adapter_sha256=
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def executed_dependencies(packet_sha256):
    readers = EXECUTED_PACKETS.get(packet_sha256)
    if readers is None:
        raise ValueError('Unrecognized closed native reading producer')
    return {'runtime_sha256': LEGACY_RUNTIME,
            'original_reading_sha256': readers[0],
            'maximum_reading_sha256': readers[1],
            'complete13_protection_sha256': PROTECTION,
            'issued_record_sha256': readers[2]}


def require_replayed(contract, proof):
    from . import reddit_final_read_runtime as runtime
    if (proof.get('version') != VERSION
            or proof.get('fingerprint') != fingerprint(contract)
            or proof.get('source_binding') != binding(contract)
            or proof.get('current_replay_provenance') != replay_provenance()
            or proof.get('new_native_execution_claimed') is not False
            or proof.get('actor_attempts') != 0 or proof.get('api_calls') != 0):
        raise ValueError('Current explicit retained-control replay required')
    archived = proof.get('archived_proof')
    if not isinstance(archived, dict) or fingerprint(archived) != proof.get('archived_proof_sha256'):
        raise ValueError('Immutable archived native proof required')
    dependencies = executed_dependencies(proof.get('executed_packet_sha256'))
    if proof.get('executed_dependencies') != dependencies:
        raise ValueError('Actual historical issued-text dependency required')
    expected = {k: v for k, v in dependencies.items() if k != 'issued_record_sha256'}
    expected['lifecycle_methods'] = runtime.METHODS
    cycles = archived.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 2:
        raise ValueError('Two archived native cycles required')
    for cycle in cycles:
        origin = cycle.get('actual_raw_origin', {})
        if (origin.get('packet_sha256') != proof.get('executed_packet_sha256')
                or not runtime.SHA.fullmatch(str(origin.get('archive_sha256', '')))
                or not runtime.SHA.fullmatch(str(origin.get('receipt_sha256', '')))
                or not runtime.SHA.fullmatch(str(origin.get('manifest_sha256', '')))
                or not runtime.SHA.fullmatch(str(origin.get('actual_batch_script_sha256', '')))
                or not runtime.SHA.fullmatch(str(cycle.get('actual_source_record_sha256', '')))
                or type(origin.get('verified_raw_members')) is not int
                or origin['verified_raw_members'] <= 0):
            raise ValueError('Complete verified actual raw origin required')
    # This repeats all existing boundary, restoration, source, normal-session,
    # rule-only reuse and exact judgment checks. evaluate() is the current code;
    # a changed classification requires new investigation, not silent regrading.
    return runtime._validate_admission(contract, archived, expected)


def wrap(contract, archived, packet_sha256):
    from copy import deepcopy
    proof = {'version': VERSION, 'fingerprint': fingerprint(contract),
             'source_binding': binding(contract),
             'current_replay_provenance': replay_provenance(),
             'executed_packet_sha256': packet_sha256,
             'executed_dependencies': executed_dependencies(packet_sha256),
             'archived_proof': deepcopy(archived),
             'archived_proof_sha256': fingerprint(archived),
             'new_native_execution_claimed': False, 'actor_attempts': 0, 'api_calls': 0}
    require_replayed(contract, proof)
    return proof
