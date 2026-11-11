"""Lossless offline Teacher-evidence compression candidate; no model integration.

Only caller-supplied JSON is encoded. This is not an information-boundary filter:
callers must first construct public/factual Teacher evidence. Actor observations,
source archives, skill bank and active Teacher requests are never modified here.
"""
import hashlib
import json

VERSION = 'teacher-evidence-lossless-v1'


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(serialized(value).encode()).hexdigest()


def pack(value):
    """Share strings and encode exact prefix/suffix differences, without truncation.

    Tagged nodes avoid collisions with arbitrary input dictionary keys. JSON
    message strings are unwrapped only when a known serialization recreates
    every original byte. References point backwards; delta chains are bounded.
    """
    strings=[];seen={};recent={};depths=[]

    def text_node(text, group):
        if len(text)<256:return ['value',text]
        if text in seen:return ['text',seen[text]]
        entry={'text':text}
        depth=0
        for base in recent.get(group,[])[-8:]:
            if depths[base]>=4:continue
            old=strings[base][0]
            prefix=0
            while prefix<min(len(old),len(text)) and old[prefix]==text[prefix]:prefix+=1
            suffix=0
            while suffix<min(len(old),len(text))-prefix and old[-suffix-1]==text[-suffix-1]:suffix+=1
            candidate={'base':base,'prefix':prefix,'suffix':suffix,
                       'insert':text[prefix:len(text)-suffix if suffix else len(text)]}
            if len(serialized(candidate))<len(serialized(entry)):
                entry=candidate;depth=depths[base]+1
        index=len(strings);seen[text]=index;strings.append((text,entry));depths.append(depth)
        recent.setdefault(group,[]).append(index)
        return ['text',index]

    def encode(item, group='root', parse_json=True):
        if isinstance(item,dict):
            if any(not isinstance(k,str) for k in item):raise ValueError('JSON string keys required')
            return ['object',[[k,encode(v,k)]for k,v in item.items()]]
        if isinstance(item,list):return ['array',[encode(v,group)for v in item]]
        if isinstance(item,str):
            if parse_json and item.startswith(('{','[')):
                try:parsed=json.loads(item)
                except (ValueError,RecursionError):parsed=None
                if isinstance(parsed,(dict,list)):
                    for ascii_only in (False,True):
                        for compact in (True,False):
                            options={'ensure_ascii':ascii_only,'allow_nan':False}
                            if compact:options['separators']=(',',':')
                            try:same=json.dumps(parsed,**options)==item
                            except ValueError:same=False
                            if same:return ['json_text',ascii_only,compact,encode(parsed,group,False)]
            return text_node(item,group)
        if item is None or type(item) in (bool,int,float):
            serialized(item)  # Reject NaN/Infinity; never invent a JSON value.
            return ['value',item]
        raise ValueError('Only JSON evidence is supported')

    root=encode(value)
    return dict(version=VERSION,source_sha256=digest(value),
                strings=[dict(entry,sha256=hashlib.sha256(text.encode()).hexdigest())for text,entry in strings],
                root=root)


def unpack(packet):
    """Validate every shared text/delta and the entire reconstructed evidence."""
    if packet.get('version')!=VERSION:raise ValueError('Unknown evidence encoding')
    texts=[];depths=[]
    for row in packet['strings']:
        if set(row)=={'text','sha256'}:
            text=row['text'];depth=0
            if not isinstance(text,str):raise ValueError('Text must be a string')
        elif set(row)=={'base','prefix','suffix','insert','sha256'}:
            base,prefix,suffix=(row[k]for k in ('base','prefix','suffix'))
            if (any(type(v)is not int for v in (base,prefix,suffix))
                    or not 0<=base<len(texts) or min(prefix,suffix)<0
                    or prefix+suffix>len(texts[base]) or not isinstance(row['insert'],str)
                    or depths[base]>=4):raise ValueError('Invalid evidence text delta')
            old=texts[base];text=old[:prefix]+row['insert']+(old[len(old)-suffix:]if suffix else '')
            depth=depths[base]+1
        else:raise ValueError('Invalid evidence text record')
        if hashlib.sha256(text.encode()).hexdigest()!=row['sha256']:raise ValueError('Evidence text digest mismatch')
        texts.append(text);depths.append(depth)

    def decode(node):
        if not isinstance(node,list) or not node:raise ValueError('Invalid evidence node')
        kind=node[0]
        if kind=='value' and len(node)==2:
            if node[1] is not None and type(node[1])not in (str,bool,int,float):raise ValueError('Invalid scalar')
            return node[1]
        if kind=='text' and len(node)==2 and type(node[1])is int and 0<=node[1]<len(texts):return texts[node[1]]
        if kind=='array' and len(node)==2:return [decode(v)for v in node[1]]
        if kind=='object' and len(node)==2:
            pairs=node[1]
            if any(not isinstance(p,list) or len(p)!=2 or not isinstance(p[0],str)for p in pairs):raise ValueError('Invalid object')
            if len({p[0]for p in pairs})!=len(pairs):raise ValueError('Duplicate object keys')
            return {k:decode(v)for k,v in pairs}
        if kind=='json_text' and len(node)==4 and type(node[1])is bool and type(node[2])is bool:
            options={'ensure_ascii':node[1],'allow_nan':False}
            if node[2]:options['separators']=(',',':')
            return json.dumps(decode(node[3]),**options)
        raise ValueError('Invalid evidence node')
    result=decode(packet['root'])
    if digest(result)!=packet['source_sha256']:raise ValueError('Reconstructed evidence digest mismatch')
    return result
