"""Preserve the exact native complete13 navigation baseline and selected guard."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,tarfile
from .io_utils import atomic_write_json
from .reddit_native_read_runtime import validate_complete_snapshot
from .site_navigation_rules import require_admission

SCOPE='Native navigation only, with two full writable resets and grouped complete13 guards; not reading or querying.'
def enabled(c,p):
    return c.get('domain')=='reddit' and bool(c.get('completion')) and p.get('scope')==SCOPE and 'native_capture_archive' in p

def fingerprint(value):
    # Historical controls used the default JSON separators, not compact JSON.
    validate_complete_snapshot(value)
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

@lru_cache(maxsize=8)
def _original(path,sha):
    p=Path(path)
    if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Native navigation archive changed')
    names={f'cycle-{i}/{n}.json'for i in (0,1)for n in ('protected-before','protected-after','reset')};values={}
    with tarfile.open(p,'r|gz')as t:
        for m in t:
            if m.name not in names:continue
            if not m.isfile()or m.name in values:raise ValueError('Invalid native navigation guard member')
            values[m.name]=json.load(t.extractfile(m))
    if set(values)!=names:raise ValueError('Incomplete native navigation guard evidence')
    return values

def expected(c,p):
    if not enabled(c,p):raise ValueError('Explicit complete13 navigation admission required')
    require_admission(c,p)
    if len(p['cycles'])!=2:raise ValueError('Two complete native navigation reset cycles required')
    a=p['native_capture_archive'];values=_original(a['path'],a['sha256']);hashes=[]
    for i,row in enumerate(p['cycles']):
        before,after=(values[f'cycle-{i}/protected-{phase}.json']for phase in ('before','after'));reset=values[f'cycle-{i}/reset.json']
        h=fingerprint(before)
        if before!=after or h!=row['initial_fingerprint'] or h!=row['final_fingerprint'] or row.get('reset_receipt')!=reset:raise ValueError('Native navigation baseline proof differs')
        if reset.get('full_writable_state')is not True or reset.get('native_services_restarted')is not True or reset.get('restore',{}).get('restore_complete')is not True:raise ValueError('Complete native reset missing')
        hashes.append(h)
    if hashes[0]!=hashes[1]:raise ValueError('Native navigation baseline differs across resets')
    return hashes[0]

def capture(site,c,p,directory,phase):
    if phase not in ('before','after'):raise ValueError('Invalid protection phase')
    expected(c,p)
    from .reddit_native_read_protection import complete_snapshot
    value=complete_snapshot(site,Path(directory)/('navigation-native-guard-'+phase))
    atomic_write_json(Path(directory)/('navigation-complete13-'+phase+'.json'),value)
    atomic_write_json(Path(directory)/('navigation-selected-'+phase+'.json'),{'fingerprint':site.fingerprint()})
    return fingerprint(value)

def selected_integrity(directory):
    try:
        a,b=(json.loads((Path(directory)/('navigation-selected-'+p+'.json')).read_text())for p in ('before','after'))
        return isinstance(a.get('fingerprint'),str)and len(a['fingerprint'])==64 and a==b
    except (OSError,ValueError,TypeError):return False
