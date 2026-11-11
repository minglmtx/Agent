"""Original visible parented-comment operations, with no semantic text judge.

The private initial parent set is resolved before actor inference. A submission
reply, a new post, or a reply to a later unrelated author match is not a parented
reply to the declared original context. No reference value enters feedback.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit, unquote

from lab_generate_skill.site_navigation_rules import valid_initial_page
from lab_generate_skill.source_revision_binding import binding, fingerprint as source_fingerprint
from lab_generate_skill.reddit_search import rendered_search_title

VERSION = 'reddit-parented-reply-public-v2'
ADMISSION_VERSION = 'reddit-parented-reply-public-two-cold-v2'
PROTECTION_VERSION = 'reddit-parented-reply-complete13-notifications-v2'
TABLES = ('forums','comments','submission_votes','comment_votes','wiki_pages',
          'wiki_revisions','forum_tags','forums_tags','hidden_forums',
          'forum_subscriptions','user_blocks','users','submissions')
KINDS = {'author_visible_parent', 'search_visible_parent'}


def validate_contract(c):
    binding(c)
    s=c.get('parented_reply')
    if (c.get('domain')!='reddit' or not isinstance(s,dict) or s.get('kind') not in KINDS
            or c.get('heldout_quarantine') is not False
            or c.get('eligible_for_training') is not False):
        raise ValueError('Explicit development-only public parented-reply source required')
    expected={'author_visible_parent':{'kind','author','reply_body'},
              'search_visible_parent':{'kind','query','reply_body'}}[s['kind']]
    if set(s)!=expected or any(not isinstance(s[k],str) or not s[k].strip() for k in expected-{'kind'}):
        raise ValueError('Declared public parent criterion and exact reply body required')
    # The two current public fixtures are plain text. Supporting mentions or
    # arbitrary Markdown requires an independently qualified native recipient
    # parser; do not silently omit those effects from supplemental protection.
    if len(s['reply_body'])>1000 or not re.fullmatch(r"[A-Za-z0-9 ,.!?'\-]+",s['reply_body']):
        raise ValueError('Declared plain public reply body required')
    required={'reply_body':s['reply_body']}
    required['parent_author' if s['kind']=='author_visible_parent' else 'matching_search_query']=s['author' if s['kind']=='author_visible_parent' else 'query']
    params=c.get('public_parameters')
    if not isinstance(params,dict) or any(params.get(k)!=v for k,v in required.items()):
        raise ValueError('Required reply parameters must be publicly supplied')
    if c.get('public_task_input')!={'goal':c['goal'],'public_parameters':params}:
        raise ValueError('Generator and actor public task input must contain exact parameters')
    if set(params)&{'private_reference','reference','expected','baseline','full_guard'}:
        raise ValueError('Private evaluator values cannot enter public task parameters')


def fingerprint(c):
    validate_contract(c)
    return source_fingerprint(c)


def positive_int(value):
    return type(value) is int and value>0


def path(value):
    u=urlsplit(value)
    return (u.path or '/')+('?' +u.query if u.query else '')+('#'+u.fragment if u.fragment else '')


def validate_ranges(value):
    if not isinstance(value,list):raise ValueError('Complete original comment ID ranges required')
    end=0
    for item in value:
        if (not isinstance(item,list) or len(item)!=2 or not all(positive_int(x) for x in item)
                or not end<item[0]<=item[1]):raise ValueError('Complete ordered comment ranges required')
        end=item[1]
    return value


def resolve_reference(c,comments,submissions,search_rows):
    """Private allowed set bound before actions, never a later chosen object."""
    validate_contract(c);spec=c['parented_reply']
    posts={r['id']:r for r in submissions}
    if len(posts)!=len(submissions) or any(not positive_int(i) for i in posts):
        raise ValueError('Complete exact native thread reference required')
    if spec['kind']=='search_visible_parent':
        expected={r['id'] for r in search_rows if r['kind']=='submission'}
        if set(posts)!=expected:raise ValueError('Native search matching thread set differs')
        for r in search_rows:
            if r['kind']=='submission' and posts[r['id']]['title']!=r['title']:
                raise ValueError('Raw native title and stored search row differ')
    parents=[]
    for row in comments:
        if (row.get('submission_id') not in posts or row.get('visibility')!='visible'
                or posts[row['submission_id']].get('visibility')!='visible'
                or posts[row['submission_id']].get('locked') is not False):continue
        if spec['kind']=='author_visible_parent' and row.get('username')!=spec['author']:continue
        if not all(positive_int(row.get(k)) for k in ('id','submission_id','user_id')):
            raise ValueError('Exact actual native parent identities required')
        parents.append(deepcopy(row))
    if not parents or len({r['id'] for r in parents})!=len(parents):
        raise ValueError('Actual eligible native parent set is missing or ambiguous')
    return {'parents':sorted(parents,key=lambda r:r['id']),
            'submission_ids':sorted({r['submission_id'] for r in parents}),
            'bound_before_actor':True}


def witnessed_parent(c,initial,observations,new_comment,*,site_origin):
    """Require an actually issued visible original parent before the new reply.

    Raw SQL title, native highlighted search label and current DOM identities
    remain distinct. A recorded highlighted label is never compared directly
    with the unhighlighted stored title, nor fixed by dropping all spaces.
    """
    from lab_generate_skill.reddit_search import search_checks
    spec=c['parented_reply'];target=new_comment.get('parent_id');thread=new_comment.get('submission_id')
    allowed={r['id']:r for r in initial['target']['parents']}
    parent=allowed.get(target)
    if not parent or parent['submission_id']!=thread:return False
    matching_posts={r['id']:r for r in initial['matching_posts']}
    validated_search_ids=set()
    for row in observations:
        actual=row.get('actual_issued_ax');public=row.get('native',{})
        if (not isinstance(actual,str)or public.get('capture_truncated')is not False
                or not valid_initial_page(row.get('page'),site_origin=site_origin)
                or row['page']['url']!=public.get('url')):continue
        if spec['kind']=='search_visible_parent' and urlsplit(public.get('url','')).path=='/search':
            checks=search_checks({'query':spec['query'],'reference':initial['search_rows'],'require_submission':True},row.get('search'),public['url'])
            if checks and all(checks.values()):
                refs={r['id']:r for r in initial['search_rows']if r['kind']=='submission'}
                for entry in public.get('submissions',[]):
                    ref=refs.get(entry.get('id'));label=rendered_search_title(ref['highlighted_title'])if ref else None
                    marker=entry.get('bid')
                    if ref and entry.get('visible')is True and entry.get('title')==label and marker and ('['+marker+']')in actual:
                        validated_search_ids.add(entry['id'])
        # A parent first noticed only after its new child was written cannot
        # retroactively supply an earlier interaction witness.
        if any(x.get('id')==new_comment.get('id')for x in public.get('comments',[])):continue
        cards=[r for r in public.get('comments',[])if r.get('id')==target and r.get('submission_id')==thread
               and r.get('visible')is True and r.get('author')==parent['username']]
        if len(cards)!=1:continue
        card=cards[0]
        if not any(isinstance(b,str)and('['+b+']')in actual for b in card.get('marker_bids',[])):continue
        post=matching_posts.get(thread)
        address=urlsplit(card.get('url',''));origin=urlsplit(site_origin)
        if (address.scheme,address.netloc)!=(origin.scheme,origin.netloc):continue
        m=re.fullmatch(r'/f/([^/]+)/([1-9][0-9]*)/[^/]+/comment/([1-9][0-9]*)',unquote(urlsplit(card.get('url','')).path))
        if not post or not m or m[1]!=post['forum']or int(m[2])!=thread or int(m[3])!=target:continue
        if spec['kind']=='author_visible_parent' or thread in validated_search_ids:return True
    return False


def ranking(row,count):
    if type(row.get('net_score')) is not int or type(count) is not int or count<0:
        raise ValueError('Native exact score/count required')
    stamp=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Native timezone required')
    score=row['net_score'];adv=score*1800+count*(5000 if score>-5 else 500)
    return int(stamp.timestamp())+max(min(adv,86400),-43200)


def certified_counter_change(before,after,new_comment,reference):
    if before.get('id')!=after.get('id') or before.get('id')!=new_comment.get('submission_id'):
        return False
    if set(before)!=set(after):return False
    changed={'comment_count','last_active','ranking'}
    if any(before[k]!=after[k] for k in before if k not in changed):return False
    if (type(before.get('comment_count')) is not int
            or reference.get('count')!=before['comment_count']
            or after.get('comment_count')!=reference['count']+1):
        return False
    try:
        old=datetime.fromisoformat((reference['latest'] or before['timestamp']).replace('Z','+00:00'))
        new=datetime.fromisoformat(new_comment['timestamp'].replace('Z','+00:00'))
        result=datetime.fromisoformat(after['last_active'].replace('Z','+00:00'))
        if any(t.tzinfo is None for t in (old,new,result)):return False
        return result==max(old,new) and after['ranking']==ranking(before,after['comment_count'])
    except (ValueError,TypeError,KeyError):return False


def native_author_vote(votes,comment,user):
    if len(votes)!=1:return False
    r=votes[0]
    if (set(r)!={'id','upvote','timestamp','user_id','ip','comment_id'} or not positive_int(r['id'])
            or r['upvote'] is not True or r['user_id']!=user or r['comment_id']!=comment['id']
            or r['ip']!=comment['ip']):return False
    try:
        a=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'))
        b=datetime.fromisoformat(comment['timestamp'].replace('Z','+00:00'))
        if a.tzinfo is None or b.tzinfo is None or abs((a-b).total_seconds())>1:return False
        if r['ip'] is not None:ipaddress.ip_address(r['ip'])
    except (ValueError,TypeError):return False
    return True


def validate_snapshot(value):
    if (not isinstance(value,dict) or value.get('version')!=PROTECTION_VERSION
            or set(value.get('tables',{}))!=set(TABLES) or value.get('ignored_columns')!=['users.last_seen']):
        raise ValueError('Complete explicit native 13-table snapshot required')
    for table,row in value['tables'].items():
        if (not isinstance(row,dict) or set(row)!={'columns','keys','count','sha256','normalized_count','normalized_sha256'}
                or type(row['count']) is not int or row['count']<0
                or type(row['normalized_count']) is not int or row['normalized_count']<0
                or not isinstance(row['columns'],list) or not row['columns'] or len(set(row['columns']))!=len(row['columns'])
                or any(not isinstance(k,str) or not re.fullmatch('[a-z][a-z0-9_]*',k) for k in row['columns'])
                or not isinstance(row['keys'],list) or not row['keys'] or len(set(row['keys']))!=len(row['keys'])
                or not set(row['keys'])<=set(row['columns'])
                or any(not isinstance(row[k],str) or not re.fullmatch('[0-9a-f]{64}',row[k]) for k in ('sha256','normalized_sha256'))):
            raise ValueError('Missing complete native row/schema coverage '+table)
    validate_ranges(value.get('known_comment_ranges'))
    validate_notifications(value.get('notifications'))


def validate_notifications(value):
    if (not isinstance(value,dict) or set(value)!={'table','columns','types','keys','count','sha256','normalized_count','normalized_sha256','owned_rows','comment_foreign_keys'}
            or value['table']!='notifications' or value['keys']!=['id']
            or not {'id','timestamp','user_id','notification_type','comment_id'}<=set(value['columns'])
            or len(value['columns'])!=len(set(value['columns']))
            or set(value['types'])!=set(value['columns']) or value['types']['id']!='uuid'
            or value['comment_foreign_keys']!=[{'table':'comment_votes','column':'comment_id'},{'table':'comments','column':'parent_id'},{'table':'notifications','column':'comment_id'}]
            or any(type(value[k])is not int or value[k]<0 for k in ('count','normalized_count'))
            or any(not isinstance(value[k],str)or not re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('sha256','normalized_sha256'))
            or not isinstance(value['owned_rows'],list)):
        raise ValueError('Complete notification/mention schema and full old-row protection required')


def notification_integrity(before,after,comment,initial):
    validate_notifications(before);validate_notifications(after)
    for key in ('table','columns','types','keys','comment_foreign_keys'):
        if before[key]!=after[key]:return False
    if (after['normalized_count'],after['normalized_sha256'])!=(before['count'],before['sha256']):return False
    rows=after['owned_rows']
    if after['count']!=before['count']+len(rows):return False
    if comment is None:return rows==[] and before==after
    recipients=initial['reply_notification_recipients'].get(str(comment.get('parent_id')))
    if not isinstance(recipients,list) or len(rows)!=len(recipients):return False
    try:
        stamp=datetime.fromisoformat(comment['timestamp'].replace('Z','+00:00'))
        seen=[]
        for row in rows:
            if (set(row)!=set(after['columns']) or row.get('notification_type')!='comment'
                    or row.get('comment_id')!=comment['id'] or row.get('user_id')not in recipients
                    or not re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',str(row.get('id','')))
                    or any(row[k]is not None for k in row if k not in {'id','timestamp','user_id','notification_type','comment_id'})):
                return False
            time=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
            if stamp.tzinfo is None or time.tzinfo is None or abs((stamp-time).total_seconds())>1:return False
            seen.append(row['user_id'])
        return sorted(seen)==sorted(recipients)
    except (ValueError,TypeError,KeyError):return False


def protected_integrity(before,after,*,initial,added,votes,threads):
    validate_snapshot(before);validate_snapshot(after)
    if before['known_comment_ranges']!=after['known_comment_ranges']:return False
    if len(added)>1:return False
    if not added:
        return (after.get('normalization') is None and votes==[]
            and all(before['tables'][t]==after['tables'][t] for t in TABLES)
            and notification_integrity(before['notifications'],after['notifications'],None,initial))
    entry=added[0];comment=entry.get('row',{});ident=comment.get('id');thread=comment.get('submission_id')
    parents={r['id']:r['submission_id'] for r in initial['target']['parents']}
    expected_comment={'id','body','timestamp','user_id','submission_id','parent_id','visibility',
        'ip','edited_at','moderated','user_flag','net_score','search_doc'}
    if (set(comment)!=expected_comment or not positive_int(ident) or comment.get('parent_id') not in parents
            or parents[comment['parent_id']]!=thread or comment.get('user_id')!=initial['user_id']
            or comment.get('visibility')!='visible' or comment.get('edited_at') is not None
            or comment.get('moderated') is not False or comment.get('net_score')!=1
            or comment.get('user_flag') not in ('none','moderator','admin')
            or entry.get('native_search_document') is not True
            or not isinstance(comment.get('body'),str) or not comment['body'].strip()
            or len(comment['body'])>10000 or not native_author_vote(votes,comment,initial['user_id'])):
        return False
    try:
        stamp=datetime.fromisoformat(comment['timestamp'].replace('Z','+00:00'))
        first=datetime.fromisoformat(before['snapshot_clock'].replace('Z','+00:00')).replace(microsecond=0)
        last=datetime.fromisoformat(after['snapshot_clock'].replace('Z','+00:00'))
        if any(t.tzinfo is None for t in (stamp,first,last)) or not first<=stamp<=last:return False
    except (ValueError,TypeError,KeyError):return False
    original={r['id']:r for r in initial['threads']};final={r['id']:r for r in threads}
    if set(original)!=set(final) or thread not in original:return False
    if not certified_counter_change(original[thread],final[thread],comment,initial['thread_counter_references'][str(thread)]):return False
    if any(original[k]!=final[k] for k in original if k!=thread):return False
    projected={'comment_id':ident,'submission_id':thread,'original_counters':
               {k:original[thread][k] for k in ('comment_count','last_active','ranking')}}
    if after.get('normalization')!=projected:return False
    for t in TABLES:
        b=before['tables'][t];a=after['tables'][t]
        if a['columns']!=b['columns'] or a['keys']!=b['keys']:return False
        if (a['normalized_count'],a['normalized_sha256'])!=(b['count'],b['sha256']):return False
        extra=1 if t in ('comments','comment_votes') else 0
        if a['count']!=b['count']+extra:return False
    return notification_integrity(before['notifications'],after['notifications'],comment,initial)


def evaluate(c,page,initial,final,*,site_origin,public,runtime_error=None):
    validate_contract(c)
    if runtime_error:return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Environment or inference error'}
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
        'one_native_comment_saved':len(final.get('added',[]))==1,
        'complete_native_non_target_records_unchanged':final.get('integrity') is True}
    if checks['one_native_comment_saved']:
        row=final['added'][0]['row'];parents={r['id']:r['submission_id'] for r in initial['target']['parents']}
        checks.update(correct_author=row.get('user_id')==initial['user_id'],
            actual_comment_parent=row.get('parent_id') in parents,
            correct_thread=row.get('parent_id') in parents and row.get('submission_id')==parents[row['parent_id']],
            exact_publicly_requested_body=row.get('body')==c['parented_reply']['reply_body'],
            publicly_visible=row.get('visibility')=='visible')
        checks['original_parent_observed_before_save']=witnessed_parent(c,initial,public.get('observations',[]),row,site_origin=site_origin)
        # A successful database write remains a success after lawful navigation
        # away, but its new reply must have been observed in this bound context.
        shown=[r for r in public.get('observed_comments',[]) if r.get('id')==row.get('id')
            and r.get('visible') is True and r.get('author')==initial['username']
            and r.get('submission_id')==row.get('submission_id')]
        checks['new_reply_observed']=bool(shown)
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls(c):
    validate_contract(c)
    return dict.fromkeys(('no_op','filled_unsaved','submission_reply','wrong_parent',
        'wrong_body','second_reply','404','login'),'failure')|{'positive':'success','saved_then_home':'success'}
