"""Reuse the exact complete13 read guard without relabeling it as selected-state hash."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import hashlib,json,tarfile
from .reddit_native_read_runtime import validate_complete_snapshot
from .io_utils import atomic_write_json

VERSION='reddit-query-retained-complete13-v1'
def enabled(c,p):
    return c.get('domain')=='reddit'and bool(c.get('query'))and 'original_capture_archive'in p

def fingerprint(snapshot):
    value=validate_complete_snapshot(snapshot)
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@lru_cache(maxsize=8)
def _captured(path,sha,pins_json):
    p=Path(path)
    if p.is_symlink()or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Original native guard archive changed')
    pins=json.loads(pins_json);data={}
    with tarfile.open(p,'r|gz')as packet:
        for m in packet:
            if m.name not in pins:continue
            if not m.isfile()or m.name in data:raise ValueError('Invalid native guard member')
            body=packet.extractfile(m).read()
            if pins[m.name]!={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}:raise ValueError('Original native guard member changed')
            data[m.name]=json.loads(body)
    if set(data)!=set(pins):raise ValueError('Original native guard evidence missing')
    return data

def expected(c,p):
    if not enabled(c,p):
        cycles=p.get('cycles',[])
        values=[x.get('initial_fingerprint')for x in cycles]
        if len(values)!=2 or not all(isinstance(v,str)and v for v in values)or values[0]!=values[1]:
            raise ValueError('Query admission lacks matching runtime initial fingerprints')
        return values[0]
    if p.get('sql_and_native_ui_verified')is not True or p.get('reset_mode')!='two_full_restores_same_factory':
        raise ValueError('Explicit actual complete13 retained proof required')
    cycles=p.get('cycles',[])
    if len(cycles)!=2:raise ValueError('Two complete13 native reset cycles required')
    names=[]
    for i,cycle in enumerate(cycles):
        expected_names=[f'cycle-{i}/protected-before.json',f'cycle-{i}/protected-after.json']
        if cycle.get('guard_members')!=expected_names or cycle.get('reset_member')!=f'cycle-{i}/reset.json':raise ValueError('Exact cycle guard members required')
        names+=expected_names+[cycle['reset_member']]
    pins={n:p['original_members'][n]for n in names};archive=p['original_capture_archive']
    data=_captured(archive['path'],archive['sha256'],json.dumps(pins,sort_keys=True));hashes=[]
    for cycle in cycles:
        before,after=(data[n]for n in cycle['guard_members']);reset=data[cycle['reset_member']]
        hashes.extend([fingerprint(before),fingerprint(after)])
        if reset.get('full_writable_state')is not True or reset.get('native_services_restarted')is not True or reset.get('restore',{}).get('restore_complete')is not True:
            raise ValueError('Actual complete writable-state reset absent')
    if len(set(hashes))!=1:raise ValueError('Native full13 baseline differs across controls/resets')
    return hashes[0]

def capture(site,c,p,directory,phase):
    expected(c,p)
    from .reddit_native_read_protection import complete_snapshot
    value=complete_snapshot(site,Path(directory)/('query-native-guard-'+phase))
    atomic_write_json(Path(directory)/('query-complete13-'+phase+'.json'),value)
    atomic_write_json(Path(directory)/('query-selected-'+phase+'.json'),{'fingerprint':site.fingerprint()})
    return fingerprint(value)

def selected_integrity(directory):
    try:
        a,b=(json.loads((Path(directory)/('query-selected-'+phase+'.json')).read_text())for phase in('before','after'))
        return isinstance(a.get('fingerprint'),str)and bool(a['fingerprint'])and a==b
    except (OSError,ValueError,TypeError):return False
