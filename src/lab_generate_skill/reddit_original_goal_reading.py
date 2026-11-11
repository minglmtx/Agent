"""Native original Reddit reading, without actor navigation or private answers.

A lack of native category taxonomy is a scope/prerequisite failure. A directory
is not silently renamed a category taxonomy. Parent-comment writes require their
own exact native protection and are intentionally outside this reading module.
"""
from copy import deepcopy
import re
from urllib.parse import quote,urlsplit
from . import reddit_remaining_normal as public
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
VERSION='reddit-original-public-reading-v1'
KINDS={'native_category_taxonomy','native_forum_existence','native_wiki_directory','native_topic_post_view','native_forums_then_music'}

def quoted(value):
 if not isinstance(value,str):raise ValueError('Literal original task scope required')
 return "'"+value.replace("'","''")+"'"
def reference(site,c,username):
 spec=c['reddit_original_reading'];kind=spec['kind']
 if kind not in KINDS or site.domain!='reddit':raise ValueError('Native original reading family required')
 accounts=select_rows(site,'SELECT id,username FROM users WHERE username='+quoted(username))
 if len(accounts)!=1:raise ValueError('One task native account required')
 result={'version':VERSION,'account':accounts[0],'kind':kind}
 if kind=='native_category_taxonomy':
  result['taxonomy']=select_rows(site,'SELECT id,name,normalized_name,description FROM forum_tags ORDER BY normalized_name,id')
  # This native site has no category taxonomy when its forum-tags relation is
  # empty. A list of forum titles cannot supply the missing concept.
  result['native_category_taxonomy_available']=bool(result['taxonomy'])
 elif kind=='native_forum_existence':
  result['forums']=select_rows(site,'SELECT id,name,title,description FROM forums ORDER BY id')
  term=spec['term'].casefold();result['eligible']=[r for r in result['forums']if term in r['name'].casefold()or term in r['title'].casefold()]
 elif kind=='native_topic_post_view':
  uid=accounts[0]['id']
  rows=select_rows(site,"SELECT s.id,s.title,s.visibility,f.name AS forum FROM submissions s JOIN forums f ON f.id=s.forum_id WHERE s.visibility='visible' AND f.name='movies' AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id="+str(uid)+" AND b.blocked_id=s.user_id) AND s.title ILIKE '%oscar%' ORDER BY s.id")
  # Literal topic predicate is independently defined before actor execution.
  # It does not select an ID from a published success trajectory.
  result['eligible']=[r for r in rows if re.search(r'\boscar\b',r['title'],re.I)and re.search(r'\b(?:nominations?|nominees?|nominated)\b',r['title'],re.I)]
 elif kind=='native_forums_then_music':
  rows=select_rows(site,"SELECT id,name,title,description FROM forums WHERE name='Music'")
  if len(rows)!=1:raise ValueError('Unique native Music forum missing')
  result['music']=rows[0]
 return result

def local_path(value,origin):
 u=urlsplit(value);o=urlsplit(origin)
 if(u.scheme,u.netloc)!=(o.scheme,o.netloc)or u.username is not None or u.password is not None:raise ValueError('Same actual native factory origin required')
 return u.path

def _valid(obs,origin):
 return isinstance(obs,dict)and valid_initial_page(obs.get('page'),site_origin=origin)and isinstance(obs.get('native'),dict)and obs['native'].get('url')==obs['page']['url']

def checks(c,observations,ref,*,site_origin,answer=None):
 spec=c['reddit_original_reading'];kind=spec['kind']
 if kind not in KINDS or ref.get('kind')!=kind or ref.get('version')!=VERSION:raise ValueError('Actual native private reference family differs')
 if not isinstance(observations,list)or not observations:raise ValueError('Actual issued observations required')
 for row in observations:
  if not isinstance(row,dict)or not isinstance(row.get('native'),dict)or row['native'].get('version')!=public.VERSION or row['native'].get('url')!=row.get('page',{}).get('url'):raise ValueError('Bound native issued observations differ')
 terminal=observations[-1];result={'terminal_native_document_valid':_valid(terminal,site_origin)}
 if not result['terminal_native_document_valid']:return result
 page,native=terminal['page'],terminal['native'];path=local_path(page['url'],site_origin)
 if kind=='native_wiki_directory':
  result['native_wiki_directory']=path=='/wiki/_all'and page.get('title')=='All pages'and native.get('main_headings')==['All pages']
 elif kind=='native_forum_existence':
  eligible={r['name']:r for r in ref['eligible']};name=path.removeprefix('/f/')if re.fullmatch(r'/f/[^/]+',path)else None
  result['native_technology_forum_witness']=name in eligible and page.get('title')==eligible[name]['title']and any('/f/'+name in h for h in native.get('main_headings',[]))
  # Typed existence output may be a boolean or {"exists": bool}, never a
  # fabricated negative inferred from a missing first-screen card.
  try:answer=__import__('json').loads(answer)if isinstance(answer,str)else answer
  except ValueError:pass
  result['correct_existence_answer']=answer is True or isinstance(answer,dict)and answer=={'exists':True}
 elif kind=='native_topic_post_view':
  matched=re.fullmatch(r'/f/([^/]+)/([1-9][0-9]*)(?:/[^/]+)?',path);rows={r['id']:r for r in ref['eligible']}
  ident=int(matched[2])if matched else None;target=rows.get(ident)
  result['native_qualifying_post_identity']=bool(target and matched[1]==target['forum'])
  posts=native.get('submissions',[])
  result['correct_native_post_title']=bool(target and len(posts)==1 and posts[0].get('ids')==[str(ident)]and public.norm(posts[0].get('title'))==public.norm(target['title']))
 elif kind=='native_forums_then_music':
  # The native Postmill directory uses "List of forums". Match the actual
  # main heading, not a case-sensitive substring in a menu or unrelated title.
  directory_titles={'forums','all forums','list of forums'}
  directories=[i for i,r in enumerate(observations)if _valid(r,site_origin)and local_path(r['page']['url'],site_origin)in('/forums','/forums/all')and any(public.norm(h).casefold()in directory_titles for h in r['native'].get('main_headings',[]))]
  music=[i for i,r in enumerate(observations)if _valid(r,site_origin)and local_path(r['page']['url'],site_origin)=='/f/Music'and '/f/Music'in r['native'].get('main_headings',[])]
  result['actual_forums_then_music_issued']=bool(directories and music and any(j>i for i in directories for j in music))
  result['terminal_music_context']=path=='/f/Music'and page.get('title')==ref['music']['title']
 else:
  if ref.get('native_category_taxonomy_available')is not True:raise ValueError('Native category taxonomy is unavailable; forum directory is not an equivalent substitute')
  # Native public tag-directory proof is intentionally required rather than
  # inventing a selector or result from unrelated forum-directory content.
  raise ValueError('Native taxonomy public listing lifecycle is not yet verified')
 return result

def evaluate(*args,**kwargs):
 try:result=checks(*args,**kwargs)
 except(ValueError,TypeError,KeyError)as exc:return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'diagnostic':str(exc),'private_values_provided':False}
 passed=all(result.values());return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':result,'private_values_provided':False}

def read(page,health):return public.read_page(page,health)
