"""Terminal repository download validation, independent of the actor's answer.

Not admitted until two native browser/control/reset cycles have passed. Private
Git references never enter actor observations or evaluator feedback.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

from .repository_downloads import zip_manifest, compare_zip
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'gitlab-download-v1'
ADMISSION_VERSION = 'gitlab-download-admission-v1'


def validate(c):
    s = c.get('repository_download')
    if c.get('domain') != 'gitlab' or not isinstance(s, dict):
        raise ValueError('Native GitLab download contract required')
    if set(s) != {'kind', 'project_id', 'project', 'head', 'ref', 'path'}:
        raise ValueError('Incomplete download identity')
    if s['kind'] not in ('zip', 'raw') or type(s['project_id']) is not int or s['project_id'] <= 0:
        raise ValueError('Invalid download kind or project identity')
    if not re.fullmatch(r'[0-9a-f]{40}', s['head']):
        raise ValueError('Pinned revision required')
    for key in ('project', 'ref'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', s[key]) or '..' in s[key]:
            raise ValueError('Invalid repository path or ref')
    path = s['path']
    if not isinstance(path, str) or (path and (path.startswith('/') or '\\' in path or any(x in ('', '.', '..') for x in path.split('/')))):
        raise ValueError('Invalid download path')
    if s['kind'] == 'raw' and not path:
        raise ValueError('Raw download requires a file')


def reference(site, c):
    validate(c); s = c['repository_download']; ident = s['project_id']
    if select_rows(site, f"SELECT path FROM routes WHERE source_type='Project' AND source_id={ident}") != [{'path': s['project']}]:
        raise ValueError('Repository identity changed')
    digest = hashlib.sha256(str(ident).encode()).hexdigest()
    gitdir = '/var/opt/gitlab/git-data/repositories/@hashed/' + digest[:2] + '/' + digest[2:4] + '/' + digest + '.git'
    def git(*args):
        result = site.command(['/opt/gitlab/embedded/bin/git', '--git-dir=' + gitdir, *args], capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Private download reference unavailable')
        return result.stdout
    if git('rev-parse', 'refs/heads/' + s['ref']).decode().strip() != s['head']:
        raise ValueError('Pinned repository revision changed')
    obj = s['head'] + (':' + s['path'] if s['path'] else '')
    if s['kind'] == 'zip':
        # Native GitLab path-scoped archives retain the selected directory.
        args = ['archive', '--format=zip', '--prefix=reference/', s['head']]
        if s['path']:
            if git('cat-file', '-t', obj).decode().strip() != 'tree':
                raise ValueError('Directory archive requires a Git tree')
            args.extend(['--', s['path']])
        values = zip_manifest(git(*args))
    else:
        if git('cat-file', '-t', obj).decode().strip() != 'blob':
            raise ValueError('Requested file is not a Git blob')
        payload = git('show', obj)
        values = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    return {'identity': dict(s), 'values': values}


def load_artifacts(directory):
    """Read only recorder-owned paths and verify their saved bookkeeping."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('Browser download recorder was not installed')
    manifest = directory / 'downloads.json'
    if not manifest.exists():
        return []
    records = json.loads(manifest.read_text())['downloads']
    if not isinstance(records, list):
        raise ValueError('Malformed download records')
    seen = set(); artifacts = []
    for record in records:
        ident = record.get('download_id')
        if type(ident) is not int or ident <= 0 or ident in seen:
            raise ValueError('Invalid download record identity')
        seen.add(ident)
        if record.get('status') == 'failed':
            continue
        if record.get('status') != 'completed':
            raise ValueError('Download capture was interrupted')
        artifact = directory / ('artifact-%04d.bin' % ident)
        if artifact.is_symlink() or artifact.stat().st_size != record.get('bytes'):
            raise ValueError('Recorded download artifact changed')
        # The archive reader also bounds uncompressed bytes separately.
        if artifact.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('Download exceeds inspection budget')
        payload = artifact.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.get('sha256'):
            raise ValueError('Recorded download digest changed')
        artifacts.append((record, payload))
    return artifacts


def evaluate(c, page, initial, final, directory, *, site_origin, runtime_error=None):
    validate(c)
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Environment or inference error')
    if (not isinstance(initial, dict) or initial.get('identity') != c['repository_download'] or
            not initial.get('values') or not isinstance(final, dict) or not final.get('values') or final.get('identity') != initial['identity']):
        return unknown('Missing repository reference')
    if (not isinstance(page, dict) or type(page.get('http_status')) is not int or not 200 <= page['http_status'] < 500 or
            not isinstance(page.get('url'), str) or any(type(page.get(k)) is not bool for k in ('login_page', 'error_page'))):
        return unknown('Missing terminal page or transport/server error')
    try:
        artifacts = load_artifacts(directory)
    except (ValueError, KeyError, TypeError, OSError):
        return unknown('Downloaded artifacts could not be audited')
    matched = False; spec = c['repository_download']
    for record, payload in artifacts:
        if spec['kind'] == 'zip':
            if not str(record.get('filename', '')).lower().endswith('.zip'):
                continue
            try:
                matched |= compare_zip(payload, initial['values'])['matches']
            except (ValueError, zipfile.BadZipFile, RuntimeError):
                # A completed but invalid/wrong ZIP is an unsuccessful download.
                # Missing recorder artifacts above are an infrastructure error.
                continue
        else:
            matched |= (record.get('filename') == spec['path'].rsplit('/', 1)[-1] and
                        all(record.get(k) == v for k, v in initial['values'].items()))
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin),
              'repository_unchanged': initial == final, 'requested_artifact_received': matched}
    ok = all(checks.values())
    return {'version': VERSION, 'status': 'success' if ok else 'failure',
            'reward': float(ok), 'checks': checks, 'reason': None}


def feedback(j):
    meanings = {'page_valid': 'The final document is a valid local website page.',
                'repository_unchanged': 'The source repository remains unchanged.',
                'requested_artifact_received': 'The requested file or complete archive was received with the correct contents.'}
    return {'status': j['status'], 'reward': j['reward'], 'reason': j.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': meanings[k]} for k, v in j['checks'].items()],
            'action_sequence_provided': False, 'reference_values_provided': False}


def fingerprint(c):
    return reference_fingerprint({k: c.get(k) for k in ('task_id', 'source_task_id', 'domain', 'goal',
        'start_path', 'repository_download', 'heldout_quarantine', 'start_revision', 'goal_revision')})


def expected_controls():
    return {'no_op': 'failure', 'navigation_only': 'failure', 'positive': 'success',
            'saved_then_home': 'success', 'wrong_artifact': 'failure', '404': 'failure', 'login': 'failure'}


def require_admission(c, proof):
    validate(c)
    if c.get('heldout_quarantine') or proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != fingerprint(c):
        raise ValueError('Quarantined or stale download proof')
    cycles = proof.get('cycles', [])
    if not proof.get('passed') or len(cycles) != 2:
        raise ValueError('Two independent native download controls required')
    for row in cycles:
        if (not row.get('passed') or not row.get('initial_valid') or row.get('checks') != expected_controls() or
                row.get('reset_downloads') != [] or not row.get('reference') or not row.get('native_download_verified')):
            raise ValueError('Download controls incomplete')
        if row['reference'].get('identity') != c['repository_download'] or not row['reference'].get('values'):
            raise ValueError('Download reference identity differs')
        if not row.get('initial_fingerprint') or row['initial_fingerprint'] != row.get('final_fingerprint'):
            raise ValueError('Repository website reset failed')
    if cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint'] or cycles[0]['reference'] != cycles[1]['reference']:
        raise ValueError('Download reference or reset state changed')
