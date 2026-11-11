"""Native Postmill plain-text search, with private SQL rank/membership checks.

The snapshot SearchRepository only accepts q. It merges the top 50 comments and
top 50 submissions, sorts by ts_rank and returns 50. Equal-rank ordering is not
specified by SQL, so ties must not be treated as an actor failure.
"""
import re,html
from urllib.parse import parse_qs,urlsplit
from .site_database import select_rows

def normalized_query(text):return ' '.join(text.split()).casefold()

def rendered_search_title(highlighted):
    # Native FormattingExtension escapes the headline then replaces b with mark;
    # Twig's whitespace control removes whitespace between adjacent mark tags.
    # Preserve this actual UI text, rather than loosening general string checks.
    escaped=html.escape(highlighted)
    marked=re.sub(r'&lt;b&gt;(.*?)&lt;/b&gt;',r'<mark>\1</mark>',escaped)
    compact=re.sub(r'>\s+<','><',marked)
    return ' '.join(html.unescape(re.sub(r'</?mark>','',compact)).split())

def search_reference(site,query):
    if site.domain!='reddit' or not isinstance(query,str) or not query.strip() or len(query)>300:raise ValueError('Explicit short search query required')
    quoted="'"+query.replace("'","''")+"'"
    rows=[]
    # Read all qualifying identities to handle native arbitrary ties at rank 50.
    # These records stay private; neither query references nor scores enter AX.
    for kind,table in [('comment','comments'),('submission','submissions')]:
        fields="e.title,ts_headline(e.title,search_query,'HighlightAll=TRUE') AS highlighted_title" if kind=='submission' else 'NULL::text AS title,NULL::text AS highlighted_title'
        rows+=select_rows(site,f"SELECT '{kind}' AS kind,e.id,{fields},ts_rank(search_doc, search_query) AS rank FROM {table} e,plainto_tsquery({quoted}::TEXT) search_query WHERE search_doc @@ search_query ORDER BY rank DESC,e.id")
    return sorted(rows,key=lambda r:(-r['rank'],r['kind'],r['id']))

def verify_search_reference(site,spec):
    if search_reference(site,spec['query'])!=spec['reference']:raise ValueError('Native search reference changed')

def read_search_page(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const root=document.querySelector('#main');
      const articles=root?[...root.querySelectorAll('article.submission,article.comment')].filter(visible):[];
      return {query_inputs:[...document.querySelectorAll('#query')].filter(visible).map(e=>e.value),
        result_headings:root?[...root.querySelectorAll('h2')].filter(e=>visible(e)&&!e.closest('article')).map(e=>e.innerText.trim()):[],
        entries:articles.map(e=>({kind:e.classList.contains('submission')?'submission':'comment',
          id:e.classList.contains('submission')?e.querySelector('[data-vote-route-value="submission_vote"]')?.getAttribute('data-vote-id-value'):e.id.replace(/^comment_/,''),
          title:e.classList.contains('submission')?e.querySelector('.submission__title')?.innerText.trim():null,
          content_present:!!e.innerText.trim()})),
        empty_notice:root?root.innerText.includes("There's nothing here…"):false};
    }''')

def search_checks(spec,state,url):
    if not isinstance(state,dict) or any(not isinstance(state.get(k),list) for k in ('query_inputs','result_headings','entries')):raise ValueError('Missing native search capture')
    query=parse_qs(urlsplit(url).query,keep_blank_values=True);value=query.get('q',[])
    checks={'search_query_submitted':len(value)==1 and normalized_query(value[0])==normalized_query(spec['query']),
            'search_input_matches':len(state['query_inputs'])==1 and len(value)==1 and state['query_inputs'][0]==value[0]}
    if not all(checks.values()):return checks
    refs=spec['reference'];expected_count=min(50,len(refs));entries=state['entries']
    summary=(f'No results for {value[0]}' if expected_count==0 else f'1 result for {value[0]}:' if expected_count==1 else f'{expected_count} results for {value[0]}:')
    checks['search_result_summary']=state['result_headings']==[summary]
    keys=[(r.get('kind'),str(r.get('id'))) for r in entries]
    by_id={(r['kind'],str(r['id'])):r for r in refs}
    valid=all(k in by_id for k in keys)
    checks['search_result_identities']=valid and len(keys)==expected_count and len(set(keys))==len(keys)
    if valid:
        ranks=[by_id[k]['rank'] for k in keys]
        threshold=refs[expected_count-1]['rank'] if expected_count else None
        required={(r['kind'],str(r['id'])) for r in refs if threshold is not None and r['rank']>threshold}
        checks['search_native_ranking']=ranks==sorted(ranks,reverse=True) and required<=set(keys) and all(x>=threshold for x in ranks)
        checks['search_visible_content']=all(r.get('content_present') is True and (r['kind']!='submission' or r.get('title')==rendered_search_title(by_id[k]['highlighted_title'])) for r,k in zip(entries,keys))
    else:checks.update(search_native_ranking=False,search_visible_content=False)
    checks['search_content_or_empty_state']=bool(entries) if expected_count else state.get('empty_notice') is True
    if spec.get('require_submission'):
        checks['search_posts_displayed']=any(r.get('kind')=='submission' for r in entries)
    return checks

FEEDBACK={'search_query_submitted':'The requested search has been submitted.',
 'search_posts_displayed':'Matching posts are displayed, rather than only comments or an empty result.',
 'search_input_matches':'The visible query agrees with the submitted search.',
 'search_result_summary':'The native result summary agrees with the submitted search.',
 'search_result_identities':'The displayed results belong to the submitted search.',
 'search_native_ranking':'The results follow the website search ranking.',
 'search_visible_content':'The native result content is displayed.',
 'search_content_or_empty_state':'Search results or the verified empty-result state are displayed.'}
