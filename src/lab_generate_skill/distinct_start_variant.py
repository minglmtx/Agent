"""Explicit task-start variants without weakening task-family split isolation.

This separates only reviewed, different source records. It cannot retry the
same source, ignore shared traces, or transfer an old score to a new start.
Every other source reservation remains pinned and every native gate still runs.
"""
import json
from pathlib import Path
from .source_revision_binding import binding, fingerprint, local_path
from .initialization_continuation import pinned, digest
from .io_utils import atomic_write_json

VERSION='reviewed-distinct-start-variant-v1'
NAME='distinct-start-variant.json'


def same_recorded_starts(declaration, original):
    """Read pinned older path-only provenance without changing old evidence."""
    urls=declaration.get('recorded_start_urls')
    if urls is not None:
        return urls==original['recorded_start_urls']
    # No inference from a lone start_path: every source start must be declared.
    return declaration.get('recorded_start_paths')==list(map(local_path,original['recorded_start_urls']))


class VariantAuthority:
    def __init__(self,base,wave,selected,spec):
        from prepare_admitted_site_actor import inventory_aliases
        self.base=Path(base).resolve();self.wave=Path(wave).resolve();self.spec=spec
        self.file=self.wave/NAME;self.sha=digest(self.file)
        if (spec.get('version')!=VERSION or spec.get('wave')!=str(self.wave)
                or self.wave.parent!=self.base or len(selected)!=1):
            raise ValueError('One explicitly reviewed variant and wave required')
        c=selected[0];binding(c);self.source=c['source_task_id']
        if (spec.get('source_task_id')!=self.source or spec.get('candidate_sha256')!=fingerprint(c)
                or spec.get('prior_score_reused')is not False or not spec.get('reason')):
            raise ValueError('Exact candidate mapping and independent scoring required')
        invpin=spec['inventory']
        if Path(invpin['path'])!=self.base/'inventory.jsonl':raise ValueError('Original inventory required')
        inventory=[json.loads(line)for line in pinned(invpin['path'],invpin['sha256']).decode().splitlines()]
        rows={r['task_id']:r for r in inventory};self.family=inventory_aliases(inventory)[self.source]
        if len(self.family)<2 or any(rows[s].get('heldout_quarantine')is not False for s in self.family):
            raise ValueError('Entire task family must be unquarantined')
        own=rows[self.source]
        if (own['domain']!=c['domain'] or own['goal']!=c['original_goal']
                or own['source_trace_ids']!=c['source_trace_ids']
                or own['recorded_start_urls']!=c['recorded_start_urls']):
            raise ValueError('Variant changed authoritative source')
        traces=set(own['source_trace_ids']);starts=set(map(local_path,own['recorded_start_urls']))
        for sid in self.family-{self.source}:
            other=rows[sid]
            if (not other.get('source_trace_ids')or not other.get('recorded_start_urls')
                    or traces&set(other['source_trace_ids'])
                    or starts&set(map(local_path,other['recorded_start_urls']))):
                raise ValueError('Shared or unknown source traces/starts cannot separate attempts')
        self.manifests={};covered=set()
        for pin in spec['sibling_manifests']:
            path=Path(pin['path'])
            if (path.parent.parent!=self.base or path.parent==self.wave
                    or not path.name.startswith(('contracts','tasks')) or path.suffix!='.jsonl'):
                raise ValueError('Exact sibling reservation required')
            records=[json.loads(line)for line in pinned(pin['path'],pin['sha256']).decode().splitlines()]
            matches=[r for r in records if r.get('source_task_id',r['task_id'])in self.family-{self.source}]
            if not matches or path in self.manifests:raise ValueError('Unique sibling manifest required')
            for old in matches:
                sid=old.get('source_task_id',old['task_id']);original=rows[sid]
                if (old['domain']!=c['domain'] or old.get('source_trace_ids')!=original['source_trace_ids']
                        or not same_recorded_starts(old,original)
                        or not old.get('start_path')
                        or local_path(old['start_path'])not in set(map(local_path,original['recorded_start_urls']))
                        or local_path(old['start_path'])==local_path(c['start_path'])):
                    raise ValueError('Sibling actual declaration must have a distinct verified start')
                covered.add(sid)
            self.manifests[path]=pin
        if covered!=self.family-{self.source}:raise ValueError('Every family sibling needs reviewed reservations')
        self.key=self.source+'-'+fingerprint(c)
        self.lease=self.base/'.first-actor-variant-claims'/self.key
        self.owner=dict(version=VERSION,wave=str(self.wave),source_task_id=self.source,
                        candidate_sha256=fingerprint(c),authorization_sha256=self.sha)
        self.check_lease()

    def permits_sibling(self,path,contract):
        sid=contract.get('source_task_id',contract['task_id']);path=Path(path)
        if sid not in self.family-{self.source}:return False
        if path not in self.manifests:raise ValueError('Unreviewed sibling reservation remains blocked')
        pinned(self.manifests[path]['path'],self.manifests[path]['sha256'])
        return True

    def check_lease(self):
        if self.lease.parent.is_symlink()or self.lease.is_symlink():raise ValueError('Unsafe variant lease')
        if self.lease.exists():
            file=self.lease/'claim.json'
            if not file.is_file()or file.is_symlink()or json.loads(file.read_text())!=self.owner:
                raise ValueError('Another or incomplete variant claim blocks submission')

    def acquire(self):
        self.check_lease();self.lease.parent.mkdir(exist_ok=True);self.lease.mkdir()
        atomic_write_json(self.lease/'claim.json',self.owner)


def load(base,wave,selected):
    path=Path(wave)/NAME
    if not path.exists():return None
    if path.is_symlink():raise ValueError('Variant declaration must be regular')
    return VariantAuthority(base,wave,selected,json.loads(path.read_text()))
