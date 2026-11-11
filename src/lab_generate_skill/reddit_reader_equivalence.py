"""Narrow migration of unchanged native-read proofs across equivalent readers.

The old full-hook proof is retained, including every cold control and snapshot.
Only exact reviewed old/new code closures can use the real full13 equality
certificate. This never admits a source or changes an evaluator result.
"""
import hashlib
import json
from pathlib import Path

VERSION='reddit-exact-reader-equivalence-v1'


def validate_certificate(value, recorded, current, installed_files, php_sha256):
    if not isinstance(value,dict) or value.get('version')!=VERSION:
        return False
    if recorded!=value.get('old_provenance') or current!=value.get('new_provenance'):
        return False
    if installed_files!=value.get('installed_files_sha256'):
        return False
    if (recorded.get('lifecycle_methods')!=current.get('lifecycle_methods')
        or recorded.get('inherited_identical_methods')is not True
        or current.get('inherited_identical_methods')is not True
        or any(recorded.get(k)!=current.get(k)for k in ('author_source_sha256','formatting_source_sha256'))):
        return False
    actual=value.get('actual_native_equivalence',{})
    if (actual.get('job_id')!='4498671' or actual.get('full_raw_members')!=26
        or actual.get('php_sha256')!=php_sha256 or actual.get('normal_admissions')!=0
        or actual.get('actor_attempts')!=0 or actual.get('api_calls')!=0
        or actual.get('schema_before')!=actual.get('schema_after')):
        return False
    from .reddit_native_read_runtime import validate_complete_snapshot
    try:
        snapshots=[validate_complete_snapshot(actual[k])for k in ('legacy_before','candidate','legacy_after')]
        return snapshots[0]==snapshots[1]==snapshots[2]
    except (KeyError,ValueError,TypeError):
        return False


def matches_historical_reader_provenance(recorded,current):
    root=Path(__file__).resolve().parents[2]
    path=root/'configs/reddit-reader-equivalence-v1.json'
    try:
        value=json.loads(path.read_text())
        expected={
            'src/lab_generate_skill/reddit_native_read_runtime.py',
            'src/lab_generate_skill/reddit_native_read_protection.py',
            'src/lab_generate_skill/reddit_submission_snapshot_stream.py',
            'src/lab_generate_skill/reddit_reader_equivalence.py',
            'src/lab_generate_skill/reddit_post_author_navigation.py',
            'src/lab_generate_skill/reddit_native_formatting_navigation.py'}
        if set(value.get('installed_files_sha256',{}))!=expected:return False
        installed={n:hashlib.sha256((root/n).read_bytes()).hexdigest()for n in expected}
        from .reddit_submission_snapshot_stream import PHP
        return validate_certificate(value,recorded,current,installed,hashlib.sha256(PHP.encode()).hexdigest())
    except (OSError,ValueError,TypeError):
        return False
