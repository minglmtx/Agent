"""Private reference lifecycle for ordinary native subscription attempts.

This module never changes the website or creates calendar fixtures. It reads
the declared native collection in a separate context; the actor's page, start,
observations and tools are untouched. Its receipts stay evaluator-only.
"""
from pathlib import Path
import hashlib

from . import gitlab_subscription_runtime as runtime
from .gitlab_local_artifacts_v2 import local_native_url
from .io_utils import atomic_write_json

VERSION = 'native-subscription-private-lifecycle-v1'


def _private_write(path, value):
    atomic_write_json(path, value)
    Path(path).chmod(0o600)


def scoped_choices(urls, *, origin, contract, username):
    spec = runtime.feed_spec(contract)
    choices = []
    for url in urls:
        try:
            url = local_native_url(url, origin, calendar=spec['kind'] == 'calendar')
            runtime.native_subscription_query(url, origin=origin, contract=spec, username=username)
        except ValueError:
            continue
        if url not in choices:
            choices.append(url)
    return choices


def capture(site, username, contract, context, directory, *, client, reader=None):
    from .browser_reference_context import private_reference_context
    from .browser_page_wait import settle_gitlab_capture
    from probe_gitlab_artifact_capabilities_v2 import PUBLIC

    directory = Path(directory)
    spec = runtime.feed_spec(contract)
    path = spec['page_path'].replace('{authenticated_username}', username)
    with private_reference_context(context) as private_context:
        page = private_context.new_page()
        response = page.goto(site.url+path, wait_until='domcontentloaded', timeout=60000)
        settle_gitlab_capture(page)
        if response is None or response.status != 200 or page.url != site.url+path:
            raise ValueError('Declared native subscription collection unavailable')
        state = page.evaluate(PUBLIC)
        choices = scoped_choices([link['href'] for link in state['links']], origin=site.url,
                                 contract=contract, username=username)
        if len(choices) != 1:
            raise ValueError('Unique native feed matching the declared scope required')
        url = choices[0]
        sort_cookies = {c['name']:c['value'] for c in private_context.cookies(site.url)
                       if c['name'] in ('issuable_sort','issue_sort','mergerequest_sort')}
        options = {'sort_cookies':sort_cookies}
        if reader is not None:options['session']=reader
        before = runtime.reference(site, username, contract, private_context, url,
                                   directory/'private-subscription-before.json', **options)
        try:
            fetched = private_context.request.get(url, timeout=45000, max_redirects=0)
            body, parsed = client.fetched_feed(fetched, spec['kind'])
        except Exception as error:
            from .native_failure_diagnostics import retain_private_failure
            retain_private_failure(site, error, browser_stage='subscription_feed_fetch')
            raise
        if fetched.url != url or fetched.status != 200:
            raise ValueError('Native feed response changed resource')
        if not runtime.inspect_payload(body, contract, before, origin=site.url)['payload_verified']:
            raise ValueError('Native response differs from independent finder selection')
        payload = directory/'private-subscription-response.bin'
        payload.write_bytes(body)
        payload.chmod(0o600)
        record = dict(version=VERSION, spec=spec, username=username, url=url,
                      status=fetched.status, kind=spec['kind'], parsed=parsed,
                      body_sha256=hashlib.sha256(body).hexdigest(), before=before,
                      sort_cookies=sort_cookies)
        _private_write(directory/'private-subscription-reference.json', record)
        return record


def finish(site, contract, record, directory, *, reader=None):
    """Read after execution, even after BrowserGym closed its contexts."""
    if record.get('version') != VERSION or record.get('spec') != runtime.feed_spec(contract):
        raise ValueError('Original declared subscription reference required')
    options = {'sort_cookies':record['sort_cookies']}
    if reader is not None:options['session']=reader
    after = runtime.reference(site, record['username'], contract, None, record['url'],
                              Path(directory)/'private-subscription-after.json', **options)
    record = dict(record, after=after, reference_unchanged=runtime.stable_reference(record['before'], after))
    _private_write(Path(directory)/'private-subscription-reference.json', record)
    return record


def verify(contract, record, directory, *, origin, artifact, client):
    """Recompute reference integrity from raw local evidence before scoring."""
    import json
    read = lambda name: json.loads(artifact(directory, name).read_text())
    spec = runtime.feed_spec(contract)
    if (record.get('version') != VERSION or record.get('spec') != spec or record.get('status') != 200
            or record.get('kind') != spec['kind'] or record.get('reference_unchanged') is not True
            or read('private-subscription-reference.json') != record
            or read('private-subscription-before.json') != record.get('before')
            or read('private-subscription-after.json') != record.get('after')
            or not runtime.stable_reference(record['before'], record['after'])):
        raise ValueError('Original complete stable subscription reference required')
    params = runtime.native_subscription_query(record['url'], origin=origin, contract=spec, username=record['username'])
    before = record['before']
    if (before.get('username') != record['username'] or before.get('kind') != spec['kind']
            or type(before.get('account_id')) is not int or before['account_id'] <= 0
            or any(before.get('native_options', {}).get(k) != v for k,v in params.items())):
        raise ValueError('Native finder account or filters differ')
    body = artifact(directory, 'private-subscription-response.bin').read_bytes()
    if (hashlib.sha256(body).hexdigest() != record['body_sha256']
            or client.parse_feed(body, spec['kind']) != record['parsed']
            or not runtime.inspect_payload(body, contract, before, origin=origin)['payload_verified']):
        raise ValueError('Original native feed response or selection differs')
    return before
