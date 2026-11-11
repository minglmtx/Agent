"""Candidate persistent local reader for actual native RSS2 responses.

The shipped Map source serves RSS2 at /traces/rss. This reader accepts native
RSS feeds without requiring entries or future delivery. HTTP/parse failures do
not create a subscription. Native and browser qualification is still required.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
import xml.etree.ElementTree as ET

STATE_VERSION = 'native-map-rss-local-reader-v187'
VERSION = 'native-map-rss-local-reader-v187-r2'
MAX_BYTES = 5 * 1024 * 1024
SCHEMA = 'CREATE TABLE subscriptions (id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, active INTEGER NOT NULL CHECK(active IN (0,1)), body BLOB NOT NULL, body_sha256 TEXT NOT NULL, parsed TEXT NOT NULL)'


def native_url(value, origin):
    root, url = urlsplit(origin), urlsplit(urljoin(origin + '/', value))
    if (root.scheme != 'http' or root.hostname != '127.0.0.1' or not root.port
            or root.path or root.query or root.fragment or root.username is not None):
        raise ValueError('Actual isolated native origin required')
    if (url.scheme, url.netloc) != (root.scheme, root.netloc) or url.username is not None or url.password is not None or url.fragment:
        raise ValueError('Feed escaped the declared native origin')
    if not url.path.startswith('/') or any(char in value for char in ('\r', '\n', '\x00')):
        raise ValueError('Invalid native URL')
    return url.geturl()


def parse_rss(payload):
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_BYTES:
        raise ValueError('Complete bounded native RSS body required')
    if re.search(br'<!DOCTYPE|<!ENTITY', payload, re.I):
        raise ValueError('RSS entity declarations are not supported')
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError('Malformed RSS XML') from error
    channels = root.findall('channel')
    if root.tag != 'rss' or root.get('version') != '2.0' or len(channels) != 1:
        raise ValueError('Native RSS2 channel required')
    channel = channels[0]
    fields = {key: channel.findtext(key) for key in ('title', 'description', 'link')}
    if any(not isinstance(v, str) or not v.strip() for v in fields.values()):
        raise ValueError('RSS channel identity is incomplete')
    # Feed entries need not exist. The task does not audit each trace or wait
    # for future delivery; the actual feed response remains stored in full.
    return {'format': 'rss2', **fields, 'entries': len(channel.findall('item'))}


def native_response(response, expected_url, origin):
    url = native_url(expected_url, origin)
    if (response.get('requested_url') != url or response.get('url') != url
            or type(response.get('status')) is not int or response['status'] != 200
            or response.get('finished') is not True):
        raise ValueError('Completed successful native response without redirects required')
    body = response['body']
    return url, body, parse_rss(body)


class LocalReader:
    def __init__(self, path, *, create=False):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError('Owned regular reader database required')
        if create:
            with self.path.open('xb'):
                pass
            with closing(sqlite3.connect(self.path)) as db:
                with db:
                    db.execute(SCHEMA)
        if not self.path.is_file():
            raise ValueError('Reader must be explicitly provisioned')
        self.snapshot()

    def snapshot(self):
        with closing(sqlite3.connect(f'file:{self.path}?mode=ro', uri=True)) as db:
            schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            expected = [r for r in schema if r[0] == 'table']
            if expected != [('table', 'subscriptions', 'subscriptions', SCHEMA)]:
                raise ValueError('Complete reader schema differs')
            rows = db.execute('SELECT id,url,active,body,body_sha256,parsed FROM subscriptions ORDER BY id').fetchall()
        records = []
        for ident, url, active, body, sha, parsed in rows:
            if (not re.fullmatch('[0-9a-f]{32}', ident) or active not in (0, 1)
                    or not isinstance(body, bytes) or hashlib.sha256(body).hexdigest() != sha
                    or json.loads(parsed) != parse_rss(body)):
                raise ValueError('Persisted reader record is malformed')
            records.append(dict(id=ident, url=url, active=bool(active), body_sha256=sha,
                                body_hex=body.hex(), parsed=json.loads(parsed)))
        return dict(version=STATE_VERSION, schema=[list(row) for row in schema], records=records)

    def subscribe(self, value, origin, fetch):
        url = native_url(value, origin)
        url, body, parsed = native_response(fetch(url), url, origin)
        ident = uuid4().hex
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                # A preexisting subscription is retained, never relabeled new.
                old = db.execute('SELECT id FROM subscriptions WHERE url=?', (url,)).fetchone()
                if old:
                    return old[0]
                db.execute('INSERT INTO subscriptions VALUES(?,?,?,?,?,?)',
                           (ident, url, 1, body, hashlib.sha256(body).hexdigest(), json.dumps(parsed, sort_keys=True)))
        return ident


def evaluate(before, after, *, origin, responses, reopened, runtime_error=None, request_events=None, trace=None, contract=None):
    unknown = lambda why: dict(status='unknown', reward=None, reason=why, version=VERSION)
    try:
        if runtime_error:
            return unknown(str(runtime_error))
        if before['version'] != STATE_VERSION or after['version'] != STATE_VERSION or before['schema'] != after['schema']:
            return unknown('Reader capture or schema mismatch')
        from .input_rejection import confirmed
        rejected = confirmed(request_events, trace, contract, origin)
        if request_events is not None:
            if not isinstance(request_events, list) or any(not isinstance(e, dict) for e in request_events):
                return unknown('Native reader request capture malformed')
            if any(e.get('event') == 'request_error' for e in request_events) and not rejected:
                return unknown('Native reader request failed')
        initial = {r['id']: r for r in before['records']}
        final = {r['id']: r for r in after['records']}
        if len(initial) != len(before['records']) or len(final) != len(after['records']):
            return unknown('Ambiguous subscription identity')
        expected = native_url('/traces/rss', origin)
        for response in responses:
            native_response(response, response['requested_url'], origin)
        added = [r for ident, r in final.items() if ident not in initial]
        if any(final.get(ident) != row for ident, row in initial.items()):
            return unknown('Preexisting reader state changed')
        matching = [r for r in added if r['url'] == expected and r['active'] is True]
        witness = False
        for row in matching:
            for response in responses:
                if response.get('requested_url') != expected:
                    continue
                _, body, parsed = native_response(response, expected, origin)
                if (row['body_sha256'] == hashlib.sha256(body).hexdigest()
                        and row['body_hex'] == body.hex() and row['parsed'] == parsed
                        and native_url(parsed['link'], origin) == origin + '/traces'):
                    witness = True
        if matching and not witness:
            return unknown('Saved row lacks a matching actual native feed response')
        if not isinstance(reopened, dict) or reopened.get('http_status') != 200 or reopened.get('error'):
            if (rejected and before == after and not responses and not added
                    and isinstance(reopened, dict) and reopened.get('url') == origin + '/__lab_local__/reader'
                    and reopened.get('http_status') == 502 and reopened.get('error') is True
                    and reopened.get('visible_subscription_ids') == []
                    and 'Could not load or save the feed.' in reopened.get('actual_public_text', '')):
                return dict(version=VERSION, status='failure', reward=0.0,
                    checks=dict(new_correct_subscription=False, native_feed_verified=False, reopened_saved_record=False),
                    reason='Captured native input validation rejected the Actor-supplied URL before fetch; no subscription was saved.')
            return unknown('Missing or unhealthy final reader/document observation')
        visible = any(row['id'] in reopened.get('visible_subscription_ids', [])
                      and row['url'] in reopened.get('actual_public_text', '') for row in matching)
        checks = dict(new_correct_subscription=len(matching) == 1, native_feed_verified=witness,
                      reopened_saved_record=visible and reopened.get('method') == 'GET'
                      and reopened.get('url') == origin + '/__lab_local__/reader')
        passed = all(checks.values())
        return dict(version=VERSION, status='success' if passed else 'failure', reward=float(passed), checks=checks)
    except (KeyError, TypeError, ValueError) as error:
        return unknown(str(error))
