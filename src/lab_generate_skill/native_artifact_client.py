"""Generic public artifact client candidate, with independent persisted checks.

No task ID, expected object, evaluator answer, native DB or success predicate
enters the public action dispatcher. A source-specific full native gate is
still required before an ordinary session may use these actions.
"""
import ast
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import uuid

from lab_generate_skill.local_artifact_actions import (
    LocalArtifactActions as DraftActions, TOOL_SCHEMAS, clone_native_url)
from lab_generate_skill.gitlab_local_artifacts_v2 import (
    MAX_FEED_BYTES, fetched_feed, local_native_url, parse_feed, redacted_url)

VERSION = 'native-artifact-client-full-content-candidate-v3'
OID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
SID = re.compile(r'[0-9a-f]{32}')


def run_git(args, *, timeout=180, auth=None, origin=None):
    """Scoped native credentials stay in child environment, never argv/logs."""
    env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
        'GIT_TERMINAL_PROMPT':'0','GIT_LFS_SKIP_SMUDGE':'1','GIT_TRACE':'0','GIT_TRACE_CURL':'0'}
    if auth is not None:
        if not isinstance(auth,dict)or not all(isinstance(auth.get(k),str)and auth[k]for k in('username','password')):
            raise ValueError('Qualified current native account credentials required')
        token=base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
        env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='http.'+origin.rstrip('/')+'/.extraHeader',
                   GIT_CONFIG_VALUE_0='Authorization: Basic '+token)
    else:env['GIT_CONFIG_COUNT']='0'
    prefix=['git','-c','credential.helper=','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
        '-c','protocol.allow=never','-c','protocol.http.allow=always','-c','protocol.https.allow=always',
        '-c','http.followRedirects=false']
    proc=subprocess.Popen(prefix+list(args),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        try:out,_=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.communicate(timeout=5);raise TimeoutError('Native repository operation exceeded deadline')from None
        if proc.returncode:raise RuntimeError('Native repository operation failed (exit '+str(proc.returncode)+')')
        return out.decode('utf-8',errors='strict').strip()
    finally:
        if proc.poll()is None:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=5)
        proc.stdout.close();proc.stderr.close()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.pending')
    with temporary.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.chmod(temporary, 0o600); os.replace(temporary, path)


def regular(root, relative):
    root = Path(root)
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError('Artifact root and ancestors must not be symlink aliases')
    root = root.resolve()
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Artifact member must remain inside the attempt workspace')
    path = root / value
    if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root)
            or any(p.is_symlink() for p in path.parents if p.is_relative_to(root))):
        raise ValueError('Original regular local artifact member required')
    return path


def repository_inventory(destination):
    """Read all cloned heads/tags and reachable objects; shallow clones fail."""
    destination = Path(destination).resolve()
    if not (destination / '.git').is_dir() or (destination / '.git').is_symlink():
        raise ValueError('Actual local checked-out Git repository required')
    def git(*args):
        return run_git(['-C', str(destination), *args], timeout=60)
    if (Path(git('rev-parse', '--show-toplevel')).resolve() != destination
            or git('rev-parse', '--is-bare-repository') != 'false'
            or git('rev-parse', '--is-shallow-repository') != 'false'):
        raise ValueError('An actual complete, non-shallow local worktree is required')
    if (destination / '.git/objects/info/alternates').exists():
        raise ValueError('Clone must own its complete objects, not borrow another workspace')
    lines = git('for-each-ref', '--format=%(refname) %(objectname)',
                'refs/remotes/origin', 'refs/tags').splitlines()
    refs = {}
    for line in lines:
        name, oid = line.split(' ', 1)
        if name == 'refs/remotes/origin/HEAD':
            continue
        if name.startswith('refs/remotes/origin/'):
            name = 'refs/heads/' + name[len('refs/remotes/origin/'):]
        if not (name.startswith(('refs/heads/', 'refs/tags/')) and OID.fullmatch(oid)):
            raise ValueError('Complete native branch/tag identities required')
        if name in refs:
            raise ValueError('Duplicate local native ref')
        refs[name] = oid
    if not refs:
        raise ValueError('Native branch/tag catalog cannot be replaced by HEAD alone')
    head = git('rev-parse', 'HEAD'); tree = git('rev-parse', 'HEAD^{tree}')
    if not OID.fullmatch(head) or not OID.fullmatch(tree):
        raise ValueError('Actual checked-out repository HEAD/tree required')
    # Include the current HEAD and every advertised branch/tag. Internal local
    # refs cannot manufacture equivalence to the actual native reference.
    objects = sorted({line.split(' ', 1)[0] for line in
        git('rev-list', '--objects', 'HEAD', *sorted(set(refs.values()))).splitlines()})
    if not objects or any(not OID.fullmatch(oid) for oid in objects):
        raise ValueError('Complete reachable native object catalog required')
    git('fsck', '--full', '--no-dangling')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Local checkout does not exactly match its committed files')
    return {'head': head, 'tree': tree, 'refs': refs, 'reachable_objects': objects,
            'origin': git('remote', 'get-url', 'origin'), 'non_shallow': True,
            'clean_checked_out_worktree': True}


def clone_completion(destination, *, expected_url, reference):
    """The private scorer supplies independently captured full native objects."""
    checks = dict.fromkeys(('actual_full_local_repository', 'native_origin',
                           'native_head', 'native_tree', 'all_native_heads_and_tags',
                           'complete_reachable_objects'), False)
    try:
        actual = repository_inventory(destination)
        required = {'head', 'tree', 'refs', 'reachable_objects'}
        if not isinstance(reference, dict) or not required <= set(reference):
            raise ValueError('Full independent native repository reference required')
        if (not OID.fullmatch(reference['head']) or not OID.fullmatch(reference['tree'])
                or not isinstance(reference['refs'], dict) or not reference['refs']
                or any(not isinstance(k, str) or not k.startswith(('refs/heads/', 'refs/tags/'))
                       or not OID.fullmatch(v) for k, v in reference['refs'].items())
                or not isinstance(reference['reachable_objects'], list)
                or not reference['reachable_objects']
                or reference['reachable_objects'] != sorted(set(reference['reachable_objects']))
                or any(not OID.fullmatch(v) for v in reference['reachable_objects'])
                or not {reference['head'], reference['tree'], *reference['refs'].values()}
                       <= set(reference['reachable_objects'])):
            raise ValueError('Complete independently captured native refs and objects required')
        checks.update(actual_full_local_repository=True,
            native_origin=actual['origin'] == expected_url,
            native_head=actual['head'] == reference['head'],
            native_tree=actual['tree'] == reference['tree'],
            all_native_heads_and_tags=actual['refs'] == reference['refs'],
            complete_reachable_objects=actual['reachable_objects'] == reference['reachable_objects'])
        return {'checks': checks, 'passed': all(checks.values()), 'actual': actual}
    except (ValueError, RuntimeError, TimeoutError, OSError, KeyError, TypeError):
        return {'checks': checks, 'passed': False}


class SubscriptionClient:
    """Actual append-only refresh receipts, checked against persisted bytes."""
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(mode=0o700, parents=True, exist_ok=False)

    def _fetch(self, folder, ident, url, origin, kind, fetch, previous):
        url = local_native_url(url, origin, calendar=kind == 'calendar')
        response = fetch(url)
        if getattr(response, 'url', None) != url:
            raise ValueError('Actual native response URL must match the subscribed resource')
        body, parsed = fetched_feed(response, kind)
        index = len(previous)
        body_name = 'refresh-' + str(index).zfill(4) + '.bin'
        body_path = folder / body_name
        with body_path.open('xb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
        os.chmod(body_path, 0o600)
        event = {'sequence': index, 'status': 200, 'url': redacted_url(url),
            'body_file': body_name, 'body_bytes': len(body),
            'body_sha256': hashlib.sha256(body).hexdigest(), 'parsed': parsed}
        record = {'version': VERSION, 'subscription_id': ident, 'active': True,
            'kind': kind, 'url': redacted_url(url), 'successful_refreshes': index + 1,
            'refreshes': previous + [event], 'explicit_local_client_adaptation': True}
        write(folder / 'state.json', record)
        return record

    def subscribe(self, url, origin, kind, fetch):
        if kind not in ('calendar', 'atom'):
            raise ValueError('Supported native feed format required')
        url = local_native_url(url, origin, calendar=kind == 'calendar')
        ident = uuid.uuid4().hex; folder = self.root / ident; folder.mkdir(mode=0o700)
        path = folder / 'fetch-url-private.txt'
        with path.open('x') as stream: stream.write(url)
        os.chmod(path, 0o600)
        return self._fetch(folder, ident, url, origin, kind, fetch, [])

    def refresh(self, ident, origin, fetch):
        if not SID.fullmatch(ident): raise ValueError('Actual subscription ID required')
        folder = self.root / ident
        record = json.loads(regular(folder, 'state.json').read_text())
        if record['active'] is not True or record['subscription_id'] != ident:
            raise ValueError('An active subscription from this attempt is required')
        url = regular(folder, 'fetch-url-private.txt').read_text()
        # Validate the previous actual receipt chain before adding a new fetch.
        if not self.completion(ident, expected_url=url, expected_kind=record['kind'], min_refreshes=1):
            raise ValueError('Original local subscription receipts are incomplete')
        return self._fetch(folder, ident, url, origin, record['kind'], fetch, record['refreshes'])

    def completion(self, ident, *, expected_url, expected_kind, min_refreshes=2, expected_parsed=None):
        if not isinstance(ident, str) or not SID.fullmatch(ident): return False
        if type(min_refreshes) is not int or min_refreshes < 1: raise ValueError('Finite positive refresh count required')
        try:
            folder = self.root / ident
            record = json.loads(regular(folder, 'state.json').read_text())
            if (record['version'] != VERSION or record['subscription_id'] != ident
                    or record['active'] is not True or record['kind'] != expected_kind
                    or record['url'] != redacted_url(expected_url)
                    or regular(folder, 'fetch-url-private.txt').read_text() != expected_url
                    or type(record['successful_refreshes']) is not int
                    or record['successful_refreshes'] < min_refreshes
                    or record['successful_refreshes'] != len(record['refreshes'])): return False
            for index, event in enumerate(record['refreshes']):
                body = regular(folder, event['body_file']).read_bytes()
                if (event['sequence'] != index or event['status'] != 200
                        or event['url'] != redacted_url(expected_url)
                        or event['body_file'] != 'refresh-' + str(index).zfill(4) + '.bin'
                        or event['body_bytes'] != len(body) or len(body) > MAX_FEED_BYTES
                        or event['body_sha256'] != hashlib.sha256(body).hexdigest()
                        or event['parsed'] != parse_feed(body, expected_kind)
                        or expected_parsed is not None and event['parsed'] != expected_parsed): return False
            return True
        except (ValueError, KeyError, TypeError, OSError): return False


class LocalArtifactActions(DraftActions):
    """Full public client, source/goal-independent and current-observation gated."""
    def __init__(self, root, origin, request, *, current_account_auth=None):
        super().__init__(root, origin, request)
        self.current_account_auth=current_account_auth
        # The parent constructs its private v2 client directory. It is empty
        # and is replaced before any operation or artifact is produced.
        self.client.root.rmdir(); self.client = SubscriptionClient(self.root / 'subscriptions')

    def clone_repository(self, url):
        url = clone_native_url(url, self.origin)
        if url not in self.observed_clones:
            raise ValueError('Clone URL is absent from the current public observation')
        ident = uuid.uuid4().hex; folder = self.repositories / ident
        # Full ordinary clone: every advertised branch and tag, no shallow or
        # recursive-submodule shortcuts and no change to transport/origin.
        run_git(['clone', '--no-recurse-submodules', '--', url, str(folder)],
                auth=self.current_account_auth,origin=self.origin)
        inventory = repository_inventory(folder)
        if inventory['origin'] != url: raise ValueError('Actual clone origin changed')
        record = {'artifact_id': ident, 'kind': 'git_clone', 'status': 'created',
            'url': redacted_url(url), 'head': inventory['head'], 'tree': inventory['tree'],
            'inventory': inventory, 'checked_out': True,
            'actual_artifact_operation': True, 'task_success_not_evaluated': True}
        write(self.root / (ident + '.json'), record); self.records[ident] = record
        return self._public(record)

    def _public(self, record):
        if record.get('kind') == 'git_clone': return super()._public(record)
        latest = record['refreshes'][-1]['parsed']
        return {'subscription_id': record['subscription_id'], 'kind': record['kind'],
            'active': record['active'], 'successful_refreshes': record['successful_refreshes'],
            'url': record['url'], 'entry_count': latest.get('entries', latest.get('events')),
            'explicit_local_client_adaptation': True, 'task_success_not_evaluated': True}


def artifact_call(action):
    """Strict literal parser; unregistered browser actions are left unchanged."""
    call = ast.parse(action, mode='eval').body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        raise ValueError('One literal operation required')
    if call.func.id not in TOOL_SCHEMAS: return None
    if call.keywords: raise ValueError('Artifact actions accept only positional literal arguments')
    args = [ast.literal_eval(value) for value in call.args]
    expected = {'clone_repository': 1, 'subscribe_feed': 2, 'refresh_subscription': 1, 'list_local_artifacts': 0}[call.func.id]
    if len(args) != expected or any(not isinstance(value, str) for value in args):
        raise ValueError('Artifact arguments do not match the public schema')
    return call.func.id, args
