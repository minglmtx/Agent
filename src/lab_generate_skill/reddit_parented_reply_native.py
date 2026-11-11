"""Bounded private native references for actual parented-comment persistence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
from lab_generate_skill.site_database import select_rows
from lab_generate_skill.io_utils import atomic_write_json
from . import reddit_parented_reply as rule

ASSET_SHA = '50c8d20cc15901555c56c25f3c3ebebbae6579ab24a6d9e58a819b073160faef'


def snapshot(site,directory,*,initial=None,candidate=None,thread_ids=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    script=Path(__file__).with_suffix('.php')
    data=script.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ASSET_SHA:
        raise ValueError('Frozen native reply asset changed')
    if thread_ids is not None and (initial is not None or not isinstance(thread_ids,list)
            or not all(rule.positive_int(v) for v in thread_ids) or thread_ids!=sorted(set(thread_ids))):
        raise ValueError('Exact independently bound initial thread identities required')
    spec={'thread_ids':initial['target']['submission_ids'] if initial else (thread_ids or [])}
    if initial:
        rule.validate_ranges(initial['known_comment_ranges'])
        spec['known_comment_ranges']=initial['known_comment_ranges']
    if candidate is not None:
        if not rule.positive_int(candidate.get('id')):raise ValueError('Exact actual inserted comment required')
        spec['candidate_comment_id']=candidate['id']
        original={r['id']:r for r in initial['threads']}
        if candidate.get('submission_id') in original:
            row=original[candidate['submission_id']]
            spec['normalization']={'comment_id':candidate['id'],'submission_id':row['id'],
                'original_counters':{k:row[k] for k in ('comment_count','last_active','ranking')}}
    try:
        response=site.command(['php','-r',data.decode().removeprefix('<?php'),str(site.db_port),json.dumps(spec)],
                              capture_output=True,text=True,timeout=600)
    except subprocess.CalledProcessError as error:
        details=[]
        for line in (error.stderr or '').splitlines():
            if line.startswith('LAB_REPLY_ERROR '):
                details.append(json.loads(line[len('LAB_REPLY_ERROR '):]))
        atomic_write_json(directory/'private-native-error.json',{'phase':'complete13_snapshot',
            'returncode':error.returncode,'native_diagnostics':details,'private_only':True})
        raise
    value=None;progress=[]
    for line in response.stdout.splitlines():
        if line.startswith('LAB_REPLY_PROGRESS '):
            row=json.loads(line[len('LAB_REPLY_PROGRESS '):])
            if set(row)!={'table','chunk','rows','seconds'} or row['table'] not in rule.TABLES+('notifications',):
                raise ValueError('Invalid native coverage progress')
            progress.append(row)
        elif line.startswith('LAB_REPLY_RESULT '):
            if value is not None:raise ValueError('Duplicate complete native result')
            value=json.loads(line[len('LAB_REPLY_RESULT '):])
        elif line.strip():raise ValueError('Unexpected private native reply output')
    rule.validate_snapshot(value)
    seen={}
    for row in progress:
        prev=seen.get(row['table'],{'chunk':0,'rows':0})
        if (type(row['chunk']) is not int or row['chunk']!=prev['chunk']+1
                or type(row['rows']) is not int or not prev['rows']<row['rows']<=prev['rows']+2048):
            raise ValueError('Full native contiguous coverage required')
        seen[row['table']]=row
    for table,row in (value['tables']|{'notifications':value['notifications']}).items():
        if seen.get(table,{}).get('rows',0)!=row['count']:
            raise ValueError('Complete actual native table count differs from chunks')
    with (directory/'native-full13-progress.jsonl').open('a') as f:
        for row in progress:f.write(json.dumps(row)+'\n')
    return value


def account(site,username):
    if not isinstance(username,str) or not username:raise ValueError('Exact task account required')
    quoted="'"+username.replace("'","''")+"'"
    rows=select_rows(site,'SELECT id,username FROM users WHERE username='+quoted)
    if len(rows)!=1 or not rule.positive_int(rows[0].get('id')):
        raise ValueError('Native task account missing or ambiguous')
    return rows[0]


def parent_reference(site,c,username):
    """Complete private initial parent eligibility, not a chosen late target."""
    from lab_generate_skill.reddit_search import search_reference
    rule.validate_contract(c);spec=c['parented_reply'];user=account(site,username)
    search_rows=search_reference(site,spec['query'])if spec['kind']=='search_visible_parent'else[]
    if spec['kind']=='search_visible_parent':
        post_ids=sorted({r['id']for r in search_rows if r['kind']=='submission'})
        if not post_ids:raise ValueError('Native matching post set is absent')
        clause='c.submission_id IN ('+','.join(map(str,post_ids))+')'
    else:clause="u.username='"+spec['author'].replace("'","''")+"'"
    # Actual observations still must establish visible UI eligibility. This
    # before-action query fixes permitted identities, never supplies them to
    # actor inputs or chooses the parent on the actor's behalf.
    predicate=(clause+" AND c.visibility='visible' AND s.visibility='visible' AND NOT s.locked"
               +' AND NOT EXISTS (SELECT 1 FROM user_blocks b WHERE b.blocker_id='+str(user['id'])+' AND b.blocked_id=c.user_id)')
    count=select_rows(site,'SELECT count(*) AS n FROM comments c JOIN users u ON u.id=c.user_id JOIN submissions s ON s.id=c.submission_id WHERE '+predicate)[0]['n']
    if type(count)is not int or count<=0:raise ValueError('Complete original allowed parent set absent')
    parents=[];last=0
    while True:
        chunk=select_rows(site,'SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.user_id JOIN submissions s ON s.id=c.submission_id WHERE '+predicate+' AND c.id>'+str(last)+' ORDER BY c.id LIMIT 2048')
        if not chunk:break
        if any(not rule.positive_int(r.get('id'))or r['id']<=last for r in chunk):raise ValueError('Actual parent key coverage differs')
        parents.extend(chunk);last=chunk[-1]['id']
    if len(parents)!=count or len({r['id']for r in parents})!=count:raise ValueError('Complete allowed parent collection required')
    if spec['kind']=='search_visible_parent':ids=post_ids
    else:ids=sorted({r['submission_id']for r in parents})
    threads=select_rows(site,'SELECT s.*,f.name AS forum FROM submissions s JOIN forums f ON f.id=s.forum_id WHERE s.id IN ('+','.join(map(str,ids))+') ORDER BY s.id')
    target=rule.resolve_reference(c,parents,threads,search_rows)
    # Snapshot counter rows are raw native submissions, without join labels.
    raw_threads=[{k:v for k,v in row.items()if k!='forum'}for row in threads if row['id']in target['submission_ids']]
    receivers=sorted({r['user_id']for r in parents})
    users=select_rows(site,'SELECT id,username,notify_on_reply FROM users WHERE id IN ('+','.join(map(str,receivers))+') ORDER BY id')
    if {r['id']for r in users}!=set(receivers):raise ValueError('Every initial native recipient required')
    blocks=select_rows(site,'SELECT blocker_id,blocked_id FROM user_blocks WHERE blocker_id IN ('+','.join(map(str,receivers))+') ORDER BY blocker_id,blocked_id')
    blocked={(r['blocker_id'],r['blocked_id'])for r in blocks};user_map={r['id']:r for r in users};recipient_map={}
    for parent in parents:
        receiver=user_map[parent['user_id']]
        eligible=(receiver['id']!=user['id']and receiver['username']!='!deleted'+str(receiver['id'])
                  and receiver['notify_on_reply']is True and(receiver['id'],user['id'])not in blocked)
        recipient_map[str(parent['id'])]=[receiver['id']]if eligible else[]
    return {'target':target,'threads':raw_threads,'matching_posts':threads,'search_rows':search_rows,
            'reply_notification_recipients':recipient_map,'recipient_user_rows':users,'recipient_block_rows':blocks,
            'user_id':user['id'],'username':user['username']}


def initial_state(site,c,username,directory,*,return_capture=False,captured_before=None):
    private=parent_reference(site,c,username)
    # Only the CPU hook's validated one-use handoff supplies captured_before.
    # Ordinary callers keep the exact fresh complete scanner and all checks.
    complete=(snapshot(site,directory,thread_ids=private['target']['submission_ids'])
              if captured_before is None else deepcopy(captured_before))
    rule.validate_snapshot(complete)
    if complete['threads']!=private['threads']:raise ValueError('Exact complete-snapshot thread rows differ from reference')
    refs=complete['thread_counter_references']
    for row in complete['threads']:
        if refs.get(str(row['id']),{}).get('count')!=row['comment_count']:raise ValueError('Actual native cached visible-comment count differs')
    result=private|{'complete13':stable_snapshot(complete),'known_comment_ranges':complete['known_comment_ranges'],
                    'thread_counter_references':refs,'reply_body':c['parented_reply']['reply_body']}
    return (result,complete) if return_capture else result


def new_candidate(site,initial):
    ranges=rule.validate_ranges(initial['known_comment_ranges'])
    predicate=' OR '.join('id BETWEEN '+str(lo)+' AND '+str(hi) for lo,hi in ranges) or 'false'
    rows=select_rows(site,'SELECT * FROM comments WHERE NOT ('+predicate+') ORDER BY id LIMIT 2')
    return rows[0] if len(rows)==1 else None


def stable_snapshot(value):
    rule.validate_snapshot(value)
    return {k:deepcopy(value[k]) for k in ('version','tables','known_comment_ranges','ignored_columns','notifications')}


NATIVE_SOURCE_PINS={'config/app_routes/comment.yaml': '1e07e8c58ee6b1036962eeb71f1b6faca391f65174c3c64c340d889ea9733834', 'config/app_routes/submission.yaml': '7b982d0ecf029fd5ba4b06b8b53aae4dd1b059887018f2a135964dd537552dd8', 'migrations/Version20190322210445.php': '03c10728d682b2bd218891dbd5cde2547c9fb39ba0210951691ebf5fcd96cf76', 'src/Controller/CommentController.php': '0a137524f93f7b3ca641dddf5091b8a2377114da1393543e59ecccf93cf3efd7', 'src/DataObject/CommentData.php': '56c5532da5620d3fe19864adecbace9b1690405155fe55c8d97186896d9b6f98', 'src/Entity/Comment.php': '7eab575b29e46287b30fabb90d73d31e2380cbb79dc517f4342db88219fd4884', 'src/Entity/CommentMention.php': '2ba0bf76d3d5e9337311758abba13555c39d9d4b1856660afc853044585820f9', 'src/Entity/CommentNotification.php': 'b31104c5590975317229a497e90c9c1a123634f7a62547ab24c236c01af1ab75', 'src/Entity/CommentVote.php': 'bc7587350d06aa03ad5a48e1daf3a234a8d6a388ccf2adbcd59eebb877886abb', 'src/Entity/Notification.php': '28e71cf83d2112595603011e42d13f5b8cc4afe0371affe65447dcc12e3cc289', 'src/Entity/Submission.php': 'ad2cf7054afde18cb4026517ec00dbf28c217e3197de05ada0f77f44548147ec', 'src/Entity/Traits/VotableTrait.php': '71a7245b765f80df468e919f0ea6c2a668987aa48f897276f775cc02149b0436', 'src/Entity/User.php': '4411003257960dd58c447fc788f50414a5efceb899248d4e907a2b02a394a352', 'src/Entity/UserFlags.php': 'df298060f820aacbc5a5555706a764a9c0e17399709570ef5ae719b784738de0', 'src/Entity/Vote.php': 'ee2f6ac7dbed36f517cbf5258bc5ccfc4224c52731e2bafe7ec987e3107b65de', 'src/EventListener/MentionsListener.php': 'e29ade8f6cebda89df9e99a821aba1c92d4753a7326d721721b05e10942f8464', 'src/Form/CommentType.php': 'c4a7e4826ebaf37a2e0ae7ff26ff3e757494171bbbd0e85bbb232cd558795deb', 'templates/_layouts/comment.html.twig': '18108b7e645c8df0a1cef4e047669d5fe857b18f90983a8e5c78a11b4fb91377', 'templates/comment/_form.html.twig': '86e7561489ca1cef9825ddc374afb0c112a241d099f981e24c6f71d0efe9fed7', 'templates/comment/_macros.html.twig': '9632bc354358857345183d676ee4cd84bca25c34281ba81a50e8c95a549144be', 'templates/comment/create.html.twig': '993ffe945037a004bc8bbac74eb794918be3a11b796569e2b25acd85cfdb9b23', 'templates/comment/form_fragment.html.twig': '18da68431f31c416c626ed61414a3b4e20326da628853a9c7e642523ab2c6e6c'}

def preflight_assets(site):
    # Reading shipped source is not website initialization or an actor tool.
    own=Path(__file__).with_suffix('.php')
    if not own.is_file() or hashlib.sha256(own.read_bytes()).hexdigest()!=ASSET_SHA:
        raise ValueError('Frozen native reply asset unavailable or changed')
    code=r"""$pins=json_decode($argv[1],true,512,JSON_THROW_ON_ERROR);$out=[];foreach($pins as $name=>$expected){if(!preg_match('/^[a-zA-Z0-9_\/.]+$/D',$name)||strpos($name,'..')!==false)throw new RuntimeException('Invalid native source');$file='/var/www/html/'.$name;if(!is_file($file))throw new RuntimeException('Native source missing');$out[$name]=hash_file('sha256',$file);}echo json_encode($out);"""
    value=json.loads(site.command(['php','-r',code,json.dumps(NATIVE_SOURCE_PINS)],capture_output=True,text=True,timeout=30).stdout)
    if value!=NATIVE_SOURCE_PINS:raise ValueError('Native parent/controller/counter code changed')
