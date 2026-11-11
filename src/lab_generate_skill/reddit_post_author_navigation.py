"""Passive native post-to-author association; no task-specific action policy.

The public click identifies a post and author. Independent native records bind
that association. Neither a copied profile URL nor a footer/user-menu link is
evidence that the agent navigated from a post. References remain private.
"""
import re
from urllib.parse import quote, unquote, urlsplit

VERSION = 'reddit-native-post-author-navigation-draft-v1'
MAX_EVENTS = 128

PASSIVE = r'''(() => {
 const visible=e=>{if(!e||!e.isConnected||!e.getClientRects().length)return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}return true;};
  // Native SearchRepository wraps whole native headline tokens in MARK;
  // the installed Twig spaceless filter removes intervening whitespace between
  // adjacent MARK tags. Restore only this native token boundary, never a
  // boundary between arbitrary inline nodes or a substring within one word.
  const publicTitle=e=>{
   const raw={post_title_raw_html:e?.innerHTML||'',post_title_text_content:e?.textContent||'',
              post_title_inner_text:e?.innerText||'',post_title_restored_mark_boundaries:0,
              post_title_semantic_origin:'native_rendered_inner_text'};
   const links=e?[...e.children].filter(n=>n.matches('a.submission__link')):[];
   if(location.pathname!=='/search'||!visible(e)||links.length!==1||!visible(links[0]))
    return {...raw,post_title:raw.post_title_inner_text.trim()};
   const a=links[0];
   // Actual native title content is text, escaped text, optional thumbnail IMG,
   // and flat search MARKs. Non-native markup has no inferred token boundary.
   if([...a.children].some(n=>!n.matches('mark,img.submission__thumb')||
       (n.matches('mark')&&n.children.length)))
    return {...raw,post_title:raw.post_title_inner_text.trim()};
   let output='',previous=null,count=0;
   for(const node of a.childNodes){
    if(node.nodeType===Node.TEXT_NODE){output+=node.nodeValue;if(node.nodeValue.length)previous=null;continue;}
    if(node.nodeType!==Node.ELEMENT_NODE||!visible(node)){previous=null;continue;}
    if(node.matches('img.submission__thumb')){previous=null;continue;}
    const value=node.textContent||'';
    if(node.matches('mark')&&previous?.matches('mark')&&output&&!/\s$/.test(output)&&value&&!/^\s/.test(value)){
     output+=' ';count++;
    }
    output+=value;previous=node;
   }
   return {...raw,post_title:output.trim(),post_title_restored_mark_boundaries:count,
           post_title_semantic_origin:'native_search_headline_tokens'};
  };
 document.addEventListener('click',event=>{
  const a=event.target.closest('a.submission__submitter[href]');
  const post=a?.closest('article.submission');if(!a||!post)return;
  const title=post.querySelector('h1.submission__title');
  const permalinks=[...post.querySelectorAll('nav.submission__nav a[href]')].map(e=>e.href);
  window.__labPostAuthorNavigation({version:'reddit-native-post-author-navigation-draft-v1',trusted:event.isTrusted,
   source_url:location.href,href:a.href,author_name:a.innerText.trim(),
   author_visible:visible(a),post_visible:visible(post),...publicTitle(title),
   native_post_permalinks:permalinks});
 },true);
})();'''

READ_PROFILE = r'''() => {
 const visible=e=>{if(!e||!e.isConnected||!e.getClientRects().length)return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}return true;};
 return {version:'reddit-native-post-author-navigation-draft-v1',url:location.href,title:document.title,
  profile_headings:[...document.querySelectorAll('#sidebar section > header h1.sidebar__title a[href]')].map(a=>({href:a.href,text:a.innerText.trim(),visible:visible(a)}))};
}'''


def origin(value):
    p = urlsplit(value)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username is not None
            or p.password is not None or p.path not in ('', '/') or p.query or p.fragment):
        raise ValueError('Trusted actual site factory origin required')
    p.port
    return p.scheme, p.netloc


def text(value):
    if not isinstance(value, str):
        raise ValueError('Native public text must be a string')
    return ' '.join(value.split())


def native_path(url, site_origin):
    p = urlsplit(url)
    if ((p.scheme, p.netloc) != origin(site_origin) or p.username is not None
            or p.password is not None or p.query or p.fragment):
        raise ValueError('Exact local native identity URL required')
    path = unquote(p.path)
    if (path.startswith('//') or '\\' in path or any(part in ('.', '..') for part in path.split('/'))):
        raise ValueError('Unsafe native identity path')
    return path


def observed_association(event, *, site_origin):
    if (not isinstance(event, dict) or event.get('version') != VERSION
            or type(event.get('trusted')) is not bool
            or type(event.get('author_visible')) is not bool
            or type(event.get('post_visible')) is not bool
            or not isinstance(event.get('native_post_permalinks'), list)):
        raise ValueError('Complete native post-author public event required')
    source = urlsplit(event['source_url'])
    if ((source.scheme, source.netloc) != origin(site_origin)
            or source.username is not None or source.password is not None):
        raise ValueError('Native post event originates outside this site')
    name = text(event['author_name'])
    path = native_path(event['href'], site_origin)
    if not name or '/' in name or path != '/user/' + name:
        raise ValueError('Public author text and native profile URL disagree')
    identities = set()
    for href in event['native_post_permalinks']:
        if not isinstance(href, str):
            raise ValueError('Public native permalink must be a URL string')
        try:
            part = native_path(href, site_origin)
        except ValueError:
            continue
        match = re.fullmatch(r'/f/([^/]+)/([1-9][0-9]*)(?:/[^/]+)?', part)
        if match:
            identities.add((match[1], int(match[2])))
    if len(identities) != 1:
        raise ValueError('One unambiguous native post identity required')
    forum_name, post_id = next(iter(identities))
    return {'post_id': post_id, 'forum_name': forum_name, 'author_name': name,
            'post_title': text(event['post_title']), 'trusted': event['trusted'],
            'public_post_visible': event['post_visible'], 'public_author_visible': event['author_visible'],
            'profile_path': path}


def verify_reference(site, event):
    """Private DB binding to observed post, never an invented user ID from URL."""
    from lab_generate_skill.site_database import select_rows
    if site.domain != 'reddit':
        raise ValueError('Native Reddit factory required')
    observed = observed_association(event, site_origin=site.url)
    rows = select_rows(site, 'SELECT s.id AS post_id,s.title AS post_title,f.name AS forum_name,'
                       'u.id AS author_id,u.username AS author_name FROM submissions s '
                       'JOIN forums f ON f.id=s.forum_id JOIN users u ON u.id=s.user_id '
                       'WHERE s.id=' + str(observed['post_id']))
    if len(rows) != 1:
        raise ValueError('Actual observed native post identity missing')
    return rows[0]


def checks(event, terminal, reference, *, site_origin):
    observed = observed_association(event, site_origin=site_origin)
    if (not isinstance(reference, dict)
            or set(reference) != {'post_id', 'post_title', 'forum_name', 'author_id', 'author_name'}
            or type(reference['post_id']) is not int or reference['post_id'] <= 0
            or type(reference['author_id']) is not int or reference['author_id'] <= 0):
        raise ValueError('Complete independently bound native post-author reference required')
    for key in ('post_title', 'forum_name', 'author_name'):
        if not text(reference[key]):
            raise ValueError('Complete native identity text required')
    if (not isinstance(terminal, dict) or terminal.get('version') != VERSION
            or type(terminal.get('http_status')) is not int
            or not isinstance(terminal.get('profile_headings'), list)
            or type(terminal.get('login_page')) is not bool
            or type(terminal.get('error_page')) is not bool):
        raise ValueError('Actual terminal profile document required')
    try:
        profile_path = native_path(terminal['url'], site_origin)
    except ValueError:
        profile_path = None
    target_path = '/user/' + reference['author_name']
    headings = terminal['profile_headings']
    valid_headings = []
    for heading in headings:
        if (not isinstance(heading, dict) or set(heading) != {'href', 'text', 'visible'}
                or type(heading['visible']) is not bool or not isinstance(heading['href'], str)):
            raise ValueError('Complete native profile heading/link required')
        label = text(heading['text'])
        try:
            path = native_path(heading['href'], site_origin)
        except ValueError:
            path = None
        if path == target_path and label == text(reference['author_name']) and heading['visible']:
            valid_headings.append(heading)
    return {
        'native_trusted_author_link_from_post': observed['trusted'] and observed['public_post_visible'] and observed['public_author_visible'],
        'native_public_post_and_author_match': (observed['post_id'] == reference['post_id']
                                               and all(observed[k] == text(reference[k]) for k in
                                                       ('forum_name', 'author_name', 'post_title'))),
        'native_terminal_author_profile': profile_path == target_path,
        'native_profile_identity_visible': len(headings) == len(valid_headings) == 1,
        'native_terminal_document_valid': 200 <= terminal['http_status'] < 300
                                         and terminal['login_page'] is False and terminal['error_page'] is False,
    }


def feedback(result):
    labels = {
        'native_trusted_author_link_from_post': 'A visible native post author link was activated.',
        'native_public_post_and_author_match': 'The post and author identities agree with native records.',
        'native_terminal_author_profile': 'The terminal page is the author profile reached from the post.',
        'native_profile_identity_visible': 'The author profile identity is visibly displayed.',
        'native_terminal_document_valid': 'The final local document is valid.',
    }
    if set(result) != set(labels) or any(type(value) is not bool for value in result.values()):
        raise ValueError('Complete boolean result checks required')
    return {'checks': [{'name': k, 'passed': result[k], 'description': labels[k]} for k in labels],
            'private_reference_values_provided': False, 'action_sequence_provided': False}


class PassivePostAuthorCapture:
    """Source-local public event recorder; no reference reads or browser actions."""
    def __init__(self, site_origin):
        origin(site_origin)
        self.site_origin = site_origin
        self.context = None
        self.events = []
        self.overflow = False
        self.capture_errors = []

    def attach(self, context):
        if self.context is not None:
            raise ValueError('One source-local post-author collector context required')
        self.context = context
        context.expose_binding('__labPostAuthorNavigation', self._record)
        context.add_init_script(PASSIVE)

    def _record(self, source, event):
        from copy import deepcopy
        page = source.get('page') if isinstance(source, dict) else None
        if page is None or page.context is not self.context:
            self.capture_errors.append('wrong_native_browser_context')
            return
        main_frame = getattr(page, 'main_frame', None)
        if main_frame is None or source.get('frame') is not main_frame:
            self.capture_errors.append('wrong_native_main_document')
            return
        try:
            observed_association(event, site_origin=self.site_origin)
        except (ValueError, TypeError, KeyError):
            self.capture_errors.append('malformed_public_native_association')
            return
        if len(self.events) == MAX_EVENTS:
            self.overflow = True
            return
        self.events.append(deepcopy(event))

    def clear(self):
        self.events.clear()
        self.overflow = False
        self.capture_errors.clear()

    def read(self):
        from copy import deepcopy
        if self.context is None:
            raise ValueError('Public native collector was not initialized')
        return {'version': VERSION, 'events': deepcopy(self.events),
                'overflow': self.overflow, 'capture_errors': list(self.capture_errors)}


def capture_checks(capture, terminal, references, *, site_origin):
    """Zero observed actions is a known no-op; absent/broken capture is unknown.

    Multiple trials are allowed. A correctly reached current profile is compared
    with the actual native post event which led to it. Earlier wrong attempts
    are retained without becoming permanent failures when a later trial works.
    """
    if (not isinstance(capture, dict) or set(capture) != {'version', 'events', 'overflow', 'capture_errors'}
            or capture['version'] != VERSION or not isinstance(capture['events'], list)
            or type(capture['overflow']) is not bool or not isinstance(capture['capture_errors'], list)
            or capture['overflow'] or capture['capture_errors'] or len(capture['events']) > MAX_EVENTS
            or not isinstance(references, dict)):
        raise ValueError('Complete initialized native event capture/reference collection required')
    if not capture['events']:
        if references:
            raise ValueError('No-op capture cannot borrow another event reference')
        return {name: False for name in ('native_trusted_author_link_from_post',
                                        'native_public_post_and_author_match', 'native_terminal_author_profile',
                                        'native_profile_identity_visible', 'native_terminal_document_valid')}
    results = []
    for event in capture['events']:
        observed = observed_association(event, site_origin=site_origin)
        if observed['post_id'] not in references:
            raise ValueError('Every observed post needs its independent native reference')
        results.append(checks(event, terminal, references[observed['post_id']], site_origin=site_origin))
    return next((row for row in reversed(results) if all(row.values())), results[-1])
