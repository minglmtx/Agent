"""Public, exact issue counts for native GitLab project directory rows.

The directory may abbreviate a count. Resolve only that case through its
native issues link, in a separate reader tab. Never multiply a rounded count,
read a private database, or change the caller's page. Existing directory
readers remain strict and unchanged.
"""
from urllib.parse import urljoin, urlsplit, unquote, parse_qs

from .browser_page_wait import settle_gitlab_capture
from .gitlab_issuable_list import read_issuable_list
from .public_counts import integer_count, parse_public_count


def exact_open_count(state, url, project_path, user_id):
    u = urlsplit(url)
    if unquote(u.path).rstrip('/') != '/' + project_path + '/-/issues' or u.fragment:
        raise ValueError('Wrong issue collection identity')
    params = parse_qs(u.query, keep_blank_values=True)
    if set(params) - {'scope', 'state'} or params.get('scope', ['all']) != ['all'] or params.get('state', ['opened']) != ['opened']:
        raise ValueError('Unexpected issue filter')
    if state.get('user_id') != user_id or state.get('needs_filter'):
        raise ValueError('Wrong account or unloaded list')
    active = [r['text'] for r in state.get('tabs', []) if r['active']]
    if len(active) != 1 or not active[0].startswith('Open '):
        raise ValueError('Missing native Open count')
    count = integer_count(active[0][5:])
    items = state.get('items', [])
    if count and not items:
        raise ValueError('Issue list has not loaded')
    if not count and (items or not state.get('no_results')):
        raise ValueError('Unconfirmed empty list')
    if any(not r['path'].startswith('/' + project_path + '/-/issues/') for r in items):
        raise ValueError('Issue list contains a different project')
    return count


def public_issue_rows(page):
    """Return exact rows and public evidence, preserving the original page."""
    origin = urlsplit(page.url)
    user_id = page.evaluate('() => window.gon?.current_user_id')
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('Native current account is missing')
    raw = page.locator('.project-row').evaluate_all(r'''es=>es.map(e=>({
      path:e.querySelector('a.project[href]')?.getAttribute('href'),
      counts:[...e.querySelectorAll('a.issues')].filter(n=>n.getClientRects().length)
        .map(n=>({text:n.innerText.trim(),href:n.getAttribute('href')}))}))''')
    if not raw:
        raise ValueError('Empty native project directory')
    rows, evidence, seen = [], [], set()
    reader = None
    try:
        for row in raw:
            link = row.get('path') or ''
            p = urlsplit(urljoin(page.url, link))
            path = unquote(p.path).strip('/')
            if p.netloc != origin.netloc or p.scheme != origin.scheme or p.query or p.fragment or len(path.split('/')) < 2 or path in seen:
                raise ValueError('Invalid or duplicate project identity')
            seen.add(path)
            counts = row.get('counts', [])
            if not counts or len({r['text'] for r in counts}) != 1:
                raise ValueError('Ambiguous issue count')
            for item in counts:
                target = urlsplit(urljoin(page.url, item.get('href') or ''))
                if target.netloc != origin.netloc or target.scheme != origin.scheme or unquote(target.path).rstrip('/') != '/' + path + '/-/issues' or target.query or target.fragment:
                    raise ValueError('Issue link has the wrong identity or scope')
            text = counts[0]['text']
            parsed = parse_public_count(text)
            if parsed['exact']:
                count = parsed['value']
                proof = {'path': path, 'display': text, 'source': 'directory'}
            else:
                # Unit conversion is presentation evidence, never an exact
                # issue count. Resolve through the original native Open tab.
                if reader is None:
                    reader = page.context.new_page()
                response = reader.goto(urljoin(page.url, counts[0]['href']), wait_until='domcontentloaded', timeout=60000)
                if not response or response.status != 200:
                    raise ValueError('Native issue page unavailable')
                wait = settle_gitlab_capture(reader)
                state = read_issuable_list(reader)
                count = exact_open_count(state, reader.url, path, user_id)
                cdp = reader.context.new_cdp_session(reader)
                try:
                    names = [n.get('name', {}).get('value', '') for n in cdp.send('Accessibility.getFullAXTree')['nodes'] if not n.get('ignored')]
                finally:
                    cdp.detach()
                proof = {'path': path, 'display': text, 'source': 'native_issue_page',
                         'url': reader.url, 'state': state, 'wait': wait, 'ax_names': names}
            rows.append({'path': path, 'open_issues': count})
            evidence.append(proof)
    finally:
        if reader is not None:
            reader.close()
    return rows, evidence
