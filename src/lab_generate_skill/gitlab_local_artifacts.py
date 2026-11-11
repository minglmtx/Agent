"""Local artifact controls; neither private references nor tools for the actor.

A real clone is different from copying a URL. A real local subscription stores
an active client record and refreshes a valid native feed; opening its URL alone
is not subscription. This explicit client adaptation still needs an admitted
browser/tool interface before it can be used in actor training.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, unquote

MAX_FEED_BYTES = 5 * 1024 * 1024


def redacted_url(url):
    part = urlsplit(url)
    if part.username is not None or part.password is not None:
        raise ValueError('Do not store URL user credentials')
    query = urlencode([(key, 'REDACTED' if re.search(r'token|secret|password', key, re.I) else value)
                       for key, value in parse_qsl(part.query, keep_blank_values=True)])
    return urlunsplit((part.scheme, part.netloc, part.path, query, part.fragment))


def local_native_url(href, origin, *, calendar=False):
    part = urlsplit(urljoin(origin + '/', href))
    current = urlsplit(origin)
    if part.scheme == 'webcal' and calendar:
        part = part._replace(scheme=current.scheme)
    if (part.scheme, part.netloc) != (current.scheme, current.netloc) or part.username is not None or part.password is not None:
        raise ValueError('Native artifact URL escaped the exact leased local origin')
    if part.scheme not in ('http', 'https') or part.fragment or not part.path.startswith('/'):
        raise ValueError('Invalid native local artifact URL')
    if unquote(part.path).startswith('//') or any(x in unquote(part.path).split('/') for x in ('.', '..')):
        raise ValueError('Invalid artifact path')
    return urlunsplit(part)


def clone_url(href, origin, project):
    url = local_native_url(href, origin)
    part = urlsplit(url)
    if unquote(part.path) != '/' + project + '.git' or part.query:
        raise ValueError('Native clone URL does not identify the exact requested repository')
    return url


def clone_completion(destination, origin, project, *, head, tree):
    """Independent final-artifact checks; copied links and wrong objects fail."""
    destination = Path(destination)
    checks = dict.fromkeys(('actual_local_git_repository', 'native_advertised_origin',
                            'pinned_repository_head', 'complete_pinned_tree_object',
                            'working_tree_checked_out'), False)
    if not (destination / '.git').is_dir(): return {'checks': checks, 'passed': False}
    env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}
    def read(*args):
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(destination), *args],
                              env=env, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    try:
        actual_head, actual_tree, actual_origin = read('rev-parse', 'HEAD'), read('rev-parse', 'HEAD^{tree}'), read('remote', 'get-url', 'origin')
        expected_origin = clone_url('/' + project + '.git', origin, project)
        checks.update(actual_local_git_repository=Path(read('rev-parse', '--show-toplevel')).resolve() == destination.resolve(),
                      native_advertised_origin=actual_origin == expected_origin, pinned_repository_head=actual_head == head,
                      complete_pinned_tree_object=actual_tree == tree, working_tree_checked_out=read('status', '--porcelain') == '')
        return {'checks': checks, 'passed': all(checks.values()), 'head': actual_head, 'tree': actual_tree,
                'origin': redacted_url(actual_origin)}
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {'checks': checks, 'passed': False}


def clone_repository(url, origin, project, destination, *, head, tree, timeout=180):
    url = clone_url(url, origin, project)
    destination = Path(destination)
    if destination.exists(): raise ValueError('Clone control needs a fresh destination')
    env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'}
    prefix = ['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
              '-c', 'protocol.allow=never', '-c', 'protocol.http.allow=always',
              '-c', 'protocol.https.allow=always', '-c', 'http.followRedirects=false']
    subprocess.run(prefix + ['clone', '--depth=1', '--no-recurse-submodules', '--', url, str(destination)],
                   env=env, capture_output=True, timeout=timeout, check=True)
    result = clone_completion(destination, origin, project, head=head, tree=tree)
    result['actual_clone'] = True
    return result


def parse_feed(payload, kind):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_FEED_BYTES:
        raise ValueError('Feed is empty or exceeds the finite artifact budget')
    if kind == 'atom':
        if re.search(br'<!DOCTYPE|<!ENTITY', payload, re.I): raise ValueError('External XML entities are prohibited')
        root = ET.fromstring(payload)
        namespace = '{http://www.w3.org/2005/Atom}'
        if root.tag != namespace + 'feed': raise ValueError('Native GitLab feed is not an Atom document')
        title = root.findtext(namespace + 'title')
        ident = root.findtext(namespace + 'id')
        if not title or not ident: raise ValueError('Atom feed lacks its own title/identity')
        entries = root.findall(namespace + 'entry')
        ids = [entry.findtext(namespace + 'id') for entry in entries]
        if any(not value for value in ids) or len(set(ids)) != len(ids): raise ValueError('Atom entry identities incomplete or duplicated')
        return {'format': 'atom', 'title': title, 'identity': redacted_url(ident), 'entries': len(entries),
                'entry_ids': [redacted_url(value) for value in ids], 'valid_empty_feed_is_allowed': True}
    if kind != 'calendar': raise ValueError('Unsupported native feed kind')
    text = payload.decode('utf-8-sig')
    lines = []
    for line in text.replace('\r\n', '\n').splitlines():
        if line.startswith((' ', '\t')) and lines: lines[-1] += line[1:]
        else: lines.append(line)
    if not lines or lines[0] != 'BEGIN:VCALENDAR' or lines[-1] != 'END:VCALENDAR' or 'VERSION:2.0' not in lines:
        raise ValueError('Invalid iCalendar envelope')
    events, current = [], None
    for line in lines[1:-1]:
        if line == 'BEGIN:VEVENT':
            if current is not None: raise ValueError('Nested calendar events')
            current = {}
        elif line == 'END:VEVENT':
            if current is None or not current.get('UID'): raise ValueError('Calendar event has no identity')
            events.append(current); current = None
        elif current is not None and ':' in line:
            key, value = line.split(':', 1); current[key.split(';', 1)[0]] = value
    if current is not None: raise ValueError('Calendar event did not end')
    ids = [event['UID'] for event in events]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate calendar events')
    return {'format': 'icalendar', 'events': len(events), 'entry_ids': ids,
            'advertised_due_date_window_not_rewritten': True, 'valid_empty_feed_is_allowed': True}


def fetched_feed(response, kind):
    if response.status != 200: raise ValueError('Native feed HTTP request did not succeed')
    body = response.body()
    return body, parse_feed(body, kind)


class LocalSubscriptionClient:
    """Explicit deterministic local client registry with real refresh records."""
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(mode=0o700, parents=True, exist_ok=False)

    def subscribe(self, native_url, origin, kind, fetch):
        url = local_native_url(native_url, origin, calendar=kind == 'calendar')
        body, parsed = fetched_feed(fetch(url), kind)
        ident = uuid.uuid4().hex
        folder = self.root / ident; folder.mkdir(mode=0o700)
        secret = folder / 'fetch-url-private.txt'
        descriptor = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as file: file.write(url)
        record = {'subscription_id': ident, 'active': True, 'url': redacted_url(url), 'kind': kind,
                  'successful_refreshes': 1, 'last_body_sha256': hashlib.sha256(body).hexdigest(), 'parsed': parsed,
                  'explicit_local_client_adaptation': True}
        (folder / 'last-feed-private.bin').write_bytes(body)
        os.chmod(folder / 'last-feed-private.bin', 0o600)
        (folder / 'state.json').write_text(json.dumps(record, indent=2) + '\n')
        return record

    def refresh(self, ident, origin, fetch):
        if not re.fullmatch(r'[0-9a-f]{32}', ident): raise ValueError('Invalid local subscription ID')
        folder = self.root / ident
        record = json.loads((folder / 'state.json').read_text())
        if not record['active']: raise ValueError('Inactive subscription cannot refresh')
        url = local_native_url((folder / 'fetch-url-private.txt').read_text(), origin, calendar=record['kind'] == 'calendar')
        body, parsed = fetched_feed(fetch(url), record['kind'])
        record.update(successful_refreshes=record['successful_refreshes'] + 1,
                      last_body_sha256=hashlib.sha256(body).hexdigest(), parsed=parsed)
        (folder / 'last-feed-private.bin').write_bytes(body)
        (folder / 'state.json').write_text(json.dumps(record, indent=2) + '\n')
        return record

    def completion(self, ident, *, expected_url, expected_kind):
        if not ident or not re.fullmatch(r'[0-9a-f]{32}', ident): return False
        file = self.root / ident / 'state.json'
        if not file.exists(): return False
        record = json.loads(file.read_text())
        return (record.get('active') is True and record.get('successful_refreshes', 0) >= 2
                and (self.root / ident / 'fetch-url-private.txt').read_text() == expected_url
                and record.get('url') == redacted_url(expected_url) and record.get('kind') == expected_kind)
