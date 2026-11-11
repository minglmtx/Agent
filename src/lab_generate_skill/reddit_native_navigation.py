"""Native Reddit description bodies and accessibility-region navigation.

References are private completion data. Reading never changes the page; trusted
activation events record what the actor actually did. A heading cannot stand in
for a description, and a fragment alone cannot establish a native skip action.
"""
import re
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlsplit

VERSION = 'reddit-native-navigation-v1'

READ = r'''selector => {
 const visible=e=>{if(!e||!e.getClientRects().length)return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}return true;};
 const cards=[...document.querySelectorAll('#main article')].map(card=>({
  identity_links:[...card.querySelectorAll('h2 a[href]')].map(a=>({href:a.href,text:a.innerText.trim(),visible:visible(a)})),
  description_elements:[...card.querySelectorAll(selector)].map(e=>({tag:e.tagName,text:e.innerText.trim(),visible:visible(e),inside_heading:!!e.closest('h1,h2,h3,h4,h5,h6,header')}))
 }));
 const regions=['main','sidebar'].map(id=>{
  const es=[...document.querySelectorAll('[id="'+id+'"]')],e=es.length===1?es[0]:null,r=e?.getBoundingClientRect();
  return {id,count:es.length,present:!!e,tag:e?.tagName||null,visible:visible(e),
   in_viewport:!!r&&r.width>0&&r.height>0&&r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth,
   text:e?.innerText||''};
 });
 return {capture_version:'reddit-native-navigation-v1',url:location.href,title:document.title,cards,regions};
}'''


def norm(value):
    if not isinstance(value, str):
        raise ValueError('Native text must be a string')
    return ' '.join(value.split())


def local_path(value):
    if not isinstance(value, str) or not value.startswith('/'):
        raise ValueError('Explicit local path required')
    parsed = urlsplit(value)
    decoded = unquote(parsed.path)
    if (parsed.scheme or parsed.netloc or decoded.startswith('//') or '\\' in decoded
            or any(p in ('.', '..') for p in decoded.split('/'))):
        raise ValueError('Unsafe local reference path')
    return parsed


def validate(spec):
    if not isinstance(spec, dict):
        raise ValueError('Explicit native navigation specification required')
    if spec.get('kind') == 'forum_description':
        if set(spec) != {'kind', 'forum_id', 'name', 'description', 'description_selector'}:
            raise ValueError('Incomplete native forum description reference')
        if type(spec['forum_id']) is not int or spec['forum_id'] <= 0:
            raise ValueError('Native forum identifier must be a positive integer')
        if not norm(spec['name']) or '/' in spec['name'] or not norm(spec['description']):
            raise ValueError('Native forum identity and description must be nonempty')
        if not isinstance(spec['description_selector'], str) or not re.fullmatch(
                r'(?:[a-z]+(?:\.[A-Za-z_][A-Za-z0-9_-]*)*(?: > )?)*(?:p|div)(?:\.[A-Za-z_][A-Za-z0-9_-]*)*',
                spec['description_selector']):
            raise ValueError('Native description body selector required')
    elif spec.get('kind') in ('skip_region', 'region_destination'):
        if set(spec) != {'kind', 'target', 'initial_path'} or spec['target'] not in ('main', 'sidebar'):
            raise ValueError('Explicit native accessibility region required')
        local_path(spec['initial_path'])
    else:
        raise ValueError('Unsupported native Reddit navigation kind')


class DescriptionTemplate(HTMLParser):
    """Recover the body selector from the shipped native forum-card template."""
    def __init__(self):
        super().__init__(); self.stack = []; self.selectors = []

    def handle_starttag(self, tag, attrs):
        self.stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack = self.stack[:i]; break

    def handle_data(self, data):
        if not re.search(r'\bforum\.description\b', data):
            return
        if (not self.stack or self.stack[-1][0] not in ('p', 'div')
                or any(tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header') for tag, _ in self.stack)):
            raise ValueError('Native description must be a dedicated body element')
        parts = []
        for tag, attrs in reversed(self.stack):
            classes = attrs.get('class', '').split()
            if classes and all(re.fullmatch('[A-Za-z_][A-Za-z0-9_-]*', c) for c in classes):
                parts.insert(0, tag+''.join('.'+c for c in classes)); break
            parts.insert(0, tag)
        else:
            raise ValueError('Native description source lacks a stable body scope')
        self.selectors.append(' > '.join(parts))


def description_selector(source):
    if not isinstance(source, str):
        raise ValueError('Native template source must be text')
    parser = DescriptionTemplate(); parser.feed(source)
    if len(parser.selectors) != 1:
        raise ValueError('Native description field missing or ambiguous')
    return parser.selectors[0]


def read_state(page, selector='p.break-text'):
    return page.evaluate(READ, selector)


def _state(state):
    if (not isinstance(state, dict) or state.get('capture_version') != VERSION
            or not isinstance(state.get('url'), str) or not isinstance(state.get('title'), str)
            or not isinstance(state.get('cards'), list) or not isinstance(state.get('regions'), list)):
        raise ValueError('Missing or malformed native navigation capture')


def _origin(site_origin):
    origin = urlsplit(site_origin)
    if (origin.scheme not in ('http', 'https') or not origin.netloc or origin.path not in ('', '/')
            or origin.query or origin.fragment):
        raise ValueError('Explicit local website origin required')
    return origin


def _description_checks(spec, state, origin):
    target = '/f/'+quote(spec['name'], safe=''); matching = []
    for card in state['cards']:
        if not isinstance(card, dict) or not isinstance(card.get('identity_links'), list) or not isinstance(card.get('description_elements'), list):
            raise ValueError('Malformed native description card')
        links = card['identity_links']
        for link in links:
            if (not isinstance(link, dict) or not isinstance(link.get('href'), str)
                    or not isinstance(link.get('text'), str) or type(link.get('visible')) is not bool):
                raise ValueError('Malformed native forum identity link')
        fields = card['description_elements']
        for field in fields:
            if (not isinstance(field, dict) or not isinstance(field.get('tag'), str)
                    or not isinstance(field.get('text'), str) or type(field.get('visible')) is not bool
                    or type(field.get('inside_heading')) is not bool):
                raise ValueError('Malformed native description field')
        if len(links) == 1:
            u = urlsplit(links[0]['href'])
            if ((u.scheme, u.netloc) == (origin.scheme, origin.netloc) and u.path == target
                    and not u.query and not u.fragment and links[0]['visible']):
                matching.append(card)
    fields = matching[0]['description_elements'] if len(matching) == 1 else []
    exact = (len(fields) == 1 and fields[0]['tag'] in ('P', 'DIV')
             and fields[0]['inside_heading'] is False and fields[0]['visible']
             and norm(fields[0]['text']) == norm(spec['description']))
    return {'reddit_description_correct_card': len(matching) == 1,
            'reddit_description_dedicated_body': len(fields) == 1,
            'reddit_description_visible_and_complete': bool(exact)}


def _region(state, target):
    rows = []
    for region in state['regions']:
        if (not isinstance(region, dict) or region.get('id') not in ('main', 'sidebar')
                or type(region.get('count')) is not int or region['count'] < 0
                or type(region.get('present')) is not bool or type(region.get('visible')) is not bool
                or type(region.get('in_viewport')) is not bool or not isinstance(region.get('text'), str)
                or region.get('tag') not in (None, 'MAIN', 'ASIDE')):
            raise ValueError('Malformed native accessibility region')
        if region['id'] == target:
            rows.append(region)
    if len(rows) != 1:
        raise ValueError('Accessibility region capture missing or duplicated')
    return rows[0]


def _jump_checks(spec, state, origin, baseline, evidence):
    _state(baseline); target = spec['target']; row = _region(state, target); before = _region(baseline, target)
    start = local_path(spec['initial_path']); current = urlsplit(state['url']); initial = urlsplit(baseline['url'])
    original = (origin.scheme, origin.netloc, start.path, start.query)
    if (initial.scheme, initial.netloc, initial.path, initial.query) != original:
        raise ValueError('Initial region capture differs from the original task start')
    destination = {
        'reddit_jump_original_page': (current.scheme, current.netloc, current.path, current.query) == original and state['title'] == baseline['title'],
        'reddit_jump_target_fragment': current.fragment == target,
        'reddit_jump_native_region_exists': row['count'] == before['count'] == 1 and row['present'] and before['present'] and row['tag'] == before['tag'] == ('MAIN' if target == 'main' else 'ASIDE'),
        'reddit_jump_target_visible': row['visible'] and row['in_viewport'],
        'reddit_jump_target_content_preserved': bool(norm(before['text'])) and norm(row['text']) == norm(before['text']),
    }
    if spec['kind'] == 'region_destination':
        # A declared destination task checks the resulting page/region. Browser
        # fragment navigation and keyboard activation are equally valid; neither
        # an arbitrary fragment nor a URL string without native content suffices.
        return destination
    if (not isinstance(evidence, dict) or evidence.get('version') != 'trusted-native-link-v1'
            or type(evidence.get('overflow')) is not bool or not isinstance(evidence.get('events'), list)):
        raise ValueError('Native link activation capture missing')
    if evidence['overflow']:
        raise ValueError('Native link activation capture overflow')
    activated = False
    for event in evidence['events']:
        if (not isinstance(event, dict) or not isinstance(event.get('source_url'), str)
                or not isinstance(event.get('href'), str) or event.get('tag') != 'a'
                or type(event.get('trusted')) is not bool or not isinstance(event.get('classes'), list)
                or any(not isinstance(c, str) for c in event['classes'])
                or not isinstance(event.get('ancestors'), list)):
            raise ValueError('Malformed native activation event')
        for ancestor in event['ancestors']:
            if (not isinstance(ancestor, dict) or not isinstance(ancestor.get('classes'), list)
                    or any(not isinstance(c, str) for c in ancestor['classes'])):
                raise ValueError('Malformed native activation context')
        source = urlsplit(event['source_url']); dest = urlsplit(event['href'])
        activated = activated or (event['trusted'] and 'site-accessibility-nav__link' in event['classes']
            and any('site-accessibility-nav' in a['classes'] for a in event['ancestors'])
            and (source.scheme, source.netloc, source.path, source.query) == original
            and (dest.scheme, dest.netloc, dest.path, dest.query, dest.fragment) == (*original, target))
    return destination | {'reddit_jump_native_activation': bool(activated)}


def checks(spec, state, *, site_origin, baseline=None, navigation_clicks=None):
    validate(spec); _state(state); origin = _origin(site_origin)
    if spec['kind'] == 'forum_description':
        return _description_checks(spec, state, origin)
    return _jump_checks(spec, state, origin, baseline, navigation_clicks)


def verify_reference(site, spec):
    """Recheck private native identities/template; never copy them into a prompt."""
    validate(spec)
    if site.domain != 'reddit':
        raise ValueError('Native Reddit reference requires the Reddit site')
    if spec['kind'] in ('skip_region', 'region_destination'):
        # Actual original region identity/content is independently captured from
        # the initial public document, rather than predicted from the task text.
        return {'kind': spec['kind'], 'initial_path': spec['initial_path'], 'target': spec['target']}
    from .site_database import select_rows
    rows = select_rows(site, 'SELECT id,name,description FROM forums WHERE id='+str(spec['forum_id']))
    if rows != [{'id': spec['forum_id'], 'name': spec['name'], 'description': spec['description']}]:
        raise ValueError('Native forum description reference changed')
    source = site.command(['cat', '/var/www/html/templates/_layouts/forum_card.html.twig'], capture_output=True, text=True, timeout=30).stdout
    if description_selector(source) != spec['description_selector']:
        raise ValueError('Native dedicated description template changed')
    return rows[0]


def keyboard_control(page, target, max_tabs=40):
    """Private CPU positive control: real native activation, not actor policy."""
    if target not in ('main', 'sidebar'):
        raise ValueError('Unsupported native region')
    link = page.locator('nav.site-accessibility-nav a.site-accessibility-nav__link[href="#'+target+'"]')
    if link.count() != 1:
        raise ValueError('Native accessibility link missing or ambiguous')
    for count in range(max_tabs+1):
        if link.evaluate('(e)=>document.activeElement===e'):
            page.keyboard.press('Enter'); return {'tabs': count, 'activation': 'native_keyboard_enter'}
        page.keyboard.press('Tab')
    raise ValueError('Native accessibility link not keyboard reachable')


FEEDBACK = {
 'reddit_description_correct_card': 'The displayed description belongs to the requested forum.',
 'reddit_description_dedicated_body': 'The native description body is displayed separately from its heading.',
 'reddit_description_visible_and_complete': 'The complete requested forum description is visible.',
 'reddit_jump_original_page': 'The original task page is preserved.',
 'reddit_jump_native_activation': 'The native accessibility control for the requested region was activated.',
 'reddit_jump_target_fragment': 'The requested region is the current navigation target.',
 'reddit_jump_native_region_exists': 'The requested native content region exists on the original page.',
 'reddit_jump_target_visible': 'The requested content region is visible in the viewport.',
 'reddit_jump_target_content_preserved': 'The original content of the requested region is preserved.',
}


def required_negatives(spec):
    validate(spec)
    if spec['kind'] == 'region_destination':
        return ('wrong_region', 'hidden_region', 'incomplete_region', 'url_only')
    return (('missing_description','hidden_description','wrong_description','heading_only','url_only')
            if spec['kind']=='forum_description' else
            ('hash_only','wrong_region','hidden_region','incomplete_region','url_only'))


def initial_fingerprint(state):
    """Stable public reset identity; exclude origin and focus/viewport positions."""
    import hashlib,json
    _state(state)
    u=urlsplit(state['url'])
    regions=[]
    for target in ('main','sidebar'):
        row=_region(state,target)
        regions.append({k:row[k] for k in ('id','count','present','tag')}|{'text':norm(row['text'])})
    value={'path':u.path,'query':u.query,'title':state['title'],'regions':regions}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
