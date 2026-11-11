"""Current native Map lifecycles bound to immutable retained source proofs.

This supplies archived bytes, not old executable modules. The ordinary runner,
public interfaces and full native admission gates remain authoritative. A batch
reads each shared archive once and restores only its declared source subtrees.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace

from . import native_goal_dispatch as dispatch
from . import map_native_facts_runtime as facts
from . import map_history_layer_runtime as finite
from . import map_native_route_runtime as routes
from . import map_export_runtime as exports
from . import map_native_layer_runtime as layers
from . import original_map_proof_archive as archive
from .original_map_proof_glob import supplier_with_glob

def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_gate(contract, proof):
    protocols = [m for m in (facts, finite, routes, exports) if m.enabled(contract)]
    if len(protocols) != 1:
        raise ValueError('Exactly one supported retained Map lifecycle required')
    protocols[0].require_admission(contract, proof)
    return protocols[0]


class RetainedMapSourceContext:
    """Owned by ReviewedMapRegistry; no independent runtime entry."""
    def __init__(self, config, *, read_pinned):
        self.stack = ExitStack()
        self.sources = {}; self.descriptors = {}; self.proofs = {}; self.profile_layers = {}
        self.control_archives_read = 0
        self.closed = False
        self.read_pinned = read_pinned
        try:
            records = self.json(config['source_registry'])['sources']
            plan = self.json(config['profile_plan'])
            if (plan.get('version') != 'map16-reviewed-normal-integration-v1'
                    or plan.get('source_registry', {}).get('sha256') != config['source_registry']['sha256']
                    or plan.get('source_registry', {}).get('path') != config['source_registry']['path']
                    or plan.get('source_count') != len(records)):
                raise ValueError('Original source registry/profile plan binding changed')
            selected = config['source_ids']
            if not selected or len(set(selected)) != len(selected):
                raise ValueError('Distinct selected retained Map sources required')
            known = {r['source_task_id']:r for r in records}
            if len(known) != len(records) or not set(selected) <= known.keys():
                raise ValueError('Retained Map source membership changed')
            groups = {}
            for group in plan['profile_groups']:
                if type(group.get('map_native_layers')) is not bool:
                    raise ValueError('Explicit native Map layer profile required')
                for sid in group['source_ids']:
                    if sid in groups:
                        raise ValueError('Duplicate Map startup profile source')
                    groups[sid] = (group['name'],group['map_native_layers'])
            selected_rows = []
            for sid in selected:
                row = known[sid]; c = self.json(row['original_contract']); proof = self.json(row['proof'])
                if (c.get('source_task_id') != sid or c.get('task_id') != row['task_id']
                        or c.get('domain') != 'map' or c.get('heldout_quarantine') is not False
                        or sid not in groups or groups[sid][0] != row['profile_group']):
                    raise ValueError('Retained Map definition/scope/profile changed')
                for ref in row['full_gate_reviews']:
                    self.json(ref)
                for key in ('original_archive_refs','durable_original_byte_suppliers','original_producer_output_directories'):
                    if row[key] != proof[key]:
                        raise ValueError('Original source proof supplier changed')
                self.sources[sid] = c; self.proofs[sid] = proof
                self.descriptors[sid] = deepcopy(proof)
                self.profile_layers[sid] = groups[sid][1]
                selected_rows.append(row)
            temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='current-map-proofs-'))
            restored = self.restore(selected_rows, Path(temporary))
            self.stack.enter_context(supplier_with_glob(archive.original_path_suppliers)(restored))
            for sid, c in self.sources.items():
                source_gate(c,self.proofs[sid])
            adapter = SimpleNamespace(**{k:getattr(finite,k) for k in (
                'enabled','require_admission','require_original_binding','NativeReadHooks','public_goal','fields','feedback')},
                FEEDBACK_VERSIONS=(finite.VERSION,),AUTHORIZED_TARGET_WRITES=False)
            dispatch.register_protocol('current_retained_map_finite',adapter)
            self.stack.callback(dispatch.unregister_protocol,'current_retained_map_finite',adapter)
            self.stack.enter_context(layers.reviewed_source_profiles(
                [(c,self.profile_layers[sid])for sid,c in self.sources.items()]))
        except BaseException:
            self.close()
            raise

    def json(self, ref):
        return json.loads(self.read_pinned(ref['path'],ref['sha256']))

    def restore(self, rows, root):
        wanted = {}
        for row in rows:
            proof = self.proofs[row['source_task_id']]
            sequences = [proof[k] for k in ('durable_original_byte_suppliers','original_archive_refs','original_producer_output_directories')]
            if {len(v)for v in sequences} != {2}:
                raise ValueError('Two complete original source suppliers required')
            for supplier,ref,out in zip(*sequences):
                key = ref['archive']['path']
                record = wanted.setdefault(key,{'ref':ref,'names':set()})
                if record['ref'] != ref:
                    raise ValueError('Shared control archive references conflict')
                for field in ('archive_file','member_map_file'):
                    name = ref['member_prefix']+'/'+Path(supplier[field]).relative_to(out).as_posix()
                    record['names'].add(archive.safe(name))
        cache = {}
        for key,record in wanted.items():
            ref = record['ref']; index = self.json(ref['member_manifest']); receipt = self.json(ref['receipt'])
            if receipt['archive_sha256'] != ref['archive']['sha256']:
                raise ValueError('Control archive/receipt binding differs')
            raw = self.read_pinned(key,ref['archive']['sha256'])
            actual = {}; kept = {}
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                for member in tar:
                    name = archive.safe(member.name)
                    if name in actual:
                        raise ValueError('Duplicate control archive member')
                    if member.issym():
                        actual[name] = {'type':'symlink','link_target':member.linkname}
                    elif member.isfile():
                        body = tar.extractfile(member).read()
                        actual[name] = {'bytes':len(body),'sha256':digest(body)}
                        if name in record['names']:
                            kept[name] = body
                    else:
                        raise ValueError('Unsupported control archive member')
            if (actual != index['files'] or len(actual) != receipt['raw_member_count']
                    or kept.keys() != record['names']):
                raise ValueError('Complete original control archive differs')
            cache[key] = actual,kept
            self.control_archives_read += 1
        restored = []
        supplied = supplier_with_glob(archive.original_path_suppliers)
        for row in rows:
            sid = row['source_task_id'];proof = self.proofs[sid]
            for i,(supplier,ref,out) in enumerate(zip(proof['durable_original_byte_suppliers'],proof['original_archive_refs'],proof['original_producer_output_directories'])):
                expected,kept = cache[ref['archive']['path']]
                base = root/sid/str(i);base.mkdir(parents=True)
                portable = {'restore_root':base,'aliases':{},'files':{}}
                for field in ('archive_file','member_map_file'):
                    original = supplier[field];name=ref['member_prefix']+'/'+Path(original).relative_to(out).as_posix()
                    target = base/Path(original).name;target.write_bytes(kept[name])
                    portable['aliases'][original] = target
                    portable['files'][target.name] = expected[name]
                with supplied([portable]):
                    restored.append(archive.restore_source(supplier,base/'members',
                        original_files=expected,original_prefix=ref['member_prefix']))
        return restored

    def close(self):
        self.stack.close()
        self.closed = True
