"""Valid private CPU wrong-field fixtures for shipped Postmill constraints.

The declared target, actor, evaluator and success conditions remain unchanged.
A valid wrong value must save before its exact-field failure is meaningful.
"""
import copy,hashlib,json,re
VERSION='reddit-valid-private-forum-negative-v1'
LIMITS={'name':(3,25),'title':(1,100),'description':(1,300),'sidebar':(1,1500)}

def validate_fields(spec):
    if not isinstance(spec,dict)or set(spec)-set(LIMITS)-{'tags'}or not set(LIMITS)<=set(spec):raise ValueError('Four exact original forum fields required')
    for field,(minimum,maximum)in LIMITS.items():
        value=spec[field]
        if not isinstance(value,str)or not value.strip()or not minimum<=len(value)<=maximum:raise ValueError('Original native forum field fails length: '+field)
    if not re.fullmatch('[A-Za-z0-9_]+',spec['name']):raise ValueError('Private fixture requires a native ASCII word forum name')
    if 'tags'in spec and(not isinstance(spec['tags'],list)or not 1<=len(spec['tags'])<=5 or any(not isinstance(s,str)or not s.strip()for s in spec['tags'])or len(set(spec['tags']))!=len(spec['tags'])):raise ValueError('Native tag count/values required')

def negative_fields(spec,wrong,baseline):
    validate_fields(spec)
    if wrong not in set(LIMITS)|({'tags'}if 'tags'in spec else set()):raise ValueError('One supported wrong field required')
    if not isinstance(baseline,dict)or not isinstance(baseline.get('forums'),list):raise ValueError('Original native forum-name baseline required')
    names=set()
    for row in baseline['forums']:
        if not isinstance(row,dict)or not isinstance(row.get('name'),str):raise ValueError('Complete native name baseline required')
        names.add(row['name'].casefold())
    result=copy.deepcopy(spec)
    if wrong=='tags':
        candidate='control_'+hashlib.sha256(json.dumps(spec['tags'],separators=(',',':')).encode()).hexdigest()[:12]
        while candidate in spec['tags']:candidate+='x'
        result['tags']=[candidate]
    else:
        for index in range(4096):
            seed=VERSION+'\0'+wrong+'\0'+spec[wrong]+'\0'+str(index)
            candidate='Control_'+hashlib.sha256(seed.encode()).hexdigest()[:16]
            if candidate!=spec[wrong]and(wrong!='name'or candidate.casefold()not in names):break
        else:raise ValueError('No unused bounded native forum fixture name available')
        result[wrong]=candidate
    validate_fields(result)
    if sum(result[k]!=spec[k]for k in spec)!=1:raise ValueError('Negative fixture changed more than one original field')
    return result
