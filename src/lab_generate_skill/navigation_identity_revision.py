"""Allow narrowly evidenced heading corrections for never-generated recovery.

This changes only page-identity predicates. Source/start/goal/split and every
other completion condition must remain identical. Both old native control
cycles must discriminate after correction, including the forged URL/title case.
"""
import hashlib,json
from pathlib import Path
from .site_navigation_rules import control_admission
from urllib.parse import urlsplit


def corrects_native_heading_only(new,old):
    try:
        revision=new['completion_revision']
        if revision.get('kind')!='native-heading-v1' or set(revision)!={'kind','evidence'}:return False
        if {k:v for k,v in new.items()if k not in ('completion','completion_revision')}!={k:v for k,v in old.items()if k!='completion'}:return False
        a,b=new['completion'],old['completion']
        if {k:v for k,v in a.items()if k not in ('heading_regex','identity_source')}!={k:v for k,v in b.items()if k not in ('heading_regex','identity_source')}:return False
        if a.get('identity_source','heading')!='heading' or not a.get('heading_regex')or a==b:return False
        if not old.get('verify_url_only')or len(revision['evidence'])!=2:return False
        cycles=set()
        for item in revision['evidence']:
            folder=Path(item['directory']);cycle=folder.parent.name
            if folder.name!=old['task_id']or cycle not in ('cycle-0','cycle-1')or cycle in cycles:return False
            cycles.add(cycle);cases={}
            if set(item['files'])!={'initial_no_op','positive','wrong_target','url_only','404','login'}:return False
            for name,digest in item['files'].items():
                file=folder/(name+'.json');data=file.read_bytes()
                if hashlib.sha256(data).hexdigest()!=digest:return False
                cases[name]=json.loads(data)['page']
            origin=urlsplit(cases['positive']['url']);origin=origin.scheme+'://'+origin.netloc
            if not control_admission(new,cases,site_origin=origin)['passed']:return False
            # An old binding that already passed these controls needs no repair.
            if control_admission(old,cases,site_origin=origin)['passed']:return False
        return cycles=={'cycle-0','cycle-1'}
    except (KeyError,TypeError,ValueError,OSError):return False
