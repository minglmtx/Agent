"""Readable, reversible Teacher evidence with shared AX pages and exact edits.

Only already-permitted Teacher evidence belongs here. This codec never reads
private evaluators, changes Actor observations, summarizes, or drops attempts.
Integrity and JSON byte-format metadata stay in an auditable recovery sidecar;
the Teacher receives ordinary task/attempt dictionaries and shared page records.
"""
from copy import deepcopy
import ast
import difflib
import hashlib
import json
import re

VERSION = 'teacher-evidence-pages-v2'
BID = re.compile(r'(?m)^([ \t]*)\[(\d+)\](?= )')
PAGE_FIELDS = ('axtree_txt', 'axtree_full_txt', 'observation')
GUIDE = '''
The user JSON contains the complete permitted evidence in teacher-evidence-pages-v2.
Read evidence as the usual task, initial observation, retrieved skills and all
candidate trajectories with actions, errors, outcomes and evaluator feedback.
An AX field {"page_ref":"pN"} refers to shared_pages. Pages are in dependency order.
A page with text contains the exact AX text. A page with base_page and segments
is reconstructed by concatenating its segments in order. {"copy_lines":[a,b]}
copies zero-based lines a through b-1 of the base, preserving line endings.
{"insert":text} inserts the exact displayed text. A copied segment may include
node_id_offset: add that integer only to the bracketed node ID at the beginning
of each AX line, leaving all names, values and other numbers unchanged. If it
instead has node_ids, replace those leading node IDs in encounter order with
the listed exact strings. These are exact page changes, not missing evidence.
readable_index contains exact, mechanically extracted page roots/headings and
an ordered timeline for EVERY attempt, including termination/report/message
functions. It labels attempted actions and their following observed errors; it
does not claim that an action succeeded. Prefer this index for temporal order
and page identity, and consult the complete evidence for all remaining details.
Use the page corresponding to each step when interpreting its action IDs.
Consider all attempts and factual feedback. A failed check does not prove a
unique cause. Return the output explicitly requested by the caller.
'''


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(serialized(value).encode()).hexdigest()


def json_style(text, value):
    for ascii_only in (False, True):
        for compact in (True, False):
            options = dict(ensure_ascii=ascii_only, allow_nan=False)
            if compact:
                options['separators'] = (',', ':')
            if json.dumps(value, **options) == text:
                return dict(ensure_ascii=ascii_only, compact=compact)
    return None


def readable_index(evidence, page_ids):
    """Expose factual chronology without requiring the model to execute a codec.

    Selection is task independent: every unique page, all headings, every
    submitted action and its observed target/error. No reference answer or
    judgment-dependent snippet selection is available to this function.
    """
    headings = re.compile(r'^\s*(?:\[\d+\] )?heading ')
    page_rows=[]
    for text,pid in page_ids.items():
        lines=text.splitlines()
        page_rows.append(dict(page_id=pid,root=next((l.strip()for l in lines if l.strip()),''),
            headings=[l.strip()for l in lines if headings.match(l)]))
    attempts=[]
    for i,attempt in enumerate(evidence['attempts']):
        trajectory=attempt['trajectory'];timeline=[];last_page=None
        def body(message):
            if not message or message.get('role')!='user':return {}
            try:value=json.loads(message.get('content',''))
            except (ValueError,TypeError):return {}
            return value if isinstance(value,dict)else{}
        def tree(observation):
            return next((observation[k]for k in PAGE_FIELDS if isinstance(observation.get(k),str)),None)
        for j,message in enumerate(trajectory):
            if message.get('role')=='user':
                current=tree(body(message))
                if current in page_ids:last_page=page_ids[current]
                continue
            if message.get('role')!='assistant':continue
            before=body(trajectory[j-1]if j else None)
            after=body(trajectory[j+1]if j+1<len(trajectory)else None)
            before_tree,after_tree=tree(before),tree(after)
            command=message.get('action_payload');functions=[];targets=[]
            if isinstance(command,str):
                try:
                    parsed=ast.parse(command)
                    for node in parsed.body:
                        if not isinstance(node,ast.Expr)or not isinstance(node.value,ast.Call):continue
                        call=node.value
                        if not isinstance(call.func,ast.Name):continue
                        name=call.func.id;functions.append(name)
                        if name in {'click','dblclick','fill','press','hover','focus','select_option','check','uncheck','drag_and_drop'}:
                            args=call.args[:2]if name=='drag_and_drop'else call.args[:1]
                            for arg in args:
                                if isinstance(arg,ast.Constant)and isinstance(arg.value,str)and arg.value.isdigit():
                                    lines=[]if before_tree is None else before_tree.splitlines()
                                    prefix=re.compile(r'^\s*\['+re.escape(arg.value)+r'\] ')
                                    targets.append(dict(node_id=arg.value,
                                        observed_lines=[l.strip()for l in lines if prefix.match(l)]))
                except (ValueError,SyntaxError):pass
            timeline.append(dict(response_index=len(timeline),message_index=j,
                submitted_action=command,functions=functions,
                before_page=page_ids.get(before_tree),after_page=page_ids.get(after_tree),
                observed_targets=targets,observed_error_after=after.get('last_action_error'),
                action_success_inferred=False))
        submitted=[r['submitted_action']for r in timeline if r['submitted_action']]
        attempts.append(dict(candidate_index=i,steps=attempt.get('steps'),success=attempt.get('success'),
            timeline=timeline,final_page=last_page,last_submitted_action=submitted[-1]if submitted else None))
    return dict(pages=page_rows,attempts=attempts,
        interpretation='Exact page identities and submitted actions with subsequent observations; outcomes remain the separately recorded evaluator facts.')


def _segments(old, new):
    before, after = old.splitlines(keepends=True), new.splitlines(keepends=True)
    key = lambda line: BID.sub(lambda m:m[1]+'[NODE_ID]', line)
    matcher = difflib.SequenceMatcher(None, list(map(key,before)), list(map(key,after)), autojunk=False)
    segments = []
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag == 'equal':
            segment = dict(copy_lines=[a,b])
            old_text, new_text = ''.join(before[a:b]), ''.join(after[c:d])
            if old_text != new_text:
                old_ids = [m[2] for m in BID.finditer(old_text)]
                new_ids = [m[2] for m in BID.finditer(new_text)]
                if not old_ids or len(old_ids) != len(new_ids):
                    raise ValueError('AX node-ID matching lost text')
                delta = int(new_ids[0])-int(old_ids[0])
                if all(str(int(x)+delta)==y for x,y in zip(old_ids,new_ids)):
                    segment['node_id_offset'] = delta
                else:
                    segment['node_ids'] = new_ids
            segments.append(segment)
        elif c != d:
            segments.append(dict(insert=''.join(after[c:d])))
    return segments


def pack(evidence):
    """Return a model-readable payload and an exact-reconstruction sidecar."""
    if not isinstance(evidence,dict) or not isinstance(evidence.get('initial_observation'),str):
        raise ValueError('Structured Teacher evidence with an initial page required')
    converted=deepcopy(evidence); pages=[]; texts=[]; depths=[]; seen={}; fields=[]; styles=[]

    def page_ref(text, path):
        if text not in seen:
            pid='p'+str(len(pages)); row=dict(page_id=pid,text=text); depth=0
            for base in range(max(0,len(pages)-8),len(pages)):
                if depths[base]>=4:continue
                candidate=dict(page_id=pid,base_page=pages[base]['page_id'],segments=_segments(texts[base],text))
                if len(serialized(candidate))<len(serialized(row)):
                    row=candidate;depth=depths[base]+1
            seen[text]=pid;pages.append(row);texts.append(text);depths.append(depth)
        fields.append(path)
        return dict(page_ref=seen[text])

    converted['initial_observation']=page_ref(evidence['initial_observation'],['initial_observation'])
    for i,attempt in enumerate(converted['attempts']):
        for j,message in enumerate(attempt['trajectory']):
            content=message.get('content')
            if message.get('role')!='user' or not isinstance(content,str):continue
            try:body=json.loads(content)
            except ValueError:continue
            if not isinstance(body,dict):continue
            style=json_style(content,body)
            if style is None:continue  # Preserve unfamiliar byte formatting exactly.
            path=['attempts',i,'trajectory',j,'content']
            styles.append(dict(path=path,**style))
            for key in PAGE_FIELDS:
                if isinstance(body.get(key),str):body[key]=page_ref(body[key],path+[key])
            message['content']=body
    payload=dict(version=VERSION,readable_index=readable_index(evidence,seen),shared_pages=pages,evidence=converted)
    recovery=dict(version=VERSION,source_sha256=digest(evidence),payload_sha256=digest(payload),
        page_fields=fields,json_text_styles=styles,page_sha256=[hashlib.sha256(t.encode()).hexdigest()for t in texts])
    return payload,recovery


def decode_pages(payload):
    if payload.get('version')!=VERSION:raise ValueError('Unknown Teacher page encoding')
    texts={};depths={}
    for index,row in enumerate(payload['shared_pages']):
        pid=row.get('page_id')
        if pid!='p'+str(index):raise ValueError('Invalid page order/identity')
        if set(row)=={'page_id','text'}:
            text=row['text'];depth=0
            if not isinstance(text,str):raise ValueError('Page text must be a string')
        elif set(row)=={'page_id','base_page','segments'}:
            base=row['base_page']
            if base not in texts or depths[base]>=4:raise ValueError('Invalid base page')
            lines=texts[base].splitlines(keepends=True);parts=[];previous_end=0
            for segment in row['segments']:
                if set(segment)=={'insert'} and isinstance(segment['insert'],str):
                    parts.append(segment['insert']);continue
                if set(segment) not in ({'copy_lines'},{'copy_lines','node_id_offset'},{'copy_lines','node_ids'}):
                    raise ValueError('Invalid copied page segment')
                bounds=segment['copy_lines']
                if not isinstance(bounds,list)or len(bounds)!=2:raise ValueError('Invalid copy bounds')
                a,b=bounds
                if type(a)is not int or type(b)is not int or not previous_end<=a<b<=len(lines):
                    raise ValueError('Invalid page line range')
                part=''.join(lines[a:b]);previous_end=b
                if 'node_id_offset'in segment:
                    delta=segment['node_id_offset']
                    if type(delta)is not int:raise ValueError('Invalid node ID offset')
                    def replace(match):
                        value=int(match[2])+delta
                        if value<0:raise ValueError('Negative node ID')
                        return match[1]+'['+str(value)+']'
                    part=BID.sub(replace,part)
                elif 'node_ids'in segment:
                    ids=segment['node_ids'];matches=list(BID.finditer(part))
                    if (not isinstance(ids,list)or len(ids)!=len(matches)
                            or any(not isinstance(n,str)or not re.fullmatch(r'\d+',n)for n in ids)):
                        raise ValueError('Invalid node ID replacement list')
                    replacements=iter(ids)
                    part=BID.sub(lambda m:m[1]+'['+next(replacements)+']',part)
                parts.append(part)
            text=''.join(parts);depth=depths[base]+1
        else:raise ValueError('Invalid page record')
        texts[pid]=text;depths[pid]=depth
    return texts


def unpack(payload,recovery):
    if recovery.get('version')!=VERSION or digest(payload)!=recovery['payload_sha256']:
        raise ValueError('Teacher payload identity changed')
    pages=decode_pages(payload)
    if [hashlib.sha256(t.encode()).hexdigest()for t in pages.values()]!=recovery['page_sha256']:
        raise ValueError('Reconstructed page changed')
    evidence=deepcopy(payload['evidence'])
    def parent(path):
        obj=evidence
        for key in path[:-1]:obj=obj[key]
        return obj,path[-1]
    for path in recovery['page_fields']:
        obj,key=parent(path);ref=obj[key]
        if not isinstance(ref,dict)or set(ref)!={'page_ref'}:raise ValueError('Invalid page reference')
        obj[key]=pages[ref['page_ref']]
    for row in recovery['json_text_styles']:
        obj,key=parent(row['path']);options=dict(ensure_ascii=row['ensure_ascii'],allow_nan=False)
        if row['compact']:options['separators']=(',',':')
        obj[key]=json.dumps(obj[key],**options)
    if digest(evidence)!=recovery['source_sha256']:raise ValueError('Teacher evidence reconstruction changed')
    if payload['readable_index']!=readable_index(evidence,{text:pid for pid,text in pages.items()}):
        raise ValueError('Readable factual index contradicts original evidence')
    return evidence


def prepare(messages,tokenizer,maximum,*,diagnostic_path):
    """Persist evidence/length diagnostics even when no representation fits."""
    from pathlib import Path
    evidence=json.loads(messages[-1]['content'])
    payload,recovery=pack(evidence)
    if unpack(payload,recovery)!=evidence:raise ValueError('Teacher evidence is not reversible')
    packed=deepcopy(messages);packed[0]['content']+=GUIDE;packed[-1]['content']=serialized(payload)
    count=lambda m:len(tokenizer.apply_chat_template(m,tokenize=True,add_generation_prompt=True,enable_thinking=False))
    raw_tokens,packed_tokens=count(messages),count(packed)
    selected=packed if packed_tokens<raw_tokens else messages
    parts={key:len(tokenizer.encode(serialized(value),add_special_tokens=False))for key,value in evidence.items()}
    report=dict(version=VERSION,source_sha256=recovery['source_sha256'],raw_tokens=raw_tokens,
        encoded_tokens=packed_tokens,selected_tokens=min(raw_tokens,packed_tokens),maximum=maximum,
        fits=min(raw_tokens,packed_tokens)<=maximum,exact_round_trip=True,
        raw_component_tokens=parts,component_tokens_include_no_chat_template=True,
        selected_encoding=VERSION if selected is packed else 'original',
        shared_page_count=len(payload['shared_pages']),attempt_count=len(evidence['attempts']))
    path=Path(diagnostic_path);path.parent.mkdir(parents=True,exist_ok=True)
    for suffix,value in [('payload',payload),('recovery',recovery),('diagnostic',report)]:
        target=path.with_name(path.stem+'-'+suffix+'.json')
        data=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        if target.exists():
            if target.read_text()!=data:raise ValueError('Teacher diagnostic checkpoint changed')
        else:
            with target.open('x')as stream:stream.write(data)
    if not report['fits']:
        raise ValueError('Teacher evidence requires %d tokens; budget %d; full diagnostics saved'%(report['selected_tokens'],maximum))
    return selected,report
