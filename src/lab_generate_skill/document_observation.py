"""Audit section exposure in the ACTUAL actor request, not the unselected AX.

This is evidence for read-oriented document tasks. It cannot establish a click,
state change, a saved edit, or a successful task without document identity checks.
"""
import ast
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

NODE=re.compile(r'''^(\s*)(?:\[[^\]]+\]\s+)?([\w-]+)\s+('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''')


def attach_last_request(page, directory, *, family='repository'):
    """Private terminal audit copy; raw capture and model input stay unchanged.

    Only the last generation is relevant. Do not fall back to an older request
    when a later generation failed or was only partially saved.
    """
    result=deepcopy(page)
    if family not in ('repository','map_diary','cms_section'):raise ValueError('Unsupported document family')
    if not isinstance(result,dict)or not isinstance(result.get(family),dict):return result,None
    files=sorted(Path(directory).glob('generation-*.json'))
    if not files:return result,None
    source=files[-1]
    try:generation=json.loads(source.read_text())
    except (ValueError,OSError):return result,None
    if not isinstance(generation,dict)or generation.get('status')!='complete' or generation.get('scripted_control'):return result,None
    messages=generation.get('messages')
    if not isinstance(messages,list)or not messages or messages[-1].get('role')!='user':return result,None
    result[family]['issued_section_request']={'status':'complete','messages':[messages[-1]]}
    return result,source


def ax_section_names(text,heading):
    nodes=[]
    for line in text.splitlines():
        match=NODE.match(line)
        if not match:continue
        try:name=ast.literal_eval(match.group(3))
        except (ValueError,SyntaxError):continue
        if not isinstance(name,str):continue
        nodes.append((len(match.group(1).expandtabs(4)),match.group(2),name))
    indexes=[i for i,(_,role,name)in enumerate(nodes)if role=='heading'and name==heading]
    if len(indexes)!=1:return None
    index=indexes[0];indent=nodes[index][0];names=[]
    for depth,role,name in nodes[index+1:]:
        if role=='heading'and depth<=indent:break
        if role in ('StaticText','link','heading')and name:names.append(name)
    return names


def words(text):return re.findall(r'\w+',text,flags=re.UNICODE)


def ordered_coverage(expected,observed):
    """Native AX may repeat link names in StaticText; require every body token."""
    wanted=words(expected)
    if not wanted:return False
    remaining=iter(words(observed))
    return all(any(actual==word for actual in remaining)for word in wanted)


def request_exposure(generation,*,terminal_url,section):
    result={'version':'issued-ax-section-v1','observed':False,'reason':None}
    if not isinstance(generation,dict)or generation.get('status')!='complete':
        return {**result,'reason':'No complete recorded actor request'}
    messages=generation.get('messages')
    if not isinstance(messages,list)or not messages or messages[-1].get('role')!='user':
        return {**result,'reason':'Missing actual user request'}
    try:body=json.loads(messages[-1]['content'])
    except (ValueError,KeyError,TypeError):return {**result,'reason':'Request is not the structured observation protocol'}
    if not isinstance(body,dict)or not isinstance(body.get('observation'),str)or not isinstance(body.get('url'),str):
        return {**result,'reason':'Selected observation or URL missing'}
    if body.get('observation_mode')not in ('full','viewport'):
        return {**result,'reason':'Selected observation mode missing'}
    if not isinstance(section,dict)or not isinstance(section.get('heading'),str)or not isinstance(section.get('text'),str):
        raise ValueError('Native section heading and body required')
    a=urlsplit(body['url']);b=urlsplit(terminal_url)
    # A fragment scroll stays in the same document; another URL/query does not.
    if (a.scheme,a.netloc,a.path,a.query)!=(b.scheme,b.netloc,b.path,b.query):
        return {**result,'reason':'Observed document differs from terminal document'}
    names=ax_section_names(body['observation'],section['heading'])
    observed=names is not None and ordered_coverage(section['text'],' '.join(names))
    return {**result,'observed':observed,'observation_mode':body['observation_mode'],
            'observation_sha256':hashlib.sha256(body['observation'].encode()).hexdigest(),
            'section_body_sha256':hashlib.sha256(' '.join(section['text'].split()).encode()).hexdigest(),
            'reason':None if observed else 'Requested section body is absent or incomplete in the selected AX'}
