"""Complete native maxima, with ties and public issued-observation coverage.

References are private SELECT results. This module never navigates, chooses an
action, adds an expected value to AX, or scores an intermediate browser step.
The native search cap is a capability boundary, not an all-results claim.
"""
from collections import Counter
from copy import deepcopy
import json
import re
from urllib.parse import parse_qs, unquote, urlsplit

from .site_database import select_rows
from .reddit_search import search_reference, normalized_query
from .source_revision_binding import binding, require_source_binding

VERSION = 'reddit-complete-native-maximum-query-v1'
KINDS = {'forum_author_count', 'search_forum_count', 'search_top_comments'}
READ = r'''() => {
 const visible=e=>{if(!e||!e.isConnected||!e.getClientRects().length)return false;
  for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse')return false;}return true;};
 const root=document.querySelector('#main');
 const own=(e,s)=>[...e.querySelectorAll(s)].filter(n=>n.closest('article')===e);
 const rows=root?[...root.querySelectorAll('article.submission,article.comment')]:[];
 return {url:location.href,title:document.title,
  viewport:{x:scrollX,y:scrollY,height:innerHeight,document_height:document.documentElement.scrollHeight},
  entries:rows.map(e=>{const comment=e.classList.contains('comment');
   const label=comment?own(e,'.comment__body')[0]:own(e,'.submission__title')[0];
   const links=own(e,'a[href]').filter(visible);
   const user=links.find(a=>/^\/user\//.test(new URL(a.href).pathname));
   const score=own(e,'.vote__net-score')[0];
   const permalinks=comment?links.filter(a=>a.innerText.trim()==='Permalink'):[];
   return {kind:comment?'comment':'submission',article_bid:e.getAttribute('bid'),label:label?.innerText||'',
    ...(comment?{permalink:permalinks.length===1?permalinks[0].href:null}:{}),
    visible:visible(label),links:links.map(a=>a.href),
    username:user?.innerText.trim()||'',score:score?.innerText.trim()??null};}),
  pagination:root?[...root.querySelectorAll('a[href]')].filter(visible)
   .filter(a=>/^(More|Next|Previous)$/i.test(a.innerText.trim())).map(a=>({label:a.innerText.trim(),url:a.href})):[],
  empty_notice:!!root&&root.innerText.includes("There's nothing here…")};
}'''


def enabled(contract):
    if 'reddit_maximum_query' not in contract:
        return False
    spec = contract['reddit_maximum_query']
    if (contract.get('domain') != 'reddit' or not isinstance(spec, dict)
            or spec.get('kind') not in KINDS or spec.get('version') != VERSION
            or contract.get('eligible_for_training') is not False
            or any(contract.get(k) for k in ('query','submission','preferences','membership',
                                           'reddit_native_task','reddit_native_read'))):
        raise ValueError('One explicit native maximum task family required')
    binding(contract)
    kind = spec['kind']
    if kind == 'forum_author_count':
        if set(spec) != {'kind','version','forum'} or not re.fullmatch('[A-Za-z0-9_]+', spec.get('forum','')):
            raise ValueError('Explicit native forum identity required')
    elif (set(spec) != {'kind','version','query'} or not isinstance(spec.get('query'), str)
          or not spec['query'].strip() or len(spec['query']) > 300):
        raise ValueError('Explicit bounded native query required')
    return True


def require_original_binding(contract, original_contract, inventory):
    enabled(contract)
    return require_source_binding(contract, original_contract, inventory, domain='reddit')


def fields(contract):
    if not enabled(contract): return None
    return {'forum_author_count':['username'], 'search_forum_count':['forum'],
            'search_top_comments':None}[contract['reddit_maximum_query']['kind']]


def public_goal(contract):
    """Only task scope and answer protocol; no private winner or counts."""
    shape = fields(contract)
    if shape is None: return contract['goal']
    from .browser_prompt_contract import query_finish_instruction
    return contract['goal'] + '\n' + query_finish_instruction(shape)


def _quoted(text): return "'" + text.replace("'", "''") + "'"


def reference(site, contract, username):
    enabled(contract); spec = contract['reddit_maximum_query']
    if site.domain != 'reddit' or not isinstance(username, str) or not username:
        raise ValueError('Native Reddit authenticated scope required')
    users = select_rows(site, 'SELECT id,username FROM users WHERE username=' + _quoted(username))
    if len(users) != 1 or type(users[0]['id']) is not int:
        raise ValueError('One native task viewer required')
    uid = users[0]['id']
    # This exactly preserves the native visible/blocked-author listing scope.
    base = ("SELECT s.id,s.user_id,u.username,s.title,s.net_score,s.visibility,"
            "f.name AS forum FROM submissions s JOIN forums f ON f.id=s.forum_id "
            "JOIN users u ON u.id=s.user_id WHERE s.visibility='visible' "
            "AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id=" + str(uid)
            + ' AND b.blocked_id=s.user_id)')
    if spec['kind'] == 'forum_author_count':
        forums = select_rows(site, 'SELECT id,name FROM forums WHERE name=' + _quoted(spec['forum']))
        if len(forums) != 1: raise ValueError('One exact native forum required')
        rows = select_rows(site, base + ' AND f.name=' + _quoted(spec['forum']) + ' ORDER BY s.id')
        return {'version':VERSION, 'viewer':users[0], 'scope':deepcopy(spec),
                'submissions':rows, 'entries':[], 'comments':{}}
    native = search_reference(site, spec['query'])
    scoped = []
    for kind, table in (('submission','submissions'), ('comment','comments')):
        ids = [r['id'] for r in native if r['kind'] == kind]
        if not ids: continue
        if any(type(i) is not int or i <= 0 for i in ids):
            raise ValueError('Exact native search IDs required')
        join = ('JOIN forums f ON f.id=e.forum_id' if kind == 'submission' else
                'JOIN submissions s ON s.id=e.submission_id JOIN forums f ON f.id=s.forum_id')
        scoped += select_rows(site, "SELECT '" + kind + "' AS kind,e.id,f.name AS forum,e.visibility FROM "
                              + table + ' e ' + join + ' WHERE e.id IN ('
                              + ','.join(map(str, ids)) + ') ORDER BY e.id')
    if {(r['kind'],r['id']) for r in native} != {(r['kind'],r['id']) for r in scoped}:
        raise ValueError('Every native search relation must have an independent forum identity')
    ids = [r['id'] for r in native if r['kind'] == 'submission']
    rows = select_rows(site, base + ' AND s.id IN (' + ','.join(map(str, ids))
                       + ') ORDER BY s.id') if ids else []
    comments = {}
    if spec['kind'] == 'search_top_comments' and rows:
        highest = max(r['net_score'] for r in rows)
        for row in rows:
            if row['net_score'] == highest:
                comments[str(row['id'])] = select_rows(site,
                    "SELECT c.id,c.submission_id,c.body,c.visibility FROM comments c WHERE c.visibility='visible' "
                    'AND c.submission_id=' + str(row['id'])
                    + ' AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id=' + str(uid)
                    + ' AND b.blocked_id=c.user_id) ORDER BY c.id')
    return {'version':VERSION, 'viewer':users[0], 'scope':deepcopy(spec),
            'submissions':rows, 'entries':scoped, 'comments':comments}


def maxima(ref):
    kind = ref['scope']['kind']
    if kind == 'forum_author_count':
        counts = Counter(r['username'] for r in ref['submissions'])
    elif kind == 'search_forum_count':
        counts = Counter(r['forum'] for r in ref['entries'])
    elif kind == 'search_top_comments':
        counts = {r['id']:r['net_score'] for r in ref['submissions']}
    else: raise ValueError('Unknown native maximum family')
    if not counts: return set()
    target = max(counts.values())
    return {name for name, count in counts.items() if count == target}


def capability(ref):
    """No private all-results oracle can make the public 50-result cap vanish."""
    kind = ref['scope']['kind']
    checks = {'nonempty_comparison_scope':bool(maxima(ref)),
              'native_search_scope_complete':kind == 'forum_author_count' or len(ref['entries']) <= 50,
              'native_search_records_visible':kind == 'forum_author_count' or all(r['visibility']=='visible' for r in ref['entries'])}
    if kind == 'search_top_comments':
        checks['native_search_post_scope_visible'] = (
            {r['id'] for r in ref['entries'] if r['kind']=='submission'}
            == {r['id'] for r in ref['submissions']})
        checks['native_exact_score_reference'] = all(type(r['net_score']) is int for r in ref['submissions'])
    return checks


def local_path(value, origin):
    p, o = urlsplit(value), urlsplit(origin)
    if (p.scheme,p.netloc) != (o.scheme,o.netloc) or p.username or p.password:
        raise ValueError('Observed records must belong to the same local website')
    return p.path


def public_identity(row, origin):
    if (not isinstance(row, dict) or row.get('visible') is not True
            or row.get('kind') not in ('submission','comment')
            or not isinstance(row.get('label'), str) or not row['label'].strip()
            or not isinstance(row.get('links'), list)):
        raise ValueError('Actual visible native record required')
    ids = set()
    links=row['links']
    if row['kind']=='comment' and 'permalink' in row:
        permalink=row['permalink']
        if not isinstance(permalink,str) or permalink not in links:
            raise ValueError('One actual visible native comment permalink required')
        links=[permalink]
    for link in links:
        try: path = local_path(link, origin)
        except (ValueError, TypeError): continue  # external title links are data
        pattern = (r'/f/[^/]+/[1-9][0-9]*/-/comment/([1-9][0-9]*)' if row['kind']=='comment'
                   else r'/f/[^/]+/([1-9][0-9]*)(?:/[^/]*)?')
        match = re.fullmatch(pattern, path)
        if match: ids.add(int(match[1]))
    if len(ids) != 1: raise ValueError('One native public permalink identity required')
    return row['kind'], next(iter(ids))


def observed_keys(snapshots, origin, ref):
    """Only real request AX, after budgeting, exposes a record to the actor."""
    seen = set()
    for snap in snapshots:
        if snap.get('record_source') != 'actual_actor_request': continue
        ax = snap.get('issued_ax'); records = snap.get('entries')
        if not isinstance(ax, str) or not isinstance(records, list):
            raise ValueError('Bound issued native observation required')
        from .reddit_issued_record import record_exposure
        path = local_path(snap['url'], origin)
        spec = ref['scope']; kind = spec['kind']
        search = parse_qs(urlsplit(snap['url']).query, keep_blank_values=True)
        listing = (kind == 'forum_author_count' and re.fullmatch(
            '/f/' + re.escape(spec['forum']) + r'(?:/(?:hot|new|top|most_commented))?/?', path)
            and search.get('t', ['all']) == ['all'])
        search_scope = (kind != 'forum_author_count' and path == '/search'
            and len(search.get('q', [])) == 1
            and normalized_query(search['q'][0]) == normalized_query(spec['query']))
        selected = re.fullmatch(r'/f/[^/]+/([1-9][0-9]*)(?:/[^/]*)?/?', path)
        comments_scope = (kind == 'search_top_comments' and selected
            and int(selected[1]) in maxima(ref))
        if not (listing or search_scope or comments_scope): continue
        for row in records:
            exposed = record_exposure(row, ax)
            if row.get('visible') is True and exposed is not None:
                key = public_identity(row, origin)
                if comments_scope and key[0] != 'comment': continue
                if kind == 'forum_author_count':
                    # A title alone does not expose who authored it.
                    if not row.get('username') or row['username'] not in exposed: continue
                if kind == 'search_top_comments' and key[0] == 'submission':
                    score=row.get('score')
                    if not isinstance(score,str):continue
                    # Postmill renders negative vote totals with U+2212.
                    score=score.replace('\u2212','-')
                    if not re.fullmatch(r'-?[0-9]+',score):continue
                    if not re.search(r'(?<![0-9])'+re.escape(score)+r'(?![0-9])',exposed.replace('\u2212','-')):continue
                seen.add(key)
    return seen


def evaluate(contract, ref, snapshots, terminal, answer, *, origin, runtime_error=None):
    enabled(contract)
    if runtime_error or ref.get('scope') != contract['reddit_maximum_query']:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{}}
    limits = capability(ref)
    if not all(limits.values()):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':limits,
                'reason':'The complete comparison scope is not publicly available.'}
    kind = ref['scope']['kind']; seen = observed_keys(snapshots, origin, ref)
    checks = {'valid_terminal_page':terminal.get('error_page') is False
              and terminal.get('login_page') is False
              and type(terminal.get('http_status')) is int and 200 <= terminal['http_status'] < 400}
    try: local_path(terminal['url'], origin)
    except (ValueError,KeyError): checks['valid_terminal_page'] = False
    required = ({('submission',r['id']) for r in ref['submissions']} if kind=='forum_author_count'
                else {(r['kind'],r['id']) for r in ref['entries']})
    checks['complete_comparison_scope_observed'] = required <= seen
    if kind in ('forum_author_count','search_forum_count'):
        field = fields(contract)[0]
        try: parsed = json.loads(answer) if isinstance(answer,str) else answer
        except ValueError: parsed = None
        checks['typed_answer_schema'] = isinstance(parsed,dict) and set(parsed)=={field} and isinstance(parsed[field],str)
        checks['maximum_answer'] = bool(checks['typed_answer_schema'] and parsed[field] in maxima(ref))
    else:
        path = urlsplit(terminal.get('url','')).path
        match = re.fullmatch(r'/f/[^/]+/([1-9][0-9]*)(?:/[^/]*)?/?', path)
        selected = int(match[1]) if match else None
        checks['maximum_post_open'] = selected in maxima(ref)
        comments = ref['comments'].get(str(selected), [])
        checks['all_target_comments_observed'] = (checks['maximum_post_open']
            and {('comment',r['id']) for r in comments} <= seen)
    success = all(checks.values())
    return {'version':VERSION,'status':'success' if success else 'failure',
            'reward':1.0 if success else 0.0,'checks':checks}


def feedback(judgment):
    return {'version':VERSION,'status':judgment['status'],'reward':judgment['reward'],
            'checks':{k:v for k,v in judgment['checks'].items() if type(v) is bool},
            'private_reference_values_provided':False,'action_sequence_provided':False}
