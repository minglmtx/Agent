"""Evaluator-only public MR collection capture; never supplies an actor answer.

The browser discovers members from status lists. No database IDs or timestamps
are passed to this reader. Control validation compares the complete captured
membership to the independent native reference afterwards.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, parse_qs

from .gitlab_completion_time_query import validate, timestamp
from .gitlab_issuable_list import read_issuable_list

EVENT = re.compile(r'^(Merged|Closed) by: .+ at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC$')


def list_identity(q, url, state):
    u = urlsplit(url); params = parse_qs(u.query, keep_blank_values=True)
    if (u.path != '/' + q['project_path'] + '/-/merge_requests' or u.fragment
            or params.get('scope') != ['all'] or params.get('state') != [state]
            or set(params) - {'scope', 'state', 'page', 'sort'}
            or any(len(v) != 1 for v in params.values())):
        raise ValueError('Public collection changed project or status scope')
    number = params.get('page', ['1'])[0]
    if not number.isdigit() or int(number) < 1:
        raise ValueError('Invalid public collection page')
    return int(number)


def listing(q, captured, url, state):
    validate(q); list_identity(q, url, state)
    if captured.get('project_ids') != [str(q['project_id'])]:
        raise ValueError('Wrong rendered project identity')
    if type(captured.get('user_id')) is not int or captured['user_id'] <= 0 or captured.get('needs_filter'):
        raise ValueError('Public collection identity or readiness unavailable')
    active = [t['text'] for t in captured['tabs'] if t['active']]
    label = {'closed': 'Closed', 'merged': 'Merged'}[state]
    if not captured['tabs'] and captured.get('merge_request_onboarding') is True and not captured['items']:
        return 0, []
    if len(active) != 1 or not re.fullmatch(label + r'\s+[\d,]+', active[0]):
        raise ValueError('Exact active terminal-state counter unavailable')
    count = int(re.sub(r'\D', '', active[0])); prefix = '/' + q['project_path'] + '/-/merge_requests/'
    rows = []
    for item in captured['items']:
        path = item['path']
        if not path.startswith(prefix) or not re.fullmatch(r'[1-9]\d*', path[len(prefix):]):
            raise ValueError('Public collection includes another object')
        rows.append({'iid': int(path[len(prefix):]), 'path': path, 'state': state})
    if len({r['iid'] for r in rows}) != len(rows) or len(rows) > count:
        raise ValueError('Duplicate or excess public collection members')
    if not count:
        if rows or not (captured.get('no_results') or captured.get('merge_request_onboarding')):
            raise ValueError('Empty count lacks an explicit empty page')
    elif not rows:
        raise ValueError('Public counter loaded without its collection')
    return count, rows


def completion_event(names, state):
    label = {'closed': 'Closed', 'merged': 'Merged'}[state]; values = set()
    for name in names:
        match = EVENT.fullmatch(name) if isinstance(name, str) else None
        if match and match[1] == label:
            values.add(datetime.strptime(match[2], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc))
    if len(values) != 1:
        raise ValueError('Unambiguous accessible terminal event required; Updated/DOM datetime is insufficient')
    return next(iter(values))


def accessible_names(page):
    cdp = page.context.new_cdp_session(page)
    try:
        return [n.get('name', {}).get('value', '') for n in cdp.send('Accessibility.getFullAXTree')['nodes']
                if not n.get('ignored', False)]
    finally:
        cdp.detach()


def observable_completion(page, state, detail, *, timeout_seconds=10):
    """Wait for asynchronous public completion content, retaining AX changes.

    The main page can be visible while GitLab's MR widget is still loading.
    Neither a DOM timestamp nor a native reference substitutes for public AX.
    """
    deadline = time.monotonic() + timeout_seconds
    for _ in range(40):
        names = accessible_names(page)
        if not detail['ax_stages'] or detail['ax_stages'][-1] != names:
            detail['ax_stages'].append(names)
        try:
            return completion_event(names, state)
        except ValueError:
            pass
        stamps = [s for s in page.locator('time').all() if s.is_visible()]
        if len(stamps) > 30:
            raise ValueError('Public timestamp capture exceeds per-page budget')
        for stamp in stamps:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            stamp.hover(timeout=min(2000, max(1, int(remaining * 1000))))
            names = accessible_names(page)
            if detail['ax_stages'][-1] != names:
                detail['ax_stages'].append(names)
            try:
                return completion_event(names, state)
            except ValueError:
                pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        page.wait_for_timeout(min(250, remaining * 1000))
    raise ValueError('Terminal timestamp is not observable in public AX within readiness budget')


def ui_values(page, q, *, evidence=None, max_pages=20, max_details=100):
    validate(q)
    origin = urlsplit(page.url)
    list_identity(q, page.url, 'all')
    base = origin.scheme + '://' + origin.netloc
    record = {'version': 'gitlab-public-completion-collection-v1', 'lists': [], 'details': [],
              'complete': False, 'values': None}
    if evidence is not None:
        evidence.append(record)  # Preserve partial capture if validation fails.
    inventory = []; account = None
    def visit(target):
        u = urlsplit(target)
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):
            raise ValueError('Public navigation leaves the local website')
        response = page.goto(target, wait_until='domcontentloaded', timeout=30000)
        if response is None or response.status != 200 or page.url != target:
            raise ValueError('Public target unavailable or redirected')
        return response.status
    for state in ('closed', 'merged'):
        target = base + '/' + q['project_path'] + '/-/merge_requests?scope=all&state=' + state
        collected = []; total = None; seen = set()
        for _ in range(max_pages):
            number = list_identity(q, target, state)
            if number in seen:
                raise ValueError('Public pagination loop')
            seen.add(number); status = visit(target)
            page.wait_for_function(r'''() => [...document.querySelectorAll('a.nav-link.active')]
              .some(e => e.getClientRects().length && /^(Closed|Merged)\s+[\d,]+$/.test(e.innerText.trim())) ||
              document.body.innerText.includes("Merge requests are a place to propose changes you've made to a project and discuss those changes with others")''', timeout=15000)
            captured = read_issuable_list(page); count, members = listing(q, captured, page.url, state)
            record['lists'].append({'url': page.url, 'http_status': status, 'state': state, 'capture': captured})
            if total is None: total = count
            if count != total or account is not None and account != captured['user_id']:
                raise ValueError('Public collection/account changed during capture')
            account = captured['user_id']; collected.extend(members)
            if len({r['iid'] for r in collected}) != len(collected) or len(collected) > total:
                raise ValueError('Repeated or excess collection member across pages')
            links = [e for e in page.get_by_role('link', name=re.compile(r'^Next\s*$')).all() if e.is_visible()]
            if not links:
                if len(collected) != total:
                    raise ValueError('Public collection incomplete at pagination end')
                break
            if len(links) != 1 or len(collected) >= total:
                raise ValueError('Pagination contradicts the public counter')
            target = urljoin(page.url, links[0].get_attribute('href') or '')
            if list_identity(q, target, state) != number + 1:
                raise ValueError('Public pagination skipped a page')
        else:
            raise ValueError('Public collection page budget exhausted')
        inventory.extend(collected)
    if len({r['iid'] for r in inventory}) != len(inventory):
        raise ValueError('Object appears in incompatible terminal-state collections')
    if len(inventory) > max_details:
        raise ValueError('Complete public detail collection exceeds capture budget')
    completions = []
    for member in inventory:
        status = visit(base + member['path'])
        page.locator('main,#content-body').first.wait_for(state='visible', timeout=10000)
        detail = {**member, 'url': page.url, 'http_status': status, 'ax_stages': []}
        record['details'].append(detail)
        event = observable_completion(page, member['state'], detail)
        detail['completed_at'] = event.isoformat(); completions.append(event)
    value = max(completions).strftime('%Y-%m-%dT%H:%MZ') if completions else 'none'
    record.update(complete=True, values={'completed_at': value}, user_id=account)
    return dict(record['values'])


def verify_collection(evidence, reference):
    """Additional control check: compare all public members, not just max time."""
    if len(evidence) != 1 or evidence[0].get('complete') is not True:
        raise ValueError('Complete independent public collection capture required')
    record = evidence[0]
    expected = {(r['iid'], {2: 'closed', 3: 'merged'}[r['state_id']]) for r in reference['source_state']}
    actual = [(r['iid'], r['state']) for r in record['details']]
    if (len(actual) != len(set(actual)) or set(actual) != expected
            or len(actual) != reference['collection_count'] or record['values'] != reference['values']):
        raise ValueError('Public completion collection differs from native reference')
    native = {r['iid']: r for r in reference['source_state']}
    for detail in record['details']:
        row = native[detail['iid']]
        expected_time = timestamp(row['latest_closed_at'] if row['state_id'] == 2 else row['merged_at'])
        observed = []
        for names in detail['ax_stages']:
            try: observed.append(completion_event(names, detail['state']))
            except ValueError: continue
        expected_path = '/' + reference['project']['path'] + '/-/merge_requests/' + str(row['iid'])
        if (detail['path'] != expected_path or urlsplit(detail['url']).path != expected_path
                or detail['http_status'] != 200 or not observed or set(observed) != {expected_time}
                or timestamp(detail['completed_at']) != expected_time):
            raise ValueError('Each complete native event must match its public detail evidence')
    return True
