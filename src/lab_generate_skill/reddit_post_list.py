"""Native Reddit forum post ordering, scope and cursor checks at task finish.

Reference data is private evaluator input. It is never added to actor observations.
Ordering follows the pinned Postmill SubmissionPage and SubmissionFinder sources.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlsplit

from .site_database import select_rows

SORTS = {'new': ('id',), 'top': ('net_score', 'id'),
         'most_commented': ('comment_count', 'id'), 'hot': ('ranking', 'id')}
LABELS = {'new': 'New', 'top': 'Top', 'most_commented': 'Most commented', 'hot': 'Hot'}
CURSOR_KEYS = {'id': 'id', 'net_score': 'netScore', 'comment_count': 'commentCount', 'ranking': 'ranking'}
TIME_LABELS = {'all': 'All time', 'day': 'Past 24 hours', 'week': 'Past week',
               'month': 'Past month', 'year': 'Past year'}
FIELDS = 's.id,s.user_id,s.title,s.timestamp,s.comment_count,s.net_score,s.visibility,s.sticky,s.ranking,s.last_active,f.name AS forum'


def post_reference(site, forum, username):
    if site.domain != 'reddit' or not re.fullmatch(r'[A-Za-z0-9_]+', forum):
        raise ValueError('Invalid native forum reference')
    account = select_rows(site, "SELECT id,username,front_page_sort_mode FROM users WHERE username='" + username.replace("'", "''") + "'")
    if len(account) != 1:
        raise ValueError('Expected one authenticated Reddit account')
    return {'account': account[0], 'blocks': select_rows(site, 'SELECT * FROM user_blocks ORDER BY blocker_id,blocked_id'),
            'rows': select_rows(site, 'SELECT ' + FIELDS + " FROM submissions s JOIN forums f ON f.id=s.forum_id WHERE f.name='" + forum + "' ORDER BY s.id")}


def verify_post_reference(site, spec):
    ref = spec['reference']
    if post_reference(site, spec['forum'], ref['account']['username']) != ref:
        raise RuntimeError('Post listing differs from pinned account and submission references')


def read_post_list(page):
    state = page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length;
      const root=document.querySelector('#main');
      const article=root?[...root.querySelectorAll('article.submission')].filter(visible):[];
      return {
        forum_heading:[...document.querySelectorAll('h1.forum-title')].filter(visible).map(e=>e.innerText.trim()),
        forum_links:[...document.querySelectorAll('h1.forum-title a[href]')].filter(visible).map(e=>new URL(e.href).pathname),
        sort_labels:root?[...root.querySelectorAll('button.tab.dropdown__toggle')].filter(visible).map(e=>e.innerText.trim()):[],
        entries:article.map(e=>({
          id:e.querySelector('form[data-vote-route-value="submission_vote"]')?.getAttribute('data-vote-id-value')||null,
          title:e.querySelector('.submission__title')?.innerText.trim()??null,
          score:e.querySelector('.vote__net-score')?.innerText.trim()??null,
          time:e.querySelector('time')?.dateTime??null,
          comments:[...e.querySelectorAll('.submission__nav a')].map(a=>a.innerText.trim()).find(t=>/^(No comments|\d+ comments?)$/.test(t))??null
        })),
        empty_notice:root?root.innerText.includes("There's nothing here…"):false
      };
    }''')
    state['captured_utc'] = datetime.now(timezone.utc).isoformat()
    return state


def _date(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Reference/capture timestamp requires timezone')
    return parsed


def _cutoff(now, window):
    if window == 'all': return None
    if window in ('day', 'week'): return now - timedelta(days=1 if window == 'day' else 7)
    # PHP DateTime modify('-1 month/year') keeps the day and rolls overflow
    # into the following month, unlike clipping to the last valid day.
    months = now.year * 12 + now.month - 1 - (1 if window == 'month' else 12)
    year, month = divmod(months, 12)
    return now.replace(year=year, month=month + 1, day=1) + timedelta(days=now.day - 1)


def expected_posts(reference, forum, mode, query, captured_utc):
    """Compute the actual native page, including blocked authors and keyset cursor."""
    window = query.get('t', ['all'])[0]
    if mode not in SORTS or window not in TIME_LABELS:
        raise ValueError('Unsupported native post sort/time range')
    rows = reference['rows']; known = {int(r['id']): r for r in rows}
    if len(known) != len(rows) or any(r['forum'] != forum for r in rows):
        raise ValueError('Duplicate or wrong-forum private reference')
    blocked = {r['blocked_id'] for r in reference['blocks'] if r['blocker_id'] == reference['account']['id']}
    available = [r for r in rows if r['visibility'] == 'visible' and r['user_id'] not in blocked]
    cutoff = _cutoff(_date(captured_utc), window)
    if cutoff:
        if any(abs((_date(r['timestamp']) - cutoff).total_seconds()) < 5 for r in available):
            raise ValueError('Time-window boundary too close to the capture clock')
        available = [r for r in available if _date(r['timestamp']) > cutoff]
    keys = SORTS[mode]
    cursor_keys = ['next[' + CURSOR_KEYS[k] + ']' for k in keys]
    supplied = [k for k in query if k.startswith('next')]
    if supplied:
        if set(supplied) != set(cursor_keys): raise ValueError('Invalid native post cursor fields')
        cursor = tuple(int(query[k][0]) for k in cursor_keys)
        anchor = known.get(cursor[-1])
        if anchor is None or tuple(int(anchor[k]) for k in keys) != cursor:
            raise ValueError('Post cursor does not identify a reference row')
        # PagerWave's rendered More link names the first unseen row, not the
        # final row on the preceding page. Native controls verify inclusion of
        # that anchor for New, Top and Most commented, including score ties.
        available = [r for r in available if not r['sticky'] and tuple(int(r[k]) for k in keys) <= cursor]
    available.sort(key=lambda r: ((int(bool(r['sticky'])),) if not supplied else ()) + tuple(int(r[k]) for k in keys), reverse=True)
    return available[:25]


def post_list_checks(spec, state, url):
    if not isinstance(state, dict) or any(not isinstance(state.get(k), list) for k in ('entries', 'forum_heading', 'forum_links', 'sort_labels')) or not isinstance(state.get('captured_utc'), str):
        raise ValueError('Missing native forum post-list capture')
    ref = spec['reference']; parts = urlsplit(url); query = parse_qs(parts.query, keep_blank_values=True)
    match = re.fullmatch(r'/f/([^/]+)(?:/(hot|new|top|most_commented))?/?', unquote(parts.path))
    mode = match[2] if match and match[2] else ref['account']['front_page_sort_mode'] or 'hot'
    forum = spec['forum']; window = query.get('t', ['all'])[0]
    checks = {'post_forum_identity': bool(match and match[1] == forum and state['forum_heading'] == [forum] and state['forum_links'] == ['/f/' + forum]),
              'post_parameters_unambiguous': all(len(v) == 1 for v in query.values()) and all(k == 't' or k.startswith('next[') for k in query),
              'post_sort_selected': mode in spec['allowed_sorts'],
              'post_time_range': window in spec['allowed_times']}
    if not all(checks.values()): return checks
    expected = expected_posts(ref, forum, mode, query, state['captured_utc'])
    labels = [LABELS[mode]] + ([TIME_LABELS[window]] if mode in ('top', 'most_commented') else [])
    checks['post_native_controls'] = state['sort_labels'] == labels
    entries = state['entries']
    ids = [str(r['id']) for r in entries]
    checks['post_list_contents'] = ids == [str(r['id']) for r in expected] and len(ids) == len(set(ids))
    by_id = {str(r['id']): r for r in expected}
    def values_match(item):
        ref_row = by_id.get(str(item['id']))
        if ref_row is None: return False
        n = ref_row['comment_count']; comments = 'No comments' if n == 0 else str(n) + (' comment' if n == 1 else ' comments')
        return (item['title'] == ref_row['title'].strip() and item['score'] == str(ref_row['net_score'])
                and item['comments'] == comments and _date(item['time']) == _date(ref_row['timestamp']))
    checks['post_visible_values'] = all(values_match(r) for r in entries)
    # Empty lists need an actual native empty-state message, not missing capture.
    checks['post_content_present'] = bool(entries) if expected else state.get('empty_notice') is True
    return checks


FEEDBACK = {
    'post_forum_identity': 'The actual post list belongs to the requested forum.',
    'post_parameters_unambiguous': 'The selected list parameters are unambiguous.',
    'post_sort_selected': 'The requested post sorting criterion is selected.',
    'post_time_range': 'The requested time range is selected.',
    'post_native_controls': 'The native list controls display the selected sorting and time range.',
    'post_list_contents': 'The actual posts match the selected ordering, time range and page.',
    'post_visible_values': 'The displayed post identities and values agree with the stored records.',
    'post_content_present': 'The native post content or its verified empty state is displayed.'}
